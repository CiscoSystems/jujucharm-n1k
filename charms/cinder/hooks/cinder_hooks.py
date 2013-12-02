#!/usr/bin/python

import os
import sys

from subprocess import check_call

from cinder_utils import (
    clean_storage,
    determine_packages,
    do_openstack_upgrade,
    ensure_block_device,
    ensure_ceph_pool,
    juju_log,
    migrate_database,
    prepare_lvm_storage,
    register_configs,
    restart_map,
    service_enabled,
    set_ceph_env_variables,
    CLUSTER_RES,
    CINDER_CONF,
    CINDER_API_CONF,
    CEPH_CONF,
)

from charmhelpers.core.hookenv import (
    Hooks,
    UnregisteredHookError,
    config,
    relation_get,
    relation_ids,
    relation_set,
    service_name,
    unit_get,
)

from charmhelpers.fetch import apt_install, apt_update
from charmhelpers.core.host import lsb_release, restart_on_change

from charmhelpers.contrib.openstack.utils import (
    configure_installation_source, openstack_upgrade_available)

from charmhelpers.contrib.storage.linux.ceph import ensure_ceph_keyring

from charmhelpers.contrib.hahelpers.cluster import (
    canonical_url,
    eligible_leader,
    is_leader,
    get_hacluster_config,
)

from charmhelpers.payload.execd import execd_preinstall

hooks = Hooks()

CONFIGS = register_configs()


@hooks.hook('install')
def install():
    execd_preinstall()
    conf = config()
    src = conf['openstack-origin']
    if (lsb_release()['DISTRIB_CODENAME'] == 'precise' and
       src == 'distro'):
        src = 'cloud:precise-folsom'
    configure_installation_source(src)
    apt_update()
    apt_install(determine_packages(), fatal=True)

    if (service_enabled('volume') and
       conf['block-device'] not in [None, 'None', 'none']):
        bdev = ensure_block_device(conf['block-device'])
        juju_log('Located valid block device: %s' % bdev)
        if conf['overwrite'] in ['true', 'True', True]:
            juju_log('Ensuring block device is clean: %s' % bdev)
            clean_storage(bdev)
        prepare_lvm_storage(bdev, conf['volume-group'])


@hooks.hook('config-changed')
@restart_on_change(restart_map())
def config_changed():
    if openstack_upgrade_available('cinder-common'):
        do_openstack_upgrade(configs=CONFIGS)
    CONFIGS.write_all()
    configure_https()


@hooks.hook('shared-db-relation-joined')
def db_joined():
    conf = config()
    relation_set(database=conf['database'], username=conf['database-user'],
                 hostname=unit_get('private-address'))


@hooks.hook('shared-db-relation-changed')
@restart_on_change(restart_map())
def db_changed():
    if 'shared-db' not in CONFIGS.complete_contexts():
        juju_log('shared-db relation incomplete. Peer not ready?')
        return
    CONFIGS.write(CINDER_CONF)
    if eligible_leader(CLUSTER_RES):
        juju_log('Cluster leader, performing db sync')
        migrate_database()


@hooks.hook('amqp-relation-joined')
def amqp_joined(relation_id=None):
    conf = config()
    relation_set(relation_id=relation_id,
                 username=conf['rabbit-user'], vhost=conf['rabbit-vhost'])


@hooks.hook('amqp-relation-changed')
@restart_on_change(restart_map())
def amqp_changed():
    if 'amqp' not in CONFIGS.complete_contexts():
        juju_log('amqp relation incomplete. Peer not ready?')
        return
    CONFIGS.write(CINDER_CONF)


@hooks.hook('identity-service-relation-joined')
def identity_joined(rid=None):
    if not eligible_leader(CLUSTER_RES):
        return

    conf = config()

    port = conf['api-listening-port']
    url = canonical_url(CONFIGS) + ':%s/v1/$(tenant_id)s' % port

    settings = {
        'region': conf['region'],
        'service': 'cinder',
        'public_url': url,
        'internal_url': url,
        'admin_url': url,
    }
    relation_set(relation_id=rid, **settings)


@hooks.hook('identity-service-relation-changed')
@restart_on_change(restart_map())
def identity_changed():
    if 'identity-service' not in CONFIGS.complete_contexts():
        juju_log('identity-service relation incomplete. Peer not ready?')
        return
    CONFIGS.write(CINDER_API_CONF)
    configure_https()


@hooks.hook('ceph-relation-joined')
def ceph_joined():
    if not os.path.isdir('/etc/ceph'):
        os.mkdir('/etc/ceph')
    apt_install('ceph-common', fatal=True)


@hooks.hook('ceph-relation-changed')
@restart_on_change(restart_map())
def ceph_changed():
    if 'ceph' not in CONFIGS.complete_contexts():
        juju_log('ceph relation incomplete. Peer not ready?')
        return
    svc = service_name()
    if not ensure_ceph_keyring(service=svc,
                               user='cinder', group='cinder'):
        juju_log('Could not create ceph keyring: peer not ready?')
        return
    CONFIGS.write(CEPH_CONF)
    CONFIGS.write(CINDER_CONF)
    set_ceph_env_variables(service=svc)

    if eligible_leader(CLUSTER_RES):
        _config = config()
        ensure_ceph_pool(service=svc,
                         replicas=_config['ceph-osd-replication-count'])


@hooks.hook('cluster-relation-changed',
            'cluster-relation-departed')
@restart_on_change(restart_map())
def cluster_changed():
    CONFIGS.write_all()


@hooks.hook('ha-relation-joined')
def ha_joined():
    config = get_hacluster_config()
    resources = {
        'res_cinder_vip': 'ocf:heartbeat:IPaddr2',
        'res_cinder_haproxy': 'lsb:haproxy'
    }

    vip_params = 'params ip="%s" cidr_netmask="%s" nic="%s"' % \
                 (config['vip'], config['vip_cidr'], config['vip_iface'])
    resource_params = {
        'res_cinder_vip': vip_params,
        'res_cinder_haproxy': 'op monitor interval="5s"'
    }
    init_services = {
        'res_cinder_haproxy': 'haproxy'
    }
    clones = {
        'cl_cinder_haproxy': 'res_cinder_haproxy'
    }
    relation_set(init_services=init_services,
                 corosync_bindiface=config['ha-bindiface'],
                 corosync_mcastport=config['ha-mcastport'],
                 resources=resources,
                 resource_params=resource_params,
                 clones=clones)


@hooks.hook('ha-relation-changed')
def ha_changed():
    clustered = relation_get('clustered')
    if not clustered or clustered in [None, 'None', '']:
        juju_log('ha_changed: hacluster subordinate not fully clustered.')
        return
    if not is_leader(CLUSTER_RES):
        juju_log('ha_changed: hacluster complete but we are not leader.')
        return
    juju_log('Cluster configured, notifying other services and updating '
             'keystone endpoint configuration')
    for rid in relation_ids('identity-service'):
        identity_joined(rid=rid)


@hooks.hook('image-service-relation-changed')
@restart_on_change(restart_map())
def image_service_changed():
    CONFIGS.write(CINDER_CONF)


@hooks.hook('amqp-relation-broken',
            'ceph-relation-broken',
            'identity-service-relation-broken',
            'image-service-relation-broken',
            'shared-db-relation-broken')
@restart_on_change(restart_map())
def relation_broken():
    CONFIGS.write_all()


def configure_https():
    '''
    Enables SSL API Apache config if appropriate and kicks identity-service
    with any required api updates.
    '''
    # need to write all to ensure changes to the entire request pipeline
    # propagate (c-api, haprxy, apache)
    CONFIGS.write_all()
    if 'https' in CONFIGS.complete_contexts():
        cmd = ['a2ensite', 'openstack_https_frontend']
        check_call(cmd)
    else:
        cmd = ['a2dissite', 'openstack_https_frontend']
        check_call(cmd)

    for rid in relation_ids('identity-service'):
        identity_joined(rid=rid)


@hooks.hook('upgrade-charm')
def upgrade_charm():
    for rel_id in relation_ids('amqp'):
        amqp_joined(relation_id=rel_id)


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        juju_log('Unknown hook {} - skipping.'.format(e))
