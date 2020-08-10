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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#  02110-1301, USA.
"""
Tab for controlling the Crazyflie using Qualisys Motion Capturing system
"""

import logging
import time
import datetime
import math
from enum import Enum

from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal, pyqtSlot, QObject, pyqtProperty
from PyQt5.QtCore import QStateMachine, QState, QEvent, QTimer
from PyQt5.QtCore import QAbstractTransition
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtGui import QStandardItemModel, QStandardItem

import cfclient
from cfclient.ui.tab import Tab
from cfclient.utils.config import Config
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncLogger import SyncLogger

import xml.etree.cElementTree as ET
import threading

import qtm
import asyncio

__author__ = 'Bitcraze AB'
__all__ = ['QualisysTab']

logger = logging.getLogger(__name__)

qualisys_tab_class, _ = uic.loadUiType(cfclient.module_path +
                                       "/ui/tabs/qualisysTab.ui")


class FlightModeEvent(QEvent):

    def __init__(self, mode, parent=None):
        super(FlightModeEvent, self).__init__(QEvent.Type(QEvent.User + 1))
        self.mode = mode


class FlightModeTransition(QAbstractTransition):

    def __init__(self, value, parent=None):
        super(FlightModeTransition, self).__init__(parent)
        self.value = value

    def eventTest(self, event):
        if event.type() != QEvent.Type(QEvent.User + 1):
            return False

        return event.mode == self.value

    def onTransition(self, event):
        pass


class FlightModeStates(Enum):
    LAND = 0
    LIFT = 1
    FOLLOW = 2
    PATH = 3
    HOVERING = 4
    GROUNDED = 5
    DISCONNECTED = 6
    CIRCLE = 7
    RECORD = 8


def start_async_task(task):
    return asyncio.ensure_future(task)


class QDiscovery(QObject):
    discoveringChanged = pyqtSignal(bool)
    discoveredQTM = pyqtSignal(str, str)

    def __init__(self, *args):
        super().__init__(*args)
        self._discovering = False
        self._found_qtms = {}

    @pyqtProperty(bool, notify=discoveringChanged)
    def discovering(self):
        return self._discovering

    @discovering.setter
    def discovering(self, value):
        if value != self._discovering:
            self._discovering = value
            self.discoveringChanged.emit(value)

    def discover(self, *, interface='0.0.0.0'):
        self.discovering = True
        start_async_task(self._discover_qtm(interface))

    async def _discover_qtm(self, interface):
        try:
            async for qtm_instance in qtm.Discover(interface):
                info = qtm_instance.info.decode("utf-8").split(",")[0]
                self.discoveredQTM.emit(info, qtm_instance.host)

        except Exception as e:
            logger.info("Exception during qtm discovery: %s", e)

        self.discovering = False


class QualisysTab(Tab, qualisys_tab_class):
    """
        Tab for controlling the crazyflie using
        Qualisys Motion Capturing system
    """

    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)
    _log_data_signal = pyqtSignal(int, object, object)
    _log_error_signal = pyqtSignal(object, str)
    _param_updated_signal = pyqtSignal(str, str)
    _imu_data_signal = pyqtSignal(int, object, object)

    _flight_path_select_row = pyqtSignal(int)
    _flight_path_set_model = pyqtSignal(object)
    _path_selector_add_item = pyqtSignal(str)
    _path_selector_set_index = pyqtSignal(int)

    statusChanged = pyqtSignal(str)
    cfStatusChanged = pyqtSignal(str)
    qtmStatusChanged = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        super(QualisysTab, self).__init__(*args)

        # Setting self._qtm_status should not be required here, but for some
        # reason python 3.7.5 crashes without it.
        self._qtm_status = None

        self.setupUi(self)

        self._machine = QStateMachine()
        self._setup_states()
        self._event = threading.Event()

        self.tabName = "Qualisys"
        self.menuName = "Qualisys Tab"
        self.tabWidget = tabWidget
        self.qtm_6DoF_labels = None
        self._helper = helper
        self._qtm_connection = None
        self._cf = None
        self.model = QStandardItemModel(10, 4)

        self._cf_status = self.cfStatusLabel.text()
        self._status = self.statusLabel.text()
        self._qtm_status = self.qtmStatusLabel.text()

        self.flying_enabled = False
        self.switch_flight_mode(FlightModeStates.DISCONNECTED)
        self.path_pos_threshold = 0.2
        self.circle_pos_threshold = 0.1
        self.circle_radius = 1.5
        self.circle_resolution = 15.0
        self.position_hold_timelimit = 0.1
        self.length_from_wand = 2.0
        self.circle_height = 1.2
        self.new_path = []
        self.recording = False
        self.land_for_recording = False
        self.default_flight_paths = [
            [
                "Path 1: Sandbox",
                [0.0, -1.0, 1.0, 0.0],
                [0.0, 1.0, 1.0, 0.0]],
            [
                "Path 2: Height Test",
                [0.0, 0.0, 0.5, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 1.5, 0.0],
                [0.0, 0.0, 2.0, 0.0],
                [0.0, 0.0, 2.3, 0.0],
                [0.0, 0.0, 1.8, 0.0],
                [0.0, 0.0, 0.5, 0.0],
                [0.0, 0.0, 0.3, 0.0],
                [0.0, 0.0, 0.15, 0.0]],
            [
                "Path 3: 'Spiral'",
                [0.0, 0.0, 1.0, 0.0],
                [0.5, 0.5, 1.0, 0.0],
                [0.0, 1.0, 1.0, 0.0],
                [-0.5, 0.5, 1.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.5, 0.5, 1.2, 0.0],
                [0.0, 1.0, 1.4, 0.0],
                [-0.5, 0.5, 1.6, 0.0],
                [0.0, 0.0, 1.8, 0.0],
                [0.5, 0.5, 1.5, 0.0],
                [0.0, 1.0, 1.0, 0.0],
                [-0.5, 0.5, 0.5, 0.0],
                [0.0, 0.0, 0.25, 0.0]]]

        # The position and rotation of the cf and wand obtained by the
        # camera tracking, if it cant be tracked the position becomes Nan
        self.cf_pos = Position(0, 0, 0)
        self.wand_pos = Position(0, 0, 0)

        # The regular cf_pos can a times due to lost tracing become Nan,
        # this the latest known valid cf position
        self.valid_cf_pos = Position(0, 0, 0)

        try:
            self.flight_paths = Config().get("flight_paths")
        except Exception:
            logger.debug("No flight config")
            self.flight_paths = self.default_flight_paths

        if self.flight_paths == []:
            self.flight_paths = self.default_flight_paths

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._connected_signal.connect(self._connected)
        self._disconnected_signal.connect(self._disconnected)
        self._log_data_signal.connect(self._log_data_received)
        self._param_updated_signal.connect(self._param_updated)

        self._flight_path_select_row.connect(self._select_flight_path_row)
        self._flight_path_set_model.connect(self._set_flight_path_model)
        self._path_selector_add_item.connect(self._add_path_selector_item)
        self._path_selector_set_index.connect(self._set_path_selector_index)

        self.statusChanged.connect(self._update_status)
        self.cfStatusChanged.connect(self._update_cf_status)
        self.qtmStatusChanged.connect(self._update_qtm_status)

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(self._connected_signal.emit)

        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

        # Connect the UI elements
        self.connectQtmButton.clicked.connect(self.establish_qtm_connection)
        self.landButton.clicked.connect(self.set_land_mode)
        self.liftButton.clicked.connect(self.set_lift_mode)
        self.followButton.clicked.connect(self.set_follow_mode)
        self.emergencyButton.clicked.connect(self.set_kill_engine)
        self.pathButton.clicked.connect(self.set_path_mode)
        self.circleButton.clicked.connect(self.set_circle_mode)
        self.recordButton.clicked.connect(self.set_record_mode)
        self.removePathButton.clicked.connect(self.remove_current_path)

        for i in range(len(self.flight_paths)):
            self.pathSelector.addItem(self.flight_paths[i][0])

        self.pathSelector.currentIndexChanged.connect(self.path_changed)

        self.quadBox.currentIndexChanged[str].connect(self.quad_changed)
        self.stickBox.currentIndexChanged[str].connect(self.stick_changed)
        self.stickName = 'qstick'
        self.quadName = 'crazyflie'

        # Populate UI elements
        self.posHoldPathBox.setText(str(self.position_hold_timelimit))
        self.radiusBox.setText(str(self.circle_radius))
        self.posHoldCircleBox.setText(str(self.position_hold_timelimit))
        self.resolutionBox.setText(str(self.circle_resolution))
        self.path_changed()

        self._discovery = QDiscovery()
        self._discovery.discoveringChanged.connect(self._is_discovering)
        self._discovery.discoveredQTM.connect(self._qtm_discovered)

        self.discoverQTM.clicked.connect(self._discovery.discover)
        self._discovery.discover()

        self._ui_update_timer = QTimer(self)
        self._ui_update_timer.timeout.connect(self._update_ui)

    def _setup_states(self):
        parent_state = QState()

        # DISCONNECTED
        disconnected = QState(parent_state)
        disconnected.assignProperty(self, "status", "Disabled")
        disconnected.assignProperty(self.pathButton, "text", "Path Mode")
        disconnected.assignProperty(self.followButton, "text", "Follow Mode")
        disconnected.assignProperty(self.circleButton, "text", "Circle Mode")
        disconnected.assignProperty(self.recordButton, "text", "Record Mode")
        disconnected.assignProperty(self.pathButton, "enabled", False)
        disconnected.assignProperty(self.emergencyButton, "enabled", False)
        disconnected.assignProperty(self.landButton, "enabled", False)
        disconnected.assignProperty(self.followButton, "enabled", False)
        disconnected.assignProperty(self.liftButton, "enabled", False)
        disconnected.assignProperty(self.circleButton, "enabled", False)
        disconnected.assignProperty(self.recordButton, "enabled", False)
        disconnected.entered.connect(self._flight_mode_disconnected_entered)

        # HOVERING
        hovering = QState(parent_state)
        hovering.assignProperty(self, "status", "Hovering...")
        hovering.assignProperty(self.pathButton, "text", "Path Mode")
        hovering.assignProperty(self.followButton, "text", "Follow Mode")
        hovering.assignProperty(self.circleButton, "text", "Circle Mode")
        hovering.assignProperty(self.recordButton, "text", "Record Mode")
        hovering.assignProperty(self.pathButton, "enabled", True)
        hovering.assignProperty(self.emergencyButton, "enabled", True)
        hovering.assignProperty(self.landButton, "enabled", True)
        hovering.assignProperty(self.followButton, "enabled", True)
        hovering.assignProperty(self.liftButton, "enabled", False)
        hovering.assignProperty(self.circleButton, "enabled", True)
        hovering.assignProperty(self.recordButton, "enabled", True)
        hovering.entered.connect(self._flight_mode_hovering_entered)

        # GROUNDED
        grounded = QState(parent_state)
        grounded.assignProperty(self, "status", "Landed")
        grounded.assignProperty(self.pathButton, "text", "Path Mode")
        grounded.assignProperty(self.followButton, "text", "Follow Mode")
        grounded.assignProperty(self.circleButton, "text", "Circle Mode")
        grounded.assignProperty(self.recordButton, "text", "Record Mode")
        grounded.assignProperty(self.pathButton, "enabled", True)
        grounded.assignProperty(self.emergencyButton, "enabled", True)
        grounded.assignProperty(self.landButton, "enabled", False)
        grounded.assignProperty(self.followButton, "enabled", False)
        grounded.assignProperty(self.liftButton, "enabled", True)
        grounded.assignProperty(self.circleButton, "enabled", True)
        grounded.assignProperty(self.recordButton, "enabled", True)
        grounded.entered.connect(self._flight_mode_grounded_entered)

        # PATH
        path = QState(parent_state)
        path.assignProperty(self, "status", "Path Mode")
        path.assignProperty(self.pathButton, "text", "Stop")
        path.assignProperty(self.followButton, "text", "Follow Mode")
        path.assignProperty(self.circleButton, "text", "Circle Mode")
        path.assignProperty(self.recordButton, "text", "Record Mode")
        path.assignProperty(self.pathButton, "enabled", True)
        path.assignProperty(self.emergencyButton, "enabled", True)
        path.assignProperty(self.landButton, "enabled", True)
        path.assignProperty(self.followButton, "enabled", False)
        path.assignProperty(self.liftButton, "enabled", False)
        path.assignProperty(self.circleButton, "enabled", False)
        path.assignProperty(self.recordButton, "enabled", False)
        path.entered.connect(self._flight_mode_path_entered)

        # FOLLOW
        follow = QState(parent_state)
        follow.assignProperty(self, "status", "Follow Mode")
        follow.assignProperty(self.pathButton, "text", "Path Mode")
        follow.assignProperty(self.followButton, "text", "Stop")
        follow.assignProperty(self.circleButton, "text", "Circle Mode")
        follow.assignProperty(self.recordButton, "text", "Record Mode")
        follow.assignProperty(self.pathButton, "enabled", False)
        follow.assignProperty(self.emergencyButton, "enabled", True)
        follow.assignProperty(self.landButton, "enabled", True)
        follow.assignProperty(self.followButton, "enabled", False)
        follow.assignProperty(self.liftButton, "enabled", False)
        follow.assignProperty(self.circleButton, "enabled", False)
        follow.assignProperty(self.recordButton, "enabled", False)
        follow.entered.connect(self._flight_mode_follow_entered)

        # LIFT
        lift = QState(parent_state)
        lift.assignProperty(self, "status", "Lifting...")
        lift.assignProperty(self.pathButton, "enabled", False)
        lift.assignProperty(self.emergencyButton, "enabled", True)
        lift.assignProperty(self.landButton, "enabled", True)
        lift.assignProperty(self.followButton, "enabled", False)
        lift.assignProperty(self.liftButton, "enabled", False)
        lift.assignProperty(self.circleButton, "enabled", False)
        lift.assignProperty(self.recordButton, "enabled", False)
        lift.entered.connect(self._flight_mode_lift_entered)

        # LAND
        land = QState(parent_state)
        land.assignProperty(self, "status", "Landing...")
        land.assignProperty(self.pathButton, "enabled", False)
        land.assignProperty(self.emergencyButton, "enabled", True)
        land.assignProperty(self.landButton, "enabled", False)
        land.assignProperty(self.followButton, "enabled", False)
        land.assignProperty(self.liftButton, "enabled", False)
        land.assignProperty(self.circleButton, "enabled", False)
        land.assignProperty(self.recordButton, "enabled", False)
        land.entered.connect(self._flight_mode_land_entered)

        # CIRCLE
        circle = QState(parent_state)
        circle.assignProperty(self, "status", "Circle Mode")
        circle.assignProperty(self.pathButton, "text", "Path Mode")
        circle.assignProperty(self.followButton, "text", "Follow Mode")
        circle.assignProperty(self.circleButton, "text", "Stop")
        circle.assignProperty(self.recordButton, "text", "Record Mode")
        circle.assignProperty(self.pathButton, "enabled", False)
        circle.assignProperty(self.emergencyButton, "enabled", True)
        circle.assignProperty(self.landButton, "enabled", True)
        circle.assignProperty(self.followButton, "enabled", False)
        circle.assignProperty(self.liftButton, "enabled", False)
        circle.assignProperty(self.circleButton, "enabled", True)
        circle.assignProperty(self.recordButton, "enabled", False)
        circle.entered.connect(self._flight_mode_circle_entered)

        # RECORD
        record = QState(parent_state)
        record.assignProperty(self, "status", "Record Mode")
        record.assignProperty(self.pathButton, "text", "Path Mode")
        record.assignProperty(self.followButton, "text", "Follow Mode")
        record.assignProperty(self.circleButton, "text", "Circle Mode")
        record.assignProperty(self.recordButton, "text", "Stop")
        record.assignProperty(self.pathButton, "enabled", False)
        record.assignProperty(self.emergencyButton, "enabled", True)
        record.assignProperty(self.landButton, "enabled", False)
        record.assignProperty(self.followButton, "enabled", False)
        record.assignProperty(self.liftButton, "enabled", False)
        record.assignProperty(self.circleButton, "enabled", False)
        record.assignProperty(self.recordButton, "enabled", True)
        record.entered.connect(self._flight_mode_record_entered)

        def add_transition(mode, child_state, parent):
            transition = FlightModeTransition(mode)
            transition.setTargetState(child_state)
            parent.addTransition(transition)

        add_transition(FlightModeStates.LAND, land, parent_state)
        add_transition(FlightModeStates.LIFT, lift, parent_state)
        add_transition(FlightModeStates.FOLLOW, follow, parent_state)
        add_transition(FlightModeStates.PATH, path, parent_state)
        add_transition(FlightModeStates.HOVERING, hovering, parent_state)
        add_transition(FlightModeStates.GROUNDED, grounded, parent_state)
        add_transition(FlightModeStates.DISCONNECTED, disconnected,
                       parent_state)
        add_transition(FlightModeStates.CIRCLE, circle, parent_state)
        add_transition(FlightModeStates.RECORD, record, parent_state)

        parent_state.setInitialState(disconnected)
        self._machine.addState(parent_state)
        self._machine.setInitialState(parent_state)
        self._machine.start()

    def _update_flight_status(self):
        prev_flying_enabled = self.flying_enabled
        self.flying_enabled = self._cf is not None and \
            self._qtm_connection is not None

        if not prev_flying_enabled and self.flying_enabled:
            self.switch_flight_mode(FlightModeStates.GROUNDED)
            t = threading.Thread(target=self.flight_controller)
            t.start()

        if prev_flying_enabled and not self.flying_enabled:
            self.switch_flight_mode(FlightModeStates.DISCONNECTED)

    def _is_discovering(self, discovering):
        if discovering:
            self.qtmIpBox.clear()
        self.discoverQTM.setEnabled(not discovering)

    def _qtm_discovered(self, info, ip):
        self.qtmIpBox.addItem("{} {}".format(ip, info))

    @pyqtSlot(str)
    def _update_status(self, status):
        self.statusLabel.setText("Status: {}".format(status))

    @pyqtSlot(str)
    def _update_cf_status(self, status):
        self.cfStatusLabel.setText(status)

    @pyqtSlot(str)
    def _update_qtm_status(self, status):
        self.qtmStatusLabel.setText(status)

    @pyqtSlot(str)
    def quad_changed(self, quad):
        self.quadName = quad

    @pyqtSlot(str)
    def stick_changed(self, stick):
        self.stickName = stick

    # Properties

    @pyqtProperty(str, notify=statusChanged)
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if value != self._status:
            self._status = value
            self.statusChanged.emit(value)

    @pyqtProperty(str, notify=qtmStatusChanged)
    def qtmStatus(self):
        return self._qtm_status

    @qtmStatus.setter
    def qtmStatus(self, value):
        if value != self._qtm_status:
            self._qtm_status = value
            self.qtmStatusChanged.emit(value)

    @pyqtProperty(str, notify=cfStatusChanged)
    def cfStatus(self):
        return self._qtm_status

    @cfStatus.setter
    def cfStatus(self, value):
        if value != self._cf_status:
            self._cf_status = value
            self.cfStatusChanged.emit(value)

    def _select_flight_path_row(self, row):
        self.flightPathDataTable.selectRow(row)

    def _set_flight_path_model(self, model):
        self.flightPathDataTable.setModel(model)

    def _add_path_selector_item(self, item):
        self.pathSelector.addItem(item)

    def _set_path_selector_index(self, index):
        self.pathSelector.setCurrentIndex(index)

    def path_changed(self):

        if self.flight_mode == FlightModeStates.PATH:
            self.switch_flight_mode(FlightModeStates.HOVERING)
            time.sleep(0.1)

        # Flight path ui table setup
        self.model = QStandardItemModel(10, 4)
        self.model.setHorizontalHeaderItem(0, QStandardItem('X (m)'))
        self.model.setHorizontalHeaderItem(1, QStandardItem('Y (m)'))
        self.model.setHorizontalHeaderItem(2, QStandardItem('Z (m)'))
        self.model.setHorizontalHeaderItem(3, QStandardItem('Yaw (deg)'))

        # Populate the table with data
        if (len(self.flight_paths) == 0):
            return
        current = self.flight_paths[self.pathSelector.currentIndex()]
        for i in range(1, len(current)):
            for j in range(0, 4):
                self.model.setItem(i - 1, j,
                                   QStandardItem(str(current[i][j])))
        self._flight_path_set_model.emit(self.model)
        Config().set("flight_paths", self.flight_paths)

    def remove_current_path(self):

        if self.flight_mode == FlightModeStates.PATH:
            self.switch_flight_mode(FlightModeStates.HOVERING)
            time.sleep(0.1)
        if len(self.flight_paths) == 0:
            return

        current_index = self.pathSelector.currentIndex()
        answer = QMessageBox.question(
            self, "CFClient: Qualisystab", "Delete the flightpath: {}?".format(
                self.flight_paths[current_index][0]),
            QMessageBox.Yes | QMessageBox.No)

        if answer == QMessageBox.Yes:
            self.flight_paths.pop(current_index)
            self.pathSelector.clear()

            for j in range(len(self.flight_paths)):
                self.pathSelector.addItem(self.flight_paths[j][0])

            if current_index == 0:
                self.pathSelector.setCurrentIndex(0)
            else:
                self.pathSelector.setCurrentIndex(current_index - 1)

            self.path_changed()

    def set_lift_mode(self):
        self.switch_flight_mode(FlightModeStates.LIFT)

    def set_land_mode(self):
        self.switch_flight_mode(FlightModeStates.LAND)

    def set_circle_mode(self):

        # Toggle circle mode on and off

        if self.flight_mode == FlightModeStates.CIRCLE:
            self.switch_flight_mode(FlightModeStates.HOVERING)

        else:
            try:
                self.position_hold_timelimit = float(
                    self.posHoldCircleBox.text())
                self.circle_radius = float(self.radiusBox.text())
                self.circle_resolution = float(self.resolutionBox.text())
                self.circle_pos_threshold = (2 * self.circle_radius * round(
                    math.sin(math.radians(
                        (self.circle_resolution / 2))), 4)) * 2
                logger.info(self.circle_pos_threshold)
            except ValueError as err:
                self.status = ("illegal character used in circle"
                               " settings: {}").format(str(err))
                logger.info(self.status)
                return

            self.switch_flight_mode(FlightModeStates.CIRCLE)

    def set_record_mode(self):
        # Toggle record mode on and off

        if self.flight_mode == FlightModeStates.RECORD:
            # Cancel the recording
            self.recording = False
            self.switch_flight_mode(FlightModeStates.GROUNDED)
            self.land_for_recording = False
        elif self.flight_mode != FlightModeStates.GROUNDED:
            # If the cf is flying, start by landing
            self.land_for_recording = True
            self.switch_flight_mode(FlightModeStates.LAND)
        else:
            self.switch_flight_mode(FlightModeStates.RECORD)

    def set_follow_mode(self):
        # Toggle follow mode on and off

        if self.flight_mode == FlightModeStates.FOLLOW:
            self.switch_flight_mode(FlightModeStates.HOVERING)
        else:
            self.switch_flight_mode(FlightModeStates.FOLLOW)

    def set_path_mode(self):
        logger.info(self.model.item(0, 0))
        # Toggle path mode on and off

        # Path mode on, return to hovering
        if self.flight_mode == FlightModeStates.PATH:
            self.switch_flight_mode(FlightModeStates.HOVERING)

        elif self.model.item(0, 0) is None:
            self.status = "missing Flight Plan"
            return
        # Path mode off, read data from UI table and start path mode
        else:

            try:
                self.position_hold_timelimit = float(
                    self.posHoldPathBox.text())
            except ValueError as err:
                self.status = ("illegal character used in path"
                               " settings: {}").format(str(err))
                logger.info(self.status)
                return

            # Get the flightpath from the GUI table
            x, y = 0, 0
            temp = self.model.item(x, y)
            reading_data = True
            list = ''
            while reading_data:
                try:
                    element = str(temp.text())

                    if element != "":
                        list += temp.text()
                        # a "," gets added after the last element,
                        # remove that later for neatness
                        list += ','
                        try:
                            float(element)
                        except ValueError:
                            self._flight_path_select_row.emit(y)
                            self.status = ("Value at cell x:{} y:{} "
                                           "must be a number").format(x, y)
                            logger.info(self.status)
                            break

                    x += 1
                    if x % 4 == 0:
                        x = 0
                        y += 1
                        # list += temp_position
                        # temp_position = []
                    temp = self.model.item(y, x)

                except Exception:
                    reading_data = False
                    # remove the last "," element
                    list = list[:(len(list) - 1)]
                    list = list.split(',')
                    list = [float(i) for i in list]
                    if (len(list) % 4) != 0:
                        self.status = ("Missing value to create a valid"
                                       " flight path")
                        logger.info(self.status)
                        break
                    list = [list[i:i + 4] for i in range(0, len(list), 4)]
                    list.insert(
                        0,
                        self.flight_paths[self.pathSelector.currentIndex()][0])
                    self.flight_paths[self.pathSelector.currentIndex()] = list
                    Config().set("flight_paths", self.flight_paths)
                    self.switch_flight_mode(FlightModeStates.PATH)

    def set_kill_engine(self):
        self.send_setpoint(Position(0, 0, 0))
        self.switch_flight_mode(FlightModeStates.GROUNDED)
        logger.info('Stop button pressed, kill engines')

    def establish_qtm_connection(self):
        if self.qtmIpBox.count() == 0 and self.qtmIpBox.currentText() == "":
            return

        if self._qtm_connection is None:
            try:
                ip = self.qtmIpBox.currentText().split(" ")[0]
            except Exception as e:
                logger.error("Incorrect entry: %s", e)
                return

            self.connectQtmButton.setEnabled(False)
            start_async_task(self.qtm_connect(ip))

        else:
            self._qtm_connection.disconnect()
            self._qtm_connection = None

    async def qtm_connect(self, ip):

        connection = await qtm.connect(
            ip,
            on_event=self.on_qtm_event,
            on_disconnect=lambda reason: start_async_task(
                self.on_qtm_disconnect(reason)))

        if connection is None:
            start_async_task(self.on_qtm_disconnect("Failed to connect"))
            return

        self._qtm_connection = connection
        await self.setup_qtm_connection()

    def setup_6dof_comboboxes(self):
        quadName = self.quadName
        stickName = self.stickName

        self.quadBox.clear()
        self.stickBox.clear()
        for label in self.qtm_6DoF_labels:
            self.quadBox.addItem(label)
            self.stickBox.addItem(label)

        if quadName in self.qtm_6DoF_labels:
            self.quadBox.setCurrentIndex(
                self.qtm_6DoF_labels.index(quadName))

        if stickName in self.qtm_6DoF_labels:
            self.stickBox.setCurrentIndex(
                self.qtm_6DoF_labels.index(stickName))

    async def setup_qtm_connection(self):
        self.connectQtmButton.setEnabled(True)
        self.connectQtmButton.setText('Disconnect QTM')
        self.qtmStatus = ': connected : Waiting QTM to start sending data'

        try:
            result = await self._qtm_connection.get_parameters(
                parameters=['6d'])

            # Parse the returned xml
            xml = ET.fromstring(result)
            self.qtm_6DoF_labels = [label.text for label in xml.iter('Name')]

            # Make all names lowercase
            self.qtm_6DoF_labels = [x.lower() for x in self.qtm_6DoF_labels]
            logger.info('6Dof bodies active in qtm: {}'.format(
                self.qtm_6DoF_labels))

            self.setup_6dof_comboboxes()

            # Gui
            self.qtmStatus = ': connected'
            self.qtmCfPositionBox.setEnabled(True)
            self.qtmWandPositionBox.setEnabled(True)
            self.discoverQTM.setEnabled(False)
            self.qtmIpBox.setEnabled(False)

            self._update_flight_status()

            self._ui_update_timer.start(200)

            # Make sure this is the last thing done with the qtm_connection
            # (due to qtmRTProtocol structure)
            await self._qtm_connection.stream_frames(
                components=['6deuler', '3d'], on_packet=self.on_packet)

        except Exception as err:
            logger.info(err)

    async def on_qtm_disconnect(self, reason):
        """Callback when QTM has been disconnected"""

        self._ui_update_timer.stop()
        self._update_flight_status()

        self._qtm_connection = None
        logger.info(reason)

        # Gui
        self.qtmCfPositionBox.setEnabled(False)
        self.qtmWandPositionBox.setEnabled(False)
        self.discoverQTM.setEnabled(True)
        self.qtmIpBox.setEnabled(True)
        self.connectQtmButton.setEnabled(True)
        self.connectQtmButton.setText('Connect QTM')
        self.qtmStatus = ': not connected : {}'.format(
            reason if reason is not None else '')

    def on_qtm_event(self, event):
        logger.info(event)
        if event == qtm.QRTEvent.EventRTfromFileStarted:
            self.qtmStatus = ': connected'
            self.qtmCfPositionBox.setEnabled(True)
            self.qtmWandPositionBox.setEnabled(True)

        elif event == qtm.QRTEvent.EventRTfromFileStopped:
            self.qtmStatus = ': connected : Waiting QTM to start sending data'
            self.qtmCfPositionBox.setEnabled(False)
            self.qtmWandPositionBox.setEnabled(False)

    def on_packet(self, packet):
        # Callback when QTM sends a 'packet' of the requested data,
        # one every tracked frame.
        # The speed depends on QTM settings
        header, bodies = packet.get_6d_euler()

        # Cf not created yet or no packet received due to various reasons...
        # Wait for the two asynchronous calls in 'setup connection'
        # to return with data
        if bodies is None or self.qtm_6DoF_labels is None:
            return

        try:
            temp_cf_pos = bodies[self.qtm_6DoF_labels.index(self.quadName)]
            # QTM returns in mm in the order x, y, z, the Crazyflie api need
            # data in meters, divide by thousand
            # QTM returns euler rotations in deg in the order
            # yaw, pitch, roll, not Qualisys Standard!
            self.cf_pos = Position(
                temp_cf_pos[0][0] / 1000,
                temp_cf_pos[0][1] / 1000,
                temp_cf_pos[0][2] / 1000,
                roll=temp_cf_pos[1][2],
                pitch=temp_cf_pos[1][1],
                yaw=temp_cf_pos[1][0])

        except ValueError:
            self.qtmStatus = ' : connected : No 6DoF body found'

        try:
            temp_wand_pos = bodies[self.qtm_6DoF_labels.index(self.stickName)]
            self.wand_pos = Position(
                temp_wand_pos[0][0] / 1000,
                temp_wand_pos[0][1] / 1000,
                temp_wand_pos[0][2] / 1000,
                roll=temp_wand_pos[1][2],
                pitch=temp_wand_pos[1][1],
                yaw=temp_wand_pos[1][0])

        except ValueError:
            self.qtmStatus = ' : connected : No 6DoF body found'

        if self._cf is not None and self.cf_pos.is_valid():
            # If a cf exists and the position is valid
            # Feed the current position of the cf back to the cf to
            # allow for self correction
            self._cf.extpos.send_extpos(self.cf_pos.x, self.cf_pos.y,
                                        self.cf_pos.z)

    def _update_ui(self):
        # Update the data in the GUI
        self.qualisysX.setText(("%0.4f" % self.cf_pos.x))
        self.qualisysY.setText(("%0.4f" % self.cf_pos.y))
        self.qualisysZ.setText(("%0.4f" % self.cf_pos.z))

        self.qualisysRoll.setText(("%0.2f" % self.cf_pos.roll))
        self.qualisysPitch.setText(("%0.2f" % self.cf_pos.pitch))
        self.qualisysYaw.setText(("%0.2f" % self.cf_pos.yaw))

        self.qualisysWandX.setText(("%0.4f" % self.wand_pos.x))
        self.qualisysWandY.setText(("%0.4f" % self.wand_pos.y))
        self.qualisysWandZ.setText(("%0.4f" % self.wand_pos.z))

        self.qualisysWandRoll.setText(("%0.2f" % self.wand_pos.roll))
        self.qualisysWandPitch.setText(("%0.2f" % self.wand_pos.pitch))
        self.qualisysWandYaw.setText(("%0.2f" % self.wand_pos.yaw))

    def _flight_mode_land_entered(self):
        self.current_goal_pos = self.valid_cf_pos
        logger.info('Trying to land at: x: {} y: {}'.format(
            self.current_goal_pos.x, self.current_goal_pos.y))
        self.land_rate = 1
        self._event.set()

    def _flight_mode_path_entered(self):
        self.path_index = 1

        current = self.flight_paths[self.pathSelector.currentIndex()]
        self.current_goal_pos = Position(
            current[self.path_index][0],
            current[self.path_index][1],
            current[self.path_index][2],
            yaw=current[self.path_index][3])
        logger.info('Setting position {}'.format(
            self.current_goal_pos))
        self._flight_path_select_row.emit(self.path_index - 1)
        self._event.set()

    def _flight_mode_circle_entered(self):
        self.current_goal_pos = Position(
            round(math.cos(math.radians(self.circle_angle)),
                  8) * self.circle_radius,
            round(math.sin(math.radians(self.circle_angle)), 8)
            * self.circle_radius,
            self.circle_height,
            yaw=self.circle_angle)

        logger.info('Setting position {}'.format(
            self.current_goal_pos))
        self._event.set()

    def _flight_mode_follow_entered(self):
        self.last_valid_wand_pos = Position(0, 0, 1)
        self._event.set()

    def _flight_mode_record_entered(self):
        self.new_path = []
        self._event.set()

    def _flight_mode_lift_entered(self):
        self.current_goal_pos = self.valid_cf_pos
        logger.info('Trying to lift at: {}'.format(
            self.current_goal_pos))
        self._event.set()

    def _flight_mode_hovering_entered(self):
        self.current_goal_pos = self.valid_cf_pos
        logger.info('Hovering at: {}'.format(
            self.current_goal_pos))
        self._event.set()

    def _flight_mode_grounded_entered(self):
        self._event.set()

    def _flight_mode_disconnected_entered(self):
        self._event.set()

    def flight_controller(self):
        try:
            logger.info('Starting flight controller thread')
            self._cf.param.set_value('stabilizer.estimator', '2')
            self.reset_estimator(self._cf)

            self._cf.param.set_value('flightmode.posSet', '1')

            time.sleep(0.1)

            # The threshold for how many frames without tracking
            # is allowed before the cf's motors are stopped
            lost_tracking_threshold = 100
            frames_without_tracking = 0
            position_hold_timer = 0
            self.circle_angle = 0.0

            # The main flight control loop, the behaviour
            # is controlled by the state of "FlightMode"
            while self.flying_enabled:

                # Check that the position is valid and store it
                if self.cf_pos.is_valid():
                    self.valid_cf_pos = self.cf_pos
                    frames_without_tracking = 0
                else:
                    # if it isn't, count number of frames
                    frames_without_tracking += 1

                    if frames_without_tracking > lost_tracking_threshold:
                        self.switch_flight_mode(FlightModeStates.GROUNDED)
                        self.status = "Tracking lost, turning off motors"
                        logger.info(self.status)

                # If the cf is upside down, kill the motors
                if self.flight_mode != FlightModeStates.GROUNDED and (
                        self.valid_cf_pos.roll > 120
                        or self.valid_cf_pos.roll < -120):
                    self.switch_flight_mode(FlightModeStates.GROUNDED)
                    self.status = "Status: Upside down, turning off motors"
                    logger.info(self.status)

                # Switch on the FlightModeState and take actions accordingly
                # Wait so that any on state change actions are completed
                self._event.wait()

                if self.flight_mode == FlightModeStates.LAND:

                    self.send_setpoint(
                        Position(
                            self.current_goal_pos.x,
                            self.current_goal_pos.y,
                            (self.current_goal_pos.z / self.land_rate),
                            yaw=0))
                    # Check if the cf has reached the  position,
                    # if it has set a new position

                    if self.valid_cf_pos.distance_to(
                            Position(self.current_goal_pos.x,
                                     self.current_goal_pos.y,
                                     self.current_goal_pos.z / self.land_rate
                                     )) < self.path_pos_threshold:
                        self.land_rate *= 1.1

                    if self.land_rate > 1000:
                        self.send_setpoint(Position(0, 0, 0))
                        if self.land_for_recording:
                            # Return the control to the recording mode
                            # after landing
                            mode = FlightModeStates.RECORD
                            self.land_for_recording = False
                        else:
                            # Regular landing
                            mode = FlightModeStates.GROUNDED
                        self.switch_flight_mode(mode)

                elif self.flight_mode == FlightModeStates.PATH:

                    self.send_setpoint(self.current_goal_pos)
                    # Check if the cf has reached the goal position,
                    # if it has set a new goal position
                    if self.valid_cf_pos.distance_to(
                            self.current_goal_pos) < self.path_pos_threshold:

                        if position_hold_timer > self.position_hold_timelimit:

                            current = self.flight_paths[
                                self.pathSelector.currentIndex()]

                            self.path_index += 1
                            if self.path_index == len(current):
                                self.path_index = 1
                            position_hold_timer = 0

                            self.current_goal_pos = Position(
                                current[self.path_index][0],
                                current[self.path_index][1],
                                current[self.path_index][2],
                                yaw=current[self.path_index][3])

                            logger.info('Setting position {}'.format(
                                self.current_goal_pos))
                            self._flight_path_select_row.emit(
                                self.path_index - 1)
                        elif position_hold_timer == 0:

                            time_of_pos_reach = time.time()
                            # Add som time just to get going,
                            # it will be overwritten in the next step.
                            # Setting it higher than the limit
                            # will break the code.
                            position_hold_timer = 0.0001
                        else:
                            position_hold_timer = time.time(
                            ) - time_of_pos_reach

                elif self.flight_mode == FlightModeStates.CIRCLE:
                    self.send_setpoint(self.current_goal_pos)

                    # Check if the cf has reached the goal position,
                    # if it has set a new goal position
                    if self.valid_cf_pos.distance_to(
                            self.current_goal_pos) < self.circle_pos_threshold:

                        if position_hold_timer >= self.position_hold_timelimit:

                            position_hold_timer = 0

                            # increment the angle
                            self.circle_angle = ((self.circle_angle +
                                                  self.circle_resolution)
                                                 % 360)

                            # Calculate the next position in
                            # the circle to fly to
                            self.current_goal_pos = Position(
                                round(
                                    math.cos(math.radians(self.circle_angle)),
                                    4) * self.circle_radius,
                                round(
                                    math.sin(math.radians(self.circle_angle)),
                                    4) * self.circle_radius,
                                self.circle_height,
                                yaw=self.circle_angle)

                            logger.info('Setting position {}'.format(
                                self.current_goal_pos))

                        elif position_hold_timer == 0:

                            time_of_pos_reach = time.time()
                            # Add som time just to get going, it will be
                            # overwritten in the next step.
                            # Setting it higher than the imit will
                            # break the code.
                            position_hold_timer = 0.0001
                        else:
                            position_hold_timer = time.time(
                            ) - time_of_pos_reach

                elif self.flight_mode == FlightModeStates.FOLLOW:

                    if self.wand_pos.is_valid():
                        self.last_valid_wand_pos = self.wand_pos

                        # Fit the angle of the wand in the interval 0-4
                        self.length_from_wand = (2 * (
                            (self.wand_pos.roll + 90) / 180) - 1) + 2
                        self.send_setpoint(
                            Position(
                                self.wand_pos.x + round(
                                    math.cos(math.radians(self.wand_pos.yaw)),
                                    4) * self.length_from_wand,
                                self.wand_pos.y + round(
                                    math.sin(math.radians(self.wand_pos.yaw)),
                                    4) * self.length_from_wand,
                                ((self.wand_pos.z + round(
                                    math.sin(
                                        math.radians(self.wand_pos.pitch)), 4)
                                  * self.length_from_wand) if
                                 ((self.wand_pos.z + round(
                                     math.sin(
                                         math.radians(self.wand_pos.pitch)), 4)
                                   * self.length_from_wand) > 0) else 0)))
                    else:
                        self.length_from_wand = (2 * (
                            (self.last_valid_wand_pos.roll + 90) / 180) -
                                                 1) + 2
                        self.send_setpoint(
                            Position(
                                self.last_valid_wand_pos.x + round(
                                    math.cos(
                                        math.radians(
                                            self.last_valid_wand_pos.yaw)),
                                    4) * self.length_from_wand,
                                self.last_valid_wand_pos.y + round(
                                    math.sin(
                                        math.radians(
                                            self.last_valid_wand_pos.yaw)),
                                    4) * self.length_from_wand,
                                int(self.last_valid_wand_pos.z + round(
                                    math.sin(
                                        math.radians(self.last_valid_wand_pos.
                                                     pitch)), 4) *
                                    self.length_from_wand)))

                elif self.flight_mode == FlightModeStates.LIFT:

                    self.send_setpoint(
                        Position(self.current_goal_pos.x,
                                 self.current_goal_pos.y, 1))

                    if self.valid_cf_pos.distance_to(
                            Position(self.current_goal_pos.x,
                                     self.current_goal_pos.y, 1)) < 0.05:
                        # Wait for hte crazyflie to reach the goal
                        self.switch_flight_mode(FlightModeStates.HOVERING)

                elif self.flight_mode == FlightModeStates.HOVERING:
                    self.send_setpoint(self.current_goal_pos)

                elif self.flight_mode == FlightModeStates.RECORD:

                    if self.valid_cf_pos.z > 1.0 and not self.recording:
                        # Start recording when the cf is lifted
                        self.recording = True
                        # Start the timer thread
                        self.save_current_position()
                        # Gui
                        self.status = "Recording Flightpath"
                        logger.info(self.status)

                    elif self.valid_cf_pos.z < 0.03 and self.recording:
                        # Stop the recording when the cf is put on
                        # the ground again
                        logger.info("Recording stopped")
                        self.recording = False

                        # Remove the last bit (1s) of the recording,
                        # containing setting the cf down
                        for self.path_index in range(20):
                            self.new_path.pop()

                        # Add the new path to list and Gui
                        now = datetime.datetime.fromtimestamp(time.time())

                        new_name = ("Recording {}/{}/{} {}:{}".format(
                            now.year - 2000, now.month
                            if now.month > 9 else "0{}".format(now.month),
                            now.day if now.day > 9 else "0{}".format(now.day),
                            now.hour if now.hour > 9 else "0{}".format(
                                now.hour), now.minute
                            if now.minute > 9 else "0{}".format(now.minute)))

                        self.new_path.insert(0, new_name)
                        self.flight_paths.append(self.new_path)
                        self._path_selector_add_item.emit(new_name)

                        # Select the new path
                        self._path_selector_set_index.emit(
                            len(self.flight_paths) - 1)
                        self.path_changed()
                        Config().set("flight_paths", self.flight_paths)

                        # Wait while the operator moves away
                        self.status = "Replay in 3s"
                        time.sleep(1)
                        self.status = "Replay in 2s"
                        time.sleep(1)
                        self.status = "Replay in 1s"
                        time.sleep(1)
                        # Switch to path mode and replay the recording
                        self.switch_flight_mode(FlightModeStates.PATH)

                elif self.flight_mode == FlightModeStates.GROUNDED:
                    pass  # If gounded, the control is switched back to gamepad

                time.sleep(0.001)

        except Exception as err:
            logger.error(err)
            self.cfStatus = str(err)

        logger.info('Terminating flight controller thread')

    def save_current_position(self):
        if self.recording:
            # Restart the timer
            threading.Timer(0.05, self.save_current_position).start()
            # Save the current position
            self.new_path.append([
                self.valid_cf_pos.x, self.valid_cf_pos.y,
                self.valid_cf_pos.z, self.valid_cf_pos.yaw
            ])

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""

        self._cf = self._helper.cf
        self._update_flight_status()

        logger.debug("Crazyflie connected to {}".format(link_uri))

        # Gui
        self.cfStatus = ': connected'

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""

        logger.info("Crazyflie disconnected from {}".format(link_uri))
        self.cfStatus = ': not connected'
        self._cf = None
        self._update_flight_status()

    def _param_updated(self, name, value):
        """Callback when the registered parameter get's updated"""

        logger.debug("Updated {0} to {1}".format(name, value))

    def _log_data_received(self, timestamp, data, log_conf):
        """Callback when the log layer receives new data"""

        logger.debug("{0}:{1}:{2}".format(timestamp, log_conf.name, data))

    def _logging_error(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""

        QMessageBox.about(
            self, "Example error", "Error when using log config"
            " [{0}]: {1}".format(log_conf.name, msg))

    def wait_for_position_estimator(self, cf):
        logger.info('Waiting for estimator to find stable position...')

        self.cfStatus = (
            'Waiting for estimator to find stable position... '
            '(QTM needs to be connected and providing data)'
        )

        log_config = LogConfig(name='Kalman Variance', period_in_ms=500)
        log_config.add_variable('kalman.varPX', 'float')
        log_config.add_variable('kalman.varPY', 'float')
        log_config.add_variable('kalman.varPZ', 'float')

        var_y_history = [1000] * 10
        var_x_history = [1000] * 10
        var_z_history = [1000] * 10

        threshold = 0.001

        with SyncLogger(cf, log_config) as log:
            for log_entry in log:
                data = log_entry[1]

                var_x_history.append(data['kalman.varPX'])
                var_x_history.pop(0)
                var_y_history.append(data['kalman.varPY'])
                var_y_history.pop(0)
                var_z_history.append(data['kalman.varPZ'])
                var_z_history.pop(0)

                min_x = min(var_x_history)
                max_x = max(var_x_history)
                min_y = min(var_y_history)
                max_y = max(var_y_history)
                min_z = min(var_z_history)
                max_z = max(var_z_history)

                # print("{} {} {}".
                # format(max_x - min_x, max_y - min_y, max_z - min_z))

                if (max_x - min_x) < threshold and (
                        max_y - min_y) < threshold and (
                        max_z - min_z) < threshold:
                    logger.info("Position found with error in, x: {}, y: {}, "
                                "z: {}".format(max_x - min_x,
                                               max_y - min_y,
                                               max_z - min_z))

                    self.cfStatus = ": connected"

                    self.switch_flight_mode(FlightModeStates.GROUNDED)

                    break

    def reset_estimator(self, cf):
        # Reset the kalman filter

        cf.param.set_value('kalman.resetEstimation', '1')
        time.sleep(0.1)
        cf.param.set_value('kalman.resetEstimation', '0')

        self.wait_for_position_estimator(cf)

    def switch_flight_mode(self, mode):
        # Handles the behaviour of switching between flight modes
        self.flight_mode = mode

        # Handle client input control.
        # Disable gamepad input if we are not grounded
        if self.flight_mode in [
            FlightModeStates.GROUNDED,
            FlightModeStates.DISCONNECTED,
            FlightModeStates.RECORD
        ]:
            self._helper.mainUI.disable_input(False)
        else:
            self._helper.mainUI.disable_input(True)

        self._event.clear()
        # Threadsafe call
        self._machine.postEvent(FlightModeEvent(mode))

        logger.info('Switching Flight Mode to: %s', mode)

    def send_setpoint(self, pos):
        # Wraps the send command to the crazyflie
        if self._cf is not None:
            self._cf.commander.send_position_setpoint(pos.x, pos.y, pos.z, 0.0)


class Position:
    def __init__(self, x, y, z, roll=0.0, pitch=0.0, yaw=0.0):
        self.x = x
        self.y = y
        self.z = z
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw

    def distance_to(self, other_point):
        return math.sqrt(
            math.pow(self.x - other_point.x, 2) +
            math.pow(self.y - other_point.y, 2) +
            math.pow(self.z - other_point.z, 2))

    def is_valid(self):
        # Checking if the respective values are nan
        return self.x == self.x and self.y == self.y and self.z == self.z

    def __str__(self):
        return "x: {} y: {} z: {} Roll: {} Pitch: {} Yaw: {}".format(
            self.x, self.y, self.z, self.roll, self.pitch, self.yaw)
