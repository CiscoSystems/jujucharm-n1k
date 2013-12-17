# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2013 Canonical Ltd.
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

"""Juju GUI server management."""

import logging
import os
import sys

from tornado.ioloop import IOLoop
from tornado.options import (
    define,
    options,
    parse_command_line,
)

import guiserver
from guiserver.apps import (
    redirector,
    server,
)


DEFAULT_API_VERSION = 'go'
DEFAULT_SSL_PATH = '/etc/ssl/juju-gui'


def _add_debug(logger):
    """Add a debug option to the option parser.

    The debug option is True if --logging=DEBUG is passed, False otherwise.
    """
    debug = logger.level == logging.DEBUG
    options.define('debug', default=debug)


def _validate_required(*args):
    """Validate required arguments.

    Exit with an error if a mandatory argument is missing.
    """
    for name in args:
        try:
            value = options[name].strip()
        except AttributeError:
            value = ''
        if not value:
            sys.exit('error: the {} argument is required'.format(name))


def _validate_choices(option_name, choices):
    """Ensure the value passed for the given option is included in the choices.

    Exit with an error if the value is not in the accepted ones.
    """
    value = options[option_name]
    if value not in choices:
        sys.exit('error: accepted values for the {} argument are: {}'.format(
            option_name, ', '.join(choices)))


def _get_ssl_options():
    """Return a Tornado SSL options dict.

    The certificate and key file paths are generated using the base SSL path
    included in the options.
    """
    return {
        'certfile': os.path.join(options.sslpath, 'juju.crt'),
        'keyfile': os.path.join(options.sslpath, 'juju.key'),
    }


def setup():
    """Set up options and logger."""
    define(
        'guiroot', type=str,
        help='The Juju GUI static files path, e.g.: '
             '/var/lib/juju/agents/unit-juju-gui-0/charm/juju-gui/build-prod')
    define(
        'apiurl', type=str,
        help='The Juju WebSocket server address. This is usually the address '
             'of the bootstrap/state node as returned by "juju status".')
    # Optional parameters.
    define(
        'apiversion', type=str, default=DEFAULT_API_VERSION,
        help='the Juju API version/implementation. Currently the possible '
             'values are "go" (default) or "python".')
    define(
        'testsroot', type=str,
        help='The filesystem path of the Juju GUI tests directory. '
             'If not provided, tests are not served.')
    define(
        'sslpath', type=str, default=DEFAULT_SSL_PATH,
        help='The path where the SSL certificates are stored.')
    define(
        'insecure', type=bool, default=False,
        help='Set to True to serve the GUI over an insecure HTTP connection. '
             'Do not set unless you understand and accept the risks.')
    define(
        'sandbox', type=bool, default=False,
        help='Set to True if the GUI is running in sandbox mode, i.e. using '
             'an in-memory backend. When this is set to True, the GUI server '
             'does not listen to incoming WebSocket connections, and '
             'therefore the --apiurl and --apiversion options are ignored.')
    define(
        'charmworldurl', type=str,
        help='The URL to use for Charmworld.')

    # In Tornado, parsing the options also sets up the default logger.
    parse_command_line()
    _validate_required('guiroot')
    _validate_choices('apiversion', ('go', 'python'))
    _add_debug(logging.getLogger())


def run():
    """Run the server"""
    if options.insecure:
        # Run the server over an insecure HTTP connection.
        server().listen(80)
    else:
        # Default configuration: run the server over a secure HTTPS connection.
        server().listen(443, ssl_options=_get_ssl_options())
        redirector().listen(80)
    version = guiserver.get_version()
    logging.info('starting Juju GUI server v{}'.format(version))
    IOLoop.instance().start()
