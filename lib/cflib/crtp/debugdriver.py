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
Fake link driver used to debug the UI without using the Crazyflie.

The operation of this driver can be controlled in two ways, either by
connecting to different URIs or by sending messages to the DebugDriver port
though CRTP once connected.

For normal connections a console thread is also started that will send
generated console output via CRTP.
"""

__author__ = 'Bitcraze AB'
__all__ = ['DebugDriver']

from threading import Thread
from .crtpdriver import CRTPDriver
from .crtpstack import CRTPPacket, CRTPPort
from .exceptions import WrongUriType
import Queue
import re
import time
import struct
from datetime import datetime
from cflib.crazyflie.log import LogTocElement
from cflib.crazyflie.param import ParamTocElement

import logging
logger = logging.getLogger(__name__)

# This setup is used to debug raw memory logging
memlogging = {0x01: {"min": 0, "max": 255, "mod": 1, "vartype": 1},
              0x02: {"min": 0, "max": 65000, "mod": 100, "vartype": 2},
              0x03: {"min": 0, "max": 100000, "mod": 1000, "vartype": 3},
              0x04: {"min": -100, "max": 100, "mod": 1, "vartype": 4},
              0x05: {"min": -10000, "max": 10000, "mod": 2000, "vartype": 5},
              0x06: {"min": -50000, "max": 50000, "mod": 1000, "vartype": 6},
              0x07: {"min": 0, "max": 255, "mod": 1, "vartype": 1}}


class DebugDriver (CRTPDriver):
    """ Debug driver used for debugging UI/communication without using a
    Crazyflie"""
    def __init__(self):
        self.fakeLoggingThreads = []
        # Fill up the fake logging TOC with values and data
        self.fakeLogToc = []
        self.fakeLogToc.append({"varid": 0, "vartype": 5, "vargroup": "imu",
                                "varname": "gyro_x", "min": -10000,
                                "max": 10000, "mod": 1000})
        self.fakeLogToc.append({"varid": 1, "vartype": 5, "vargroup": "imu",
                                "varname": "gyro_y", "min": -10000,
                                "max": 10000, "mod": 150})
        self.fakeLogToc.append({"varid": 2, "vartype": 5, "vargroup": "imu",
                                "varname": "gyro_z", "min": -10000,
                                "max": 10000, "mod": 200})
        self.fakeLogToc.append({"varid": 3, "vartype": 5, "vargroup": "imu",
                                "varname": "acc_x", "min": -1000,
                                "max": 1000, "mod": 15})
        self.fakeLogToc.append({"varid": 4, "vartype": 5, "vargroup": "imu",
                                "varname": "acc_y", "min": -1000,
                                "max": 1000, "mod": 10})
        self.fakeLogToc.append({"varid": 5, "vartype": 5, "vargroup": "imu",
                                "varname": "acc_z", "min": -1000,
                                "max": 1000, "mod": 20})
        self.fakeLogToc.append({"varid": 6, "vartype": 7,
                                "vargroup": "stabilizer", "varname": "roll",
                                "min": -90, "max": 90, "mod": 2})
        self.fakeLogToc.append({"varid": 7, "vartype": 7,
                                "vargroup": "stabilizer", "varname": "pitch",
                                "min": -90, "max": 90, "mod": 1.5})
        self.fakeLogToc.append({"varid": 8, "vartype": 7,
                                "vargroup": "stabilizer", "varname": "yaw",
                                "min": -90, "max": 90, "mod": 2.5})
        self.fakeLogToc.append({"varid": 9, "vartype": 7, "vargroup": "pm",
                                "varname": "vbat", "min": 3.0,
                                "max": 4.0, "mod": 0.1})
        self.fakeLogToc.append({"varid": 10, "vartype": 6, "vargroup": "motor",
                                "varname": "m1", "min": 0, "max": 65000,
                                "mod": 1000})
        self.fakeLogToc.append({"varid": 11, "vartype": 6, "vargroup": "motor",
                                "varname": "m2", "min": 0, "max": 65000,
                                "mod": 1000})
        self.fakeLogToc.append({"varid": 12, "vartype": 6, "vargroup": "motor",
                                "varname": "m3", "min": 0, "max": 65000,
                                "mod": 1000})
        self.fakeLogToc.append({"varid": 13, "vartype": 6, "vargroup": "motor",
                                "varname": "m4", "min": 0, "max": 65000,
                                "mod": 1000})
        self.fakeLogToc.append({"varid": 14, "vartype": 2,
                                "vargroup": "stabilizer", "varname": "thrust",
                                "min": 0, "max": 65000, "mod": 1000})

        # Fill up the fake logging TOC with values and data
        self.fakeParamToc = []
        self.fakeParamToc.append({"varid": 0, "vartype": 0x08,
                                  "vargroup": "blah", "varname": "p",
                                  "writable": True, "value": 100})
        self.fakeParamToc.append({"varid": 1, "vartype": 0x0A,
                                  "vargroup": "info", "varname": "cid",
                                  "writable": False, "value": 1234})
        self.fakeParamToc.append({"varid": 2, "vartype": 0x06,
                                  "vargroup": "rpid", "varname": "prp",
                                  "writable": True, "value": 1.5})
        self.fakeParamToc.append({"varid": 3, "vartype": 0x06,
                                  "vargroup": "rpid", "varname": "pyaw",
                                  "writable": True, "value": 2.5})
        self.fakeParamToc.append({"varid": 4, "vartype": 0x06,
                                  "vargroup": "rpid", "varname": "irp",
                                  "writable": True, "value": 3.5})
        self.fakeParamToc.append({"varid": 5, "vartype": 0x06,
                                  "vargroup": "rpid", "varname": "iyaw",
                                  "writable": True, "value": 4.5})
        self.fakeParamToc.append({"varid": 6, "vartype": 0x06,
                                  "vargroup": "rpid", "varname": "drp",
                                  "writable": True, "value": 5.5})
        self.fakeParamToc.append({"varid": 7, "vartype": 0x06,
                                  "vargroup": "rpid", "varname": "dyaw",
                                  "writable": True, "value": 6.5})
        self.fakeParamToc.append({"varid": 8, "vartype": 0x06,
                                  "vargroup": "apid", "varname": "prp",
                                  "writable": True, "value": 7.5})
        self.fakeParamToc.append({"varid": 9, "vartype": 0x06,
                                  "vargroup": "apid", "varname": "pyaw",
                                  "writable": True, "value": 8.5})
        self.fakeParamToc.append({"varid": 10, "vartype": 0x06,
                                  "vargroup": "apid", "varname": "irp",
                                  "writable": True, "value": 9.5})
        self.fakeParamToc.append({"varid": 11, "vartype": 0x06,
                                  "vargroup": "apid", "varname": "iyaw",
                                  "writable": True, "value": 10.5})
        self.fakeParamToc.append({"varid": 12, "vartype": 0x06,
                                  "vargroup": "apid", "varname": "drp",
                                  "writable": True, "value": 11.5})
        self.fakeParamToc.append({"varid": 13, "vartype": 0x06,
                                  "vargroup": "apid", "varname": "dyaw",
                                  "writable": True, "value": 12.5})
        self.fakeParamToc.append({"varid": 14, "vartype": 0x08,
                                  "vargroup": "flightctrl",
                                  "varname": "xmode", "writable": True,
                                  "value": 1})
        self.fakeParamToc.append({"varid": 15, "vartype": 0x08,
                                  "vargroup": "flightctrl",
                                  "varname": "ratepid", "writable": True,
                                  "value": 1})

        self.fakeflash = {}

    def scan_interface(self):
        return [["debug://0/0", "Normal connect"],
                ["debug://0/1", "Don't send anything back"],
                ["debug://0/2", "Incomplete Log TOC"]]

    def connect(self, uri, linkQualityCallback, linkErrorCallback):

        if not re.search("^debug://", uri):
            raise WrongUriType("Not a debug URI")

        self.queue = Queue.Queue()

        self.linkErrorCallback = linkErrorCallback
        self.linkQualityCallback = linkQualityCallback

        # Debug-options for this driver that
        # is set by using different connection URIs
        self.inhibitAnswers = False
        self.doIncompleteLogTOC = False
        self.bootloader = False

        if (re.search("^debug://.*/1\Z", uri)):
            self.inhibitAnswers = True
        if (re.search("^debug://.*/110\Z", uri)):
            self.bootloader = True
        if (re.search("^debug://.*/2\Z", uri)):
            self.doIncompleteLogTOC = True

        if (self.inhibitAnswers is False and self.bootloader is False):
            self.fakeConsoleThread = FakeConsoleThread(self.queue)
            self.fakeConsoleThread.start()

        if (self.linkQualityCallback is not None):
            self.linkQualityCallback(0)

        self.nowAnswerCounter = 4

    def receive_packet(self, time=0):
        if time == 0:
            try:
                return self.queue.get(False)
            except Queue.Empty:
                return None
        elif time < 0:
            try:
                return self.queue.get(True)
            except Queue.Empty:
                return None
        else:
            try:
                return self.queue.get(True, time)
            except Queue.Empty:
                return None

    def send_packet(self, pk):
        if (self.inhibitAnswers):
            self.nowAnswerCounter = self.nowAnswerCounter - 1
            logger.debug("Not answering with any data, will send link errori"
                         " in %d retries", self.nowAnswerCounter)
            if (self.nowAnswerCounter == 0):
                self.linkErrorCallback("Nothing is answering, and it"
                                       " shouldn't")
            return

        if (pk.port == 0xFF):
            self._handle_bootloader(pk)
        elif (pk.port == CRTPPort.DEBUGDRIVER):
            self._handle_debugmessage(pk)
        elif (pk.port == CRTPPort.COMMANDER):
            pass
        elif (pk.port == CRTPPort.LOGGING):
            self._handle_logging(pk)
        elif (pk.port == CRTPPort.PARAM):
            self.handleParam(pk)
        else:
            logger.warning("Not handling incomming packets on port [%d]",
                           pk.port)

    def _handle_bootloader(self, pk):
        cmd = pk.datal[1]
        if (cmd == 0x10):  # Request info about copter
            p = CRTPPacket()
            p.set_header(0xFF, 0xFF)
            pageSize = 1024
            buffPages = 10
            flashPages = 100
            flashStart = 1
            p.data = struct.pack('<BBHHHH', 0xFF, 0x10, pageSize, buffPages,
                                 flashPages, flashStart)
            p.data += struct.pack('B'*12, 0xA0A1A2A3A4A5)
            self.queue.put(p)
            logging.info("Bootloader: Sending info back info")
        elif (cmd == 0x14):  # Upload buffer
            [page, addr] = struct.unpack('<HH', p.data[0:4])
        elif (cmd == 0x18):  # Flash page
            p = CRTPPacket()
            p.set_header(0xFF, 0xFF)
            p.data = struct.pack('<BBH', 0xFF, 0x18, 1)
            self.queue.put(p)
        elif (cmd == 0xFF):  # Reset to firmware
            logger.info("Bootloader: Got reset command")
        else:
            logger.warning("Bootloader: Unknown command 0x%02X", cmd)

    def _handle_debugmessage(self, pk):
        if (pk.channel == 0):
            cmd = struct.unpack("B", pk.data[0])[0]
            if (cmd == 0):  # Fake link quality
                newLinkQuality = struct.unpack("B", pk.data[1])[0]
                self.linkQualityCallback(newLinkQuality)
            elif (cmd == 1):
                self.linkErrorCallback("DebugDriver was forced to disconnect!")
            else:
                logger.warning("Debug port: Not handling cmd=%d on channel 0",
                               cmd)
        else:
            logger.warning("Debug port: Not handling channel=%d",
                           pk.channel)

    def _handle_toc_access(self, pk):
        chan = pk.channel
        cmd = struct.unpack("B", pk.data[0])[0]
        logger.info("TOC access on port %d", pk.port)
        if (chan == 0):  # TOC Access
            cmd = struct.unpack("B", pk.data[0])[0]
            if (cmd == 0):  # Reqest variable info
                p = CRTPPacket()
                p.set_header(pk.port, 0)
                varIndex = 0
                if (len(pk.data) > 1):
                    varIndex = struct.unpack("B", pk.data[1])[0]
                    logger.debug("TOC[%d]: Requesting ID=%d", pk.port,
                                 varIndex)
                else:
                    logger.debug("TOC[%d]: Requesting first index..surprise,"
                                 " it 0 !", pk.port)

                if (pk.port == CRTPPort.LOGGING):
                    l = self.fakeLogToc[varIndex]
                if (pk.port == CRTPPort.PARAM):
                    l = self.fakeParamToc[varIndex]

                vartype = l["vartype"]
                if (pk.port == CRTPPort.PARAM and l["writable"] is True):
                    vartype = vartype | (0x10)

                p.data = struct.pack("<BBB", cmd, l["varid"], vartype)
                for ch in l["vargroup"]:
                    p.data += ch
                p.data += '\0'
                for ch in l["varname"]:
                    p.data += ch
                p.data += '\0'
                if (self.doIncompleteLogTOC is False):
                    self.queue.put(p)
                elif (varIndex < 5):
                    self.queue.put(p)
                else:
                    logger.info("TOC: Doing incomplete TOC, stopping after"
                                " varIndex => 5")

            if (cmd == 1):  # TOC CRC32 request
                if (pk.port == CRTPPort.LOGGING):
                    tocLen = len(self.fakeLogToc)
                if (pk.port == CRTPPort.PARAM):
                    tocLen = len(self.fakeParamToc)
                logger.info("TOC[%d]: Requesting TOC CRC, sending back fake"
                            " stuff: %d", pk.port, len(self.fakeLogToc))
                p = CRTPPacket()
                p.set_header(pk.port, 0)
                p.data = struct.pack('<BBIBB', 1, tocLen, 0xBCCFBCCF, 16, 24)
                self.queue.put(p)

    def handleParam(self, pk):
        chan = pk.channel
        cmd = struct.unpack("B", pk.data[0])[0]
        logger.debug("PARAM: Port=%d, Chan=%d, cmd=%d", pk.port,
                     chan, cmd)
        if (chan == 0):  # TOC Access
            self._handle_toc_access(pk)
        elif (chan == 2):  # Settings access
            varId = pk.datal[0]
            formatStr = ParamTocElement.types[self.fakeParamToc
                                              [varId]["vartype"]][1]
            newvalue = struct.unpack(formatStr, pk.data[1:])[0]
            self.fakeParamToc[varId]["value"] = newvalue
            logger.info("PARAM: New value [%s] for param [%d]", newvalue,
                        varId)
            # Send back the new value
            p = CRTPPacket()
            p.set_header(pk.port, 2)
            p.data += struct.pack("<B", varId)
            p.data += struct.pack(formatStr, self.fakeParamToc[varId]["value"])
            self.queue.put(p)
        elif (chan == 1):
            p = CRTPPacket()
            p.set_header(pk.port, 2)
            varId = cmd
            p.data += struct.pack("<B", varId)
            formatStr = ParamTocElement.types[self.fakeParamToc
                                              [varId]["vartype"]][1]
            p.data += struct.pack(formatStr, self.fakeParamToc[varId]["value"])
            logger.info("PARAM: Getting value for %d", varId)
            self.queue.put(p)

    def _handle_logging(self, pk):
        chan = pk.channel
        cmd = struct.unpack("B", pk.data[0])[0]
        logger.debug("LOG: Chan=%d, cmd=%d", chan, cmd)
        if (chan == 0):  # TOC Access
            self._handle_toc_access(pk)
        elif (chan == 1):  # Settings access
            if (cmd == 0):
                blockId = ord(pk.data[1])
                period = ord(pk.data[2])*10  # Sent as multiple of 10ms
                logger.info("LOG:Adding block id=%d, period=%d",
                            blockId, period)
                listofvars = pk.data[3:]

                fakeThread = _FakeLoggingDataThread(self.queue, blockId,
                                                    period, listofvars,
                                                    self.fakeLogToc)
                self.fakeLoggingThreads.append(fakeThread)
                fakeThread.start()
                # Anser that everything is ok
                p = CRTPPacket()
                p.set_header(5, 1)
                p.data = struct.pack('<BBB', 0, blockId, 0x00)
                self.queue.put(p)
            if (cmd == 1):
                logger.warning("LOG: Appending block not implemented!")
            if (cmd == 2):
                logger.info("LOG: Should delete block %d", blockId)
                success = False
                for fb in self.fakeLoggingThreads:
                    if (fb.blockId == blockId):
                        fb._disable_logging()
                        fb.quit()

                        p = CRTPPacket()
                        p.set_header(5, 1)
                        p.data = struct.pack('<BBB', cmd, blockId, 0x00)
                        self.queue.put(p)
                        logger.info("LOG: Deleted block=%d", blockId)
                        success = True
                if (success is False):
                    logger.warning("LOG: Could not delete block=%d, not found",
                                   blockId)
                    # TODO: Send back error code

            if (cmd == 3):
                blockId = ord(pk.data[1])
                logger.info("LOG:Starting block %d", blockId)
                success = False
                for fb in self.fakeLoggingThreads:
                    if (fb.blockId == blockId):
                        fb._enable_logging()
                        p = CRTPPacket()
                        p.set_header(5, 1)
                        p.data = struct.pack('<BBB', cmd, blockId, 0x00)
                        self.queue.put(p)
                        logger.info("LOG:Started block=%d", blockId)
                        success = True
                if (success is False):
                    logger.info("LOG:Could not start block=%d, not found",
                                blockId)
                    # TODO: Send back error code
            if (cmd == 4):
                blockId = ord(pk.data[1])
                logger.info("LOG:Pausing block %d", blockId)
                success = False
                for fb in self.fakeLoggingThreads:
                    if (fb.blockId == blockId):
                        fb._disable_logging()
                        p = CRTPPacket()
                        p.set_header(5, 1)
                        p.data = struct.pack('<BBB', cmd, blockId, 0x00)
                        self.queue.put(p)
                        logger.info("LOG:Pause block=%d", blockId)
                        success = True
                if (success is False):
                    logger.warning("LOG:Could not pause block=%d, not found",
                                   blockId)
                    # TODO: Send back error code
        elif (chan > 1):
            logger.warning("LOG: Uplink packets with channes > 1 not"
                           " supported!")


class _FakeLoggingDataThread (Thread):
    """Thread that will send back fake logging data via CRTP"""

    def __init__(self, outQueue, blockId, period, listofvars, fakeLogToc):
        Thread.__init__(self)
        self.outQueue = outQueue
        self.setDaemon(True)
        self.mod = 0
        self.blockId = blockId
        self.period = period
        self.listofvars = listofvars
        self.shouldLog = False
        self.fakeLogToc = fakeLogToc
        self.fakeLoggingData = []
        self.setName("Fakelog block=%d" % blockId)
        self.shouldQuit = False

        logging.info("FakeDataLoggingThread created for blockid=%d with"
                     " period=%d", blockId, period)
        i = 0
        while (i < len(listofvars)):
            varType = ord(listofvars[i])
            var_stored_as = (varType >> 4)
            var_fetch_as = (varType & 0xF)
            if (var_stored_as > 0):
                addr = struct.unpack("<I", listofvars[i+1:i+5])
                logger.debug("FakeLoggingThread: We should log a memory addr"
                             " 0x%04X", addr)
                self.fakeLoggingData.append([memlogging[var_fetch_as],
                                            memlogging[var_fetch_as]["min"],
                                            1])
                i = i + 5
            else:
                varId = ord(listofvars[i])
                logger.debug("FakeLoggingThread: We sould log variable from"
                             " TOC: id=%d, type=0x%02X", varId, varType)
                for t in self.fakeLogToc:
                    if (varId == t["varid"]):
                        # Each touple will have var data and current fake value
                        self.fakeLoggingData.append([t, t["min"], 1])
                i = i + 2

    def _enable_logging(self):
        self.shouldLog = True
        logging.info("_FakeLoggingDataThread: Enable thread [%s]",
                     self.getName())

    def _disable_logging(self):
        self.shouldLog = False
        logging.info("_FakeLoggingDataThread: Disable thread [%s]",
                     self.getName())

    def quit(self):
        self.shouldQuit = True

    def run(self):
        while(self.shouldQuit is False):
            if (self.shouldLog is True):

                p = CRTPPacket()
                p.set_header(5, 2)
                p.data = struct.pack('<B',  self.blockId)
                p.data += struct.pack('BBB', 0, 0, 0)  # Timestamp

                for d in self.fakeLoggingData:
                    # Set new value
                    d[1] = d[1] + d[0]["mod"]*d[2]
                    # Obej the limitations
                    if (d[1] > d[0]["max"]):
                        d[1] = d[0]["max"]  # Limit value
                        d[2] = -1  # Switch direction
                    if (d[1] < d[0]["min"]):
                        d[1] = d[0]["min"]  # Limit value
                        d[2] = 1  # Switch direction
                    # Pack value
                    formatStr = LogTocElement.types[d[0]["vartype"]][1]
                    p.data += struct.pack(formatStr, d[1])
                self.outQueue.put(p)
            time.sleep(self.period/1000.0)  # Period in ms here


class FakeConsoleThread (Thread):
    """Thread that will send back fake console data via CRTP"""
    def __init__(self, outQueue):
        Thread.__init__(self)
        self.outQueue = outQueue
        self.setDaemon(True)

    def run(self):
        while(True):
            p = CRTPPacket()
            p.set_header(0, 0)

            message = "Time is now %s\n" % datetime.now()

            us = "%is" % len(message)
            # This might be done prettier ;-)
            p.data = struct.pack(us, message)

            self.outQueue.put(p)
            time.sleep(2)
