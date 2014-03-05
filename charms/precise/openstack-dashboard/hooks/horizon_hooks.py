#!/usr/bin/python
# vim: set ts=4:et

import sys
from charmhelpers.core.hookenv import (
    Hooks, UnregisteredHookError,
    log,
    open_port,
    config,
    relation_set,
    relation_get,
    relation_ids,
    unit_get
)
from charmhelpers.fetch import (
    apt_update, apt_install,
    filter_installed_packages,
)
from charmhelpers.core.host import (
    restart_on_change
)
from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    openstack_upgrade_available,
    save_script_rc
)
from horizon_utils import (
    PACKAGES, register_configs,
    restart_map,
    LOCAL_SETTINGS, HAPROXY_CONF,
    enable_ssl,
    do_openstack_upgrade
)
from charmhelpers.contrib.hahelpers.apache import install_ca_cert
from charmhelpers.contrib.hahelpers.cluster import get_hacluster_config
from charmhelpers.payload.execd import execd_preinstall

hooks = Hooks()
CONFIGS = register_configs()


@hooks.hook('install')
def install():
    configure_installation_source(config('openstack-origin'))
    if config('profile-support') == 'cisco':
        get_cisco_repository()
    apt_update(fatal=True)
    apt_install(filter_installed_packages(PACKAGES), fatal=True)


@hooks.hook('upgrade-charm')
@restart_on_change(restart_map())
def upgrade_charm():
    execd_preinstall()
    apt_install(filter_installed_packages(PACKAGES), fatal=True)
    CONFIGS.write_all()


@hooks.hook('config-changed')
@restart_on_change(restart_map())
def config_changed():
    # Ensure default role changes are propagated to keystone
    for relid in relation_ids('identity-service'):
        keystone_joined(relid)
    enable_ssl()
    if openstack_upgrade_available('openstack-dashboard'):
        do_openstack_upgrade(configs=CONFIGS)

    env_vars = {
        'OPENSTACK_URL_HORIZON':
        "http://localhost:70{}|Login+-+OpenStack".format(
            config('webroot')
        ),
        'OPENSTACK_SERVICE_HORIZON': "apache2",
        'OPENSTACK_PORT_HORIZON_SSL': 433,
        'OPENSTACK_PORT_HORIZON': 70
    }
    save_script_rc(**env_vars)
    CONFIGS.write_all()
    open_port(80)
    open_port(443)


@hooks.hook('identity-service-relation-joined')
def keystone_joined(rel_id=None):
    relation_set(relation_id=rel_id,
                 service="None",
                 region="None",
                 public_url="None",
                 admin_url="None",
                 internal_url="None",
                 requested_roles=config('default-role'))


@hooks.hook('identity-service-relation-changed')
@restart_on_change(restart_map())
def keystone_changed():
    CONFIGS.write(LOCAL_SETTINGS)
    if relation_get('ca_cert'):
        install_ca_cert(relation_get('ca_cert'))


@hooks.hook('cluster-relation-departed',
            'cluster-relation-changed')
@restart_on_change(restart_map())
def cluster_relation():
    CONFIGS.write(HAPROXY_CONF)


@hooks.hook('ha-relation-joined')
def ha_relation_joined():
    config = get_hacluster_config()
    resources = {
        'res_horizon_vip': 'ocf:heartbeat:IPaddr2',
        'res_horizon_haproxy': 'lsb:haproxy'
    }
    vip_params = 'params ip="{}" cidr_netmask="{}" nic="{}"'.format(
        config['vip'], config['vip_cidr'], config['vip_iface'])
    resource_params = {
        'res_horizon_vip': vip_params,
        'res_horizon_haproxy': 'op monitor interval="5s"'
    }
    init_services = {
        'res_horizon_haproxy': 'haproxy'
    }
    clones = {
        'cl_horizon_haproxy': 'res_horizon_haproxy'
    }
    relation_set(init_services=init_services,
                 corosync_bindiface=config['ha-bindiface'],
                 corosync_mcastport=config['ha-mcastport'],
                 resources=resources,
                 resource_params=resource_params,
                 clones=clones)


@hooks.hook('website-relation-joined')
def website_relation_joined():
    relation_set(port=70,
                 hostname=unit_get('private-address'))


def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))


if __name__ == '__main__':
    main()
