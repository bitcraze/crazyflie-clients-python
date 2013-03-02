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
Crazyradio CRTP link driver.

This driver is used to communicate with the Crazyflie using the Crazyradio
USB dongle.
"""

__author__ = 'Bitcraze AB'
__all__ = ['RadioDriver']

import logging
logger = logging.getLogger(__name__)

from crtpdriver import CRTPDriver
from .crtpstack import CRTPPacket
from .exceptions import WrongUriType
import threading
import Queue
import re
import array

from cflib.drivers.crazyradio import Crazyradio


class RadioDriver (CRTPDriver):
    """ Crazyradio link driver """
    def __init__(self):
        """ Create the link driver """
        self.cradio = None
        self.linkErrorCallback = None
        self.linkQualityCallback = None

    def connect(self, uri, linkQualityCallback, linkErrorCallback):
        """
        Connect the link driver to a specified URI of the format:
        radio://<dongle nbr>/<radio channel>/[250K,1M,2M]

        The callback for linkQuality can be called at any moment from the
        driver to report back the link quality in percentage. The
        callback from linkError will be called when a error occues with
        an error message.
        """

        #check if the URI is a radio URI
        if not re.search("^radio://", uri):
            raise WrongUriType("Not a radio URI")

        #Open the USB dongle
        if not re.search("^radio://([0-9]+)((/([0-9]+))(/(250K|1M|2M))?)?$",
                         uri):
            raise Exception('Wrong radio URI format!')

        uriData = re.search("^radio://([0-9]+)((/([0-9]+))(/(250K|1M|2M))?)?$",
                            uri)

        self.uri = uri

        channel = 2
        if uriData.group(4):
            channel = int(uriData.group(4))

        datarate = Crazyradio.DR_2MPS
        if uriData.group(6) == "250K":
            datarate = Crazyradio.DR_250KPS
        if uriData.group(6) == "1M":
            datarate = Crazyradio.DR_1MPS
        if uriData.group(6) == "2M":
            datarate = Crazyradio.DR_2MPS

        #FIXME: Still required to open more than one dongle?
        if self.cradio is None:
            self.cradio = Crazyradio()
        else:
            raise Exception("Link already open!")

        if self.cradio.version >= 0.4:
            self.cradio.setArc(10)
        else:
            logger.warning("Radio version <0.4 will be obsoleted soon!")

        self.cradio.setChannel(channel)

        self.cradio.setDatarate(datarate)

        #Prepare the inter-thread communication queue
        self.inQueue = Queue.Queue()
        self.outQueue = Queue.Queue(50)  # Limited size out queue to avoid
                                         # "ReadBack" effect

        #Launch the comm thread
        self.thread = RadioDriverThread(self.cradio, self.inQueue,
                                        self.outQueue, linkQualityCallback,
                                        linkErrorCallback)
        self.thread.start()

        self.linkErrorCallback = linkErrorCallback

    def receivePacket(self, time=0):
        """
        Receive a packet though the link. This call is blocking but will
        timeout and return None if a timeout is supplied.
        """
        if time == 0:
            try:
                return self.inQueue.get(False)
            except Queue.Empty:
                return None
        elif time < 0:
            try:
                return self.inQueue.get(True)
            except Queue.Empty:
                return None
        else:
            try:
                return self.inQueue.get(True, time)
            except Queue.Empty:
                return None

    def sendPacket(self, pk):
        """ Send the packet pk though the link """
        #if self.outQueue.full():
        #    self.outQueue.get()
        if (self.cradio is None):
            return

        try:
            self.outQueue.put(pk, True, 2)
        except Queue.Full:
            if self.linkErrorCallback:
                self.linkErrorCallback("RadioDriver: Could not send packet to"
                                       " copter")

    def close(self):
        """ Close the link. """
        #Stop the comm thread
        self.thread.stop()

        #Close the USB dongle
        try:
            if self.cradio:
                self.cradio.close()
        except:
            # If we pull out the dongle we will not make this call
            pass
        self.cradio = None

    def scanRadioChannels(self, start=0, stop=125):
        """ Scan for Crazyflies between the supplied channels. """
        return list(self.cradio.scannChannels(start, stop, (0xff,)))

    def scanInterface(self):
        """ Scan interface for Crazyflies """
        if self.cradio is None:
            try:
                self.cradio = Crazyradio()
            except Exception:
                return []
        else:
            raise Exception("Cannot scann for links while the link is open!")

        #FIXME: implements serial number in the Crazyradio driver!
        serial = "N/A"

        logger.info("v%s dongle with serial %s found", self.cradio.version,
                    serial)
        found = []

        self.cradio.setArc(1)

        self.cradio.setDatarate(self.cradio.DR_250KPS)
        found += map(lambda c: ["radio://0/{}/250K".format(c), ""],
                     self.scanRadioChannels())
        self.cradio.setDatarate(self.cradio.DR_1MPS)
        found += map(lambda c: ["radio://0/{}/1M".format(c), ""],
                     self.scanRadioChannels())
        self.cradio.setDatarate(self.cradio.DR_2MPS)
        found += map(lambda c: ["radio://0/{}/2M".format(c), ""],
                     self.scanRadioChannels())

        self.cradio.close()
        self.cradio = None

        return found


#Transmit/receive radio thread
class RadioDriverThread (threading.Thread):
    """
    Radio link receiver thread used to read data from the
    Crazyradio USB driver. """

    RETRYCOUNT_BEFORE_DISCONNECT = 10

    def __init__(self, cradio, inQueue, outQueue, linkQualityCallback,
                 linkErrorCallback):
        """ Create the object """
        threading.Thread.__init__(self)
        self.cradio = cradio
        self.inQueue = inQueue
        self.outQueue = outQueue
        self.sp = False
        self.linkErrorCallback = linkErrorCallback
        self.linkQualityCallback = linkQualityCallback
        self.retryBeforeDisconnect = self.RETRYCOUNT_BEFORE_DISCONNECT

    def stop(self):
        """ Stop the thread """
        self.sp = True
        try:
            self.join()
        except Exception:
            pass

    def run(self):
        """ Run the receiver thread """
        dataOut = array.array('B', [0xFF])
        waitTime = 0
        emptyCtr = 0

        while(True):
            if (self.sp):
                break

            try:
                ackStatus = self.cradio.sendPacket(dataOut)
            except Exception as e:
                import traceback
                self.linkErrorCallback("Error communicating with crazy radio,"
                                       " it has probably been unplugged!\n"
                                       "Exception:%s\n\n%s" % (e,
                                       traceback.format_exc()))

            #Analise the in data packet ...
            if ackStatus is None:
                if (self.linkErrorCallback is not None):
                        self.linkErrorCallback("Dongle communication error"
                                               " (ackStatus==None)")
                continue

            if (self.linkQualityCallback is not None):
                self.linkQualityCallback((10-ackStatus.retry)*10)

            #If no copter, retry
            if ackStatus.ack is False:
                self.retryBeforeDisconnect = self.retryBeforeDisconnect - 1
                if (self.retryBeforeDisconnect == 0 and
                        self.linkErrorCallback is not None):
                    self.linkErrorCallback("Too many packets lost")
                continue
            self.retryBeforeDisconnect = self.RETRYCOUNT_BEFORE_DISCONNECT

            data = ackStatus.data

            #If there is a copter in range, the packet is analysed and the next
            #packet to send is prepared
            if (len(data) > 0):
                inPacket = CRTPPacket(data[0], list(data[1:]))
                #print "<- " + inPacket.__str__()
                self.inQueue.put(inPacket)
                waitTime = 0
                emptyCtr = 0
            else:
                emptyCtr += 1
                if (emptyCtr > 10):
                    emptyCtr = 10
                    waitTime = 0.01  # Relaxation time if the last 10 packet
                                     # where empty
                else:
                    waitTime = 0

            #get the next packet to send of relaxation (wait 10ms)
            outPacket = None
            try:
                outPacket = self.outQueue.get(True, waitTime)
            except Queue.Empty:
                outPacket = None

            dataOut = array.array('B')

            if outPacket:
                #print "-> " + outPacket.__str__()
                dataOut.append(outPacket.header)
                for X in outPacket.data:
                    if type(X) == int:
                        dataOut.append(X)
                    else:
                        dataOut.append(ord(X))
            else:
                dataOut.append(0xFF)
