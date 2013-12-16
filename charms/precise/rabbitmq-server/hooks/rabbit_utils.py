import os
import pwd
import grp
import re
import subprocess
import glob
import lib.utils as utils
import apt_pkg as apt

PACKAGES = ['pwgen', 'rabbitmq-server', 'python-amqplib']

RABBITMQ_CTL = '/usr/sbin/rabbitmqctl'
COOKIE_PATH = '/var/lib/rabbitmq/.erlang.cookie'
ENV_CONF = '/etc/rabbitmq/rabbitmq-env.conf'
RABBITMQ_CONF = '/etc/rabbitmq/rabbitmq.config'

def vhost_exists(vhost):
    cmd = [RABBITMQ_CTL, 'list_vhosts']
    out = subprocess.check_output(cmd)
    for line in out.split('\n')[1:]:
        if line == vhost:
            utils.juju_log('INFO', 'vhost (%s) already exists.' % vhost)
            return True
    return False


def create_vhost(vhost):
    if vhost_exists(vhost):
        return
    cmd = [RABBITMQ_CTL, 'add_vhost', vhost]
    subprocess.check_call(cmd)
    utils.juju_log('INFO', 'Created new vhost (%s).' % vhost)


def user_exists(user):
    cmd = [RABBITMQ_CTL, 'list_users']
    out = subprocess.check_output(cmd)
    for line in out.split('\n')[1:]:
        _user = line.split('\t')[0]
        if _user == user:
            admin = line.split('\t')[1]
            return True, (admin == '[administrator]')
    return False, False


def create_user(user, password, admin=False):
    exists, is_admin = user_exists(user)

    if not exists:
        cmd = [RABBITMQ_CTL, 'add_user', user, password]
        subprocess.check_call(cmd)
        utils.juju_log('INFO', 'Created new user (%s).' % user)

    if admin == is_admin:
        return

    if admin:
        cmd = [RABBITMQ_CTL, 'set_user_tags', user, 'administrator']
        utils.juju_log('INFO', 'Granting user (%s) admin access.')
    else:
        cmd = [RABBITMQ_CTL, 'set_user_tags', user]
        utils.juju_log('INFO', 'Revoking user (%s) admin access.')


def grant_permissions(user, vhost):
    cmd = [RABBITMQ_CTL, 'set_permissions', '-p',
           vhost, user, '.*', '.*', '.*']
    subprocess.check_call(cmd)


def service(action):
    cmd = ['service', 'rabbitmq-server', action]
    subprocess.check_call(cmd)


def rabbit_version():
    apt.init()
    cache = apt.Cache()
    pkg = cache['rabbitmq-server']
    if pkg.current_ver:
        return apt.upstream_version(pkg.current_ver.ver_str)
    else:
        return None


def cluster_with(host):
    utils.juju_log('INFO', 'Clustering with remote rabbit host (%s).' % host)
    vers = rabbit_version()
    if vers >= '3.0.1-1':
        cluster_cmd = 'join_cluster'
    else:
        cluster_cmd = 'cluster'
    out = subprocess.check_output([RABBITMQ_CTL, 'cluster_status'])
    for line in out.split('\n'):
        if re.search(host, line):
            utils.juju_log('INFO', 'Host already clustered with %s.' % host)
            return
    cmd = [RABBITMQ_CTL, 'stop_app']
    subprocess.check_call(cmd)
    cmd = [RABBITMQ_CTL, cluster_cmd, 'rabbit@%s' % host]
    subprocess.check_call(cmd)
    cmd = [RABBITMQ_CTL, 'start_app']
    subprocess.check_call(cmd)


def set_node_name(name):
    # update or append RABBITMQ_NODENAME to environment config.
    # rabbitmq.conf.d is not present on all releases, so use or create
    # rabbitmq-env.conf instead.
    if not os.path.isfile(ENV_CONF):
        utils.juju_log('INFO', '%s does not exist, creating.' % ENV_CONF)
        with open(ENV_CONF, 'wb') as out:
            out.write('RABBITMQ_NODENAME=%s\n' % name)
        return

    out = []
    f = False
    for line in open(ENV_CONF).readlines():
        if line.strip().startswith('RABBITMQ_NODENAME'):
            f = True
            line = 'RABBITMQ_NODENAME=%s\n' % name
        out.append(line)
    if not f:
        out.append('RABBITMQ_NODENAME=%s\n' % name)
    utils.juju_log('INFO', 'Updating %s, RABBITMQ_NODENAME=%s' %\
                   (ENV_CONF, name))
    with open(ENV_CONF, 'wb') as conf:
        conf.write(''.join(out))


def get_node_name():
    if not os.path.exists(ENV_CONF):
        return None
    env_conf = open(ENV_CONF, 'r').readlines()
    node_name = None
    for l in env_conf:
        if l.startswith('RABBITMQ_NODENAME'):
            node_name = l.split('=')[1].strip()
    return node_name


def _manage_plugin(plugin, action):
    os.environ['HOME'] = '/root'
    _rabbitmq_plugins = \
        glob.glob('/usr/lib/rabbitmq/lib/rabbitmq_server-*/sbin/rabbitmq-plugins')[0]
    subprocess.check_call([ _rabbitmq_plugins, action, plugin])


def enable_plugin(plugin):
    _manage_plugin(plugin, 'enable')


def disable_plugin(plugin):
    _manage_plugin(plugin, 'disable')

ssl_key_file = "/etc/rabbitmq/rabbit-server-privkey.pem"
ssl_cert_file = "/etc/rabbitmq/rabbit-server-cert.pem"


def enable_ssl(ssl_key, ssl_cert, ssl_port):
    uid = pwd.getpwnam("root").pw_uid
    gid = grp.getgrnam("rabbitmq").gr_gid
    with open(ssl_key_file, 'w') as key_file:
        key_file.write(ssl_key)
    os.chmod(ssl_key_file, 0640)
    os.chown(ssl_key_file, uid, gid)
    with open(ssl_cert_file, 'w') as cert_file:
        cert_file.write(ssl_cert)
    os.chmod(ssl_cert_file, 0640)
    os.chown(ssl_cert_file, uid, gid)
    with open(RABBITMQ_CONF, 'w') as rmq_conf:
        rmq_conf.write(utils.render_template(os.path.basename(RABBITMQ_CONF),
                              { "ssl_port": ssl_port,
                                "ssl_cert_file": ssl_cert_file,
                                "ssl_key_file": ssl_key_file})
                       )
