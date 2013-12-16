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

"""Tests for the Juju GUI server authentication management."""

import datetime
import unittest

import mock
from tornado.testing import LogTrapTestCase

from guiserver import auth
from guiserver.tests import helpers


class TestUser(unittest.TestCase):

    def test_authenticated_repr(self):
        # An authenticated user is correctly represented.
        user = auth.User(
            username='the-doctor', password='bad-wolf', is_authenticated=True)
        expected = '<User: the-doctor (authenticated)>'
        self.assertEqual(expected, repr(user))

    def test_not_authenticated_repr(self):
        # A not authenticated user is correctly represented.
        user = auth.User(
            username='the-doctor', password='bad-wolf', is_authenticated=False)
        expected = '<User: the-doctor (not authenticated)>'
        self.assertEqual(expected, repr(user))

    def test_anonymous_repr(self):
        # An anonymous user is correctly represented.
        user = auth.User()
        expected = '<User: anonymous (not authenticated)>'
        self.assertEqual(expected, repr(user))

    def test_str(self):
        # The string representation of an user is correctly generated.
        user = auth.User(username='the-doctor')
        self.assertEqual('the-doctor', str(user))


class AuthMiddlewareTestMixin(object):
    """Include tests for the AuthMiddleware.

    Subclasses must subclass one of the API test mixins in helpers.
    """

    def setUp(self):
        self.user = auth.User()
        self.io_loop = mock.Mock()
        self.write_message = mock.Mock()
        self.tokens = auth.AuthenticationTokenHandler(io_loop=self.io_loop)
        self.auth = auth.AuthMiddleware(
            self.user, self.get_auth_backend(), self.tokens,
            self.write_message)

    def assert_user(self, username, password, is_authenticated):
        """Ensure the current user reflects the given values."""
        user = self.user
        self.assertEqual(username, user.username)
        self.assertEqual(password, user.password)
        self.assertEqual(is_authenticated, user.is_authenticated)

    def test_login_request(self):
        # The authentication process starts if a login request is processed.

        request = self.make_login_request(username='user', password='passwd')
        response = self.auth.process_request(request)
        self.assertEqual(request, response)
        self.assertTrue(self.auth.in_progress())
        self.assert_user('', '', False)

    def test_login_success(self):
        # The user is logged in if the authentication process completes.
        request = self.make_login_request(username='user', password='passwd')
        self.auth.process_request(request)
        response = self.make_login_response()
        result = self.auth.process_response(response)
        self.assertEqual(response, result)
        self.assertFalse(self.auth.in_progress())
        self.assert_user('user', 'passwd', True)

    def test_login_failure(self):
        # The user is not logged in if the authentication process fails.
        request = self.make_login_request()
        self.auth.process_request(request)
        response = self.make_login_response(successful=False)
        result = self.auth.process_response(response)
        self.assertEqual(response, result)
        self.assertFalse(self.auth.in_progress())
        self.assert_user('', '', False)

    def test_request_mismatch(self):
        # The authentication fails if the request and response identifiers
        # don't match.
        request = self.make_login_request(
            request_id=42, username='user', password='passwd')
        self.auth.process_request(request)
        response = self.make_login_response(request_id=47)
        self.auth.process_response(response)
        self.assertTrue(self.auth.in_progress())
        self.assert_user('', '', False)

    def test_multiple_auth_requests(self):
        # The last authentication request is honored.
        request1 = self.make_login_request(request_id=1)
        request2 = self.make_login_request(
            request_id=2, username='user2', password='passwd2')
        self.auth.process_request(request1)
        self.auth.process_request(request2)
        # The first response arrives.
        response = self.make_login_response(request_id=1)
        self.auth.process_response(response)
        # The user is authenticated but the auth is still in progress.
        self.assertTrue(self.user.is_authenticated)
        self.assertTrue(self.auth.in_progress())
        # The second response arrives.
        response = self.make_login_response(request_id=2)
        self.auth.process_response(response)
        # The user logged in and the auth process completed.
        self.assert_user('user2', 'passwd2', True)
        self.assertFalse(self.auth.in_progress())

    def test_request_id_is_zero(self):
        # The authentication process starts if a login request is processed
        # and the request id is zero.
        request = self.make_login_request(request_id=0)
        self.auth.process_request(request)
        self.assertTrue(self.auth.in_progress())


class TestGoAuthMiddleware(
        helpers.GoAPITestMixin, AuthMiddlewareTestMixin,
        LogTrapTestCase, unittest.TestCase):

    def test_token_login_request(self):
        # The authentication process starts with a token login request also.
        request = self.make_token_login_request(
            self.tokens, username='user', password='passwd')
        response = self.auth.process_request(request)
        # The response now looks as if it were made without a token.
        self.assertEqual(
            self.make_login_request(username='user', password='passwd'),
            response)
        self.assertTrue(self.auth.in_progress())
        self.assert_user('', '', False)
        self.assertFalse(self.write_message.called)

    def test_token_login_success(self):
        # The user is logged in if the authentication process completes.
        request = self.make_token_login_request(
            self.tokens, username='user', password='passwd')
        self.auth.process_request(request)
        response = self.make_login_response()
        result = self.auth.process_response(response)
        self.assertEqual(
            dict(RequestId=42,
                 Response=dict(AuthTag='user', Password='passwd')),
            result)
        self.assertFalse(self.auth.in_progress())
        self.assert_user('user', 'passwd', True)
        self.assertFalse(self.write_message.called)

    def test_token_login_failure(self):
        # The user is not logged in if the authentication process fails.
        request = self.make_token_login_request(
            self.tokens, username='user', password='passwd')
        self.auth.process_request(request)
        response = self.make_login_response(successful=False)
        result = self.auth.process_response(response)
        self.assertEqual(response, result)
        self.assertFalse(self.auth.in_progress())
        self.assert_user('', '', False)
        self.assertFalse(self.write_message.called)

    def test_token_login_missing(self):
        # The user is not logged in if the authentication process fails.
        request = self.make_token_login_request()
        response = self.auth.process_request(request)
        # None is a marker indicating that the request has been handled and
        # should not be continued on through to Juju.
        self.assertIsNone(response)
        self.write_message.assert_called_once_with(dict(
            RequestId=42,
            Error='unknown, fulfilled, or expired token',
            ErrorCode='unauthorized access',
            Response={}))
        self.assertFalse(self.auth.in_progress())
        self.assert_user('', '', False)


class TestPythonAuthMiddleware(
        helpers.PythonAPITestMixin, AuthMiddlewareTestMixin,
        LogTrapTestCase, unittest.TestCase):
    pass


class BackendTestMixin(object):
    """Include tests for the authentication backends.

    Subclasses must subclass one of the API test mixins in helpers.
    """

    def setUp(self):
        self.backend = self.get_auth_backend()

    def test_get_request_id(self):
        # The request id is correctly returned.
        request = self.make_login_request(request_id=42)
        self.assertEqual(42, self.backend.get_request_id(request))

    def test_get_request_id_failure(self):
        # If the request id cannot be found, None is returned.
        self.assertIsNone(self.backend.get_request_id({}))

    def test_request_is_login(self):
        # True is returned if a login request is passed.
        request = self.make_login_request()
        self.assertTrue(self.backend.request_is_login(request))

    def test_get_credentials(self):
        # The user name and password are returned parsing the login request.
        request = self.make_login_request(username='user', password='passwd')
        username, password = self.backend.get_credentials(request)
        self.assertEqual('user', username)
        self.assertEqual('passwd', password)

    def test_login_succeeded(self):
        # True is returned if the login attempt succeeded.
        response = self.make_login_response()
        self.assertTrue(self.backend.login_succeeded(response))

    def test_login_failed(self):
        # False is returned if the login attempt failed.
        response = self.make_login_response(successful=False)
        self.assertFalse(self.backend.login_succeeded(response))

    def test_make_request(self):
        expected = self.make_login_request(
            request_id=42, username='user', password='passwd')
        self.assertEqual(
            expected, self.backend.make_request(42, 'user', 'passwd'))


class TestGoBackend(
        helpers.GoAPITestMixin, BackendTestMixin, unittest.TestCase):

    def test_request_is_not_login(self):
        # False is returned if the passed data is not a login request.
        requests = (
            {},
            {
                'RequestId': 1,
                'Type': 'INVALID',
                'Request': 'Login',
                'Params': {'AuthTag': 'user', 'Password': 'passwd'},
            },
            {
                'RequestId': 2,
                'Type': 'Admin',
                'Request': 'INVALID',
                'Params': {'AuthTag': 'user', 'Password': 'passwd'},
            },
            {
                'RequestId': 3,
                'Type': 'Admin',
                'Request': 'Login',
                'Params': {'Password': 'passwd'},
            },
        )
        for request in requests:
            is_login = self.backend.request_is_login(request)
            self.assertFalse(is_login, request)


class TestPythonBackend(
        helpers.PythonAPITestMixin, BackendTestMixin, unittest.TestCase):

    def test_request_is_not_login(self):
        # False is returned if the passed data is not a login request.
        requests = (
            {},
            {
                'request_id': 42,
                'op': 'INVALID',
                'user': 'user',
                'password': 'passwd',
            },
            {
                'request_id': 42,
                'op': 'login',
                'password': 'passwd',
            },
            {
                'request_id': 42,
                'op': 'login',
                'user': 'user',
            },
        )
        for request in requests:
            is_login = self.backend.request_is_login(request)
            self.assertFalse(is_login, request)


class TestAuthenticationTokenHandler(LogTrapTestCase, unittest.TestCase):

    def setUp(self):
        super(TestAuthenticationTokenHandler, self).setUp()
        self.io_loop = mock.Mock()
        self.max_life = datetime.timedelta(minutes=1)
        self.tokens = auth.AuthenticationTokenHandler(
            self.max_life, self.io_loop)

    def test_explicit_initialization(self):
        # The class accepted the explicit initialization.
        self.assertEqual(self.max_life, self.tokens._max_life)
        self.assertEqual(self.io_loop, self.tokens._io_loop)
        self.assertEqual({}, self.tokens._data)

    @mock.patch('tornado.ioloop.IOLoop.current',
                mock.Mock(return_value='mockloop'))
    def test_default_initialization(self):
        # The class has sane initialization defaults.
        tokens = auth.AuthenticationTokenHandler()
        self.assertEqual(
            datetime.timedelta(minutes=2), tokens._max_life)
        self.assertEqual('mockloop', tokens._io_loop)

    def test_token_requested(self):
        # It recognizes a token request.
        requests = (
            dict(RequestId=42, Type='GUIToken', Request='Create'),
            dict(RequestId=22, Type='GUIToken', Request='Create', Params={}))
        for request in requests:
            is_token_requested = self.tokens.token_requested(request)
            self.assertTrue(is_token_requested, request)

    def test_not_token_requested(self):
        # It rejects invalid token requests.
        requests = (
            dict(),
            dict(Type='GUIToken', Request='Create'),
            dict(RequestId=42, Request='Create'),
            dict(RequestId=42, Type='GUIToken'))
        for request in requests:
            token_requested = self.tokens.token_requested(request)
            self.assertFalse(token_requested, request)

    @mock.patch('uuid.uuid4', mock.Mock(return_value=mock.Mock(hex='DEFACED')))
    @mock.patch('datetime.datetime',
                mock.Mock(
                    **{'utcnow.return_value':
                       datetime.datetime(2013, 11, 21, 21)}))
    def test_process_token_request(self):
        # It correctly responds to token requests.
        user = auth.User('user-admin', 'ADMINSECRET', True)
        write_message = mock.Mock()
        data = dict(RequestId=42, Type='GUIToken', Request='Create')
        self.tokens.process_token_request(data, user, write_message)
        write_message.assert_called_once_with(dict(
            RequestId=42,
            Response=dict(
                Token='DEFACED',
                Created='2013-11-21T21:00:00Z',
                Expires='2013-11-21T21:01:00Z'
            )
        ))
        self.assertTrue('DEFACED' in self.tokens._data)
        self.assertEqual(
            {'username', 'password', 'handle'},
            set(self.tokens._data['DEFACED'].keys()))
        self.assertEqual(
            user.username, self.tokens._data['DEFACED']['username'])
        self.assertEqual(
            user.password, self.tokens._data['DEFACED']['password'])
        self.assertEqual(
            self.max_life, self.io_loop.add_timeout.call_args[0][0])
        self.assertTrue('DEFACED' in self.tokens._data)
        expire_token = self.io_loop.add_timeout.call_args[0][1]
        expire_token()
        self.assertFalse('DEFACED' in self.tokens._data)

    def test_unauthenticated_process_token_request(self):
        # Unauthenticated token requests get an informative error.
        user = auth.User(is_authenticated=False)
        write_message = mock.Mock()
        data = dict(RequestId=42, Type='GUIToken', Request='Create')
        self.tokens.process_token_request(data, user, write_message)
        write_message.assert_called_once_with(dict(
            RequestId=42,
            Error='tokens can only be created by authenticated users.',
            ErrorCode='unauthorized access',
            Response={}
        ))
        self.assertEqual({}, self.tokens._data)
        self.assertFalse(self.io_loop.add_timeout.called)

    def test_authentication_requested(self):
        # It recognizes an authentication request.
        request = dict(
            RequestId=42, Type='GUIToken', Request='Login',
            Params={'Token': 'DEFACED'})
        auth_requested = self.tokens.authentication_requested(request)
        self.assertTrue(auth_requested, request)

    def test_not_authentication_requested(self):
        # It rejects invalid authentication requests.
        requests = (
            dict(),
            dict(Type='GUIToken', Request='Login', Params={'Token': 'T'}),
            dict(RequestId=42, Request='Login', Params={'Token': 'DEFACED'}),
            dict(RequestId=42, Type='GUIToken', Params={'Token': 'DEFACED'}),
            dict(RequestId=42, Type='GUIToken', Request='Login'),
            dict(RequestId=42, Type='GUIToken', Request='Login', Params={}))
        for request in requests:
            auth_requested = self.tokens.authentication_requested(request)
            self.assertFalse(auth_requested, request)

    def test_known_authentication_request(self):
        # It correctly responds to authentication requests with known tokens.
        username = 'user-admin'
        password = 'ADMINSECRET'
        self.tokens._data['DEFACED'] = dict(
            handle='handle marker', username=username, password=password)
        request = dict(
            RequestId=42, Type='GUIToken', Request='Login',
            Params={'Token': 'DEFACED'})
        write_message = mock.Mock()
        self.assertEqual(
            (username, password),
            self.tokens.process_authentication_request(request, write_message))
        self.io_loop.remove_timeout.assert_called_once_with('handle marker')
        self.assertFalse(write_message.called)
        self.assertFalse('DEFACED' in self.tokens._data)

    def test_unknown_authentication_request(self):
        # It correctly rejects authentication requests with unknown tokens.
        request = dict(
            RequestId=42, Type='GUIToken', Request='Login',
            Params={'Token': 'DEFACED'})
        write_message = mock.Mock()
        self.assertEqual(
            None,
            self.tokens.process_authentication_request(request, write_message))
        self.assertFalse(self.io_loop.remove_timeout.called)
        write_message.assert_called_once_with(dict(
            RequestId=42,
            Error='unknown, fulfilled, or expired token',
            ErrorCode='unauthorized access',
            Response={}))

    @mock.patch('uuid.uuid4', mock.Mock(return_value=mock.Mock(hex='DEFACED')))
    @mock.patch('datetime.datetime',
                mock.Mock(
                    **{'utcnow.return_value':
                       datetime.datetime(2013, 11, 21, 21)}))
    def test_token_request_and_authentication_collaborate(self):
        # process_token_request and process_authentication_request collaborate.
        # This is a small integration test of the two functions' interaction.
        user = auth.User('user-admin', 'ADMINSECRET', True)
        write_message = mock.Mock()
        request = dict(RequestId=42, Type='GUIToken', Request='Create')
        self.tokens.process_token_request(request, user, write_message)
        request = dict(
            RequestId=43, Type='GUIToken', Request='Login',
            Params={'Token': 'DEFACED'})
        self.assertEqual(
            (user.username, user.password),
            self.tokens.process_authentication_request(request, write_message))

    def test_process_authentication_response(self):
        # It translates a normal authentication success.
        user = auth.User('user-admin', 'ADMINSECRET', True)
        response = {'RequestId': 42, 'Response': {}}
        self.assertEqual(
            dict(RequestId=42,
                 Response=dict(AuthTag=user.username, Password=user.password)),
            self.tokens.process_authentication_response(response, user))
