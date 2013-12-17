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

"""Tests for the deployment utility functions and objects."""

import unittest

from concurrent.futures import Future
import mock
from tornado import gen
from tornado.testing import(
    AsyncTestCase,
    ExpectLog,
    gen_test,
    LogTrapTestCase,
)
import urllib

from guiserver import watchers
from guiserver.bundles import utils
from guiserver.tests import helpers
from jujuclient import EnvError

mock_time = mock.patch('time.time', mock.Mock(return_value=12345))


@mock_time
class TestCreateChange(unittest.TestCase):

    def test_status(self):
        # The change includes the deployment status.
        expected = {'DeploymentId': 0, 'Status': utils.STARTED, 'Time': 12345}
        obtained = utils.create_change(0, utils.STARTED)
        self.assertEqual(expected, obtained)

    def test_queue(self):
        # The change includes the deployment queue length.
        expected = {
            'DeploymentId': 1,
            'Status': utils.SCHEDULED,
            'Time': 12345,
            'Queue': 42,
        }
        obtained = utils.create_change(1, utils.SCHEDULED, queue=42)
        self.assertEqual(expected, obtained)

    def test_error(self):
        # The change includes a deployment error.
        expected = {
            'DeploymentId': 2,
            'Status': utils.COMPLETED,
            'Time': 12345,
            'Error': 'an error',
        }
        obtained = utils.create_change(2, utils.COMPLETED, error='an error')
        self.assertEqual(expected, obtained)

    def test_all_params(self):
        # The change includes all the parameters.
        expected = {
            'DeploymentId': 3,
            'Status': utils.COMPLETED,
            'Time': 12345,
            'Queue': 47,
            'Error': 'an error',
        }
        obtained = utils.create_change(
            3, utils.COMPLETED, queue=47, error='an error')
        self.assertEqual(expected, obtained)


class TestMessageFromError(LogTrapTestCase, unittest.TestCase):

    def test_with_message(self):
        # The error message is logged and returned.
        expected_type = "error type: <type 'exceptions.ValueError'>"
        expected_message = 'error message: bad wolf'
        with ExpectLog('', expected_type, required=True):
            with ExpectLog('', expected_message, required=True):
                error = utils.message_from_error(ValueError('bad wolf'))
        self.assertEqual('bad wolf', error)

    def test_env_error_extracted(self):
        # An EnvError as returned from the Go environment is not suitable for
        # display to the user.  The Error field is extracted and returned.
        expected_type = "error type: <class 'jujuclient.EnvError'>"
        expected_message = 'error message: cannot parse json'
        with ExpectLog('', expected_type, required=True):
            with ExpectLog('', expected_message, required=True):
                exception = EnvError({'Error': 'cannot parse json'})
                error = utils.message_from_error(exception)
        self.assertEqual('cannot parse json', error)

    def test_without_message(self):
        # A placeholder message is returned.
        expected_type = "error type: <type 'exceptions.SystemExit'>"
        expected_message = 'empty error message'
        with ExpectLog('', expected_type, required=True):
            with ExpectLog('', expected_message, required=True):
                error = utils.message_from_error(SystemExit())
        self.assertEqual('no further details can be provided', error)


class TestObserver(LogTrapTestCase, unittest.TestCase):

    def setUp(self):
        self.observer = utils.Observer()

    def assert_deployment(self, deployment_id):
        """Ensure the given deployment id is being observed.

        Also check that a watcher is associated with the given deployment id.
        Return the watcher.
        """
        deployments = self.observer.deployments
        self.assertIn(deployment_id, deployments)
        watcher = deployments[deployment_id]
        self.assertIsInstance(watcher, watchers.AsyncWatcher)
        return watcher

    def assert_watcher(self, watcher_id, deployment_id):
        """Ensure the given watcher id is associated with the deployment id."""
        watchers = self.observer.watchers
        self.assertIn(watcher_id, watchers)
        self.assertEqual(deployment_id, watchers[watcher_id])

    def test_initial(self):
        # A newly created observer does not contain deployments.
        self.assertEqual({}, self.observer.deployments)
        self.assertEqual({}, self.observer.watchers)

    def test_add_deployment(self):
        # A new deployment is correctly added to the observer.
        deployment_id = self.observer.add_deployment()
        self.assertEqual(1, len(self.observer.deployments))
        self.assert_deployment(deployment_id)

    def test_add_deployment_logs(self):
        # A new deployment is properly logged.
        with ExpectLog('', 'deployment 0 scheduled', required=True):
            self.observer.add_deployment()

    def test_add_multiple_deployments(self):
        # Multiple deployments can be added to the observer.
        deployment1 = self.observer.add_deployment()
        deployment2 = self.observer.add_deployment()
        self.assertNotEqual(deployment1, deployment2)
        self.assertEqual(2, len(self.observer.deployments))
        watcher1 = self.assert_deployment(deployment1)
        watcher2 = self.assert_deployment(deployment2)
        self.assertNotEqual(watcher1, watcher2)

    def test_add_watcher(self):
        # A new watcher is correctly added to the observer.
        deployment_id = self.observer.add_deployment()
        watcher_id = self.observer.add_watcher(deployment_id)
        self.assertEqual(1, len(self.observer.watchers))
        self.assert_watcher(watcher_id, deployment_id)

    def test_add_multiple_watchers(self):
        # Multiple watchers can be added to the observer.
        deployment1 = self.observer.add_deployment()
        deployment2 = self.observer.add_deployment()
        watcher1 = self.observer.add_watcher(deployment1)
        watcher2 = self.observer.add_watcher(deployment2)
        self.assertNotEqual(watcher1, watcher2)
        self.assertEqual(2, len(self.observer.watchers))
        self.assert_watcher(watcher1, deployment1)
        self.assert_watcher(watcher2, deployment2)

    @mock_time
    def test_notify_scheduled(self):
        # It is possible to notify a new queue position for a deployment.
        deployment_id = self.observer.add_deployment()
        watcher = self.observer.deployments[deployment_id]
        self.observer.notify_position(deployment_id, 3)
        expected = {
            'DeploymentId': deployment_id,
            'Status': utils.SCHEDULED,
            'Time': 12345,
            'Queue': 3,
        }
        self.assertEqual(expected, watcher.getlast())
        self.assertFalse(watcher.closed)

    @mock_time
    def test_notify_started(self):
        # It is possible to notify that a deployment is (about to be) started.
        deployment_id = self.observer.add_deployment()
        watcher = self.observer.deployments[deployment_id]
        self.observer.notify_position(deployment_id, 0)
        expected = {
            'DeploymentId': deployment_id,
            'Status': utils.STARTED,
            'Time': 12345,
            'Queue': 0,
        }
        self.assertEqual(expected, watcher.getlast())
        self.assertFalse(watcher.closed)

    @mock_time
    def test_notify_cancelled(self):
        # It is possible to notify that a deployment has been cancelled.
        deployment_id = self.observer.add_deployment()
        watcher = self.observer.deployments[deployment_id]
        self.observer.notify_cancelled(deployment_id)
        expected = {
            'DeploymentId': deployment_id,
            'Status': utils.CANCELLED,
            'Time': 12345,
        }
        self.assertEqual(expected, watcher.getlast())
        self.assertTrue(watcher.closed)

    def test_notify_cancelled_logs(self):
        # A deployment cancellation is properly logged.
        deployment_id = self.observer.add_deployment()
        expected = 'deployment {} cancelled'.format(deployment_id)
        with ExpectLog('', expected, required=True):
            self.observer.notify_cancelled(deployment_id)

    @mock_time
    def test_notify_completed(self):
        # It is possible to notify that a deployment is completed.
        deployment_id = self.observer.add_deployment()
        watcher = self.observer.deployments[deployment_id]
        self.observer.notify_completed(deployment_id)
        expected = {
            'DeploymentId': deployment_id,
            'Status': utils.COMPLETED,
            'Time': 12345,
        }
        self.assertEqual(expected, watcher.getlast())
        self.assertTrue(watcher.closed)

    def test_notify_completed_logs(self):
        # A deployment completion is properly logged.
        deployment_id = self.observer.add_deployment()
        expected = 'deployment {} completed'.format(deployment_id)
        with ExpectLog('', expected, required=True):
            self.observer.notify_completed(deployment_id)

    @mock_time
    def test_notify_error(self):
        # It is possible to notify that an error occurred during a deployment.
        deployment_id = self.observer.add_deployment()
        watcher = self.observer.deployments[deployment_id]
        self.observer.notify_completed(deployment_id, error='bad wolf')
        expected = {
            'DeploymentId': deployment_id,
            'Status': utils.COMPLETED,
            'Time': 12345,
            'Error': 'bad wolf',
        }
        self.assertEqual(expected, watcher.getlast())
        self.assertTrue(watcher.closed)


class TestPrepareConstraints(unittest.TestCase):

    def test_valid_constraints(self):
        # Valid constraints are returned as they are.
        constraints = {
            'arch': 'i386',
            'cpu-cores': 4,
            'cpu-power': 2,
            'mem': 2000,
        }
        self.assertEqual(constraints, utils._prepare_constraints(constraints))

    def test_valid_constraints_subset(self):
        # A subset of valid constraints is returned as it is.
        constraints = {'cpu-cores': '4', 'cpu-power': 2}
        self.assertEqual(constraints, utils._prepare_constraints(constraints))

    def test_invalid_constraints(self):
        # A ValueError is raised if unsupported constraints are found.
        with self.assertRaises(ValueError) as context_manager:
            utils._prepare_constraints({'arch': 'i386', 'not-valid': 'bang!'})
        self.assertEqual(
            'unsupported constraints: not-valid',
            str(context_manager.exception))

    def test_string_constraints(self):
        # String constraints are converted to a dict.
        constraints = 'arch=i386,cpu-cores=4,cpu-power=2,mem=2000'
        expected = {
            'arch': 'i386',
            'cpu-cores': '4',
            'cpu-power': '2',
            'mem': '2000',
        }
        self.assertEqual(expected, utils._prepare_constraints(constraints))

    def test_string_constraints_subset(self):
        # A subset of string constraints is converted to a dict.
        constraints = 'cpu-cores=4,mem=2000'
        expected = {'cpu-cores': '4', 'mem': '2000'}
        self.assertEqual(expected, utils._prepare_constraints(constraints))

    def test_unsupported_string_constraints(self):
        # A ValueError is raised if unsupported string constraints are found.
        with self.assertRaises(ValueError) as context_manager:
            utils._prepare_constraints('cpu-cores=4,invalid1=1,invalid2=2')
        self.assertEqual(
            'unsupported constraints: invalid1, invalid2',
            str(context_manager.exception))

    def test_invalid_string_constraints(self):
        # A ValueError is raised if unsupported string constraints are found.
        with self.assertRaises(ValueError) as context_manager:
            utils._prepare_constraints('arch=,cpu-cores=,')
        self.assertEqual(
            'invalid constraints: arch=,cpu-cores=,',
            str(context_manager.exception))


class TestPrepareBundle(unittest.TestCase):

    def test_constraints_conversion(self):
        # Service constraints stored as strings are converted to a dict.
        bundle = {
            'services': {
                'django': {'constraints': 'arch=i386,cpu-cores=4,mem=2000'},
            },
        }
        expected = {
            'services': {
                'django': {
                    'constraints': {
                        'arch': 'i386',
                        'cpu-cores': '4',
                        'mem': '2000',
                    },
                },
            },
        }
        utils.prepare_bundle(bundle)
        self.assertEqual(expected, bundle)

    def test_constraints_deletion(self):
        # Empty service constraints are deleted.
        bundle = {'services': {'django': {'constraints': ''}}}
        expected = {'services': {'django': {}}}
        utils.prepare_bundle(bundle)
        self.assertEqual(expected, bundle)

    def test_no_constraints(self):
        # A bundle with no constraints is not modified.
        bundle = {'services': {'django': {}}}
        expected = bundle.copy()
        utils.prepare_bundle(bundle)
        self.assertEqual(expected, bundle)

    def test_dict_constraints(self):
        # A bundle with valid constraints as dict is not modified.
        bundle = {
            'services': {
                'django': {
                    'constraints': {
                        'arch': 'i386',
                        'cpu-cores': '4',
                        'mem': '2000',
                    },
                },
            },
        }
        expected = bundle.copy()
        utils.prepare_bundle(bundle)
        self.assertEqual(expected, bundle)

    def test_invalid_bundle(self):
        # A ValueError is raised if the bundle is not well structured.
        with self.assertRaises(ValueError) as context_manager:
            utils.prepare_bundle('invalid')
        self.assertEqual(
            'the bundle data is not well formed',
            str(context_manager.exception))

    def test_no_services(self):
        # A ValueError is raised if the bundle does not include services.
        with self.assertRaises(ValueError) as context_manager:
            utils.prepare_bundle({})
        self.assertEqual(
            'the bundle does not contain any services',
            str(context_manager.exception))


class TestRequireAuthenticatedUser(
        helpers.BundlesTestMixin, LogTrapTestCase, AsyncTestCase):

    deployer = 'fake-deployer'

    def make_view(self):
        """Return a view to be used for tests.

        The resulting callable must be called with a request object as first
        argument and with self.deployer as second argument.
        """
        @gen.coroutine
        @utils.require_authenticated_user
        def myview(request, deployer):
            """An example testing view."""
            self.assertEqual(self.deployer, deployer)
            raise utils.response(info='ok')
        return myview

    @gen_test
    def test_authenticated(self):
        # The view is executed normally if the user is authenticated.
        view = self.make_view()
        request = self.make_view_request(is_authenticated=True)
        response = yield view(request, self.deployer)
        self.assertEqual({'Response': 'ok'}, response)

    @gen_test
    def test_not_authenticated(self):
        # The view returns an error response if the user is not authenticated.
        view = self.make_view()
        request = self.make_view_request(is_authenticated=False)
        response = yield view(request, self.deployer)
        expected = {
            'Response': {},
            'Error': 'unauthorized access: no user logged in',
        }
        self.assertEqual(expected, response)

    def test_wrap(self):
        # The decorated view looks like the wrapped function.
        view = self.make_view()
        self.assertEqual('myview', view.__name__)
        self.assertEqual('An example testing view.', view.__doc__)


class TestResponse(LogTrapTestCase, unittest.TestCase):

    def assert_response(self, expected, response):
        """Ensure the given gen.Return instance contains the expected response.
        """
        self.assertIsInstance(response, gen.Return)
        self.assertEqual(expected, response.value)

    def test_empty(self):
        # An empty response is correctly generated.
        expected = {'Response': {}}
        response = utils.response()
        self.assert_response(expected, response)

    def test_success(self):
        # A success response is correctly generated.
        expected = {'Response': {'foo': 'bar'}}
        response = utils.response({'foo': 'bar'})
        self.assert_response(expected, response)

    def test_failure(self):
        # A failure response is correctly generated.
        expected = {'Error': 'an error occurred', 'Response': {}}
        response = utils.response(error='an error occurred')
        self.assert_response(expected, response)

    def test_log_failure(self):
        # An error log is written when a failure response is generated.
        with ExpectLog('', 'deployer: an error occurred', required=True):
            utils.response(error='an error occurred')


def mock_fetch_factory(response_code, called_with=None):
    def fetch(*args, **kwargs):
        if called_with is not None:
            called_with.append((args[1:], kwargs))

        class FakeResponse(object):
            pass

        resp = FakeResponse()
        resp.code = response_code
        future = Future()
        future.set_result(resp)
        return future
    return fetch


class TestIncrementDeploymentCounter(LogTrapTestCase, AsyncTestCase):

    @gen_test
    def test_no_cw_url_returns_true(self):
        bundle_id = '~bac/muletrain/wiki'
        mock_path = 'tornado.httpclient.AsyncHTTPClient.fetch'
        with mock.patch(mock_path) as mock_fetch:
            ok = yield utils.increment_deployment_counter(bundle_id, None)
        self.assertFalse(ok)
        self.assertFalse(mock_fetch.called)

    @gen_test
    def test_increment_nonstring_bundle_id(self):
        bundle_id = 4
        cw_url = 'http://my.charmworld.example.com/'
        mock_path = 'tornado.httpclient.AsyncHTTPClient.fetch'
        with mock.patch(mock_path) as mock_fetch:
            ok = yield utils.increment_deployment_counter(bundle_id, cw_url)
        self.assertFalse(ok)
        self.assertFalse(mock_fetch.called)

    @gen_test
    def test_increment_nonstring_cwurl(self):
        bundle_id = u'~bac/muletrain/wiki'
        cw_url = 7
        mock_path = 'tornado.httpclient.AsyncHTTPClient.fetch'
        with mock.patch(mock_path) as mock_fetch:
            ok = yield utils.increment_deployment_counter(bundle_id, cw_url)
        self.assertFalse(ok)
        self.assertFalse(mock_fetch.called)

    @gen_test
    def test_increment_url_logged(self):
        bundle_id = '~bac/muletrain/wiki'
        cw_url = 'http://my.charmworld.example.com/'
        url = u'{}api/3/bundle/{}/metric/deployments/increment'.format(
            cw_url, bundle_id)
        expected = 'Incrementing bundle.+'
        called_with = []
        mock_fetch = mock_fetch_factory(200, called_with)
        with ExpectLog('', expected, required=True):
            mock_path = 'tornado.httpclient.AsyncHTTPClient.fetch'
            with mock.patch(mock_path, mock_fetch):
                ok = yield utils.increment_deployment_counter(
                    bundle_id, cw_url)
        self.assertTrue(ok)
        called_args, called_kwargs = called_with[0]
        self.assertEqual(url, urllib.unquote(called_args[0]))
        self.assertEqual(dict(callback=None), called_kwargs)

    @gen_test
    def test_increment_errors(self):
        bundle_id = '~bac/muletrain/wiki'
        cw_url = 'http://my.charmworld.example.com/'
        mock_path = 'tornado.httpclient.AsyncHTTPClient.fetch'
        mock_fetch = mock_fetch_factory(404)
        with mock.patch(mock_path, mock_fetch):
            ok = yield utils.increment_deployment_counter(bundle_id, cw_url)
        self.assertFalse(ok)
