# Copyright 2012 Canonical Ltd.

# This file is taken from the python-shelltoolbox package.
#
# IMPORTANT: Do not modify this file to add or change functionality.  If you
# really feel the need to do so, first convert our code to the shelltoolbox
# library, and modify it instead (or modify the helpers or utils module here,
# as appropriate).
#
# python-shell-toolbox is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the
# Free Software Foundation, version 3 of the License.
#
# python-shell-toolbox is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License
# along with python-shell-toolbox. If not, see <http://www.gnu.org/licenses/>.

"""Helper functions for accessing shell commands in Python."""

__metaclass__ = type
__all__ = [
    'apt_get_install',
    'bzr_whois',
    'cd',
    'command',
    'DictDiffer',
    'environ',
    'file_append',
    'file_prepend',
    'generate_ssh_keys',
    'get_su_command',
    'get_user_home',
    'get_user_ids',
    'install_extra_repositories',
    'join_command',
    'mkdirs',
    'run',
    'Serializer',
    'script_name',
    'search_file',
    'ssh',
    'su',
    'user_exists',
    'wait_for_page_contents',
    ]

from collections import namedtuple
from contextlib import contextmanager
from email.Utils import parseaddr
import errno
import json
import operator
import os
import pipes
import pwd
import re
import subprocess
import sys
from textwrap import dedent
import time
import urllib2


Env = namedtuple('Env', 'uid gid home')


def apt_get_install(*args, **kwargs):
    """Install given packages using apt.

    It is possible to pass environment variables to be set during install
    using keyword arguments.

    :raises: subprocess.CalledProcessError
    """
    caller = kwargs.pop('caller', run)
    debian_frontend = kwargs.pop('DEBIAN_FRONTEND', 'noninteractive')
    with environ(DEBIAN_FRONTEND=debian_frontend, **kwargs):
        cmd = ('apt-get', '-y', 'install') + args
        return caller(*cmd)


def bzr_whois(user):
    """Return full name and email of bzr `user`.

    Return None if the given `user` does not have a bzr user id.
    """
    with su(user):
        try:
            whoami = run('bzr', 'whoami')
        except (subprocess.CalledProcessError, OSError):
            return None
    return parseaddr(whoami)


@contextmanager
def cd(directory):
    """A context manager to temporarily change current working dir, e.g.::

        >>> import os
        >>> os.chdir('/tmp')
        >>> with cd('/bin'): print os.getcwd()
        /bin
        >>> print os.getcwd()
        /tmp
    """
    cwd = os.getcwd()
    os.chdir(directory)
    try:
        yield
    finally:
        os.chdir(cwd)


def command(*base_args):
    """Return a callable that will run the given command with any arguments.

    The first argument is the path to the command to run, subsequent arguments
    are command-line arguments to "bake into" the returned callable.

    The callable runs the given executable and also takes arguments that will
    be appeneded to the "baked in" arguments.

    For example, this code will list a file named "foo" (if it exists):

        ls_foo = command('/bin/ls', 'foo')
        ls_foo()

    While this invocation will list "foo" and "bar" (assuming they exist):

        ls_foo('bar')
    """
    def callable_command(*args):
        all_args = base_args + args
        return run(*all_args)

    return callable_command


@contextmanager
def environ(**kwargs):
    """A context manager to temporarily change environment variables.

    If an existing environment variable is changed, it is restored during
    context cleanup::

        >>> import os
        >>> os.environ['MY_VARIABLE'] = 'foo'
        >>> with environ(MY_VARIABLE='bar'): print os.getenv('MY_VARIABLE')
        bar
        >>> print os.getenv('MY_VARIABLE')
        foo
        >>> del os.environ['MY_VARIABLE']

    If we are adding environment variables, they are removed during context
    cleanup::

        >>> import os
        >>> with environ(MY_VAR1='foo', MY_VAR2='bar'):
        ...     print os.getenv('MY_VAR1'), os.getenv('MY_VAR2')
        foo bar
        >>> os.getenv('MY_VAR1') == os.getenv('MY_VAR2') == None
        True
    """
    backup = {}
    for key, value in kwargs.items():
        backup[key] = os.getenv(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, value in backup.items():
            if value is None:
                del os.environ[key]
            else:
                os.environ[key] = value


def file_append(filename, line):
    r"""Append given `line`, if not present, at the end of `filename`.

    Usage example::

        >>> import tempfile
        >>> f = tempfile.NamedTemporaryFile('w', delete=False)
        >>> f.write('line1\n')
        >>> f.close()
        >>> file_append(f.name, 'new line\n')
        >>> open(f.name).read()
        'line1\nnew line\n'

    Nothing happens if the file already contains the given `line`::

        >>> file_append(f.name, 'new line\n')
        >>> open(f.name).read()
        'line1\nnew line\n'

    A new line is automatically added before the given `line` if it is not
    present at the end of current file content::

        >>> import tempfile
        >>> f = tempfile.NamedTemporaryFile('w', delete=False)
        >>> f.write('line1')
        >>> f.close()
        >>> file_append(f.name, 'new line\n')
        >>> open(f.name).read()
        'line1\nnew line\n'

    The file is created if it does not exist::

        >>> import tempfile
        >>> filename = tempfile.mktemp()
        >>> file_append(filename, 'line1\n')
        >>> open(filename).read()
        'line1\n'
    """
    if not line.endswith('\n'):
        line += '\n'
    with open(filename, 'a+') as f:
        lines = f.readlines()
        if line not in lines:
            if not lines or lines[-1].endswith('\n'):
                f.write(line)
            else:
                f.write('\n' + line)


def file_prepend(filename, line):
    r"""Insert given `line`, if not present, at the beginning of `filename`.

    Usage example::

        >>> import tempfile
        >>> f = tempfile.NamedTemporaryFile('w', delete=False)
        >>> f.write('line1\n')
        >>> f.close()
        >>> file_prepend(f.name, 'line0\n')
        >>> open(f.name).read()
        'line0\nline1\n'

    If the file starts with the given `line`, nothing happens::

        >>> file_prepend(f.name, 'line0\n')
        >>> open(f.name).read()
        'line0\nline1\n'

    If the file contains the given `line`, but not at the beginning,
    the line is moved on top::

        >>> file_prepend(f.name, 'line1\n')
        >>> open(f.name).read()
        'line1\nline0\n'
    """
    if not line.endswith('\n'):
        line += '\n'
    with open(filename, 'r+') as f:
        lines = f.readlines()
        if lines[0] != line:
            try:
                lines.remove(line)
            except ValueError:
                pass
            lines.insert(0, line)
            f.seek(0)
            f.writelines(lines)


def generate_ssh_keys(path, passphrase=''):
    """Generate ssh key pair, saving them inside the given `directory`.

        >>> generate_ssh_keys('/tmp/id_rsa')
        0
        >>> open('/tmp/id_rsa').readlines()[0].strip()
        '-----BEGIN RSA PRIVATE KEY-----'
        >>> open('/tmp/id_rsa.pub').read().startswith('ssh-rsa')
        True
        >>> os.remove('/tmp/id_rsa')
        >>> os.remove('/tmp/id_rsa.pub')

    If either of the key files already exist, generate_ssh_keys() will
    raise an Exception.

    Note that ssh-keygen will prompt if the keyfiles already exist, but
    when we're using it non-interactively it's better to pre-empt that
    behaviour.

        >>> with open('/tmp/id_rsa', 'w') as key_file:
        ...    key_file.write("Don't overwrite me, bro!")
        >>> generate_ssh_keys('/tmp/id_rsa') # doctest: +ELLIPSIS
        Traceback (most recent call last):
        Exception: File /tmp/id_rsa already exists...
        >>> os.remove('/tmp/id_rsa')

        >>> with open('/tmp/id_rsa.pub', 'w') as key_file:
        ...    key_file.write("Don't overwrite me, bro!")
        >>> generate_ssh_keys('/tmp/id_rsa') # doctest: +ELLIPSIS
        Traceback (most recent call last):
        Exception: File /tmp/id_rsa.pub already exists...
        >>> os.remove('/tmp/id_rsa.pub')
    """
    if os.path.exists(path):
        raise Exception("File {} already exists.".format(path))
    if os.path.exists(path + '.pub'):
        raise Exception("File {}.pub already exists.".format(path))
    return subprocess.call([
        'ssh-keygen', '-q', '-t', 'rsa', '-N', passphrase, '-f', path])


def get_su_command(user, args):
    """Return a command line as a sequence, prepending "su" if necessary.

    This can be used together with `run` when the `su` context manager is not
    enough (e.g. an external program uses uid rather than euid).

        run(*get_su_command(user, ['bzr', 'whoami']))

    If the su is requested as current user, the arguments are returned as
    given::

        >>> import getpass
        >>> current_user = getpass.getuser()

        >>> get_su_command(current_user, ('ls', '-l'))
        ('ls', '-l')

    Otherwise, "su" is prepended::

        >>> get_su_command('nobody', ('ls', '-l', 'my file'))
        ('su', 'nobody', '-c', "ls -l 'my file'")
    """
    if get_user_ids(user)[0] != os.getuid():
        args = [i for i in args if i is not None]
        return ('su', user, '-c', join_command(args))
    return args


def get_user_home(user):
    """Return the home directory of the given `user`.

        >>> get_user_home('root')
        '/root'

    If the user does not exist, return a default /home/[username] home::

        >>> get_user_home('_this_user_does_not_exist_')
        '/home/_this_user_does_not_exist_'
    """
    try:
        return pwd.getpwnam(user).pw_dir
    except KeyError:
        return os.path.join(os.path.sep, 'home', user)


def get_user_ids(user):
    """Return the uid and gid of given `user`, e.g.::

        >>> get_user_ids('root')
        (0, 0)
    """
    userdata = pwd.getpwnam(user)
    return userdata.pw_uid, userdata.pw_gid


def install_extra_repositories(*repositories):
    """Install all of the extra repositories and update apt.

    Given repositories can contain a "{distribution}" placeholder, that will
    be replaced by current distribution codename.

    :raises: subprocess.CalledProcessError
    """
    distribution = run('lsb_release', '-cs').strip()
    # Starting from Oneiric, `apt-add-repository` is interactive by
    # default, and requires a "-y" flag to be set.
    assume_yes = None if distribution == 'lucid' else '-y'
    for repo in repositories:
        repository = repo.format(distribution=distribution)
        run('apt-add-repository', assume_yes, repository)
    run('apt-get', 'clean')
    run('apt-get', 'update')


def join_command(args):
    """Return a valid Unix command line from `args`.

        >>> join_command(['ls', '-l'])
        'ls -l'

    Arguments containing spaces and empty args are correctly quoted::

        >>> join_command(['command', 'arg1', 'arg containing spaces', ''])
        "command arg1 'arg containing spaces' ''"
    """
    return ' '.join(pipes.quote(arg) for arg in args)


def mkdirs(*args):
    """Create leaf directories (given as `args`) and all intermediate ones.

        >>> import tempfile
        >>> base_dir = tempfile.mktemp(suffix='/')
        >>> dir1 = tempfile.mktemp(prefix=base_dir)
        >>> dir2 = tempfile.mktemp(prefix=base_dir)
        >>> mkdirs(dir1, dir2)
        >>> os.path.isdir(dir1)
        True
        >>> os.path.isdir(dir2)
        True

    If the leaf directory already exists the function returns without errors::

        >>> mkdirs(dir1)

    An `OSError` is raised if the leaf path exists and it is a file::

        >>> f = tempfile.NamedTemporaryFile(
        ...     'w', delete=False, prefix=base_dir)
        >>> f.close()
        >>> mkdirs(f.name) # doctest: +ELLIPSIS
        Traceback (most recent call last):
        OSError: ...
    """
    for directory in args:
        try:
            os.makedirs(directory)
        except OSError as err:
            if err.errno != errno.EEXIST or os.path.isfile(directory):
                raise


def run(*args, **kwargs):
    """Run the command with the given arguments.

    The first argument is the path to the command to run.
    Subsequent arguments are command-line arguments to be passed.

    This function accepts all optional keyword arguments accepted by
    `subprocess.Popen`.
    """
    args = [i for i in args if i is not None]
    pipe = subprocess.PIPE
    process = subprocess.Popen(
        args, stdout=kwargs.pop('stdout', pipe),
        stderr=kwargs.pop('stderr', pipe),
        close_fds=kwargs.pop('close_fds', True), **kwargs)
    stdout, stderr = process.communicate()
    if process.returncode:
        exception = subprocess.CalledProcessError(
            process.returncode, repr(args))
        # The output argument of `CalledProcessError` was introduced in Python
        # 2.7. Monkey patch the output here to avoid TypeErrors in older
        # versions of Python, still preserving the output in Python 2.7.
        exception.output = ''.join(filter(None, [stdout, stderr]))
        raise exception
    return stdout


def script_name():
    """Return the name of this script."""
    return os.path.basename(sys.argv[0])


def search_file(regexp, filename):
    """Return the first line in `filename` that matches `regexp`."""
    with open(filename) as f:
        for line in f:
            if re.search(regexp, line):
                return line


def ssh(location, user=None, key=None, caller=subprocess.call):
    """Return a callable that can be used to run ssh shell commands.

    The ssh `location` and, optionally, `user` must be given.
    If the user is None then the current user is used for the connection.

    The callable internally uses the given `caller`::

        >>> def caller(cmd):
        ...     print tuple(cmd)
        >>> sshcall = ssh('example.com', 'myuser', caller=caller)
        >>> root_sshcall = ssh('example.com', caller=caller)
        >>> sshcall('ls -l') # doctest: +ELLIPSIS
        ('ssh', '-t', ..., 'myuser@example.com', '--', 'ls -l')
        >>> root_sshcall('ls -l') # doctest: +ELLIPSIS
        ('ssh', '-t', ..., 'example.com', '--', 'ls -l')

    The ssh key path can be optionally provided::

        >>> root_sshcall = ssh('example.com', key='/tmp/foo', caller=caller)
        >>> root_sshcall('ls -l') # doctest: +ELLIPSIS
        ('ssh', '-t', ..., '-i', '/tmp/foo', 'example.com', '--', 'ls -l')

    If the ssh command exits with an error code,
    a `subprocess.CalledProcessError` is raised::

        >>> ssh('loc', caller=lambda cmd: 1)('ls -l') # doctest: +ELLIPSIS
        Traceback (most recent call last):
        CalledProcessError: ...

    If ignore_errors is set to True when executing the command, no error
    will be raised, even if the command itself returns an error code.

        >>> sshcall = ssh('loc', caller=lambda cmd: 1)
        >>> sshcall('ls -l', ignore_errors=True)
    """
    sshcmd = [
        'ssh',
        '-t',
        '-t',  # Yes, this second -t is deliberate. See `man ssh`.
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        ]
    if key is not None:
        sshcmd.extend(['-i', key])
    if user is not None:
        location = '{}@{}'.format(user, location)
    sshcmd.extend([location, '--'])

    def _sshcall(cmd, ignore_errors=False):
        command = sshcmd + [cmd]
        retcode = caller(command)
        if retcode and not ignore_errors:
            raise subprocess.CalledProcessError(retcode, ' '.join(command))

    return _sshcall


@contextmanager
def su(user):
    """A context manager to temporarily run the script as a different user."""
    uid, gid = get_user_ids(user)
    os.setegid(gid)
    os.seteuid(uid)
    home = get_user_home(user)
    with environ(HOME=home):
        try:
            yield Env(uid, gid, home)
        finally:
            os.setegid(os.getgid())
            os.seteuid(os.getuid())


def user_exists(username):
    """Return True if given `username` exists, e.g.::

        >>> user_exists('root')
        True
        >>> user_exists('_this_user_does_not_exist_')
        False
    """
    try:
        pwd.getpwnam(username)
    except KeyError:
        return False
    return True


def wait_for_page_contents(url, contents, timeout=120, validate=None):
    if validate is None:
        validate = operator.contains
    start_time = time.time()
    while True:
        try:
            stream = urllib2.urlopen(url)
        except (urllib2.HTTPError, urllib2.URLError):
            pass
        else:
            page = stream.read()
            if validate(page, contents):
                return page
        if time.time() - start_time >= timeout:
            raise RuntimeError('timeout waiting for contents of ' + url)
        time.sleep(0.1)


class DictDiffer:
    """
    Calculate the difference between two dictionaries as:
    (1) items added
    (2) items removed
    (3) keys same in both but changed values
    (4) keys same in both and unchanged values
    """

    # Based on answer by hughdbrown at:
    # http://stackoverflow.com/questions/1165352

    def __init__(self, current_dict, past_dict):
        self.current_dict = current_dict
        self.past_dict = past_dict
        self.set_current = set(current_dict)
        self.set_past = set(past_dict)
        self.intersect = self.set_current.intersection(self.set_past)

    @property
    def added(self):
        return self.set_current - self.intersect

    @property
    def removed(self):
        return self.set_past - self.intersect

    @property
    def changed(self):
        return set(key for key in self.intersect
                   if self.past_dict[key] != self.current_dict[key])

    @property
    def unchanged(self):
        return set(key for key in self.intersect
                   if self.past_dict[key] == self.current_dict[key])

    @property
    def modified(self):
        return self.current_dict != self.past_dict

    @property
    def added_or_changed(self):
        return self.added.union(self.changed)

    def _changes(self, keys):
        new = {}
        old = {}
        for k in keys:
            new[k] = self.current_dict.get(k)
            old[k] = self.past_dict.get(k)
        return "%s -> %s" % (old, new)

    def __str__(self):
        if self.modified:
            s = dedent("""\
            added: %s
            removed: %s
            changed: %s
            unchanged: %s""") % (
                self._changes(self.added),
                self._changes(self.removed),
                self._changes(self.changed),
                list(self.unchanged))
        else:
            s = "no changes"
        return s


class Serializer:
    """Handle JSON (de)serialization."""

    def __init__(self, path, default=None, serialize=None, deserialize=None):
        self.path = path
        self.default = default or {}
        self.serialize = serialize or json.dump
        self.deserialize = deserialize or json.load

    def exists(self):
        return os.path.exists(self.path)

    def get(self):
        if self.exists():
            with open(self.path) as f:
                return self.deserialize(f)
        return self.default

    def set(self, data):
        with open(self.path, 'w') as f:
            self.serialize(data, f)
