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

"""Tests for the Juju GUI server management helpers."""

from contextlib import contextmanager
import logging
import unittest

import mock
from tornado.testing import LogTrapTestCase

from guiserver import manage


@mock.patch('guiserver.manage.options')
class TestAddDebug(unittest.TestCase):

    def test_debug_enabled(self, mock_options):
        # The debug option is true if the log level is debug.
        logger = mock.Mock(level=logging.DEBUG)
        manage._add_debug(logger)
        mock_options.define.assert_called_once_with('debug', default=True)

    def test_debug_disabled(self, mock_options):
        # The debug option is false if the log level is not debug.
        logger = mock.Mock(level=logging.INFO)
        manage._add_debug(logger)
        mock_options.define.assert_called_once_with('debug', default=False)


class ValidatorTestMixin(object):
    """Add methods for testing functions producing a system exit."""

    @contextmanager
    def assert_sysexit(self, error):
        """Ensure the code in the context manager block produces a system exit.

        Also check that the given error is returned.
        """
        with mock.patch('sys.exit') as mock_exit:
            yield
            mock_exit.assert_called_once_with(error)


class TestValidateRequired(ValidatorTestMixin, unittest.TestCase):

    error = 'error: the {} argument is required'

    def test_success(self):
        # The validation passes if the args are correctly found.
        with mock.patch('guiserver.manage.options', {'arg1': 'value1'}):
            manage._validate_required('arg1')

    def test_success_multiple_args(self):
        # The validation passes for multiple args.
        options = {'arg1': 'value1', 'arg2': 'value2'}
        with mock.patch('guiserver.manage.options', options):
            manage._validate_required(*options.keys())

    def test_failure(self):
        # The validation fails if the arg value is an empty string.
        with mock.patch('guiserver.manage.options', {'arg1': ''}):
            with self.assert_sysexit(self.error.format('arg1')):
                manage._validate_required('arg1')

    def test_failure_multiple_args(self):
        # The validation fails if one of the arg values is an empty string.
        options = {'arg1': 'value1', 'arg2': ''}
        with mock.patch('guiserver.manage.options', options):
            with self.assert_sysexit(self.error.format('arg2')):
                manage._validate_required(*options.keys())

    def test_failure_missing(self):
        # The validation fails if the value is missing.
        with mock.patch('guiserver.manage.options', {'arg1': None}):
            with self.assert_sysexit(self.error.format('arg1')):
                manage._validate_required('arg1')

    def test_failure_empty(self):
        # The validation fails if the stripped value is an empty string.
        with mock.patch('guiserver.manage.options', {'arg1': ' '}):
            with self.assert_sysexit(self.error.format('arg1')):
                manage._validate_required('arg1')

    def test_failure_invalid_type(self):
        # The validation fails if the arg value is not a string.
        with mock.patch('guiserver.manage.options', {'arg1': 42}):
            with self.assert_sysexit(self.error.format('arg1')):
                manage._validate_required('arg1')


class TestValidateChoices(ValidatorTestMixin, unittest.TestCase):

    choices = ('choice1', 'choice2')
    error = 'error: accepted values for the {} argument are: choice1, choice2'

    def test_success(self):
        # The validation passes if the value is included in the choices.
        with mock.patch('guiserver.manage.options', {'arg1': 'choice1'}):
            manage._validate_choices('arg1', self.choices)

    def test_failure_invalid_choice(self):
        # The validation fails if the value is not in choices.
        with mock.patch('guiserver.manage.options', {'arg1': 'not-a-choice'}):
            with self.assert_sysexit(self.error.format('arg1')):
                manage._validate_choices('arg1', self.choices)

    def test_failure_missing(self):
        # The validation fails if the value is missing.
        with mock.patch('guiserver.manage.options', {'arg1': None}):
            with self.assert_sysexit(self.error.format('arg1')):
                manage._validate_choices('arg1', self.choices)


class TestGetSslOptions(unittest.TestCase):

    def test_options(self):
        # The SSL options are correctly returned.
        mock_options = mock.Mock(sslpath='/my/path')
        expected = {
            'certfile': '/my/path/juju.crt',
            'keyfile': '/my/path/juju.key',
        }
        with mock.patch('guiserver.manage.options', mock_options):
            self.assertEqual(expected, manage._get_ssl_options())


class TestRun(LogTrapTestCase, unittest.TestCase):

    def mock_and_run(self, **kwargs):
        """Run the application after mocking the IO loop and the options/apps.

        Additional options can be specified using kwargs.
        """
        options = {
            'apiversion': 'go',
            'guiroot': '/my/guiroot',
            'sslpath': '/my/sslpath',
        }
        options.update(kwargs)
        with \
                mock.patch('guiserver.manage.IOLoop') as ioloop, \
                mock.patch('guiserver.manage.options', mock.Mock(**options)), \
                mock.patch('guiserver.manage.redirector') as redirector, \
                mock.patch('guiserver.manage.server') as server:
            manage.run()
        return ioloop.instance().start, redirector().listen, server().listen

    def test_secure_mode(self):
        # The application is correctly run in secure mode.
        _, redirector_listen, server_listen = self.mock_and_run(insecure=False)
        expected_ssl_options = {
            'certfile': '/my/sslpath/juju.crt',
            'keyfile': '/my/sslpath/juju.key',
        }
        redirector_listen.assert_called_once_with(80)
        server_listen.assert_called_once_with(
            443, ssl_options=expected_ssl_options)

    def test_insecure_mode(self):
        # The application is correctly run in insecure mode.
        _, redirector_listen, server_listen = self.mock_and_run(insecure=True)
        self.assertEqual(0, redirector_listen.call_count)
        server_listen.assert_called_once_with(80)

    def test_ioloop_started(self):
        # The IO loop instance is started when the application is run.
        ioloop_start, _, _ = self.mock_and_run()
        ioloop_start.assert_called_once_with()
