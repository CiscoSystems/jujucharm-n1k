from charmhelpers.core.host import (
    service_running,
    service_stop
)
from charmhelpers.core.hookenv import (
    log,
    config,
    relations_of_type,
    unit_private_ip
)
from charmhelpers.fetch import (
    apt_install,
    apt_update
)
from charmhelpers.contrib.network.ovs import (
    add_bridge,
    add_bridge_port,
    full_restart
)
from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    get_os_codename_install_source,
    get_os_codename_package,
    get_hostname
)

import charmhelpers.contrib.openstack.context as context
import charmhelpers.contrib.openstack.templating as templating
from charmhelpers.contrib.openstack.neutron import headers_package
from quantum_contexts import (
    CORE_PLUGIN, OVS, NVP, N1KV,
    NEUTRON, QUANTUM,
    networking_name,
    QuantumGatewayContext,
    NetworkServiceContext,
    L3AgentContext,
    QuantumSharedDBContext,
    ExternalPortContext,
)


def valid_plugin():
    return config('plugin') in CORE_PLUGIN[networking_name()]

QUANTUM_OVS_PLUGIN_CONF = \
    "/etc/quantum/plugins/openvswitch/ovs_quantum_plugin.ini"
QUANTUM_NVP_PLUGIN_CONF = \
    "/etc/quantum/plugins/nicira/nvp.ini"
QUANTUM_N1KV_PLUGIN_CONF = \
    "/etc/quantum/plugins/cisco/cisco_plugins.ini"
QUANTUM_PLUGIN_CONF = {
    OVS: QUANTUM_OVS_PLUGIN_CONF,
    NVP: QUANTUM_NVP_PLUGIN_CONF,
    N1KV: QUANTUM_N1KV_PLUGIN_CONF
}

NEUTRON_OVS_PLUGIN_CONF = \
    "/etc/neutron/plugins/openvswitch/ovs_neutron_plugin.ini"
NEUTRON_NVP_PLUGIN_CONF = \
    "/etc/neutron/plugins/nicira/nvp.ini"
NEUTRON_N1KV_PLUGIN_CONF = \
    "/etc/neutron/plugins/cisco/cisco_plugins.ini"
NEUTRON_PLUGIN_CONF = {
    OVS: NEUTRON_OVS_PLUGIN_CONF,
    NVP: NEUTRON_NVP_PLUGIN_CONF,
    N1KV: NEUTRON_N1KV_PLUGIN_CONF
}

QUANTUM_GATEWAY_PKGS = {
    OVS: [
        "quantum-plugin-openvswitch-agent",
        "quantum-l3-agent",
        "quantum-dhcp-agent",
        'python-mysqldb',
        "nova-api-metadata"
    ],
    NVP: [
        "openvswitch-switch",
        "quantum-dhcp-agent",
        'python-mysqldb',
        "nova-api-metadata"
    ],
    N1KV: [
        "neutron-plugin-cisco",
        "openvswitch-switch",
        "neutron-dhcp-agent",
        "python-mysqldb",
        "nova-api-metadata",
        "neutron-common",
        "quantum-l3-agent"
    ]
}

NEUTRON_GATEWAY_PKGS = {
    OVS: [
        "neutron-plugin-openvswitch-agent",
        "openvswitch-switch",
        "neutron-l3-agent",
        "neutron-dhcp-agent",
        'python-mysqldb',
        'python-oslo.config',  # Force upgrade
        "nova-api-metadata"
    ],
    NVP: [
        "neutron-dhcp-agent",
        'python-mysqldb',
        'python-oslo.config',  # Force upgrade
        "nova-api-metadata"
    ],
    N1KV: [
        "neutron-plugin-cisco",
        "neutron-dhcp-agent",
        "python-mysqldb",
        "nova-api-metadata",
        "neutron-common",
        "neutron-l3-agent"
    ]
}

GATEWAY_PKGS = {
    QUANTUM: QUANTUM_GATEWAY_PKGS,
    NEUTRON: NEUTRON_GATEWAY_PKGS,
}

EARLY_PACKAGES = {
    OVS: ['openvswitch-datapath-dkms'],
    NVP: [],
    N1KV: []
}


def get_early_packages():
    '''Return a list of package for pre-install based on configured plugin'''
    if config('plugin') in EARLY_PACKAGES:
        pkgs = EARLY_PACKAGES[config('plugin')]
    else:
        return []

    # ensure headers are installed build any required dkms packages
    if [p for p in pkgs if 'dkms' in p]:
        return pkgs + [headers_package()]
    return pkgs


def get_packages():
    '''Return a list of packages for install based on the configured plugin'''
    return GATEWAY_PKGS[networking_name()][config('plugin')]


def get_common_package():
    if get_os_codename_package('quantum-common', fatal=False) is not None:
        return 'quantum-common'
    else:
        return 'neutron-common'

EXT_PORT_CONF = '/etc/init/ext-port.conf'
TEMPLATES = 'templates'

QUANTUM_CONF = "/etc/quantum/quantum.conf"
QUANTUM_L3_AGENT_CONF = "/etc/quantum/l3_agent.ini"
QUANTUM_DHCP_AGENT_CONF = "/etc/quantum/dhcp_agent.ini"
QUANTUM_METADATA_AGENT_CONF = "/etc/quantum/metadata_agent.ini"

NEUTRON_CONF = "/etc/neutron/neutron.conf"
NEUTRON_L3_AGENT_CONF = "/etc/neutron/l3_agent.ini"
NEUTRON_DHCP_AGENT_CONF = "/etc/neutron/dhcp_agent.ini"
NEUTRON_METADATA_AGENT_CONF = "/etc/neutron/metadata_agent.ini"

NOVA_CONF = "/etc/nova/nova.conf"

NOVA_CONFIG_FILES = {
    NOVA_CONF: {
        'hook_contexts': [context.AMQPContext(),
                          QuantumSharedDBContext(),
                          NetworkServiceContext(),
                          QuantumGatewayContext()],
        'services': ['nova-api-metadata']
    },
}

QUANTUM_SHARED_CONFIG_FILES = {
    QUANTUM_DHCP_AGENT_CONF: {
        'hook_contexts': [QuantumGatewayContext()],
        'services': ['quantum-dhcp-agent']
    },
    QUANTUM_METADATA_AGENT_CONF: {
        'hook_contexts': [NetworkServiceContext(),
                          QuantumGatewayContext()],
        'services': ['quantum-metadata-agent']
    },
}
QUANTUM_SHARED_CONFIG_FILES.update(NOVA_CONFIG_FILES)

NEUTRON_SHARED_CONFIG_FILES = {
    NEUTRON_DHCP_AGENT_CONF: {
        'hook_contexts': [QuantumGatewayContext()],
        'services': ['neutron-dhcp-agent']
    },
    NEUTRON_METADATA_AGENT_CONF: {
        'hook_contexts': [NetworkServiceContext(),
                          QuantumGatewayContext()],
        'services': ['neutron-metadata-agent']
    },
}
NEUTRON_SHARED_CONFIG_FILES.update(NOVA_CONFIG_FILES)

QUANTUM_OVS_CONFIG_FILES = {
    QUANTUM_CONF: {
        'hook_contexts': [context.AMQPContext(),
                          QuantumGatewayContext()],
        'services': ['quantum-l3-agent',
                     'quantum-dhcp-agent',
                     'quantum-metadata-agent',
                     'quantum-plugin-openvswitch-agent']
    },
    QUANTUM_L3_AGENT_CONF: {
        'hook_contexts': [NetworkServiceContext()],
        'services': ['quantum-l3-agent']
    },
    # TODO: Check to see if this is actually required
    QUANTUM_OVS_PLUGIN_CONF: {
        'hook_contexts': [QuantumSharedDBContext(),
                          QuantumGatewayContext()],
        'services': ['quantum-plugin-openvswitch-agent']
    },
    EXT_PORT_CONF: {
        'hook_contexts': [ExternalPortContext()],
        'services': []
    }
}
QUANTUM_OVS_CONFIG_FILES.update(QUANTUM_SHARED_CONFIG_FILES)

NEUTRON_OVS_CONFIG_FILES = {
    NEUTRON_CONF: {
        'hook_contexts': [context.AMQPContext(),
                          QuantumGatewayContext()],
        'services': ['neutron-l3-agent',
                     'neutron-dhcp-agent',
                     'neutron-metadata-agent',
                     'neutron-plugin-openvswitch-agent']
    },
    NEUTRON_L3_AGENT_CONF: {
        'hook_contexts': [NetworkServiceContext(),
                          L3AgentContext()],
        'services': ['neutron-l3-agent']
    },
    # TODO: Check to see if this is actually required
    NEUTRON_OVS_PLUGIN_CONF: {
        'hook_contexts': [QuantumSharedDBContext(),
                          QuantumGatewayContext()],
        'services': ['neutron-plugin-openvswitch-agent']
    },
    EXT_PORT_CONF: {
        'hook_contexts': [ExternalPortContext()],
        'services': []
    }
}
NEUTRON_OVS_CONFIG_FILES.update(NEUTRON_SHARED_CONFIG_FILES)

QUANTUM_NVP_CONFIG_FILES = {
    QUANTUM_CONF: {
        'hook_contexts': [context.AMQPContext()],
        'services': ['quantum-dhcp-agent', 'quantum-metadata-agent']
    },
}
QUANTUM_NVP_CONFIG_FILES.update(QUANTUM_SHARED_CONFIG_FILES)

NEUTRON_NVP_CONFIG_FILES = {
    NEUTRON_CONF: {
        'hook_contexts': [context.AMQPContext()],
        'services': ['neutron-dhcp-agent', 'neutron-metadata-agent']
    },
}
NEUTRON_NVP_CONFIG_FILES.update(NEUTRON_SHARED_CONFIG_FILES)

QUANTUM_N1KV_CONFIG_FILES = {
    QUANTUM_CONF: {
        'hook_contexts': [context.AMQPContext()],
        'services': ['quantum-dhcp-agent', 'quantum-metadata-agent']
    },
}
QUANTUM_N1KV_CONFIG_FILES.update(QUANTUM_SHARED_CONFIG_FILES)

NEUTRON_N1KV_CONFIG_FILES = {
    NEUTRON_CONF: {
        'hook_contexts': [context.AMQPContext()],
        'services': ['neutron-dhcp-agent',
                     'neutron-metadata-agent']
    },
    NEUTRON_L3_AGENT_CONF: {
        'hook_contexts': [NetworkServiceContext(),
                          L3AgentContext()],
        'services': ['neutron-l3-agent']
    },
}
NEUTRON_N1KV_CONFIG_FILES.update(NEUTRON_SHARED_CONFIG_FILES)

CONFIG_FILES = {
    QUANTUM: {
        NVP: QUANTUM_NVP_CONFIG_FILES,
        OVS: QUANTUM_OVS_CONFIG_FILES,
        N1KV: QUANTUM_N1KV_CONFIG_FILES,
    },
    NEUTRON: {
        NVP: NEUTRON_NVP_CONFIG_FILES,
        OVS: NEUTRON_OVS_CONFIG_FILES,
        N1KV: NEUTRON_N1KV_CONFIG_FILES,
    },
}


def register_configs():
    ''' Register config files with their respective contexts. '''
    release = get_os_codename_install_source(config('openstack-origin'))
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)

    plugin = config('plugin')
    name = networking_name()
    for conf in CONFIG_FILES[name][plugin]:
        configs.register(conf,
                         CONFIG_FILES[name][plugin][conf]['hook_contexts'])

    return configs


def stop_services():
    name = networking_name()
    svcs = set()
    for ctxt in CONFIG_FILES[name][config('plugin')].itervalues():
        for svc in ctxt['services']:
            svcs.add(svc)
    for svc in svcs:
        service_stop(svc)


def restart_map():
    '''
    Determine the correct resource map to be passed to
    charmhelpers.core.restart_on_change() based on the services configured.

    :returns: dict: A dictionary mapping config file to lists of services
                    that should be restarted when file changes.
    '''
    _map = {}
    name = networking_name()
    for f, ctxt in CONFIG_FILES[name][config('plugin')].iteritems():
        svcs = []
        for svc in ctxt['services']:
            svcs.append(svc)
        if svcs:
            _map[f] = svcs
    return _map


INT_BRIDGE = "br-int"
EXT_BRIDGE = "br-ex"

DHCP_AGENT = "DHCP Agent"
L3_AGENT = "L3 Agent"


# TODO: make work with neutron
def reassign_agent_resources():
    ''' Use agent scheduler API to detect down agents and re-schedule '''
    env = NetworkServiceContext()()
    if not env:
        log('Unable to re-assign resources at this time')
        return
    try:
        from quantumclient.v2_0 import client
    except ImportError:
        ''' Try to import neutronclient instead for havana+ '''
        from neutronclient.v2_0 import client

    # TODO: Fixup for https keystone
    auth_url = 'http://%(keystone_host)s:%(auth_port)s/v2.0' % env
    quantum = client.Client(username=env['service_username'],
                            password=env['service_password'],
                            tenant_name=env['service_tenant'],
                            auth_url=auth_url,
                            region_name=env['region'])

    partner_gateways = [unit_private_ip().split('.')[0]]
    for partner_gateway in relations_of_type(reltype='cluster'):
        gateway_hostname = get_hostname(partner_gateway['private-address'])
        partner_gateways.append(gateway_hostname.partition('.')[0])

    agents = quantum.list_agents(agent_type=DHCP_AGENT)
    dhcp_agents = []
    l3_agents = []
    networks = {}
    for agent in agents['agents']:
        if not agent['alive']:
            log('DHCP Agent %s down' % agent['id'])
            for network in \
                    quantum.list_networks_on_dhcp_agent(
                        agent['id'])['networks']:
                networks[network['id']] = agent['id']
        else:
            if agent['host'].partition('.')[0] in partner_gateways:
                dhcp_agents.append(agent['id'])

    agents = quantum.list_agents(agent_type=L3_AGENT)
    routers = {}
    for agent in agents['agents']:
        if not agent['alive']:
            log('L3 Agent %s down' % agent['id'])
            for router in \
                    quantum.list_routers_on_l3_agent(
                        agent['id'])['routers']:
                routers[router['id']] = agent['id']
        else:
            if agent['host'].split('.')[0] in partner_gateways:
                l3_agents.append(agent['id'])

    if len(dhcp_agents) == 0 or len(l3_agents) == 0:
        log('Unable to relocate resources, there are %s dhcp_agents and %s \
             l3_agents in this cluster' % (len(dhcp_agents), len(l3_agents)))
        return

    index = 0
    for router_id in routers:
        agent = index % len(l3_agents)
        log('Moving router %s from %s to %s' %
            (router_id, routers[router_id], l3_agents[agent]))
        quantum.remove_router_from_l3_agent(l3_agent=routers[router_id],
                                            router_id=router_id)
        quantum.add_router_to_l3_agent(l3_agent=l3_agents[agent],
                                       body={'router_id': router_id})
        index += 1

    index = 0
    for network_id in networks:
        agent = index % len(dhcp_agents)
        log('Moving network %s from %s to %s' %
            (network_id, networks[network_id], dhcp_agents[agent]))
        quantum.remove_network_from_dhcp_agent(dhcp_agent=networks[network_id],
                                               network_id=network_id)
        quantum.add_network_to_dhcp_agent(dhcp_agent=dhcp_agents[agent],
                                          body={'network_id': network_id})
        index += 1


def do_openstack_upgrade(configs):
    """
    Perform an upgrade.  Takes care of upgrading packages, rewriting
    configs, database migrations and potentially any other post-upgrade
    actions.

    :param configs: The charms main OSConfigRenderer object.
    """
    new_src = config('openstack-origin')
    new_os_rel = get_os_codename_install_source(new_src)

    log('Performing OpenStack upgrade to %s.' % (new_os_rel))

    configure_installation_source(new_src)
    dpkg_opts = [
        '--option', 'Dpkg::Options::=--force-confnew',
        '--option', 'Dpkg::Options::=--force-confdef',
    ]
    apt_update(fatal=True)
    apt_install(packages=get_early_packages(),
                options=dpkg_opts,
                fatal=True)
    apt_install(packages=get_packages(),
                options=dpkg_opts,
                fatal=True)

    # set CONFIGS to load templates from new release
    configs.set_release(openstack_release=new_os_rel)


def configure_ovs():
    if config('plugin') == OVS:
        if not service_running('openvswitch-switch'):
            full_restart()
        add_bridge(INT_BRIDGE)
        add_bridge(EXT_BRIDGE)
        ext_port = config('ext-port')
        if ext_port:
            add_bridge_port(EXT_BRIDGE, ext_port)


    
