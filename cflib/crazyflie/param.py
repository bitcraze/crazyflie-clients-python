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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
Enableds reading/writing of parameter values to/from the Crazyflie.

When a Crazyflie is connected it's possible to download a TableOfContent of all
the parameters that can be written/read.

"""

__author__ = 'Bitcraze AB'
__all__ = ['Param', 'ParamTocElement']

from cflib.utils.callbacks import Caller
import cflib.crtp
import struct
from cflib.crtp.crtpstack import CRTPPacket, CRTPPort
from .toc import Toc, TocFetcher, TocElement

from threading import Thread

from Queue import Queue

import logging
logger = logging.getLogger(__name__)

#Possible states
IDLE       = 0
WAIT_TOC   = 1
WAIT_READ  = 2
WAIT_WRITE = 3

TOC_CHANNEL   = 0
READ_CHANNEL  = 1
WRITE_CHANNEL = 2

# TOC access command
TOC_RESET    = 0
TOC_GETNEXT  = 1
TOC_GETCRC32 = 2


# One element entry in the TOC
class ParamTocElement:
    """An element in the Log TOC."""
    
    RW_ACCESS = 0
    RO_ACCESS = 1
    
    types = { 0x08: ("uint8_t",  '<B'),
        0x09: ("uint16_t", '<H'),
        0x0A: ("uint32_t", '<L'),
        0x0B: ("uint64_t", '<Q'),
        0x00: ("int8_t",   '<b'),
        0x01: ("int16_t",  '<h'),
        0x02: ("int32_t",  '<i'),
        0x03: ("int64_t",  '<q'),
        0x05: ("FP16",     ''),
        0x06: ("float",    '<f'),
        0x07: ("double",   '<d'),
    }

    def __init__(self, data):
        """TocElement creator. Data is the binary payload of the element."""
        element = TocElement()

        strs = struct.unpack("s"*len(data[2:]), data[2:])
        strs = ("{}"*len(strs)).format(*strs).split("\0")
        self.group = strs[0]
        self.name = strs[1]
        
        self.ident = ord(data[0])

        
        self.ctype = self.types[ord(data[1])&0x0F][0]
        self.pytype = self.types[ord(data[1])&0x0F][1]
        
        self.access = ord(data[1])&0x10

class Param():
    """
    Used to read and write parameter values in the Crazyflie.
    """
    
    toc = Toc()

    def __init__(self, crazyflie):
        self.cf = crazyflie
        self.paramUpdateCallbacks = {}
        self.paramUpdater = ParamUpdater(self.cf, self.paramUpdated)
        self.paramUpdater.start()


    def paramUpdated(self, pk):
        varId = pk.datal[0]
        element = self.toc.getByIdent(varId)
        s = struct.unpack(element.pytype, pk.data[1:])[0]
        s = s.__str__()
        completeName = "%s.%s" % (element.group, element.name)
        cb = self.paramUpdateCallbacks[completeName]
        cb.call(completeName, s)

    def addParamUpdateCallback(self, paramname, cb):
        """
        Add a callback for a specific parameter name. This callback will be executed when
        a new value is read from the Crazyflie.
        """
        if ((paramname in self.paramUpdateCallbacks) == False):
            self.paramUpdateCallbacks[paramname] = Caller()

        self.paramUpdateCallbacks[paramname].addCallback(cb)

    def refreshTOC(self, refreshDoneCallback):
        """
        Initiate a refresh of the parameter TOC.
        """
        self.toc = Toc()
        tocFetcher = TocFetcher(self.cf, ParamTocElement,
                                CRTPPort.PARAM, self.toc, refreshDoneCallback)
        tocFetcher.getToc()

    def requestParamUpdate(self, completeName):
        """
        Request an update of the value for the supplied parameter.
        """
        self.paramUpdater.requestParamUpdate(self.toc.getElementId(completeName))

    def setParamValue(self, completeName, value):
        """
        Set the value for the supplied parameter.
        """
        element = self.toc.getByCompleteName(completeName)
        if (element != None):
            varid = element.ident
            pk = CRTPPacket()
            pk.setHeader(CRTPPort.PARAM, WRITE_CHANNEL);
            pk.data = struct.pack('<B',varid)
            pk.data += struct.pack(element.pytype, eval(value))
            self.cf.sendLinkPacket(pk, expectAnswer = True)
        else:
            logger.warning("Cannot set value for [%s], it's not in the TOC!", completeName)

class ParamUpdater(Thread):
    def __init__(self, cf, updatedCallback):
        Thread.__init__(self)
        self.setDaemon(True)
        self.cf = cf
        self.updatedCallback = updatedCallback
        self.requestQueue = Queue()
        self.incommingQueue = Queue()
        self.cf.incomming.addPortCallback(CRTPPort.PARAM, self.incomming)

    def incomming(self, pk):
        if (pk.getChannel() != TOC_CHANNEL):    
            self.updatedCallback(pk)
            self.incommingQueue.put(0) # Don't care what we put, used to sync

    def addUpdateRequest(self, varid):
        self.requestQueue.put(varid)
    
    def requestParamUpdate(self, varid):
        logger.debug("Requesting update for varid %d", varid)
        pk = CRTPPacket()
        pk.setHeader(CRTPPort.PARAM, READ_CHANNEL);
        pk.data = struct.pack('<B',varid)
        self.cf.sendLinkPacket(pk, expectAnswer = True)

    def run(self):
        while(True):
            varid = self.requestQueue.get() # Wait for request update
            self.requestParamUpdate(varid) # Send request for update
            self.incommingQueue.get() # Blocking until reply arrives with value
            
