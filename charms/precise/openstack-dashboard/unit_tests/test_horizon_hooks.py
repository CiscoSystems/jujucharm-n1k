from mock import MagicMock, patch, call
import horizon_utils as utils
_register_configs = utils.register_configs
utils.register_configs = MagicMock()
import horizon_hooks as hooks
RESTART_MAP = utils.restart_map()
utils.register_configs = _register_configs
from charmhelpers.contrib.hahelpers.cluster import HAIncompleteConfig
from test_utils import CharmTestCase

TO_PATCH = [
    'config',
    'relation_set',
    'relation_get',
    'configure_installation_source',
    'apt_update',
    'apt_install',
    'filter_installed_packages',
    'open_port',
    'CONFIGS',
    'get_hacluster_config',
    'relation_ids',
    'enable_ssl',
    'openstack_upgrade_available',
    'do_openstack_upgrade',
    'save_script_rc',
    'install_ca_cert',
    'unit_get',
    'log',
    'execd_preinstall']


class TestHorizonHooks(CharmTestCase):

    def setUp(self):
        super(TestHorizonHooks, self).setUp(hooks, TO_PATCH)
        self.config.side_effect = self.test_config.get

    def _call_hook(self, hookname):
        hooks.hooks.execute([
            'hooks/{}'.format(hookname)])

    def test_install_hook(self):
        self.filter_installed_packages.return_value = ['foo', 'bar']
        self._call_hook('install')
        self.configure_installation_source.assert_called_with('distro')
        self.apt_update.assert_called_with(fatal=True)
        self.apt_install.assert_called_with(['foo', 'bar'], fatal=True)

    @patch('charmhelpers.core.host.file_hash')
    @patch('charmhelpers.core.host.service')
    def test_upgrade_charm_hook(self, _service, _hash):
        side_effects = []
        [side_effects.append(None) for f in RESTART_MAP.keys()]
        [side_effects.append('bar') for f in RESTART_MAP.keys()]
        _hash.side_effect = side_effects
        self.filter_installed_packages.return_value = ['foo']
        self._call_hook('upgrade-charm')
        self.apt_install.assert_called_with(['foo'], fatal=True)
        self.CONFIGS.write_all.assert_called()
        ex = [
            call('restart', 'apache2'),
            call('restart', 'haproxy')
        ]
        self.assertEquals(ex, _service.call_args_list)

    def test_ha_joined_complete_config(self):
        conf = {
            'ha-bindiface': 'eth100',
            'ha-mcastport': '37373',
            'vip': '192.168.25.163',
            'vip_iface': 'eth101',
            'vip_cidr': '19'
        }
        self.get_hacluster_config.return_value = conf
        self._call_hook('ha-relation-joined')
        ex_args = {
            'corosync_mcastport': '37373',
            'init_services': {
                'res_horizon_haproxy': 'haproxy'},
            'resource_params': {
                'res_horizon_vip':
                'params ip="192.168.25.163" cidr_netmask="19"'
                ' nic="eth101"',
                'res_horizon_haproxy': 'op monitor interval="5s"'},
            'corosync_bindiface': 'eth100',
            'clones': {
                'cl_horizon_haproxy': 'res_horizon_haproxy'},
            'resources': {
                'res_horizon_vip': 'ocf:heartbeat:IPaddr2',
                'res_horizon_haproxy': 'lsb:haproxy'}
        }
        self.relation_set.assert_called_with(**ex_args)

    def test_ha_joined_incomplete_config(self):
        self.get_hacluster_config.side_effect = HAIncompleteConfig(1, 'bang')
        self.assertRaises(HAIncompleteConfig, self._call_hook,
                          'ha-relation-joined')

    @patch('horizon_hooks.keystone_joined')
    def test_config_changed_no_upgrade(self, _joined):
        self.relation_ids.return_value = ['identity/0']
        self.openstack_upgrade_available.return_value = False
        self._call_hook('config-changed')
        _joined.assert_called_with('identity/0')
        self.openstack_upgrade_available.assert_called_with(
            'openstack-dashboard'
        )
        self.enable_ssl.assert_called()
        self.do_openstack_upgrade.assert_not_called()
        self.save_script_rc.assert_called()
        self.CONFIGS.write_all.assert_called()
        self.open_port.assert_has_calls([call(80), call(443)])

    def test_config_changed_do_upgrade(self):
        self.relation_ids.return_value = []
        self.test_config.set('openstack-origin', 'cloud:precise-grizzly')
        self.openstack_upgrade_available.return_value = True
        self._call_hook('config-changed')
        self.do_openstack_upgrade.assert_called()

    def test_keystone_joined_in_relation(self):
        self._call_hook('identity-service-relation-joined')
        self.relation_set.assert_called_with(
            relation_id=None, service='None', region='None',
            public_url='None', admin_url='None', internal_url='None',
            requested_roles='Member'
        )

    def test_keystone_joined_not_in_relation(self):
        hooks.keystone_joined('identity/0')
        self.relation_set.assert_called_with(
            relation_id='identity/0', service='None', region='None',
            public_url='None', admin_url='None', internal_url='None',
            requested_roles='Member'
        )

    def test_keystone_changed_no_cert(self):
        self.relation_get.return_value = None
        self._call_hook('identity-service-relation-changed')
        self.CONFIGS.write.assert_called_with(
            '/etc/openstack-dashboard/local_settings.py'
        )
        self.install_ca_cert.assert_not_called()

    def test_keystone_changed_cert(self):
        self.relation_get.return_value = 'certificate'
        self._call_hook('identity-service-relation-changed')
        self.CONFIGS.write.assert_called_with(
            '/etc/openstack-dashboard/local_settings.py'
        )
        self.install_ca_cert.assert_called_with('certificate')

    def test_cluster_departed(self):
        self._call_hook('cluster-relation-departed')
        self.CONFIGS.write.assert_called_with('/etc/haproxy/haproxy.cfg')

    def test_cluster_changed(self):
        self._call_hook('cluster-relation-changed')
        self.CONFIGS.write.assert_called_with('/etc/haproxy/haproxy.cfg')

    def test_website_joined(self):
        self.unit_get.return_value = '192.168.1.1'
        self._call_hook('website-relation-joined')
        self.relation_set.assert_called_with(port=70, hostname='192.168.1.1')

    @patch('sys.argv')
    @patch.object(hooks, 'install')
    def test_main_hook_exists(self, _install, _argv):
        _argv = ['hooks/install']
        hooks.main()
        _install.assert_called()

    @patch('sys.argv')
    def test_main_hook_missing(self, _argv):
        _argv = ['hooks/start']
        hooks.main()
        self.log.assert_called()
