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
import errno
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


class LogEntry(object):
    """Representation of one log configuration that enables logging
    from the Crazyflie"""
    block_idCounter = 1

    def __init__(self, crazyflie, logconf):
        """Initialize the entry"""
        self.data_received = Caller()
        self.error = Caller()
        self.started_cb = Caller()
        self.added_cb = Caller()
        self.err_no = 0

        self.logconf = logconf
        self.block_id = LogEntry.block_idCounter
        LogEntry.block_idCounter += 1 % 255
        self.cf = crazyflie
        self.period = logconf.getPeriod() / 10
        self.period_in_ms = logconf.getPeriod()
        self._added = False
        self._started = False

    def _set_added(self, added):
        self._added = added
        self.added_cb.call(added)

    def _get_added(self):
        return self._added

    def _set_started(self, started):
        self._started = started
        self.started_cb.call(started)

    def _get_started(self):
        return self._started

    added = property(_get_added, _set_added)
    started = property(_get_started, _set_started)

    def start(self):
        """Start the logging for this entry"""
        if (self.cf.link is not None):
            if (self._added is False):
                logger.debug("First time block is started, add block")
                pk = CRTPPacket()
                pk.set_header(5, CHAN_SETTINGS)
                pk.data = (CMD_CREATE_BLOCK, self.block_id)
                for var in self.logconf.getVariables():
                    if (var.isTocVariable() is False):  # Memory location
                        logger.debug("Logging to raw memory %d, 0x%04X",
                                     var.getStoredFetchAs(), var.getAddress())
                        pk.data += struct.pack('<B', var.getStoredFetchAs())
                        pk.data += struct.pack('<I', var.getAddress())
                    else:  # Item in TOC
                        logger.debug("Adding %s with id=%d and type=0x%02X",
                                     var.getName(),
                                     self.cf.log.toc.get_element_id(
                                     var.getName()), var.getStoredFetchAs())
                        pk.data += struct.pack('<B', var.getStoredFetchAs())
                        pk.data += struct.pack('<B', self.cf.log.toc.
                                               get_element_id(var.getName()))
                logger.debug("Adding log block id {}".format(self.block_id))
                self.cf.send_packet(pk)

            else:
                logger.debug("Block already registered, starting logging"
                             " for %d", self.block_id)
                pk = CRTPPacket()
                pk.set_header(5, CHAN_SETTINGS)
                pk.data = (CMD_START_LOGGING, self.block_id, self.period)
                self.cf.send_packet(pk)

    def stop(self):
        """Stop the logging for this entry"""
        if (self.cf.link is not None):
            if (self.block_id is None):
                logger.warning("Stopping block, but no block registered")
            else:
                logger.debug("Sending stop logging for block %d", self.block_id)
                pk = CRTPPacket()
                pk.set_header(5, CHAN_SETTINGS)
                pk.data = (CMD_STOP_LOGGING, self.block_id)
                self.cf.send_packet(pk)

    def close(self):
        """Delete this entry in the Crazyflie"""
        if (self.cf.link is not None):
            if (self.block_id is None):
                logger.warning("Delete block, but no block registered")
            else:
                logger.debug("LogEntry: Sending delete logging for block %d"
                             % self.block_id)
                pk = CRTPPacket()
                pk.set_header(5, CHAN_SETTINGS)
                pk.data = (CMD_DELETE_BLOCK, self.block_id)
                self.cf.send_packet(pk)
                self.block_id = None  # Wait until we get confirmation of delete

    def unpack_log_data(self, log_data, timestamp):
        """Unpack received logging data so it represent real values according
        to the configuration in the entry"""
        ret_data = {}
        data_index = 0
        for var in self.logconf.getVariables():
            size = LogTocElement.get_size_from_id(var.getFetchAs())
            name = var.getName()
            unpackstring = LogTocElement.get_unpack_string_from_id(
                var.getFetchAs())
            value = struct.unpack(unpackstring,
                                  log_data[data_index:data_index + size])[0]
            data_index += size
            ret_data[name] = value
        self.data_received.call(ret_data, timestamp)


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
    def get_id_from_cstring(name):
        """Return variable type id given the C-storage name"""
        for key in LogTocElement.types.keys():
            if (LogTocElement.types[key][0] == name):
                return key
        raise KeyError("Type [%s] not found in LogTocElement.types!" % name)

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

    def __init__(self, data=None):
        """TocElement creator. Data is the binary payload of the element."""

        if (data):
            strs = struct.unpack("s" * len(data[2:]), data[2:])
            strs = ("{}" * len(strs)).format(*strs).split("\0")
            self.group = strs[0]
            self.name = strs[1]

            self.ident = ord(data[0])

            self.ctype = LogTocElement.get_cstring_from_id(ord(data[1]))
            self.pytype = LogTocElement.get_unpack_string_from_id(ord(data[1]))

            self.access = ord(data[1]) & 0x10


class Log():
    """Create log configuration"""

    # These codes can be decoded using os.stderror, but
    # some of the text messages will look very stange
    # in the UI, so they are redefined here
    _err_codes = {
            errno.ENOMEM: "No more memory available",
            errno.ENOEXEC: "Command not found",
            errno.ENOENT: "No such block id",
            errno.E2BIG: "Block too large"
            }

    def __init__(self, crazyflie=None):
        self.log_blocks = []
        # Called with newly created blocks
        self.block_added_cb = Caller()

        self.cf = crazyflie
        self.toc = None
        self.cf.add_port_callback(CRTPPort.LOGGING, self._new_packet_cb)

        self.toc_updated = Caller()
        self.state = IDLE
        self.fake_toc_crc = 0xDEADBEEF

    def create_log_packet(self, logconf):
        """Create a new log configuration"""
        size = 0
        period = logconf.getPeriod() / 10
        for var in logconf.getVariables():
            size += LogTocElement.get_size_from_id(var.getFetchAs())
            # Check that we are able to find the variable in the TOC so
            # we can return error already now and not when the config is sent
            if (var.isTocVariable()):
                if (self.toc.get_element_by_complete_name(
                        var.getName()) is None):
                    logger.warning("Log: %s not in TOC, this block cannot be"
                                   " used!", var.getName())
                    return None
        if (size <= MAX_LOG_DATA_PACKET_SIZE and period > 0 and period < 0xFF):
            block = LogEntry(self.cf, logconf)
            self.log_blocks.append(block)
            self.block_added_cb.call(block)
            return block
        else:
            return None

    def refresh_toc(self, refresh_done_callback, toc_cache):
        """Start refreshing the table of loggale variables"""
        pk = CRTPPacket()
        pk.set_header(CRTPPort.LOGGING, CHAN_SETTINGS)
        pk.data = (CMD_RESET_LOGGING, )
        self.cf.send_packet(pk)

        self.log_blocks = []

        self.toc = Toc()
        toc_fetcher = TocFetcher(self.cf, LogTocElement, CRTPPort.LOGGING,
                                self.toc, refresh_done_callback, toc_cache)
        toc_fetcher.start()

    def _find_block(self, block_id):
        for block in self.log_blocks:
            if block.block_id == block_id:
                return block
        return None

    def _new_packet_cb(self, packet):
        """Callback for newly arrived packets with TOC information"""
        chan = packet.channel
        cmd = packet.datal[0]
        payload = struct.pack("B" * (len(packet.datal) - 1), *packet.datal[1:])

        if (chan == CHAN_SETTINGS):
            block_id = ord(payload[0])
            error_status = ord(payload[1])
            block = self._find_block(block_id)
            if (cmd == CMD_CREATE_BLOCK):
                if (block is not None):
                    if (error_status == 0):  # No error
                        logger.debug("Have successfully added block_id=%d",
                                     block_id)

                        pk = CRTPPacket()
                        pk.set_header(5, CHAN_SETTINGS)
                        pk.data = (CMD_START_LOGGING, block_id,
                                   block.period)
                        self.cf.send_packet(pk)
                        block.added = True
                    else:
                        msg = self._err_codes[error_status]
                        logger.warning("Error %d when adding block_id=%d (%s)"
                                       , error_status, block_id, msg)
                        block.err_no = error_status
                        block.added_cb.call(False)
                        block.error.call(block.logconf, msg)

                else:
                    logger.warning("No LogEntry to assign block to !!!")
            if (cmd == CMD_START_LOGGING):
                if (error_status == 0x00):
                    logger.info("Have successfully started logging for block=%d",
                                block_id)
                    if block:
                        block.started = True

                else:
                    msg = self._err_codes[error_status]
                    logger.warning("Error %d when starting block_id=%d (%s)"
                                   , error_status, new_block_id, msg)
                    if block:
                        block.err_no = error_status
                        block.started_cb.call(False)
                        block.error.call(block.logconf, msg)

            if (cmd == CMD_STOP_LOGGING):
                if (error_status == 0x00):
                    logger.info("Have successfully stopped logging for block=%d",
                                block_id)
                    if block:
                        block.started = False

        if (chan == CHAN_LOGDATA):
            chan = packet.channel
            block_id = packet.datal[0]
            block = self._find_block(block_id)
            timestamps = struct.unpack("<BBB", packet.data[1:4])
            timestamp = (timestamps[0] | timestamps[1] << 8 | timestamps[2] << 16)
            logdata = packet.data[4:]
            if (block is not None):
                block.unpack_log_data(logdata, timestamp)
            else:
                logger.warning("Error no LogEntry to handle block=%d", block_id)
