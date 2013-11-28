import os
import subprocess
import ConfigParser

from base64 import b64encode
from collections import OrderedDict
from copy import deepcopy

from charmhelpers.contrib.openstack import context, templating
from charmhelpers.contrib.openstack.neutron import (
    network_manager, neutron_plugin_attribute)

from charmhelpers.contrib.hahelpers.cluster import eligible_leader

from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    get_host_ip,
    get_hostname,
    get_os_codename_install_source,
    is_ip,
    os_release,
    save_script_rc as _save_script_rc)

from charmhelpers.fetch import (
    apt_install,
    apt_update,
)

from charmhelpers.core.hookenv import (
    config,
    log,
    relation_get,
    relation_ids,
    remote_unit,
    INFO,
    ERROR,
)


import nova_cc_context

TEMPLATES = 'templates/'

CLUSTER_RES = 'res_nova_vip'

# removed from original: python-mysqldb python-keystone charm-helper-sh
BASE_PACKAGES = [
    'apache2',
    'haproxy',
    'python-keystoneclient',
    'uuid',
]

BASE_SERVICES = [
    'nova-api-ec2',
    'nova-api-os-compute',
    'nova-objectstore',
    'nova-cert',
    'nova-scheduler',
]

API_PORTS = {
    'nova-api-ec2': 8773,
    'nova-api-os-compute': 8774,
    'nova-api-os-volume': 8776,
    'nova-objectstore': 3333,
    'neutron-server': 9696,
    'quantum-server': 9696,
}

NOVA_CONF = '/etc/nova/nova.conf'
NOVA_API_PASTE = '/etc/nova/api-paste.ini'
QUANTUM_CONF = '/etc/quantum/quantum.conf'
QUANTUM_API_PASTE = '/etc/quantum/api-paste.ini'
NEUTRON_CONF = '/etc/neutron/neutron.conf'
HAPROXY_CONF = '/etc/haproxy/haproxy.cfg'
APACHE_CONF = '/etc/apache2/sites-available/openstack_https_frontend'
APACHE_24_CONF = '/etc/apache2/sites-available/openstack_https_frontend.conf'
NEUTRON_DEFAULT = '/etc/default/neutron-server'
QUANTUM_DEFAULT = '/etc/default/quantum-server'

BASE_RESOURCE_MAP = OrderedDict([
    (NOVA_CONF, {
        'services': BASE_SERVICES,
        'contexts': [context.AMQPContext(),
                     context.SharedDBContext(relation_prefix='nova'),
                     context.ImageServiceContext(),
                     context.OSConfigFlagContext(),
                     context.SubordinateConfigContext(
                         interface='nova-vmware',
                         service='nova',
                         config_file=NOVA_CONF,
                     ),
                     nova_cc_context.HAProxyContext(),
                     nova_cc_context.IdentityServiceContext(),
                     nova_cc_context.VolumeServiceContext(),
                     nova_cc_context.NeutronCCContext()],
    }),
    (NOVA_API_PASTE, {
        'services': [s for s in BASE_SERVICES if 'api' in s],
        'contexts': [nova_cc_context.IdentityServiceContext()],
    }),
    (QUANTUM_CONF, {
        'services': ['quantum-server'],
        'contexts': [context.AMQPContext(),
                     nova_cc_context.HAProxyContext(),
                     nova_cc_context.IdentityServiceContext(),
                     nova_cc_context.NeutronCCContext()],
    }),
    (QUANTUM_DEFAULT, {
        'services': ['quantum-server'],
        'contexts': [nova_cc_context.NeutronCCContext()],
    }),
    (QUANTUM_API_PASTE, {
        'services': ['quantum-server'],
        'contexts': [nova_cc_context.IdentityServiceContext()],
    }),
    (NEUTRON_CONF, {
        'services': ['neutron-server'],
        'contexts': [context.AMQPContext(),
                     nova_cc_context.IdentityServiceContext(),
                     nova_cc_context.NeutronCCContext(),
                     nova_cc_context.HAProxyContext()],
    }),
    (NEUTRON_DEFAULT, {
        'services': ['neutron-server'],
        'contexts': [nova_cc_context.NeutronCCContext()],
    }),
    (HAPROXY_CONF, {
        'contexts': [context.HAProxyContext(),
                     nova_cc_context.HAProxyContext()],
        'services': ['haproxy'],
    }),
    (APACHE_CONF, {
        'contexts': [nova_cc_context.ApacheSSLContext()],
        'services': ['apache2'],
    }),
    (APACHE_24_CONF, {
        'contexts': [nova_cc_context.ApacheSSLContext()],
        'services': ['apache2'],
    }),
])

CA_CERT_PATH = '/usr/local/share/ca-certificates/keystone_juju_ca_cert.crt'

NOVA_SSH_DIR = '/etc/nova/compute_ssh/'


def resource_map():
    '''
    Dynamically generate a map of resources that will be managed for a single
    hook execution.
    '''
    resource_map = deepcopy(BASE_RESOURCE_MAP)

    if relation_ids('nova-volume-service'):
        # if we have a relation to a nova-volume service, we're
        # also managing the nova-volume API endpoint (legacy)
        resource_map['/etc/nova/nova.conf']['services'].append(
            'nova-api-os-volume')

    net_manager = network_manager()

    # pop out irrelevant resources from the OrderedDict (easier than adding
    # them late)
    if net_manager != 'quantum':
        [resource_map.pop(k) for k in list(resource_map.iterkeys())
         if 'quantum' in k]
    if net_manager != 'neutron':
        [resource_map.pop(k) for k in list(resource_map.iterkeys())
         if 'neutron' in k]

    if os.path.exists('/etc/apache2/conf-available'):
        resource_map.pop(APACHE_CONF)
    else:
        resource_map.pop(APACHE_24_CONF)

    # add neutron plugin requirements. nova-c-c only needs the neutron-server
    # associated with configs, not the plugin agent.
    if net_manager in ['quantum', 'neutron']:
        plugin = neutron_plugin()
        if plugin:
            conf = neutron_plugin_attribute(plugin, 'config', net_manager)
            ctxts = (neutron_plugin_attribute(plugin, 'contexts', net_manager)
                     or [])
            services = neutron_plugin_attribute(plugin, 'server_services',
                                                net_manager)
            resource_map[conf] = {}
            resource_map[conf]['services'] = services
            resource_map[conf]['contexts'] = ctxts
            resource_map[conf]['contexts'].append(
                nova_cc_context.NeutronCCContext())

    # nova-conductor for releases >= G.
    if os_release('nova-common') not in ['essex', 'folsom']:
        resource_map['/etc/nova/nova.conf']['services'] += ['nova-conductor']

    # also manage any configs that are being updated by subordinates.
    vmware_ctxt = context.SubordinateConfigContext(interface='nova-vmware',
                                                   service='nova',
                                                   config_file=NOVA_CONF)
    vmware_ctxt = vmware_ctxt()
    if vmware_ctxt and 'services' in vmware_ctxt:
        for s in vmware_ctxt['services']:
            if s not in resource_map[NOVA_CONF]['services']:
                resource_map[NOVA_CONF]['services'].append(s)
    return resource_map


def register_configs():
    release = os_release('nova-common')
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)
    for cfg, rscs in resource_map().iteritems():
        configs.register(cfg, rscs['contexts'])
    return configs


def restart_map():
    return OrderedDict([(cfg, v['services'])
                        for cfg, v in resource_map().iteritems()
                        if v['services']])


def determine_ports():
    '''Assemble a list of API ports for services we are managing'''
    ports = []
    for cfg, services in restart_map().iteritems():
        for service in services:
            try:
                ports.append(API_PORTS[service])
            except KeyError:
                pass
    return list(set(ports))


def api_port(service):
    return API_PORTS[service]


def determine_packages():
    # currently all packages match service names
    packages = [] + BASE_PACKAGES
    for k, v in resource_map().iteritems():
        packages.extend(v['services'])
    if network_manager() in ['neutron', 'quantum']:
        pkgs = neutron_plugin_attribute(neutron_plugin(), 'server_packages',
                                        network_manager())
        packages.extend(pkgs)
    return list(set(packages))


def save_script_rc():
    env_vars = {
        'OPENSTACK_PORT_MCASTPORT': config('ha-mcastport'),
        'OPENSTACK_SERVICE_API_EC2': 'nova-api-ec2',
        'OPENSTACK_SERVICE_API_OS_COMPUTE': 'nova-api-os-compute',
        'OPENSTACK_SERVICE_CERT': 'nova-cert',
        'OPENSTACK_SERVICE_CONDUCTOR': 'nova-conductor',
        'OPENSTACK_SERVICE_OBJECTSTORE': 'nova-objectstore',
        'OPENSTACK_SERVICE_SCHEDULER': 'nova-scheduler',
    }
    if relation_ids('nova-volume-service'):
        env_vars['OPENSTACK_SERVICE_API_OS_VOL'] = 'nova-api-os-volume'
    if network_manager() == 'quantum':
        env_vars['OPENSTACK_SERVICE_API_QUANTUM'] = 'quantum-server'
    if network_manager() == 'neutron':
        env_vars['OPENSTACK_SERVICE_API_NEUTRON'] = 'neutron-server'
    _save_script_rc(**env_vars)


def do_openstack_upgrade(configs):
    new_src = config('openstack-origin')
    new_os_rel = get_os_codename_install_source(new_src)
    log('Performing OpenStack upgrade to %s.' % (new_os_rel))

    configure_installation_source(new_src)
    apt_update()

    dpkg_opts = [
        '--option', 'Dpkg::Options::=--force-confnew',
        '--option', 'Dpkg::Options::=--force-confdef',
    ]

    apt_install(packages=determine_packages(), options=dpkg_opts, fatal=True)

    # set CONFIGS to load templates from new release and regenerate config
    configs.set_release(openstack_release=new_os_rel)
    configs.write_all()

    if eligible_leader(CLUSTER_RES):
        migrate_database()


def volume_service():
    '''Specifies correct volume API for specific OS release'''
    os_vers = os_release('nova-common')
    if os_vers == 'essex':
        return 'nova-volume'
    elif os_vers == 'folsom':  # support both drivers in folsom.
        if not relation_ids('cinder-volume-service'):
            return 'nova-volume'
    return 'cinder'


def migrate_database():
    '''Runs nova-manage to initialize a new database or migrate existing'''
    log('Migrating the nova database.', level=INFO)
    cmd = ['nova-manage', 'db', 'sync']
    subprocess.check_output(cmd)


def auth_token_config(setting):
    '''
    Returns currently configured value for setting in api-paste.ini's
    authtoken section, or None.
    '''
    config = ConfigParser.RawConfigParser()
    config.read('/etc/nova/api-paste.ini')
    try:
        value = config.get('filter:authtoken', setting)
    except:
        return None
    if value.startswith('%'):
        return None
    return value


def keystone_ca_cert_b64():
    '''Returns the local Keystone-provided CA cert if it exists, or None.'''
    if not os.path.isfile(CA_CERT_PATH):
        return None
    with open(CA_CERT_PATH) as _in:
        return b64encode(_in.read())


def ssh_directory_for_unit():
    remote_service = remote_unit().split('/')[0]
    _dir = os.path.join(NOVA_SSH_DIR, remote_service)
    for d in [NOVA_SSH_DIR, _dir]:
        if not os.path.isdir(d):
            os.mkdir(d)
    for f in ['authorized_keys', 'known_hosts']:
        f = os.path.join(_dir, f)
        if not os.path.isfile(f):
            open(f, 'w').close()
    return _dir


def known_hosts():
    return os.path.join(ssh_directory_for_unit(), 'known_hosts')


def authorized_keys():
    return os.path.join(ssh_directory_for_unit(), 'authorized_keys')


def ssh_known_host_key(host):
    cmd = ['ssh-keygen', '-f', known_hosts(), '-H', '-F', host]
    return subprocess.check_output(cmd).strip()


def remove_known_host(host):
    log('Removing SSH known host entry for compute host at %s' % host)
    cmd = ['ssh-kegen', '-f', known_hosts(), '-R', host]
    subprocess.check_call(cmd)


def add_known_host(host):
    '''Add variations of host to a known hosts file.'''
    cmd = ['ssh-keyscan', '-H', '-t', 'rsa', host]
    try:
        remote_key = subprocess.check_output(cmd).strip()
    except Exception as e:
        log('Could not obtain SSH host key from %s' % host, level=ERROR)
        raise e

    current_key = ssh_known_host_key(host)
    if current_key:
        if remote_key == current_key:
            log('Known host key for compute host %s up to date.' % host)
            return
        else:
            remove_known_host(host)

    log('Adding SSH host key to known hosts for compute node at %s.' % host)
    with open(known_hosts(), 'a') as out:
        out.write(remote_key + '\n')


def ssh_authorized_key_exists(public_key):
    with open(authorized_keys()) as keys:
        return (' %s ' % public_key) in keys.read()


def add_authorized_key(public_key):
    with open(authorized_keys(), 'a') as keys:
        keys.write(public_key + '\n')


def ssh_compute_add(public_key):
    # If remote compute node hands us a hostname, ensure we have a
    # known hosts entry for its IP, hostname and FQDN.
    private_address = relation_get('private-address')
    hosts = [private_address]

    if not is_ip(private_address):
        hosts.append(get_host_ip(private_address))
        hosts.append(private_address.split('.')[0])
    else:
        hn = get_hostname(private_address)
        hosts.append(hn)
        hosts.append(hn.split('.')[0])

    for host in list(set(hosts)):
        if not ssh_known_host_key(host):
            add_known_host(host)

    if not ssh_authorized_key_exists(public_key):
        log('Saving SSH authorized key for compute host at %s.' %
            private_address)
        add_authorized_key(public_key)


def ssh_known_hosts_b64():
    with open(known_hosts()) as hosts:
        return b64encode(hosts.read())


def ssh_authorized_keys_b64():
    with open(authorized_keys()) as keys:
        return b64encode(keys.read())


def ssh_compute_remove(public_key):
    if not (os.path.isfile(authorized_keys()) or
            os.path.isfile(known_hosts())):
        return

    with open(authorized_keys()) as _keys:
        keys = [k.strip() for k in _keys.readlines()]

    if public_key not in keys:
        return

    [keys.remove(key) for key in keys if key == public_key]

    with open(authorized_keys(), 'w') as _keys:
        _keys.write('\n'.join(keys))


def determine_endpoints(url):
    '''Generates a dictionary containing all relevant endpoints to be
    passed to keystone as relation settings.'''
    region = config('region')

    # TODO: Configurable nova API version.
    nova_url = ('%s:%s/v1.1/$(tenant_id)s' %
                (url, api_port('nova-api-os-compute')))
    ec2_url = '%s:%s/services/Cloud' % (url, api_port('nova-api-ec2'))
    nova_volume_url = ('%s:%s/v1/$(tenant_id)s' %
                       (url, api_port('nova-api-os-compute')))
    neutron_url = '%s:%s' % (url, api_port('neutron-server'))
    s3_url = '%s:%s' % (url, api_port('nova-objectstore'))

    # the base endpoints
    endpoints = {
        'nova_service': 'nova',
        'nova_region': region,
        'nova_public_url': nova_url,
        'nova_admin_url': nova_url,
        'nova_internal_url': nova_url,
        'ec2_service': 'ec2',
        'ec2_region': region,
        'ec2_public_url': ec2_url,
        'ec2_admin_url': ec2_url,
        'ec2_internal_url': ec2_url,
        's3_service': 's3',
        's3_region': region,
        's3_public_url': s3_url,
        's3_admin_url': s3_url,
        's3_internal_url': s3_url,
    }

    if relation_ids('nova-volume-service'):
        endpoints.update({
            'nova-volume_service': 'nova-volume',
            'nova-volume_region': region,
            'nova-volume_public_url': nova_volume_url,
            'nova-volume_admin_url': nova_volume_url,
            'nova-volume_internal_url': nova_volume_url,
        })

    # XXX: Keep these relations named quantum_*??
    if network_manager() in ['quantum', 'neutron']:
        endpoints.update({
            'quantum_service': 'quantum',
            'quantum_region': region,
            'quantum_public_url': neutron_url,
            'quantum_admin_url': neutron_url,
            'quantum_internal_url': neutron_url,
        })

    return endpoints


def neutron_plugin():
    # quantum-plugin config setting can be safely overriden
    # as we only supported OVS in G/neutron
    return config('neutron-plugin') or config('quantum-plugin')
