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

"""Tests for the Juju GUI server watchers."""

from contextlib import contextmanager
import unittest

from guiserver import watchers


class TestAsyncWatcher(unittest.TestCase):

    def setUp(self):
        # Set up an async watcher.
        self.watcher = watchers.AsyncWatcher()

    def assert_results(self, future, expected):
        """Ensure the future is done and it contains the expected results."""
        self.assertTrue(future.done())
        self.assertEqual(expected, future.result())

    @contextmanager
    def assert_error(self, error):
        """Ensure a WatcherError is raised in the context block.

        Also check that the exception includes the expected error message.
        """
        with self.assertRaises(watchers.WatcherError) as context_manager:
            yield
        self.assertEqual(error, str(context_manager.exception))

    def test_changes_available(self):
        # Changes are suddenly returned when available.
        self.watcher.put('change1')
        future = self.watcher.next('watcher1')
        self.assert_results(future, ['change1'])

    def test_changes_unavailable(self):
        # The watcher's get() method returns a future that is fired when a
        # change becomes available.
        future = self.watcher.next('watcher1')
        self.assertFalse(future.done())
        self.watcher.put('change1')
        self.assert_results(future, ['change1'])

    def test_multiple_changes(self):
        # All the available changes are sent when the watcher's get() method
        # is called.
        self.watcher.put('change1')
        self.watcher.put('change2')
        self.watcher.put('change3')
        future = self.watcher.next('watcher1')
        self.assert_results(future, ['change1', 'change2', 'change3'])

    def test_resuming_watcher(self):
        # Only new changes are sent when resuming a watcher.
        future = self.watcher.next('watcher1')
        self.assertFalse(future.done())
        self.watcher.put('change1')
        self.watcher.put('change2')
        self.watcher.put('change3')
        self.assert_results(future, ['change1'])
        # Resume the watcher in order to get new changes.
        future = self.watcher.next('watcher1')
        self.assert_results(future, ['change2', 'change3'])

    def test_multiple_watchers(self):
        # Multiple watcher identifiers can be used to wait for changes.
        future1 = self.watcher.next('watcher1')
        future2 = self.watcher.next('watcher2')
        self.assertFalse(future1.done())
        self.assertFalse(future2.done())
        # When a change is put into the watcher, both listeners are notified.
        self.watcher.put('change1')
        self.assert_results(future1, ['change1'])
        self.assert_results(future2, ['change1'])

    def test_multiple_watcher_positions(self):
        # The watcher remembers what has been sent to each listener.
        future1 = self.watcher.next('watcher1')
        self.watcher.put('change1')
        self.watcher.put('change2')
        self.watcher.put('change3')
        self.assert_results(future1, ['change1'])
        # Create another listener, and ensure it is immediately notified of
        # all changes.
        future2 = self.watcher.next('watcher2')
        self.assert_results(future2, ['change1', 'change2', 'change3'])
        # Add a new change, resume the first listener, and ensure it is
        # immediately notified of missing changes.
        self.watcher.put('change4')
        future1 = self.watcher.next('watcher1')
        self.assert_results(future1, ['change2', 'change3', 'change4'])
        # Resume the second listener: it should receive the last change.
        future2 = self.watcher.next('watcher2')
        self.assert_results(future2, ['change4'])
        # A third listener gets all the changes.
        future3 = self.watcher.next('watcher3')
        self.assert_results(
            future3, ['change1', 'change2', 'change3', 'change4'])

    def test_integers(self):
        # Integer numbers can be used as watcher identifiers.
        # Note that each hashable object can be used: integers are tested here
        # because they are used in production code.
        future1 = self.watcher.next(1)
        future2 = self.watcher.next(2)
        self.watcher.put({'foo': 'bar'})
        self.assert_results(future1, [{'foo': 'bar'}])
        self.assert_results(future2, [{'foo': 'bar'}])

    def test_getlast(self):
        # It is possible to retrieve the last change from the watcher.
        self.watcher.put('change1')
        self.watcher.put('change2')
        self.assertEqual('change2', self.watcher.getlast())

    def test_getlast_empty(self):
        # An error is raised when getlast() is invoked on an empty watcher.
        with self.assert_error('the watcher is empty'):
            self.watcher.getlast()

    def test_getlast_closed(self):
        # The closing message is returned when the getlast() method is invoked
        # on a closed watcher.
        self.watcher.close('final change')
        self.assertEqual('final change', self.watcher.getlast())

    def test_empty(self):
        # It is possible to know if the watcher is empty.
        self.assertTrue(self.watcher.empty)
        self.watcher.put('a change')
        self.assertFalse(self.watcher.empty)

    def test_closing_time(self):
        # When a watcher is closed, only the last change is sent to all
        # listeners.
        self.assertFalse(self.watcher.closed)
        self.watcher.put('change1')
        future1 = self.watcher.next('watcher1')
        self.assert_results(future1, ['change1'])
        # Add a pending listener.
        future1 = self.watcher.next('watcher1')
        # Close the watcher.
        self.watcher.close('final change')
        self.assertTrue(self.watcher.closed)
        self.assert_results(future1, ['final change'])
        # Subsequent subscriptions are always immediately notified of the final
        # change.
        future1 = self.watcher.next('watcher1')
        self.assert_results(future1, ['final change'])
        future2 = self.watcher.next('watcher2')
        self.assert_results(future2, ['final change'])

    def test_closing_twice(self):
        # An error is raised attempting to close an already closed watcher.
        self.watcher.close('final change')
        with self.assert_error('the watcher is already closed'):
            self.watcher.close('final final change')
        # The last message is not overridden.
        self.assert_results(self.watcher.next('watcher1'), ['final change'])

    def test_close_and_put(self):
        # An error is raised if changes are added to a closed watcher.
        self.watcher.close('final change')
        with self.assert_error('unable to put changes in a closed watcher'):
            self.watcher.put('another change')
        # The last message is not overridden.
        self.assert_results(self.watcher.next('watcher1'), ['final change'])

    def test_get_error(self):
        # An error is raised if the same watcher identifier is used a second
        # time while the first listener is pending.
        future = self.watcher.next('w1')
        with self.assert_error('watcher w1 is already waiting for changes'):
            self.watcher.next('w1')
        # The first listener is not affected by the error.
        self.watcher.put('change1')
        self.assert_results(future, ['change1'])
