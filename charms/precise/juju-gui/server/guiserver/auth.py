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

"""Juju GUI server authentication management.

This module includes the pieces required to process user authentication.

    - User: this is a simple data structure representing a logged in or
      anonymous user.
    - Authentication backends (GoBackend and PythonBackend): the primary
      purpose of auth backends is to provide the logic to parse requests' data
      based on the API implementation currently in use. They can also be used
      to create authentication requests.  They must implement the following
      interface:
        - get_request_id(data) -> id or None;
        - request_is_login(data) -> bool;
        - get_credentials(data) -> (str, str);
        - login_succeeded(data) -> bool; and
        - make_request(request_id, username, password) -> dict.
      Backends don't know anything about the authentication process or the
      current user, and are not intended to store state: one backend (the one
      suitable for the current API implementation) is instantiated once when
      the application is bootstrapped and used as a singleton by all WebSocket
      requests.
    - AuthMiddleware: this middleware processes authentication requests and
      responses, using the backend to parse the WebSocket messages, logging in
      the current user if the authentication succeeds.
    - AuthenticationTokenHandler: This handles authentication token creation
      and usage requests.  It is used both by the AuthMiddleware and by
      handlers.WebSocketHandler in the ``on_message`` and ``on_juju_message``
      methods.
"""

import datetime
import logging
import uuid

from tornado.ioloop import IOLoop


class User(object):
    """The current WebSocket user."""

    def __init__(self, username='', password='', is_authenticated=False):
        self.is_authenticated = is_authenticated
        self.username = username
        self.password = password

    def __repr__(self):
        if self.is_authenticated:
            status = 'authenticated'
        else:
            status = 'not authenticated'
        username = self.username or 'anonymous'
        return '<User: {} ({})>'.format(username, status)

    def __str__(self):
        return self.username.encode('utf-8')


class AuthMiddleware(object):
    """Handle user authentication.

    This class handles the process of authenticating the provided user using
    the given auth backend. Note that, since the GUI just disconnects when the
    user logs out, there is no need to handle the log out process.
    """

    def __init__(self, user, backend, tokens, write_message):
        self._user = user
        self._backend = backend
        self._tokens = tokens
        self._write_message = write_message
        self._request_ids = {}

    def in_progress(self):
        """Return True if authentication is in progress, False otherwise.
        """
        return bool(self._request_ids)

    def process_request(self, data):
        """Parse the WebSocket data arriving from the client.

        Start the authentication process if data represents a login request
        performed by the GUI user.
        """
        backend = self._backend
        tokens = self._tokens
        request_id = backend.get_request_id(data)
        if request_id is not None:
            credentials = None
            is_token = False
            if backend.request_is_login(data):
                credentials = backend.get_credentials(data)
            elif tokens.authentication_requested(data):
                is_token = True
                credentials = tokens.process_authentication_request(
                    data, self._write_message)
                if credentials is None:
                    # This means that the tokens object handled the request.
                    return None
                else:
                    # We need a "real" authentication request.
                    data = backend.make_request(request_id, *credentials)
            if credentials is not None:
                # Stashing credentials is a security risk.  We currently deem
                # this risk to be acceptably small.  Even keeping an
                # authenticated websocket in memory seems to be of a similar
                # risk profile, and we cannot operate without that.
                self._request_ids[request_id] = dict(
                    is_token=is_token,
                    username=credentials[0],
                    password=credentials[1])
        return data

    def process_response(self, data):
        """Parse the WebSocket data arriving from the Juju API server.

        Complete the authentication process if data represents the response
        to a login request previously initiated. Authenticate the user if the
        authentication succeeded.
        """
        request_id = self._backend.get_request_id(data)
        if request_id in self._request_ids:
            info = self._request_ids.pop(request_id)
            user = self._user
            logged_in = self._backend.login_succeeded(data)
            if logged_in:
                # Stashing credentials is a security risk.  We currently deem
                # this risk to be acceptably small.  Even keeping an
                # authenticated websocket in memory seems to be of a similar
                # risk profile, and we cannot operate without that.
                user.username = info['username']
                user.password = info['password']
                logging.info('auth: user {} logged in'.format(user))
                user.is_authenticated = True
                if info['is_token']:
                    data = self._tokens.process_authentication_response(
                        data, user)
        return data


class GoBackend(object):
    """Authentication backend for the Juju Go API implementation.

    A login request looks like the following:

        {
            'RequestId': 42,
            'Type': 'Admin',
            'Request': 'Login',
            'Params': {'AuthTag': 'user-admin', 'Password': 'ADMIN-SECRET'},
        }

    Here is an example of a successful login response:

        {'RequestId': 42, 'Response': {}}

    A login failure response is like the following:

        {
            'RequestId': 42,
            'Error': 'invalid entity name or password',
            'ErrorCode': 'unauthorized access',
            'Response': {},
        }
    """

    def get_request_id(self, data):
        """Return the request identifier associated with the provided data."""
        return data.get('RequestId')

    def request_is_login(self, data):
        """Return True if data represents a login request, False otherwise."""
        params = data.get('Params', {})
        return (
            data.get('Type') == 'Admin' and
            data.get('Request') == 'Login' and
            'AuthTag' in params and
            'Password' in params
        )

    def get_credentials(self, data):
        """Parse the provided login data and return username and password."""
        params = data['Params']
        return params['AuthTag'], params['Password']

    def login_succeeded(self, data):
        """Return True if data represents a successful login, False otherwise.
        """
        return 'Error' not in data

    def make_request(self, request_id, username, password):
        """Create and return an authentication request."""
        return dict(
            RequestId=request_id,
            Type='Admin',
            Request='Login',
            Params=dict(AuthTag=username, Password=password))


class PythonBackend(object):
    """Authentication backend for the Juju Python implementation.

    A login request looks like the following:

        {
            'request_id': 42,
            'op': 'login',
            'user': 'admin',
            'password': 'ADMIN-SECRET',
        }

    A successful login response includes these fields:

        {
            'request_id': 42,
            'op': 'login',
            'user': 'admin',
            'password': 'ADMIN-SECRET',
            'result': True,
        }

    A login failure response is like the following:

        {
            'request_id': 42,
            'op': 'login',
            'user': 'admin',
            'password': 'ADMIN-SECRET',
            'err': True,
        }
    """

    def get_request_id(self, data):
        """Return the request identifier associated with the provided data."""
        return data.get('request_id')

    def request_is_login(self, data):
        """Return True if data represents a login request, False otherwise."""
        op = data.get('op')
        return (op == 'login') and ('user' in data) and ('password' in data)

    def get_credentials(self, data):
        """Parse the provided login data and return username and password."""
        return data['user'], data['password']

    def login_succeeded(self, data):
        """Return True if data represents a successful login, False otherwise.
        """
        return data.get('result') and not data.get('err')

    def make_request(self, request_id, username, password):
        """Create and return an authentication request."""
        return dict(
            request_id=request_id,
            op='login',
            user=username,
            password=password)


def get_backend(apiversion):
    """Return the auth backend instance to use for the given API version."""
    backend_class = {'go': GoBackend, 'python': PythonBackend}[apiversion]
    return backend_class()


class AuthenticationTokenHandler(object):
    """Handle requests related to authentication tokens.

    A token creation request looks like the following:

        {
            'RequestId': 42,
            'Type': 'GUIToken',
            'Request': 'Create',
            'Params': {},
        }

    Here is an example of a successful token creation response.

        {
            'RequestId': 42,
            'Response': {
                'Token': 'TOKEN-STRING',
                'Created': '2013-11-21T12:34:46.778866Z',
                'Expires': '2013-11-21T12:36:46.778866Z'
            }
        }

    If the user is not authenticated, the failure response will look like this.

        {
            'RequestId': 42,
            'Error': 'tokens can only be created by authenticated users.',
            'ErrorCode': 'unauthorized access',
            'Response': {},
        }

    A token authentication request looks like the following:

        {
            'RequestId': 42,
            'Type': 'GUIToken',
            'Request': 'Login',
            'Params': {'Token': 'TOKEN-STRING'},
        }

    Here is an example of a successful login response:

        {
            'RequestId': 42,
            'Response': {'AuthTag': 'user-admin', 'Password': 'ADMIN-SECRET'}
        }

    A login failure response is like the following:

        {
            'RequestId': 42,
            'Error': 'unknown, fulfilled, or expired token',
            'ErrorCode': 'unauthorized access',
            'Response': {},
        }

    Juju itself might return a failure response like the following, but this
    would be difficult or impossible to trigger as of this writing:

        {
            'RequestId': 42,
            'Error': 'invalid entity name or password',
            'ErrorCode': 'unauthorized access',
            'Response': {},
        }
    """

    def __init__(self, max_life=datetime.timedelta(minutes=2), io_loop=None):
        self._max_life = max_life
        if io_loop is None:
            io_loop = IOLoop.current()
        self._io_loop = io_loop
        self._data = {}

    def token_requested(self, data):
        """Does data represent a token creation request?  True or False."""
        return (
            'RequestId' in data and
            data.get('Type', None) == 'GUIToken' and
            data.get('Request', None) == 'Create'
        )

    def process_token_request(self, data, user, write_message):
        """Create a single-use, time-expired token and send it back."""
        if not user.is_authenticated:
            write_message(dict(
                RequestId=data['RequestId'],
                Error='tokens can only be created by authenticated users.',
                ErrorCode='unauthorized access',
                Response={}))
            return
        token = uuid.uuid4().hex

        def expire_token():
            self._data.pop(token, None)
            logging.info('auth: expired token {}'.format(token))
        handle = self._io_loop.add_timeout(self._max_life, expire_token)
        now = datetime.datetime.utcnow()
        # Stashing these is a security risk.  We currently deem this risk to
        # be acceptably small.  Even keeping an authenticated websocket in
        # memory seems to be of a similar risk profile, and we cannot operate
        # without that.
        self._data[token] = dict(
            username=user.username,
            password=user.password,
            handle=handle
            )
        write_message({
            'RequestId': data['RequestId'],
            'Response': {
                'Token': token,
                'Created': now.isoformat() + 'Z',
                'Expires': (now + self._max_life).isoformat() + 'Z'
            }
        })

    def authentication_requested(self, data):
        """Does data represent a token authentication request? True or False.
        """
        params = data.get('Params', {})
        return (
            'RequestId' in data and
            data.get('Type') == 'GUIToken' and
            data.get('Request') == 'Login' and
            'Token' in params
        )

    def process_authentication_request(self, data, write_message):
        """Get the credentials for the token, or send an error."""
        token = data['Params']['Token']
        credentials = self._data.pop(token, None)
        if credentials is not None:
            logging.info('auth: using token {}'.format(token))
            self._io_loop.remove_timeout(credentials['handle'])
            return credentials['username'], credentials['password']
        else:
            write_message({
                'RequestId': data['RequestId'],
                'Error': 'unknown, fulfilled, or expired token',
                'ErrorCode': 'unauthorized access',
                'Response': {},
            })
            # None is an explicit return marker to say "I handled this".
            # It is returned by default.

    def process_authentication_response(self, data, user):
        """Make a successful token authentication response.

        This includes the username and password so that clients can then use
        them.  For instance, the GUI stashes them in session storage so that
        reloading the page does not require logging in again."""
        return {
            'RequestId': data['RequestId'],
            'Response': {'AuthTag': user.username, 'Password': user.password}
        }
