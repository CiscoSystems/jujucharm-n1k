from collections import OrderedDict
from mock import patch, MagicMock, call
from copy import deepcopy
from test_utils import CharmTestCase, patch_open

from charmhelpers.core import hookenv

_conf = hookenv.config
hookenv.config = MagicMock()

import nova_cc_utils as utils

hookenv.config = _conf

TO_PATCH = [
    'config',
    'log',
    'network_manager',
    'neutron_plugin',
    'neutron_plugin_attribute',
    'os_release',
    'relation_ids',
    'remote_unit',
    '_save_script_rc',
]

SCRIPTRC_ENV_VARS = {
    'OPENSTACK_PORT_MCASTPORT': 5404,
    'OPENSTACK_SERVICE_API_EC2': 'nova-api-ec2',
    'OPENSTACK_SERVICE_API_OS_COMPUTE': 'nova-api-os-compute',
    'OPENSTACK_SERVICE_CERT': 'nova-cert',
    'OPENSTACK_SERVICE_CONDUCTOR': 'nova-conductor',
    'OPENSTACK_SERVICE_OBJECTSTORE': 'nova-objectstore',
    'OPENSTACK_SERVICE_SCHEDULER': 'nova-scheduler',
}


AUTHORIZED_KEYS = """
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC27Us7lSjCpa7bumXAgc nova-compute-1
ssh-rsa BBBBB3NzaC1yc2EBBBBDBQBBBBBBBQC27Us7lSjCpa7bumXBgc nova-compute-2
ssh-rsa CCCCB3NzaC1yc2ECCCCDCQCBCCCBCQC27Us7lSjCpa7bumXCgc nova-compute-3
"""

BASE_ENDPOINTS = {
    'ec2_admin_url': 'http://foohost.com:8773/services/Cloud',
    'ec2_internal_url': 'http://foohost.com:8773/services/Cloud',
    'ec2_public_url': 'http://foohost.com:8773/services/Cloud',
    'ec2_region': 'RegionOne',
    'ec2_service': 'ec2',
    'nova_admin_url': 'http://foohost.com:8774/v1.1/$(tenant_id)s',
    'nova_internal_url': 'http://foohost.com:8774/v1.1/$(tenant_id)s',
    'nova_public_url': 'http://foohost.com:8774/v1.1/$(tenant_id)s',
    'nova_region': 'RegionOne',
    'nova_service': 'nova',
    's3_admin_url': 'http://foohost.com:3333',
    's3_internal_url': 'http://foohost.com:3333',
    's3_public_url': 'http://foohost.com:3333',
    's3_region': 'RegionOne',
    's3_service': 's3'
}

# Restart map should be constructed such that API services restart
# before frontends (haproxy/apaceh) to avoid port conflicts.
RESTART_MAP = OrderedDict([
    ('/etc/nova/nova.conf', [
        'nova-api-ec2', 'nova-api-os-compute', 'nova-objectstore',
        'nova-cert', 'nova-scheduler', 'nova-api-os-volume', 'nova-conductor'
    ]),
    ('/etc/nova/api-paste.ini', [
        'nova-api-ec2', 'nova-api-os-compute'
    ]),
    ('/etc/neutron/neutron.conf', ['neutron-server']),
    ('/etc/default/neutron-server', ['neutron-server']),
    ('/etc/haproxy/haproxy.cfg', ['haproxy']),
    ('/etc/apache2/sites-available/openstack_https_frontend', ['apache2']),
    ('/etc/quantum/plugins/openvswitch/ovs_quantum_plugin.ini',
        ['quantum-server'])
])


PLUGIN_ATTRIBUTES = {
    'ovs': {
        'config': '/etc/quantum/plugins/openvswitch/'
                  'ovs_quantum_plugin.ini',
        'driver': 'quantum.plugins.openvswitch.ovs_quantum_plugin.'
                  'OVSQuantumPluginV2',
        'contexts': ['FakeDBContext'],
        'services': ['quantum-plugin-openvswitch-agent'],
        'packages': ['quantum-plugin-openvswitch-agent',
                     'openvswitch-datapath-dkms'],
        'server_packages': ['quantum-server', 'quantum-plugin-openvswitch'],
        'server_services': ['quantum-server'],
    },
    'nvp': {
        'config': '/etc/quantum/plugins/nicira/nvp.ini',
        'driver': 'quantum.plugins.nicira.nicira_nvp_plugin.'
                  'QuantumPlugin.NvpPluginV2',
        'services': [],
        'packages': [],
        'server_packages': ['quantum-server', 'quantum-plugin-nicria'],
        'server_services': ['quantum-server'],
    }
}


def fake_plugin_attribute(plugin, attr, net_manager):
    if plugin in PLUGIN_ATTRIBUTES:
        try:
            return PLUGIN_ATTRIBUTES[plugin][attr]
        except KeyError:
            pass


class NovaCCUtilsTests(CharmTestCase):

    def setUp(self):
        super(NovaCCUtilsTests, self).setUp(utils, TO_PATCH)
        self.config.side_effect = self.test_config.get

    def _resource_map(self, network_manager=None, volume_manager=None):
        if network_manager:
            self.network_manager.return_value = network_manager
            self.test_config.set('network-manager', network_manager.title())
            self.neutron_plugin.return_value = 'ovs'
            self.neutron_plugin_attribute.side_effect = fake_plugin_attribute
        if volume_manager == 'nova-volume':
            self.relation_ids.return_value = 'nova-volume-service:0'
        with patch('charmhelpers.contrib.openstack.context.'
                   'SubordinateConfigContext'):
            _map = utils.resource_map()
            return _map

    @patch('charmhelpers.contrib.openstack.context.SubordinateConfigContext')
    def test_resource_map_quantum(self, subcontext):
        self._resource_map(network_manager='quantum')
        _map = utils.resource_map()
        confs = [
            '/etc/quantum/quantum.conf',
            '/etc/quantum/api-paste.ini',
            '/etc/quantum/plugins/openvswitch/ovs_quantum_plugin.ini',
        ]
        [self.assertIn(q_conf, _map.keys()) for q_conf in confs]

    @patch('charmhelpers.contrib.openstack.context.SubordinateConfigContext')
    def test_resource_map_neutron(self, subcontext):
        self._resource_map(network_manager='neutron')
        _map = utils.resource_map()
        confs = [
            '/etc/neutron/neutron.conf',
        ]
        [self.assertIn(q_conf, _map.keys()) for q_conf in confs]

    @patch('charmhelpers.contrib.openstack.context.SubordinateConfigContext')
    def test_resource_map_vmware(self, subcontext):
        fake_context = MagicMock()
        fake_context.return_value = {
            'sections': [],
            'services': ['nova-compute', 'nova-network'],

        }
        subcontext.return_value = fake_context
        _map = utils.resource_map()
        for s in ['nova-compute', 'nova-network']:
            self.assertIn(s, _map['/etc/nova/nova.conf']['services'])

    @patch('charmhelpers.contrib.openstack.context.SubordinateConfigContext')
    def test_resource_map_neutron_no_agent_installed(self, subcontext):
        self._resource_map(network_manager='neutron')
        _map = utils.resource_map()
        services = []
        [services.extend(_map[c]['services'])for c in _map]
        for svc in services:
            self.assertNotIn('agent', svc)

    @patch('charmhelpers.contrib.openstack.context.SubordinateConfigContext')
    def test_resource_map_nova_volume(self, subcontext):
        self.relation_ids.return_value = ['nova-volume-service:0']
        _map = utils.resource_map()
        self.assertIn('nova-api-os-volume',
                      _map['/etc/nova/nova.conf']['services'])

    @patch('os.path.exists')
    @patch('charmhelpers.contrib.openstack.context.SubordinateConfigContext')
    def test_restart_map_api_before_frontends(self, subcontext, _exists):
        _exists.return_value = False
        self._resource_map(network_manager='neutron')
        _map = utils.restart_map()
        self.assertTrue(isinstance(_map, OrderedDict))
        self.assertEquals(_map, RESTART_MAP)

    @patch('charmhelpers.contrib.openstack.context.SubordinateConfigContext')
    @patch('os.path.exists')
    def test_restart_map_apache24(self, _exists, subcontext):
        _exists.return_Value = True
        self._resource_map(network_manager='neutron')
        _map = utils.restart_map()
        self.assertTrue('/etc/apache2/sites-available/'
                        'openstack_https_frontend.conf' in _map)
        self.assertTrue('/etc/apache2/sites-available/'
                        'openstack_https_frontend' not in _map)

    @patch('charmhelpers.contrib.openstack.context.SubordinateConfigContext')
    def test_determine_packages_quantum(self, subcontext):
        self._resource_map(network_manager='quantum')
        pkgs = utils.determine_packages()
        self.assertIn('quantum-server', pkgs)

    @patch('charmhelpers.contrib.openstack.context.SubordinateConfigContext')
    def test_determine_packages_neutron(self, subcontext):
        self._resource_map(network_manager='neutron')
        pkgs = utils.determine_packages()
        self.assertIn('neutron-server', pkgs)

    @patch('charmhelpers.contrib.openstack.context.SubordinateConfigContext')
    def test_determine_packages_nova_volume(self, subcontext):
        self.relation_ids.return_value = ['nova-volume-service:0']
        pkgs = utils.determine_packages()
        self.assertIn('nova-api-os-volume', pkgs)

    @patch('charmhelpers.contrib.openstack.context.SubordinateConfigContext')
    def test_determine_packages_base(self, subcontext):
        self.relation_ids.return_value = []
        self.os_release.return_value = 'folsom'
        pkgs = utils.determine_packages()
        ex = list(set(utils.BASE_PACKAGES + utils.BASE_SERVICES))
        self.assertEquals(ex, pkgs)

    @patch('charmhelpers.contrib.openstack.context.SubordinateConfigContext')
    def test_determine_packages_base_grizzly_beyond(self, subcontext):
        self.relation_ids.return_value = []
        self.os_release.return_value = 'grizzly'
        pkgs = utils.determine_packages()
        ex = list(set(utils.BASE_PACKAGES + utils.BASE_SERVICES))
        ex.append('nova-conductor')
        self.assertEquals(sorted(ex), sorted(pkgs))

    @patch.object(utils, 'restart_map')
    def test_determine_ports(self, restart_map):
        restart_map.return_value = {
            '/etc/nova/nova.conf': ['nova-api-os-compute', 'nova-api-ec2'],
            '/etc/nova/api-paste.ini': ['nova-api-os-compute', 'nova-api-ec2'],
            '/etc/quantum/quantum.conf': ['quantum-server'],
        }
        ports = utils.determine_ports()
        ex = [8773, 8774, 9696]
        self.assertEquals(ex, sorted(ports))

    def test_save_script_rc_base(self):
        self.relation_ids.return_value = []
        utils.save_script_rc()
        self._save_script_rc.called_with(**SCRIPTRC_ENV_VARS)

    def test_save_script_quantum(self):
        self.relation_ids.return_value = []
        self.test_config.set('network-manager', 'Quantum')
        utils.save_script_rc()
        _ex = deepcopy(SCRIPTRC_ENV_VARS)
        _ex['OPENSTACK_SERVICE_API_QUANTUM'] = 'quantum-server'
        self._save_script_rc.called_with(**_ex)

    def test_save_script_nova_volume(self):
        self.relation_ids.return_value = ['nvol:0']
        utils.save_script_rc()
        _ex = deepcopy(SCRIPTRC_ENV_VARS)
        _ex['OPENSTACK_SERVICE_API_OS_VOL'] = 'nova-api-os-volume'
        self._save_script_rc.called_with(**_ex)

    def test_determine_volume_service_essex(self):
        self.os_release.return_value = 'essex'
        self.assertEquals('nova-volume', utils.volume_service())

    def test_determine_volume_service_folsom_cinder(self):
        self.os_release.return_value = 'folsom'
        self.relation_ids.return_value = ['cinder:0']
        self.assertEquals('cinder', utils.volume_service())

    def test_determine_volume_service_folsom_nova_vol(self):
        self.os_release.return_value = 'folsom'
        self.relation_ids.return_value = []
        self.assertEquals('nova-volume', utils.volume_service())

    def test_determine_volume_service_grizzly_and_beyond(self):
        pass

    @patch.object(utils, 'remove_known_host')
    @patch.object(utils, 'ssh_known_host_key')
    @patch('subprocess.check_output')
    def test_add_known_host_exists(self, check_output, host_key, rm):
        check_output.return_value = 'fookey'
        host_key.return_value = 'fookey'
        with patch_open() as (_open, _file):
            utils.add_known_host('foohost')
            self.assertFalse(rm.called)
            self.assertFalse(_file.write.called)

    @patch.object(utils, 'known_hosts')
    @patch.object(utils, 'remove_known_host')
    @patch.object(utils, 'ssh_known_host_key')
    @patch('subprocess.check_output')
    def test_add_known_host_exists_outdated(
            self, check_output, host_key, rm, known_hosts):
        check_output.return_value = 'fookey'
        host_key.return_value = 'fookey_old'
        with patch_open() as (_open, _file):
            utils.add_known_host('foohost')
            rm.assert_called_with('foohost')

    @patch.object(utils, 'known_hosts')
    @patch.object(utils, 'remove_known_host')
    @patch.object(utils, 'ssh_known_host_key')
    @patch('subprocess.check_output')
    def test_add_known_host_exists_added(
            self, check_output, host_key, rm, known_hosts):
        check_output.return_value = 'fookey'
        host_key.return_value = None
        with patch_open() as (_open, _file):
            _file.write = MagicMock()
            utils.add_known_host('foohost')
            self.assertFalse(rm.called)
            _file.write.assert_called_with('fookey\n')

    @patch('__builtin__.open')
    @patch('os.mkdir')
    @patch('os.path.isdir')
    def test_ssh_directory_for_unit(self, isdir, mkdir, _open):
        self.remote_unit.return_value = 'nova-compute/0'
        isdir.return_value = False
        self.assertEquals(utils.ssh_directory_for_unit(),
                          '/etc/nova/compute_ssh/nova-compute')
        self.assertIn([
            call('/etc/nova/compute_ssh/nova-compute/authorized_keys', 'w'),
            call('/etc/nova/compute_ssh/nova-compute/known_hosts', 'w')
        ], _open.call_args_list)

    @patch.object(utils, 'ssh_directory_for_unit')
    def test_known_hosts(self, ssh_dir):
        ssh_dir.return_value = '/tmp/foo'
        self.assertEquals(utils.known_hosts(), '/tmp/foo/known_hosts')

    @patch.object(utils, 'ssh_directory_for_unit')
    def test_authorized_keys(self, ssh_dir):
        ssh_dir.return_value = '/tmp/foo'
        self.assertEquals(utils.authorized_keys(), '/tmp/foo/authorized_keys')

    @patch.object(utils, 'known_hosts')
    @patch('subprocess.check_call')
    def test_remove_host_key(self, check_call, known_hosts):
        known_hosts.return_value = '/tmp/known_hosts'
        utils.remove_known_host('foo')
        check_call.assert_called_with([
            'ssh-kegen', '-f', known_hosts(), '-R', 'foo'])

    @patch.object(utils, 'authorized_keys')
    def test_ssh_authorized_key_exists(self, keys):
        key = 'BBBBB3NzaC1yc2EBBBBDBQBBBBBBBQC27Us7lSjCpa7bumXBgc'
        with patch_open() as (_open, _file):
            _file.read.return_value = AUTHORIZED_KEYS
            self.assertTrue(utils.ssh_authorized_key_exists(key))

    @patch.object(utils, 'authorized_keys')
    def test_ssh_authorized_key_doesnt_exist(self, keys):
        key = ('xxxx')
        with patch_open() as (_open, _file):
            _file.read = MagicMock()
            _file.readreturn_value = AUTHORIZED_KEYS
            self.assertFalse(utils.ssh_authorized_key_exists(key))

    @patch.object(utils, 'known_hosts')
    @patch.object(utils, 'authorized_keys')
    @patch('os.path.isfile')
    def test_ssh_compute_remove(self, isfile, auth_key, known_host):
        isfile.return_value = False

        removed_key = AUTHORIZED_KEYS.split('\n')[2]

        keys_removed = (
            "\nssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC27Us7lSjCpa7bumXAgc "
            "nova-compute-1\n"
            "ssh-rsa CCCCB3NzaC1yc2ECCCCDCQCBCCCBCQC27Us7lSjCpa7bumXCgc "
            "nova-compute-3\n"
        )
        isfile.return_value = True
        self.remote_unit.return_value = 'nova-compute/2'
        with patch_open() as (_open, _file):
            _file.readlines = MagicMock()
            _file.write = MagicMock()
            _file.readlines.return_value = AUTHORIZED_KEYS.split('\n')
            utils.ssh_compute_remove(removed_key)
            _file.write.assert_called_with(keys_removed)

    def test_network_manager_untranslated(self):
        self.test_config.set('network-manager', 'foo')
        self.os_release.return_value = 'folsom'

    def test_determine_endpoints_base(self):
        self.relation_ids.return_value = []
        self.assertEquals(
            BASE_ENDPOINTS, utils.determine_endpoints('http://foohost.com'))

    def test_determine_endpoints_nova_volume(self):
        self.relation_ids.return_value = ['nova-volume-service/0']
        endpoints = deepcopy(BASE_ENDPOINTS)
        endpoints.update({
            'nova-volume_admin_url':
            'http://foohost.com:8774/v1/$(tenant_id)s',
            'nova-volume_internal_url':
            'http://foohost.com:8774/v1/$(tenant_id)s',
            'nova-volume_public_url':
            'http://foohost.com:8774/v1/$(tenant_id)s',
            'nova-volume_region': 'RegionOne',
            'nova-volume_service': 'nova-volume'})
        self.assertEquals(
            endpoints, utils.determine_endpoints('http://foohost.com'))

    def test_determine_endpoints_quantum_neutron(self):
        self.relation_ids.return_value = []
        self.network_manager.return_value = 'quantum'
        endpoints = deepcopy(BASE_ENDPOINTS)
        endpoints.update({
            'quantum_admin_url': 'http://foohost.com:9696',
            'quantum_internal_url': 'http://foohost.com:9696',
            'quantum_public_url': 'http://foohost.com:9696',
            'quantum_region': 'RegionOne',
            'quantum_service': 'quantum'})
        self.assertEquals(
            endpoints, utils.determine_endpoints('http://foohost.com'))
