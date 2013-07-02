#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2013 Bitcraze AB
#
#  Crazyflie Nano Quadcopter Client
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.

"""
CRTP packet and ports.
"""

__author__ = 'Bitcraze AB'
__all__ = ['CRTPPort', 'CRTPPacket']


import struct


class CRTPPort:
    """
    Lists the available ports for the CRTP.
    """
    CONSOLE = 0x00
    PARAM = 0x02
    COMMANDER = 0x03
    LOGGING = 0x05
    DEBUGDRIVER = 0x0E
    LINKCTRL = 0x0F
    ALL = 0xFF


class CRTPPacket(object):
    """
    A packet that can be sent via the CRTP.
    """

    def __init__(self, header=0, dt=None):
        """
        Create an empty packet with default values.
        """
        self.size = 0
        self._data = ""
        self.header = header
        self._port = (header & 0xF0) >> 4
        self._channel = header & 0x03
        if dt:
            self._set_data(dt)

    def _get_channel(self):
        return self._channel

    def _set_channel(self, channel):
        self._channel = channel
        self._update_header()

    def _get_port(self):
        return self._port

    def _set_port(self, port):
        self._port = port
        self._update_header()

    def get_header(self):
        """Get the header"""
        self._update_header()
        return self.header

    def set_header(self, port, channel):
        """
        Set the port and channel for this packet.
        """
        self._port = port
        self.channel = channel
        self._update_header()

    def _update_header(self):
        self.header = ((self._port & 0x0f) << 4 | 0x3 << 2 |
                       (self.channel & 0x03))

    #Some python madness to access different format of the data
    def _get_data(self):
        return self._data

    def _set_data(self, data):
        if type(data) == str:
            self._data = data
        elif type(data) == list or type(data) == tuple:
            if len(data) == 1:
                self._data = struct.pack("B", data[0])
            elif len(data) > 1:
                self._data = struct.pack("B" * len(data), *data)
            else:
                self._data = ""
        else:
            raise Exception("Data shall be of str, tupple or list type")

    def _get_data_l(self):
        return list(self._get_data_t())

    def _get_data_t(self):
        return struct.unpack("B" * len(self._data), self._data)

    def __str__(self):
        return "{}:{} {}".format(self._port, self.channel, self.datat)

    data = property(_get_data, _set_data)
    datal = property(_get_data_l, _set_data)
    datat = property(_get_data_t, _set_data)
    datas = property(_get_data, _set_data)
    port = property(_get_port, _set_port)
    channel = property(_get_channel, _set_channel)
