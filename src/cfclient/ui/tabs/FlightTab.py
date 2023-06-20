#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2022 Bitcraze AB
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

#  You should have received a copy of the GNU General Public License along with
#  this program; if not, write to the Free Software Foundation, Inc.,
#  51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
The flight control tab shows telemetry data and flight settings.
"""

import logging
from enum import Enum

from PyQt5 import uic
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QMessageBox

import cfclient
from cfclient.ui.widgets.ai import AttitudeIndicator

from cfclient.utils.config import Config
from cflib.crazyflie.log import LogConfig

from cfclient.utils.input import JoystickReader

from cfclient.ui.tab_toolbox import TabToolbox

from sys import stdout
import traceback

__author__ = 'Bitcraze AB'
__all__ = ['FlightTab']

logger = logging.getLogger(__name__)

flight_tab_class = uic.loadUiType(cfclient.module_path +
                                  "/ui/tabs/flightTab.ui")[0]

MAX_THRUST = 65536.0

TOOLTIP_ALTITUDE_HOLD = """\
Keeps the Crazyflie at its current altitude.
Thrust control becomes height velocity control. The Crazyflie
uses the barometer for height control and uses body-fixed coordinates."""

TOOLTIP_POSITION_HOLD = """\
Keeps the Crazyflie at its current 3D position. Pitch/Roll/
Thrust control becomes X/Y/Z velocity control. Uses world coordinates."""

TOOLTIP_HEIGHT_HOLD = """\
When activated, keeps the Crazyflie at 40cm above the ground.
Thrust control becomes height velocity control. Requires a height
sensor like the Z-Ranger deck or flow deck. Uses body-fixed coordinates.."""

TOOLTIP_HOVER = """\
When activated, keeps the Crazyflie at 40cm above the ground and tries to
keep the position in X and Y as well. Thrust control becomes height velocity
control. Requires a flow deck. Uses body-fixed coordinates."""


class CommanderAction(Enum):
    TAKE_OFF = 1
    LAND = 2
    UP = 3
    DOWN = 4
    LEFT = 5
    RIGHT = 6
    FORWARD = 7
    BACK = 8


class FlightTab(TabToolbox, flight_tab_class):
    uiSetupReadySignal = pyqtSignal()

    _log_data_signal = pyqtSignal(int, object, object)
    _pose_data_signal = pyqtSignal(object, object)

    _input_updated_signal = pyqtSignal(float, float, float, float)
    _rp_trim_updated_signal = pyqtSignal(float, float)
    _emergency_stop_updated_signal = pyqtSignal(bool)
    _arm_updated_signal = pyqtSignal(bool)
    _assisted_control_updated_signal = pyqtSignal(bool)
    _heighthold_input_updated_signal = pyqtSignal(float, float, float, float)
    _hover_input_updated_signal = pyqtSignal(float, float, float, float)

    _log_error_signal = pyqtSignal(object, str)

    # UI_DATA_UPDATE_FPS = 10

    connectionFinishedSignal = pyqtSignal(str)
    disconnectedSignal = pyqtSignal(str)

    _limiting_updated = pyqtSignal(bool, bool, bool)

    LOG_NAME_THRUST = 'stabilizer.thrust'
    LOG_NAME_MOTOR_1 = 'motor.m1'
    LOG_NAME_MOTOR_2 = 'motor.m2'
    LOG_NAME_MOTOR_3 = 'motor.m3'
    LOG_NAME_MOTOR_4 = 'motor.m4'
    LOG_NAME_CAN_FLY = 'sys.canfly'
    LOG_NAME_SUPERVISOR_INFO = 'supervisor.info'

    def __init__(self, helper):
        super(FlightTab, self).__init__(helper, 'Flight Control')
        self.setupUi(self)

        self._sticks_for_sim = None

        self.disconnectedSignal.connect(self.disconnected)
        self.connectionFinishedSignal.connect(self.connected)
        # Incomming signals
        self._helper.cf.connected.add_callback(
            self.connectionFinishedSignal.emit)
        self._helper.cf.disconnected.add_callback(self.disconnectedSignal.emit)

        self._input_updated_signal.connect(self.updateInputControl)
        self._helper.inputDeviceReader.input_updated.add_callback(
            self._input_updated_signal.emit)
        self._rp_trim_updated_signal.connect(self.calUpdateFromInput)
        self._helper.inputDeviceReader.rp_trim_updated.add_callback(
            self._rp_trim_updated_signal.emit)
        self._emergency_stop_updated_signal.connect(self.updateEmergencyStop)
        self._helper.inputDeviceReader.emergency_stop_updated.add_callback(
            self._emergency_stop_updated_signal.emit)
        self._arm_updated_signal.connect(self.updateArm)
        self._helper.inputDeviceReader.arm_updated.add_callback(
                self._arm_updated_signal.emit)

        self._helper.inputDeviceReader.heighthold_input_updated.add_callback(
            self._heighthold_input_updated_signal.emit)
        self._heighthold_input_updated_signal.connect(
            self._heighthold_input_updated)
        self._helper.inputDeviceReader.hover_input_updated.add_callback(
            self._hover_input_updated_signal.emit)
        self._hover_input_updated_signal.connect(
            self._hover_input_updated)

        self._helper.inputDeviceReader.assisted_control_updated.add_callback(
            self._assisted_control_updated_signal.emit)

        self._assisted_control_updated_signal.connect(
            self._assisted_control_updated)

        self._pose_data_signal.connect(self._pose_data_received)
        self._log_data_signal.connect(self._log_data_received)

        self._log_error_signal.connect(self._logging_error)

        self._isConnected = False

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
        self.isInCrazyFlightmode = False

        # Command Based Flight Control
        self._can_fly_deprecated = 0
        self.commanderTakeOffButton.clicked.connect(
                lambda: self._flight_command(CommanderAction.TAKE_OFF))
        self.commanderLandButton.clicked.connect(
                lambda: self._flight_command(CommanderAction.LAND))
        self.commanderLeftButton.clicked.connect(
                lambda: self._flight_command(CommanderAction.LEFT))
        self.commanderRightButton.clicked.connect(
                lambda: self._flight_command(CommanderAction.RIGHT))
        self.commanderForwardButton.clicked.connect(
                lambda: self._flight_command(CommanderAction.FORWARD))
        self.commanderBackButton.clicked.connect(
                lambda: self._flight_command(CommanderAction.BACK))
        self.commanderUpButton.clicked.connect(
                lambda: self._flight_command(CommanderAction.UP))
        self.commanderDownButton.clicked.connect(
                lambda: self._flight_command(CommanderAction.DOWN))
        self._update_flight_commander(False)

        # Supervisor
        self._supervisor_info_bitfield = 0
        self.armButton.clicked.connect(self.updateArm)
        self._update_arm_button(False)

        self.uiSetupReady()

        self._led_ring_headlight.clicked.connect(
            lambda enabled: self._helper.cf.param.set_value(
                "ring.headlightEnable", int(enabled)))

        self._helper.cf.param.add_update_callback(
            group="ring", name="headlightEnable",
            cb=(lambda name, checked: 
                self._led_ring_headlight.setChecked(bool(int(checked)))))

        self._ledring_nbr_effects = 0

        self._helper.cf.param.add_update_callback(
                group="ring", name="effect", cb=self._ring_effect_updated)

        self._helper.cf.param.add_update_callback(
                group="imu_sensors", cb=self._set_available_sensors)

        self._helper.cf.param.all_updated.add_callback(self._all_params_updated)

        self.logAltHold = None

        self.ai = AttitudeIndicator()
        self.verticalLayout_4.addWidget(self.ai)
        self.splitter.setSizes([1000, 1])

        self.targetCalPitch.setValue(Config().get("trim_pitch"))
        self.targetCalRoll.setValue(Config().get("trim_roll"))

        self._helper.inputDeviceReader.alt1_updated.add_callback(
                self.alt1_updated)
        self._helper.inputDeviceReader.alt2_updated.add_callback(
                self.alt2_updated)
        self._tf_state = 0
        self._ring_effect = 0

        # Connect callbacks for input device limiting of roll/pitch/yaw/thrust
        self._helper.inputDeviceReader.limiting_updated.add_callback(
                self._limiting_updated.emit)
        self._limiting_updated.connect(self._set_limiting_enabled)

        self._helper.pose_logger.data_received_cb.add_callback(
                self._pose_data_signal.emit)

    def _set_limiting_enabled(
            self, rp_limiting_enabled, yaw_limiting_enabled, 
            thrust_limiting_enabled):

        self.targetCalRoll.setEnabled(rp_limiting_enabled)
        self.targetCalPitch.setEnabled(rp_limiting_enabled)

        advanced_is_enabled = self.isInCrazyFlightmode
        self.maxAngle.setEnabled(rp_limiting_enabled and advanced_is_enabled)
        self.maxYawRate.setEnabled(
                yaw_limiting_enabled and advanced_is_enabled)
        self.maxThrust.setEnabled(
                thrust_limiting_enabled and advanced_is_enabled)
        self.minThrust.setEnabled(
                thrust_limiting_enabled and advanced_is_enabled)
        self.slewEnableLimit.setEnabled(
                thrust_limiting_enabled and advanced_is_enabled)
        self.thrustLoweringSlewRateLimit.setEnabled(
                thrust_limiting_enabled and advanced_is_enabled)

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

    def updatePoseFromSim(self, pose):
        self._pose_data_received(None, pose)

    def _flight_command(self, action):
        current_z = self._helper.pose_logger.position[2]
        move_dist = 0.5
        move_vel = 0.5

        if action == CommanderAction.TAKE_OFF:
            self._helper.cf.param.set_value('commander.enHighLevel', '1')
            z_target = current_z + move_dist
            self._helper.cf.high_level_commander.takeoff(
                    z_target, move_dist / move_vel)
        elif action == CommanderAction.LAND:
            self._helper.cf.high_level_commander.land(0, current_z / move_vel)
        elif action == CommanderAction.LEFT:
            self._helper.cf.high_level_commander.go_to(
                    0, move_dist, 0, 0, move_dist / move_vel, relative=True)
        elif action == CommanderAction.RIGHT:
            self._helper.cf.high_level_commander.go_to(
                    0, -move_dist, 0, 0, move_dist / move_vel, relative=True)
        elif action == CommanderAction.FORWARD:
            self._helper.cf.high_level_commander.go_to(
                    move_dist, 0, 0, 0, move_dist / move_vel, relative=True)
        elif action == CommanderAction.BACK:
            self._helper.cf.high_level_commander.go_to(
                    -move_dist, 0, 0, 0, move_dist / move_vel, relative=True)
        elif action == CommanderAction.UP:
            self._helper.cf.high_level_commander.go_to(
                    0, 0, move_dist, 0, move_dist / move_vel, relative=True)
        elif action == CommanderAction.DOWN:
            self._helper.cf.high_level_commander.go_to(
                    0, 0, -move_dist, 0, move_dist / move_vel, relative=True)

    def _logging_error(self, log_conf, msg):
        QMessageBox.about(self, "Log error",
                          "Error when starting log config [%s]: %s" % (
                              log_conf.name, msg))

    def _log_data_received(self, timestamp, data, logconf):
        if self.isVisible() and self._isConnected:
            self.actualM1.setValue(data[self.LOG_NAME_MOTOR_1])
            self.actualM2.setValue(data[self.LOG_NAME_MOTOR_2])
            self.actualM3.setValue(data[self.LOG_NAME_MOTOR_3])
            self.actualM4.setValue(data[self.LOG_NAME_MOTOR_4])

            self.estimateThrust.setText(
                "%.2f%%" % self.thrustToPercentage(data[self.LOG_NAME_THRUST]))

            if data[self.LOG_NAME_CAN_FLY] != self._can_fly_deprecated:
                self._can_fly_deprecated = data[self.LOG_NAME_CAN_FLY]
                self._update_flight_commander(True)

            if self.LOG_NAME_SUPERVISOR_INFO in data:
                self._supervisor_info_bitfield = (
                        data[self.LOG_NAME_SUPERVISOR_INFO])

            self._update_arm_button(True)

    def _debug(self, msg):
        print(msg)
        stdout.flush()

    def _pose_data_received(self, _, pose):
        if self.isVisible():

            estimated_z = pose[2]
            roll = pose[3]
            pitch = pose[4]

            self.estimateX.setText(("%.2f" % pose[0]))
            self.estimateY.setText(("%.2f" % pose[1]))
            self.estimateZ.setText(("%.2f" % estimated_z))
            self.estimateRoll.setText(("%.2f" % roll))
            self.estimatePitch.setText(("%.2f" % pitch))
            self.estimateYaw.setText(("%.2f" % pose[5]))

            self.ai.setBaro(estimated_z, self.is_visible())
            self.ai.setRollPitch(-roll, pitch, self.is_visible())

    def _heighthold_input_updated(self, roll, pitch, yaw, height):
        if (self.isVisible() and
                (self._helper.inputDeviceReader.get_assisted_control() ==
                 self._helper.inputDeviceReader.ASSISTED_CONTROL_HEIGHTHOLD)):

            self.targetRoll.setText(("%0.2f deg" % roll))
            self.targetPitch.setText(("%0.2f deg" % pitch))
            self.targetYaw.setText(("%0.2f deg/s" % yaw))
            self.targetHeight.setText(("%.2f m" % height))
            self.ai.setHover(height, self.is_visible())

            self._change_input_labels(using_hover_assist=False)

    def _hover_input_updated(self, vx, vy, yaw, height):
        if (self.isVisible() and
                (self._helper.inputDeviceReader.get_assisted_control() ==
                 self._helper.inputDeviceReader.ASSISTED_CONTROL_HOVER)):

            self.targetRoll.setText(("%0.2f m/s" % vy))
            self.targetPitch.setText(("%0.2f m/s" % vx))
            self.targetYaw.setText(("%0.2f deg/s" % yaw))
            self.targetHeight.setText(("%.2f m" % height))
            self.ai.setHover(height, self.is_visible())

            self._change_input_labels(using_hover_assist=True)

    def _change_input_labels(self, using_hover_assist):
        if using_hover_assist:
            pitch, roll, yaw = 'Velocity X', 'Velocity Y', 'Velocity Z'
        else:
            pitch, roll, yaw = 'Pitch', 'Roll', 'Yaw'

        self.inputPitchLabel.setText(pitch)
        self.inputRollLabel.setText(roll)
        self.inputYawLabel.setText(yaw)

    def _update_arm_button(self, connected):
        if not connected:
            self.armButton.setStyleSheet("")
            self.armButton.setText("Arm")
            self.armButton.setEnabled(False)
            return

        if self._is_flying():
            self.armButton.setEnabled(True)
            self.armButton.setText("Emergency stop")
            self.armButton.setStyleSheet("background-color: red")
            return

        if self._is_armed():
            self.armButton.setStyleSheet("background-color: red")
            if self._auto_arming():
                self.armButton.setEnabled(False)
                self.armButton.setText("Auto armed")
            else:
                self.armButton.setEnabled(True)
                self.armButton.setText("Disarm")
        else:
            self.armButton.setText("Arm")
            if self._can_arm():
                self.armButton.setEnabled(True)
                self.armButton.setStyleSheet("background-color: lightgreen")
            else:
                self.armButton.setStyleSheet("")
                self.armButton.setEnabled(False)

    def _update_flight_commander(self, connected):
        self.commanderBox.setToolTip(str())
        if not connected:
            self.commanderBox.setEnabled(False)
            return

        if self._can_fly_deprecated == 0:
            self.commanderBox.setEnabled(False)
            self.commanderBox.setToolTip(
                    'The Crazyflie reports that flight is not possible')
            return

        # We cannot know if we have a positioning deck until we get params
        if not self._helper.cf.param.is_updated:
            self.commanderBox.setEnabled(False)
            return

        #                  flowV1    flowV2     LightHouse       LPS
        position_decks = [
                'bcFlow', 'bcFlow2', 'bcLighthouse4', 'bcLoco', 'bcDWM1000']
        for deck in position_decks:
            if int(self._helper.cf.param.values['deck'][deck]) == 1:
                self.commanderBox.setEnabled(True)
                break
        else:
            self.commanderBox.setToolTip(
                    'You need a positioning deck to use Command Based Flight')
            self.commanderBox.setEnabled(False)
            return

        # To prevent conflicting commands from the controller and the flight
        # panel
        if JoystickReader().available_devices():
            self.commanderBox.setToolTip(
                'Cant use both an controller and Command Based Flight'
            )
            self.commanderBox.setEnabled(False)
            return

    def connected(self, linkURI):
        self._isConnected = True
        # MOTOR & THRUST
        lg = LogConfig("Motors", Config().get("ui_update_period"))
        lg.add_variable(self.LOG_NAME_THRUST, "uint16_t")
        lg.add_variable(self.LOG_NAME_MOTOR_1)
        lg.add_variable(self.LOG_NAME_MOTOR_2)
        lg.add_variable(self.LOG_NAME_MOTOR_3)
        lg.add_variable(self.LOG_NAME_MOTOR_4)
        lg.add_variable(self.LOG_NAME_CAN_FLY)

        # Add supervisor info if it exists to keep backwards compatibility
        if self._helper.cf.log.toc.get_element_by_complete_name(
                self.LOG_NAME_SUPERVISOR_INFO):
            lg.add_variable(self.LOG_NAME_SUPERVISOR_INFO)

        try:
            self._helper.cf.log.add_config(lg)
            lg.data_received_cb.add_callback(self._log_data_signal.emit)
            lg.error_cb.add_callback(self._log_error_signal.emit)
            lg.start()
        except KeyError as e:
            logger.warning(str(e))
        except AttributeError as e:
            logger.warning(str(e))

    def _enable_estimators(self, should_enable):
        self.estimateX.setEnabled(should_enable)
        self.estimateY.setEnabled(should_enable)
        self.estimateZ.setEnabled(should_enable)

    def _set_available_sensors(self, name, available):
        logger.debug("[%s]: %s", name, available)
        available = eval(available)

        self._enable_estimators(True)
        self._helper.inputDeviceReader.set_alt_hold_available(available)

    def disconnected(self, linkURI):
        self._isConnected = False
        self.ai.setRollPitch(0, 0)
        self.actualM1.setValue(0)
        self.actualM2.setValue(0)
        self.actualM3.setValue(0)
        self.actualM4.setValue(0)

        self.estimateRoll.setText("")
        self.estimatePitch.setText("")
        self.estimateYaw.setText("")
        self.estimateThrust.setText("")
        self.estimateX.setText("")
        self.estimateY.setText("")
        self.estimateZ.setText("")

        self.targetHeight.setText("Not Set")
        self.ai.setHover(0, self.is_visible())
        self.targetHeight.setEnabled(False)

        self._enable_estimators(False)

        self.logAltHold = None
        self._led_ring_effect.setEnabled(False)
        self._led_ring_effect.clear()
        try:
            self._led_ring_effect.currentIndexChanged.disconnect(
                self._ring_effect_changed)
        except TypeError:
            # Signal was not connected
            pass
        self._led_ring_effect.setCurrentIndex(-1)
        self._led_ring_headlight.setEnabled(False)

        try:
            self._assist_mode_combo.currentIndexChanged.disconnect(
                self._assist_mode_changed)
        except TypeError:
            # Signal was not connected
            pass
        self._assist_mode_combo.setEnabled(False)
        self._assist_mode_combo.clear()

        self._update_flight_commander(False)

        self._supervisor_info_bitfield = 0
        self._update_arm_button(False)

    def _can_arm(self):
        return bool(self._supervisor_info_bitfield & 0x0001)

    def _is_armed(self):
        return bool(self._supervisor_info_bitfield & 0x0002)

    def _auto_arming(self):
        return bool(self._supervisor_info_bitfield & 0x0004)

    def _can_fly(self):
        return bool(self._supervisor_info_bitfield & 0x0008)

    def _is_flying(self):
        return bool(self._supervisor_info_bitfield & 0x0010)

    def _is_tumbled(self):
        return bool(self._supervisor_info_bitfield & 0x0020)

    def minMaxThrustChanged(self):
        self._helper.inputDeviceReader.min_thrust = self.minThrust.value()
        self._helper.inputDeviceReader.max_thrust = self.maxThrust.value()
        if (self.isInCrazyFlightmode is True):
            Config().set("min_thrust", self.minThrust.value())
            Config().set("max_thrust", self.maxThrust.value())

    def thrustLoweringSlewRateLimitChanged(self):
        self._helper.inputDeviceReader.thrust_slew_rate = (
            self.thrustLoweringSlewRateLimit.value())
        self._helper.inputDeviceReader.thrust_slew_limit = (
            self.slewEnableLimit.value())
        if (self.isInCrazyFlightmode is True):
            Config().set("slew_limit", self.slewEnableLimit.value())
            Config().set("slew_rate", self.thrustLoweringSlewRateLimit.value())

    def maxYawRateChanged(self):
        logger.debug("MaxYawrate changed to %d", self.maxYawRate.value())
        self._helper.inputDeviceReader.max_yaw_rate = self.maxYawRate.value()
        if (self.isInCrazyFlightmode is True):
            Config().set("max_yaw", self.maxYawRate.value())

    def maxAngleChanged(self):
        logger.debug("MaxAngle changed to %d", self.maxAngle.value())
        self._helper.inputDeviceReader.max_rp_angle = self.maxAngle.value()
        if (self.isInCrazyFlightmode is True):
            Config().set("max_rp", self.maxAngle.value())

    def _trim_pitch_changed(self, value):
        logger.debug("Pitch trim updated to [%f]" % value)
        self._helper.inputDeviceReader.trim_pitch = value
        Config().set("trim_pitch", value)

    def _trim_roll_changed(self, value):
        logger.debug("Roll trim updated to [%f]" % value)
        self._helper.inputDeviceReader.trim_roll = value
        Config().set("trim_roll", value)

    def calUpdateFromInput(self, rollCal, pitchCal):
        logger.debug("Trim changed on joystick: roll=%.2f, pitch=%.2f",
                     rollCal, pitchCal)
        self.targetCalRoll.setValue(rollCal)
        self.targetCalPitch.setValue(pitchCal)

    def updateInputControl(self, roll, pitch, yaw, thrust):
        thrustPercent = self.thrustToPercentage(thrust)
        self.targetRoll.setText(("%0.2f deg" % roll))
        self.targetPitch.setText(("%0.2f deg" % pitch))
        self.targetYaw.setText(("%0.2f deg/s" % yaw))
        self.targetThrust.setText(("%0.2f %%" % thrustPercent))
                                   
        self.thrustProgress.setValue(int(thrust))

        self._change_input_labels(using_hover_assist=False)

        self._sticks_for_sim = (thrustPercent, roll, pitch, yaw)

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
            self._helper.cf.loc.send_emergency_stop()
            # TODO krri disarm?
        else:
            self.setMotorLabelsEnabled(True)

    def updateArm(self):
        if self._is_flying():
            self._helper.cf.loc.send_emergency_stop()
            # TODO krri disarm?
        else:
            if self._is_armed():
                self._helper.cf.platform.send_arming_request(False)
            else:
                if self._can_arm():
                    self.armButton.setStyleSheet("background-color: orange")
                    self._helper.cf.platform.send_arming_request(True)

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

    def _debug(self, msg):
        print(msg)
        stdout.flush()

    def _assist_mode_changed(self, item):
        mode = None

        if (item == 0):  # Altitude hold
            mode = JoystickReader.ASSISTED_CONTROL_ALTHOLD
        if (item == 1):  # Position hold
            mode = JoystickReader.ASSISTED_CONTROL_POSHOLD
        if (item == 2):  # Position hold
            mode = JoystickReader.ASSISTED_CONTROL_HEIGHTHOLD
        if (item == 3):  # Position hold
            mode = JoystickReader.ASSISTED_CONTROL_HOVER

        self._helper.inputDeviceReader.set_assisted_control(mode)
        Config().set("assistedControl", mode)

    def _assisted_control_updated(self, enabled):
        if self._helper.inputDeviceReader.get_assisted_control() == \
                JoystickReader.ASSISTED_CONTROL_POSHOLD:
            self.targetThrust.setEnabled(not enabled)
            self.targetRoll.setEnabled(not enabled)
            self.targetPitch.setEnabled(not enabled)
        elif ((self._helper.inputDeviceReader.get_assisted_control() ==
                JoystickReader.ASSISTED_CONTROL_HEIGHTHOLD) or
                (self._helper.inputDeviceReader.get_assisted_control() ==
                 JoystickReader.ASSISTED_CONTROL_HOVER)):
            self.targetThrust.setEnabled(not enabled)
            self.targetHeight.setEnabled(enabled)
            print('Chaning enable for target height: %s' % enabled)
        else:
            self._helper.cf.param.set_value("flightmode.althold", str(enabled))

    def alt1_updated(self, state):
        if state:
            new_index = (self._ring_effect+1) % (self._ledring_nbr_effects+1)
            self._helper.cf.param.set_value("ring.effect", str(new_index))

    def alt2_updated(self, state):
        self._helper.cf.param.set_value("ring.headlightEnable", str(state))

    def _all_params_updated(self):
        self._ring_populate_dropdown()
        self._populate_assisted_mode_dropdown()
        self._update_flight_commander(True)
        self._update_arm_button(True)

    def _ring_populate_dropdown(self):
        try:
            nbr = int(self._helper.cf.param.values["ring"]["neffect"])
            current = int(self._helper.cf.param.values["ring"]["effect"])
        except KeyError:
            return

        # Used only in alt1_updated function
        self._ring_effect = current
        self._ledring_nbr_effects = nbr

        hardcoded_names = {
            0: "Off",
            1: "White spinner",
            2: "Color spinner",
            3: "Tilt effect",
            4: "Brightness effect",
            5: "Color spinner 2",
            6: "Double spinner",
            7: "Solid color effect",
            8: "Factory test",
            9: "Battery status",
            10: "Boat lights",
            11: "Alert",
            12: "Gravity",
            13: "LED tab",
            14: "Color fader",
            15: "Link quality",
            16: "Location server status",
            17: "Sequencer",
            18: "Lighthouse quality",
        }

        for i in range(nbr + 1):
            name = "{}: ".format(i)
            if i in hardcoded_names:
                name += hardcoded_names[i]
            else:
                name += "N/A"
            self._led_ring_effect.addItem(name, i)

        self._led_ring_effect.currentIndexChanged.connect(
            self._ring_effect_changed)

        self._led_ring_effect.setCurrentIndex(current)
        if int(self._helper.cf.param.values["deck"]["bcLedRing"]) == 1:
            self._led_ring_effect.setEnabled(True)
            self._led_ring_headlight.setEnabled(True)

    def _ring_effect_changed(self, index):
        self._ring_effect = index
        if index > -1:
            i = self._led_ring_effect.itemData(index)
            logger.debug("Changed effect to {}".format(i))
            if i != int(self._helper.cf.param.values["ring"]["effect"]):
                self._helper.cf.param.set_value("ring.effect", str(i))

    def _ring_effect_updated(self, name, value):
        if self._helper.cf.param.is_updated:
            self._led_ring_effect.setCurrentIndex(int(value))

    def _populate_assisted_mode_dropdown(self):
        self._assist_mode_combo.addItem("Altitude hold", 0)
        self._assist_mode_combo.addItem("Position hold", 1)
        self._assist_mode_combo.addItem("Height hold", 2)
        self._assist_mode_combo.addItem("Hover", 3)

        # Add the tooltips to the assist-mode items.
        self._assist_mode_combo.setItemData(0, TOOLTIP_ALTITUDE_HOLD,
                                            Qt.ToolTipRole)
        self._assist_mode_combo.setItemData(1, TOOLTIP_POSITION_HOLD,
                                            Qt.ToolTipRole)
        self._assist_mode_combo.setItemData(2, TOOLTIP_HEIGHT_HOLD,
                                            Qt.ToolTipRole)
        self._assist_mode_combo.setItemData(3, TOOLTIP_HOVER,
                                            Qt.ToolTipRole)

        heightHoldPossible = False
        hoverPossible = False

        if int(self._helper.cf.param.values["deck"]["bcZRanger"]) == 1:
            heightHoldPossible = True
            self._helper.inputDeviceReader.set_hover_max_height(1.0)

        if int(self._helper.cf.param.values["deck"]["bcZRanger2"]) == 1:
            heightHoldPossible = True
            self._helper.inputDeviceReader.set_hover_max_height(2.0)

        if int(self._helper.cf.param.values["deck"]["bcFlow"]) == 1:
            heightHoldPossible = True
            hoverPossible = True
            self._helper.inputDeviceReader.set_hover_max_height(1.0)

        if int(self._helper.cf.param.values["deck"]["bcFlow2"]) == 1:
            heightHoldPossible = True
            hoverPossible = True
            self._helper.inputDeviceReader.set_hover_max_height(2.0)

        if not heightHoldPossible:
            self._assist_mode_combo.model().item(2).setEnabled(False)
        else:
            self._assist_mode_combo.model().item(0).setEnabled(False)

        if not hoverPossible:
            self._assist_mode_combo.model().item(3).setEnabled(False)
        else:
            self._assist_mode_combo.model().item(0).setEnabled(False)

        self._assist_mode_combo.currentIndexChanged.connect(
            self._assist_mode_changed)
        self._assist_mode_combo.setEnabled(True)

        try:
            assistmodeComboIndex = Config().get("assistedControl")
            if assistmodeComboIndex == 3 and not hoverPossible:
                self._assist_mode_combo.setCurrentIndex(0)
                self._assist_mode_combo.currentIndexChanged.emit(0)
            elif assistmodeComboIndex == 0 and hoverPossible:
                self._assist_mode_combo.setCurrentIndex(3)
                self._assist_mode_combo.currentIndexChanged.emit(3)
            elif assistmodeComboIndex == 2 and not heightHoldPossible:
                self._assist_mode_combo.setCurrentIndex(0)
                self._assist_mode_combo.currentIndexChanged.emit(0)
            elif assistmodeComboIndex == 0 and heightHoldPossible:
                self._assist_mode_combo.setCurrentIndex(2)
                self._assist_mode_combo.currentIndexChanged.emit(2)
            else:
                self._assist_mode_combo.setCurrentIndex(assistmodeComboIndex)
                self._assist_mode_combo.currentIndexChanged.emit(
                                                    assistmodeComboIndex)
        except KeyError:
            defaultOption = 0
            if hoverPossible:
                defaultOption = 3
            elif heightHoldPossible:
                defaultOption = 2
            self._assist_mode_combo.setCurrentIndex(defaultOption)
            self._assist_mode_combo.currentIndexChanged.emit(defaultOption)
