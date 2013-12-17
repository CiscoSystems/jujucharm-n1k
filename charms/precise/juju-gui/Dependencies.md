<!--
Dependencies.md
Copyright 2013 Canonical Ltd.
This work is licensed under the Creative Commons Attribution-Share Alike 3.0
Unported License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/3.0/ or send a letter to Creative
Commons, 171 Second Street, Suite 300, San Francisco, California, 94105, USA.
-->

# Juju GUI Charm external dependencies #

The Juju GUI has a number of external dependencies including packages that are
in the Ubuntu repositories and other packages that are collected together into
a single PPA that the Juju GUI charm developers maintain.

The packages in our devel PPA provide a superset of all software the charm may
need for different deployment strategies, such as using the sandbox
vs. improv, or Python Juju vs. Go Juju.

# Stable and Devel #

The GUI developers are members of the group ~juju-gui on Launchpad
(http://launchpad.net/~juju-gui). We have two PPAs hosted there to support the
GUI, `stable` and `devel`.

To isolate charm deployments from upstream code changes, we have collected all
of the external software we depend upon and stored them in the PPAs we manage.

The `stable` PPA includes only versions of our dependencies that we have
tested and found to work with the charm.  The `devel` version includes new
versions of external software that are in the process of being tested.

# Selecting the PPA #

In the charm configuration file (config.yaml) there is an entry
`repository-location` that defaults to `juju-gui/charm_stable`.  You can
change that in your config.yaml file or do a

`juju set juju-gui repository-location=ppa:juju-gui/charm_devel`,

for instance, immediately after deploying the GUI charm to pull from the devel
version.  Only Juju GUI developers doing QA for the new PPA should ever need
to select the devel version.

# Deploying for the enterprise #

Organizations deploying the charm for their enterprise may have the
requirement to not allow the installation of software from outside of their
local network.  Typically those environments require all external software to
be downloaded to a local server and used from there.  Our stable PPA provides a
single starting place to obtain QA'd software.  Dev ops can grab the subset of
packages they need, audit, test, and then serve them locally.  The
`repository-location` config variable can be used to point to the local repo.
