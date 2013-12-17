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

"""Juju GUI server applications."""

import os
import time

from tornado import web
from tornado.options import options

from guiserver import (
    auth,
    handlers,
)
from guiserver.bundles.base import Deployer


def server():
    """Return the main server application.

    The server app is responsible for serving the WebSocket connection, the
    Juju GUI static files and the main index file for dynamic URLs.
    """
    # Set up static paths.
    guiroot = options.guiroot
    static_path = os.path.join(guiroot, 'juju-ui')
    # Set up the bundle deployer.
    deployer = Deployer(options.apiurl, options.apiversion,
                        options.charmworldurl)
    # Set up handlers.
    server_handlers = []
    if not options.sandbox:
        tokens = auth.AuthenticationTokenHandler()
        websocket_handler_options = {
            # The Juju API backend url.
            'apiurl': options.apiurl,
            # The backend to use for user authentication.
            'auth_backend': auth.get_backend(options.apiversion),
            # The Juju deployer to use for importing bundles.
            'deployer': deployer,
            # The tokens collection for authentication token requests.
            'tokens': tokens,
        }
        server_handlers.append(
            # Handle WebSocket connections.
            (r'^/ws$', handlers.WebSocketHandler, websocket_handler_options),
        )
    if options.testsroot:
        params = {'path': options.testsroot, 'default_filename': 'index.html'}
        server_handlers.append(
            # Serve the Juju GUI tests.
            (r'^/test/(.*)', web.StaticFileHandler, params),
        )
    info_handler_options = {
        'apiurl': options.apiurl,
        'apiversion': options.apiversion,
        'deployer': deployer,
        'sandbox': options.sandbox,
        'start_time': int(time.time()),
    }
    server_handlers.extend([
        # Handle static files.
        (r'^/juju-ui/(.*)', web.StaticFileHandler, {'path': static_path}),
        (r'^/(favicon\.ico)$', web.StaticFileHandler, {'path': guiroot}),
        # Handle GUI server info.
        (r'^/gui-server-info', handlers.InfoHandler, info_handler_options),
        # Any other path is served by index.html.
        (r'^/(.*)', handlers.IndexHandler, {'path': guiroot}),
    ])
    return web.Application(server_handlers, debug=options.debug)


def redirector():
    """Return the redirector application.

    The redirector app is responsible for redirecting HTTP traffic to HTTPS.
    """
    return web.Application([
        # Redirect all HTTP traffic to HTTPS.
        (r'.*', handlers.HttpsRedirectHandler),
    ], debug=options.debug)
