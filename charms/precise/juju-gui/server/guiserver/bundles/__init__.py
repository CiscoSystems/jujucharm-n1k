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

"""Juju GUI server bundles support.

This package includes the objects and functions required to support deploying
bundles in juju-core. The base pieces of the infrastructure are placed in the
base module:

    - base.Deployer: any object implementing the following interface:
        - validate(user, name, bundle) -> Future (str or None);
        - import_bundle(user, name, bundle) -> int (a deployment id);
        - watch(deployment_id) -> int or None (a watcher id);
        - next(watcher_id) -> Future (changes or None);
        - status() -> list (of changes).

      The following arguments are passed to the validate and import_bundle
      interface methods:
        - user: a guiserver.auth.User instance, representing a logged in user;
        - name: a string representing the name of the bundle to be imported;
        - bundle: a YAML decoded object representing the bundle contents.
      The watch and next interface methods are used to retrieve information
      about the status of the currently started/scheduled deployments.

      The Deployer provides the logic to validate deployment requests based on
      the current state of the Juju environment, to import bundles, and to
      observe the deployment process. The Deployer does not know anything about
      the WebSocket request/response aspects, or how incoming data is retrieved
      or generated.

      The Deployer implementation in this package uses the juju-deployer
      library to import the provided bundle into the Juju environment. Since
      the mentioned operations are executed in a separate process, it is safe
      for the Deployer to interact with the blocking juju-deployer library.
      Those blocking functions are defined in the guiserver module of the
      juju-deployer project, described below.

      Note that the Deployer is not intended to store request related data: one
      instance is created once when the application is bootstrapped and used as
      a singleton by all WebSocket requests;

    - base.DeployMiddleware: process deployment requests arriving from the
      client, validate the requests' data and send the appropriate responses.
      Since the bundles deployment protocol (described below) mimics the usual
      request/response paradigm over a WebSocket, the real request handling
      is delegated by the DeployMiddleware to simple functions present in the
      views module of this package. The DeployMiddleware dispatches requests
      and collect responses to be sent back to the API client.

The views module is responsible for handling the request/response process and
of starting/scheduling bundle deployments.

    - views: as already mentioned, the functions in this module handle the
      requests from the API client, and set up responses. Since the views have
      access to the Deployer (described above), they can start/queue bundle
      deployments.

The deployer.guiserver module in the juju-deployer library is responsible for
validating a bundle and starting a deployment. Specifically the module defines
two functions:
    - validate: validate a bundle based on the state of the Juju env.;
    - import_bundle: starts the bundle deployment process.

The infrastructure described above can be summarized like the following
(each arrow meaning "calls"):
    - request handling: request -> DeployMiddleware -> views
    - deployment handling: views -> Deployer -> deployer.guiserver
    - response handling: views -> response

While the DeployMiddleware parses the request data and statically validates
that it is well formed, the Deployer takes care of validating the request in
the context of the current Juju environment.

Importing a bundle.
-------------------

A deployment request looks like the following:

    {
        'RequestId': 1,
        'Type': 'Deployer',
        'Request': 'Import',
        'Params': {
            'Name': 'bundle-name',
            'YAML': 'bundles',
            'BundleID': 'id'
        },
    }

In the request parameters above, the YAML field stores the YAML encoded
contents representing one or more bundles, and the Name field is the name of
the specific bundle (included in YAML) that must be deployed. The Name
parameter is optional in the case YAML includes only one bundle.  The BundleID
is optional and is used for incrementing the deployment counter in
Charmworld.

After receiving a deployment request, the DeployMiddleware sends a response
indicating whether or not the request has been accepted. This response is sent
relatively quickly.

If the request is not valid, the response looks like the following:

    {
        'RequestId': 1,
        'Response': {},
        'Error': 'some error: error details',
    }


If instead the request is valid, the response is like this:

    {
        'RequestId': 1,
        'Response': {'DeploymentId': 42},
    }

The deployment identifier can be used later to observe the progress and status
of the deployment (see below).

Watching a deployment progress.
-------------------------------

To start observing the progress of a specific deployment, the client must send
a watch request like the following:

    {
        'RequestId': 2,
        'Type': 'Deployer',
        'Request': 'Watch',
        'Params': {'DeploymentId': 42},
    }

If any error occurs, the response is like this:

    {
        'RequestId': 2,
        'Response': {},
        'Error': 'some error: error details',
    }

Otherwise, the response includes the watcher identifier to use to actually
retrieve deployment events, e.g.:

    {
        'RequestId': 2,
        'Response': {'WatcherId': 42},
    }

Use the watcher id to retrieve changes:

    {
        'RequestId': 3,
        'Type': 'Deployer',
        'Request': 'Next',
        'Params': {'WatcherId': 47},
    }

As usual, if an error occurs, the error description will be included in the
response:

    {
        'RequestId': 3,
        'Response': {},
        'Error': 'some error: error details',
    }

If everything is ok, a response is sent as soon as any unseen deployment change
becomes available, e.g.:

    {
        'RequestId': 3,
        'Response': {
            'Changes': [
                {'DeploymentId': 42, 'Status': 'scheduled', 'Time': 1377080066,
                 'Queue': 2},
                {'DeploymentId': 42, 'Status': 'scheduled', 'Time': 1377080062,
                 'Queue': 1},
                {'DeploymentId': 42, 'Status': 'started', 'Time': 1377080000,
                 'Queue': 0},
            ],
        },
    }

The Queue values in the response indicates the position of the requested
bundle deployment in the queue. The Deployer implementation processes one
bundle at the time. A Queue value of zero means the deployment will be started
as soon as possible.

The Status can be one of the following: 'scheduled', 'started', 'completed' and
'cancelled. See the next section for an explanation of how to cancel a pending
(scheduled) deployment.

The Time field indicates the number of seconds since the epoch at the time of
the change.

The Next request can be performed as many times as required by the API clients
after receiving a response from a previous one. However, if the Status of the
last deployment change is 'completed', no further changes will be notified, and
the watch request will always return only the last change:

    {
        'RequestId': 4,
        'Response': {
            'Changes': [
                {
                  'DeploymentId': 42,
                  'Status': 'completed',
                  'Time': 1377080000,
                  'Error': 'this field is only present if an error occurred',
                },
            ],
        },
    }

XXX frankban: a timeout to delete completed deployments history will be
eventually implemented.

Cancelling a deployment.
------------------------

It is possible to cancel the execution of scheduled deployments by sending a
Cancel request, e.g.:

    {
        'RequestId': 5,
        'Type': 'Deployer',
        'Request': 'Cancel',
        'Params': {'DeploymentId': 42},
    }

Note that it is allowed to cancel a deployment only if it is not yet started,
i.e. if it is in a 'scheduled' state.

If any error occurs, the response is like this:

    {
        'RequestId': 5,
        'Response': {},
        'Error': 'some error: error details',
    }

Usually an error response is returned when either an invalid deployment id was
provided or the request attempted to cancel an already started deployment.

If the deployment is successfully cancelled, the response is the following:

    {
        'RequestId': 5,
        'Response': {},
    }

Deployments status.
-------------------

To retrieve the current status of all the active/scheduled bundle deployments,
the client can send the following request:

    {
        'RequestId': 6,
        'Type': 'Deployer',
        'Request': 'Status',
    }

In the two examples below, the first one represents a response with errors,
the second one is a successful response:

    {
        'RequestId': 6,
        'Response': {},
        'Error': 'some error: error details',
    }

    {
        'RequestId': 6,
        'Response': {
            'LastChanges': [
                {'DeploymentId': 1, 'Status': 'completed', 'Time': 1377080001,
                 'Error': 'error'},
                {'DeploymentId': 2, 'Status': 'completed', 'Time': 1377080002},
                {'DeploymentId': 3, 'Status': 'started', 'Time': 1377080003,
                 'Queue': 0},
                {'DeploymentId': 4, 'Status': 'cancelled', 'Time': 1377080004},
                {'DeploymentId': 5, 'Status': 'scheduled', 'Time': 1377080005,
                 'Queue': 1},
            ],
        },
    }

In the second response above, the Error field in the first attempted deployment
(1) contains details about an error that occurred while deploying a bundle.
This means that bundle deployment has been completed but an error occurred
during the process.
"""
