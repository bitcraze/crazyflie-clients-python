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
from PyQt4.QtCore import Qt, pyqtSlot, pyqtSignal, QVariant
from PyQt4.QtGui import QMessageBox

from cflib.crazyflie import Crazyflie

from cfclient.ui.widgets.ai import AttitudeIndicator

from cfclient.utils.config import Config
from cflib.crazyflie.log import Log, LogVariable, LogConfig

from cfclient.ui.tab import Tab

from cflib.crazyflie.mem import MemoryElement

flight_tab_class = uic.loadUiType(sys.path[0] +
                                  "/cfclient/ui/tabs/flightTab.ui")[0]

MAX_THRUST = 65365.0


class FlightTab(Tab, flight_tab_class):

    uiSetupReadySignal = pyqtSignal()

    _motor_data_signal = pyqtSignal(int, object, object)
    _imu_data_signal = pyqtSignal(int, object, object)
    _althold_data_signal = pyqtSignal(int, object, object)
    _baro_data_signal = pyqtSignal(int, object, object)

    _input_updated_signal = pyqtSignal(float, float, float, float)
    _rp_trim_updated_signal = pyqtSignal(float, float)
    _emergency_stop_updated_signal = pyqtSignal(bool)

    _log_error_signal = pyqtSignal(object, str)

    #UI_DATA_UPDATE_FPS = 10

    connectionFinishedSignal = pyqtSignal(str)
    disconnectedSignal = pyqtSignal(str)

    _limiting_updated = pyqtSignal(bool, bool, bool)

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
        self.helper.cf.connected.add_callback(
            self.connectionFinishedSignal.emit)
        self.helper.cf.disconnected.add_callback(self.disconnectedSignal.emit)

        self._input_updated_signal.connect(self.updateInputControl)
        self.helper.inputDeviceReader.input_updated.add_callback(
                                     self._input_updated_signal.emit)
        self._rp_trim_updated_signal.connect(self.calUpdateFromInput)
        self.helper.inputDeviceReader.rp_trim_updated.add_callback(
                                     self._rp_trim_updated_signal.emit)
        self._emergency_stop_updated_signal.connect(self.updateEmergencyStop)
        self.helper.inputDeviceReader.emergency_stop_updated.add_callback(
                                     self._emergency_stop_updated_signal.emit)
        
        self.helper.inputDeviceReader.althold_updated.add_callback(
                    lambda enabled: self.helper.cf.param.set_value("flightmode.althold", enabled))

        self._imu_data_signal.connect(self._imu_data_received)
        self._baro_data_signal.connect(self._baro_data_received)
        self._althold_data_signal.connect(self._althold_data_received)
        self._motor_data_signal.connect(self._motor_data_received)

        self._log_error_signal.connect(self._logging_error)

        # Connect UI signals that are in this tab
        self.flightModeCombo.currentIndexChanged.connect(self.flightmodeChange)
        self.minThrust.valueChanged.connect(self.minMaxThrustChanged)
        self.maxThrust.valueChanged.connect(self.minMaxThrustChanged)
        self.thrustLoweringSlewRateLimit.valueChanged.connect(
                                      self.thrustLoweringSlewRateLimitChanged)
        self.slewEnableLimit.valueChanged.connect(
                                      self.thrustLoweringSlewRateLimitChanged)
        self.targetCalRoll.valueChanged.connect(self._trim_roll_changed)
        self.targetCalPitch.valueChanged.connect(self._trim_pitch_changed)
        self.maxAngle.valueChanged.connect(self.maxAngleChanged)
        self.maxYawRate.valueChanged.connect(self.maxYawRateChanged)
        self.uiSetupReadySignal.connect(self.uiSetupReady)
        self.clientXModeCheckbox.toggled.connect(self.changeXmode)
        self.isInCrazyFlightmode = False
        self.uiSetupReady()

        self.clientXModeCheckbox.setChecked(Config().get("client_side_xmode"))

        self.crazyflieXModeCheckbox.clicked.connect(
                             lambda enabled:
                             self.helper.cf.param.set_value("flightmode.x",
                                                            str(enabled)))
        self.helper.cf.param.add_update_callback(
                        group="flightmode", name="xmode",
                        cb=( lambda name, checked:
                        self.crazyflieXModeCheckbox.setChecked(eval(checked))))

        self.ratePidRadioButton.clicked.connect(
                    lambda enabled:
                    self.helper.cf.param.set_value("flightmode.ratepid",
                                                   str(enabled)))

        self.angularPidRadioButton.clicked.connect(
                    lambda enabled:
                    self.helper.cf.param.set_value("flightmode.ratepid",
                                                   str(not enabled)))

        self._led_ring_headlight.clicked.connect(
                    lambda enabled:
                    self.helper.cf.param.set_value("ring.headlightEnable",
                                                   str(enabled)))

        self.helper.cf.param.add_update_callback(
                    group="flightmode", name="ratepid",
                    cb=(lambda name, checked:
                    self.ratePidRadioButton.setChecked(eval(checked))))

        self.helper.cf.param.add_update_callback(
                    group="ring", name="headlightEnable",
                    cb=(lambda name, checked:
                    self._led_ring_headlight.setChecked(eval(checked))))

        self.helper.cf.param.add_update_callback(
                    group="flightmode", name="althold",
                    cb=(lambda name, enabled:
                    self.helper.inputDeviceReader.enable_alt_hold(eval(enabled))))

        self._ledring_nbr_effects = 0

        self.helper.cf.param.add_update_callback(
                        group="ring",
                        name="neffect",
                        cb=(lambda name, value: self._set_neffect(eval(value))))

        self.helper.cf.param.add_update_callback(
                        group="imu_sensors",
                        cb=self._set_available_sensors)

        self.helper.cf.param.all_updated.add_callback(self._ring_populate_dropdown)

        self.logBaro = None
        self.logAltHold = None

        self.ai = AttitudeIndicator()
        self.verticalLayout_4.addWidget(self.ai)
        self.splitter.setSizes([1000,1])

        self.targetCalPitch.setValue(Config().get("trim_pitch"))
        self.targetCalRoll.setValue(Config().get("trim_roll"))

        self.helper.inputDeviceReader.alt1_updated.add_callback(self.alt1_updated)
        self.helper.inputDeviceReader.alt2_updated.add_callback(self.alt2_updated)
        self._tf_state = 0
        self._ring_effect = 0

        # Connect callbacks for input device limiting of rpöö/pitch/yaw/thust
        self.helper.inputDeviceReader.limiting_updated.add_callback(
            self._limiting_updated.emit)
        self._limiting_updated.connect(self._set_limiting_enabled)

    def _set_limiting_enabled(self, rp_limiting_enabled,
                                    yaw_limiting_enabled,
                                    thrust_limiting_enabled):
        self.maxAngle.setEnabled(rp_limiting_enabled)
        self.targetCalRoll.setEnabled(rp_limiting_enabled)
        self.targetCalPitch.setEnabled(rp_limiting_enabled)
        self.maxYawRate.setEnabled(yaw_limiting_enabled)
        self.maxThrust.setEnabled(thrust_limiting_enabled)
        self.minThrust.setEnabled(thrust_limiting_enabled)
        self.slewEnableLimit.setEnabled(thrust_limiting_enabled)
        self.thrustLoweringSlewRateLimit.setEnabled(thrust_limiting_enabled)

    def _set_neffect(self, n):
        self._ledring_nbr_effects = n

    def thrustToPercentage(self, thrust):
        return ((thrust / MAX_THRUST) * 100.0)

    def uiSetupReady(self):
        flightComboIndex = self.flightModeCombo.findText(
                             Config().get("flightmode"), Qt.MatchFixedString)
        if (flightComboIndex < 0):
            self.flightModeCombo.setCurrentIndex(0)
            self.flightModeCombo.currentIndexChanged.emit(0)
        else:
            self.flightModeCombo.setCurrentIndex(flightComboIndex)
            self.flightModeCombo.currentIndexChanged.emit(flightComboIndex)

    def _logging_error(self, log_conf, msg):
        QMessageBox.about(self, "Log error", "Error when starting log config"
                " [%s]: %s" % (log_conf.name, msg))

    def _motor_data_received(self, timestamp, data, logconf):
        if self.isVisible():
            self.actualM1.setValue(data["motor.m1"])
            self.actualM2.setValue(data["motor.m2"])
            self.actualM3.setValue(data["motor.m3"])
            self.actualM4.setValue(data["motor.m4"])
        
    def _baro_data_received(self, timestamp, data, logconf):
        if self.isVisible():
            self.actualASL.setText(("%.2f" % data["baro.aslLong"]))
            self.ai.setBaro(data["baro.aslLong"])
        
    def _althold_data_received(self, timestamp, data, logconf):
        if self.isVisible():
            target = data["altHold.target"]
            if target>0:
                if not self.targetASL.isEnabled():
                    self.targetASL.setEnabled(True) 
                self.targetASL.setText(("%.2f" % target))
                self.ai.setHover(target)    
            elif self.targetASL.isEnabled():
                self.targetASL.setEnabled(False)
                self.targetASL.setText("Not set")   
                self.ai.setHover(0)    
        
    def _imu_data_received(self, timestamp, data, logconf):
        if self.isVisible():
            self.actualRoll.setText(("%.2f" % data["stabilizer.roll"]))
            self.actualPitch.setText(("%.2f" % data["stabilizer.pitch"]))
            self.actualYaw.setText(("%.2f" % data["stabilizer.yaw"]))
            self.actualThrust.setText("%.2f%%" %
                                      self.thrustToPercentage(
                                                      data["stabilizer.thrust"]))
    
            self.ai.setRollPitch(-data["stabilizer.roll"],
                                 data["stabilizer.pitch"])

    def connected(self, linkURI):
        # IMU & THRUST
        lg = LogConfig("Stabalizer", Config().get("ui_update_period"))
        lg.add_variable("stabilizer.roll", "float")
        lg.add_variable("stabilizer.pitch", "float")
        lg.add_variable("stabilizer.yaw", "float")
        lg.add_variable("stabilizer.thrust", "uint16_t")

        try:
            self.helper.cf.log.add_config(lg)
            lg.data_received_cb.add_callback(self._imu_data_signal.emit)
            lg.error_cb.add_callback(self._log_error_signal.emit)
            lg.start()
        except KeyError as e:
            logger.warning(str(e))
        except AttributeError as e:
            logger.warning(str(e))

        # MOTOR
        lg = LogConfig("Motors", Config().get("ui_update_period"))
        lg.add_variable("motor.m1")
        lg.add_variable("motor.m2")
        lg.add_variable("motor.m3")
        lg.add_variable("motor.m4")

        try:
            self.helper.cf.log.add_config(lg)
            lg.data_received_cb.add_callback(self._motor_data_signal.emit)
            lg.error_cb.add_callback(self._log_error_signal.emit)
            lg.start()
        except KeyError as e:
            logger.warning(str(e))
        except AttributeError as e:
            logger.warning(str(e))

        if self.helper.cf.mem.ow_search(vid=0xBC, pid=0x01):
            self._led_ring_effect.setEnabled(True)
            self._led_ring_headlight.setEnabled(True)

    def _set_available_sensors(self, name, available):
        logger.info("[%s]: %s", name, available)
        available = eval(available)
        if ("HMC5883L" in name):
            if (not available):
                self.actualASL.setText("N/A")
                self.actualASL.setEnabled(False)
            else:
                self.actualASL.setEnabled(True)
                self.helper.inputDeviceReader.set_alt_hold_available(available)
                if (not self.logBaro and not self.logAltHold):
                    # The sensor is available, set up the logging
                    self.logBaro = LogConfig("Baro", 200)
                    self.logBaro.add_variable("baro.aslLong", "float")

                    try:
                        self.helper.cf.log.add_config(self.logBaro)
                        self.logBaro.data_received_cb.add_callback(
                                self._baro_data_signal.emit)
                        self.logBaro.error_cb.add_callback(
                                self._log_error_signal.emit)
                        self.logBaro.start()
                    except KeyError as e:
                        logger.warning(str(e))
                    except AttributeError as e:
                        logger.warning(str(e))
                    self.logAltHold = LogConfig("AltHold", 200)
                    self.logAltHold.add_variable("altHold.target", "float")

                    try:
                        self.helper.cf.log.add_config(self.logAltHold)
                        self.logAltHold.data_received_cb.add_callback(
                            self._althold_data_signal.emit)
                        self.logAltHold.error_cb.add_callback(
                            self._log_error_signal.emit)
                        self.logAltHold.start()
                    except KeyError as e:
                        logger.warning(str(e))
                    except AttributeError:
                        logger.warning(str(e))

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
        self.actualASL.setText("")
        self.targetASL.setText("Not Set")
        self.targetASL.setEnabled(False)
        self.actualASL.setEnabled(False)
        self.logBaro = None
        self.logAltHold = None
        self._led_ring_effect.setEnabled(False)
        self._led_ring_headlight.setEnabled(False)


    def minMaxThrustChanged(self):
        self.helper.inputDeviceReader.set_thrust_limits(
                            self.minThrust.value(), self.maxThrust.value())
        if (self.isInCrazyFlightmode == True):
            Config().set("min_thrust", self.minThrust.value())
            Config().set("max_thrust", self.maxThrust.value())

    def thrustLoweringSlewRateLimitChanged(self):
        self.helper.inputDeviceReader.set_thrust_slew_limiting(
                            self.thrustLoweringSlewRateLimit.value(),
                            self.slewEnableLimit.value())
        if (self.isInCrazyFlightmode == True):
            Config().set("slew_limit", self.slewEnableLimit.value())
            Config().set("slew_rate", self.thrustLoweringSlewRateLimit.value())

    def maxYawRateChanged(self):
        logger.debug("MaxYawrate changed to %d", self.maxYawRate.value())
        self.helper.inputDeviceReader.set_yaw_limit(self.maxYawRate.value())
        if (self.isInCrazyFlightmode == True):
            Config().set("max_yaw", self.maxYawRate.value())

    def maxAngleChanged(self):
        logger.debug("MaxAngle changed to %d", self.maxAngle.value())
        self.helper.inputDeviceReader.set_rp_limit(self.maxAngle.value())
        if (self.isInCrazyFlightmode == True):
            Config().set("max_rp", self.maxAngle.value())

    def _trim_pitch_changed(self, value):
        logger.debug("Pitch trim updated to [%f]" % value)
        self.helper.inputDeviceReader.set_trim_pitch(value)
        Config().set("trim_pitch", value)

    def _trim_roll_changed(self, value):
        logger.debug("Roll trim updated to [%f]" % value)
        self.helper.inputDeviceReader.set_trim_roll(value)
        Config().set("trim_roll", value)

    def calUpdateFromInput(self, rollCal, pitchCal):
        logger.debug("Trim changed on joystick: roll=%.2f, pitch=%.2f",
                     rollCal, pitchCal)
        self.targetCalRoll.setValue(rollCal)
        self.targetCalPitch.setValue(pitchCal)

    def updateInputControl(self, roll, pitch, yaw, thrust):
        self.targetRoll.setText(("%0.2f" % roll))
        self.targetPitch.setText(("%0.2f" % pitch))
        self.targetYaw.setText(("%0.2f" % yaw))
        self.targetThrust.setText(("%0.2f %%" %
                                   self.thrustToPercentage(thrust)))
        self.thrustProgress.setValue(thrust)

    def setMotorLabelsEnabled(self, enabled):
        self.M1label.setEnabled(enabled)
        self.M2label.setEnabled(enabled)
        self.M3label.setEnabled(enabled)
        self.M4label.setEnabled(enabled)

    def emergencyStopStringWithText(self, text):
        return ("<html><head/><body><p>"
                "<span style='font-weight:600; color:#7b0005;'>{}</span>"
                "</p></body></html>".format(text))

    def updateEmergencyStop(self, emergencyStop):
        if emergencyStop:
            self.setMotorLabelsEnabled(False)
            self.emergency_stop_label.setText(
                      self.emergencyStopStringWithText("Kill switch active"))
        else:
            self.setMotorLabelsEnabled(True)
            self.emergency_stop_label.setText("")

    def flightmodeChange(self, item):
        Config().set("flightmode", str(self.flightModeCombo.itemText(item)))
        logger.debug("Changed flightmode to %s",
                    self.flightModeCombo.itemText(item))
        self.isInCrazyFlightmode = False
        if (item == 0):  # Normal
            self.maxAngle.setValue(Config().get("normal_max_rp"))
            self.maxThrust.setValue(Config().get("normal_max_thrust"))
            self.minThrust.setValue(Config().get("normal_min_thrust"))
            self.slewEnableLimit.setValue(Config().get("normal_slew_limit"))
            self.thrustLoweringSlewRateLimit.setValue(
                                              Config().get("normal_slew_rate"))
            self.maxYawRate.setValue(Config().get("normal_max_yaw"))
        if (item == 1):  # Advanced
            self.maxAngle.setValue(Config().get("max_rp"))
            self.maxThrust.setValue(Config().get("max_thrust"))
            self.minThrust.setValue(Config().get("min_thrust"))
            self.slewEnableLimit.setValue(Config().get("slew_limit"))
            self.thrustLoweringSlewRateLimit.setValue(
                                                  Config().get("slew_rate"))
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
        Config().set("client_side_xmode", checked)
        logger.info("Clientside X-mode enabled: %s", checked)

    def alt1_updated(self, state):
        if state:
            self._ring_effect += 1
            if self._ring_effect > self._ledring_nbr_effects:
                self._ring_effect = 0
            self.helper.cf.param.set_value("ring.effect", str(self._ring_effect))

    def alt2_updated(self, state):
        self.helper.cf.param.set_value("ring.headlightEnable", str(state))

    def _ring_populate_dropdown(self):
        nbr = int(self.helper.cf.param.values["ring"]["neffect"])
        current = int(self.helper.cf.param.values["ring"]["effect"])

        hardcoded_names = {0: "Off",
                           1: "White spinner",
                           2: "Color spinner",
                           3: "Tilt effect",
                           4: "Brightness effect",
                           5: "Color spinner 2",
                           6: "Double spinner",
                           7: "Solid color effect",
                           8: "Factory test",
                           9: "Battery status",
                           10: "Boat lights"}

        for i in range(nbr+1):
            name = "{}: ".format(i)
            if i in hardcoded_names:
                name += hardcoded_names[i]
            else:
                name += "N/A"
            self._led_ring_effect.addItem(name, QVariant(i))

        self._led_ring_effect.setCurrentIndex(current)
        self._led_ring_effect.currentIndexChanged.connect(self._ring_effect_changed)
        self.helper.cf.param.add_update_callback(group="ring",
                                         name="effect",
                                         cb=self._ring_effect_updated)

    def _ring_effect_changed(self, index):
        i = self._led_ring_effect.itemData(index).toInt()[0]
        logger.info("Changed effect to {}".format(i))
        if i != self.helper.cf.param.values["ring"]["effect"]:
            self.helper.cf.param.set_value("ring.effect", str(i))

    def _ring_effect_updated(self, name, value):
        self._led_ring_effect.setCurrentIndex(int(value))
