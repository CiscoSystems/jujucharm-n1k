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

"""Bundle deployment base objects.

This module defines the base pieces of the bundle support infrastructure,
including the Deployer object, responsible of starting/scheduling deployments,
and the DeployMiddleware, glue code that connects the WebSocket handler, the
bundle views and the Deployer itself. See the bundles package docstring for
a detailed explanation of how these objects are used.
"""

import time

from concurrent.futures import (
    process,
    ProcessPoolExecutor,
)
from deployer import guiserver as blocking
import deployer.cli
from tornado import gen
from tornado.ioloop import IOLoop
from tornado.util import ObjectDict

from guiserver.bundles import (
    utils,
    views,
)
from guiserver.utils import add_future
from guiserver.watchers import WatcherError


# Controls how many more calls than processes will be queued in the call queue.
# Set to zero to make Future.cancel() succeed more frequently (Futures in the
# call queue cannot be cancelled).
process.EXTRA_QUEUED_CALLS = 0
# Juju API versions supported by the GUI server Deployer.
# Tests use the first API version in this list.
SUPPORTED_API_VERSIONS = ['go']
# Options used by the juju-deployer.  The defaults work for us.
IMPORTER_OPTIONS = deployer.cli.setup_parser().parse_args([])


class Deployer(object):
    """Handle the bundle deployment process.

    This class provides the logic to validate deployment requests based on the
    current state of the Juju environment, and to start/observe the import
    process.

    The validation and deployments steps are executed in separate processes.
    It is possible to process only one bundle at the time.

    Note that the Deployer is not intended to store request related state: it
    is instantiated once when the application is bootstrapped and used as a
    singleton by all WebSocket requests.
    """

    def __init__(self, apiurl, apiversion, charmworldurl=None, io_loop=None):
        """Initialize the deployer.

        The apiurl argument is the URL of the juju-core WebSocket server.
        The apiversion argument is the Juju API version (e.g. "go").
        """
        self._apiurl = apiurl
        self._apiversion = apiversion
        if charmworldurl is not None and not charmworldurl.endswith('/'):
            charmworldurl = charmworldurl + '/'
        self._charmworldurl = charmworldurl
        if io_loop is None:
            io_loop = IOLoop.current()
        self._io_loop = io_loop

        # Deployment validation and importing executors.
        self._validate_executor = ProcessPoolExecutor(1)
        self._run_executor = ProcessPoolExecutor(1)

        # An observer instance is used to watch the deployments progress.
        self._observer = utils.Observer()
        # Queue stores the deployment identifiers corresponding to the
        # currently started/queued jobs.
        self._queue = []
        # The futures attribute maps deployment identifiers to Futures.
        self._futures = {}

    @gen.coroutine
    def validate(self, user, name, bundle):
        """Validate the deployment bundle.

        The validation is executed in a separate process using the
        juju-deployer library.

        Three arguments are provided:
          - user: the current authenticated user;
          - name: then name of the bundle to be imported;
          - bundle: a YAML decoded object representing the bundle contents.

        Return a Future whose result is a string representing an error or None
        if no error occurred.
        """
        apiversion = self._apiversion
        if apiversion not in SUPPORTED_API_VERSIONS:
            raise gen.Return('unsupported API version: {}'.format(apiversion))
        try:
            yield self._validate_executor.submit(
                blocking.validate, self._apiurl, user.password, bundle)
        except Exception as err:
            raise gen.Return(str(err))

    def import_bundle(self, user, name, bundle, bundle_id, test_callback=None):
        """Schedule a deployment bundle import process.

        The deployment is executed in a separate process.

        The following arguments are required:
          - user: the current authenticated user;
          - name: the name of the bundle to be imported;
          - bundle: a YAML decoded object representing the bundle contents.
          - bundle_id: the ID of the bundle.  May be None.

        It is possible to also provide an optional test_callback that will be
        called when the deployment is completed. Note that this functionality
        is present only for tests: clients should not consider the
        test_callback argument part of the API, and should instead use the
        watch/next methods to observe the progress of a deployment (see below).

        Return the deployment identifier assigned to this deployment process.
        """
        # Start observing this deployment, retrieve the next available
        # deployment id and notify its position at the end of the queue.
        deployment_id = self._observer.add_deployment()
        self._observer.notify_position(deployment_id, len(self._queue))
        # Add this deployment to the queue.
        self._queue.append(deployment_id)
        # Add the import bundle job to the run executor, and set up a callback
        # to be called when the import process completes.
        future = self._run_executor.submit(
            blocking.import_bundle,
            self._apiurl, user.password, name, bundle, IMPORTER_OPTIONS)
        add_future(self._io_loop, future, self._import_callback,
                   deployment_id, bundle_id)
        self._futures[deployment_id] = future
        # If a customized callback is provided, schedule it as well.
        if test_callback is not None:
            add_future(self._io_loop, future, test_callback)
        # Submit a sleeping job in order to avoid the next deployment job to be
        # immediately put in the executor's call queue. This allows for
        # cancelling scheduled jobs, even if the job is the next to be started.
        self._run_executor.submit(time.sleep, 1)
        return deployment_id

    def _import_callback(self, deployment_id, bundle_id, future):
        """Callback called when a deployment process is completed.

        This callback, scheduled in self.import_bundle(), receives the
        deployment_id identifying one specific deployment job, and the fired
        future returned by the executor.
        """
        if future.cancelled():
            # Notify a deployment has been cancelled.
            self._observer.notify_cancelled(deployment_id)
            success = False
        else:
            error = None
            success = True
            exception = future.exception()
            if exception is not None:
                error = utils.message_from_error(exception)
                success = False
            # Notify a deployment completed.
            self._observer.notify_completed(deployment_id, error=error)
        # Remove the completed deployment job from the queue.
        self._queue.remove(deployment_id)
        del self._futures[deployment_id]
        # Notify the new position of all remaining deployments in the queue.
        for position, deploy_id in enumerate(self._queue):
            self._observer.notify_position(deploy_id, position)
        # Increment the Charmworld deployment count upon successful
        # deployment.
        if success and bundle_id is not None:
            utils.increment_deployment_counter(
                bundle_id, self._charmworldurl)

    def watch(self, deployment_id):
        """Start watching a deployment and return a watcher identifier.

        The watcher id can be used by clients to observe changes occurring
        during the deployment process identified by the deployment id.
        Use the returned watcher id to start observing deployment changes
        (see the self.next() method below).

        Return None if the deployment identifier is not valid.
        """
        if deployment_id in self._observer.deployments:
            return self._observer.add_watcher(deployment_id)

    def next(self, watcher_id):
        """Wait for the next changes on a specific deployment.

        The given watcher identifier refers to a specific deployment process
        (see the self.watch() method above).
        Return a future whose result is a list of deployment changes.
        """
        deployment_id = self._observer.watchers.get(watcher_id)
        if deployment_id is None:
            return
        watcher = self._observer.deployments[deployment_id]
        try:
            return watcher.next(watcher_id)
        except WatcherError:
            return

    def cancel(self, deployment_id):
        """Attempt to cancel the deployment identified by deployment_id.

        Return None if the deployment has been correctly cancelled.
        Return an error string otherwise.
        """
        future = self._futures.get(deployment_id)
        if future is None:
            return 'deployment not found or already completed'
        if not future.cancel():
            return 'unable to cancel the deployment'

    def status(self):
        """Return a list containing the last known change for each deployment.
        """
        watchers = self._observer.deployments.values()
        return [i.getlast() for i in watchers]


class DeployMiddleware(object):
    """Handle the bundles deployment request/response process.

    This class handles the process of parsing requests from the GUI, checking
    if any incoming message is a deployment request, ensuring that the request
    is well-formed and, if so, forwarding the requests to the bundle views.

    Assuming that:
      - user is a guiserver.auth.User instance (used by this middleware in
        order to retrieve the credentials for connecting the Deployer to the
        Juju API server);
      - deployer is a guiserver.bundles.base.Deployer instance;
      - write_response is a callable that will be used to send responses to the
        client, i.e. deployments status and the results;
      - data is a JSON decoded object representing a single Juju API request;
    here is an usage example:

        deployment = DeployMiddleware(user, deployer, write_response)
        if deployment.requested(data):
            deployment.process_request(data)
    """

    def __init__(self, user, deployer, write_response):
        """Initialize the deployment middleware."""
        self._user = user
        self._deployer = deployer
        self._write_response = write_response
        self.routes = {
            'Import': views.import_bundle,
            'Watch': views.watch,
            'Next': views.next,
            'Cancel': views.cancel,
            'Status': views.status,
        }

    def requested(self, data):
        """Return True if data is a deployment request, False otherwise."""
        return (
            'RequestId' in data and
            data.get('Type') == 'Deployer' and
            data.get('Request') in self.routes
        )

    @gen.coroutine
    def process_request(self, data):
        """Process a deployment request."""
        request_id = data['RequestId']
        view = self.routes[data['Request']]
        request = ObjectDict(params=data.get('Params', {}), user=self._user)
        response = yield view(request, self._deployer)
        response['RequestId'] = request_id
        self._write_response(response)
