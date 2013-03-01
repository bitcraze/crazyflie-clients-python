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
The flight control tab shows telimitry data and flight settings.
"""

__author__ = 'Bitcraze AB'
__all__ = ['FlightTab']

import sys

import logging
logger = logging.getLogger(__name__)

from time import time

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import Qt, pyqtSlot, pyqtSignal, QThread, SIGNAL

from cflib.crazyflie import Crazyflie

from ui.widgets.ai import AttitudeIndicator

from utils.config import Config, ConfigParams
from cflib.crazyflie.log import Log

from ui.tab import Tab

from utils.logconfigreader import LogVariable, LogConfig

flight_tab_class = uic.loadUiType("ui/tabs/flightTab.ui")[0]

MAX_THRUST = 65365.0

class FlightTab(Tab, flight_tab_class):

    uiSetupReadySignal = pyqtSignal()
    
    logDataSignal = pyqtSignal(object)
    
    UI_DATA_UPDATE_FPS = 10

    batteryUpdateSignal = pyqtSignal(int)
    imuUpdateSignal = pyqtSignal(float, float, float)
    motorUpdateSignal = pyqtSignal(int, int, int, int)

    connectionFinishedSignal = pyqtSignal(str)
    disconnectedSignal = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        super(FlightTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Flight Control"
        self.menuName = "Flight Control"

        self.tabWidget = tabWidget
        self.helper = helper

        self.batteryUpdateSignal.connect(self.updateBattData)
        self.imuUpdateSignal.connect(self.updateIMUData)
        self.motorUpdateSignal.connect(self.updateMotorData)

        self.disconnectedSignal.connect(self.disconnected)
        self.connectionFinishedSignal.connect(self.connected)
        # Incomming signals
        self.helper.cf.connectSetupFinished.addCallback(self.connectionFinishedSignal.emit)
        self.helper.cf.disconnected.addCallback(self.disconnectedSignal.emit)
        self.helper.inputDeviceReader.inputUpdateSignal.connect(self.updateInputControl)
        self.helper.inputDeviceReader.calUpdateSignal.connect(self.calUpdateFromInput) 

        self.logDataSignal.connect(self.logDataReceived)

        # Connect UI signals that are in this tab
        self.flightModeCombo.currentIndexChanged.connect(self.flightmodeChange)
        self.minThrust.valueChanged.connect(self.minMaxThrustChanged)
        self.maxThrust.valueChanged.connect(self.minMaxThrustChanged)
        self.thrustLoweringSlewRateLimit.valueChanged.connect(self.thrustLoweringSlewRateLimitChanged)
        self.slewEnableLimit.valueChanged.connect(self.thrustLoweringSlewRateLimitChanged)
        self.targetCalRoll.valueChanged.connect(self.calValueChanged)
        self.targetCalPitch.valueChanged.connect(self.calValueChanged)
        self.maxAngle.valueChanged.connect(self.maxAngleChanged)
        self.maxYawRate.valueChanged.connect(self.maxYawRateChanged)
        self.uiSetupReadySignal.connect(self.uiSetupReady)
        self.clientXModeCheckbox.clicked.connect(self.changeXmode)
        self.isInCrazyFlightmode = False
        self.uiSetupReady()
        
        self.crazyflieXModeCheckbox.clicked.connect(
                    lambda enabled: self.helper.cf.param.setParamValue("flightctrl.xmode", str(enabled)))
        self.helper.cf.param.addParamUpdateCallback("flightctrl.xmode", 
                    lambda name, checked: self.crazyflieXModeCheckbox.setChecked(eval(checked)))
        self.ratePidRadioButton.clicked.connect(
                    lambda enabled: self.helper.cf.param.setParamValue("flightctrl.ratepid", str(enabled)))
        self.angularPidRadioButton.clicked.connect(
                    lambda enabled: self.helper.cf.param.setParamValue("flightctrl.ratepid", str(not enabled)))
        self.helper.cf.param.addParamUpdateCallback("flightctrl.ratepid", 
                    lambda name, checked: self.ratePidRadioButton.setChecked(eval(checked)))


        self.ai = AttitudeIndicator()
        self.gridLayout.addWidget(self.ai, 0, 1)
        
    def thrustToPercentage(self, thrust):
        return ((thrust/MAX_THRUST)*100.0)

    def percentageToThrust(self, percentage):
        return int(MAX_THRUST*(percentage/100.0))

    def uiSetupReady(self):
        try:        
            self.flightModeCombo.setCurrentIndex(self.flightModeCombo.findText(Config().getParam(ConfigParams.FLIGHT_MODE), Qt.MatchFixedString))
        except:
            self.flightModeCombo.setCurrentIndex(1)

    def loggingError(self):
        logger.warning("Callback of error in LogEntry :(")

    def logDataReceived(self, data):
        #print "FlighTab: Got callback for new data of length %d" % len(data)
        self.updateIMUData(data["stabalizer.roll"], data["stabalizer.pitch"], data["stabalizer.yaw"])
        #self.updateMotorData(data["motor.1"], data["motor.2"], data["motor.3"], data["motor.4"])
        #print data

    def connected(self, linkURI):
        lg = LogConfig("FlightTab", 100)
        lg.addVariable(LogVariable("stabalizer.roll", "float"))
        lg.addVariable(LogVariable("stabalizer.pitch", "float"))
        lg.addVariable(LogVariable("stabalizer.yaw", "float"))
        #lg.addVariable(LogVariable("motor.m1", Log.UINT8))
        #lg.addVariable(LogVariable("motor.m2", Log.UINT8))
        #lg.addVariable(LogVariable("motor.m3", Log.UINT8))
        #lg.addVariable(LogVariable("motor.m4", Log.UINT8))

        self.log = self.helper.cf.log.newLogPacket(lg)
        if (self.log != None):
            self.log.dataReceived.addCallback(self.logDataSignal.emit)
            self.log.error.addCallback(self.loggingError)
            self.log.startLogging()
        else:
            logger.warning("Could not setup logconfiguration after connection!")
    
    def disconnected(self, linkURI):
        self.ai.setRollPitch(0, 0)
        self.actualRoll.setText("")
        self.actualPitch.setText("")
        self.actualYaw.setText("")

    def updateIMUData(self, roll, pitch, yaw):
        self.actualRoll.setText(("%.2f" % roll));
        self.actualPitch.setText(("%.2f" % pitch));
        self.actualYaw.setText(("%.2f" % yaw));

        self.ai.setRollPitch(-roll, pitch)

    def updateMotorData(self, m1, m2, m3, m4):
        self.actualM1.setValue(m1)
        self.actualM2.setValue(m2)
        self.actualM3.setValue(m3)
        self.actualM4.setValue(m4)

    def minMaxThrustChanged(self):
        self.helper.inputDeviceReader.updateMinMaxThrustSignal.emit(self.percentageToThrust(self.minThrust.value()), 
                                                                    self.percentageToThrust(self.maxThrust.value()))
        if (self.isInCrazyFlightmode == True):
            Config().setParam(ConfigParams.CRAZY_MIN_THRUST, self.percentageToThrust(self.minThrust.value()))
            Config().setParam(ConfigParams.CRAZY_MAX_THRUST, self.percentageToThrust(self.maxThrust.value()))

    def thrustLoweringSlewRateLimitChanged(self):
        self.helper.inputDeviceReader.updateThrustLoweringSlewrateSignal.emit(
                                            self.percentageToThrust(self.thrustLoweringSlewRateLimit.value()),
                                            self.percentageToThrust(self.slewEnableLimit.value()))
        if (self.isInCrazyFlightmode == True):
            Config().setParam(ConfigParams.CRAZY_SLEW_LIMIT,
                                            self.percentageToThrust(self.slewEnableLimit.value()))
            Config().setParam(ConfigParams.CRAZY_SLEW_RATE,
                                            self.percentageToThrust(self.thrustLoweringSlewRateLimit.value()))

    def maxYawRateChanged(self):
        logger.debug("MaxYawrate changed to %d", self.maxYawRate.value())
        self.helper.inputDeviceReader.updateMaxYawRateSignal.emit(self.maxYawRate.value())
        if (self.isInCrazyFlightmode == True):
            Config().setParam(ConfigParams.CRAZY_MAX_YAWRATE, self.maxYawRate.value())

    def maxAngleChanged(self):
        logger.debug("MaxAngle changed to %d", self.maxAngle.value())
        self.helper.inputDeviceReader.updateMaxRPAngleSignal.emit(self.maxAngle.value())
        if (self.isInCrazyFlightmode == True):
            Config().setParam(ConfigParams.CRAZY_MAX_RP_ANGLE, self.maxAngle.value())

    def calValueChanged(self):
        logger.debug("Trim changed in UI: roll=%.2f, pitch=%.2f", self.targetCalRoll.value(), self.targetCalPitch.value())
        self.helper.inputDeviceReader.updateRPCalSignal.emit(self.targetCalRoll.value(), self.targetCalPitch.value())
        if (self.isInCrazyFlightmode == True):
            Config().setParam(ConfigParams.CAL_ROLL, self.targetCalRoll.value())
            Config().setParam(ConfigParams.CAL_PITCH, self.targetCalPitch.value())

    def calUpdateFromInput(self, rollCal, pitchCal):
        logger.debug("Trim changed on joystick: roll=%.2f, pitch=%.2f", rollCal, pitchCal)
        self.targetCalRoll.setValue(rollCal)
        self.targetCalPitch.setValue(pitchCal)
        if (self.isInCrazyFlightmode == True):
            Config().setParam(ConfigParams.CAL_ROLL, rollCal)
            Config().setParam(ConfigParams.CAL_PITCH, pitchCal)

    def updateBattData(self, voltage):
        self.actualBattVoltage.setText(str(voltage/1000.0))

    def updateInputControl(self, roll, pitch, yaw, thrust):
        self.targetRoll.setText(("%0.2f" % roll));
        self.targetPitch.setText(("%0.2f" % pitch));
        self.targetYaw.setText(("%0.2f" % yaw));
        self.targetThrust.setText(("%0.2f %%" % self.thrustToPercentage(thrust)));
        self.thrustProgress.setValue(thrust)

    def flightmodeChange(self, item):
        Config().setParam(ConfigParams.FLIGHT_MODE, self.flightModeCombo.itemText(item))
        logger.info("Changed flightmode to %s", self.flightModeCombo.itemText(item))
        self.isInCrazyFlightmode = False
        if (item == 2): # Normal
            self.maxAngle.setValue(15)
            self.maxThrust.setValue(self.thrustToPercentage(50000))
            self.minThrust.setValue(self.thrustToPercentage(20000))
            self.slewEnableLimit.setValue(self.thrustToPercentage(30000))
            self.thrustLoweringSlewRateLimit.setValue(self.thrustToPercentage(20000))
            self.maxYawRate.setValue(200)
        if (item == 1): # Safe
            self.maxAngle.setValue(10)
            self.maxThrust.setValue(self.thrustToPercentage(50000))
            self.minThrust.setValue(self.thrustToPercentage(20000))
            self.slewEnableLimit.setValue(self.thrustToPercentage(30000))
            self.thrustLoweringSlewRateLimit.setValue(self.thrustToPercentage(20000))
            self.maxYawRate.setValue(50)
        if (item == 0): # Crazy
            try:
                self.maxAngle.setValue(int(Config().getParam(ConfigParams.CRAZY_MAX_RP_ANGLE)))
                self.maxThrust.setValue(self.thrustToPercentage(int(Config().getParam(ConfigParams.CRAZY_MAX_THRUST))))
                self.minThrust.setValue(self.thrustToPercentage(int(Config().getParam(ConfigParams.CRAZY_MIN_THRUST))))
                self.slewEnableLimit.setValue(self.thrustToPercentage(int(Config().getParam(ConfigParams.CRAZY_SLEW_LIMIT))))
                self.thrustLoweringSlewRateLimit.setValue(self.thrustToPercentage(int(Config().getParam(ConfigParams.CRAZY_SLEW_RATE))))
                self.maxYawRate.setValue(int(Config().getParam(ConfigParams.CRAZY_MAX_YAWRATE)))
            except KeyError:
                self.isInCrazyFlightmode = True
                self.maxAngle.setValue(20)
                self.maxThrust.setValue(self.thrustToPercentage(55000))
                self.minThrust.setValue(self.thrustToPercentage(20000))
                self.slewEnableLimit.setValue(self.thrustToPercentage(30000))
                self.thrustLoweringSlewRateLimit.setValue(self.thrustToPercentage(20000))
                self.maxYawRate.setValue(400)
            self.isInCrazyFlightmode = True

        if (item == 1 or item == 2):
            newState = False
        else:
            newState = True
        self.maxThrust.setEnabled(newState)
        self.maxAngle.setEnabled(newState)
        self.minThrust.setEnabled(newState)
        self.thrustLoweringSlewRateLimit.setEnabled(newState)
        self.slewEnableLimit.setEnabled(newState)
        self.maxYawRate.setEnabled(newState)

    @pyqtSlot(bool)
    def changeXmode(self, checked):
        self.helper.cf.commander.setClientSideXModeEnabled(checked)
        logger.debug("Clientside X-mode enabled: %s", checked)

