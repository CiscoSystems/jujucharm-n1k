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

"""Juju GUI server distribution file."""

from distutils.core import setup
import os


ROOT = os.path.abspath(os.path.dirname(__file__))
PROJECT_NAME = 'guiserver'

project = __import__(PROJECT_NAME)
readme_path = os.path.join(ROOT, '..', 'README.md')

os.chdir(ROOT)
setup(
    name=PROJECT_NAME,
    version=project.get_version(),
    description=project.__doc__,
    long_description=open(readme_path).read(),
    author='The Juju GUI team',
    author_email='juju-gui@lists.ubuntu.com',
    url='https://launchpad.net/juju-gui',
    keywords='juju gui server',
    packages=[
        PROJECT_NAME,
        '{}.bundles'.format(PROJECT_NAME),
        '{}.tests'.format(PROJECT_NAME),
        '{}.tests.bundles'.format(PROJECT_NAME),
    ],
    scripts=['runserver.py'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU Affero General Public License v3',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Topic :: System :: Installation/Setup',
    ],
)
