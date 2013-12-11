
from mock import MagicMock, patch, call


import cinder_utils as utils

from test_utils import (
    CharmTestCase,
    RESTART_MAP,
)

# Need to do some early patching to get the module loaded.
_restart_map = utils.restart_map
_register_configs = utils.register_configs

utils.restart_map = MagicMock()
utils.restart_map.return_value = RESTART_MAP
utils.register_configs = MagicMock()

import cinder_hooks as hooks

# Unpatch it now that its loaded.
utils.restart_map = _restart_map
utils.register_configs = _register_configs

TO_PATCH = [
    'check_call',
    # cinder_utils
    'clean_storage',
    'determine_packages',
    'do_openstack_upgrade',
    'ensure_block_device',
    'ensure_ceph_keyring',
    'ensure_ceph_pool',
    'juju_log',
    'lsb_release',
    'migrate_database',
    'prepare_lvm_storage',
    'register_configs',
    'restart_map',
    'service_enabled',
    'set_ceph_env_variables',
    'CONFIGS',
    'CLUSTER_RES',
    # charmhelpers.core.hookenv
    'config',
    'relation_get',
    'relation_ids',
    'relation_set',
    'service_name',
    'unit_get',
    # charmhelpers.core.host
    'apt_install',
    'apt_update',
    # charmhelpers.contrib.openstack.openstack_utils
    'configure_installation_source',
    'openstack_upgrade_available',
    # charmhelpers.contrib.hahelpers.cluster_utils
    'canonical_url',
    'eligible_leader',
    'is_leader',
    'get_hacluster_config',
    'execd_preinstall',
]


class TestInstallHook(CharmTestCase):
    def setUp(self):
        super(TestInstallHook, self).setUp(hooks, TO_PATCH)
        self.config.side_effect = self.test_config.get_all

    def test_install_precise_distro(self):
        '''It redirects to cloud archive if setup to install precise+distro'''
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'precise'}
        hooks.hooks.execute(['hooks/install'])
        ca = 'cloud:precise-folsom'
        self.configure_installation_source.assert_called_with(ca)

    def test_correct_install_packages(self):
        '''It installs the correct packages based on what is determined'''
        self.determine_packages.return_value = ['foo', 'bar', 'baz']
        hooks.hooks.execute(['hooks/install'])
        self.apt_install.assert_called_with(['foo', 'bar', 'baz'], fatal=True)

    def test_storage_prepared(self):
        '''It prepares local storage if volume service enabled'''
        self.test_config.set('block-device', 'vdb')
        self.test_config.set('volume-group', 'cinder')
        self.test_config.set('overwrite', 'true')
        self.service_enabled.return_value = True
        self.ensure_block_device.return_value = '/dev/vdb'
        hooks.hooks.execute(['hooks/install'])
        self.ensure_block_device.assert_called_with('vdb')
        self.prepare_lvm_storage.assert_called_with('/dev/vdb', 'cinder')

    def test_storage_not_prepared(self):
        '''It does not prepare storage when not necessary'''
        self.service_enabled.return_value = False
        hooks.hooks.execute(['hooks/install'])
        self.assertFalse(self.ensure_block_device.called)
        self.service_enabled.return_value = True
        for none in ['None', 'none', None]:
            self.test_config.set('block-device', none)
            hooks.hooks.execute(['hooks/install'])
            self.assertFalse(self.ensure_block_device.called)

    def test_storage_is_cleaned(self):
        '''It cleans storage when configured to do so'''
        self.ensure_block_device.return_value = '/dev/foo'
        for true in ['True', 'true', True]:
            self.test_config.set('overwrite', true)
            hooks.hooks.execute(['hooks/install'])
            self.clean_storage.assert_called_with('/dev/foo')

    def test_storage_is_not_cleaned(self):
        '''It does not clean storage when not configured to'''
        self.ensure_block_device.return_value = '/dev/foo'
        for true in ['False', 'false', False]:
            self.test_config.set('overwrite', true)
            hooks.hooks.execute(['hooks/install'])
            self.assertFalse(self.clean_storage.called)


class TestChangedHooks(CharmTestCase):
    def setUp(self):
        super(TestChangedHooks, self).setUp(hooks, TO_PATCH)
        self.config.side_effect = self.test_config.get_all

    @patch.object(hooks, 'amqp_joined')
    def test_upgrade_charm_no_amqp(self, _joined):
        self.relation_ids.return_value = []
        hooks.hooks.execute(['hooks/upgrade-charm'])
        _joined.assert_not_called()

    @patch.object(hooks, 'amqp_joined')
    def test_upgrade_charm_with_amqp(self, _joined):
        self.relation_ids.return_value = ['amqp:1']
        hooks.hooks.execute(['hooks/upgrade-charm'])
        _joined.assert_called_with(relation_id='amqp:1')

    @patch.object(hooks, 'configure_https')
    def test_config_changed(self, conf_https):
        '''It writes out all config'''
        self.openstack_upgrade_available.return_value = False
        hooks.hooks.execute(['hooks/config-changed'])
        self.assertTrue(self.CONFIGS.write_all.called)
        self.assertTrue(conf_https.called)

    @patch.object(hooks, 'configure_https')
    def test_config_changed_upgrade_available(self, conf_https):
        '''It writes out all config with an available OS upgrade'''
        self.openstack_upgrade_available.return_value = True
        hooks.hooks.execute(['hooks/config-changed'])
        self.do_openstack_upgrade.assert_called_with(configs=self.CONFIGS)

    def test_db_changed(self):
        '''It writes out cinder.conf on db changed'''
        self.CONFIGS.complete_contexts.return_value = ['shared-db']
        hooks.hooks.execute(['hooks/shared-db-relation-changed'])
        self.CONFIGS.write.assert_called_with('/etc/cinder/cinder.conf')
        self.assertTrue(self.migrate_database.called)

    def test_db_changed_relation_incomplete(self):
        '''It does not write out cinder.conf with incomplete shared-db rel'''
        hooks.hooks.execute(['hooks/shared-db-relation-changed'])
        self.assertFalse(self.CONFIGS.write.called)
        self.assertFalse(self.migrate_database.called)

    def test_db_changed_not_leader(self):
        '''It does not migrate database when not leader'''
        self.eligible_leader.return_value = False
        self.CONFIGS.complete_contexts.return_value = ['shared-db']
        hooks.hooks.execute(['hooks/shared-db-relation-changed'])
        self.CONFIGS.write.assert_called_with('/etc/cinder/cinder.conf')
        self.assertFalse(self.migrate_database.called)

    def test_amqp_changed(self):
        '''It writes out cinder.conf on amqp changed with complete relation'''
        self.CONFIGS.complete_contexts.return_value = ['amqp']
        hooks.hooks.execute(['hooks/amqp-relation-changed'])
        self.CONFIGS.write.assert_called_with('/etc/cinder/cinder.conf')

    def test_amqp_changed_incomplete(self):
        '''It does not write out cinder.conf with incomplete relation'''
        self.CONFIGS.complete_contexts.return_value = ['']
        hooks.hooks.execute(['hooks/amqp-relation-changed'])
        self.assertFalse(self.CONFIGS.write.called)

    @patch.object(hooks, 'configure_https')
    def test_identity_changed(self, conf_https):
        '''It writes out api-paste.ini on identity-service changed'''
        self.CONFIGS.complete_contexts.return_value = ['identity-service']
        hooks.hooks.execute(['hooks/identity-service-relation-changed'])
        self.CONFIGS.write.assert_called_with('/etc/cinder/api-paste.ini')
        self.assertTrue(conf_https.called)

    def test_identity_changed_incomplete(self):
        '''It doesn't write api-paste.ini with incomplete identity-service'''
        hooks.hooks.execute(['hooks/identity-service-relation-changed'])
        self.assertFalse(self.CONFIGS.write.called)

    @patch.object(hooks, 'identity_joined')
    def test_configure_https_enable(self, identity_joined):
        '''It enables https from hooks when we have https data'''
        self.CONFIGS.complete_contexts.return_value = ['https']
        self.relation_ids.return_value = ['identity-service:0']
        hooks.configure_https()
        cmd = ['a2ensite', 'openstack_https_frontend']
        self.check_call.assert_called_with(cmd)
        identity_joined.assert_called_with(rid='identity-service:0')

    @patch.object(hooks, 'identity_joined')
    def test_configure_https_disable(self, identity_joined):
        '''It enables https from hooks when we have https data'''
        self.CONFIGS.complete_contexts.return_value = []
        self.relation_ids.return_value = ['identity-service:0']
        hooks.configure_https()
        cmd = ['a2dissite', 'openstack_https_frontend']
        self.check_call.assert_called_with(cmd)
        identity_joined.assert_called_with(rid='identity-service:0')

    def test_image_service_changed(self):
        ''' Ensure all configuration files written if image service changes '''
        hooks.hooks.execute(['hooks/image-service-relation-changed'])
        self.CONFIGS.write.assert_called_with('/etc/cinder/cinder.conf')

    def test_relation_broken(self):
        ''' Ensure all configuration files written if image service changes '''
        hooks.hooks.execute(['hooks/image-service-relation-broken'])
        self.assertTrue(self.CONFIGS.write_all.called)


class TestJoinedHooks(CharmTestCase):
    def setUp(self):
        super(TestJoinedHooks, self).setUp(hooks, TO_PATCH)
        self.config.side_effect = self.test_config.get_all

    def test_db_joined(self):
        '''It properly requests access to a shared-db service'''
        self.unit_get.return_value = 'cindernode1'
        hooks.hooks.execute(['hooks/shared-db-relation-joined'])
        expected = {'username': 'cinder',
                    'hostname': 'cindernode1', 'database': 'cinder'}
        self.relation_set.assert_called_with(**expected)

    def test_amqp_joined(self):
        '''It properly requests access to an amqp service'''
        hooks.hooks.execute(['hooks/amqp-relation-joined'])
        self.relation_set.assert_called_with(username='cinder',
                                             vhost='openstack',
                                             relation_id=None)

    def test_amqp_joined_passes_relation_id(self):
        ''' Ensures relation_id correct passed to relation_set for out of
            hook execution '''
        hooks.amqp_joined(relation_id='amqp:1')
        self.relation_set.assert_called_with(username='cinder',
                                             vhost='openstack',
                                             relation_id='amqp:1')

    def test_identity_service_joined(self):
        '''It properly requests unclustered endpoint via identity-service'''
        self.unit_get.return_value = 'cindernode1'
        self.canonical_url.return_value = 'http://cindernode1'
        hooks.hooks.execute(['hooks/identity-service-relation-joined'])
        expected = {
            'service': 'cinder',
            'region': 'RegionOne',
            'public_url': 'http://cindernode1:8776/v1/$(tenant_id)s',
            'admin_url': 'http://cindernode1:8776/v1/$(tenant_id)s',
            'internal_url': 'http://cindernode1:8776/v1/$(tenant_id)s',
            'relation_id': None,
        }
        self.relation_set.assert_called_with(**expected)

    def test_identity_service_joined_no_leadership(self):
        '''It does nothing on identity-joined when not eligible leader'''
        self.eligible_leader.return_value = False
        hooks.hooks.execute(['hooks/identity-service-relation-joined'])
        self.assertFalse(self.relation_set.called)

    @patch('os.mkdir')
    def test_ceph_joined(self, mkdir):
        '''It correctly prepares for a ceph changed hook'''
        with patch('os.path.isdir') as isdir:
            isdir.return_value = False
            hooks.hooks.execute(['hooks/ceph-relation-joined'])
            mkdir.assert_called_with('/etc/ceph')
        self.apt_install.assert_called_with('ceph-common', fatal=True)

    def test_ceph_changed_no_key(self):
        '''It does nothing when ceph key is not available'''
        self.CONFIGS.complete_contexts.return_value = ['']
        hooks.hooks.execute(['hooks/ceph-relation-changed'])
        m = 'ceph relation incomplete. Peer not ready?'
        self.juju_log.assert_called_with(m)

    def test_ceph_changed(self):
        '''It ensures ceph assets created on ceph changed'''
        self.CONFIGS.complete_contexts.return_value = ['ceph']
        self.service_name.return_value = 'cinder'
        self.ensure_ceph_keyring.return_value = True
        hooks.hooks.execute(['hooks/ceph-relation-changed'])
        self.ensure_ceph_keyring.assert_called_with(service='cinder',
                                                    user='cinder',
                                                    group='cinder')
        self.ensure_ceph_pool.assert_called_with(service='cinder', replicas=2)
        for c in [call('/etc/ceph/ceph.conf'),
                  call('/etc/cinder/cinder.conf')]:
            self.assertIn(c, self.CONFIGS.write.call_args_list)
        self.set_ceph_env_variables.assert_called_with(service='cinder')

    def test_ceph_changed_no_keys(self):
        '''It ensures ceph assets created on ceph changed'''
        self.CONFIGS.complete_contexts.return_value = ['ceph']
        self.service_name.return_value = 'cinder'
        self.ensure_ceph_keyring.return_value = False
        hooks.hooks.execute(['hooks/ceph-relation-changed'])
        # NOTE(jamespage): If ensure_ceph keyring fails, then
        # the hook should just exit 0 and return.
        self.assertTrue(self.juju_log.called)
        self.assertFalse(self.CONFIGS.write.called)

    def test_ceph_changed_no_leadership(self):
        '''It does not attempt to create ceph pool if not leader'''
        self.eligible_leader.return_value = False
        self.service_name.return_value = 'cinder'
        self.ensure_ceph_keyring.return_value = True
        hooks.hooks.execute(['hooks/ceph-relation-changed'])
        self.assertFalse(self.ensure_ceph_pool.called)
