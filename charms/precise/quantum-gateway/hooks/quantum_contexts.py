# vim: set ts=4:et
import os
import uuid
import socket
from charmhelpers.core.hookenv import (
    config,
    relation_ids,
    related_units,
    relation_get,
    unit_get,
    cached,
)
from charmhelpers.fetch import (
    apt_install,
)
from charmhelpers.contrib.openstack.context import (
    OSContextGenerator,
    context_complete
)
from charmhelpers.contrib.openstack.utils import (
    get_os_codename_install_source
)
from charmhelpers.contrib.hahelpers.cluster import(
    eligible_leader
)

DB_USER = "quantum"
QUANTUM_DB = "quantum"
NOVA_DB_USER = "nova"
NOVA_DB = "nova"

QUANTUM_OVS_PLUGIN = \
    "quantum.plugins.openvswitch.ovs_quantum_plugin.OVSQuantumPluginV2"
QUANTUM_NVP_PLUGIN = \
    "quantum.plugins.nicira.nicira_nvp_plugin.QuantumPlugin.NvpPluginV2"
QUANTUM_N1KV_PLUGIN = \
    "quantum.plugins.cisco.n1kv.n1kv_quantum_plugin.N1kvQuantumPluginV2"
NEUTRON_OVS_PLUGIN = \
    "neutron.plugins.openvswitch.ovs_neutron_plugin.OVSNeutronPluginV2"
NEUTRON_NVP_PLUGIN = \
    "neutron.plugins.nicira.nicira_nvp_plugin.NeutronPlugin.NvpPluginV2"
NEUTRON_N1KV_PLUGIN = \
    "neutron.plugins.cisco.n1kv.n1kv_neutron_plugin.N1kvNeutronPluginV2"
NEUTRON = 'neutron'
QUANTUM = 'quantum'


def networking_name():
    ''' Determine whether neutron or quantum should be used for name '''
    if get_os_codename_install_source(config('openstack-origin')) >= 'havana':
        return NEUTRON
    else:
        return QUANTUM

OVS = 'ovs'
NVP = 'nvp'
N1KV = 'n1kv'

CORE_PLUGIN = {
    QUANTUM: {
        OVS: QUANTUM_OVS_PLUGIN,
        NVP: QUANTUM_NVP_PLUGIN,
        N1KV: QUANTUM_N1KV_PLUGIN
    },
    NEUTRON: {
        OVS: NEUTRON_OVS_PLUGIN,
        NVP: NEUTRON_NVP_PLUGIN,
        N1KV: NEUTRON_N1KV_PLUGIN
    },
}


def core_plugin():
    return CORE_PLUGIN[networking_name()][config('plugin')]


class NetworkServiceContext(OSContextGenerator):
    interfaces = ['quantum-network-service']

    def __call__(self):
        for rid in relation_ids('quantum-network-service'):
            for unit in related_units(rid):
                ctxt = {
                    'keystone_host': relation_get('keystone_host',
                                                  rid=rid, unit=unit),
                    'service_port': relation_get('service_port', rid=rid,
                                                 unit=unit),
                    'auth_port': relation_get('auth_port', rid=rid, unit=unit),
                    'service_tenant': relation_get('service_tenant',
                                                   rid=rid, unit=unit),
                    'service_username': relation_get('service_username',
                                                     rid=rid, unit=unit),
                    'service_password': relation_get('service_password',
                                                     rid=rid, unit=unit),
                    'quantum_host': relation_get('quantum_host',
                                                 rid=rid, unit=unit),
                    'quantum_port': relation_get('quantum_port',
                                                 rid=rid, unit=unit),
                    'quantum_url': relation_get('quantum_url',
                                                rid=rid, unit=unit),
                    'region': relation_get('region',
                                           rid=rid, unit=unit),
                    # XXX: Hard-coded http.
                    'service_protocol': 'http',
                    'auth_protocol': 'http',
                }
                if context_complete(ctxt):
                    return ctxt
        return {}


class L3AgentContext(OSContextGenerator):
    def __call__(self):
        ctxt = {}
        if config('run-internal-router') == 'leader':
            ctxt['handle_internal_only_router'] = eligible_leader(None)

        if config('run-internal-router') == 'all':
            ctxt['handle_internal_only_router'] = True

        if config('run-internal-router') == 'none':
            ctxt['handle_internal_only_router'] = False

        if config('external-network-id'):
            ctxt['ext_net_id'] = config('external-network-id')

        if config('plugin'):
            ctxt['plugin'] = config('plugin')
        return ctxt


class ExternalPortContext(OSContextGenerator):
    def __call__(self):
        if config('ext-port'):
            return {"ext_port": config('ext-port')}
        else:
            return None


class QuantumGatewayContext(OSContextGenerator):
    def __call__(self):
        ctxt = {
            'shared_secret': get_shared_secret(),
            'local_ip': get_host_ip(),  # XXX: data network impact
            'core_plugin': core_plugin(),
            'plugin': config('plugin')
        }
        return ctxt


class QuantumSharedDBContext(OSContextGenerator):
    interfaces = ['shared-db']

    def __call__(self):
        for rid in relation_ids('shared-db'):
            for unit in related_units(rid):
                ctxt = {
                    'database_host': relation_get('db_host', rid=rid,
                                                  unit=unit),
                    'quantum_db': QUANTUM_DB,
                    'quantum_user': DB_USER,
                    'quantum_password': relation_get('quantum_password',
                                                     rid=rid, unit=unit),
                    'nova_db': NOVA_DB,
                    'nova_user': NOVA_DB_USER,
                    'nova_password': relation_get('nova_password', rid=rid,
                                                  unit=unit)
                }
                if context_complete(ctxt):
                    return ctxt
        return {}


@cached
def get_host_ip(hostname=None):
    try:
        import dns.resolver
    except ImportError:
        apt_install('python-dnspython', fatal=True)
        import dns.resolver
    hostname = hostname or unit_get('private-address')
    try:
        # Test to see if already an IPv4 address
        socket.inet_aton(hostname)
        return hostname
    except socket.error:
        answers = dns.resolver.query(hostname, 'A')
        if answers:
            return answers[0].address


SHARED_SECRET = "/etc/{}/secret.txt"


def get_shared_secret():
    secret = None
    _path = SHARED_SECRET.format(networking_name())
    if not os.path.exists(_path):
        secret = str(uuid.uuid4())
        with open(_path, 'w') as secret_file:
            secret_file.write(secret)
    else:
        with open(_path, 'r') as secret_file:
            secret = secret_file.read().strip()
    return secret
