import re
import os

from subprocess import check_call, call

# Stuff copied from cinder py charm, needs to go somewhere
# common.
from misc_utils import (
    ensure_block_device,
    clean_storage,
)

from swift_storage_context import (
    SwiftStorageContext,
    SwiftStorageServerContext,
    RsyncContext,
)

from charmhelpers.fetch import apt_install, apt_update

from charmhelpers.core.host import (
    mkdir,
    mount,
    service_restart,
)

from charmhelpers.core.hookenv import (
    config,
    log,
    unit_private_ip,
    ERROR,
)

from charmhelpers.contrib.storage.linux.utils import (
    is_block_device,
)

from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    get_os_codename_install_source,
    get_os_codename_package,
    save_script_rc as _save_script_rc,
)

from charmhelpers.contrib.openstack import (
    templating,
)

PACKAGES = [
    'swift', 'swift-account', 'swift-container', 'swift-object',
    'xfsprogs', 'gdisk', 'lvm2', 'python-jinja2',
]

TEMPLATES = 'templates/'

ACCOUNT_SVCS = [
    'swift-account', 'swift-account-auditor',
    'swift-account-reaper', 'swift-account-replicator'
]

CONTAINER_SVCS = [
    'swift-container', 'swift-container-auditor',
    'swift-container-updater', 'swift-container-replicator'
]

OBJECT_SVCS = [
    'swift-object', 'swift-object-auditor',
    'swift-object-updater', 'swift-object-replicator'
]

RESTART_MAP = {
    '/etc/rsyncd.conf': ['rsync'],
    '/etc/swift/account-server.conf': ACCOUNT_SVCS,
    '/etc/swift/container-server.conf': CONTAINER_SVCS,
    '/etc/swift/object-server.conf': OBJECT_SVCS,
    '/etc/swift/swift.conf': ACCOUNT_SVCS + CONTAINER_SVCS + OBJECT_SVCS
}


def ensure_swift_directories():
    '''
    Ensure all directories required for a swift storage node exist with
    correct permissions.
    '''
    dirs = [
        '/etc/swift',
        '/var/cache/swift',
        '/srv/node',
    ]
    [mkdir(d, owner='swift', group='swift') for d in dirs
     if not os.path.isdir(d)]


def register_configs():
    release = get_os_codename_package('python-swift', fatal=False) or 'essex'
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)
    configs.register('/etc/swift/swift.conf',
                     [SwiftStorageContext()])
    configs.register('/etc/rsyncd.conf',
                     [RsyncContext()])
    for server in ['account', 'object', 'container']:
        configs.register('/etc/swift/%s-server.conf' % server,
                         [SwiftStorageServerContext()]),
    return configs


def swift_init(target, action, fatal=False):
    '''
    Call swift-init on a specific target with given action, potentially
    raising exception.
    '''
    cmd = ['swift-init', target, action]
    if fatal:
        return check_call(cmd)
    return call(cmd)


def do_openstack_upgrade(configs):
    new_src = config('openstack-origin')
    new_os_rel = get_os_codename_install_source(new_src)

    log('Performing OpenStack upgrade to %s.' % (new_os_rel))
    configure_installation_source(new_src)
    dpkg_opts = [
        '--option', 'Dpkg::Options::=--force-confnew',
        '--option', 'Dpkg::Options::=--force-confdef',
    ]
    apt_update()
    apt_install(packages=PACKAGES, options=dpkg_opts, fatal=True)
    configs.set_release(openstack_release=new_os_rel)
    configs.write_all()
    [service_restart(svc) for svc in
     (ACCOUNT_SVCS + CONTAINER_SVCS + OBJECT_SVCS)]


def find_block_devices():
    found = []
    incl = ['sd[a-z]', 'vd[a-z]', 'cciss\/c[0-9]d[0-9]']
    blacklist = ['sda', 'vda', 'cciss/c0d0']

    with open('/proc/partitions') as proc:
        print proc
        partitions = [p.split() for p in proc.readlines()[2:]]
    for partition in [p[3] for p in partitions if p]:
        for inc in incl:
            _re = re.compile(r'^(%s)$' % inc)
            if _re.match(partition) and partition not in blacklist:
                found.append(os.path.join('/dev', partition))
    return [f for f in found if is_block_device(f)]


def determine_block_devices():
    block_device = config('block-device')

    if not block_device or block_device in ['None', 'none']:
        log('No storage devices specified in config as block-device',
            level=ERROR)
        return None

    if block_device == 'guess':
        bdevs = find_block_devices()
    else:
        bdevs = block_device.split(' ')

    return [ensure_block_device(bd) for bd in bdevs]


def mkfs_xfs(bdev):
    cmd = ['mkfs.xfs', '-f', '-i', 'size=1024', bdev]
    check_call(cmd)


def setup_storage():
    for dev in determine_block_devices():
        if config('overwrite') in ['True', 'true']:
            clean_storage(dev)
        # if not cleaned and in use, mkfs should fail.
        mkfs_xfs(dev)
        _dev = os.path.basename(dev)
        _mp = os.path.join('/srv', 'node', _dev)
        mkdir(_mp, owner='swift', group='swift')
        mount(dev, '/srv/node/%s' % _dev, persist=True)
    check_call(['chown', '-R', 'swift:swift', '/srv/node/'])
    check_call(['chmod', '-R', '0750', '/srv/node/'])


def fetch_swift_rings(rings_url):
    log('swift-storage-node: Fetching all swift rings from proxy @ %s.' %
        rings_url)
    for server in ['account', 'object', 'container']:
        url = '%s/%s.ring.gz' % (rings_url, server)
        log('Fetching %s.' % url)
        cmd = ['wget', url, '-O', '/etc/swift/%s.ring.gz' % server]
        check_call(cmd)


def save_script_rc():
    env_vars = {}
    ip = unit_private_ip()
    for server in ['account', 'container', 'object']:
        port = config('%s-server-port' % server)
        url = 'http://%s:%s/recon/diskusage|"mounted":true' % (ip, port)
        svc = server.upper()
        env_vars.update({
            'OPENSTACK_PORT_%s' % svc: port,
            'OPENSTACK_SWIFT_SERVICE_%s' % svc: '%s-server' % server,
            'OPENSTACK_URL_%s' % svc: url,
        })
    _save_script_rc(**env_vars)
