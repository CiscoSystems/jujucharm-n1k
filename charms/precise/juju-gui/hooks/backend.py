# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2012-2013 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
A composition system for creating backend objects.

Backends implement install(), start() and stop() methods. A backend is composed
of many mixins and each mixin will implement any/all of those methods and all
will be called. Backends additionally provide for collecting property values
from each mixin into a single final property on the backend.

Mixins are not actually mixed in to the backend class using Python inheritance
machinery. Instead, each mixin is instantiated and collected in the Backend
__init__, as needed. Then the install(), start(), and stop() methods have a
"self" that is the simple instantiated mixin, and a "backend" argument that is
the backend instance. Python inheritance machinery is somewhat mimicked in that
certain properties and methods are explicitly aggregated on the backend
instance: see the chain_methods and merge_properties functions, and their
usages.

There is also a feature for determining if configuration values have changed
between old and new configurations so we can selectively take action.

The mixins appear in the code in the order they are instantiated by the
backend. Keeping them that way is useful.
"""

import errno
import os
import shutil

from charmhelpers import (
    log,
    open_port,
)

import utils


class SetUpMixin(object):
    """Handle the overall set up and clean up processes."""

    def install(self, backend):
        log('Setting up base dir: {}.'.format(utils.BASE_DIR))
        try:
            os.makedirs(utils.BASE_DIR)
        except OSError as err:
            # The base directory might already exist: ignore the error.
            if err.errno != errno.EEXIST:
                raise

    def destroy(self, backend):
        log('Cleaning up base dir: {}.'.format(utils.BASE_DIR))
        shutil.rmtree(utils.BASE_DIR)


class PythonInstallMixinBase(object):
    """Provide a common "install" method to ImprovMixin and PythonMixin."""

    def install(self, backend):
        if (not os.path.exists(utils.JUJU_AGENT_DIR) or
                backend.different('staging', 'juju-api-branch')):
            utils.fetch_api(backend.config['juju-api-branch'])


class ImprovMixin(PythonInstallMixinBase):
    """Manage the improv backend when on staging."""

    debs = ('zookeeper',)

    def start(self, backend):
        config = backend.config
        utils.start_improv(
            config['staging-environment'], config['ssl-cert-path'])

    def stop(self, backend):
        utils.stop_improv()


class SandboxMixin(object):
    pass


class PythonMixin(PythonInstallMixinBase):
    """Manage the real PyJuju backend."""

    def start(self, backend):
        utils.start_agent(backend.config['ssl-cert-path'])

    def stop(self, backend):
        utils.stop_agent()


class GoMixin(object):
    """Manage the real Go juju-core backend."""
    pass


class GuiMixin(object):
    """Install and start the GUI and its dependencies."""

    # The curl package is used to download release tarballs from Launchpad.
    debs = ('curl',)

    def install(self, backend):
        """Install the GUI and dependencies."""
        # If the source setting has changed since the last time this was run,
        # get the code, from either a static release or a branch as specified
        # by the souce setting, and install it.
        if backend.different('juju-gui-source'):
            # Get a tarball somehow.
            origin, version_or_branch = utils.parse_source(
                backend.config['juju-gui-source'])
            if origin == 'branch':
                logpath = backend.config['command-log-file']
                # Make sure we have the required build dependencies.
                # Note that we also need to add the juju-gui repository
                # containing our version of nodejs.
                log('Installing build dependencies.')
                utils.install_missing_packages(
                    utils.DEB_BUILD_DEPENDENCIES,
                    repository=backend.config['repository-location'])
                branch_url, revision = version_or_branch
                release_tarball_path = utils.fetch_gui_from_branch(
                    branch_url, revision, logpath)
            else:
                release_tarball_path = utils.fetch_gui_release(
                    origin, version_or_branch)
            # Install the tarball.
            utils.setup_gui(release_tarball_path)

    def start(self, backend):
        log('Starting Juju GUI.')
        config = backend.config
        build_dir = utils.compute_build_dir(
            config['juju-gui-debug'], config['serve-tests'])
        utils.write_gui_config(
            config['juju-gui-console-enabled'], config['login-help'],
            config['read-only'], config['staging'], config['charmworld-url'],
            build_dir, secure=config['secure'], sandbox=config['sandbox'],
            ga_key=config['ga-key'],
            default_viewmode=config['default-viewmode'],
            show_get_juju_button=config['show-get-juju-button'],
            password=config.get('password'))
        # Expose the service.
        open_port(80)
        open_port(443)


class ServerInstallMixinBase(object):
    """
    Provide a common "_setup_certificates" method to HaproxyApacheMixin and
    BuiltinServerMixin.
    """

    def _setup_certificates(self, backend):
        # Set up the SSL certificates.
        if backend.different(
                'ssl-cert-path', 'ssl-cert-contents', 'ssl-key-contents'):
            config = backend.config
            utils.save_or_create_certificates(
                config['ssl-cert-path'], config.get('ssl-cert-contents'),
                config.get('ssl-key-contents'))


class HaproxyApacheMixin(ServerInstallMixinBase):
    """Manage haproxy and Apache via Upstart."""

    debs = ('apache2', 'haproxy', 'openssl')
    # We need to add the juju-gui PPA containing our customized haproxy.
    ppa_required = True

    def install(self, backend):
        self._setup_certificates(backend)

    def start(self, backend):
        config = backend.config
        build_dir = utils.compute_build_dir(
            config['juju-gui-debug'], config['serve-tests'])
        utils.start_haproxy_apache(
            build_dir, config['serve-tests'], config['ssl-cert-path'],
            config['secure'])

    def stop(self, backend):
        utils.stop_haproxy_apache()


class BuiltinServerMixin(ServerInstallMixinBase):
    """Manage the builtin server via Upstart."""

    # The package python-bzrlib is required by juju-deployer.
    # The package python-pip is is used to install the GUI server dependencies.
    debs = ('openssl', 'python-bzrlib', 'python-pip')

    def install(self, backend):
        utils.install_builtin_server()
        self._setup_certificates(backend)

    def start(self, backend):
        config = backend.config
        build_dir = utils.compute_build_dir(
            config['juju-gui-debug'], config['serve-tests'])
        utils.start_builtin_server(
            build_dir, config['ssl-cert-path'], config['serve-tests'],
            config['sandbox'], config['builtin-server-logging'],
            not config['secure'], config['charmworld-url'])

    def stop(self, backend):
        utils.stop_builtin_server()


def call_methods(objects, name, *args):
    """For each given object, call, if present, the method named name.

    Pass the given args.
    """
    for obj in objects:
        method = getattr(obj, name, None)
        if method is not None:
            method(*args)


class Backend(object):
    """
    Support many configurations by composing methods and policy to interact
    with a Juju backend, collecting them from Strategy pattern mixin objects.
    """

    def __init__(self, config=None, prev_config=None):
        """Generate a list of mixin classes that implement the backend, working
        through composition.

        'config' is a dict which typically comes from the JSON de-serialization
            of config.json in JujuGUI.
        'prev_config' is a dict used to compute the differences. If it is not
            passed, all current config values are considered new.
        """
        if config is None:
            config = utils.get_config()
        self.config = config
        if prev_config is None:
            prev_config = {}
        self.prev_config = prev_config
        self.mixins = [SetUpMixin()]

        is_legacy_juju = utils.legacy_juju()

        if config['staging']:
            if not is_legacy_juju:
                raise ValueError('Unable to use staging with go backend')
            self.mixins.append(ImprovMixin())
        elif config['sandbox']:
            self.mixins.append(SandboxMixin())
        else:
            mixin = PythonMixin() if is_legacy_juju else GoMixin()
            self.mixins.append(mixin)

        # We always install and start the GUI.
        self.mixins.append(GuiMixin())
        # TODO: eventually this option will go away, as well as haproxy and
        # Apache.
        if config.get('builtin-server', False):
            self.mixins.append(BuiltinServerMixin())
        else:
            self.mixins.append(HaproxyApacheMixin())

    def different(self, *keys):
        """Return a boolean indicating if the current config
        value differs from the config value passed in prev_config
        with respect to any of the passed in string keys.
        """
        # Minimize lookups inside the loop, just because.
        current, previous = self.config.get, self.prev_config.get
        return any(current(key) != previous(key) for key in keys)

    def get_dependencies(self):
        """Return a tuple (debs, repository) representing dependencies."""
        debs = set()
        needs_ppa = False
        # Collect the required dependencies and check if adding the juju-gui
        # PPA is required.
        for mixin in self.mixins:
            debs.update(getattr(mixin, 'debs', ()))
            if getattr(mixin, 'ppa_required', False):
                needs_ppa = True
        return debs, self.config['repository-location'] if needs_ppa else None

    def install(self):
        """Execute the installation steps."""
        debs, repository = self.get_dependencies()
        log('Installing dependencies.')
        utils.install_missing_packages(debs, repository=repository)
        call_methods(self.mixins, 'install', self)

    def start(self):
        """Execute the charm's "start" steps."""
        call_methods(self.mixins, 'start', self)

    def stop(self):
        """Execute the charm's "stop" steps.

        Iterate through the mixins in reverse order.
        """
        call_methods(reversed(self.mixins), 'stop', self)

    def destroy(self):
        """Execute the charm removal steps.

        Iterate through the mixins in reverse order.
        """
        call_methods(reversed(self.mixins), 'destroy', self)
