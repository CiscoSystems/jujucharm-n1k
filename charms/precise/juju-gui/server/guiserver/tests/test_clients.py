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

"""Tests for the Juju GUI server clients."""

from tornado import (
    concurrent,
    web,
)
from tornado.testing import (
    AsyncHTTPSTestCase,
    gen_test,
)

from guiserver import clients
from guiserver.tests import helpers


class TestWebSocketClientConnection(AsyncHTTPSTestCase, helpers.WSSTestMixin):

    def get_app(self):
        # In this test case the WebSocket client is connected to a WebSocket
        # echo server returning received messages.
        self.received = []
        self.server_closed_future = concurrent.Future()
        options = {
            'close_future': self.server_closed_future,
            'io_loop': self.io_loop,
        }
        return web.Application([(r'/', helpers.EchoWebSocketHandler, options)])

    def connect(self, headers=None):
        """Return a future whose result is a connected client."""
        return clients.websocket_connect(
            self.io_loop, self.get_wss_url('/'), self.received.append,
            headers=headers)

    @gen_test
    def test_initial_connection(self):
        # The client correctly establishes a connection to the server.
        yield self.connect()

    @gen_test
    def test_send_receive(self):
        # The client correctly sends and receives messages on the secure
        # WebSocket connection.
        client = yield self.connect()
        client.write_message('hello')
        message = yield client.read_message()
        self.assertEqual('hello', message)

    @gen_test
    def test_callback(self):
        # The client executes the given callback each time a message is
        # received.
        client = yield self.connect()
        client.write_message('hello')
        client.write_message('world')
        # Read the two messages.
        yield client.read_message()
        yield client.read_message()
        # Ensure the provided callback has been called both times.
        self.assertEqual(['hello', 'world'], self.received)

    @gen_test
    def test_customized_headers(self):
        # Customized headers can be passed when connecting the WebSocket.
        origin = self.get_url('/')
        client = yield self.connect(headers={'Origin': origin})
        headers = client.request.headers
        self.assertIn('Origin', headers)
        self.assertEqual(origin, headers['Origin'])

    @gen_test
    def test_connection_close(self):
        # The client connection is correctly terminated.
        client = yield self.connect()
        yield client.close()
        message = yield client.read_message()
        self.assertIsNone(message)
        yield self.server_closed_future
