#!/usr/bin/python

#
# Copyright 2012 Canonical Ltd.
#
# Authors:
#  James Page <james.page@ubuntu.com>
#

import shutil
import subprocess
import sys
import glob
import os
import ceph

import utils


def install_www_scripts():
    for x in glob.glob('files/www/*'):
        shutil.copy(x, '/var/www/')


NSS_DIR='/var/lib/ceph/nss'


def install():
    utils.juju_log('INFO', 'Begin install hook.')
    utils.enable_pocket('multiverse')
    utils.configure_source()
    utils.install('radosgw',
                  'libapache2-mod-fastcgi',
                  'apache2',
                  'ntp')
    os.makedirs(NSS_DIR)
    utils.juju_log('INFO', 'End install hook.')


def emit_cephconf():
    # Ensure ceph directory actually exists
    if not os.path.exists('/etc/ceph'):
        os.makedirs('/etc/ceph')

    cephcontext = {
        'auth_supported': get_auth() or 'none',
        'mon_hosts': ' '.join(get_mon_hosts()),
        'hostname': utils.get_unit_hostname(),
        'version': ceph.get_ceph_version('radosgw')
        }
    
    # Check to ensure that correct version of ceph is 
    # in use
    if ceph.get_ceph_version('radosgw') >= "0.55":    
        # Add keystone configuration if found
        ks_conf = get_keystone_conf()
        if ks_conf:
            cephcontext.update(ks_conf)

    with open('/etc/ceph/ceph.conf', 'w') as cephconf:
        cephconf.write(utils.render_template('ceph.conf', cephcontext))


def emit_apacheconf():
    apachecontext = {
        "hostname": utils.unit_get('private-address')
        }
    with open('/etc/apache2/sites-available/rgw', 'w') as apacheconf:
        apacheconf.write(utils.render_template('rgw', apachecontext))


def apache_sites():
    utils.juju_log('INFO', 'Begin apache_sites.')
    subprocess.check_call(['a2dissite', 'default'])
    subprocess.check_call(['a2ensite', 'rgw'])
    utils.juju_log('INFO', 'End apache_sites.')


def apache_modules():
    utils.juju_log('INFO', 'Begin apache_sites.')
    subprocess.check_call(['a2enmod', 'fastcgi'])
    subprocess.check_call(['a2enmod', 'rewrite'])
    utils.juju_log('INFO', 'End apache_sites.')


def apache_reload():
    subprocess.call(['service', 'apache2', 'reload'])


def config_changed():
    utils.juju_log('INFO', 'Begin config-changed hook.')
    emit_cephconf()
    emit_apacheconf()
    install_www_scripts()
    apache_sites()
    apache_modules()
    apache_reload()
    utils.juju_log('INFO', 'End config-changed hook.')


def get_mon_hosts():
    hosts = []
    for relid in utils.relation_ids('mon'):
        for unit in utils.relation_list(relid):
            hosts.append(
                '{}:6789'.format(utils.get_host_ip(
                                    utils.relation_get('private-address',
                                                       unit, relid)))
                )

    hosts.sort()
    return hosts


def get_auth():
    return get_conf('auth')


def get_conf(name):
    for relid in utils.relation_ids('mon'):
        for unit in utils.relation_list(relid):
            conf = utils.relation_get(name,
                                      unit, relid)
            if conf:
                return conf
    return None

def get_keystone_conf():
    for relid in utils.relation_ids('identity-service'):
        for unit in utils.relation_list(relid):
            ks_auth = {
                'auth_type': 'keystone',
                'auth_protocol': 'http',
                'auth_host': utils.relation_get('auth_host', unit, relid),
                'auth_port': utils.relation_get('auth_port', unit, relid),
                'admin_token': utils.relation_get('admin_token', unit, relid),
                'user_roles': utils.config_get('operator-roles'),
                'cache_size': utils.config_get('cache-size'),
                'revocation_check_interval': utils.config_get('revocation-check-interval')
            }
            if None not in ks_auth.itervalues():
                return ks_auth
    return None


def mon_relation():
    utils.juju_log('INFO', 'Begin mon-relation hook.')
    emit_cephconf()
    key = utils.relation_get('radosgw_key')
    if key:
        ceph.import_radosgw_key(key)
        restart()  # TODO figure out a better way todo this
    utils.juju_log('INFO', 'End mon-relation hook.')


def gateway_relation():
    utils.juju_log('INFO', 'Begin gateway-relation hook.')
    utils.relation_set(hostname=utils.unit_get('private-address'),
                       port=80)
    utils.juju_log('INFO', 'Begin gateway-relation hook.')


def upgrade_charm():
    utils.juju_log('INFO', 'Begin upgrade-charm hook.')
    utils.juju_log('INFO', 'End upgrade-charm hook.')


def start():
    subprocess.call(['service', 'radosgw', 'start'])
    utils.expose(port=80)


def stop():
    subprocess.call(['service', 'radosgw', 'stop'])
    utils.expose(port=80)


def restart():
    subprocess.call(['service', 'radosgw', 'restart'])
    utils.expose(port=80)


def identity_joined(relid=None):
    if ceph.get_ceph_version('radosgw') < "0.55":
        utils.juju_log('ERROR',
                       'Integration with keystone requires ceph >= 0.55')
        sys.exit(1)

    hostname = utils.unit_get('private-address')
    admin_url = 'http://{}:80/swift'.format(hostname)
    internal_url = public_url = '{}/v1'.format(admin_url)
    utils.relation_set(service='swift',
                       region=utils.config_get('region'),
                       public_url=public_url, internal_url=internal_url,
                       admin_url=admin_url,
                       requested_roles=utils.config_get('operator-roles'),
                       rid=relid)


def identity_changed():
    emit_cephconf()
    restart() 


utils.do_hooks({
        'install': install,
        'config-changed': config_changed,
        'mon-relation-departed': mon_relation,
        'mon-relation-changed': mon_relation,
        'gateway-relation-joined': gateway_relation,
        'upgrade-charm': config_changed,  # same function ATM
        'identity-service-relation-joined': identity_joined,
        'identity-service-relation-changed': identity_changed
        })

sys.exit(0)
