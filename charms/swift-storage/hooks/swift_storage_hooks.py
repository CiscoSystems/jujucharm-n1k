#!/usr/bin/python

import os
import sys

from swift_storage_utils import (
    PACKAGES,
    RESTART_MAP,
    determine_block_devices,
    do_openstack_upgrade,
    ensure_swift_directories,
    fetch_swift_rings,
    register_configs,
    save_script_rc,
    setup_storage,
)

from charmhelpers.core.hookenv import (
    Hooks, UnregisteredHookError,
    config,
    log,
    relation_get,
    relation_set,
)

from charmhelpers.fetch import apt_install, apt_update
from charmhelpers.core.host import restart_on_change
from charmhelpers.payload.execd import execd_preinstall

from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    openstack_upgrade_available,
)

hooks = Hooks()
CONFIGS = register_configs()


@hooks.hook()
def install():
    execd_preinstall()
    configure_installation_source(config('openstack-origin'))
    apt_update()
    apt_install(PACKAGES, fatal=True)
    setup_storage()
    ensure_swift_directories()


@hooks.hook('config-changed')
@restart_on_change(RESTART_MAP)
def config_changed():
    if openstack_upgrade_available('swift'):
        do_openstack_upgrade(configs=CONFIGS)
    CONFIGS.write_all()
    save_script_rc()


@hooks.hook()
def swift_storage_relation_joined():
    devs = [os.path.basename(dev) for dev in determine_block_devices()]
    rel_settings = {
        'zone': config('zone'),
        'object_port': config('object-server-port'),
        'container_port': config('container-server-port'),
        'account_port': config('account-server-port'),
        'device': ':'.join(devs),
    }
    relation_set(**rel_settings)


@hooks.hook('swift-storage-relation-changed')
@restart_on_change(RESTART_MAP)
def swift_storage_relation_changed():
    rings_url = relation_get('rings_url')
    swift_hash = relation_get('swift_hash')
    if '' in [rings_url, swift_hash] or None in [rings_url, swift_hash]:
        log('swift_storage_relation_changed: Peer not ready?')
        sys.exit(0)
    CONFIGS.write('/etc/swift/swift.conf')
    fetch_swift_rings(rings_url)


def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))


if __name__ == '__main__':
    main()
