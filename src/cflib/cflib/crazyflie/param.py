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
Enables reading/writing of parameter values to/from the Crazyflie.

When a Crazyflie is connected it's possible to download a TableOfContent of all
the parameters that can be written/read.

"""
import logging
import struct
import sys
from threading import Lock
from threading import Thread

from cflib.crtp.crtpstack import CRTPPacket
from cflib.crtp.crtpstack import CRTPPort
from cflib.utils.callbacks import Caller

from .toc import Toc
from .toc import TocFetcher
if sys.version_info < (3,):
    from Queue import Queue
else:
    from queue import Queue


__author__ = 'Bitcraze AB'
__all__ = ['Param', 'ParamTocElement']

logger = logging.getLogger(__name__)

# Possible states
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

    types = {0x08: ("uint8_t", '<B'),
             0x09: ("uint16_t", '<H'),
             0x0A: ("uint32_t", '<L'),
             0x0B: ("uint64_t", '<Q'),
             0x00: ("int8_t", '<b'),
             0x01: ("int16_t", '<h'),
             0x02: ("int32_t", '<i'),
             0x03: ("int64_t", '<q'),
             0x05: ("FP16", ''),
             0x06: ("float", '<f'),
             0x07: ("double", '<d')}

    def __init__(self, data=None):
        """TocElement creator. Data is the binary payload of the element."""
        if (data):
            strs = struct.unpack("s" * len(data[2:]), data[2:])
            if sys.version_info < (3,):
                strs = ("{}" * len(strs)).format(*strs).split("\0")
            else:
                s = ""
                for ch in strs:
                    s += ch.decode('ISO-8859-1')
                strs = s.split("\x00")
            self.group = strs[0]
            self.name = strs[1]

            if type(data[0]) == str:
                self.ident = ord(data[0])
            else:
                self.ident = data[0]

            metadata = data[1]
            if type(metadata) == str:
                metadata = ord(metadata)

            self.ctype = self.types[metadata & 0x0F][0]
            self.pytype = self.types[metadata & 0x0F][1]
            if ((metadata & 0x40) != 0):
                self.access = ParamTocElement.RO_ACCESS
            else:
                self.access = ParamTocElement.RW_ACCESS

    def get_readable_access(self):
        if (self.access == ParamTocElement.RO_ACCESS):
            return "RO"
        return "RW"


class Param():
    """
    Used to read and write parameter values in the Crazyflie.
    """

    toc = Toc()

    def __init__(self, crazyflie):
        self.cf = crazyflie
        self.param_update_callbacks = {}
        self.group_update_callbacks = {}
        self.all_update_callback = Caller()
        self.param_updater = None

        self.param_updater = _ParamUpdater(self.cf, self._param_updated)
        self.param_updater.start()

        self.cf.disconnected.add_callback(self._disconnected)

        self.all_updated = Caller()
        self.is_updated = False

        self.values = {}

    def request_update_of_all_params(self):
        """Request an update of all the parameters in the TOC"""
        for group in self.toc.toc:
            for name in self.toc.toc[group]:
                complete_name = "%s.%s" % (group, name)
                self.request_param_update(complete_name)

    def _check_if_all_updated(self):
        """Check if all parameters from the TOC has at least been fetched
        once"""
        for g in self.toc.toc:
            if g not in self.values:
                return False
            for n in self.toc.toc[g]:
                if n not in self.values[g]:
                    return False

        return True

    def _param_updated(self, pk):
        """Callback with data for an updated parameter"""
        var_id = pk.data[0]
        element = self.toc.get_element_by_id(var_id)
        if element:
            s = struct.unpack(element.pytype, pk.data[1:])[0]
            s = s.__str__()
            complete_name = "%s.%s" % (element.group, element.name)

            # Save the value for synchronous access
            if element.group not in self.values:
                self.values[element.group] = {}
            self.values[element.group][element.name] = s

            logger.debug("Updated parameter [%s]" % complete_name)
            if complete_name in self.param_update_callbacks:
                self.param_update_callbacks[complete_name].call(
                    complete_name, s)
            if element.group in self.group_update_callbacks:
                self.group_update_callbacks[element.group].call(
                    complete_name, s)
            self.all_update_callback.call(complete_name, s)

            # Once all the parameters are updated call the
            # callback for "everything updated" (after all the param
            # updated callbacks)
            if self._check_if_all_updated() and not self.is_updated:
                self.is_updated = True
                self.all_updated.call()
        else:
            logger.debug("Variable id [%d] not found in TOC", var_id)

    def remove_update_callback(self, group, name=None, cb=None):
        """Remove the supplied callback for a group or a group.name"""
        if not cb:
            return

        if not name:
            if group in self.group_update_callbacks:
                self.group_update_callbacks[group].remove_callback(cb)
        else:
            paramname = "{}.{}".format(group, name)
            if paramname in self.param_update_callbacks:
                self.param_update_callbacks[paramname].remove_callback(cb)

    def add_update_callback(self, group=None, name=None, cb=None):
        """
        Add a callback for a specific parameter name. This callback will be
        executed when a new value is read from the Crazyflie.
        """
        if not group and not name:
            self.all_update_callback.add_callback(cb)
        elif not name:
            if group not in self.group_update_callbacks:
                self.group_update_callbacks[group] = Caller()
            self.group_update_callbacks[group].add_callback(cb)
        else:
            paramname = "{}.{}".format(group, name)
            if paramname not in self.param_update_callbacks:
                self.param_update_callbacks[paramname] = Caller()
            self.param_update_callbacks[paramname].add_callback(cb)

    def refresh_toc(self, refresh_done_callback, toc_cache):
        """
        Initiate a refresh of the parameter TOC.
        """
        toc_fetcher = TocFetcher(self.cf, ParamTocElement,
                                 CRTPPort.PARAM, self.toc,
                                 refresh_done_callback, toc_cache)
        toc_fetcher.start()

    def _disconnected(self, uri):
        """Disconnected callback from Crazyflie API"""
        self.param_updater.close()
        self.is_updated = False
        # Clear all values from the previous Crazyflie
        self.toc = Toc()
        self.values = {}

    def request_param_update(self, complete_name):
        """
        Request an update of the value for the supplied parameter.
        """
        self.param_updater.request_param_update(
            self.toc.get_element_id(complete_name))

    def set_value(self, complete_name, value):
        """
        Set the value for the supplied parameter.
        """
        element = self.toc.get_element_by_complete_name(complete_name)

        if not element:
            logger.warning("Cannot set value for [%s], it's not in the TOC!",
                           complete_name)
            raise KeyError("{} not in param TOC".format(complete_name))
        elif element.access == ParamTocElement.RO_ACCESS:
            logger.debug("[%s] is read only, no trying to set value",
                         complete_name)
            raise AttributeError("{} is read-only!".format(complete_name))
        else:
            varid = element.ident
            pk = CRTPPacket()
            pk.set_header(CRTPPort.PARAM, WRITE_CHANNEL)
            pk.data = struct.pack('<B', varid)
            pk.data += struct.pack(element.pytype, eval(value))
            self.param_updater.request_param_setvalue(pk)


class _ParamUpdater(Thread):
    """This thread will update params through a queue to make sure that we
    get back values"""

    def __init__(self, cf, updated_callback):
        """Initialize the thread"""
        Thread.__init__(self)
        self.setDaemon(True)
        self.wait_lock = Lock()
        self.cf = cf
        self.updated_callback = updated_callback
        self.request_queue = Queue()
        self.cf.add_port_callback(CRTPPort.PARAM, self._new_packet_cb)
        self._should_close = False
        self._req_param = -1

    def close(self):
        # First empty the queue from all packets
        while not self.request_queue.empty():
            self.request_queue.get()
        # Then force an unlock of the mutex if we are waiting for a packet
        # we didn't get back due to a disconnect for example.
        try:
            self.wait_lock.release()
        except:
            pass

    def request_param_setvalue(self, pk):
        """Place a param set value request on the queue. When this is sent to
        the Crazyflie it will answer with the update param value. """
        self.request_queue.put(pk)

    def _new_packet_cb(self, pk):
        """Callback for newly arrived packets"""
        if pk.channel == READ_CHANNEL or pk.channel == WRITE_CHANNEL:
            var_id = pk.data[0]
            if (pk.channel != TOC_CHANNEL and self._req_param == var_id and
                    pk is not None):
                self.updated_callback(pk)
                self._req_param = -1
                try:
                    self.wait_lock.release()
                except:
                    pass

    def request_param_update(self, var_id):
        """Place a param update request on the queue"""
        pk = CRTPPacket()
        pk.set_header(CRTPPort.PARAM, READ_CHANNEL)
        pk.data = struct.pack('<B', var_id)
        logger.debug("Requesting request to update param [%d]", var_id)
        self.request_queue.put(pk)

    def run(self):
        while not self._should_close:
            pk = self.request_queue.get()  # Wait for request update
            self.wait_lock.acquire()
            if self.cf.link:
                self._req_param = pk.data[0]
                self.cf.send_packet(pk, expected_reply=(tuple(pk.data[0:2])))
            else:
                self.wait_lock.release()
