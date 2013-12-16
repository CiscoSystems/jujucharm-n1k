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

"""Juju GUI server websocket clients."""

from tornado import (
    concurrent,
    httpclient,
    websocket,
)


def websocket_connect(io_loop, url, on_message_callback, headers=None):
    """WebSocket client connection factory.

    The client factory receives the following arguments:
        - io_loop: the Tornado IO loop instance;
        - url: the WebSocket URL to use for the connection;
        - on_message_callback: a callback that will be called each time
          a new message is received by the client;
        - headers (optional): a dict of additional headers to include in the
          client handshake.

    Return a Future whose result is a WebSocketClientConnection.
    """
    request = httpclient.HTTPRequest(
        url, validate_cert=False, request_timeout=100)
    if headers is not None:
        request.headers.update(headers)
    conn = WebSocketClientConnection(io_loop, request, on_message_callback)
    return conn.connect_future


class WebSocketClientConnection(websocket.WebSocketClientConnection):
    """WebSocket client connection supporting secure WebSockets.

    Use this connection as described in
    <http://www.tornadoweb.org/en/stable/websocket.html#client-side-support>.
    """

    def __init__(self, io_loop, request, on_message_callback):
        """Client initializer.

        The WebSocket client receives all the arguments accepted by
        tornado.websocket.WebSocketClientConnection and a callback that will be
        called each time a new message is received by the client.
        """
        super(WebSocketClientConnection, self).__init__(io_loop, request)
        self._on_message_callback = on_message_callback
        self.close_future = concurrent.Future()

    def on_message(self, message):
        """Hook called when a new message is received.

        The on_message_callback is called passing it the message.
        """
        super(WebSocketClientConnection, self).on_message(message)
        self._on_message_callback(message)

    def close(self):
        """Close the client connection.

        Return a Future that is fired when the connection is terminated.
        """
        self.stream.close()
        return self.close_future

    def _on_close(self):
        """Fire the close_future and send a None message."""
        super(WebSocketClientConnection, self)._on_close()
        # Since this is just a notification the Future result is set to None.
        self.close_future.set_result(None)
