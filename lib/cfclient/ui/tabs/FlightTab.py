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

from cfclient.ui.widgets.ai import AttitudeIndicator

from cfclient.utils.config import Config
from cflib.crazyflie.log import Log

from cfclient.ui.tab import Tab

from cfclient.utils.logconfigreader import LogVariable, LogConfig

flight_tab_class = uic.loadUiType(sys.path[0] + "/cfclient/ui/tabs/flightTab.ui")[0]

MAX_THRUST = 65365.0

class FlightTab(Tab, flight_tab_class):

    uiSetupReadySignal = pyqtSignal()
    
    _motor_data_signal = pyqtSignal(object)
    _imu_data_signal = pyqtSignal(object)

    UI_DATA_UPDATE_FPS = 10

    connectionFinishedSignal = pyqtSignal(str)
    disconnectedSignal = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        super(FlightTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Flight Control"
        self.menuName = "Flight Control"

        self.tabWidget = tabWidget
        self.helper = helper

        self.disconnectedSignal.connect(self.disconnected)
        self.connectionFinishedSignal.connect(self.connected)
        # Incomming signals
        self.helper.cf.connectSetupFinished.add_callback(self.connectionFinishedSignal.emit)
        self.helper.cf.disconnected.add_callback(self.disconnectedSignal.emit)
        self.helper.inputDeviceReader.inputUpdateSignal.connect(self.updateInputControl)
        self.helper.inputDeviceReader.calUpdateSignal.connect(self.calUpdateFromInput) 

        self._imu_data_signal.connect(self._imu_data_received)
        self._motor_data_signal.connect(self._motor_data_received)

        # Connect UI signals that are in this tab
        self.flightModeCombo.currentIndexChanged.connect(self.flightmodeChange)
        self.minThrust.valueChanged.connect(self.minMaxThrustChanged)
        self.maxThrust.valueChanged.connect(self.minMaxThrustChanged)
        self.thrustLoweringSlewRateLimit.valueChanged.connect(self.thrustLoweringSlewRateLimitChanged)
        self.slewEnableLimit.valueChanged.connect(self.thrustLoweringSlewRateLimitChanged)
        self.targetCalRoll.valueChanged.connect(self._trim_roll_changed)
        self.targetCalPitch.valueChanged.connect(self._trim_pitch_changed)
        self.maxAngle.valueChanged.connect(self.maxAngleChanged)
        self.maxYawRate.valueChanged.connect(self.maxYawRateChanged)
        self.uiSetupReadySignal.connect(self.uiSetupReady)
        self.clientXModeCheckbox.clicked.connect(self.changeXmode)
        self.isInCrazyFlightmode = False
        self.uiSetupReady()
        
        self.crazyflieXModeCheckbox.clicked.connect(
                    lambda enabled: self.helper.cf.param.set_value("flightctrl.xmode", str(enabled)))
        self.helper.cf.param.add_update_callback("flightctrl.xmode", 
                    lambda name, checked: self.crazyflieXModeCheckbox.setChecked(eval(checked)))
        self.ratePidRadioButton.clicked.connect(
                    lambda enabled: self.helper.cf.param.set_value("flightctrl.ratepid", str(enabled)))
        self.angularPidRadioButton.clicked.connect(
                    lambda enabled: self.helper.cf.param.set_value("flightctrl.ratepid", str(not enabled)))
        self.helper.cf.param.add_update_callback("flightctrl.ratepid", 
                    lambda name, checked: self.ratePidRadioButton.setChecked(eval(checked)))


        self.ai = AttitudeIndicator()
        self.gridLayout.addWidget(self.ai, 0, 1)

        self.targetCalPitch.setValue(Config().get("trim_pitch"))
        self.targetCalRoll.setValue(Config().get("trim_roll"))

    def thrustToPercentage(self, thrust):
        return ((thrust/MAX_THRUST)*100.0)

    def percentageToThrust(self, percentage):
        return int(MAX_THRUST*(percentage/100.0))

    def uiSetupReady(self):
        flightComboIndex = self.flightModeCombo.findText(Config().get("flightmode"), Qt.MatchFixedString) 
        if (flightComboIndex < 0):
            self.flightModeCombo.setCurrentIndex(0)
            self.flightModeCombo.currentIndexChanged.emit(0)
        else:
            self.flightModeCombo.setCurrentIndex(flightComboIndex)
            self.flightModeCombo.currentIndexChanged.emit(flightComboIndex)

    def loggingError(self):
        logger.warning("Callback of error in LogEntry :(")

    def _motor_data_received(self, data):
        self.actualM1.setValue(data["motor.m1"])
        self.actualM2.setValue(data["motor.m2"])
        self.actualM3.setValue(data["motor.m3"])
        self.actualM4.setValue(data["motor.m4"])

    def _imu_data_received(self, data):
        self.actualRoll.setText(("%.2f" % data["stabilizer.roll"]));
        self.actualPitch.setText(("%.2f" % data["stabilizer.pitch"]));
        self.actualYaw.setText(("%.2f" % data["stabilizer.yaw"]));
        self.actualThrust.setText("%.2f%%" % self.thrustToPercentage(data["stabilizer.thrust"]))

        self.ai.setRollPitch(-data["stabilizer.roll"], data["stabilizer.pitch"])

    def connected(self, linkURI):
        lg = LogConfig("Stabalizer", 100)
        lg.addVariable(LogVariable("stabilizer.roll", "float"))
        lg.addVariable(LogVariable("stabilizer.pitch", "float"))
        lg.addVariable(LogVariable("stabilizer.yaw", "float"))
        lg.addVariable(LogVariable("stabilizer.thrust", "uint16_t"))

        self.log = self.helper.cf.log.create_log_packet(lg)
        if (self.log is not None):
            self.log.dataReceived.add_callback(self._imu_data_signal.emit)
            self.log.error.add_callback(self.loggingError)
            self.log.start()
        else:
            logger.warning("Could not setup logconfiguration after connection!")

        lg = LogConfig("Motors", 100)
        lg.addVariable(LogVariable("motor.m1", "uint32_t")) 
        lg.addVariable(LogVariable("motor.m2", "uint32_t"))
        lg.addVariable(LogVariable("motor.m3", "uint32_t"))
        lg.addVariable(LogVariable("motor.m4", "uint32_t"))        

        self.log = self.helper.cf.log.create_log_packet(lg)
        if (self.log is not None):
            self.log.dataReceived.add_callback(self._motor_data_signal.emit)
            self.log.error.add_callback(self.loggingError)
            self.log.start()
        else:
            logger.warning("Could not setup logconfiguration after connection!")
  
    def disconnected(self, linkURI):
        self.ai.setRollPitch(0, 0)
        self.actualM1.setValue(0)
        self.actualM2.setValue(0)
        self.actualM3.setValue(0)
        self.actualM4.setValue(0)
        self.actualRoll.setText("")
        self.actualPitch.setText("")
        self.actualYaw.setText("")
        self.actualThrust.setText("")

    def minMaxThrustChanged(self):
        self.helper.inputDeviceReader.updateMinMaxThrustSignal.emit(self.percentageToThrust(self.minThrust.value()), 
                                                                    self.percentageToThrust(self.maxThrust.value()))
        if (self.isInCrazyFlightmode == True):
            Config().set("min_thrust", self.minThrust.value())
            Config().set("max_thrust", self.maxThrust.value())

    def thrustLoweringSlewRateLimitChanged(self):
        self.helper.inputDeviceReader.updateThrustLoweringSlewrateSignal.emit(
                                            self.percentageToThrust(self.thrustLoweringSlewRateLimit.value()),
                                            self.percentageToThrust(self.slewEnableLimit.value()))
        if (self.isInCrazyFlightmode == True):
            Config().set("slew_limit", self.slewEnableLimit.value())
            Config().set("slew_rate", self.thrustLoweringSlewRateLimit.value())

    def maxYawRateChanged(self):
        logger.debug("MaxYawrate changed to %d", self.maxYawRate.value())
        self.helper.inputDeviceReader.updateMaxYawRateSignal.emit(self.maxYawRate.value())
        if (self.isInCrazyFlightmode == True):
            Config().set("max_yaw", self.maxYawRate.value())

    def maxAngleChanged(self):
        logger.debug("MaxAngle changed to %d", self.maxAngle.value())
        self.helper.inputDeviceReader.updateMaxRPAngleSignal.emit(self.maxAngle.value())
        if (self.isInCrazyFlightmode == True):
            Config().set("max_rp", self.maxAngle.value())

    def _trim_pitch_changed(self, value):
        logger.debug("Pitch trim updated to [%f]" % value)
        self.helper.inputDeviceReader.update_trim_pitch_signal.emit(value)
        Config().set("trim_pitch", value)

    def _trim_roll_changed(self, value):
        logger.debug("Roll trim updated to [%f]" % value)
        self.helper.inputDeviceReader.update_trim_roll_signal.emit(value)
        Config().set("trim_roll", value)

    def calUpdateFromInput(self, rollCal, pitchCal):
        logger.debug("Trim changed on joystick: roll=%.2f, pitch=%.2f",
                     rollCal, pitchCal)
        self.targetCalRoll.setValue(rollCal)
        self.targetCalPitch.setValue(pitchCal)

    def updateInputControl(self, roll, pitch, yaw, thrust):
        self.targetRoll.setText(("%0.2f" % roll));
        self.targetPitch.setText(("%0.2f" % pitch));
        self.targetYaw.setText(("%0.2f" % yaw));
        self.targetThrust.setText(("%0.2f %%" % self.thrustToPercentage(thrust)));
        self.thrustProgress.setValue(thrust)

    def flightmodeChange(self, item):
        Config().set("flightmode", self.flightModeCombo.itemText(item))
        logger.info("Changed flightmode to %s", self.flightModeCombo.itemText(item))
        self.isInCrazyFlightmode = False
        if (item == 0): # Normal
            self.maxAngle.setValue(Config().get("normal_max_rp"))
            self.maxThrust.setValue(Config().get("normal_max_thrust"))
            self.minThrust.setValue(Config().get("normal_min_thrust"))
            self.slewEnableLimit.setValue(Config().get("normal_slew_limit"))
            self.thrustLoweringSlewRateLimit.setValue(Config().get("normal_slew_rate"))
            self.maxYawRate.setValue(Config().get("normal_max_yaw"))
        if (item == 1): # Advanced
            self.maxAngle.setValue(Config().get("max_rp"))
            self.maxThrust.setValue(Config().get("max_thrust"))
            self.minThrust.setValue(Config().get("min_thrust"))
            self.slewEnableLimit.setValue(Config().get("slew_limit"))
            self.thrustLoweringSlewRateLimit.setValue(Config().get("slew_rate"))
            self.maxYawRate.setValue(Config().get("max_yaw"))
            self.isInCrazyFlightmode = True

        if (item == 0):
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
        self.helper.cf.commander.set_client_xmode(checked)
        logger.debug("Clientside X-mode enabled: %s", checked)

