# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2013 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Juju GUI server HTTP/HTTPS handlers."""

from collections import deque
import logging
import os
import time

from tornado import (
    escape,
    gen,
    web,
    websocket,
)
from tornado.ioloop import IOLoop

from guiserver import get_version
from guiserver.auth import (
    AuthMiddleware,
    User,
)
from guiserver.bundles.base import DeployMiddleware
from guiserver.clients import websocket_connect
from guiserver.utils import (
    get_headers,
    json_decode_dict,
    request_summary,
    wrap_write_message,
)


class WebSocketHandler(websocket.WebSocketHandler):
    """WebSocket handler supporting secure WebSockets.

    This handler acts as a proxy between the browser connection and the
    Juju API server. It also handles API authentication and requests for
    bundles deployment (using the juju-deployer deployment format).

    Relevant attributes:

      - connected: True if the current browser is connected, False otherwise;
      - juju_connected: True if the Juju API is connected, False otherwise;
      - juju_connection: the WebSocket client connection to the Juju API.

    Callbacks:

      - on_message(message): called when a message arrives from the browser;
      - on_juju_message(message): called when a message arrives from Juju;
      - on_close(): called when the browser closes the connection;
      - on_juju_close(): called when juju closes the connection.

    Methods:
      - write_message(message): send a message to the browser;
      - close(): terminate the browser connection.
    """

    @gen.coroutine
    def initialize(self, apiurl, auth_backend, deployer, tokens, io_loop=None):
        """Initialize the WebSocket server.

        Create a new WebSocket client and connect it to the Juju API.
        Set up the authentication system.
        Handle the queued messages.
        """
        if io_loop is None:
            io_loop = IOLoop.current()
        self._io_loop = io_loop
        self._summary = request_summary(self.request) + ' '
        logging.info(self._summary + 'client connected')
        self.connected = True
        self.juju_connected = False
        self._juju_message_queue = queue = deque()
        # Set up the authentication infrastructure.
        self.tokens = tokens
        write_message = wrap_write_message(self)
        self.user = User()
        self.auth = AuthMiddleware(
            self.user, auth_backend, tokens, write_message)
        # Set up the bundle deployment infrastructure.
        self.deployment = DeployMiddleware(self.user, deployer, write_message)
        # Juju requires the Origin header to be included in the WebSocket
        # client handshake request. Propagate the client origin if present;
        # use the Juju API server as origin otherwise.
        headers = get_headers(self.request, apiurl)
        # Connect the WebSocket client to the Juju API server.
        self._juju_connected_future = websocket_connect(
            io_loop, apiurl, self.on_juju_message, headers=headers)
        try:
            self.juju_connection = yield self._juju_connected_future
        except Exception as err:
            logging.error(self._summary + 'unable to connect to the Juju API')
            logging.exception(err)
            self.connected = False
            raise gen.Return()
        # At this point the Juju API is successfully connected.
        self.juju_connected = True
        logging.info(self._summary + 'Juju API connected')
        # Send all the messages that have been enqueued before the connection
        # to the Juju API server was established.
        while self.connected and self.juju_connected and len(queue):
            message = queue.popleft()
            encoded = message.encode('utf-8')
            logging.debug(self._summary + 'queue -> juju: {}'.format(encoded))
            self.juju_connection.write_message(message)

    def select_subprotocol(self, subprotocols):
        """Return the first sub-protocol sent by the client.

        If the client does not include sub-protocols in the
        Sec-WebSocket-Protocol header, this method is not called.

        Overriding this method is required due to a new behavior of development
        versions of the Chrome browser, which disconnects if if the
        sub-protocol does not match the one sent by the client.
        """
        return subprotocols[0]

    def on_message(self, message):
        """Hook called when a new message is received from the browser.

        If the message is a deployment request, start the deployment process.
        Otherwise the message is propagated to the Juju API server.
        Messages sent before the client connection to the Juju API server is
        established are queued for later delivery.
        """
        data = json_decode_dict(message)
        encoded = None
        if data is not None:
            # Handle deployment requests.
            if self.deployment.requested(data):
                return self.deployment.process_request(data)
            # Handle authentication requests.
            if not self.user.is_authenticated:
                new_data = self.auth.process_request(data)
                if new_data is None:
                    # The None marker indicates that a response was sent.
                    return
                elif new_data != data:
                    encoded = escape.json_encode(new_data)
                    message = encoded.decode('utf8')
            # Handle authentication token requests.
            if self.tokens.token_requested(data):
                return self.tokens.process_token_request(
                    data, self.user, wrap_write_message(self))
        # Propagate messages to the Juju API server.
        if encoded is None:
            encoded = message.encode('utf-8')
        if self.juju_connected:
            logging.debug(self._summary + 'client -> juju: {}'.format(encoded))
            return self.juju_connection.write_message(message)
        logging.debug(self._summary + 'client -> queue: {}'.format(encoded))
        self._juju_message_queue.append(message)

    def on_juju_message(self, message):
        """Hook called when a new message is received from the Juju API server.

        The message is propagated to the browser.
        """
        if message is None:
            # The Juju API closed the connection.
            return self.on_juju_close()
        data = json_decode_dict(message)
        if (data is not None) and self.auth.in_progress():
            encoded = escape.json_encode(
                self.auth.process_response(data))
            message = encoded.decode('utf8')
        else:
            encoded = message.encode('utf-8')
        logging.debug(self._summary + 'juju -> client: {}'.format(encoded))
        self.write_message(message)

    def on_close(self):
        """Hook called when the WebSocket connection is terminated."""
        logging.info(self._summary + 'client connection closed')
        self.connected = False
        # At this point the WebSocket client connection to the Juju API server
        # might not yet be established. For this reason the connection is
        # terminated adding a callback to the corresponding future.
        callback = lambda _: self.juju_connection.close()
        self._io_loop.add_future(self._juju_connected_future, callback)

    def on_juju_close(self):
        """Hook called when the WebSocket connection to Juju is terminated."""
        logging.info(self._summary + 'Juju API connection closed')
        self.juju_connected = False
        self.juju_connection = None
        # Usually the Juju API connection is terminated as a consequence of a
        # browser disconnection. A server disconnection is unexpected and
        # unlikely to happen. In the future Juju will support HA and we will
        # need to react accordingly to server disconnections, but for the time
        # being we just disconnect the browser and log an error.
        if self.connected:
            logging.error(self._summary + 'Juju API unexpectedly disconnected')
            self.close()


class IndexHandler(web.StaticFileHandler):
    """Serve all requests using the index.html file placed in the static root.
    """

    @classmethod
    def get_absolute_path(cls, root, path):
        """See tornado.web.StaticFileHandler.get_absolute_path."""
        return os.path.join(root, 'index.html')


class InfoHandler(web.RequestHandler):
    """Return information about the GUI server."""

    def initialize(self, apiurl, apiversion, deployer, sandbox, start_time):
        """Initialize the handler."""
        self.apiurl = apiurl
        self.apiversion = apiversion
        self.deployer = deployer
        self.sandbox = sandbox
        self.start_time = start_time

    def get_info(self, settings):
        return {
            'apiurl': self.apiurl,
            'apiversion': self.apiversion,
            'debug': settings.get('debug', False),
            'deployer': self.deployer.status(),
            'sandbox': self.sandbox,
            'uptime': int(time.time()) - self.start_time,
            'version': get_version(),
        }

    def get(self):
        """Handle GET requests."""
        info = self.get_info(self.application.settings)
        # In Tornado Web handlers, just writing a dict JSON encodes the
        # response contents and sets the proper content type header
        # (application/json; charset=UTF-8).
        self.write(info)


class HttpsRedirectHandler(web.RequestHandler):
    """Permanently redirect all the requests to the equivalent HTTPS URL."""

    def get(self):
        """Handle GET requests."""
        request = self.request
        url = 'https://{}{}'.format(request.host, request.uri)
        self.redirect(url, permanent=True)
