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
USB driver for the Crazyradio USB dongle.
"""

__author__ = 'Bitcraze AB'
__all__ = ['Crazyradio']


import os
import usb

#USB parameters
CRADIO_VID = 0x1915
CRADIO_PID = 0x7777

# Dongle configuration requests
#See http://wiki.bitcraze.se/projects:crazyradio:protocol for documentation
SET_RADIO_CHANNEL = 0x01
SET_RADIO_ADDRESS = 0x02
SET_DATA_RATE     = 0x03
SET_RADIO_POWER   = 0x04
SET_RADIO_ARD     = 0x05
SET_RADIO_ARC     = 0x06
ACK_ENABLE        = 0x10
SET_CONT_CARRIER  = 0x20
SCANN_CHANNELS    = 0x21
LAUNCH_BOOTLOADER = 0xFF

try:
    import usb.core
    pyusb1 = True
except:
    pyusb1 = False

def findDevices():
    """
    Returns a list of CrazyRadio devices currently connected to the computer
    """
    ret = []
    
    if pyusb1:
        #FIXME: pyUSB 1.x should also be able to return a list of device!
        dev = usb.core.find(idVendor=0x1915, idProduct=0x7777)
        if dev!=None:
            ret += [dev,]
    else:
      busses = usb.busses()
      for bus in busses:
        for device in bus.devices:
          if device.idVendor == CRADIO_VID:
            if device.idProduct == CRADIO_PID:
              ret += [device, ]
    
    return ret

class radioAck:
    ack = False
    powerDet = False
    retry = 0
    data = ()

class Crazyradio:
    """ Used for communication with the Crazyradio USB dongle """
    #configuration constants
    DR_250KPS = 0
    DR_1MPS   = 1
    DR_2MPS   = 2
    
    P_M18DBM = 0
    P_M12DBM = 1
    P_M6DBM  = 2
    P_0DBM   = 3
    
    
    def __init__(self, device=None):
        """ Create object and scan for USB dongle if no device is supplied """
        if device == None:
            try:
                device = findDevices()[0]
            except Exception:
                raise Exception("Cannot find a Crazyradio Dongle")

        self.dev = device
        
        if (pyusb1 == True):
            self.dev.set_configuration(1)
            self.handle = self.dev
            self.version = float( "{0:x}.{1:x}".format(self.dev.bcdDevice>>8, self.dev.bcdDevice&0x0FF) )
        else:       
            self.handle = self.dev.open()
            self.handle.setConfiguration(1)
            self.handle.claimInterface(0)
            self.version = float(self.dev.deviceVersion)
        
        if self.version < 0.3:
            raise "This driver requires Crazyradio firmware V0.3+"
        
        if self.version < 0.4:
            print "Warning: you should update to Crazyradio firmware V0.4+"
        
        #Reset the dongle to power up settings
        self.setDatarate(self.DR_2MPS)
        self.setChannel(2)
        self.arc = -1
        if self.version >= 0.4:
            self.setContCarrier(False)
            self.setAddress((0xE7,)*5)
            self.setPower(self.P_0DBM)
            self.setArc(3)
            self.setArdBytes(32)
    
    def close(self):
        if (pyusb1 == False):
            if self.handle:
                self.handle.releaseInterface();
                self.handle.reset();
        else:
            if self.dev:
                if os.name != 'nt':
                    self.dev.reset()
        
        self.handle = None
        self.dev = None
        

    ### Dongle configuration ###
    def setChannel(self, channel):
        """ Set the radio channel to be used """
        sendVendorSetup(self.handle, SET_RADIO_CHANNEL, channel, 0, ())
    
    def setAddress(self, address):
        """ Set the radio address to be used"""
        if len(address) != 5:
            raise Exception("Crazyradio: the radio address shall be 5 bytes long")
        
        sendVendorSetup(self.handle, SET_RADIO_ADDRESS, 0, 0, address)
    
    def setDatarate(self, datarate):
        """ Set the radio datarate to be used """
        sendVendorSetup(self.handle, SET_DATA_RATE, datarate, 0, ())
    
    def setPower(self, power):
        """ Set the radio power to be used """
        sendVendorSetup(self.handle, SET_RADIO_POWER, power, 0, ())
    
    def setArc(self, arc):
        """ Set the ACK retry count for radio communication """
        sendVendorSetup(self.handle, SET_RADIO_ARC, arc, 0, ())
        self.arc = arc
    
    def setArdTime(self, us):
        """ Set the ACK retry delay for radio communication """
        # Auto Retransmit Delay: 
        # 0000 - Wait 250uS
        # 0001 - Wait 500uS 
        # 0010 - Wait 750uS 
        # ........
        # 1111 - Wait 4000uS
        t = int((us/250)-1); # round down, to value representing a multiple of 250uS
        if (t < 0):
            t = 0;
        if (t > 0xF):
            t = 0xF;
        sendVendorSetup(self.handle, SET_RADIO_ARD, t, 0, ())
    
    def setArdBytes(self, nbytes):
        sendVendorSetup(self.handle, SET_RADIO_ARD, 0x80 | nbytes, 0, ())
    
    def setContCarrier(self, active):
        if active:
            sendVendorSetup(self.handle, SET_CONT_CARRIER, 1, 0, ())
        else:
            sendVendorSetup(self.handle, SET_CONT_CARRIER, 0, 0, ())
    
    def hasFwScann(self):
        return self.version>=0.5
    
    def scannChannels(self, start, stop, packet):
        if self.hasFwScann():# Fast firmware-driven scann
            sendVendorSetup(self.handle, SCANN_CHANNELS, start, stop, packet)
            return tuple(getVendorSetup(self.handle, SCANN_CHANNELS, 0, 0, 64))
        else: # Slow PC-driven scann
            result = tuple()
            for i in range(start, stop+1):
                self.setChannel(i)
                status = self.sendPacket(packet)
                if status and status.ack:
                    result = result + (i,)
            return result
    
    ### Data transferts ###
    def sendPacket(self, dataOut):
        """ Send a packet and receive the ack from the radio dongle
            The ack contains information about the packet transmition
            and a data payload if the ack packet contained any """
        ackIn = None
        data = None
        try:
            if (pyusb1 == False):
                self.handle.bulkWrite(1, dataOut, 1000)
                data = self.handle.bulkRead(0x81, 64,1000)
            else:
                self.handle.write(1, dataOut, 0, 1000); 
                data = self.handle.read(0x81, 64, 0, 1000)
        except usb.USBError, error:
            pass
        
        if data != None:
            ackIn = radioAck()
            if data[0] != 0:
                ackIn.ack = (data[0]&0x01) != 0
                ackIn.powerDet = (data[0]&0x02) != 0
                ackIn.retry = data[0]>>4
                ackIn.data = data[1:]
            else:
                ackIn.retry = self.arc
            
        return ackIn


#Private utility functions
def sendVendorSetup(handle, request, value, index, data):
    if pyusb1:
        handle.ctrl_transfer(usb.TYPE_VENDOR, request, wValue=value, wIndex=index, timeout=1000, data_or_wLength = data)
    else:
        handle.controlMsg(usb.TYPE_VENDOR, request, data, value=value, index=index, timeout=1000)

def getVendorSetup(handle, request, value, index, length):
    if pyusb1:
        return handle.ctrl_transfer(usb.TYPE_VENDOR | 0x80, request, wValue=value, 
                                    wIndex=index, timeout=1000, data_or_wLength = length)
    else:
        return handle.controlMsg(usb.TYPE_VENDOR | 0x80, request, length, value=value, 
                                index=index, timeout=1000)
