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

"""Example data used in tests."""


BUNDLE1 = """
bundle1:
  series: precise
  services:
    wordpress:
      charm: "cs:precise/wordpress-15"
      num_units: 1
      to: '0'
      options:
        debug: "no"
        engine: nginx
        tuning: single
        "wp-content": ""
      constraints: "cpu-cores=4,mem=4000"
      annotations:
        "gui-x": 313
        "gui-y": 51
    mysql:
      charm: "cs:precise/mysql-26"
      num_units: 2
      options:
        "binlog-format": MIXED
        "block-size": "5"
        "dataset-size": "80%"
        flavor: distro
        "ha-bindiface": eth0
        "ha-mcastport": "5411"
        "max-connections": "-1"
        "preferred-storage-engine": InnoDB
        "query-cache-size": "-1"
        "query-cache-type": "OFF"
        "rbd-name": mysql1
        "tuning-level": safest
        vip: ""
        vip_cidr: "24"
        vip_iface: eth0
      annotations:
        "gui-x": 669.5
        "gui-y": -33.5
  relations:
    - - "wordpress:db"
      - "mysql:db"
"""

BUNDLE2 = """
bundle2:
  series: precise
  services:
    mediawiki:
      charm: "cs:precise/mediawiki-9"
      num_units: 1
      to: '0'
      options:
        admins: ""
        debug: false
        logo: ""
        name: Please set name of wiki
        skin: vector
      annotations:
        "gui-x": 432
        "gui-y": 120
  relations: []
"""
