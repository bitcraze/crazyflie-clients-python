__author__ = 'kristoffer'

import unittest

from cflib.crtp.crtpstack import CRTPPacket


class CRTPPacketTest(unittest.TestCase):

    def setUp(self):
        self.callback_count = 0
        self.sut = CRTPPacket()

    def test_that_port_and_channle_is_encoded_in_header(self):
        # Fixture
        self.sut.set_header(2, 1)

        # Test
        actual = self.sut.get_header()

        # Assert
        expected = 0x2d
        self.assertEqual(expected, actual)

    def test_that_port_is_truncated_in_header(self):
        # Fixture
        port = 0xff
        self.sut.set_header(port, 0)

        # Test
        actual = self.sut.get_header()

        # Assert
        expected = 0xfc
        self.assertEqual(expected, actual)

    def test_that_channel_is_truncated_in_header(self):
        # Fixture
        channel = 0xff
        self.sut.set_header(0, channel)

        # Test
        actual = self.sut.get_header()

        # Assert
        expected = 0x0f
        self.assertEqual(expected, actual)

    def test_that_port_and_channel_is_encoded_in_header_when_set_separat(self):
        # Fixture
        self.sut.port = 2
        self.sut.channel = 1

        # Test
        actual = self.sut.get_header()

        # Assert
        expected = 0x2d
        self.assertEqual(expected, actual)

    def test_that_default_header_is_set_when_constructed(self):
        # Fixture

        # Test
        actual = self.sut.get_header()

        # Assert
        expected = 0x0c
        self.assertEqual(expected, actual)

    def test_that_header_is_set_when_constructed(self):
        # Fixture
        sut = CRTPPacket(header=0x21)

        # Test
        actual = sut.get_header()

        # Assert
        self.assertEqual(0x2d, actual)
        self.assertEqual(2, sut.port)
        self.assertEqual(1, sut.channel)
