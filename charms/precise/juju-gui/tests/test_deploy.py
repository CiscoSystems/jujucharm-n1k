# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2012-2013 Canonical Ltd.
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

"""Juju GUI deploy module tests."""

import os
import shutil
import tempfile
import unittest

import mock

import deploy
from deploy import (
    juju_deploy,
    setup_repository,
)


def contains(needle, haystack):
    """Does the sequence (haystack) contain the given subsequence (needle)?"""
    for i in xrange(len(haystack)-len(needle)+1):
        for j in xrange(len(needle)):
            if haystack[i+j] != needle[j]:
                break
        else:
            return True
    return False


class TestSetupRepository(unittest.TestCase):

    name = 'test-charm'

    def setUp(self):
        # Create a directory structure for the charm source.
        self.source = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.source)
        # Create a file in the source dir.
        _, self.root_file = tempfile.mkstemp(dir=self.source)
        # Create a Bazaar repository directory with a file in it.
        bzr_dir = os.path.join(self.source, '.bzr')
        os.mkdir(bzr_dir)
        tempfile.mkstemp(dir=bzr_dir)
        # Create a tests directory including a .venv directory and a file.
        self.tests_dir = os.path.join(self.source, 'tests')
        venv_dir = os.path.join(self.tests_dir, '.venv')
        os.makedirs(venv_dir)
        tempfile.mkstemp(dir=venv_dir)
        # Create a test file.
        _, self.tests_file = tempfile.mkstemp(dir=self.tests_dir)

    def assert_dir_exists(self, path):
        self.assertTrue(
            os.path.isdir(path),
            'the directory {!r} does not exist'.format(path))

    def assert_files_equal(self, expected, path):
        fileset = set()
        for dirpath, _, filenames in os.walk(path):
            relpath = os.path.relpath(dirpath, path)
            if relpath == '.':
                relpath = ''
            else:
                fileset.add(relpath + os.path.sep)
            fileset.update(os.path.join(relpath, name) for name in filenames)
        self.assertEqual(expected, fileset)

    def check_repository(self, repo, series):
        # The repository has been created in the temp directory.
        self.assertEqual(tempfile.tempdir, os.path.split(repo)[0])
        self.assert_dir_exists(repo)
        # The repository only contains the series directory.
        self.assertEqual([series], os.listdir(repo))
        series_dir = os.path.join(repo, series)
        self.assert_dir_exists(series_dir)
        # The series directory only contains our charm.
        self.assertEqual([self.name], os.listdir(series_dir))
        self.assert_dir_exists(os.path.join(series_dir, self.name))

    def test_repository(self):
        # The charm repository is correctly created with the default series.
        repo = setup_repository(self.name, self.source)
        self.check_repository(repo, 'precise')

    def test_series(self):
        # The charm repository is created with the given series.
        repo = setup_repository(self.name, self.source, series='raring')
        self.check_repository(repo, 'raring')

    def test_charm_files(self):
        # The charm files are correctly copied inside the repository, excluding
        # unwanted directories.
        repo = setup_repository(self.name, self.source)
        charm_dir = os.path.join(repo, 'precise', self.name)
        expected = set([
            os.path.basename(self.root_file)
        ])
        self.assert_files_equal(expected, charm_dir)


REPO_PATH = '/tmp/repo/'


@mock.patch('deploy.setup_repository', mock.Mock(return_value=REPO_PATH))
class TestJujuDeploy(unittest.TestCase):

    unit_info = {'public-address': 'unit.example.com'}
    charm = 'test-charm'
    local_charm = 'local:precise/{}'.format(charm)

    @mock.patch('deploy.juju')
    @mock.patch('deploy.wait_for_unit')
    def call_deploy(
            self, mock_wait_for_unit, mock_juju,
            service_name=None, options=None, force_machine=None,
            charm_source=None, series='precise'):
        mock_wait_for_unit.return_value = self.unit_info
        if charm_source is None:
            expected_source = os.path.join(os.path.dirname(__file__), '..')
        else:
            expected_source = charm_source
        deploy.setup_repository.reset_mock()
        unit_info = juju_deploy(
            self.charm, service_name=service_name, options=options,
            force_machine=force_machine, charm_source=charm_source,
            series=series)
        deploy.setup_repository.assert_called_once_with(
            self.charm, expected_source, series=series)
        # The unit address is correctly returned.
        self.assertEqual(self.unit_info, unit_info)
        self.assertEqual(1, mock_wait_for_unit.call_count)
        # Juju is called two times: deploy and expose.
        juju_calls = mock_juju.call_args_list
        self.assertEqual(2, len(juju_calls))
        # We expect a "juju expose" to have been called on the service.
        expected_expose_call = mock.call('expose', service_name or self.charm)
        deploy_call, expose_call = juju_calls
        self.assertEqual(expected_expose_call, expose_call)
        self.assertEqual(deploy_call[0][0], 'deploy')
        return deploy_call[0]

    def test_deployment(self):
        # The function deploys and exposes the given charm.
        command = self.call_deploy()
        # A local repository is included in the command.
        self.assertTrue(contains(('--repository', REPO_PATH), command))
        # The charm name is also included.
        self.assertIn(self.local_charm, command)

    def test_options(self):
        # The function handles charm options.
        mock_config_file = mock.Mock()
        mock_config_file.name = '/tmp/config.yaml'
        with mock.patch('deploy.make_charm_config_file') as mock_callable:
            mock_callable.return_value = mock_config_file
            command = self.call_deploy(options={'foo': 'bar'})
        # Since options were provided to the deploy call, a config file was
        # created and passed to "juju deploy".
        self.assertTrue(contains(('--config', mock_config_file.name), command))

    def test_force_machine(self):
        # The function can deploy charms in a specified machine.
        command = self.call_deploy(force_machine=42)
        self.assertTrue(contains(('--to', '42'), command))

    def test_charm_source(self):
        # The function can deploy a charm from a specific source.
        with mock.patch('deploy.setup_repository') as mock_setup_repository:
            charm_source = '/tmp/source/'
            self.call_deploy(charm_source=charm_source)
            # The setup_repository function is called with the charm source as
            # its second argument.
            setup_source = mock_setup_repository.mock_calls[0][1][1]
        # The source provided to the "deploy" call is the same that was passed
        # along to setup_repository.
        self.assertEqual(setup_source, charm_source)

    def test_series(self):
        # The function can deploy a charm from a specific series.
        charm_url = 'local:raring/{}'.format(self.charm)
        command = self.call_deploy(series='raring')
        self.assertIn(charm_url, command)

    def test_no_service_name(self):
        # If the service name is not provided, the charm name is used.
        command = self.call_deploy()
        service_name = command[-1]
        self.assertEqual(self.charm, service_name)

    def test_service_name(self):
        # A customized service name can be provided and it is passed to Juju as
        # the last argument.
        command = self.call_deploy(service_name='my-service')
        service_name = command[-1]
        self.assertEqual('my-service', service_name)
