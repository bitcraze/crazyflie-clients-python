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
A generic TableOfContents module that is used to fetch, store and minipulate
a TOC for logging or parameters.
"""

__author__ = 'Bitcraze AB'
__all__ = ['TocElement', 'Toc', 'TocFetcher']

from cflib.crtp.crtpstack import CRTPPacket
import struct

import logging
logger = logging.getLogger(__name__)

TOC_CHANNEL = 0

# Commands used when accessing the Table of Contents
CMD_TOC_ELEMENT = 0
CMD_TOC_INFO = 1

# Possible states when receiving TOC
IDLE = "IDLE"
GET_TOC_INFO = "GET_TOC_INFO"
GET_TOC_ELEMENT = "GET_TOC_ELEMENT"


class TocElement:
    """An element in the TOC."""
    RW_ACCESS = 0
    RO_ACCESS = 1

    ident = 0
    group = ""
    name = ""
    ctype = ""
    pytype = ""
    access = RO_ACCESS


class Toc:
    """Container for TocElements."""

    def __init__(self):
        self.toc = {}

    def clear(self):
        """Clear the TOC"""
        self.toc = {}

    def addElement(self, element):
        """Add a new TocElement to the TOC container."""
        try:
            self.toc[element.group][element.name] = element
        except Exception:
            self.toc[element.group] = {}
            self.toc[element.group][element.name] = element

    def getByCompleteName(self, completeName):
        """Get a TocElement element identified by complete name from the
        container."""
        try:
            return self.getByIdent(self.getElementId(completeName))
        except:
            # Item not found
            return None

    def getElementId(self, completeName):
        """Get the TocElement element id-number of the element with the
        supplied name."""
        [group, name] = completeName.split(".")
        element = self.getElement(group, name)
        if element:
            return element.ident
        else:
            logger.warning("Unable to find variable [%s]", completeName)
            return None

    def getAllCompleteNames(self):
        """Get all complete names of the elements in the TOC."""
        completeNames = []
        for group in self.toc.keys():
            for name in self.toc[group].keys():
                completeNames.append("%s.%s" % (group, name))
        return completeNames

    def getElement(self, group, name):
        """Get a TocElement element identified by name and group from the
        container."""
        try:
            return self.toc[group][name]
        except Exception:
            return None

    def getByIdent(self, ident):
        """Get a TocElement element identified by index number from the
        container."""
        for group in self.toc.keys():
            for name in self.toc[group].keys():
                if self.toc[group][name].ident == ident:
                    return self.toc[group][name]
        return None


class TocFetcher:
    """Fetches TOC entries from the Crazyflie"""
    def __init__(self, crazyflie, elementClass, port, tocHolder,
                 finishedCallback):
        self.cf = crazyflie
        self.port = port
        self.toc = tocHolder
        self.finishedCallback = finishedCallback
        self.elementClass = elementClass
        return

    def getToc(self):
        """Initiate fetching of the TOC."""
        logger.debug("[%d]: Start fetching...", self.port)
        # Register callback in this class for the port
        self.cf.incomming.addPortCallback(self.port, self.incomming)

        # Request the TOC CRC
        self.state = GET_TOC_INFO
        pk = CRTPPacket()
        pk.setHeader(self.port, TOC_CHANNEL)
        pk.data = (CMD_TOC_INFO, )
        self.cf.sendLinkPacket(pk, expectAnswer=True)

    def tocFetchFinished(self):
        self.cf.incomming.removePortCallback(self.port, self.incomming)
        logger.debug("[%d]: Done!", self.port)
        self.finishedCallback()

    def incomming(self, packet):
        chan = packet.getChannel()
        if (chan != 0):
            logger.error("Got packet that was not on TOC channel, TOC fetch"
                         " will probably not succeed")
            return
        payload = struct.pack("B"*(len(packet.datal)-1), *packet.datal[1:])

        #logger.debug("%s", packet)

        if (self.state == GET_TOC_INFO):
            [self.nbrOfItems, crc] = struct.unpack("<BI", payload[:5])
            logger.debug("[%d]: Got TOC CRC, %d items and crc=0x%08X",
                         self.port, self.nbrOfItems, crc)
            
            # TODO: Implement TOC cache using the CRC as a key
            self.state = GET_TOC_ELEMENT
            self.requestedIndex = 0
            self.requestTocElement(self.requestedIndex)
        elif (self.state == GET_TOC_ELEMENT):
            # Always add new element, but only request new if it's not the
            # last one.
            if self.requestedIndex != ord(payload[0]):
                # TODO: There might be a timing issue here with resending old
                #       packets while loosing new ones. Then if 7 is requested
                #       but 6 is send back due to timing issues with the resend
                #       while 7 is lost then we will never resend for 7.
                #       This is pretty hard to reproduce but happens...
                logging.warning("[%d]: Was expecting %d but got %d",
                                self.port, self.requestedIndex,
                                ord(payload[0]))
                return
            self.toc.addElement(self.elementClass(payload))
            logger.debug("Added element [%s]",
                         self.elementClass(payload).ident)
            if (self.requestedIndex < (self.nbrOfItems-1)):
                logger.debug("[%d]: More variables, requesting index %d",
                             self.port, self.requestedIndex+1)
                self.requestedIndex = self.requestedIndex+1
                self.requestTocElement(self.requestedIndex)
            else:  # No more variables in TOC
                # TODO: Save TOC in a cache with CRC as a key so that it can
                #       be loaded from cache the next time.
                self.tocFetchFinished()

    def requestTocElement(self, index):
        logger.debug("Requesting index %d on port %d", index, self.port)
        pk = CRTPPacket()
        pk.setHeader(self.port, TOC_CHANNEL)
        pk.data = (CMD_TOC_ELEMENT, index)
        self.cf.sendLinkPacket(pk, expectAnswer=True)
