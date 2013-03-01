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
Crazyflie radio bootloader for flashing firmware.
"""

__author__ = 'Bitcraze AB'
__all__ = ['Cloader']


import cflib.crtp

from cflib.crtp.crtpstack import CRTPPacket, CRTPPort

import sys
import time
import struct
import math

class Cloader:
    def __init__(self, link, clink_address="radio://0/110"):
        """Init the communication class by starting to comunicate with the link
        given. clink is the link address used after reseting to the bootloader.

        The device is actually considered in firmware mode.
        """
        self.link = link
        self.clink_address = clink_address
        self.in_loader = False

        self.pageSize = 0
        self.bufferPages = 0
        self.flashPages = 0
        self.startPage = 0
        self.cpuid = "N/A"

    def close(self):
        """ Close the link """
        self.link.close()

    def resetBootloader(self, cpu_id):
        """ Reset to the bootloader
        The parameter cpuid shall correspond to the device to reset.

        Return true if the reset has been done and the contact with the bootloader
        is established.
        """
        #Send an echo request and wait for the answer
        #Mainly aim to bypass a bug of the crazyflie firmware that prevent reset
        #before normal CRTP communication
        pk = CRTPPacket()
        pk.setPort(CRTPPort.LINKCTRL)
        pk.data = (1, 2, 3)+cpu_id
        self.link.sendPacket(pk)

        pk = None
        while True:
            pk = self.link.receivePacket(2)
            if not pk:
                return False

            if pk.getPort()==CRTPPort.LINKCTRL:
                break;

        #Send the reset to bootloader request
        pk = CRTPPacket()
        pk.setHeader(0xFF, 0xFF)
        pk.data = (0xFF, 0xFE)+cpu_id
        self.link.sendPacket(pk)

        #Wait to ack the reset ...
        pk = None
        while True:
            pk = self.link.receivePacket(2)
            if not pk:
                return False

            if pk.port==0xFF and tuple(pk.data) == (0xFF, 0xFE)+cpu_id:
                pk.data = (0xFF, 0xF0)+cpu_id
                self.link.sendPacket(pk)
                break;

        time.sleep(0.1)
        self.link.close()
        self.link = cflib.crtp.getDriver(self.clink_address)
        #time.sleep(0.1)

        return self.updateInfo()

    def resetFirmware(self, cpu_id):
        """ Reset to firmware
        The parameter cpuid shall correspond to the device to reset.

        Return true if the reset has been done
        """
        #Send the reset to bootloader request
        pk = CRTPPacket()
        pk.setHeader(0xFF, 0xFF)
        pk.data = (0xFF, 0xFF)+cpu_id
        self.link.sendPacket(pk)

        #Wait to ack the reset ...
        pk = None
        while True:
            pk = self.link.receivePacket(2)
            if not pk:
                return False

            if pk.getHeader()==0xFF and struct.unpack("B"*len(pk.data), pk.data) == (0xFF, 0xFF)+cpu_id:
                pk.data = (0xFF, 0xF0)+cpu_id
                self.link.sendPacket(pk)
                break;

        time.sleep(0.1)

    def coldBoot(self):
        """Try to get a connection with the bootloader by calling updateInfo 5 times.
        This let rougly 10 seconds to boot the copter ..."""
        for i in range(0,5):
            self.link.close()
            self.link = cflib.crtp.getDriver(self.clink_address)
            if self.updateInfo():
                return True

        return False

    def updateInfo(self):
        """ Call the command getInfo and fill up the information received in
        the fields of the object
        """

        #Call getInfo ...
        pk = CRTPPacket()
        pk.setHeader(0xFF, 0xFF)
        pk.data = (0xFF, 0x10)
        self.link.sendPacket(pk);

        #Wait for the answer
        pk= self.link.receivePacket(2)

        if pk and pk.getHeader() == 0xFF and struct.unpack("<BB", pk.data[0:2]) == (0xFF, 0x10):
            tab = struct.unpack("BBHHHH", pk.data[0:10])
            cpuid = struct.unpack("B"*12, pk.data[10:])
            self.pageSize = tab[2]
            self.bufferPages = tab[3]
            self.flashPages = tab[4]
            self.startPage = tab[5]
            self.cpuid = "%02X" % cpuid[0]
            for i in cpuid[1:]:
                self.cpuid += ":%02X" %i

            return True

        return False

    def loadBuffer(self, page, address, buff):
        """Upload data into a buffer on the Crazyflie"""
        #print len(buff)
        count=0
        pk = CRTPPacket()
        pk.setHeader(0xFF, 0xFF)
        pk.data = struct.pack("=BBHH", 0xFF, 0x14, page, address)

        for i in range(0,len(buff)):
            #print "[0x%02X]" %  ord(buff[i]),
            pk.data += buff[i]

            count += 1

            if count>24:
                self.link.sendPacket(pk)
                count = 0
                pk = CRTPPacket()
                pk.setHeader(0xFF, 0xFF)
                pk.data = struct.pack("=BBHH", 0xFF, 0x14, page, i+address+1)

                #sys.stdout.write("+")
                #sys.stdout.flush()

        self.link.sendPacket(pk)

    def readFlashPage(self, page):
        """Read back a flash page from the Crazyflie and return it"""
        buff = ""

        for i in range(0, int(math.ceil(self.pageSize/25.0))):
            pk = CRTPPacket()
            pk.setHeader(0xFF, 0xFF)
            pk.data = struct.pack("<BBHH", 0xFF, 0x1C, page, (i*25))
            self.link.sendPacket(pk);

            pk = self.link.receivePacket(1)
            buff += pk.data[6:]

        return buff[0:1024] # For some reason we get one byte extra here...

    def flash(self, bufferPage, flashPage, nPage):
        """Initate flashing of data in the buffers to flashPage and nPage number of buffers."""
        #print "Write page", flashPage
        #print "Writing page [%d] and [%d] forward" % (flashPage, nPage)

        pk = CRTPPacket()
        pk.setHeader(0xFF, 0xFF)
        pk.data = struct.pack("<BBHHH", 0xFF, 0x18, bufferPage, flashPage, nPage);
        self.link.sendPacket(pk);

        pk = self.link.receivePacket(1)
        while not pk or pk.getHeader()!=0xFF or struct.unpack("<BB", pk.data[0:2])!=(0xFF, 0x18):
            pk = self.link.receivePacket(1)

        if not pk:
            self.error_code = -1
            return False

        self.error_code = ord(pk.data[3])

        return ord(pk.data[2]) == 1

    def decodeCpuId(self, cpuid):
        ret = ()
        for i in cpuid.split(':'):
            ret += (eval("0x"+i), )

        return ret

    def getErrorCode(self):
        """Get the last occured error code."""
        return self.error_code
