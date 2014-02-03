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
Crazyflie radio bootloader for flashing firmware.
"""

__author__ = 'Bitcraze AB'
__all__ = ['Cloader']

import logging
logger = logging.getLogger(__name__)

import time
import struct
import math
import random

import cflib.crtp
from cflib.crtp.crtpstack import CRTPPacket, CRTPPort


class Cloader:
    """Bootloader utility for the Crazyflie"""
    def __init__(self, link, clink_address="radio://0/110"):
        """Init the communication class by starting to comunicate with the
        link given. clink is the link address used after reseting to the
        bootloader.

        The device is actually considered in firmware mode.
        """
        self.link = link
        self.clink_address = clink_address
        self.in_loader = False

        self.page_size = 0
        self.buffer_pages = 0
        self.flash_pages = 0
        self.start_page = 0
        self.cpuid = "N/A"
        self.error_code = 0
        self.protocol_version = 0

    def close(self):
        """ Close the link """
        self.link.close()

    def reset_to_bootloader(self, cpu_id):
        """ Reset to the bootloader
        The parameter cpuid shall correspond to the device to reset.

        Return true if the reset has been done and the contact with the
        bootloader is established.
        """
        #Send an echo request and wait for the answer
        #Mainly aim to bypass a bug of the crazyflie firmware that prevent
        #reset before normal CRTP communication
        pk = CRTPPacket()
        pk.port = CRTPPort.LINKCTRL
        pk.data = (1, 2, 3) + cpu_id
        self.link.send_packet(pk)

        pk = None
        while True:
            pk = self.link.receive_packet(2)
            if not pk:
                return False

            if pk.port == CRTPPort.LINKCTRL:
                break

        #Send the reset to bootloader request
        pk = CRTPPacket()
        pk.set_header(0xFF, 0xFF)
        pk.data = (0xFF, 0xFE) + cpu_id
        self.link.send_packet(pk)

        #Wait to ack the reset ...
        pk = None
        while True:
            pk = self.link.receive_packet(2)
            if not pk:
                return False

            if pk.port == 0xFF and tuple(pk.data) == (0xFF, 0xFE) + cpu_id:
                pk.data = (0xFF, 0xF0) + cpu_id
                self.link.send_packet(pk)
                break

        time.sleep(0.1)
        self.link.close()
        self.link = cflib.crtp.get_link_driver(self.clink_address)
        #time.sleep(0.1)

        return self._update_info()

    def reset_to_firmware(self, cpu_id):
        """ Reset to firmware
        The parameter cpuid shall correspond to the device to reset.

        Return true if the reset has been done
        """
        #Send the reset to bootloader request
        pk = CRTPPacket()
        pk.set_header(0xFF, 0xFF)
        pk.data = (0xFF, 0xFF) + cpu_id
        self.link.send_packet(pk)

        #Wait to ack the reset ...
        pk = None
        while True:
            pk = self.link.receive_packet(2)
            if not pk:
                return False

            if (pk.header == 0xFF and
                struct.unpack("B" * len(pk.data),
                              pk.data) == (0xFF, 0xFF) + cpu_id):
                pk.data = (0xFF, 0xF0) + cpu_id
                self.link.send_packet(pk)
                break

        time.sleep(0.1)

    def coldboot(self):
        """Try to get a connection with the bootloader by requesting info
        5 times. This let rougly 10 seconds to boot the copter ..."""
        for _ in range(0, 5):
            self.link.close()
            self.link = cflib.crtp.get_link_driver(self.clink_address)
            if self._update_info():
                if self.protocol_version == 0:
                    return True
                # Set radio link to a random address
                addr = [0xbc] + map(lambda x: random.randint(0, 255), range(4))
                return self._set_address(addr)

        return False

    def _set_address(self, new_address):
        """ Change copter radio address.
            This function workd only with crazyradio crtp link.
        """

        logging.debug("Setting bootloader radio address to"
                      " {}".format(new_address))

        if len(new_address) != 5:
            raise Exception("Radio address should be 5 bytes long")

        self.link.pause()

        for _ in range(10):
            logging.debug("Trying to set new radio address")
            self.link.cradio.set_address((0xE7,) * 5)
            pkdata = (0xFF, 0xFF, 0x11) + tuple(new_address)
            self.link.cradio.send_packet(pkdata)
            self.link.cradio.set_address(tuple(new_address))
            if self.link.cradio.send_packet((0xff,)).ack:
                logging.info("Bootloader set to radio address"
                             " {}".format(new_address))
                self.link.restart()
                return True

        self.link.restart()
        return False

    def _update_info(self):
        """ Call the command getInfo and fill up the information received in
        the fields of the object
        """

        #Call getInfo ...
        pk = CRTPPacket()
        pk.set_header(0xFF, 0xFF)
        pk.data = (0xFF, 0x10)
        self.link.send_packet(pk)

        #Wait for the answer
        pk = self.link.receive_packet(2)

        if (pk and pk.header == 0xFF and
                struct.unpack("<BB", pk.data[0:2]) == (0xFF, 0x10)):
            tab = struct.unpack("BBHHHH", pk.data[0:10])
            cpuid = struct.unpack("B" * 12, pk.data[10:22])
            if len(pk.data) > 22:
                self.protocol_version = pk.data[22]
            self.page_size = tab[2]
            self.buffer_pages = tab[3]
            self.flash_pages = tab[4]
            self.start_page = tab[5]
            self.cpuid = "%02X" % cpuid[0]
            for i in cpuid[1:]:
                self.cpuid += ":%02X" % i

            return True

        return False

    def upload_buffer(self, page, address, buff):
        """Upload data into a buffer on the Crazyflie"""
        #print len(buff)
        count = 0
        pk = CRTPPacket()
        pk.set_header(0xFF, 0xFF)
        pk.data = struct.pack("=BBHH", 0xFF, 0x14, page, address)

        for i in range(0, len(buff)):
            #print "[0x%02X]" %  ord(buff[i]),
            pk.data += buff[i]

            count += 1

            if count > 24:
                self.link.send_packet(pk)
                count = 0
                pk = CRTPPacket()
                pk.set_header(0xFF, 0xFF)
                pk.data = struct.pack("=BBHH", 0xFF, 0x14, page,
                                      i + address + 1)

                #sys.stdout.write("+")
                #sys.stdout.flush()

        self.link.send_packet(pk)

    def read_flash(self, page):
        """Read back a flash page from the Crazyflie and return it"""
        buff = ""

        for i in range(0, int(math.ceil(self.page_size / 25.0))):
            pk = None
            retry_counter = 5
            while ((not pk or pk.header != 0xFF or
                    struct.unpack("<BB", pk.data[0:2]) != (0xFF, 0x1C))
                    and retry_counter >= 0):
                pk = CRTPPacket()
                pk.set_header(0xFF, 0xFF)
                pk.data = struct.pack("<BBHH", 0xFF, 0x1C, page, (i * 25))
                self.link.send_packet(pk)

                pk = self.link.receive_packet(1)
                retry_counter -= 1
            if (retry_counter < 0):
                return None
            else:
                buff += pk.data[6:]

        return buff[0:self.page_size]  # For some reason we get one byte extra here...

    def write_flash(self, page_buffer, target_page, page_count):
        """Initate flashing of data in the buffer to flash."""
        #print "Write page", flashPage
        #print "Writing page [%d] and [%d] forward" % (flashPage, nPage)
        pk = None
        retry_counter = 5
        while ((not pk or pk.header != 0xFF or
                struct.unpack("<BB", pk.data[0:2]) != (0xFF, 0x18))
                and retry_counter >= 0):
            pk = CRTPPacket()
            pk.set_header(0xFF, 0xFF)
            pk.data = struct.pack("<BBHHH", 0xFF, 0x18, page_buffer,
                                  target_page, page_count)
            self.link.send_packet(pk)
            pk = self.link.receive_packet(1)
            retry_counter -= 1

        if retry_counter < 0:
            self.error_code = -1
            return False

        self.error_code = ord(pk.data[3])

        return ord(pk.data[2]) == 1

    def decode_cpu_id(self, cpuid):
        """Decode the CPU id into a string"""
        ret = ()
        for i in cpuid.split(':'):
            ret += (eval("0x" + i), )

        return ret
