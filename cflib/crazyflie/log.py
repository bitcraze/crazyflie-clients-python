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
Enableds logging of variables from the Crazyflie.

When a Crazyflie is connected it's possible to download a TableOfContent of all
the variables that can be logged. Using this it's possible to add logging
configurations where selected variables are sent to the client at a
specified period.

"""

__author__ = 'Bitcraze AB'
__all__ = ['Log', 'LogTocElement']

import struct
from cflib.crtp.crtpstack import CRTPPacket, CRTPPort
from cflib.utils.callbacks import Caller
from .toc import Toc, TocFetcher

# Channels used for the logging port
CHAN_TOC = 0
CHAN_SETTINGS = 1
CHAN_LOGDATA = 2

# Commands used when accessing the Table of Contents
CMD_TOC_ELEMENT = 0
CMD_TOC_INFO = 1

# Commands used when accessing the Log configurations
CMD_CREATE_BLOCK = 0
CMD_APPEND_BLOCK = 1
CMD_DELETE_BLOCK = 2
CMD_START_LOGGING = 3
CMD_STOP_LOGGING = 4
CMD_RESET_LOGGING = 5

# Possible states when receiving TOC
IDLE = "IDLE"
GET_TOC_INF = "GET_TOC_INFO"
GET_TOC_ELEMENT = "GET_TOC_ELEMENT"

# The max size of a CRTP packet payload
MAX_LOG_DATA_PACKET_SIZE = 30

import logging
logger = logging.getLogger(__name__)


class LogEntry:

    blockIdCounter = 1

    def __init__(self, crazyflie, logconf):
        self.dataReceived = Caller()
        self.error = Caller()

        self.logconf = logconf
        self.blockId = LogEntry.blockIdCounter
        LogEntry.blockIdCounter += 1
        self.cf = crazyflie
        self.period = logconf.getPeriod()/10
        self.blockCreated = False

    def set_period(self, period):
        real_period = period/10  # Period set in 10th of ms
        if (real_period > 0 and real_period < 256):
            self.period = period
        else:
            logger.warning("LogEntry: Warning, period %d=>%d is not"
                           " accepted!", period, real_period)

    def start(self):
        if (self.cf.link is not None):
            if (self.blockCreated is False):
                logger.debug("First time block is started, add block")
                self.blockCreated = True
                pk = CRTPPacket()
                pk.set_header(5, CHAN_SETTINGS)
                # TODO: Fix the period!
                pk.data = (CMD_CREATE_BLOCK, self.blockId)
                for v in self.logconf.getVariables():
                    if (v.isTocVariable() is False):  # Memory location
                        logger.debug("Logging to raw memory %d, 0x%04X",
                                     v.getStoredFetchAs(), v.getAddress())
                        pk.data += struct.pack('<B', v.getStoredFetchAs())
                        pk.data += struct.pack('<I', v.getAddress())
                    else:  # Item in TOC
                        logger.debug("Adding %s with id=%d and type=0x%02X",
                                     v.getName(),
                                     self.cf.log.toc.get_element_id(
                                     v.getName()), v.getStoredFetchAs())
                        pk.data += struct.pack('<B', v.getStoredFetchAs())
                        pk.data += struct.pack('<B', self.cf.log.toc.
                                               get_element_id(v.getName()))
                logger.debug("Adding log block id {}".format(self.blockId))
                self.cf.send_packet(pk)

            else:
                logger.debug("Block already registered, starting logging"
                             " for %d", self.blockId)
                pk = CRTPPacket()
                pk.set_header(5, CHAN_SETTINGS)
                pk.data = (CMD_START_LOGGING, self.blockId, self.period)
                self.cf.send_packet(pk)

    def stop(self):
        if (self.cf.link is not None):
            if (self.blockId is None):
                logger.warning("Stopping block, but no block registered")
            else:
                logger.debug("Sending stop logging for block %d", self.blockId)
                pk = CRTPPacket()
                pk.set_header(5, CHAN_SETTINGS)
                pk.data = (CMD_STOP_LOGGING, self.blockId)
                self.cf.send_packet(pk)

    def close(self):
        if (self.cf.link is not None):
            if (self.blockId is None):
                logger.warning("Delete block, but no block registered")
            else:
                logger.debug("LogEntry: Sending delete logging for block %d"
                             % self.blockId)
                pk = CRTPPacket()
                pk.set_header(5, CHAN_SETTINGS)
                pk.data = (CMD_DELETE_BLOCK, self.blockId)
                self.cf.send_packet(pk)
                self.blockId = None  # Wait until we get confirmation of delete

    def unpack_log_data(self, logData):
        retData = {}
        dataIndex = 0
        #print len(logData)
        for v in self.logconf.getVariables():
            size = LogTocElement.get_size_from_id(v.getFetchAs())
            name = v.getName()
            unpackstring = LogTocElement.get_unpack_string_from_id(
                v.getFetchAs())
            value = struct.unpack(unpackstring,
                                  logData[dataIndex:dataIndex+size])[0]
            dataIndex += size
            retData[name] = value
        self.dataReceived.call(retData)


class LogTocElement:
    """An element in the Log TOC."""
    types = {0x01: ("uint8_t",  '<B', 1),
             0x02: ("uint16_t", '<H', 2),
             0x03: ("uint32_t", '<L', 4),
             0x04: ("int8_t",   '<b', 1),
             0x05: ("int16_t",  '<h', 2),
             0x06: ("int32_t",  '<i', 4),
             0x08: ("FP16",     '<h', 2),
             0x07: ("float",    '<f', 4)}

    @staticmethod
    def get_id_from_cstring(s):
        """Return variable type id given the C-storage name"""
        for t in LogTocElement.types.keys():
            if (LogTocElement.types[t][0] == s):
                return t
        raise KeyError("Type [%s] not found in LogTocElement.types!" % s)

    @staticmethod
    def get_cstring_from_id(ident):
        """Return the C-storage name given the variable type id"""
        try:
            return LogTocElement.types[ident][0]
        except KeyError:
            raise KeyError("Type [%d] not found in LogTocElement.types"
                           "!" % ident)

    @staticmethod
    def get_size_from_id(ident):
        """Return the size in bytes given the variable type id"""
        try:
            return LogTocElement.types[ident][2]
        except KeyError:
            raise KeyError("Type [%d] not found in LogTocElement.types"
                           "!" % ident)

    @staticmethod
    def get_unpack_string_from_id(ident):
        """Return the Python unpack string given the variable type id"""
        try:
            return LogTocElement.types[ident][1]
        except KeyError:
            raise KeyError("Type [%d] not found in LogTocElement.types"
                           "!" % ident)

    def __init__(self, data):
        """TocElement creator. Data is the binary payload of the element."""

        strs = struct.unpack("s"*len(data[2:]), data[2:])
        strs = ("{}"*len(strs)).format(*strs).split("\0")
        self.group = strs[0]
        self.name = strs[1]

        self.ident = ord(data[0])

        self.ctype = LogTocElement.get_cstring_from_id(ord(data[1]))
        self.pytype = LogTocElement.get_unpack_string_from_id(ord(data[1]))

        self.access = ord(data[1]) & 0x10


class Log():
    """Create log configuration"""

    def __init__(self, crazyflie=None):
        self.logBlocks = []

        self.cf = crazyflie

        self.cf.add_port_callback(CRTPPort.LOGGING, self._new_packet_cb)

        self.tocUpdated = Caller()
        self.state = IDLE
        self.fakeTOCCRC = 0xBABEBABA

    def create_log_packet(self, logconf):
        """Create a new log configuration"""
        size = 0
        period = logconf.getPeriod() / 10
        for v in logconf.getVariables():
            size += LogTocElement.get_size_from_id(v.getFetchAs())
            # Check that we are able to find the variable in the TOC so
            # we can return error already now and not when the config is sent
            if (v.isTocVariable()):
                if (self.toc.get_element_by_complete_name(
                        v.getName()) is None):
                    logger.warning("Log: %s not in TOC, this block cannot be"
                                   " used!", v.getName())
                    return None
        if (size <= MAX_LOG_DATA_PACKET_SIZE and period > 0 and period < 0xFF):
            block = LogEntry(self.cf, logconf)
            self.logBlocks.append(block)
            return block
        else:
            return None

    def refresh_toc(self, refreshDoneCallback):
        pk = CRTPPacket()
        pk.set_header(CRTPPort.LOGGING, CHAN_SETTINGS)
        pk.data = (CMD_RESET_LOGGING, )
        self.cf.send_packet(pk)

        self.toc = Toc()
        tocFetcher = TocFetcher(self.cf, LogTocElement, CRTPPort.LOGGING,
                                self.toc, refreshDoneCallback)
        tocFetcher.start()

    def _new_packet_cb(self, packet):
        chan = packet.channel
        cmd = packet.datal[0]
        payload = struct.pack("B"*(len(packet.datal)-1), *packet.datal[1:])

        if (chan == CHAN_SETTINGS):
            newBlockId = ord(payload[0])
            errorStatus = ord(payload[1])
            if (cmd == CMD_CREATE_BLOCK):
                block = None
                for b in self.logBlocks:
                    if (b.blockId == newBlockId):
                        block = b
                if (block is not None):
                    if (errorStatus == 0):  # No error
                        logger.debug("Have successfully added blockId=%d",
                                     newBlockId)

                        pk = CRTPPacket()
                        pk.set_header(5, CHAN_SETTINGS)
                        pk.data = (CMD_START_LOGGING, newBlockId, 10)
                        self.cf.send_packet(pk)
                    else:
                        logger.warning("Error when adding blockId=%d, should"
                                       " tell listenders...", newBlockId)

                else:
                    logger.warning("No LogEntry to assign block to !!!")
            if (cmd == CMD_START_LOGGING):
                if (errorStatus == 0x00):
                    logger.info("Have successfully logging for block=%d",
                                newBlockId)
                else:
                    logger.warning("Error=%d when starting logging for "
                                   "block=%d", errorStatus, newBlockId)
        if (chan == CHAN_LOGDATA):
            chan = packet.channel
            blockId = ord(packet.data[0])
            # timestamp = packet.data[0:4] # Not currently used
            logdata = packet.data[4:]
            block = None
            for b in self.logBlocks:
                if (b.blockId == blockId):
                    block = b
            if (block is not None):
                block.unpack_log_data(logdata)
            else:
                logger.warning("Error no LogEntry to handle block=%d", blockId)
