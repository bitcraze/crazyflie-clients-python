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
The input module that will read joysticks/input devices and send control set-points to
the Crazyflie. It will also accept settings from the UI.

This module can use different drivers for reading the input device data. Currently it can
just use the PyGame driver but in the future there will be a Linux and Windows driver that can
bypass PyGame.

When reading values from inputdevice a config is used to map axis and buttons to control functions
for the Crazyflie.
"""

__author__ = 'Bitcraze AB'
__all__ = ['JoystickReader']

import sys

import json
import os
import glob
import traceback
import logging
import shutil

logger = logging.getLogger(__name__)

from pygamereader import PyGameReader

from PyQt4 import Qt, QtCore, QtGui, uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qt import *

class JoystickReader(QThread):
    """Thread that will read input from devices/joysticks and send control-setponts to
    the Crazyflie"""
    PITCH_AXIS_ID  = 0
    ROLL_AXIS_ID   = 1
    YAW_AXIS_ID    = 2
    THRUST_AXIS_ID = 3

    # Incomming signal to start input capture
    startInputSignal = pyqtSignal(int, str)
    # Incomming signal to stop input capture
    stopInputSignal = pyqtSignal()
    # Incomming signal to set min/max thrust
    updateMinMaxThrustSignal = pyqtSignal(int, int)
    # Incomming signal to set roll/pitch calibration
    updateRPCalSignal = pyqtSignal(float, float)
    # Incomming signal to set max roll/pitch angle
    updateMaxRPAngleSignal = pyqtSignal(int)
    # Incomming signal to set max yaw rate
    updateMaxYawRateSignal = pyqtSignal(int)
    # Incomming signal to set thrust lowering slew rate limiting
    updateThrustLoweringSlewrateSignal = pyqtSignal(int, int)

    # Configure the aixs: Axis id, joystick axis id and inverse or not
    updateAxisConfigSignal = pyqtSignal(int, int, float)
    # Start detection of variation for joystick axis
    detectAxisVarSignal = pyqtSignal()
    
    # Outgoing signal for device found
    inputUpdateSignal = pyqtSignal(float, float, float, float)
    # Outgoing signal for when pitch/roll calibration has been updated
    calUpdateSignal = pyqtSignal(float, float)

    inputDeviceErrorSignal = pyqtSignal('QString')

    sendControlSetpointSignal = pyqtSignal(float, float, float, int)

    inputConfig = []
    
    def __init__(self):
        QThread.__init__(self)
        #self.moveToThread(self)

        # TODO: Should be OS dependant
        self.inputdevice = PyGameReader()

        self.startInputSignal.connect(self.startInput)
        self.stopInputSignal.connect(self.stopInput)
        self.updateMinMaxThrustSignal.connect(self.updateMinMaxThrust)
        self.updateRPCalSignal.connect(self.updateRPCal)
        self.updateMaxRPAngleSignal.connect(self.updateMaxRPAngle)
        self.updateThrustLoweringSlewrateSignal.connect(self.updateThrustLoweringSlewrate)
        self.updateMaxYawRateSignal.connect(self.updateMaxYawRate)

        self.maxRPAngle = 0
        self.thrustDownSlew = 0
        self.thrustSlewEnabled = False
        self.slewEnableLimit = 0
        self.maxYawRate = 0
        self.detectAxis = False

        self.oldThrust = 0

        # TODO: The polling interval should be set from config file
        self.readTimer = QTimer()
        self.readTimer.setInterval(10);
        self.connect(self.readTimer, SIGNAL("timeout()"), self.readInput)

        self.listOfConfigs = []

        # Check if user config exists, otherwise copy files
        if (not os.path.isdir(sys.path[1] + "/input")):
            logger.info("No user config found, copying dist files")
            os.makedirs(sys.path[1] + "/input")
            for f in glob.glob(sys.path[0] + "/cfclient/configs/input/[A-Za-z]*.json"):
                shutil.copy2(f, sys.path[1] + "/input")

        try:
            configsfound = [ os.path.basename(f) for f in glob.glob(sys.path[1] + "/input/[A-Za-z]*.json")]
            self.inputConfig = []
            for conf in configsfound:            
                logger.info("Parsing [%s]", conf)
                json_data = open (sys.path[1] + "/input/%s"%conf)                
                self.data = json.load(json_data)
                newInputDevice = {}
                for a in self.data["inputconfig"]["inputdevice"]["axis"]:
                    axis = {}
                    axis["scale"] = a["scale"]
                    axis["type"] = a["type"]
                    axis["key"] = a["key"]
                    axis["name"] = a["name"]
                    index = "%s-%d" % (a["type"], a["id"]) # 'type'-'id' defines unique index for axis
                    newInputDevice[index] = axis
                self.inputConfig.append(newInputDevice)
                json_data.close()
                self.listOfConfigs.append(conf[:-5])
        except Exception as e:
            logger.warning("Exception while parsing inputconfig file: %s ", e)

    def getAvailableDevices(self):
        """List all available input devices."""
        return self.inputdevice.getAvailableDevices()

    def getConfig(self, configName):
        """Get the configuratio for an input device."""
        try:
            idx = self.listOfConfigs.index(configName)
            return self.inputConfig[idx]
        except:
            return None

    def getListOfConfigs(self):
        """Get a list of all the input devices."""
        return self.listOfConfigs

    def enableRawReading(self, deviceId):
        """Enable raw reading of the input device with id deviceId. This is used to
        get raw values for setting up of input devices. Values are read without using a mapping."""
        self.inputdevice.enableRawReading(deviceId)

    def disableRawReading(self):
        """Disable raw reading of input device."""
        self.inputdevice.disableRawReading()

    def readRawValues(self):
        """ Read raw values from the input device."""
        return self.inputdevice.readRawValues()

    # Fix for Ubuntu... doing self.moveToThread will not work without this
    # since it seems that the default implementation of run will not call exec_ to process
    # events.
    def run(self):
        self.exec_()

    @pyqtSlot(int, str)
    def startInput(self, deviceId, configName):
        """Start reading inpyt from the device with id deviceId using config configName"""
        try:
            idx = self.listOfConfigs.index(configName)
            self.inputdevice.startInput(deviceId, self.inputConfig[idx])
            self.readTimer.start()
        except Exception:
            self.inputDeviceErrorSignal.emit("Error while opening/initializing input device %i\n\n%s" % (deviceId, traceback.format_exc()))

    @pyqtSlot()
    def stopInput(self):
        """Stop reading from the input device."""
        self.readTimer.stop()

    @pyqtSlot(int)
    def updateMaxYawRate(self, maxRate):
        """Set a new max yaw rate value."""
        self.maxYawRate = maxRate

    @pyqtSlot(int)
    def updateMaxRPAngle(self, maxAngle):
        """Set a new max roll/pitch value."""
        self.maxRPAngle = maxAngle

    @pyqtSlot(int, int)
    def updateThrustLoweringSlewrate(self, thrustDownSlew, slewLimit):
        """Set new values for limit where the slewrate control kicks in and
        for the slewrate."""
        self.thrustDownSlew = thrustDownSlew
        self.slewEnableLimit = slewLimit
        if (thrustDownSlew > 0):
            self.thrustSlewEnabled = True
        else:
            self.thrustSlewEnabled = False

    def setCrazyflie(self, cf):
        """Set the referance for the Crazyflie"""
        self.cf = cf

    @pyqtSlot(int, int)
    def updateMinMaxThrust(self, minThrust, maxThrust):
        """Set a new min/max thrust limit."""
        self.minThrust = minThrust
        self.maxThrust = maxThrust

    @pyqtSlot(float, float)
    def updateRPCal(self, calRoll, calPitch):
        """Set a new value for the roll/pitch trim."""
        self.rollCal = calRoll
        self.pitchCal = calPitch

    @pyqtSlot()
    def readInput(self):
        """Read input data from the selected device"""
        try:
            data = self.inputdevice.readInput()
            roll = data["roll"] * self.maxRPAngle
            pitch = data["pitch"] * self.maxRPAngle
            thrust = data["thrust"]
            yaw = data["yaw"]
            raw_thrust = data["thrust"]

            rollcal = data["rollcal"]
            pitchcal = data["pitchcal"]

            # Thust limiting (slew, minimum and emergency stop)
            if (raw_thrust<0.05 or data["estop"] == True):
                thrust=0
            else:
                thrust = self.minThrust + thrust * (self.maxThrust - self.minThrust)
            if (self.thrustSlewEnabled == True and self.slewEnableLimit > thrust and data["estop"] == False):
                if (self.oldThrust > self.slewEnableLimit):
                    self.oldThrust = self.slewEnableLimit
                if (thrust < (self.oldThrust - (self.thrustDownSlew/100))):
                    thrust = self.oldThrust - self.thrustDownSlew/100
                if (raw_thrust < 0 or thrust < self.minThrust):
                    thrust = 0
            self.oldThrust = thrust

            # Yaw deadband
            # TODO: Add to input device config?
            if (yaw < -0.2 or yaw > 0.2):
                if (yaw < 0):
                    yaw = (yaw + 0.2) * self.maxYawRate * 1.25
                else:
                    yaw = (yaw - 0.2) * self.maxYawRate * 1.25
            else:
                self.yaw = 0

            self.inputUpdateSignal.emit(roll, pitch, yaw, thrust)
            self.calUpdateSignal.emit(rollcal, pitchcal)
            self.sendControlSetpointSignal.emit(roll + rollcal, pitch + pitchcal, yaw, thrust)
        except Exception:
            logger.warning("Exception while reading inputdevice: %s", traceback.format_exc())
            self.inputDeviceErrorSignal.emit("Error reading from input device\n\n%s"%traceback.format_exc())
            self.readTimer.stop()


