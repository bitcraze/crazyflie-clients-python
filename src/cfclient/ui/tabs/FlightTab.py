#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2025 Bitcraze AB
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

from __future__ import annotations

import asyncio
import logging
from enum import Enum

from PySide6.QtUiTools import loadUiType
from PySide6.QtCore import Qt, Signal

import cfclient
from cflib2 import Crazyflie
from cflib2.error import DisconnectedError
from cfclient.gui import create_task
from cfclient.ui.pose_logger import PoseLogger
from cfclient.ui.widgets.ai import AttitudeIndicator

from cfclient.utils.config import Config
from cfclient.utils.input import JoystickReader

from cfclient.ui.tab_toolbox import TabToolbox

__author__ = "Bitcraze AB"
__all__ = ["FlightTab"]

logger = logging.getLogger(__name__)

flight_tab_class = loadUiType(cfclient.module_path + "/ui/tabs/flightTab.ui")[0]

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
    uiSetupReadySignal = Signal()

    _pose_data_signal = Signal(object, object)

    _input_updated_signal = Signal(float, float, float, float)
    _rp_trim_updated_signal = Signal(float, float)
    _emergency_stop_updated_signal = Signal(bool)
    _arm_updated_signal = Signal(bool)
    _assisted_control_updated_signal = Signal(bool)
    _heighthold_input_updated_signal = Signal(float, float, float, float)
    _hover_input_updated_signal = Signal(float, float, float, float)

    _limiting_updated = Signal(bool, bool, bool)

    LOG_NAME_THRUST = "stabilizer.thrust"
    LOG_NAME_MOTOR_1 = "motor.m1"
    LOG_NAME_MOTOR_2 = "motor.m2"
    LOG_NAME_MOTOR_3 = "motor.m3"
    LOG_NAME_MOTOR_4 = "motor.m4"
    LOG_NAME_CAN_FLY = "sys.canfly"
    LOG_NAME_SUPERVISOR_INFO = "supervisor.info"

    def __init__(self, helper: object) -> None:
        super(FlightTab, self).__init__(helper, "Flight Control")
        self.setupUi(self)

        self._cf = None
        self._log_task = None
        self._setup_task = None
        self._isConnected = False

        self._input_updated_signal.connect(self.updateInputControl)
        self._rp_trim_updated_signal.connect(self.calUpdateFromInput)
        self._emergency_stop_updated_signal.connect(self.updateEmergencyStop)
        self._arm_updated_signal.connect(
            lambda _enabled: self.updateArm(from_controller=True)
        )
        self._heighthold_input_updated_signal.connect(self._heighthold_input_updated)
        self._hover_input_updated_signal.connect(self._hover_input_updated)
        self._assisted_control_updated_signal.connect(self._assisted_control_updated)

        if self._helper.inputDeviceReader is not None:
            self._helper.inputDeviceReader.input_updated.add_callback(
                self._input_updated_signal.emit
            )
            self._helper.inputDeviceReader.rp_trim_updated.add_callback(
                self._rp_trim_updated_signal.emit
            )
            self._helper.inputDeviceReader.emergency_stop_updated.add_callback(
                self._emergency_stop_updated_signal.emit
            )
            self._helper.inputDeviceReader.arm_updated.add_callback(
                self._arm_updated_signal.emit
            )
            self._helper.inputDeviceReader.heighthold_input_updated.add_callback(
                self._heighthold_input_updated_signal.emit
            )
            self._helper.inputDeviceReader.hover_input_updated.add_callback(
                self._hover_input_updated_signal.emit
            )
            self._helper.inputDeviceReader.assisted_control_updated.add_callback(
                self._assisted_control_updated_signal.emit
            )
            self._helper.inputDeviceReader.limiting_updated.add_callback(
                self._limiting_updated.emit
            )

        self._pose_data_signal.connect(self._pose_data_received)

        # Connect UI signals that are in this tab
        self.flightModeCombo.currentIndexChanged.connect(self.flightmodeChange)
        self.minThrust.valueChanged.connect(self.minMaxThrustChanged)
        self.maxThrust.valueChanged.connect(self.minMaxThrustChanged)
        self.thrustLoweringSlewRateLimit.valueChanged.connect(
            self.thrustLoweringSlewRateLimitChanged
        )
        self.slewEnableLimit.valueChanged.connect(
            self.thrustLoweringSlewRateLimitChanged
        )
        self.targetCalRoll.valueChanged.connect(self._trim_roll_changed)
        self.targetCalPitch.valueChanged.connect(self._trim_pitch_changed)
        self.maxAngle.valueChanged.connect(self.maxAngleChanged)
        self.maxYawRate.valueChanged.connect(self.maxYawRateChanged)
        self.uiSetupReadySignal.connect(self.uiSetupReady)
        self.isInCrazyFlightmode = False

        # Command Based Flight Control
        self._can_fly_deprecated = 0
        self.commanderTakeOffButton.clicked.connect(
            lambda: self._flight_command(CommanderAction.TAKE_OFF)
        )
        self.commanderLandButton.clicked.connect(
            lambda: self._flight_command(CommanderAction.LAND)
        )
        self.commanderLeftButton.clicked.connect(
            lambda: self._flight_command(CommanderAction.LEFT)
        )
        self.commanderRightButton.clicked.connect(
            lambda: self._flight_command(CommanderAction.RIGHT)
        )
        self.commanderForwardButton.clicked.connect(
            lambda: self._flight_command(CommanderAction.FORWARD)
        )
        self.commanderBackButton.clicked.connect(
            lambda: self._flight_command(CommanderAction.BACK)
        )
        self.commanderUpButton.clicked.connect(
            lambda: self._flight_command(CommanderAction.UP)
        )
        self.commanderDownButton.clicked.connect(
            lambda: self._flight_command(CommanderAction.DOWN)
        )
        self.commanderBox.setEnabled(False)

        # Supervisor
        self._supervisor_info_bitfield = 0
        self.armButton.clicked.connect(self.updateArm)
        self._update_supervisor_and_arming(False)

        self.uiSetupReady()

        self.logAltHold = None

        self.ai = AttitudeIndicator()
        self.verticalLayout_4.addWidget(self.ai)
        self.splitter.setSizes([1000, 1])

        self.targetCalPitch.setValue(Config().get("trim_pitch"))
        self.targetCalRoll.setValue(Config().get("trim_roll"))

        self._tf_state = 0

        # Connect callbacks for input device limiting of roll/pitch/yaw/thrust
        self._limiting_updated.connect(self._set_limiting_enabled)

        if self._helper.pose_logger is not None:
            self._helper.pose_logger.data_received_cb.add_callback(
                self._pose_data_signal.emit
            )

    def _set_limiting_enabled(
        self,
        rp_limiting_enabled: bool,
        yaw_limiting_enabled: bool,
        thrust_limiting_enabled: bool,
    ) -> None:
        self.targetCalRoll.setEnabled(rp_limiting_enabled)
        self.targetCalPitch.setEnabled(rp_limiting_enabled)

        advanced_is_enabled = self.isInCrazyFlightmode
        self.maxAngle.setEnabled(rp_limiting_enabled and advanced_is_enabled)
        self.maxYawRate.setEnabled(yaw_limiting_enabled and advanced_is_enabled)
        self.maxThrust.setEnabled(thrust_limiting_enabled and advanced_is_enabled)
        self.minThrust.setEnabled(thrust_limiting_enabled and advanced_is_enabled)
        self.slewEnableLimit.setEnabled(thrust_limiting_enabled and advanced_is_enabled)
        self.thrustLoweringSlewRateLimit.setEnabled(
            thrust_limiting_enabled and advanced_is_enabled
        )

    def thrustToPercentage(self, thrust: float) -> float:
        return (thrust / MAX_THRUST) * 100.0

    def uiSetupReady(self) -> None:
        flightComboIndex = self.flightModeCombo.findText(
            Config().get("flightmode"), Qt.MatchFlag.MatchFixedString
        )
        if flightComboIndex < 0:
            self.flightModeCombo.setCurrentIndex(0)
            self.flightModeCombo.currentIndexChanged.emit(0)
        else:
            self.flightModeCombo.setCurrentIndex(flightComboIndex)
            self.flightModeCombo.currentIndexChanged.emit(flightComboIndex)

    def _flight_command(self, action: CommanderAction) -> None:
        if self._cf is not None:
            create_task(self._async_flight_command(action))

    async def _async_flight_command(self, action: CommanderAction) -> None:
        pose_logger = self._helper.pose_logger
        current_z = pose_logger.position[2] if pose_logger else 0.0
        move_dist = 0.5
        move_vel = 0.5

        hlc = self._cf.high_level_commander()
        param = self._cf.param()

        if action == CommanderAction.TAKE_OFF:
            await param.set("commander.enHighLevel", 1)
            z_target = current_z + move_dist
            await hlc.take_off(z_target, None, move_dist / move_vel, None)
        elif action == CommanderAction.LAND:
            await hlc.land(0, None, current_z / move_vel, None)
        elif action == CommanderAction.LEFT:
            await hlc.go_to(
                0,
                move_dist,
                0,
                0,
                move_dist / move_vel,
                relative=True,
                linear=False,
                group_mask=None,
            )
        elif action == CommanderAction.RIGHT:
            await hlc.go_to(
                0,
                -move_dist,
                0,
                0,
                move_dist / move_vel,
                relative=True,
                linear=False,
                group_mask=None,
            )
        elif action == CommanderAction.FORWARD:
            await hlc.go_to(
                move_dist,
                0,
                0,
                0,
                move_dist / move_vel,
                relative=True,
                linear=False,
                group_mask=None,
            )
        elif action == CommanderAction.BACK:
            await hlc.go_to(
                -move_dist,
                0,
                0,
                0,
                move_dist / move_vel,
                relative=True,
                linear=False,
                group_mask=None,
            )
        elif action == CommanderAction.UP:
            await hlc.go_to(
                0,
                0,
                move_dist,
                0,
                move_dist / move_vel,
                relative=True,
                linear=False,
                group_mask=None,
            )
        elif action == CommanderAction.DOWN:
            await hlc.go_to(
                0,
                0,
                -move_dist,
                0,
                move_dist / move_vel,
                relative=True,
                linear=False,
                group_mask=None,
            )

    def _log_data_received(self, timestamp: int, data: dict[str, float | int]) -> None:
        if self.isVisible() and self._isConnected:
            self.actualM1.setValue(data[self.LOG_NAME_MOTOR_1])
            self.actualM2.setValue(data[self.LOG_NAME_MOTOR_2])
            self.actualM3.setValue(data[self.LOG_NAME_MOTOR_3])
            self.actualM4.setValue(data[self.LOG_NAME_MOTOR_4])

            self.estimateThrust.setText(
                "%.2f%%" % self.thrustToPercentage(data[self.LOG_NAME_THRUST])
            )

            if data[self.LOG_NAME_CAN_FLY] != self._can_fly_deprecated:
                self._can_fly_deprecated = data[self.LOG_NAME_CAN_FLY]
                if self._cf is not None:
                    create_task(self._update_flight_commander(self._cf))

            if self.LOG_NAME_SUPERVISOR_INFO in data:
                self._supervisor_info_bitfield = data[self.LOG_NAME_SUPERVISOR_INFO]

            self._update_supervisor_and_arming(True)

    def _pose_data_received(
        self, pose_logger: PoseLogger, pose: tuple[float, ...]
    ) -> None:
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

    def _heighthold_input_updated(
        self, roll: float, pitch: float, yaw: float, height: float
    ) -> None:
        if self._helper.inputDeviceReader is None:
            return
        if self.isVisible() and (
            self._helper.inputDeviceReader.get_assisted_control()
            == self._helper.inputDeviceReader.ASSISTED_CONTROL_HEIGHTHOLD
        ):
            self.targetRoll.setText(("%0.2f deg" % roll))
            self.targetPitch.setText(("%0.2f deg" % pitch))
            self.targetYaw.setText(("%0.2f deg/s" % yaw))
            self.targetHeight.setText(("%.2f m" % height))
            self.ai.setHover(height, self.is_visible())

            self._change_input_labels(using_hover_assist=False)

    def _hover_input_updated(
        self, vx: float, vy: float, yaw: float, height: float
    ) -> None:
        if self._helper.inputDeviceReader is None:
            return
        if self.isVisible() and (
            self._helper.inputDeviceReader.get_assisted_control()
            == self._helper.inputDeviceReader.ASSISTED_CONTROL_HOVER
        ):
            self.targetRoll.setText(("%0.2f m/s" % vy))
            self.targetPitch.setText(("%0.2f m/s" % vx))
            self.targetYaw.setText(("%0.2f deg/s" % yaw))
            self.targetHeight.setText(("%.2f m" % height))
            self.ai.setHover(height, self.is_visible())

            self._change_input_labels(using_hover_assist=True)

    def _change_input_labels(self, using_hover_assist: bool) -> None:
        if using_hover_assist:
            pitch, roll, yaw = "Velocity X", "Velocity Y", "Velocity Z"
        else:
            pitch, roll, yaw = "Pitch", "Roll", "Yaw"

        self.inputPitchLabel.setText(pitch)
        self.inputRollLabel.setText(roll)
        self.inputYawLabel.setText(yaw)

    def _update_supervisor_and_arming(self, connected: bool) -> None:
        if not connected:
            self.armButton.setStyleSheet("")
            self.armButton.setText("Arm")
            self.armButton.setEnabled(False)
            self._supervisor_state.setText("")
            self._supervisor_state.setStyleSheet("")
            return

        self._supervisor_state.setText("")
        if self._is_tumbled():
            self._supervisor_state.setText("Tumbled")

        if self._is_locked():
            self.armButton.setText("")
            self.armButton.setEnabled(False)
            self.armButton.setStyleSheet("")
            self._supervisor_state.setText("Locked-please reboot")
            self._supervisor_state.setStyleSheet("background-color: red")
            return
        else:
            self._supervisor_state.setStyleSheet("")

        if self._is_crashed():
            self.armButton.setText("Recover")
            if self._is_tumbled():
                self.armButton.setEnabled(False)
                self.armButton.setStyleSheet("")
                self._supervisor_state.setText("Crashed, flip over to recover")
            else:
                self.armButton.setEnabled(True)
                self.armButton.setStyleSheet("background-color: red")
                self._supervisor_state.setText("Crashed, click Recover")

            self._supervisor_state.setStyleSheet("background-color: red")
            return

        if self._is_flying():
            self.armButton.setEnabled(True)
            self.armButton.setText("Emergency stop")
            self.armButton.setStyleSheet("background-color: red")
            self._supervisor_state.setText("Flying")
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

    async def _update_flight_commander(self, cf: Crazyflie) -> None:
        self.commanderBox.setToolTip(str())
        self.commanderBox.setEnabled(False)

        if self._can_fly_deprecated == 0:
            self.commanderBox.setToolTip(
                "The Crazyflie reports that flight is not possible"
            )
            return

        param = cf.param()

        position_decks = [
            "bcFlow",
            "bcFlow2",
            "bcLighthouse4",
            "bcLoco",
            "bcDWM1000",
        ]
        has_position_deck = False
        for deck in position_decks:
            name = f"deck.{deck}"
            if name in param.names():
                if int(await param.get(name)) == 1:
                    has_position_deck = True
                    break

        if not has_position_deck:
            self.commanderBox.setToolTip(
                "You need a positioning deck to use Command Based Flight"
            )
            return

        # To prevent conflicting commands from the controller and
        # the flight panel
        reader = self._helper.inputDeviceReader
        if reader is not None and reader.available_devices():
            self.commanderBox.setToolTip(
                "Cannot use both a controller and Command Based Flight"
            )
            return

        self.commanderBox.setEnabled(True)

    def connected(self, cf: Crazyflie) -> None:
        self._cf = cf
        self._isConnected = True
        self._log_task = create_task(self._stream_motors(cf))
        self._setup_task = create_task(self._setup_after_connect(cf))

    async def _stream_motors(self, cf: Crazyflie) -> None:
        log = cf.log()
        stream = None
        try:
            block = await log.create_block()
            await block.add_variable(self.LOG_NAME_THRUST)
            await block.add_variable(self.LOG_NAME_MOTOR_1)
            await block.add_variable(self.LOG_NAME_MOTOR_2)
            await block.add_variable(self.LOG_NAME_MOTOR_3)
            await block.add_variable(self.LOG_NAME_MOTOR_4)
            await block.add_variable(self.LOG_NAME_CAN_FLY)

            if self.LOG_NAME_SUPERVISOR_INFO in log.names():
                await block.add_variable(self.LOG_NAME_SUPERVISOR_INFO)

            period_ms = Config().get("ui_update_period")
            stream = await block.start(period_ms)
            while True:
                data = await stream.next()
                self._log_data_received(data.timestamp, data.data)
        except DisconnectedError:
            pass
        finally:
            if stream is not None:
                try:
                    await asyncio.shield(stream.stop())
                except (DisconnectedError, asyncio.CancelledError):
                    pass

    async def _setup_after_connect(self, cf: Crazyflie) -> None:
        param = cf.param()
        platform = cf.platform()

        # Protocol version check for supervisor UI
        protocol_version = await platform.get_protocol_version()
        update_supervisor_info = protocol_version >= 7
        self._supervisor_state.setVisible(update_supervisor_info)
        self._supervisor_label1.setVisible(update_supervisor_info)
        self._supervisor_label2.setVisible(update_supervisor_info)

        # Check imu_sensors
        if "imu_sensors.HMC5883L" in param.names():
            val = await param.get("imu_sensors.HMC5883L")
            self._set_available_sensors("imu_sensors.HMC5883L", val)

        # Populate assisted mode dropdown (reads deck params)
        await self._populate_assisted_mode_dropdown(cf)

        # Update flight commander (reads deck params)
        await self._update_flight_commander(cf)

        self._update_supervisor_and_arming(True)

    def _enable_estimators(self, should_enable: bool) -> None:
        self.estimateX.setEnabled(should_enable)
        self.estimateY.setEnabled(should_enable)
        self.estimateZ.setEnabled(should_enable)

    def _set_available_sensors(self, name: str, available: str) -> None:
        logger.debug("[%s]: %s", name, available)
        available = int(available)

        self._enable_estimators(True)
        if self._helper.inputDeviceReader is not None:
            self._helper.inputDeviceReader.set_alt_hold_available(available)

    def disconnected(self) -> None:
        if self._log_task is not None:
            self._log_task.cancel()
            self._log_task = None
        if self._setup_task is not None:
            self._setup_task.cancel()
            self._setup_task = None
        self._cf = None
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

        try:
            self._assist_mode_combo.currentIndexChanged.disconnect(
                self._assist_mode_changed
            )
        except TypeError:
            # Signal was not connected
            pass
        self._assist_mode_combo.setEnabled(False)
        self._assist_mode_combo.clear()

        self.commanderBox.setEnabled(False)

        self._supervisor_info_bitfield = 0
        self._update_supervisor_and_arming(False)

    def _can_arm(self) -> bool:
        return bool(self._supervisor_info_bitfield & 0x0001)

    def _is_armed(self) -> bool:
        return bool(self._supervisor_info_bitfield & 0x0002)

    def _auto_arming(self) -> bool:
        return bool(self._supervisor_info_bitfield & 0x0004)

    def _can_fly(self) -> bool:
        return bool(self._supervisor_info_bitfield & 0x0008)

    def _is_flying(self) -> bool:
        return bool(self._supervisor_info_bitfield & 0x0010)

    def _is_tumbled(self) -> bool:
        return bool(self._supervisor_info_bitfield & 0x0020)

    def _is_locked(self) -> bool:
        return bool(self._supervisor_info_bitfield & 0x0040)

    def _is_crashed(self) -> bool:
        return bool(self._supervisor_info_bitfield & 0x0080)

    def minMaxThrustChanged(self) -> None:
        if self._helper.inputDeviceReader is None:
            return
        self._helper.inputDeviceReader.min_thrust = self.minThrust.value()
        self._helper.inputDeviceReader.max_thrust = self.maxThrust.value()
        if self.isInCrazyFlightmode is True:
            Config().set("min_thrust", self.minThrust.value())
            Config().set("max_thrust", self.maxThrust.value())

    def thrustLoweringSlewRateLimitChanged(self) -> None:
        if self._helper.inputDeviceReader is None:
            return
        self._helper.inputDeviceReader.thrust_slew_rate = (
            self.thrustLoweringSlewRateLimit.value()
        )
        self._helper.inputDeviceReader.thrust_slew_limit = self.slewEnableLimit.value()
        if self.isInCrazyFlightmode is True:
            Config().set("slew_limit", self.slewEnableLimit.value())
            Config().set("slew_rate", self.thrustLoweringSlewRateLimit.value())

    def maxYawRateChanged(self) -> None:
        logger.debug("MaxYawrate changed to %d", self.maxYawRate.value())
        if self._helper.inputDeviceReader is not None:
            self._helper.inputDeviceReader.max_yaw_rate = self.maxYawRate.value()
        if self.isInCrazyFlightmode is True:
            Config().set("max_yaw", self.maxYawRate.value())

    def maxAngleChanged(self) -> None:
        logger.debug("MaxAngle changed to %d", self.maxAngle.value())
        if self._helper.inputDeviceReader is not None:
            self._helper.inputDeviceReader.max_rp_angle = self.maxAngle.value()
        if self.isInCrazyFlightmode is True:
            Config().set("max_rp", self.maxAngle.value())

    def _trim_pitch_changed(self, value: float) -> None:
        logger.debug("Pitch trim updated to [%f]" % value)
        if self._helper.inputDeviceReader is not None:
            self._helper.inputDeviceReader.trim_pitch = value
        Config().set("trim_pitch", value)

    def _trim_roll_changed(self, value: float) -> None:
        logger.debug("Roll trim updated to [%f]" % value)
        if self._helper.inputDeviceReader is not None:
            self._helper.inputDeviceReader.trim_roll = value
        Config().set("trim_roll", value)

    def calUpdateFromInput(self, rollCal: float, pitchCal: float) -> None:
        logger.debug(
            "Trim changed on joystick: roll=%.2f, pitch=%.2f", rollCal, pitchCal
        )
        self.targetCalRoll.setValue(rollCal)
        self.targetCalPitch.setValue(pitchCal)

    def updateInputControl(
        self, roll: float, pitch: float, yaw: float, thrust: float
    ) -> None:
        self.targetRoll.setText(("%0.2f deg" % roll))
        self.targetPitch.setText(("%0.2f deg" % pitch))
        self.targetYaw.setText(("%0.2f deg/s" % yaw))
        self.targetThrust.setText(("%0.2f %%" % self.thrustToPercentage(thrust)))
        self.thrustProgress.setValue(int(thrust))

        self._change_input_labels(using_hover_assist=False)

    def setMotorLabelsEnabled(self, enabled: bool) -> None:
        self.M1label.setEnabled(enabled)
        self.M2label.setEnabled(enabled)
        self.M3label.setEnabled(enabled)
        self.M4label.setEnabled(enabled)

    def emergencyStopStringWithText(self, text: str) -> str:
        return (
            "<html><head/><body><p>"
            "<span style='font-weight:600; color:#7b0005;'>{}</span>"
            "</p></body></html>".format(text)
        )

    def updateEmergencyStop(self, emergencyStop: bool) -> None:
        if emergencyStop:
            self.setMotorLabelsEnabled(False)
            if self._cf is not None:
                create_task(self._cf.localization().emergency().send_emergency_stop())
        else:
            self.setMotorLabelsEnabled(True)

    def updateArm(self, from_controller: bool = False) -> None:
        if self._cf is not None:
            create_task(self._async_update_arm(from_controller))

    async def _async_update_arm(self, from_controller: bool) -> None:
        if self._is_flying() and not from_controller:
            await self._cf.localization().emergency().send_emergency_stop()
        elif self._is_crashed():
            await self._cf.platform().send_crash_recovery_request()
        elif self._is_armed():
            await self._cf.platform().send_arming_request(False)
        elif self._can_arm():
            self.armButton.setStyleSheet("background-color: orange")
            await self._cf.platform().send_arming_request(True)

    def flightmodeChange(self, item: int) -> None:
        Config().set("flightmode", str(self.flightModeCombo.itemText(item)))
        logger.debug("Changed flightmode to %s", self.flightModeCombo.itemText(item))
        self.isInCrazyFlightmode = False
        if item == 0:  # Normal
            self.maxAngle.setValue(Config().get("normal_max_rp"))
            self.maxThrust.setValue(Config().get("normal_max_thrust"))
            self.minThrust.setValue(Config().get("normal_min_thrust"))
            self.slewEnableLimit.setValue(Config().get("normal_slew_limit"))
            self.thrustLoweringSlewRateLimit.setValue(Config().get("normal_slew_rate"))
            self.maxYawRate.setValue(Config().get("normal_max_yaw"))
        if item == 1:  # Advanced
            self.maxAngle.setValue(Config().get("max_rp"))
            self.maxThrust.setValue(Config().get("max_thrust"))
            self.minThrust.setValue(Config().get("min_thrust"))
            self.slewEnableLimit.setValue(Config().get("slew_limit"))
            self.thrustLoweringSlewRateLimit.setValue(Config().get("slew_rate"))
            self.maxYawRate.setValue(Config().get("max_yaw"))
            self.isInCrazyFlightmode = True

        if item == 0:
            newState = False
        else:
            newState = True
        self.maxThrust.setEnabled(newState)
        self.maxAngle.setEnabled(newState)
        self.minThrust.setEnabled(newState)
        self.thrustLoweringSlewRateLimit.setEnabled(newState)
        self.slewEnableLimit.setEnabled(newState)
        self.maxYawRate.setEnabled(newState)

    def _assist_mode_changed(self, item: int) -> None:
        mode = None

        if item == 0:  # Altitude hold
            mode = JoystickReader.ASSISTED_CONTROL_ALTHOLD
        if item == 1:  # Position hold
            mode = JoystickReader.ASSISTED_CONTROL_POSHOLD
        if item == 2:  # Height hold
            mode = JoystickReader.ASSISTED_CONTROL_HEIGHTHOLD
        if item == 3:  # Hover
            mode = JoystickReader.ASSISTED_CONTROL_HOVER

        if self._helper.inputDeviceReader is not None:
            self._helper.inputDeviceReader.set_assisted_control(mode)
        Config().set("assistedControl", mode)

    def _assisted_control_updated(self, enabled: bool) -> None:
        if self._helper.inputDeviceReader is None:
            return
        if (
            self._helper.inputDeviceReader.get_assisted_control()
            == JoystickReader.ASSISTED_CONTROL_POSHOLD
        ):
            self.targetThrust.setEnabled(not enabled)
            self.targetRoll.setEnabled(not enabled)
            self.targetPitch.setEnabled(not enabled)
        elif (
            self._helper.inputDeviceReader.get_assisted_control()
            == JoystickReader.ASSISTED_CONTROL_HEIGHTHOLD
        ) or (
            self._helper.inputDeviceReader.get_assisted_control()
            == JoystickReader.ASSISTED_CONTROL_HOVER
        ):
            self.targetThrust.setEnabled(not enabled)
            self.targetHeight.setEnabled(enabled)
        else:
            if self._cf is not None:
                create_task(self._cf.param().set("flightmode.althold", int(enabled)))

    async def _populate_assisted_mode_dropdown(self, cf: Crazyflie) -> None:
        param = cf.param()

        self._assist_mode_combo.addItem("Altitude hold", 0)
        self._assist_mode_combo.addItem("Position hold", 1)
        self._assist_mode_combo.addItem("Height hold", 2)
        self._assist_mode_combo.addItem("Hover", 3)

        # Add the tooltips to the assist-mode items.
        self._assist_mode_combo.setItemData(
            0, TOOLTIP_ALTITUDE_HOLD, Qt.ItemDataRole.ToolTipRole
        )
        self._assist_mode_combo.setItemData(
            1, TOOLTIP_POSITION_HOLD, Qt.ItemDataRole.ToolTipRole
        )
        self._assist_mode_combo.setItemData(
            2, TOOLTIP_HEIGHT_HOLD, Qt.ItemDataRole.ToolTipRole
        )
        self._assist_mode_combo.setItemData(
            3, TOOLTIP_HOVER, Qt.ItemDataRole.ToolTipRole
        )

        heightHoldPossible = False
        hoverPossible = False

        if (
            "deck.bcZRanger" in param.names()
            and int(await param.get("deck.bcZRanger")) == 1
        ):
            heightHoldPossible = True
            if self._helper.inputDeviceReader is not None:
                self._helper.inputDeviceReader.set_hover_max_height(1.0)

        if (
            "deck.bcZRanger2" in param.names()
            and int(await param.get("deck.bcZRanger2")) == 1
        ):
            heightHoldPossible = True
            if self._helper.inputDeviceReader is not None:
                self._helper.inputDeviceReader.set_hover_max_height(2.0)

        if "deck.bcFlow" in param.names() and int(await param.get("deck.bcFlow")) == 1:
            heightHoldPossible = True
            hoverPossible = True
            if self._helper.inputDeviceReader is not None:
                self._helper.inputDeviceReader.set_hover_max_height(1.0)

        if (
            "deck.bcFlow2" in param.names()
            and int(await param.get("deck.bcFlow2")) == 1
        ):
            heightHoldPossible = True
            hoverPossible = True
            if self._helper.inputDeviceReader is not None:
                self._helper.inputDeviceReader.set_hover_max_height(2.0)

        if not heightHoldPossible:
            self._assist_mode_combo.model().item(2).setEnabled(False)
        else:
            self._assist_mode_combo.model().item(0).setEnabled(False)

        if not hoverPossible:
            self._assist_mode_combo.model().item(3).setEnabled(False)
        else:
            self._assist_mode_combo.model().item(0).setEnabled(False)

        self._assist_mode_combo.currentIndexChanged.connect(self._assist_mode_changed)
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
                self._assist_mode_combo.currentIndexChanged.emit(assistmodeComboIndex)
        except KeyError:
            defaultOption = 0
            if hoverPossible:
                defaultOption = 3
            elif heightHoldPossible:
                defaultOption = 2
            self._assist_mode_combo.setCurrentIndex(defaultOption)
            self._assist_mode_combo.currentIndexChanged.emit(defaultOption)
