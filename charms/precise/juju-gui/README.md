<!--
README.md
Copyright 2013 Canonical Ltd.
This work is licensed under the Creative Commons Attribution-Share Alike 3.0
Unported License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/3.0/ or send a letter to Creative
Commons, 171 Second Street, Suite 300, San Francisco, California, 94105, USA.
-->

# Juju GUI Charm #

This charm makes it easy to deploy a Juju GUI into an existing environment.

## Supported Browsers ##

The Juju GUI supports recent releases of the Chrome, Chromium and Firefox web
browsers.

## Demo and Staging Servers ##

The Juju GUI runs the Juju Charm Store on
[jujucharms.com](http://jujucharms.com).  From there,  you can browse charms,
try the GUI, and build an example environment to export for use elsewhere.

A [staging server](http://comingsoon.jujucharms.com/) is also available,
running the latest and greatest version.

## Deploying the Juju GUI ##

Deploying the Juju GUI is accomplished using Juju itself.

You need a configured and bootstrapped Juju environment: see the Juju docs
about [getting started](https://juju.ubuntu.com/docs/getting-started.html),
and then run the usual bootstrap command.

    juju bootstrap

Next, you simply need to deploy the charm and expose it.  (See also "Deploying
with Jitsu" below, for another option.)

    juju deploy juju-gui
    juju expose juju-gui

Finally, you need to identify the GUI's URL. It can take a few minutes for the
GUI to be built and to start; this command will let you see when it is ready
to go by giving you regular status updates:

    watch juju status

Eventually, at the end of the status you will see something that looks like
this:

    services:
      juju-gui:
        charm: cs:precise/juju-gui-7
        exposed: true
        relations: {}
        units:
          juju-gui/0:
            agent-state: started
            machine: 1
            open-ports:
            - 80/tcp
            - 443/tcp
            public-address: ec2-www-xxx-yyy-zzz.compute-1.amazonaws.com

That means you can go to the public-address in my browser via HTTPS
(https://ec2-www-xxx-yyy-zzz.compute-1.amazonaws.com/ in this example), and
start configuring the rest of Juju with the GUI.  You should see a similar
web address.  Accessing the GUI via HTTP will redirect to using HTTPS.

By default, the deployment uses self-signed certificates. The browser will ask
you to accept a security exception once.

You will see a login form with the username fixed to "user-admin" (for juju-
core) or "admin" (for pyjuju). The password is the same as your Juju
environment's `admin-secret`, found in `~/.juju/environments.yaml`.

### Deploying behind a firewall ###

When using the default options the charm uses the network connection only for
installing Deb packages from the default Ubuntu repositories. For this reason
the charm can be deployed behind a firewall in the usual way:

    juju deploy juju-gui

There are situations and customizations in which the charm needs to connect to
Launchpad:

- juju-gui-source is set to "stable" or "trunk": in this cases the charm pulls
  the latest stable or development release from Launchpad;
- juju-gui-source is set to a branch (e.g. "lp:juju-gui"): in this case the
  charm retrieves a checkout of the specified branch from Launchpad, and adds
  an external Launchpad PPA to install build dependencies;
- juju-gui-source is set to a specific version number not available in the
  local store (i.e. in the releases directory of the deployed charm): in this
  case the release is downloaded from Launchpad;
- builtin-server is set to false: in this case the charm adds an external
  Launchpad PPA to install the legacy server dependencies.

If, for any reason, you need to use the legacy server, it is still possible to
deploy behind a firewall configuring the charm to pull the GUI release from a
location you specify.

For both Juju Core and PyJuju, you must simply do the following steps.  Note
that PyJuju must do these steps, plus another set described further below.

The config variable `juju-gui-source` allows a `url:` prefix which understands
both `http://` and `file://` protocols.  We will use this to load a local copy
of the GUI source.

1. Download the latest release of the Juju GUI Source from [the Launchpad
downloads page](https://launchpad.net/juju-gui/+download) and save it to a
location that will be accessible to the *unit* either via filesystem or HTTP.
2. Set the config variable to that location using a command such as

    `juju set juju-gui juju-gui-source=url:...`

    where the ellipsis after the `url:` is your `http://` or `file://` URI.  This
    may also be done during the deploy step using `--config`.

3. If you had already tried to deploy the GUI and received an install error due
to not being able to retrieve the source, you may also need to retry the unit
with the following command (using the unit the GUI is deployed on):

    `juju resolved --retry juju-gui/0`

These steps are sufficient for Juju Core.  If you are using PyJuju, you need to
do another set of steps in addition.

1. Use bzr to branch lp:~hazmat/juju/rapi-rollup locally ("bzr branch
lp:~hazmat/juju/rapi-rollup") and copy the branch to the gui service machine.

2. Use "juju set juju-gui juju-api-branch=PATH_TO_LOCAL_BZR_BRANCH" (where the
path is *not* a file:// URI).

3. Retry as described in the step 3 above (`juju resolved --retry juju-gui/0`).

### Upgrading the charm behind a firewall ###

When a new version of Juju GUI is released, the charm is updated to include the
new release in the local releases repository. Assuming the new version is
1.0.1, after upgrading the charm, it is possible to also upgrade to the newer
Juju GUI release by running the following:

    juju set juju-gui-source=1.0.1

In this case the new version will be found in the local repository and
therefore the charm will not attempt to connect to Launchpad.

### Deploying to a chosen machine ###

The instructions above cause you to use a separate machine to work with the
GUI.  If you'd like to reduce your machine footprint (and perhaps your costs),
you can colocate the GUI with the Juju bootstrap node.

This approach might change in the future (possibly with the Juju shipped with
Ubuntu 13.10), so be warned.

The instructions differ depending on the Juju implementation.

#### juju-core ####

Replace "juju deploy cs:precise/juju-gui" from the previous
instructions with this:

    juju deploy --force-machine 0 cs:precise/juju-gui

#### pyjuju ####

Colocation support is not included by default in the pyjuju implementation; to
activate it, you will need to install Jitsu:

    sudo apt-get install juju-jitsu

and then replace "juju deploy cs:precise/juju-gui" from the previous
instructions with this:

    jitsu deploy-to 0 cs:precise/juju-gui

## Contacting the Developers ##

If you run into problems with the charm, please feel free to contact us on the
[Juju mailing list](https://lists.ubuntu.com/mailman/listinfo/juju), or on
Freenode's IRC network on #juju.  We're not always around (working hours in
Europe and North America are your best bets), but if you send us a mail or
ping "jujugui" we will eventually get back to you.

If you want to help develop the charm, please see the charm's `HACKING.md`.
