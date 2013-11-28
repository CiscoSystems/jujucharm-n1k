from mock import MagicMock, patch

from test_utils import CharmTestCase

import nova_cc_utils as utils

_reg = utils.register_configs
_map = utils.restart_map

utils.register_configs = MagicMock()
utils.restart_map = MagicMock()

import nova_cc_hooks as hooks

utils.register_configs = _reg
utils.restart_map = _map


TO_PATCH = [
    'api_port',
    'apt_update',
    'apt_install',
    'canonical_url',
    'configure_installation_source',
    'charm_dir',
    'do_openstack_upgrade',
    'openstack_upgrade_available',
    'config',
    'determine_packages',
    'determine_ports',
    'open_port',
    'relation_get',
    'relation_set',
    'ssh_compute_add',
    'ssh_known_hosts_b64',
    'ssh_authorized_keys_b64',
    'save_script_rc',
    'execd_preinstall',
    'network_manager',
    'volume_service',
    'unit_get',
    'eligible_leader',
    'keystone_ca_cert_b64',
    'neutron_plugin',
]


FAKE_KS_AUTH_CFG = {
    'auth_host': 'kshost',
    'auth_port': '5000',
    'service_port': 'token',
    'service_username': 'admin_user',
    'service_password': 'admin_passwd',
    'service_tenant_name': 'admin_tenant',
    'auth_uri': 'http://kshost:5000/v2',
    # quantum-gateway interface deviates a bit.
    'keystone_host': 'kshost',
    'service_tenant': 'service_tenant',
}


class NovaCCHooksTests(CharmTestCase):

    def setUp(self):
        super(NovaCCHooksTests, self).setUp(hooks, TO_PATCH)
        self.config.side_effect = self.test_config.get
        self.relation_get.side_effect = self.test_relation.get
        self.charm_dir.return_value = '/var/lib/juju/charms/nova/charm'

    def test_install_hook(self):
        self.determine_packages.return_value = [
            'nova-scheduler', 'nova-api-ec2']
        self.determine_ports.return_value = [80, 81, 82]
        hooks.install()
        self.apt_install.assert_called_with(
            ['nova-scheduler', 'nova-api-ec2'], fatal=True)
        self.execd_preinstall.assert_called()

    @patch.object(hooks, 'configure_https')
    def test_config_changed_no_upgrade(self, conf_https):
        self.openstack_upgrade_available.return_value = False
        hooks.config_changed()
        self.assertTrue(self.save_script_rc.called)

    @patch.object(hooks, 'configure_https')
    def test_config_changed_with_upgrade(self, conf_https):
        self.openstack_upgrade_available.return_value = True
        hooks.config_changed()
        self.assertTrue(self.do_openstack_upgrade.called)
        self.assertTrue(self.save_script_rc.called)

    def test_compute_changed_ssh_migration(self):
        self.test_relation.set({
            'migration_auth_type': 'ssh', 'ssh_public_key': 'fookey',
            'private-address': '10.0.0.1'})
        self.ssh_known_hosts_b64.return_value = 'hosts'
        self.ssh_authorized_keys_b64.return_value = 'keys'
        hooks.compute_changed()
        self.ssh_compute_add.assert_called_with('fookey')
        self.relation_set.assert_called_with(known_hosts='hosts',
                                             authorized_keys='keys')

    @patch.object(hooks, '_auth_config')
    def test_compute_joined_neutron(self, auth_config):
        self.network_manager.return_value = 'neutron'
        self.eligible_leader = True
        self.keystone_ca_cert_b64.return_value = 'foocert64'
        self.volume_service.return_value = 'cinder'
        self.unit_get.return_value = 'nova-cc-host1'
        self.canonical_url.return_value = 'http://nova-cc-host1'
        self.api_port.return_value = '9696'
        self.neutron_plugin.return_value = 'nvp'
        auth_config.return_value = FAKE_KS_AUTH_CFG
        hooks.compute_joined()

        self.relation_set.assert_called_with(
            relation_id=None,
            quantum_url='http://nova-cc-host1:9696',
            ca_cert='foocert64',
            quantum_security_groups='no',
            region='RegionOne',
            volume_service='cinder',
            ec2_host='nova-cc-host1',
            quantum_plugin='nvp',
            network_manager='neutron', **FAKE_KS_AUTH_CFG)

    @patch.object(hooks, '_auth_config')
    def test_nova_vmware_joined(self, auth_config):
        auth_config.return_value = FAKE_KS_AUTH_CFG
        # quantum-security-groups, plugin
        self.neutron_plugin.return_value = 'nvp'
        self.network_manager.return_value = 'neutron'
        self.canonical_url.return_value = 'http://nova-cc-host1'
        self.api_port.return_value = '9696'
        hooks.nova_vmware_relation_joined()
        self.relation_set.assert_called_with(
            network_manager='neutron', quantum_security_groups='no',
            quantum_url='http://nova-cc-host1:9696', quantum_plugin='nvp',
            relation_id=None,
            **FAKE_KS_AUTH_CFG)
