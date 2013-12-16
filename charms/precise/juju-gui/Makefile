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

JUJUTEST = yes | juju-test --timeout=40m -v -e "$(JUJU_ENV)"
VENV = tests/.venv
SYSDEPS = build-essential bzr libapt-pkg-dev libpython-dev python-virtualenv \
	rsync xvfb


all: setup

# The virtualenv is created by the 00-setup script and not here. This way we
# support the juju-test plugin, which calls the executable files in
# alphabetical order.
setup:
	tests/00-setup
	# Ensure the correct version of pip has been installed
	tests/.venv/bin/pip --version | grep "pip 1.4" || exit 1

sysdeps:
	sudo apt-get install --yes $(SYSDEPS)

unittest: setup
	tests/10-unit.test
	tests/11-server.test

ensure-juju-env:
ifndef JUJU_ENV
	$(error JUJU_ENV must be set.  See HACKING.md)
endif

ensure-juju-test: ensure-juju-env
	@which juju-test > /dev/null \
		|| (echo 'The "juju-test" command is missing.  See HACKING.md' \
		; false)

ftest: setup ensure-juju-test
	$(JUJUTEST) 20-functional.test

# This will be eventually removed when we have juju-test --clean-state.
test: unittest ftest

# This will be eventually renamed as test when we have juju-test --clean-state.
jujutest:
	$(JUJUTEST)

lint: setup
	@$(VENV)/bin/flake8 --show-source --exclude=.venv \
		hooks/ tests/ server/

clean:
	find . -name '*.pyc' -delete
	rm -rf $(VENV)
	rm -rf tests/download-cache

deploy: setup
	$(VENV)/bin/python tests/deploy.py

help:
	@echo -e 'Juju GUI charm - list of make targets:\n'
	@echo -e 'make sysdeps - Install the required system packages.\n'
	@echo -e 'make - Set up development and testing environment.\n'
	@echo 'make test JUJU_ENV="my-juju-env" - Run functional and unit tests.'
	@echo -e '  JUJU_ENV is the Juju environment that will be bootstrapped.\n'
	@echo -e 'make unittest - Run unit tests.\n'
	@echo 'make ftest JUJU_ENV="my-juju-env" - Run functional tests.'
	@echo -e '  JUJU_ENV is the Juju environment that will be bootstrapped.\n'
	@echo -e 'make lint - Run linter and pep8.\n'
	@echo -e 'make clean - Remove bytecode files and virtualenvs.\n'
	@echo 'make deploy [JUJU_ENV="my-juju-env]" - Deploy and expose the Juju'
	@echo '  GUI charm setting up a temporary Juju repository. Wait for the'
	@echo '  service to be started.  If JUJU_ENV is not passed, the charm will'
	@echo '  be deployed in the default Juju environment.'

.PHONY: all clean deploy ensure-juju-test ensure-juju-env ftest help \
    jujutest lint setup test unittest
