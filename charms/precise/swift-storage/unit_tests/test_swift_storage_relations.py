from mock import patch, MagicMock

from test_utils import CharmTestCase

import swift_storage_utils as utils

_reg = utils.register_configs
utils.register_configs = MagicMock()

import swift_storage_hooks as hooks

utils.register_configs = _reg

from swift_storage_utils import PACKAGES

TO_PATCH = [
    'CONFIGS',
    # charmhelpers.core.hookenv
    'Hooks',
    'config',
    'log',
    'relation_set',
    'relation_get',
    # charmhelpers.core.host
    'apt_update',
    'apt_install',
    # charmehelpers.contrib.openstack.utils
    'configure_installation_source',
    'openstack_upgrade_available',
    # swift_storage_utils
    'determine_block_devices',
    'do_openstack_upgrade',
    'ensure_swift_directories',
    'fetch_swift_rings',
    'save_script_rc',
    'setup_storage',
    'register_configs',
    'execd_preinstall'
]


class SwiftStorageRelationsTests(CharmTestCase):
    def setUp(self):
        super(SwiftStorageRelationsTests, self).setUp(hooks,
                                                      TO_PATCH)
        self.config.side_effect = self.test_config.get
        self.relation_get.side_effect = self.test_relation.get

    def test_install_hook(self):
        self.test_config.set('openstack-origin', 'cloud:precise-havana')
        hooks.install()
        self.configure_installation_source.assert_called_with(
            'cloud:precise-havana',
        )
        self.apt_update.assert_called()
        self.apt_install.assert_called_with(PACKAGES, fatal=True)

        self.setup_storage.assert_called()
        self.execd_preinstall.assert_called()

    def test_config_changed_no_upgrade_available(self):
        self.openstack_upgrade_available.return_value = False
        hooks.config_changed()
        self.assertFalse(self.do_openstack_upgrade.called)
        self.assertTrue(self.CONFIGS.write_all.called)

    def test_config_changed_upgrade_available(self):
        self.openstack_upgrade_available.return_value = True
        hooks.config_changed()
        self.assertTrue(self.do_openstack_upgrade.called)
        self.assertTrue(self.CONFIGS.write_all.called)

    def test_storage_joined_single_device(self):
        self.determine_block_devices.return_value = ['/dev/vdb']
        hooks.swift_storage_relation_joined()
        self.relation_set.assert_called_with(
            device='vdb', object_port=6000, account_port=6002,
            zone=1, container_port=6001
        )

    def test_storage_joined_multi_device(self):
        self.determine_block_devices.return_value = ['/dev/vdb', '/dev/vdc',
                                                     '/dev/vdd']
        hooks.swift_storage_relation_joined()
        self.relation_set.assert_called_with(
            device='vdb:vdc:vdd', object_port=6000, account_port=6002,
            zone=1, container_port=6001
        )

    @patch('sys.exit')
    def test_storage_changed_missing_relation_data(self, exit):
        hooks.swift_storage_relation_changed()
        exit.assert_called_with(0)

    def test_storage_changed_with_relation_data(self):
        self.test_relation.set({
            'swift_hash': 'foo_hash',
            'rings_url': 'http://swift-proxy.com/rings/',
        })
        hooks.swift_storage_relation_changed()
        self.CONFIGS.write.assert_called_with('/etc/swift/swift.conf')
        self.fetch_swift_rings.assert_called_with(
            'http://swift-proxy.com/rings/'
        )

    @patch('sys.argv')
    @patch.object(hooks, 'install')
    def test_main_hook_exists(self, _install, _argv):
        hooks.main()
        _install.assert_called()

    @patch('sys.argv')
    def test_main_hook_missing(self, _argv):
        hooks.main()
        self.log.assert_called()
