__author__ = 'kristoffer'

import unittest

from cflib.utils.callbacks import Caller


class CallerTest(unittest.TestCase):

    def setUp(self):
        self.callback_count = 0
        self.sut = Caller()

    def test_that_callback_is_added(self):
        # Fixture

        # Test
        self.sut.add_callback(self._callback)

        # Assert
        self.sut.call()
        self.assertEqual(1, self.callback_count)

    def test_that_callback_is_added_only_one_time(self):
        # Fixture

        # Test
        self.sut.add_callback(self._callback)
        self.sut.add_callback(self._callback)

        # Assert
        self.sut.call()
        self.assertEqual(1, self.callback_count)

    def test_that_multiple_callbacks_are_added(self):
        # Fixture

        # Test
        self.sut.add_callback(self._callback)
        self.sut.add_callback(self._callback2)

        # Assert
        self.sut.call()
        self.assertEqual(2, self.callback_count)

    def test_that_callback_is_removed(self):
        # Fixture
        self.sut.add_callback(self._callback)

        # Test
        self.sut.remove_callback(self._callback)

        # Assert
        self.sut.call()
        self.assertEqual(0, self.callback_count)

    def test_that_callback_is_called_with_arguments(self):
        # Fixture
        self.sut.add_callback(self._callback_with_args)

        # Test
        self.sut.call('The token')

        # Assert
        self.assertEqual('The token', self.callback_token)

    def _callback(self):
        self.callback_count += 1

    def _callback2(self):
        self.callback_count += 1

    def _callback_with_args(self, token):
        self.callback_token = token
