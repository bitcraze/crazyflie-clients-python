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
Enableds reading/writing of parameter values to/from the Crazyflie.

When a Crazyflie is connected it's possible to download a TableOfContent of all
the parameters that can be written/read.

"""

__author__ = 'Bitcraze AB'
__all__ = ['Param', 'ParamTocElement']

from cflib.utils.callbacks import Caller
import struct
from cflib.crtp.crtpstack import CRTPPacket, CRTPPort
from .toc import Toc, TocFetcher
from threading import Thread, Lock

from Queue import Queue

import logging
logger = logging.getLogger(__name__)

#Possible states
IDLE = 0
WAIT_TOC = 1
WAIT_READ = 2
WAIT_WRITE = 3

TOC_CHANNEL = 0
READ_CHANNEL = 1
WRITE_CHANNEL = 2

# TOC access command
TOC_RESET = 0
TOC_GETNEXT = 1
TOC_GETCRC32 = 2


# One element entry in the TOC
class ParamTocElement:
    """An element in the Log TOC."""

    RW_ACCESS = 0
    RO_ACCESS = 1

    types = {0x08: ("uint8_t",  '<B'),
             0x09: ("uint16_t", '<H'),
             0x0A: ("uint32_t", '<L'),
             0x0B: ("uint64_t", '<Q'),
             0x00: ("int8_t",   '<b'),
             0x01: ("int16_t",  '<h'),
             0x02: ("int32_t",  '<i'),
             0x03: ("int64_t",  '<q'),
             0x05: ("FP16",     ''),
             0x06: ("float",    '<f'),
             0x07: ("double",   '<d')}

    def __init__(self, data=None):
        """TocElement creator. Data is the binary payload of the element."""
        if (data):
            strs = struct.unpack("s" * len(data[2:]), data[2:])
            strs = ("{}" * len(strs)).format(*strs).split("\0")
            self.group = strs[0]
            self.name = strs[1]

            self.ident = ord(data[0])

            self.ctype = self.types[ord(data[1]) & 0x0F][0]
            self.pytype = self.types[ord(data[1]) & 0x0F][1]

            self.access = ord(data[1]) & 0x10


class Param():
    """
    Used to read and write parameter values in the Crazyflie.
    """

    toc = Toc()

    def __init__(self, crazyflie):
        self.cf = crazyflie
        self.paramUpdateCallbacks = {}
        self.paramUpdater = _ParamUpdater(self.cf, self._param_updated)
        self.paramUpdater.start()

    def _param_updated(self, pk):
        varId = pk.datal[0]
        element = self.toc.get_element_by_id(varId)
        s = struct.unpack(element.pytype, pk.data[1:])[0]
        s = s.__str__()
        completeName = "%s.%s" % (element.group, element.name)
        cb = self.paramUpdateCallbacks[completeName]
        cb.call(completeName, s)

    def add_update_callback(self, paramname, cb):
        """
        Add a callback for a specific parameter name. This callback will be
        executed when a new value is read from the Crazyflie.
        """
        if ((paramname in self.paramUpdateCallbacks) is False):
            self.paramUpdateCallbacks[paramname] = Caller()

        self.paramUpdateCallbacks[paramname].add_callback(cb)

    def refresh_toc(self, refreshDoneCallback, toc_cache):
        """
        Initiate a refresh of the parameter TOC.
        """
        self.toc = Toc()
        tocFetcher = TocFetcher(self.cf, ParamTocElement,
                                CRTPPort.PARAM, self.toc,
                                refreshDoneCallback, toc_cache)
        tocFetcher.start()

    def request_param_update(self, completeName):
        """
        Request an update of the value for the supplied parameter.
        """
        self.paramUpdater.requestQueue.put(
            self.toc.get_element_id(completeName))

    def set_value(self, completeName, value):
        """
        Set the value for the supplied parameter.
        """
        element = self.toc.get_element_by_complete_name(completeName)
        if (element is not None):
            varid = element.ident
            pk = CRTPPacket()
            pk.set_header(CRTPPort.PARAM, WRITE_CHANNEL)
            pk.data = struct.pack('<B', varid)
            pk.data += struct.pack(element.pytype, eval(value))
            self.cf.send_packet(pk, expect_answer=True)
        else:
            logger.warning("Cannot set value for [%s], it's not in the TOC!",
                           completeName)


class _ParamUpdater(Thread):
    def __init__(self, cf, updatedCallback):
        Thread.__init__(self)
        self.setDaemon(True)
        self.wait_lock = Lock()
        self.cf = cf
        self.updatedCallback = updatedCallback
        self.requestQueue = Queue()
        self.cf.add_port_callback(CRTPPort.PARAM, self._new_packet_cb)

    def _new_packet_cb(self, pk):
        if (pk.channel != TOC_CHANNEL):
            self.updatedCallback(pk)
            self.wait_lock.release()

    def _request_param_update(self, varid):
        logger.debug("Requesting update for varid %d", varid)
        pk = CRTPPacket()
        pk.set_header(CRTPPort.PARAM, READ_CHANNEL)
        pk.data = struct.pack('<B', varid)
        self.cf.send_packet(pk, expect_answer=True)

    def run(self):
        while(True):
            varid = self.requestQueue.get()  # Wait for request update
            self.wait_lock.acquire()
            self._request_param_update(varid)  # Send request for update
