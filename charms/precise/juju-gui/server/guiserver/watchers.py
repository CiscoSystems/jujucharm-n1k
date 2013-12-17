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

"""Juju GUI server watchers."""

from concurrent.futures import Future


class WatcherError(Exception):
    """Errors in the execution of the watcher methods."""


class AsyncWatcher(object):
    """An asynchronous watcher implementation returning Futures.

    Creating the watcher and putting changes in it is straightforward:

        watcher = AsyncWatcher()
        watcher.put('a change')

    Listeners can ask to be notified of the next changes using a watcher
    identifier (any hashable object, usually an integer number):

        changes_future = watcher.next(42)

    A request for changes returns a Future whose result is a list of changes
    not yet seen by the listener identified by the watcher id (42).
    If the watcher already includes changes that are new for a specific
    listener, the future is suddenly fired; otherwise, a call to
    changes_future.result() blocks until a new change is made available.
    Use this watcher in combination with Tornado's gen.coroutine decorator in
    order to suspend the function execution (and release the IO loop) until a
    change is available, e.g.:

    @gen.coroutine
    def my function(watcher):
        changes = yield watcher.next(42)
        print('New changes:', changes)

    A watcher can be closed with a final change by invoking its close() method.
    When a watcher is closed, it is no longer possible to put new changes in
    it, and subsequent listeners will receive only the closing change.
    """

    def __init__(self):
        self.closed = False
        self._changes = []

        # The _futures attribute maps watcher identifiers to pending Futures.
        self._futures = {}
        # The _positions attribute maps watcher identifiers to the
        # corresponding position in the changes list.
        self._positions = {}

    def _fire_futures(self, changes):
        """Set a result to all pending Futures.

        Update the position for all involved listeners.
        """
        position = len(self._changes)
        for watcher_id, future in self._futures.items():
            self._positions[watcher_id] = position
            future.set_result(changes)
        self._futures = {}

    @property
    def empty(self):
        """Return True if the watcher is empty, False otherwise."""
        return not self._changes

    def next(self, watcher_id):
        """Subscribe the given watcher id to the watcher, requesting changes.

        Return a Future whose result is a list of unseen changes.
        """
        if watcher_id in self._futures:
            raise WatcherError(
                'watcher {} is already waiting for changes'.format(watcher_id))
        future = Future()
        if self.closed:
            future.set_result(self._changes)
            return future
        position = len(self._changes)
        watcher_position = self._positions.get(watcher_id, 0)
        if watcher_position < position:
            # There are already unseen changes to send.
            missing_changes = self._changes[watcher_position:]
            future.set_result(missing_changes)
            self._positions[watcher_id] = position
        else:
            # There are not unseen changes, the returned future will be
            # probably fired later.
            self._futures[watcher_id] = future
        return future

    def getlast(self):
        """Return the last notified change.

        Raise an error if the watcher is empty.
        """
        if self._changes:
            return self._changes[-1]
        raise WatcherError('the watcher is empty')

    def put(self, change):
        """Put a change into the watcher."""
        if self.closed:
            raise WatcherError('unable to put changes in a closed watcher')
        self._changes.append(change)
        self._fire_futures([change])

    def close(self, change):
        """Close the watcher with the given closing message."""
        if self.closed:
            raise WatcherError('the watcher is already closed')
        self.closed = True
        self._changes = [change]
        self._fire_futures([change])
        self._positions = {}
