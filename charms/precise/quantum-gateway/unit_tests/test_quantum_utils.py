from mock import MagicMock, call, patch

import charmhelpers.contrib.openstack.templating as templating

templating.OSConfigRenderer = MagicMock()

import quantum_utils


try:
    import neutronclient
except ImportError:
    neutronclient = None

from test_utils import (
    CharmTestCase
)

import charmhelpers.core.hookenv as hookenv


TO_PATCH = [
    'config',
    'get_os_codename_install_source',
    'get_os_codename_package',
    'apt_update',
    'apt_install',
    'configure_installation_source',
    'log',
    'add_bridge',
    'add_bridge_port',
    'networking_name',
    'headers_package',
    'full_restart',
    'service_running',
    'NetworkServiceContext',
    'unit_private_ip',
    'relations_of_type',
    'service_stop',
]


class TestQuantumUtils(CharmTestCase):
    def setUp(self):
        super(TestQuantumUtils, self).setUp(quantum_utils, TO_PATCH)
        self.networking_name.return_value = 'neutron'
        self.headers_package.return_value = 'linux-headers-2.6.18'

    def tearDown(self):
        # Reset cached cache
        hookenv.cache = {}

    def test_valid_plugin(self):
        self.config.return_value = 'ovs'
        self.assertTrue(quantum_utils.valid_plugin())
        self.config.return_value = 'nvp'
        self.assertTrue(quantum_utils.valid_plugin())

    def test_invalid_plugin(self):
        self.config.return_value = 'invalid'
        self.assertFalse(quantum_utils.valid_plugin())

    def test_get_early_packages_ovs(self):
        self.config.return_value = 'ovs'
        self.assertEquals(
            quantum_utils.get_early_packages(),
            ['openvswitch-datapath-dkms', 'linux-headers-2.6.18'])

    def test_get_early_packages_nvp(self):
        self.config.return_value = 'nvp'
        self.assertEquals(
            quantum_utils.get_early_packages(),
            [])

    @patch.object(quantum_utils, 'EARLY_PACKAGES')
    def test_get_early_packages_no_dkms(self, _early_packages):
        pass

    def test_get_early_packages_empty(self):
        self.config.return_value = 'noop'
        self.assertEquals(quantum_utils.get_early_packages(),
                          [])

    def test_get_packages_ovs(self):
        self.config.return_value = 'ovs'
        self.assertNotEqual(quantum_utils.get_packages(), [])

    def test_configure_ovs_starts_service_if_required(self):
        self.config.return_value = 'ovs'
        self.service_running.return_value = False
        quantum_utils.configure_ovs()
        self.assertTrue(self.full_restart.called)

    def test_configure_ovs_doesnt_restart_service(self):
        self.service_running.return_value = True
        quantum_utils.configure_ovs()
        self.assertFalse(self.full_restart.called)

    def test_configure_ovs_ovs_ext_port(self):
        self.config.side_effect = self.test_config.get
        self.test_config.set('plugin', 'ovs')
        self.test_config.set('ext-port', 'eth0')
        quantum_utils.configure_ovs()
        self.add_bridge.assert_has_calls([
            call('br-int'),
            call('br-ex')
        ])
        self.add_bridge_port.assert_called_with('br-ex', 'eth0')

    def test_do_openstack_upgrade(self):
        self.config.side_effect = self.test_config.get
        self.test_config.set('openstack-origin', 'cloud:precise-havana')
        self.test_config.set('plugin', 'ovs')
        self.config.return_value = 'cloud:precise-havana'
        self.get_os_codename_install_source.return_value = 'havana'
        configs = MagicMock()
        quantum_utils.do_openstack_upgrade(configs)
        configs.set_release.assert_called_with(openstack_release='havana')
        self.log.assert_called()
        self.apt_update.assert_called_with(fatal=True)
        dpkg_opts = [
            '--option', 'Dpkg::Options::=--force-confnew',
            '--option', 'Dpkg::Options::=--force-confdef',
        ]
        self.apt_install.assert_called_with(
            packages=quantum_utils.GATEWAY_PKGS['neutron']['ovs'],
            options=dpkg_opts, fatal=True
        )
        self.configure_installation_source.assert_called_with(
            'cloud:precise-havana'
        )

    def test_register_configs_ovs(self):
        self.config.return_value = 'ovs'
        configs = quantum_utils.register_configs()
        confs = [quantum_utils.NEUTRON_DHCP_AGENT_CONF,
                 quantum_utils.NEUTRON_METADATA_AGENT_CONF,
                 quantum_utils.NOVA_CONF,
                 quantum_utils.NEUTRON_CONF,
                 quantum_utils.NEUTRON_L3_AGENT_CONF,
                 quantum_utils.NEUTRON_OVS_PLUGIN_CONF,
                 quantum_utils.EXT_PORT_CONF]
        print configs.register.calls()
        for conf in confs:
            configs.register.assert_any_call(
                conf,
                quantum_utils.CONFIG_FILES['neutron'][quantum_utils.OVS][conf]
                                          ['hook_contexts']
            )

    def test_restart_map_ovs(self):
        self.config.return_value = 'ovs'
        ex_map = {
            quantum_utils.NEUTRON_L3_AGENT_CONF: ['neutron-l3-agent'],
            quantum_utils.NEUTRON_OVS_PLUGIN_CONF:
            ['neutron-plugin-openvswitch-agent'],
            quantum_utils.NOVA_CONF: ['nova-api-metadata'],
            quantum_utils.NEUTRON_METADATA_AGENT_CONF:
            ['neutron-metadata-agent'],
            quantum_utils.NEUTRON_DHCP_AGENT_CONF: ['neutron-dhcp-agent'],
            quantum_utils.NEUTRON_CONF: ['neutron-l3-agent',
                                         'neutron-dhcp-agent',
                                         'neutron-metadata-agent',
                                         'neutron-plugin-openvswitch-agent']
        }
        self.assertEquals(quantum_utils.restart_map(), ex_map)

    def test_register_configs_nvp(self):
        self.config.return_value = 'nvp'
        configs = quantum_utils.register_configs()
        confs = [quantum_utils.NEUTRON_DHCP_AGENT_CONF,
                 quantum_utils.NEUTRON_METADATA_AGENT_CONF,
                 quantum_utils.NOVA_CONF,
                 quantum_utils.NEUTRON_CONF]
        for conf in confs:
            configs.register.assert_any_call(
                conf,
                quantum_utils.CONFIG_FILES['neutron'][quantum_utils.NVP][conf]
                                          ['hook_contexts']
            )

    def test_stop_services_nvp(self):
        self.config.return_value = 'nvp'
        quantum_utils.stop_services()
        calls = [
            call('neutron-dhcp-agent'),
            call('nova-api-metadata'),
            call('neutron-metadata-agent')
        ]
        self.service_stop.assert_has_calls(
            calls,
            any_order=True,
        )

    def test_stop_services_ovs(self):
        self.config.return_value = 'ovs'
        quantum_utils.stop_services()
        calls = [call('neutron-dhcp-agent'),
                 call('neutron-plugin-openvswitch-agent'),
                 call('nova-api-metadata'),
                 call('neutron-l3-agent'),
                 call('neutron-metadata-agent')]
        self.service_stop.assert_has_calls(
            calls,
            any_order=True,
        )

    def test_restart_map_nvp(self):
        self.config.return_value = 'nvp'
        ex_map = {
            quantum_utils.NEUTRON_DHCP_AGENT_CONF: ['neutron-dhcp-agent'],
            quantum_utils.NOVA_CONF: ['nova-api-metadata'],
            quantum_utils.NEUTRON_CONF: ['neutron-dhcp-agent',
                                         'neutron-metadata-agent'],
            quantum_utils.NEUTRON_METADATA_AGENT_CONF:
            ['neutron-metadata-agent'],
        }
        self.assertEquals(quantum_utils.restart_map(), ex_map)

    def test_register_configs_pre_install(self):
        self.config.return_value = 'ovs'
        self.networking_name.return_value = 'quantum'
        configs = quantum_utils.register_configs()
        confs = [quantum_utils.QUANTUM_DHCP_AGENT_CONF,
                 quantum_utils.QUANTUM_METADATA_AGENT_CONF,
                 quantum_utils.NOVA_CONF,
                 quantum_utils.QUANTUM_CONF,
                 quantum_utils.QUANTUM_L3_AGENT_CONF,
                 quantum_utils.QUANTUM_OVS_PLUGIN_CONF,
                 quantum_utils.EXT_PORT_CONF]
        print configs.register.mock_calls
        for conf in confs:
            configs.register.assert_any_call(
                conf,
                quantum_utils.CONFIG_FILES['quantum'][quantum_utils.OVS][conf]
                                          ['hook_contexts']
            )

    def test_get_common_package_quantum(self):
        self.get_os_codename_package.return_value = 'folsom'
        self.assertEquals(quantum_utils.get_common_package(), 'quantum-common')

    def test_get_common_package_neutron(self):
        self.get_os_codename_package.return_value = None
        self.assertEquals(quantum_utils.get_common_package(), 'neutron-common')


network_context = {
    'service_username': 'foo',
    'service_password': 'bar',
    'service_tenant': 'baz',
    'region': 'foo-bar',
    'keystone_host': 'keystone',
    'auth_port': 5000
}


class DummyNetworkServiceContext():
    def __init__(self, return_value):
        self.return_value = return_value

    def __call__(self):
        return self.return_value

agents_all_alive = {
    'DHCP Agent': {
        'agents': [
            {'alive': True,
             'host': 'cluster1-machine1.internal',
             'id': '3e3550f2-38cc-11e3-9617-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster1-machine2.internal',
             'id': '53d6eefc-38cc-11e3-b3c8-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine1.internal',
             'id': '92b8b6bc-38ce-11e3-8537-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine3.internal',
             'id': 'ebdcc950-51c8-11e3-a804-1c6f65b044df'},
        ]
    },
    'L3 Agent': {
        'agents': [
            {'alive': True,
             'host': 'cluster1-machine1.internal',
             'id': '7128198e-38ce-11e3-ba78-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster1-machine2.internal',
             'id': '72453824-38ce-11e3-938e-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine1.internal',
             'id': '84a04126-38ce-11e3-9449-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine3.internal',
             'id': '00f4268a-51c9-11e3-9177-1c6f65b044df'},
        ]
    }
}

agents_some_dead_cl1 = {
    'DHCP Agent': {
        'agents': [
            {'alive': False,
             'host': 'cluster1-machine1.internal',
             'id': '3e3550f2-38cc-11e3-9617-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine1.internal',
             'id': '53d6eefc-38cc-11e3-b3c8-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine2.internal',
             'id': '92b8b6bc-38ce-11e3-8537-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine3.internal',
             'id': 'ebdcc950-51c8-11e3-a804-1c6f65b044df'},
        ]
    },
    'L3 Agent': {
        'agents': [
            {'alive': False,
             'host': 'cluster1-machine1.internal',
             'id': '7128198e-38ce-11e3-ba78-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine1.internal',
             'id': '72453824-38ce-11e3-938e-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine2.internal',
             'id': '84a04126-38ce-11e3-9449-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine3.internal',
             'id': '00f4268a-51c9-11e3-9177-1c6f65b044df'},
        ]
    }
}

agents_some_dead_cl2 = {
    'DHCP Agent': {
        'agents': [
            {'alive': True,
             'host': 'cluster1-machine1.internal',
             'id': '3e3550f2-38cc-11e3-9617-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine1.internal',
             'id': '53d6eefc-38cc-11e3-b3c8-3c970e8b1cf7'},
            {'alive': False,
             'host': 'cluster2-machine2.internal',
             'id': '92b8b6bc-38ce-11e3-8537-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine3.internal',
             'id': 'ebdcc950-51c8-11e3-a804-1c6f65b044df'},
        ]
    },
    'L3 Agent': {
        'agents': [
            {'alive': True,
             'host': 'cluster1-machine1.internal',
             'id': '7128198e-38ce-11e3-ba78-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine1.internal',
             'id': '72453824-38ce-11e3-938e-3c970e8b1cf7'},
            {'alive': False,
             'host': 'cluster2-machine2.internal',
             'id': '84a04126-38ce-11e3-9449-3c970e8b1cf7'},
            {'alive': True,
             'host': 'cluster2-machine3.internal',
             'id': '00f4268a-51c9-11e3-9177-1c6f65b044df'},
        ]
    }
}

dhcp_agent_networks = {
    'networks': [
        {'id': 'foo'},
        {'id': 'bar'}
    ]
}

l3_agent_routers = {
    'routers': [
        {'id': 'baz'},
        {'id': 'bong'}
    ]
}

cluster1 = ['cluster1-machine1.internal']
cluster2 = ['cluster2-machine1.internal', 'cluster2-machine2.internal'
            'cluster2-machine3.internal']


class TestQuantumAgentReallocation(CharmTestCase):
    def setUp(self):
        if not neutronclient:
            raise self.skipTest('Skipping, no neutronclient installed')
        super(TestQuantumAgentReallocation, self).setUp(quantum_utils,
                                                        TO_PATCH)

    def tearDown(self):
        # Reset cached cache
        hookenv.cache = {}

    def test_no_network_context(self):
        self.NetworkServiceContext.return_value = \
            DummyNetworkServiceContext(return_value=None)
        quantum_utils.reassign_agent_resources()
        self.log.assert_called()

    @patch('neutronclient.v2_0.client.Client')
    def test_no_down_agents(self, _client):
        self.NetworkServiceContext.return_value = \
            DummyNetworkServiceContext(return_value=network_context)
        dummy_client = MagicMock()
        dummy_client.list_agents.side_effect = agents_all_alive.itervalues()
        _client.return_value = dummy_client
        quantum_utils.reassign_agent_resources()
        dummy_client.add_router_to_l3_agent.assert_not_called()
        dummy_client.remove_router_from_l3_agent.assert_not_called()
        dummy_client.add_network_to_dhcp_agent.assert_not_called()
        dummy_client.remove_network_from_dhcp_agent.assert_not_called()

    @patch('neutronclient.v2_0.client.Client')
    def test_agents_down_relocation_required(self, _client):
        self.NetworkServiceContext.return_value = \
            DummyNetworkServiceContext(return_value=network_context)
        dummy_client = MagicMock()
        dummy_client.list_agents.side_effect = \
            agents_some_dead_cl2.itervalues()
        dummy_client.list_networks_on_dhcp_agent.return_value = \
            dhcp_agent_networks
        dummy_client.list_routers_on_l3_agent.return_value = \
            l3_agent_routers
        _client.return_value = dummy_client
        self.unit_private_ip.return_value = 'cluster2-machine1.internal'
        self.relations_of_type.return_value = \
            [{'private-address': 'cluster2-machine3.internal'}]
        quantum_utils.reassign_agent_resources()

        # Ensure routers removed from dead l3 agent
        dummy_client.remove_router_from_l3_agent.assert_has_calls(
            [call(l3_agent='84a04126-38ce-11e3-9449-3c970e8b1cf7',
                  router_id='bong'),
             call(l3_agent='84a04126-38ce-11e3-9449-3c970e8b1cf7',
                  router_id='baz')], any_order=True)
        # and re-assigned across the remaining two live agents
        dummy_client.add_router_to_l3_agent.assert_has_calls(
            [call(l3_agent='00f4268a-51c9-11e3-9177-1c6f65b044df',
                  body={'router_id': 'baz'}),
             call(l3_agent='72453824-38ce-11e3-938e-3c970e8b1cf7',
                  body={'router_id': 'bong'})], any_order=True)
        # Ensure networks removed from dead dhcp agent
        dummy_client.remove_network_from_dhcp_agent.assert_has_calls(
            [call(dhcp_agent='92b8b6bc-38ce-11e3-8537-3c970e8b1cf7',
                  network_id='foo'),
             call(dhcp_agent='92b8b6bc-38ce-11e3-8537-3c970e8b1cf7',
                  network_id='bar')], any_order=True)
        # and re-assigned across the remaining two live agents
        dummy_client.add_network_to_dhcp_agent.assert_has_calls(
            [call(dhcp_agent='53d6eefc-38cc-11e3-b3c8-3c970e8b1cf7',
                  body={'network_id': 'foo'}),
             call(dhcp_agent='ebdcc950-51c8-11e3-a804-1c6f65b044df',
                  body={'network_id': 'bar'})], any_order=True)

    @patch('neutronclient.v2_0.client.Client')
    def test_agents_down_relocation_impossible(self, _client):
        self.NetworkServiceContext.return_value = \
            DummyNetworkServiceContext(return_value=network_context)
        dummy_client = MagicMock()
        dummy_client.list_agents.side_effect = \
            agents_some_dead_cl1.itervalues()
        dummy_client.list_networks_on_dhcp_agent.return_value = \
            dhcp_agent_networks
        dummy_client.list_routers_on_l3_agent.return_value = \
            l3_agent_routers
        _client.return_value = dummy_client
        self.unit_private_ip.return_value = 'cluster1-machine1.internal'
        self.relations_of_type.return_value = []
        quantum_utils.reassign_agent_resources()
        self.log.assert_called()
        assert not dummy_client.remove_router_from_l3_agent.called
        assert not dummy_client.remove_network_from_dhcp_agent.called
