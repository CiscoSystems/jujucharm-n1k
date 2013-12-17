
#
# Copyright 2012 Canonical Ltd.
#
# Authors:
#  James Page <james.page@canonical.com>
#  Paul Collins <paul.collins@canonical.com>
#

import json
import subprocess
import time
import os
import apt_pkg as apt
from charmhelpers.core.host import (
    mkdir,
    service_restart,
)
from charmhelpers.core.hookenv import (
    log,
    ERROR,
)
from charmhelpers.contrib.storage.linux.utils import (
    zap_disk,
    is_block_device,
)
from utils import (
    get_unit_hostname,
)

LEADER = 'leader'
PEON = 'peon'
QUORUM = [LEADER, PEON]

PACKAGES = ['ceph', 'gdisk', 'ntp', 'btrfs-tools', 'python-ceph', 'xfsprogs']


def is_quorum():
    asok = "/var/run/ceph/ceph-mon.{}.asok".format(get_unit_hostname())
    cmd = [
        "ceph",
        "--admin-daemon",
        asok,
        "mon_status"
    ]
    if os.path.exists(asok):
        try:
            result = json.loads(subprocess.check_output(cmd))
        except subprocess.CalledProcessError:
            return False
        except ValueError:
            # Non JSON response from mon_status
            return False
        if result['state'] in QUORUM:
            return True
        else:
            return False
    else:
        return False


def is_leader():
    asok = "/var/run/ceph/ceph-mon.{}.asok".format(get_unit_hostname())
    cmd = [
        "ceph",
        "--admin-daemon",
        asok,
        "mon_status"
    ]
    if os.path.exists(asok):
        try:
            result = json.loads(subprocess.check_output(cmd))
        except subprocess.CalledProcessError:
            return False
        except ValueError:
            # Non JSON response from mon_status
            return False
        if result['state'] == LEADER:
            return True
        else:
            return False
    else:
        return False


def wait_for_quorum():
    while not is_quorum():
        time.sleep(3)


def add_bootstrap_hint(peer):
    asok = "/var/run/ceph/ceph-mon.{}.asok".format(get_unit_hostname())
    cmd = [
        "ceph",
        "--admin-daemon",
        asok,
        "add_bootstrap_peer_hint",
        peer
    ]
    if os.path.exists(asok):
        # Ignore any errors for this call
        subprocess.call(cmd)

DISK_FORMATS = [
    'xfs',
    'ext4',
    'btrfs'
]


def is_osd_disk(dev):
    try:
        info = subprocess.check_output(['sgdisk', '-i', '1', dev])
        info = info.split("\n")  # IGNORE:E1103
        for line in info:
            if line.startswith(
                'Partition GUID code: 4FBD7E29-9D25-41B8-AFD0-062C0CEFF05D'
            ):
                return True
    except subprocess.CalledProcessError:
        pass
    return False


def start_osds(devices):
    # Scan for ceph block devices
    rescan_osd_devices()
    if get_ceph_version() >= "0.56.6":
        # Use ceph-disk-activate for directory based OSD's
        for dev_or_path in devices:
            if os.path.exists(dev_or_path) and os.path.isdir(dev_or_path):
                subprocess.check_call(['ceph-disk-activate', dev_or_path])


def rescan_osd_devices():
    cmd = [
        'udevadm', 'trigger',
        '--subsystem-match=block', '--action=add'
    ]

    subprocess.call(cmd)


_bootstrap_keyring = "/var/lib/ceph/bootstrap-osd/ceph.keyring"


def is_bootstrapped():
    return os.path.exists(_bootstrap_keyring)


def wait_for_bootstrap():
    while (not is_bootstrapped()):
        time.sleep(3)


def import_osd_bootstrap_key(key):
    if not os.path.exists(_bootstrap_keyring):
        cmd = [
            'ceph-authtool',
            _bootstrap_keyring,
            '--create-keyring',
            '--name=client.bootstrap-osd',
            '--add-key={}'.format(key)
        ]
        subprocess.check_call(cmd)

# OSD caps taken from ceph-create-keys
_osd_bootstrap_caps = {
    'mon': [
        'allow command osd create ...',
        'allow command osd crush set ...',
        r'allow command auth add * osd allow\ * mon allow\ rwx',
        'allow command mon getmap'
    ]
}

_osd_bootstrap_caps_profile = {
    'mon': [
        'allow profile bootstrap-osd'
    ]
}


def parse_key(raw_key):
    # get-or-create appears to have different output depending
    # on whether its 'get' or 'create'
    # 'create' just returns the key, 'get' is more verbose and
    # needs parsing
    key = None
    if len(raw_key.splitlines()) == 1:
        key = raw_key
    else:
        for element in raw_key.splitlines():
            if 'key' in element:
                key = element.split(' = ')[1].strip()  # IGNORE:E1103
    return key


def get_osd_bootstrap_key():
    try:
        # Attempt to get/create a key using the OSD bootstrap profile first
        key = get_named_key('bootstrap-osd',
                            _osd_bootstrap_caps_profile)
    except:
        # If that fails try with the older style permissions
        key = get_named_key('bootstrap-osd',
                            _osd_bootstrap_caps)
    return key


_radosgw_keyring = "/etc/ceph/keyring.rados.gateway"


def import_radosgw_key(key):
    if not os.path.exists(_radosgw_keyring):
        cmd = [
            'ceph-authtool',
            _radosgw_keyring,
            '--create-keyring',
            '--name=client.radosgw.gateway',
            '--add-key={}'.format(key)
        ]
        subprocess.check_call(cmd)

# OSD caps taken from ceph-create-keys
_radosgw_caps = {
    'mon': ['allow rw'],
    'osd': ['allow rwx']
}


def get_radosgw_key():
    return get_named_key('radosgw.gateway', _radosgw_caps)


_default_caps = {
    'mon': ['allow rw'],
    'osd': ['allow rwx']
}


def get_named_key(name, caps=None):
    caps = caps or _default_caps
    cmd = [
        'ceph',
        '--name', 'mon.',
        '--keyring',
        '/var/lib/ceph/mon/ceph-{}/keyring'.format(
            get_unit_hostname()
        ),
        'auth', 'get-or-create', 'client.{}'.format(name),
    ]
    # Add capabilities
    for subsystem, subcaps in caps.iteritems():
        cmd.extend([
            subsystem,
            '; '.join(subcaps),
        ])
    return parse_key(subprocess.check_output(cmd).strip())  # IGNORE:E1103


def upgrade_key_caps(key, caps):
    ''' Upgrade key to have capabilities caps '''
    if not is_leader():
        # Not the MON leader OR not clustered
        return
    cmd = [
        'ceph', 'auth', 'caps', key
    ]
    for subsystem, subcaps in caps.iteritems():
        cmd.extend([subsystem, '; '.join(subcaps)])
    subprocess.check_call(cmd)


def bootstrap_monitor_cluster(secret):
    hostname = get_unit_hostname()
    path = '/var/lib/ceph/mon/ceph-{}'.format(hostname)
    done = '{}/done'.format(path)
    upstart = '{}/upstart'.format(path)
    keyring = '/var/lib/ceph/tmp/{}.mon.keyring'.format(hostname)

    if os.path.exists(done):
        log('bootstrap_monitor_cluster: mon already initialized.')
    else:
        # Ceph >= 0.61.3 needs this for ceph-mon fs creation
        mkdir('/var/run/ceph', perms=0755)
        mkdir(path)
        # end changes for Ceph >= 0.61.3
        try:
            subprocess.check_call(['ceph-authtool', keyring,
                                   '--create-keyring', '--name=mon.',
                                   '--add-key={}'.format(secret),
                                   '--cap', 'mon', 'allow *'])

            subprocess.check_call(['ceph-mon', '--mkfs',
                                   '-i', hostname,
                                   '--keyring', keyring])

            with open(done, 'w'):
                pass
            with open(upstart, 'w'):
                pass

            service_restart('ceph-mon-all')
        except:
            raise
        finally:
            os.unlink(keyring)


def get_ceph_version():
    apt.init()
    cache = apt.Cache()
    pkg = cache['ceph']
    if pkg.current_ver:
        return apt.upstream_version(pkg.current_ver.ver_str)
    else:
        return None


def version_compare(a, b):
    return apt.version_compare(a, b)


def update_monfs():
    hostname = get_unit_hostname()
    monfs = '/var/lib/ceph/mon/ceph-{}'.format(hostname)
    upstart = '{}/upstart'.format(monfs)
    if os.path.exists(monfs) and not os.path.exists(upstart):
        # Mark mon as managed by upstart so that
        # it gets start correctly on reboots
        with open(upstart, 'w'):
            pass


def osdize(dev, osd_format, osd_journal, reformat_osd=False):
    if dev.startswith('/dev'):
        osdize_dev(dev, osd_format, osd_journal, reformat_osd)
    else:
        osdize_dir(dev)


def osdize_dev(dev, osd_format, osd_journal, reformat_osd=False):
    if not os.path.exists(dev):
        log('Path {} does not exist - bailing'.format(dev))
        return

    if not is_block_device(dev):
        log('Path {} is not a block device - bailing'.format(dev))
        return

    if (is_osd_disk(dev) and not reformat_osd):
        log('Looks like {} is already an OSD, skipping.'.format(dev))
        return

    if device_mounted(dev):
        log('Looks like {} is in use, skipping.'.format(dev))
        return

    cmd = ['ceph-disk-prepare']
    # Later versions of ceph support more options
    if get_ceph_version() >= "0.48.3":
        if osd_format:
            cmd.append('--fs-type')
            cmd.append(osd_format)
        cmd.append(dev)
        if osd_journal and os.path.exists(osd_journal):
            cmd.append(osd_journal)
    else:
        # Just provide the device - no other options
        # for older versions of ceph
        cmd.append(dev)

    if reformat_osd:
        zap_disk(dev)

    subprocess.check_call(cmd)


def osdize_dir(path):
    if os.path.exists(os.path.join(path, 'upstart')):
        log('Path {} is already configured as an OSD - bailing'.format(path))
        return

    if get_ceph_version() < "0.56.6":
        log('Unable to use directories for OSDs with ceph < 0.56.6',
            level=ERROR)
        raise

    mkdir(path)
    cmd = [
        'ceph-disk-prepare',
        '--data-dir',
        path
    ]
    subprocess.check_call(cmd)


def device_mounted(dev):
    return subprocess.call(['grep', '-wqs', dev + '1', '/proc/mounts']) == 0


def filesystem_mounted(fs):
    return subprocess.call(['grep', '-wqs', fs, '/proc/mounts']) == 0
