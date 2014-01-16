from mock import MagicMock, patch
import quantum_contexts
from contextlib import contextmanager

from test_utils import (
    CharmTestCase
)

TO_PATCH = [
    'config',
    'relation_get',
    'relation_ids',
    'related_units',
    'context_complete',
    'unit_get',
    'apt_install',
    'get_os_codename_install_source',
    'eligible_leader',
]


@contextmanager
def patch_open():
    '''Patch open() to allow mocking both open() itself and the file that is
    yielded.

    Yields the mock for "open" and "file", respectively.'''
    mock_open = MagicMock(spec=open)
    mock_file = MagicMock(spec=file)

    @contextmanager
    def stub_open(*args, **kwargs):
        mock_open(*args, **kwargs)
        yield mock_file

    with patch('__builtin__.open', stub_open):
        yield mock_open, mock_file


class _TestQuantumContext(CharmTestCase):
    def setUp(self):
        super(_TestQuantumContext, self).setUp(quantum_contexts, TO_PATCH)
        self.config.side_effect = self.test_config.get

    def test_not_related(self):
        self.relation_ids.return_value = []
        self.assertEquals(self.context(), {})

    def test_no_units(self):
        self.relation_ids.return_value = []
        self.relation_ids.return_value = ['foo']
        self.related_units.return_value = []
        self.assertEquals(self.context(), {})

    def test_no_data(self):
        self.relation_ids.return_value = ['foo']
        self.related_units.return_value = ['bar']
        self.relation_get.side_effect = self.test_relation.get
        self.context_complete.return_value = False
        self.assertEquals(self.context(), {})

    def test_data_multi_unit(self):
        self.relation_ids.return_value = ['foo']
        self.related_units.return_value = ['bar', 'baz']
        self.context_complete.return_value = True
        self.relation_get.side_effect = self.test_relation.get
        self.assertEquals(self.context(), self.data_result)

    def test_data_single_unit(self):
        self.relation_ids.return_value = ['foo']
        self.related_units.return_value = ['bar']
        self.context_complete.return_value = True
        self.relation_get.side_effect = self.test_relation.get
        self.assertEquals(self.context(), self.data_result)


class TestQuantumSharedDBContext(_TestQuantumContext):
    def setUp(self):
        super(TestQuantumSharedDBContext, self).setUp()
        self.context = quantum_contexts.QuantumSharedDBContext()
        self.test_relation.set(
            {'db_host': '10.5.0.1',
             'nova_password': 'novapass',
             'quantum_password': 'quantumpass'}
        )
        self.data_result = {
            'database_host': '10.5.0.1',
            'nova_user': 'nova',
            'nova_password': 'novapass',
            'nova_db': 'nova',
            'quantum_user': 'quantum',
            'quantum_password': 'quantumpass',
            'quantum_db': 'quantum'
        }


class TestNetworkServiceContext(_TestQuantumContext):
    def setUp(self):
        super(TestNetworkServiceContext, self).setUp()
        self.context = quantum_contexts.NetworkServiceContext()
        self.test_relation.set(
            {'keystone_host': '10.5.0.1',
             'service_port': '5000',
             'auth_port': '20000',
             'service_tenant': 'tenant',
             'service_username': 'username',
             'service_password': 'password',
             'quantum_host': '10.5.0.2',
             'quantum_port': '9696',
             'quantum_url': 'http://10.5.0.2:9696/v2',
             'region': 'aregion'}
        )
        self.data_result = {
            'keystone_host': '10.5.0.1',
            'service_port': '5000',
            'auth_port': '20000',
            'service_tenant': 'tenant',
            'service_username': 'username',
            'service_password': 'password',
            'quantum_host': '10.5.0.2',
            'quantum_port': '9696',
            'quantum_url': 'http://10.5.0.2:9696/v2',
            'region': 'aregion',
            'service_protocol': 'http',
            'auth_protocol': 'http',
        }


class TestExternalPortContext(CharmTestCase):
    def setUp(self):
        super(TestExternalPortContext, self).setUp(quantum_contexts,
                                                   TO_PATCH)

    def test_no_ext_port(self):
        self.config.return_value = None
        self.assertEquals(quantum_contexts.ExternalPortContext()(),
                          None)

    def test_ext_port(self):
        self.config.return_value = 'eth1010'
        self.assertEquals(quantum_contexts.ExternalPortContext()(),
                          {'ext_port': 'eth1010'})


class TestL3AgentContext(CharmTestCase):
    def setUp(self):
        super(TestL3AgentContext, self).setUp(quantum_contexts,
                                              TO_PATCH)
        self.config.side_effect = self.test_config.get

    def test_no_ext_netid(self):
        self.test_config.set('run-internal-router', 'none')
        self.test_config.set('external-network-id', '')
        self.eligible_leader.return_value = False
        self.assertEquals(quantum_contexts.L3AgentContext()(),
                          {'handle_internal_only_router': False})

    def test_hior_leader(self):
        self.test_config.set('run-internal-router', 'leader')
        self.test_config.set('external-network-id', 'netid')
        self.eligible_leader.return_value = True
        self.assertEquals(quantum_contexts.L3AgentContext()(),
                          {'handle_internal_only_router': True,
                           'ext_net_id': 'netid'})

    def test_hior_all(self):
        self.test_config.set('run-internal-router', 'all')
        self.test_config.set('external-network-id', 'netid')
        self.eligible_leader.return_value = True
        self.assertEquals(quantum_contexts.L3AgentContext()(),
                          {'handle_internal_only_router': True,
                           'ext_net_id': 'netid'})


class TestQuantumGatewayContext(CharmTestCase):
    def setUp(self):
        super(TestQuantumGatewayContext, self).setUp(quantum_contexts,
                                                     TO_PATCH)

    @patch.object(quantum_contexts, 'get_shared_secret')
    @patch.object(quantum_contexts, 'get_host_ip')
    def test_all(self, _host_ip, _secret):
        self.config.return_value = 'ovs'
        self.get_os_codename_install_source.return_value = 'folsom'
        _host_ip.return_value = '10.5.0.1'
        _secret.return_value = 'testsecret'
        self.assertEquals(quantum_contexts.QuantumGatewayContext()(), {
            'shared_secret': 'testsecret',
            'local_ip': '10.5.0.1',
            'core_plugin': "quantum.plugins.openvswitch.ovs_quantum_plugin."
                           "OVSQuantumPluginV2",
            'plugin': 'ovs'
        })


class TestSharedSecret(CharmTestCase):
    def setUp(self):
        super(TestSharedSecret, self).setUp(quantum_contexts,
                                            TO_PATCH)
        self.config.side_effect = self.test_config.get

    @patch('os.path')
    @patch('uuid.uuid4')
    def test_secret_created_stored(self, _uuid4, _path):
        _path.exists.return_value = False
        _uuid4.return_value = 'secret_thing'
        with patch_open() as (_open, _file):
            self.assertEquals(quantum_contexts.get_shared_secret(),
                              'secret_thing')
            _open.assert_called_with(
                quantum_contexts.SHARED_SECRET.format('quantum'), 'w')
            _file.write.assert_called_with('secret_thing')

    @patch('os.path')
    def test_secret_retrieved(self, _path):
        _path.exists.return_value = True
        with patch_open() as (_open, _file):
            _file.read.return_value = 'secret_thing\n'
            self.assertEquals(quantum_contexts.get_shared_secret(),
                              'secret_thing')
            _open.assert_called_with(
                quantum_contexts.SHARED_SECRET.format('quantum'), 'r')


class TestHostIP(CharmTestCase):
    def setUp(self):
        super(TestHostIP, self).setUp(quantum_contexts,
                                      TO_PATCH)
        self.config.side_effect = self.test_config.get

    def test_get_host_ip_already_ip(self):
        self.assertEquals(quantum_contexts.get_host_ip('10.5.0.1'),
                          '10.5.0.1')

    def test_get_host_ip_noarg(self):
        self.unit_get.return_value = "10.5.0.1"
        self.assertEquals(quantum_contexts.get_host_ip(),
                          '10.5.0.1')

    @patch('dns.resolver.query')
    def test_get_host_ip_hostname_unresolvable(self, _query):
        class NXDOMAIN(Exception):
            pass
        _query.side_effect = NXDOMAIN()
        self.assertRaises(NXDOMAIN, quantum_contexts.get_host_ip,
                          'missing.example.com')

    @patch('dns.resolver.query')
    def test_get_host_ip_hostname_resolvable(self, _query):
        data = MagicMock()
        data.address = '10.5.0.1'
        _query.return_value = [data]
        self.assertEquals(quantum_contexts.get_host_ip('myhost.example.com'),
                          '10.5.0.1')
        _query.assert_called_with('myhost.example.com', 'A')


class TestNetworkingName(CharmTestCase):
    def setUp(self):
        super(TestNetworkingName,
              self).setUp(quantum_contexts,
                          TO_PATCH)

    def test_lt_havana(self):
        self.get_os_codename_install_source.return_value = 'folsom'
        self.assertEquals(quantum_contexts.networking_name(), 'quantum')

    def test_ge_havana(self):
        self.get_os_codename_install_source.return_value = 'havana'
        self.assertEquals(quantum_contexts.networking_name(), 'neutron')
