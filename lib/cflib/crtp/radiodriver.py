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

from cflib.crtp.crtpdriver import CRTPDriver
from .crtpstack import CRTPPacket
from .exceptions import WrongUriType
import threading
import Queue
import re
import array

from cflib.drivers.crazyradio import Crazyradio
from usb import USBError

class RadioDriver (CRTPDriver):
    """ Crazyradio link driver """
    def __init__(self):
        """ Create the link driver """
        CRTPDriver.__init__(self)
        self.cradio = None
        self.uri = ""
        self.link_error_callback = None
        self.link_quality_callback = None
        self.in_queue = None
        self.out_queue = None
        self._thread = None

    def connect(self, uri, link_quality_callback, link_error_callback):
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
            raise WrongUriType('Wrong radio URI format!')

        uri_data = re.search("^radio://([0-9]+)((/([0-9]+))"
                             "(/(250K|1M|2M))?)?$",
                             uri)

        self.uri = uri

        channel = 2
        if uri_data.group(4):
            channel = int(uri_data.group(4))

        datarate = Crazyradio.DR_2MPS
        if uri_data.group(6) == "250K":
            datarate = Crazyradio.DR_250KPS
        if uri_data.group(6) == "1M":
            datarate = Crazyradio.DR_1MPS
        if uri_data.group(6) == "2M":
            datarate = Crazyradio.DR_2MPS

        #FIXME: Still required to open more than one dongle?
        if self.cradio is None:
            self.cradio = Crazyradio()
        else:
            raise Exception("Link already open!")

        if self.cradio.version >= 0.4:
            self.cradio.set_arc(10)
        else:
            logger.warning("Radio version <0.4 will be obsoleted soon!")

        self.cradio.set_channel(channel)

        self.cradio.set_data_rate(datarate)

        #Prepare the inter-thread communication queue
        self.in_queue = Queue.Queue()
        self.out_queue = Queue.Queue(50)  # Limited size out queue to avoid
                                         # "ReadBack" effect

        #Launch the comm thread
        self._thread = _RadioDriverThread(self.cradio, self.in_queue,
                                          self.out_queue,
                                          link_quality_callback,
                                          link_error_callback)
        self._thread.start()

        self.link_error_callback = link_error_callback

    def receive_packet(self, time=0):
        """
        Receive a packet though the link. This call is blocking but will
        timeout and return None if a timeout is supplied.
        """
        if time == 0:
            try:
                return self.in_queue.get(False)
            except Queue.Empty:
                return None
        elif time < 0:
            try:
                return self.in_queue.get(True)
            except Queue.Empty:
                return None
        else:
            try:
                return self.in_queue.get(True, time)
            except Queue.Empty:
                return None

    def send_packet(self, pk):
        """ Send the packet pk though the link """
        #if self.out_queue.full():
        #    self.out_queue.get()
        if (self.cradio is None):
            return

        try:
            self.out_queue.put(pk, True, 2)
        except Queue.Full:
            if self.link_error_callback:
                self.link_error_callback("RadioDriver: Could not send packet"
                                         " to copter")
    def pause(self):
        self._thread.stop()
        self._thread = None

    def restart(self):
	if self._thread:
            return

        self._thread = _RadioDriverThread(self.cradio, self.in_queue,
                                          self.out_queue,
                                          self.link_quality_callback,
                                          self.link_error_callback)
        self._thread.start()


    def close(self):
        """ Close the link. """
        #Stop the comm thread
        self._thread.stop()

        #Close the USB dongle
        try:
            if self.cradio:
                self.cradio.close()
        except:
            # If we pull out the dongle we will not make this call
            pass
        self.cradio = None

    def _scan_radio_channels(self, start=0, stop=125):
        """ Scan for Crazyflies between the supplied channels. """
        return list(self.cradio.scan_channels(start, stop, (0xff,)))

    def scan_interface(self):
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

        self.cradio.set_arc(1)

        self.cradio.set_data_rate(self.cradio.DR_250KPS)
        found += map(lambda c: ["radio://0/{}/250K".format(c), ""],
                     self._scan_radio_channels())
        self.cradio.set_data_rate(self.cradio.DR_1MPS)
        found += map(lambda c: ["radio://0/{}/1M".format(c), ""],
                     self._scan_radio_channels())
        self.cradio.set_data_rate(self.cradio.DR_2MPS)
        found += map(lambda c: ["radio://0/{}/2M".format(c), ""],
                     self._scan_radio_channels())

        self.cradio.close()
        self.cradio = None

        return found
    
    def get_status(self):
        if self.cradio is None:
            try:
                self.cradio = Crazyradio()
            except USBError as e:
                return "Cannot open Crazyradio. Permission problem?"\
                       " ({})".format(str(e))
            except Exception as e:
                return str(e)

        return "Crazyradio version {}".format(self.cradio.version)

    def get_name(self):
        return "radio"


#Transmit/receive radio thread
class _RadioDriverThread (threading.Thread):
    """
    Radio link receiver thread used to read data from the
    Crazyradio USB driver. """

    RETRYCOUNT_BEFORE_DISCONNECT = 10

    def __init__(self, cradio, inQueue, outQueue, link_quality_callback,
                 link_error_callback):
        """ Create the object """
        threading.Thread.__init__(self)
        self.cradio = cradio
        self.in_queue = inQueue
        self.out_queue = outQueue
        self.sp = False
        self.link_error_callback = link_error_callback
        self.link_quality_callback = link_quality_callback
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
                ackStatus = self.cradio.send_packet(dataOut)
            except Exception as e:
                import traceback
                self.link_error_callback("Error communicating with crazy radio"
                                         " ,it has probably been unplugged!\n"
                                         "Exception:%s\n\n%s" % (e,
                                         traceback.format_exc()))

            #Analise the in data packet ...
            if ackStatus is None:
                if (self.link_error_callback is not None):
                    self.link_error_callback("Dongle communication error"
                                             " (ackStatus==None)")
                continue

            if (self.link_quality_callback is not None):
                self.link_quality_callback((10-ackStatus.retry)*10)

            #If no copter, retry
            if ackStatus.ack is False:
                self.retryBeforeDisconnect = self.retryBeforeDisconnect - 1
                if (self.retryBeforeDisconnect == 0 and
                        self.link_error_callback is not None):
                    self.link_error_callback("Too many packets lost")
                continue
            self.retryBeforeDisconnect = self.RETRYCOUNT_BEFORE_DISCONNECT

            data = ackStatus.data

            #If there is a copter in range, the packet is analysed and the next
            #packet to send is prepared
            if (len(data) > 0):
                inPacket = CRTPPacket(data[0], list(data[1:]))
                #print "<- " + inPacket.__str__()
                self.in_queue.put(inPacket)
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
                outPacket = self.out_queue.get(True, waitTime)
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
