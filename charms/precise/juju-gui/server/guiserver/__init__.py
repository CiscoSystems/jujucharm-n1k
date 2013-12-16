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

"""Juju GUI server.

The GUI server is a custom-made application based on the
[Tornado](http://www.tornadoweb.org/) framework.

It directly serves static files to the browser, including images, HTML, CSS and
JavaScript files via an HTTPS connection to port 443. HTTP connections to port
80 are redirected to the former one. All other URLs serve the common
`index.html` file.

It also acts as a proxy between the browser and the Juju API server that
performs the actual orchestration work. Both browser-server and server-Juju
connections are bidirectional, using the WebSocket protocol on the same port as
the HTTPS connection, allowing changes in the Juju environment to be propagated
and shown immediately by the browser. """

VERSION = (0, 2, 2)


def get_version():
    """Return the Juju GUI server version as a string."""
    return '.'.join(map(str, VERSION))
