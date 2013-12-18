# vim: set ts=4:et
import horizon_contexts
import charmhelpers.contrib.openstack.templating as templating
import subprocess
import os
from collections import OrderedDict

from charmhelpers.contrib.openstack.utils import (
    get_os_codename_package,
    get_os_codename_install_source,
    configure_installation_source
)
from charmhelpers.core.hookenv import (
    config,
    log
)
from charmhelpers.fetch import (
    apt_install,
    apt_update
)

PACKAGES = [
    "openstack-dashboard", "python-keystoneclient", "python-memcache",
    "memcached", "haproxy", "python-novaclient",
    "nodejs", "node-less", "openstack-dashboard-ubuntu-theme"
]

LOCAL_SETTINGS = "/etc/openstack-dashboard/local_settings.py"
HAPROXY_CONF = "/etc/haproxy/haproxy.cfg"
APACHE_CONF = "/etc/apache2/conf.d/openstack-dashboard.conf"
APACHE_24_CONF = "/etc/apache2/conf-available/openstack-dashboard.conf"
PORTS_CONF = "/etc/apache2/ports.conf"
APACHE_SSL = "/etc/apache2/sites-available/default-ssl"
APACHE_DEFAULT = "/etc/apache2/sites-available/default"

TEMPLATES = 'templates'

CONFIG_FILES = OrderedDict([
    (LOCAL_SETTINGS, {
        'hook_contexts': [horizon_contexts.HorizonContext(),
                          horizon_contexts.IdentityServiceContext()],
        'services': ['apache2']
    }),
    (APACHE_CONF, {
        'hook_contexts': [horizon_contexts.HorizonContext()],
        'services': ['apache2'],
    }),
    (APACHE_24_CONF, {
        'hook_contexts': [horizon_contexts.HorizonContext()],
        'services': ['apache2'],
    }),
    (APACHE_SSL, {
        'hook_contexts': [horizon_contexts.ApacheSSLContext(),
                          horizon_contexts.ApacheContext()],
        'services': ['apache2'],
    }),
    (APACHE_DEFAULT, {
        'hook_contexts': [horizon_contexts.ApacheContext()],
        'services': ['apache2'],
    }),
    (PORTS_CONF, {
        'hook_contexts': [horizon_contexts.ApacheContext()],
        'services': ['apache2'],
    }),
    (HAPROXY_CONF, {
        'hook_contexts': [horizon_contexts.HorizonHAProxyContext()],
        'services': ['haproxy'],
    }),
])


def register_configs():
    ''' Register config files with their respective contexts. '''
    release = get_os_codename_package('openstack-dashboard', fatal=False) or \
        'essex'
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)

    confs = [LOCAL_SETTINGS,
             HAPROXY_CONF,
             APACHE_SSL,
             APACHE_DEFAULT,
             PORTS_CONF]

    for conf in confs:
        configs.register(conf, CONFIG_FILES[conf]['hook_contexts'])

    if os.path.exists(os.path.dirname(APACHE_24_CONF)):
        configs.register(APACHE_24_CONF,
                         CONFIG_FILES[APACHE_24_CONF]['hook_contexts'])
    else:
        configs.register(APACHE_CONF,
                         CONFIG_FILES[APACHE_CONF]['hook_contexts'])

    return configs


def restart_map():
    '''
    Determine the correct resource map to be passed to
    charmhelpers.core.restart_on_change() based on the services configured.

    :returns: dict: A dictionary mapping config file to lists of services
                    that should be restarted when file changes.
    '''
    _map = []
    for f, ctxt in CONFIG_FILES.iteritems():
        svcs = []
        for svc in ctxt['services']:
            svcs.append(svc)
        if svcs:
            _map.append((f, svcs))
    return OrderedDict(_map)


def enable_ssl():
    ''' Enable SSL support in local apache2 instance '''
    subprocess.call(['a2ensite', 'default-ssl'])
    subprocess.call(['a2enmod', 'ssl'])


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
    apt_install(packages=PACKAGES, options=dpkg_opts, fatal=True)

    # set CONFIGS to load templates from new release
    configs.set_release(openstack_release=new_os_rel)
