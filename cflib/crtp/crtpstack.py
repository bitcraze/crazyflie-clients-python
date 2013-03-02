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
        self.port2 = (header & 0xF0) >> 4
        self.channel = header & 0x03
        if dt:
            self.setData(dt)

    def getChannel(self):
        """
        Return the channel for this packet.
        """
        return self.channel

    def getPort(self):
        """
        Return the port for this packet.
        """
        return self.port2

    def getHeader(self):
        """
        Return the complete header for this packet.
        """
        return self.header

    def setPort(self, port):
        """
        Set the port for this packet.
        """
        self.port2 = port
        self.updateHeader()

    def setChannel(self, channel):
        """
        Set the channel for this packet.
        """
        self.channel = channel
        self.updateHeader()

    def setHeader(self, port, channel):
        """
        Set the port and channel for this packet.
        """
        self.port2 = port
        self.channel = channel
        self.updateHeader()

    def updateHeader(self):
        self.header = ((self.port2 & 0x0f) << 4 | 0x3 << 2 |
                       (self.channel & 0x03))

    #Some python madness to access different format of the data
    def getdata(self):
        return self._data

    def setData(self, data):
        if type(data) == str:
            self._data = data
        elif type(data) == list or type(data) == tuple:
            if len(data) == 1:
                self._data = struct.pack("B", data[0])
            elif len(data) > 1:
                self._data = struct.pack("B"*len(data), *data)
            else:
                self._data = ""
        else:
            raise Exception("Data shall be of str, tupple or list type")

    def getdatal(self):
        return list(self.getdatat())

    def getdatat(self):
        return struct.unpack("B"*len(self._data), self._data)

    def __str__(self):
        return "{}:{} {}".format(self.port2, self.channel, self.datat)

    data = property(getdata, setData)
    datal = property(getdatal, setData)
    datat = property(getdatat, setData)
    datas = property(getdata, setData)
