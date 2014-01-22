#!/usr/bin/python

from charmhelpers.core.hookenv import (
    log, ERROR, WARNING,
    config,
    relation_get,
    relation_set,
    relation_ids,
    unit_get,
    Hooks, UnregisteredHookError
)
from charmhelpers.fetch import (
    apt_update,
    apt_install,
    filter_installed_packages,
)
from charmhelpers.core.host import (
    restart_on_change,
    lsb_release,
    service_start,
    service_stop,
    service_running,
)
from charmhelpers.contrib.hahelpers.cluster import(
    eligible_leader
)
from charmhelpers.contrib.hahelpers.apache import(
    install_ca_cert
)
from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    openstack_upgrade_available,
)
from charmhelpers.payload.execd import execd_preinstall

import sys
from quantum_utils import (
    register_configs,
    restart_map,
    do_openstack_upgrade,
    get_packages,
    get_early_packages,
    get_common_package,
    valid_plugin,
    configure_ovs,
    reassign_agent_resources,
    n1kv_add_repo,
    stop_services
)
from quantum_contexts import (
    DB_USER, QUANTUM_DB,
    NOVA_DB_USER, NOVA_DB,
)

hooks = Hooks()
CONFIGS = register_configs()


@hooks.hook('install')
def install():
    execd_preinstall()
    if config('plugin') == 'n1kv':
        n1kv_add_repo()
    src = config('openstack-origin')
    if (lsb_release()['DISTRIB_CODENAME'] == 'precise' and
            src == 'distro'):
        src = 'cloud:precise-folsom'
    configure_installation_source(src)
    apt_update(fatal=True)
    if valid_plugin():
        apt_install(filter_installed_packages(get_early_packages()),
                    fatal=True)
        apt_install(filter_installed_packages(get_packages()),
                    fatal=True)
    else:
        log('Please provide a valid plugin config', level=ERROR)
        sys.exit(1)


@hooks.hook('config-changed')
@restart_on_change(restart_map())
def config_changed():
    if openstack_upgrade_available(get_common_package()):
        do_openstack_upgrade(CONFIGS)
    if valid_plugin():
        CONFIGS.write_all()
        configure_ovs()
    else:
        log('Please provide a valid plugin config', level=ERROR)
        sys.exit(1)
    if config('plugin') == 'n1kv':
        if config('l3-agent') == 'enable':
            if not service_running('neutron-l3-agent'):
                service_start('neutron-l3-agent')
        else:
            if service_running('neutron-l3-agent'):
                service_stop('neutron-l3-agent')

@hooks.hook('upgrade-charm')
def upgrade_charm():
    # NOTE(jamespage): Deal with changes to rabbitmq configuration for
    # common virtual host across services
    for r_id in relation_ids('amqp'):
        amqp_joined(relation_id=r_id)
    install()
    config_changed()


@hooks.hook('shared-db-relation-joined')
def db_joined():
    relation_set(quantum_username=DB_USER,
                 quantum_database=QUANTUM_DB,
                 quantum_hostname=unit_get('private-address'),
                 nova_username=NOVA_DB_USER,
                 nova_database=NOVA_DB,
                 nova_hostname=unit_get('private-address'))


@hooks.hook('amqp-relation-joined')
def amqp_joined(relation_id=None):
    relation_set(relation_id=relation_id,
                 username=config('rabbit-user'),
                 vhost=config('rabbit-vhost'))


@hooks.hook('shared-db-relation-changed',
            'amqp-relation-changed',
            'cluster-relation-changed',
            'cluster-relation-joined')
@restart_on_change(restart_map())
def db_amqp_changed():
    CONFIGS.write_all()


@hooks.hook('quantum-network-service-relation-changed')
@restart_on_change(restart_map())
def nm_changed():
    CONFIGS.write_all()
    if relation_get('ca_cert'):
        install_ca_cert(relation_get('ca_cert'))

@hooks.hook("cluster-relation-departed")
@restart_on_change(restart_map())
def cluster_departed():
    if config('plugin') == 'nvp':
        log('Unable to re-assign agent resources for failed nodes with nvp',
            level=WARNING)
        return
    if config('plugin') == 'n1kv':
        log('Unable to re-assign agent resources for failed nodes with n1kv',
            level=WARNING)
        return
    if eligible_leader(None):
        reassign_agent_resources()
        CONFIGS.write_all()


@hooks.hook('cluster-relation-broken')
@hooks.hook('stop')
def stop():
    stop_services()

if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))
