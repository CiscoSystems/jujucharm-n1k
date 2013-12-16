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

"""Backend tests."""


from contextlib import (
    contextmanager,
    nested,
)
import os
import shutil
import tempfile
import unittest

import mock

import backend
import utils


EXPECTED_PYTHON_LEGACY_DEBS = ('apache2', 'curl', 'haproxy', 'openssl')
EXPECTED_GO_LEGACY_DEBS = ('apache2', 'curl', 'haproxy', 'openssl')
EXPECTED_PYTHON_BUILTIN_DEBS = (
    'curl', 'openssl', 'python-bzrlib', 'python-pip')
EXPECTED_GO_BUILTIN_DEBS = ('curl', 'openssl', 'python-bzrlib', 'python-pip')

simulate_pyjuju = mock.patch('utils.legacy_juju', mock.Mock(return_value=True))
simulate_juju_core = mock.patch(
    'utils.legacy_juju', mock.Mock(return_value=False))


class TestBackendProperties(unittest.TestCase):
    """Ensure the correct mixins and property values are collected."""

    def assert_mixins(self, expected, backend):
        """Ensure the given backend includes the expected mixins."""
        obtained = tuple(mixin.__class__.__name__ for mixin in backend.mixins)
        self.assertEqual(tuple(expected), obtained)

    def assert_dependencies(self, expected_debs, expected_repository, backend):
        """Ensure the given backend includes the expected dependencies."""
        obtained_debs, obtained_repository = backend.get_dependencies()
        self.assertEqual(set(expected_debs), obtained_debs)
        self.assertEqual(expected_repository, obtained_repository)

    def check_sandbox_mode(self):
        """The backend includes the correct mixins when sandbox mode is active.
        """
        expected_mixins = (
            'SetUpMixin', 'SandboxMixin', 'GuiMixin', 'HaproxyApacheMixin')
        config = {
            'builtin-server': False,
            'repository-location': 'ppa:my/location',
            'sandbox': True,
            'staging': False,
        }
        test_backend = backend.Backend(config=config)
        self.assert_mixins(expected_mixins, test_backend)
        self.assert_dependencies(
            EXPECTED_PYTHON_LEGACY_DEBS, 'ppa:my/location', test_backend)

    def test_python_staging_backend(self):
        expected_mixins = (
            'SetUpMixin', 'ImprovMixin', 'GuiMixin', 'HaproxyApacheMixin')
        config = {
            'builtin-server': False,
            'repository-location': 'ppa:my/location',
            'sandbox': False,
            'staging': True,
        }
        with simulate_pyjuju:
            test_backend = backend.Backend(config=config)
            self.assert_mixins(expected_mixins, test_backend)
            self.assert_dependencies(
                EXPECTED_PYTHON_LEGACY_DEBS + ('zookeeper',),
                'ppa:my/location', test_backend)

    def test_go_staging_backend(self):
        config = {'sandbox': False, 'staging': True, 'builtin-server': False}
        with simulate_juju_core:
            with self.assertRaises(ValueError) as context_manager:
                backend.Backend(config=config)
        error = str(context_manager.exception)
        self.assertEqual('Unable to use staging with go backend', error)

    def test_python_sandbox_backend(self):
        with simulate_pyjuju:
            self.check_sandbox_mode()

    def test_go_sandbox_backend(self):
        with simulate_juju_core:
            self.check_sandbox_mode()

    def test_python_backend(self):
        expected_mixins = (
            'SetUpMixin', 'PythonMixin', 'GuiMixin', 'HaproxyApacheMixin')
        config = {
            'builtin-server': False,
            'repository-location': 'ppa:my/location',
            'sandbox': False,
            'staging': False,
        }
        with simulate_pyjuju:
            test_backend = backend.Backend(config=config)
            self.assert_mixins(expected_mixins, test_backend)
            self.assert_dependencies(
                EXPECTED_PYTHON_LEGACY_DEBS, 'ppa:my/location', test_backend)

    def test_go_backend(self):
        expected_mixins = (
            'SetUpMixin', 'GoMixin', 'GuiMixin', 'HaproxyApacheMixin')
        config = {
            'builtin-server': False,
            'repository-location': 'ppa:my/location',
            'sandbox': False,
            'staging': False,
        }
        with simulate_juju_core:
            test_backend = backend.Backend(config=config)
            self.assert_mixins(expected_mixins, test_backend)
            self.assert_dependencies(
                EXPECTED_GO_LEGACY_DEBS, 'ppa:my/location', test_backend)

    def test_go_builtin_server(self):
        config = {
            'builtin-server': True,
            'repository-location': 'ppa:my/location',
            'sandbox': False,
            'staging': False,
        }
        expected_mixins = (
            'SetUpMixin', 'GoMixin', 'GuiMixin', 'BuiltinServerMixin')
        with simulate_juju_core:
            test_backend = backend.Backend(config)
            self.assert_mixins(expected_mixins, test_backend)
            self.assert_dependencies(
                EXPECTED_GO_BUILTIN_DEBS, None, test_backend)

    def test_python_builtin_server(self):
        config = {
            'builtin-server': True,
            'repository-location': 'ppa:my/location',
            'sandbox': False,
            'staging': False,
        }
        expected_mixins = (
            'SetUpMixin', 'PythonMixin', 'GuiMixin', 'BuiltinServerMixin')
        with simulate_pyjuju:
            test_backend = backend.Backend(config)
            self.assert_mixins(expected_mixins, test_backend)
            self.assert_dependencies(
                EXPECTED_PYTHON_BUILTIN_DEBS, None, test_backend)

    def test_sandbox_builtin_server(self):
        config = {
            'builtin-server': True,
            'repository-location': 'ppa:my/location',
            'sandbox': True,
            'staging': False,
        }
        expected_mixins = (
            'SetUpMixin', 'SandboxMixin', 'GuiMixin', 'BuiltinServerMixin')
        with simulate_juju_core:
            test_backend = backend.Backend(config)
            self.assert_mixins(expected_mixins, test_backend)
            self.assert_dependencies(
                EXPECTED_PYTHON_BUILTIN_DEBS, None, test_backend)


class TestBackendCommands(unittest.TestCase):

    def setUp(self):
        # Set up directories.
        self.playground = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.playground)
        self.base_dir = os.path.join(self.playground, 'juju-gui')
        self.command_log_file = os.path.join(self.playground, 'logs')
        self.juju_agent_dir = os.path.join(self.playground, 'juju-agent-dir')
        self.ssl_cert_path = os.path.join(self.playground, 'ssl-cert-path')
        # Set up default values.
        self.juju_api_branch = 'lp:juju-api'
        self.juju_gui_source = 'stable'
        self.repository_location = 'ppa:my/location'
        self.parse_source_return_value = ('stable', None)

    def make_config(self, options=None):
        """Create and return a backend configuration dict."""
        config = {
            'builtin-server': True,
            'builtin-server-logging': 'info',
            'charmworld-url': 'http://charmworld.example.com/',
            'command-log-file': self.command_log_file,
            'default-viewmode': 'sidebar',
            'ga-key': 'my-key',
            'juju-api-branch': self.juju_api_branch,
            'juju-gui-debug': False,
            'juju-gui-console-enabled': False,
            'juju-gui-source': self.juju_gui_source,
            'login-help': 'login-help',
            'read-only': False,
            'repository-location': self.repository_location,
            'sandbox': False,
            'secure': True,
            'serve-tests': False,
            'show-get-juju-button': False,
            'ssl-cert-path': self.ssl_cert_path,
            'staging': False,
        }
        if options is not None:
            config.update(options)
        return config

    @contextmanager
    def mock_all(self):
        """Mock all the extrenal functions used by the backend framework."""
        mock_parse_source = mock.Mock(
            return_value=self.parse_source_return_value)
        mocks = {
            'base_dir': mock.patch('backend.utils.BASE_DIR', self.base_dir),
            'compute_build_dir': mock.patch('backend.utils.compute_build_dir'),
            'fetch_api': mock.patch('backend.utils.fetch_api'),
            'fetch_gui_from_branch': mock.patch(
                'backend.utils.fetch_gui_from_branch'),
            'fetch_gui_release': mock.patch('backend.utils.fetch_gui_release'),
            'install_builtin_server': mock.patch(
                'backend.utils.install_builtin_server'),
            'install_missing_packages': mock.patch(
                'backend.utils.install_missing_packages'),
            'juju_agent_dir': mock.patch(
                'backend.utils.JUJU_AGENT_DIR', self.juju_agent_dir),
            'log': mock.patch('backend.log'),
            'open_port': mock.patch('backend.open_port'),
            'parse_source': mock.patch(
                'backend.utils.parse_source', mock_parse_source),
            'save_or_create_certificates': mock.patch(
                'backend.utils.save_or_create_certificates'),
            'setup_gui': mock.patch('backend.utils.setup_gui'),
            'start_agent': mock.patch('backend.utils.start_agent'),
            'start_builtin_server': mock.patch(
                'backend.utils.start_builtin_server'),
            'start_haproxy_apache': mock.patch(
                'backend.utils.start_haproxy_apache'),
            'stop_agent': mock.patch('backend.utils.stop_agent'),
            'stop_builtin_server': mock.patch(
                'backend.utils.stop_builtin_server'),
            'stop_haproxy_apache': mock.patch(
                'backend.utils.stop_haproxy_apache'),
            'write_gui_config': mock.patch('backend.utils.write_gui_config'),
        }
        # Note: nested is deprecated for good reasons which do not apply here.
        # Used here to easily nest a dynamically generated list of context
        # managers.
        with nested(*mocks.values()) as context_managers:
            object_dict = dict(zip(mocks.keys(), context_managers))
            yield type('Mocks', (object,), object_dict)

    def assert_write_gui_config_called(self, mocks, config):
        """Ensure the mocked write_gui_config has been properly called."""
        mocks.write_gui_config.assert_called_once_with(
            config['juju-gui-console-enabled'], config['login-help'],
            config['read-only'], config['staging'], config['charmworld-url'],
            mocks.compute_build_dir(), secure=config['secure'],
            sandbox=config['sandbox'], ga_key=config['ga-key'],
            default_viewmode=config['default-viewmode'],
            show_get_juju_button=config['show-get-juju-button'], password=None)

    def test_base_dir_created(self):
        # The base Juju GUI directory is correctly created.
        config = self.make_config()
        test_backend = backend.Backend(config=config)
        with self.mock_all():
            test_backend.install()
        self.assertTrue(os.path.isdir(self.base_dir))

    def test_base_dir_removed(self):
        # The base Juju GUI directory is correctly removed.
        config = self.make_config()
        test_backend = backend.Backend(config=config)
        with self.mock_all():
            test_backend.install()
            test_backend.destroy()
        self.assertFalse(os.path.exists(utils.BASE_DIR), utils.BASE_DIR)

    def test_install_python_legacy_stable(self):
        # Install a pyJuju backend with legacy server and stable release.
        config = self.make_config({'builtin-server': False})
        with simulate_pyjuju:
            test_backend = backend.Backend(config=config)
            with self.mock_all() as mocks:
                test_backend.install()
        mocks.install_missing_packages.assert_called_once_with(
            set(EXPECTED_PYTHON_LEGACY_DEBS),
            repository=self.repository_location)
        mocks.fetch_api.assert_called_once_with(self.juju_api_branch)
        mocks.parse_source.assert_called_once_with(self.juju_gui_source)
        mocks.fetch_gui_release.assert_called_once_with(
            *self.parse_source_return_value)
        self.assertFalse(mocks.fetch_gui_from_branch.called)
        mocks.setup_gui.assert_called_once_with(mocks.fetch_gui_release())
        self.assertFalse(mocks.install_builtin_server.called)

    def test_install_go_legacy_stable(self):
        # Install a juju-core backend with legacy server and stable release.
        config = self.make_config({'builtin-server': False})
        with simulate_juju_core:
            test_backend = backend.Backend(config=config)
            with self.mock_all() as mocks:
                test_backend.install()
        mocks.install_missing_packages.assert_called_once_with(
            set(EXPECTED_GO_LEGACY_DEBS), repository=self.repository_location)
        self.assertFalse(mocks.fetch_api.called)
        mocks.parse_source.assert_called_once_with(self.juju_gui_source)
        mocks.fetch_gui_release.assert_called_once_with(
            *self.parse_source_return_value)
        self.assertFalse(mocks.fetch_gui_from_branch.called)
        mocks.setup_gui.assert_called_once_with(mocks.fetch_gui_release())
        self.assertFalse(mocks.install_builtin_server.called)

    def test_install_python_builtin_stable(self):
        # Install a pyJuju backend with builtin server and stable release.
        config = self.make_config({'builtin-server': True})
        with simulate_pyjuju:
            test_backend = backend.Backend(config=config)
            with self.mock_all() as mocks:
                test_backend.install()
        mocks.install_missing_packages.assert_called_once_with(
            set(EXPECTED_PYTHON_BUILTIN_DEBS), repository=None)
        mocks.fetch_api.assert_called_once_with(self.juju_api_branch)
        mocks.parse_source.assert_called_once_with(self.juju_gui_source)
        mocks.fetch_gui_release.assert_called_once_with(
            *self.parse_source_return_value)
        self.assertFalse(mocks.fetch_gui_from_branch.called)
        mocks.setup_gui.assert_called_once_with(mocks.fetch_gui_release())
        mocks.install_builtin_server.assert_called_once_with()

    def test_install_go_builtin_stable(self):
        # Install a juju-core backend with builtin server and stable release.
        config = self.make_config({'builtin-server': True})
        with simulate_juju_core:
            test_backend = backend.Backend(config=config)
            with self.mock_all() as mocks:
                test_backend.install()
        mocks.install_missing_packages.assert_called_once_with(
            set(EXPECTED_GO_BUILTIN_DEBS), repository=None)
        self.assertFalse(mocks.fetch_api.called)
        mocks.parse_source.assert_called_once_with(self.juju_gui_source)
        mocks.fetch_gui_release.assert_called_once_with(
            *self.parse_source_return_value)
        self.assertFalse(mocks.fetch_gui_from_branch.called)
        mocks.setup_gui.assert_called_once_with(mocks.fetch_gui_release())
        mocks.install_builtin_server.assert_called_once_with()

    def test_install_go_builtin_branch(self):
        # Install a juju-core backend with builtin server and branch release.
        self.parse_source_return_value = ('branch', ('lp:juju-gui', 42))
        expected_calls = [
            mock.call(set(EXPECTED_GO_BUILTIN_DEBS), repository=None),
            mock.call(
                utils.DEB_BUILD_DEPENDENCIES,
                repository=self.repository_location,
            ),
        ]
        config = self.make_config({'builtin-server': True})
        with simulate_juju_core:
            test_backend = backend.Backend(config=config)
            with self.mock_all() as mocks:
                test_backend.install()
        mocks.install_missing_packages.assert_has_calls(expected_calls)
        self.assertFalse(mocks.fetch_api.called)
        mocks.parse_source.assert_called_once_with(self.juju_gui_source)
        mocks.fetch_gui_from_branch.assert_called_once_with(
            'lp:juju-gui', 42, self.command_log_file)
        self.assertFalse(mocks.fetch_gui_release.called)
        mocks.setup_gui.assert_called_once_with(mocks.fetch_gui_from_branch())
        mocks.install_builtin_server.assert_called_once_with()

    def test_start_python_legacy(self):
        # Start a pyJuju backend with legacy server.
        config = self.make_config({'builtin-server': False})
        with simulate_pyjuju:
            test_backend = backend.Backend(config=config)
            with self.mock_all() as mocks:
                test_backend.start()
        mocks.start_agent.assert_called_once_with(self.ssl_cert_path)
        mocks.compute_build_dir.assert_called_with(
            config['juju-gui-debug'], config['serve-tests'])
        self.assert_write_gui_config_called(mocks, config)
        mocks.open_port.assert_has_calls([mock.call(80), mock.call(443)])
        mocks.start_haproxy_apache.assert_called_once_with(
            mocks.compute_build_dir(), config['serve-tests'],
            self.ssl_cert_path, config['secure'])
        self.assertFalse(mocks.start_builtin_server.called)

    def test_start_go_legacy(self):
        # Start a juju-core backend with legacy server.
        config = self.make_config({'builtin-server': False})
        with simulate_juju_core:
            test_backend = backend.Backend(config=config)
            with self.mock_all() as mocks:
                test_backend.start()
        self.assertFalse(mocks.start_agent.called)
        mocks.compute_build_dir.assert_called_with(
            config['juju-gui-debug'], config['serve-tests'])
        self.assert_write_gui_config_called(mocks, config)
        mocks.open_port.assert_has_calls([mock.call(80), mock.call(443)])
        mocks.start_haproxy_apache.assert_called_once_with(
            mocks.compute_build_dir(), config['serve-tests'],
            self.ssl_cert_path, config['secure'])
        self.assertFalse(mocks.start_builtin_server.called)

    def test_start_python_builtin(self):
        # Start a pyJuju backend with builtin server.
        config = self.make_config({'builtin-server': True})
        with simulate_pyjuju:
            test_backend = backend.Backend(config=config)
            with self.mock_all() as mocks:
                test_backend.start()
        mocks.start_agent.assert_called_once_with(self.ssl_cert_path)
        mocks.compute_build_dir.assert_called_with(
            config['juju-gui-debug'], config['serve-tests'])
        self.assert_write_gui_config_called(mocks, config)
        mocks.open_port.assert_has_calls([mock.call(80), mock.call(443)])
        mocks.start_builtin_server.assert_called_once_with(
            mocks.compute_build_dir(), self.ssl_cert_path,
            config['serve-tests'], config['sandbox'],
            config['builtin-server-logging'], not config['secure'],
            config['charmworld-url'])
        self.assertFalse(mocks.start_haproxy_apache.called)

    def test_start_go_builtin(self):
        # Start a juju-core backend with builtin server.
        config = self.make_config({'builtin-server': True})
        with simulate_juju_core:
            test_backend = backend.Backend(config=config)
            with self.mock_all() as mocks:
                test_backend.start()
        self.assertFalse(mocks.start_agent.called)
        mocks.compute_build_dir.assert_called_with(
            config['juju-gui-debug'], config['serve-tests'])
        self.assert_write_gui_config_called(mocks, config)
        mocks.open_port.assert_has_calls([mock.call(80), mock.call(443)])
        mocks.start_builtin_server.assert_called_once_with(
            mocks.compute_build_dir(), self.ssl_cert_path,
            config['serve-tests'], config['sandbox'],
            config['builtin-server-logging'], not config['secure'],
            config['charmworld-url'])
        self.assertFalse(mocks.start_haproxy_apache.called)

    def test_stop_python_legacy(self):
        # Stop a pyJuju backend with legacy server.
        config = self.make_config({'builtin-server': False})
        with simulate_pyjuju:
            test_backend = backend.Backend(config=config)
            with self.mock_all() as mocks:
                test_backend.stop()
        mocks.stop_agent.assert_called_once_with()
        mocks.stop_haproxy_apache.assert_called_once_with()
        self.assertFalse(mocks.stop_builtin_server.called)

    def test_stop_go_legacy(self):
        # Stop a juju-core backend with legacy server.
        config = self.make_config({'builtin-server': False})
        with simulate_juju_core:
            test_backend = backend.Backend(config=config)
            with self.mock_all() as mocks:
                test_backend.stop()
        self.assertFalse(mocks.stop_agent.called)
        mocks.stop_haproxy_apache.assert_called_once_with()
        self.assertFalse(mocks.stop_builtin_server.called)

    def test_stop_python_builtin(self):
        # Stop a pyJuju backend with builtin server.
        config = self.make_config({'builtin-server': True})
        with simulate_pyjuju:
            test_backend = backend.Backend(config=config)
            with self.mock_all() as mocks:
                test_backend.stop()
        mocks.stop_agent.assert_called_once_with()
        mocks.stop_builtin_server.assert_called_once_with()
        self.assertFalse(mocks.stop_haproxy_apache.called)

    def test_stop_go_builtin(self):
        # Stop a juju-core backend with builtin server.
        config = self.make_config({'builtin-server': True})
        with simulate_juju_core:
            test_backend = backend.Backend(config=config)
            with self.mock_all() as mocks:
                test_backend.stop()
        self.assertFalse(mocks.stop_agent.called)
        mocks.stop_builtin_server.assert_called_once_with()
        self.assertFalse(mocks.stop_haproxy_apache.called)


class TestBackendUtils(unittest.TestCase):

    def test_same_config(self):
        test_backend = backend.Backend(
            config={
                'sandbox': False, 'staging': False, 'builtin-server': False},
            prev_config={
                'sandbox': False, 'staging': False, 'builtin-server': False},
        )
        self.assertFalse(test_backend.different('sandbox'))
        self.assertFalse(test_backend.different('staging'))

    def test_different_config(self):
        test_backend = backend.Backend(
            config={
                'sandbox': False, 'staging': False, 'builtin-server': False},
            prev_config={
                'sandbox': True, 'staging': False, 'builtin-server': False},
        )
        self.assertTrue(test_backend.different('sandbox'))
        self.assertFalse(test_backend.different('staging'))


class TestCallMethods(unittest.TestCase):

    def setUp(self):
        self.called = []
        self.objects = [self.make_object('Obj1'), self.make_object('Obj2')]

    def make_object(self, name, has_method=True):
        """Create and return an test object with the given name."""
        def method(obj, *args):
            self.called.append([obj.__class__.__name__, args])
        object_dict = {'method': method} if has_method else {}
        return type(name, (object,), object_dict)()

    def test_call(self):
        # The methods are correctly called.
        backend.call_methods(self.objects, 'method', 'arg1', 'arg2')
        expected = [['Obj1', ('arg1', 'arg2')], ['Obj2', ('arg1', 'arg2')]]
        self.assertEqual(expected, self.called)

    def test_no_method(self):
        # An object without the method is ignored.
        self.objects.append(self.make_object('Obj3', has_method=False))
        backend.call_methods(self.objects, 'method')
        expected = [['Obj1', ()], ['Obj2', ()]]
        self.assertEqual(expected, self.called)
