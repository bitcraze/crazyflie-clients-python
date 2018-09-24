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

from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtGui import QStandardItemModel, QStandardItem

import cfclient
from cfclient.ui.tab import Tab
from cfclient.utils.config import Config
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.syncLogger import SyncLogger

import xml.etree.cElementTree as ET
import threading

import qtm
import asyncio

__author__ = 'Bitcraze AB'
__all__ = ['QualisysTab']

logger = logging.getLogger(__name__)

qualisys_tab_class, _ = uic.loadUiType(cfclient.module_path + "/ui/tabs/qualisysTab.ui")


class FlightModeStates:
    LAND = 0
    LIFT = 1
    FOLLOW = 2
    PATH = 3
    HOVERING = 4
    GROUNDED = 5
    DISCONNECTED = 6
    CIRCLE = 7
    RECORD = 8

COLOR_BLUE = '#3399ff'
COLOR_GREEN = '#00ff60'
COLOR_RED = '#cc0404'

def progressbar_stylesheet(color):
    return """
        QProgressBar {
            border: 1px solid #AAA;
            background-color: transparent;
        }

        QProgressBar::chunk {
            background-color: """ + color + """;
        }
    """

def start_async_task(task):
    asyncio.ensure_future(task)

class QualisysTab(Tab, qualisys_tab_class):
    """Tab for controlling the crazyflie using Qualisys Motion Capturing system"""

    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)
    _log_data_signal = pyqtSignal(int, object, object)
    _log_error_signal = pyqtSignal(object, str)
    _param_updated_signal = pyqtSignal(str, str)
    _imu_data_signal = pyqtSignal(int, object, object)



    def __init__(self, tabWidget, helper, *args):
        super(QualisysTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Qualisys"
        self.menuName = "Qualisys Tab"
        self.tabWidget = tabWidget
        self.qtm_6DoF_labels = None
        self._helper = helper
        self._qtm_connection = None
        self.scf = None
        self.uri = "80/2M"
        self.model = QStandardItemModel(10, 4)

        self.flying_enabled = False
        self.flight_mode_switched = True
        self.current_flight_mode = FlightModeStates.DISCONNECTED
        self.switch_flight_mode()
        self.cf_ready_to_fly = False
        self.path_pos_threshold = 0.2
        self.circle_pos_threshold = 0.1
        self.circle_radius = 1.5
        self.circle_resolution = 15.0
        self.position_hold_timelimit = 0.1
        self.length_from_wand = 2.0
        self.circle_height = 1.2
        self.new_path = []
        self.recording_in_progress = False
        self.land_for_recording = False
        self.default_flight_paths = [
            ["Path 1: Sandbox",
             [0.0, -1.0, 1.0, 0.0],
             [0.0, 1.0, 1.0, 0.0]
             ],
            ["Path 2: Height Test",
             [0.0, 0.0, 0.5, 0.0],
             [0.0, 0.0, 1.0, 0.0],
             [0.0, 0.0, 1.5, 0.0],
             [0.0, 0.0, 2.0, 0.0],
             [0.0, 0.0, 2.3, 0.0],
             [0.0, 0.0, 1.8, 0.0],
             [0.0, 0.0, 0.5, 0.0],
             [0.0, 0.0, 0.3, 0.0],
             [0.0, 0.0, 0.15, 0.0]
             ],
            ["Path 3: 'Spiral'",
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
             [0.0, 0.0, 0.25, 0.0]
             ]]


        # The position and rotation of the cf and wand obtained by the camera tracking, if it cant be tracked the position becomes Nan
        self.cf_pos = Position(0, 0, 0)
        self.wand_pos = Position(0, 0, 0)

        # The regular cf_pos can a times due to lost tracing become Nan, this the latest known valid cf position
        self.latest_valid_cf_pos = Position(0,0,0)

        try:
            self.flight_paths = Config().get("flight_paths")
        except Exception as err:
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

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(
            self._connected_signal.emit)

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

        self.droneBox.currentIndexChanged[str].connect(self.drone_changed)
        self.stickBox.currentIndexChanged[str].connect(self.stick_changed)
        self.stickName = 'qstick'
        self.droneName = 'crazyflie'

        # Populate UI elements
        self.posHoldPathBox.setText(str(self.position_hold_timelimit))
        self.radiusBox.setText(str(self.circle_radius))
        self.posHoldCircleBox.setText(str(self.position_hold_timelimit))
        self.resolutionBox.setText(str(self.circle_resolution))
        self.path_changed()
        start_async_task(self.discover_qtm_on_network())

    @pyqtSlot(str)
    def drone_changed(self, drone):
        self.droneName = drone

    @pyqtSlot(str)
    def stick_changed(self, stick):
        self.stickName = stick

    def path_changed(self):

        if self.current_flight_mode == FlightModeStates.PATH:
            self.current_flight_mode = FlightModeStates.HOVERING
            self.switch_flight_mode()
            time.sleep(0.1)

        self.model.clear()

        # Flight path ui table setup
        self.model = QStandardItemModel(10, 4)
        self.model.setHorizontalHeaderItem(0, QStandardItem('X (m)'))
        self.model.setHorizontalHeaderItem(1, QStandardItem('Y (m)'))
        self.model.setHorizontalHeaderItem(2, QStandardItem('Z (m)'))
        self.model.setHorizontalHeaderItem(3, QStandardItem('Yaw (deg)'))

        # Populate the table with data
        if(len(self.flight_paths) == 0):
            return
        for i in range(1, len(self.flight_paths[self.pathSelector.currentIndex()])):
            for j in range(0, 4):
                self.model.setItem(i - 1, j, QStandardItem(str(self.flight_paths[self.pathSelector.currentIndex()][i][j])))
        self.flightPathDataTable.setModel(self.model)
        Config().set("flight_paths", self.flight_paths)

    def remove_current_path(self):

        if self.current_flight_mode == FlightModeStates.PATH:
            self.current_flight_mode = FlightModeStates.HOVERING
            self.switch_flight_mode()
            time.sleep(0.1)
        if len(self.flight_paths) == 0:
            return

        current_index = self.pathSelector.currentIndex()
        answer = QMessageBox.question(self, "CFClient: Qualisystab", "Delete the flightpath: {}?".format(self.flight_paths[current_index][0]), QMessageBox.Yes | QMessageBox.No)

        if answer == QMessageBox.Yes:
            self.flight_paths.pop(current_index)
            self.pathSelector.clear()

            for j in range(len(self.flight_paths)):
                self.pathSelector.addItem(self.flight_paths[j][0])

            if current_index == 0:
                self.pathSelector.setCurrentIndex(0)
            else:
                self.pathSelector.setCurrentIndex(current_index-1)

            self.path_changed()

    def set_lift_mode(self):
        self.current_flight_mode = FlightModeStates.LIFT
        self.switch_flight_mode()

    def set_land_mode(self):
        self.current_flight_mode = FlightModeStates.LAND
        self.switch_flight_mode()

    def set_circle_mode(self):

        # Toggle circle mode on and off

        if self.current_flight_mode == FlightModeStates.CIRCLE:
            self.current_flight_mode = FlightModeStates.HOVERING
            self.switch_flight_mode()


        else:
            try:
                self.position_hold_timelimit = float(self.posHoldCircleBox.text())
                self.circle_radius = float(self.radiusBox.text())
                self.circle_resolution = float(self.resolutionBox.text())
                self.circle_pos_threshold = (2 * self.circle_radius * round(math.sin(math.radians((self.circle_resolution/2))),4)) * 2
                logger.info(self.circle_pos_threshold)
            except ValueError as err:
                logger.info("illegal character used: {}".format(str(err)))
                self.statusLabel.setText("Status: illegal character used in circle settings: {}".format(str(err)))
                return

            self.current_flight_mode = FlightModeStates.CIRCLE
            self.switch_flight_mode()

    def set_record_mode(self):
        # Toggle record mode on and off

        if self.current_flight_mode == FlightModeStates.RECORD:
            # Cancel the recording
            self.current_flight_mode = FlightModeStates.GROUNDED
            self.recording_in_progress = False
            self.switch_flight_mode()
            self.land_for_recording = False
        elif self.current_flight_mode != FlightModeStates.GROUNDED:
            # If the cf is flying, start by landing
            self.land_for_recording = True
            self.current_flight_mode = FlightModeStates.LAND
            self.switch_flight_mode()
        else:
            self.current_flight_mode = FlightModeStates.RECORD
            self.switch_flight_mode()

    def set_follow_mode(self):

        # Toggle follow mode on and off

        if self.current_flight_mode == FlightModeStates.FOLLOW:
            self.current_flight_mode = FlightModeStates.HOVERING
            self.switch_flight_mode()
        else:

            self.current_flight_mode = FlightModeStates.FOLLOW
            self.switch_flight_mode()

    def set_path_mode(self):
        logger.info(self.model.item(0, 0))
        # Toggle path mode on and off

        # Path mode on, return to hovering
        if self.current_flight_mode == FlightModeStates.PATH:
            self.current_flight_mode = FlightModeStates.HOVERING
            self.switch_flight_mode()

        elif self.model.item(0, 0) == None:
            self.statusLabel.setText("Status: missing Flight Plan")
            return
        # Path mode off, read data from UI table and start path mode
        else:

            try:
                self.position_hold_timelimit = float(self.posHoldPathBox.text())
            except ValueError as err:
                logger.info("illegal character used: {}".format(str(err)))
                self.statusLabel.setText("Status: illegal character used in path settings: {}".format(str(err)))
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
                        # a "," gets added after the last element, remove that later for neatness
                        list += ','
                        try:
                            float(element)
                        except ValueError:
                            self.flightPathDataTable.selectRow(y)
                            logger.info("Value at cell x:{} y:{} must be a number".format(x, y))
                            self.statusLabel.setText("Flight Path: Value at cell x:{} y:{} must be a number"
                                                               .format(x, y))
                            break

                    x += 1
                    if x % 4 == 0:
                        x = 0
                        y += 1
                        # list += temp_position
                        # temp_position = []
                    temp = self.model.item(y, x)

                except Exception as err:
                    reading_data = False
                    # remove the last "," element
                    list = list[: (len(list) - 1)]
                    list = list.split(',')
                    list = [float(i) for i in list]
                    if (len(list) % 4) != 0:
                        logger.info("Missing value to create a valid flight path")
                        self.statusLabel.setText("Flight Path: Missing value to create a valid flight path")
                        break
                    list = [list[i:i + 4] for i in range(0, len(list), 4)]
                    list.insert(0, self.flight_paths[self.pathSelector.currentIndex()][0])
                    self.flight_paths[self.pathSelector.currentIndex()] = list
                    Config().set("flight_paths", self.flight_paths)
                    self.current_flight_mode = FlightModeStates.PATH
                    self.switch_flight_mode()

    def set_kill_engine(self):
        self.send_setpoint(self.scf, Position(0, 0, 0))
        self.current_flight_mode = FlightModeStates.GROUNDED
        self.switch_flight_mode()
        logger.info('Stop button pressed, kill engines')

    async def discover_qtm_on_network(self):
        async for qtm_instance in qtm.Discover("127.0.0.1"):
            qtm_info = qtm_instance.info.decode('UTF-8').split(",")[0]
            self.qtmIpBox.addItem("{} {}".format(qtm_info, qtm_instance.host ))

    def establish_qtm_connection(self):
        if self.qtmIpBox.count() == 0:
            return

        if self._qtm_connection is None:
            ip = self.qtmIpBox.currentText().split(" ")[1]
            start_async_task(self.qtm_connect(ip))

        else:
            self._qtm_connection.disconnect()
            self._qtm_connection = None

    async def qtm_connect(self, ip):

        connection = await qtm.connect(ip, on_event=self.on_qtm_event, on_disconnect=lambda reason: start_async_task(self.on_qtm_disconnect(reason)))

        if connection is None:
            start_async_task(self.on_qtm_disconnect("Failed to connect"))
            return

        self._qtm_connection = connection
        await self.setup_qtm_connection()

    def setup_6dof_comboboxes(self):
        droneName = self.droneName
        stickName = self.stickName

        self.droneBox.clear()
        self.stickBox.clear()
        for label in self.qtm_6DoF_labels:
            self.droneBox.addItem(label)
            self.stickBox.addItem(label)

        if droneName in self.qtm_6DoF_labels:
            self.droneBox.setCurrentIndex(self.qtm_6DoF_labels.index(droneName))

        if stickName in self.qtm_6DoF_labels:
            self.stickBox.setCurrentIndex(self.qtm_6DoF_labels.index(stickName))

    async def setup_qtm_connection(self):
        self.connectQtmButton.setText('Disconnect QTM')
        self.qtmStatusLabel.setText(': connected : Waiting QTM to start sending data')

        try:
            result = await self._qtm_connection.get_parameters(parameters=['6d'])

            # Parse the returned xml
            xml = ET.fromstring(result)
            self.qtm_6DoF_labels = [label.text for label in xml.iter('Name')]

            # Make all names lowercase
            self.qtm_6DoF_labels =[x.lower() for x in self.qtm_6DoF_labels]
            logger.info('6Dof bodies active in qtm: {}'.format(self.qtm_6DoF_labels))

            self.setup_6dof_comboboxes()

            #Gui
            self.qtmStatusLabel.setText(': connected')
            self.qtmCfPositionBox.setEnabled(True)
            self.qtmWandPositionBox.setEnabled(True)

            if self.cf_ready_to_fly:
                self.current_flight_mode = FlightModeStates.GROUNDED
                self.switch_flight_mode()

            # Make sure this is the last thing done with the qtm_connection (due to qtmRTProtocol structure)
            await self._qtm_connection.stream_frames(components=['6deuler', '3d'], on_packet=self.on_packet)

        except Exception as err:
            logger.info(err)

    async def on_qtm_disconnect(self, reason):
        """Callback when QTM has been disconnected"""

        self._qtm_connection = None
        logger.info(reason)
        self.qtmStatusLabel.setText(str(reason))

        #Gui
        self.qtmCfPositionBox.setEnabled(False)
        self.qtmWandPositionBox.setEnabled(False)
        self.connectQtmButton.setText('Connect QTM')
        self.qtmStatusLabel.setText(': not connected : {}'.format(reason))

        self.current_flight_mode = FlightModeStates.DISCONNECTED
        self.switch_flight_mode()

    def on_qtm_event(self, event):

        logger.info(event)

        if event == qtm.QRTEvent.EventRTfromFileStarted:
            self.qtmStatusLabel.setText(': connected')
            self.qtmCfPositionBox.setEnabled(True)
            self.qtmWandPositionBox.setEnabled(True)

        elif event == qtm.QRTEvent.EventRTfromFileStopped:
            self.qtmStatusLabel.setText(': connected : Waiting QTM to start sending data')
            self.qtmCfPositionBox.setEnabled(False)
            self.qtmWandPositionBox.setEnabled(False)


    def on_packet(self, packet):
        # Callback when QTM sends a 'packet' of the requested data, one every tracked frame.
        # The speed depends on QTM settings
        header, bodies = packet.get_6d_euler()

        # Cf not created yet or no packet received due to various reasons...
        # Wait for the two asynchronous calls in 'setup connection' to return with data
        if bodies is None or self.qtm_6DoF_labels is None:
            return

        try:
            temp_cf_pos = bodies[self.qtm_6DoF_labels.index(self.droneName)]
            # QTM returns in mm in the order x, y, z, the Crazyflie api need data in meters, divide by thousand
            # QTM returns euler rotations in deg in the order yaw, pitch, roll, not Qualisys Standard!
            self.cf_pos = Position(temp_cf_pos[0][0] / 1000, temp_cf_pos[0][1] / 1000,temp_cf_pos[0][2] / 1000,
                                    roll=temp_cf_pos[1][2], pitch=temp_cf_pos[1][1], yaw=temp_cf_pos[1][0])

        except ValueError as err:
            self.qtmStatusLabel.setText(' : connected : No 6DoF body found called \'Crazyflie\'')

        try :
            temp_wand_pos = bodies[self.qtm_6DoF_labels.index(self.stickName)]
            self.wand_pos = Position(temp_wand_pos[0][0] / 1000, temp_wand_pos[0][1] / 1000,temp_wand_pos[0][2] / 1000,
                                        roll=temp_wand_pos[1][2], pitch=temp_wand_pos[1][1], yaw=temp_wand_pos[1][0])

        except ValueError as err:
            self.qtmStatusLabel.setText(' : connected : No 6DoF body found called \'QStick\'')


        if self.scf is not None and self.cf_pos.is_valid():
            # If a scf (syncronous Crazyflie) exists and the position is valid
            # Feed the current position of the cf back to the cf to allow for self correction
            self.scf.cf.extpos.send_extpos(self.cf_pos.x, self.cf_pos.y, self.cf_pos.z)

            #logger.info("\nExtPos data x: {} y: {} z: {}".format(self.cf_pos.x, self.cf_pos.y, self.cf_pos.z))

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

    def flight_controller(self):
        try:
            _scf = SyncCrazyflie(
                "radio://0/{}".format(self.uri), self._helper.cf)

            # init scf
            self.scf = _scf
            cf = self.scf.cf
            self.reset_estimator(self.scf)

            cf.param.set_value('flightmode.posSet', '1')

            time.sleep(0.1)

            # The threshold for how many frames without tracking is allowed before the cf's motors are stopped
            lost_tracking_threshold = 100
            frames_without_tracking = 0
            position_hold_timer = 0
            circle_angle_deg = 0.0


            # The main flight control loop, the behaviour is controlled by the state of "FlightMode"
            while self.flying_enabled:

                # Check that the position is valid and store it
                if self.cf_pos.is_valid():
                    self.latest_valid_cf_pos = self.cf_pos
                    frames_without_tracking = 0
                else:
                    # if it isn't, count number of frames
                    frames_without_tracking += 1

                    if frames_without_tracking > lost_tracking_threshold:
                        self.current_flight_mode = FlightModeStates.GROUNDED
                        self.switch_flight_mode()
                        self.statusLabel.setText("Status: Tracking lost, turning off motors")
                        logger.info('Tracking lost, turning off motors')

                # If the cf is upside down, kill the motors
                if self.current_flight_mode != FlightModeStates.GROUNDED and (self.latest_valid_cf_pos.roll > 120 or self.latest_valid_cf_pos.roll < -120):
                    self.current_flight_mode = FlightModeStates.GROUNDED
                    self.switch_flight_mode()
                    self.statusLabel.setText("Status: Upside down, turning off motors")
                    logger.info('Upside down, turning off motors')


                # Some of the flight modes needs an initial init when they are activated, which is done here
                if self.flight_mode_switched:
                    if self.current_flight_mode == FlightModeStates.LAND:
                            self.current_goal_pos = self.latest_valid_cf_pos
                            logger.info('Trying to land at: x: {} y: {}'.format(self.current_goal_pos.x, self.current_goal_pos.y))
                            land_rate_index = 1

                    elif self.current_flight_mode == FlightModeStates.PATH:
                        i = 1

                        self.current_goal_pos = Position(self.flight_paths[self.pathSelector.currentIndex()][i][0], self.flight_paths[self.pathSelector.currentIndex()][i][1],
                                                            self.flight_paths[self.pathSelector.currentIndex()][i][2], yaw=self.flight_paths[self.pathSelector.currentIndex()][i][3])
                        logger.info(
                            'Setting position {}'.format(self.current_goal_pos))
                        self.flightPathDataTable.selectRow(i-1)

                    elif self.current_flight_mode == FlightModeStates.CIRCLE:

                        self.current_goal_pos = Position(
                            round(math.cos(math.radians(circle_angle_deg)), 8) * self.circle_radius,
                            round(math.sin(math.radians(circle_angle_deg)), 8) * self.circle_radius,
                            self.circle_height, yaw=circle_angle_deg)


                        logger.info(
                            'Setting position {}'.format(self.current_goal_pos))

                    elif self.current_flight_mode == FlightModeStates.FOLLOW:
                        self.last_valid_wand_pos = Position(0, 0, 1)

                    elif self.current_flight_mode == FlightModeStates.RECORD:
                        self.new_path = []

                    elif self.current_flight_mode == FlightModeStates.LIFT:
                        self.current_goal_pos = self.latest_valid_cf_pos
                        logger.info('Trying to lift at: {}'.format(self.current_goal_pos))

                    elif self.current_flight_mode == FlightModeStates.HOVERING:
                        self.current_goal_pos = self.latest_valid_cf_pos
                        logger.info('Hovering at: {}'.format(self.current_goal_pos))

                    elif self.current_flight_mode == FlightModeStates.GROUNDED:
                        pass

                    # Remember to set the flag back to false after the init is done
                    self.flight_mode_switched = False

                # Switch on the FlightModeState and take actions accordingly

                if self.current_flight_mode == FlightModeStates.LAND:

                    self.send_setpoint(self.scf, Position(self.current_goal_pos.x, self.current_goal_pos.y,
                                                            (self.current_goal_pos.z / land_rate_index), yaw=0))
                    # Check if the cf has reached the  position, if it has set a new position

                    if self.latest_valid_cf_pos.distance_to(Position(self.current_goal_pos.x, self.current_goal_pos.y, (self.current_goal_pos.z /
                                                                                                    land_rate_index))) < self.path_pos_threshold:
                        land_rate_index *= 1.1

                    if land_rate_index > 1000:
                        self.send_setpoint(self.scf, Position(0, 0, 0))
                        if self.land_for_recording:
                            # Return the control to the recording mode after landing
                            self.current_flight_mode = FlightModeStates.RECORD
                            self.land_for_recording = False
                        else:
                            # Regular landing
                            self.current_flight_mode = FlightModeStates.GROUNDED

                        self.switch_flight_mode()

                elif self.current_flight_mode == FlightModeStates.PATH:

                    self.send_setpoint(self.scf, self.current_goal_pos)
                    # Check if the cf has reached the goal position, if it has set a new goal position
                    if self.latest_valid_cf_pos.distance_to(self.current_goal_pos) < self.path_pos_threshold:


                        if position_hold_timer > self.position_hold_timelimit:

                            i = (i + 1)
                            if i == (len(self.flight_paths[self.pathSelector.currentIndex()])):
                                i = 1
                            position_hold_timer = 0
                            self.current_goal_pos = Position(self.flight_paths[self.pathSelector.currentIndex()][i][0], self.flight_paths[self.pathSelector.currentIndex()][i][1],
                                                                self.flight_paths[self.pathSelector.currentIndex()][i][2], yaw=self.flight_paths[self.pathSelector.currentIndex()][i][3])


                            logger.info('Setting position {}'.format(self.current_goal_pos))
                            self.flightPathDataTable.selectRow(i-1)
                        elif position_hold_timer == 0:

                            time_of_pos_reach = time.time()
                            # Add som time just to get going, it will be overwritten in the next step. Setting it higher than the imit will break hte code.
                            position_hold_timer = 0.0001
                        else:
                            position_hold_timer = time.time() - time_of_pos_reach

                elif self.current_flight_mode == FlightModeStates.CIRCLE:
                    self.send_setpoint(self.scf, self.current_goal_pos)

                    # Check if the cf has reached the goal position, if it has set a new goal position
                    if self.latest_valid_cf_pos.distance_to(self.current_goal_pos) < self.circle_pos_threshold:

                        if position_hold_timer >= self.position_hold_timelimit:

                            position_hold_timer = 0

                            # increment the angle
                            circle_angle_deg = (circle_angle_deg + self.circle_resolution) % 360

                            # Calculate the next position in the circle to fly to
                            self.current_goal_pos = Position(round(math.cos(math.radians(circle_angle_deg)),4) * self.circle_radius,
                                                                round(math.sin(math.radians(circle_angle_deg)),4) * self.circle_radius,
                                                                self.circle_height, yaw=circle_angle_deg)


                            logger.info('Setting position {}'.format(self.current_goal_pos))

                        elif position_hold_timer == 0:

                            time_of_pos_reach = time.time()
                            # Add som time just to get going, it will be overwritten in the next step.
                            # Setting it higher than the imit will break the code.
                            position_hold_timer = 0.0001
                        else:
                            position_hold_timer = time.time() - time_of_pos_reach

                elif self.current_flight_mode == FlightModeStates.FOLLOW:

                    if self.wand_pos.is_valid():
                        self.last_valid_wand_pos = self.wand_pos

                        # Fit the angle of the wand in the interval 0-4
                        self.length_from_wand = (2*((self.wand_pos.roll + 90)/180)-1) + 2
                        self.send_setpoint(self.scf, Position(self.wand_pos.x +
                                                                round(math.cos(math.radians(self.wand_pos.yaw)),4)
                                                    * self.length_from_wand, self.wand_pos.y +
                                                                round(math.sin(math.radians(self.wand_pos.yaw)),4) *
                                                    self.length_from_wand, ((self.wand_pos.z +
                                                                                round(math.sin(math.radians(self.wand_pos.pitch)),4) *
                                                    self.length_from_wand) if ((self.wand_pos.z +
                                                                                round(math.sin(math.radians(self.wand_pos.pitch)),4) *
                                                    self.length_from_wand) > 0) else 0)))
                    else:
                        self.length_from_wand = (2 * ((self.last_valid_wand_pos.roll + 90) / 180) - 1) + 2
                        self.send_setpoint(self.scf, Position(self.last_valid_wand_pos.x +
                                                                round(math.cos(math.radians(self.last_valid_wand_pos.yaw)), 4)
                                                                * self.length_from_wand, self.last_valid_wand_pos.y +
                                                                round(math.sin(math.radians(self.last_valid_wand_pos.yaw)), 4) *
                                                                self.length_from_wand, int(self.last_valid_wand_pos.z +
                                                                                            round(math.sin(
                                                                                                math.radians(
                                                                                                    self.last_valid_wand_pos.pitch)),
                                                                                                4) *
                                                                                            self.length_from_wand)))

                elif self.current_flight_mode == FlightModeStates.LIFT:

                    self.send_setpoint(self.scf, Position(self.current_goal_pos.x, self.current_goal_pos.y, 1))

                    if self.latest_valid_cf_pos.distance_to(Position(self.current_goal_pos.x, self.current_goal_pos.y, 1)) < 0.05:
                        # Wait for hte crazyflie to reach the goal
                        self.current_flight_mode = FlightModeStates.HOVERING
                        self.switch_flight_mode()

                elif self.current_flight_mode == FlightModeStates.HOVERING:
                    self.send_setpoint(self.scf, self.current_goal_pos)

                elif self.current_flight_mode == FlightModeStates.RECORD:

                    if self.latest_valid_cf_pos.z > 1.0 and not self.recording_in_progress:
                        # Start recording when the cf is lifted
                        self.recording_in_progress = True
                        # Start the timer thread
                        self.save_current_position()
                        # Gui
                        logger.info("Recording flightpath")
                        self.statusLabel.setText("Status: Recording Flightpath")

                    elif self.latest_valid_cf_pos.z < 0.03 and self.recording_in_progress:
                        # Stop the recording when the cf is put on the ground again
                        logger.info("Recording stopped")
                        self.recording_in_progress = False

                        # Remove the last bit (1s) of the recording, containing setting the cf down
                        for i in range(20):
                            self.new_path.pop()

                        # Add the new path to list and Gui
                        now = datetime.datetime.fromtimestamp(time.time())

                        new_name = ("Recording {}/{}/{} {}:{}".format(now.year-2000, now.month if now.month > 9
                        else "0{}".format(now.month), now.day if now.day > 9 else "0{}".format(now.day), now.hour
                        if now.hour > 9 else "0{}".format(now.hour), now.minute if now.minute > 9 else
                        "0{}".format(now.minute)))

                        self.new_path.insert(0, new_name)
                        self.flight_paths.append(self.new_path)
                        self.pathSelector.addItem(new_name)

                        # Select the new path
                        self.pathSelector.setCurrentIndex(len(self.flight_paths) - 1)
                        self.path_changed()
                        Config().set("flight_paths", self.flight_paths)

                        # Wait while the operator moves away
                        self.statusLabel.setText("Status: Replay in 3s")
                        time.sleep(1)
                        self.statusLabel.setText("Status: Replay in 2s")
                        time.sleep(1)
                        self.statusLabel.setText("Status: Replay in 1s")
                        time.sleep(1)
                        # Switch to path mode and replay the recording
                        self.current_flight_mode = FlightModeStates.PATH
                        self.switch_flight_mode()


                elif self.current_flight_mode == FlightModeStates.GROUNDED:
                    # self.send_setpoint(self.scf, Position(0, 0, 0))
                    pass  # If gounded, the control is switched back to gamepad

                time.sleep(0.001)


        except Exception as err:
            logger.info(err)
            self.cfStatusLabel.setText(str(err))

    def save_current_position(self):
        if self.recording_in_progress:
            # Restart the timer
            threading.Timer(0.05, self.save_current_position).start()
            # Save the current position
            self.new_path.append([self.latest_valid_cf_pos.x, self.latest_valid_cf_pos.y, self.latest_valid_cf_pos.z,
                                  self.latest_valid_cf_pos.yaw])

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""

        if not self.flying_enabled:
            self.flying_enabled = True
            self.cfStatusLabel.setText(": connecting...")
            t = threading.Thread(target=self.flight_controller)
            t.start()

        self.uri = link_uri
        logger.debug("Crazyflie connected to {}".format(self.uri))

        #Gui
        self.cfStatusLabel.setText(': connected')
        self.cf_ready_to_fly = True


    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""

        logger.info("Crazyflie disconnected from {}".format(link_uri))
        self.cfStatusLabel.setText(': not connected')
        self.flying_enabled = False
        self.cf_ready_to_fly = False

    def _param_updated(self, name, value):
        """Callback when the registered parameter get's updated"""

        logger.debug("Updated {0} to {1}".format(name, value))

    def _log_data_received(self, timestamp, data, log_conf):
        """Callback when the log layer receives new data"""

        logger.debug("{0}:{1}:{2}".format(timestamp, log_conf.name, data))

    def _logging_error(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""

        QMessageBox.about(self, "Example error",
                          "Error when using log config"
                          " [{0}]: {1}".format(log_conf.name, msg))

    def wait_for_position_estimator(self, scf):
        logger.info('Waiting for estimator to find stable position...')

        self.cfStatusLabel.setText('Waiting for estimator to find stable position... (QTM needs to be connected and providing data)')

        log_config = LogConfig(name='Kalman Variance', period_in_ms=500)
        log_config.add_variable('kalman.varPX', 'float')
        log_config.add_variable('kalman.varPY', 'float')
        log_config.add_variable('kalman.varPZ', 'float')

        var_y_history = [1000] * 10
        var_x_history = [1000] * 10
        var_z_history = [1000] * 10

        threshold = 0.001

        with SyncLogger(scf, log_config) as log:
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

                #print("{} {} {}".
                      #format(max_x - min_x, max_y - min_y, max_z - min_z))

                if (max_x - min_x) < threshold and (
                            max_y - min_y) < threshold and (
                            max_z - min_z) < threshold:
                    logger.info("Position found with error in, x: {}, y: {}, z: {}".
                          format(max_x - min_x, max_y - min_y, max_z - min_z))

                    self.cfStatusLabel.setText(": connected")

                    self.current_flight_mode = FlightModeStates.GROUNDED
                    self.switch_flight_mode()
                    self.cf_ready_to_fly = True

                    break

    def reset_estimator(self, scf):
        # Reset the kalman filter

        cf = scf.cf
        cf.param.set_value('kalman.resetEstimation', '1')
        time.sleep(0.1)
        cf.param.set_value('kalman.resetEstimation', '0')

        self.wait_for_position_estimator(cf)

    def switch_flight_mode(self):
        # Handles the behaviour of switching between flight modes

        # Handle client input control. Disable gamepad input if we are not grounded
        if self.current_flight_mode in [FlightModeStates.GROUNDED, FlightModeStates.DISCONNECTED, FlightModeStates.RECORD]:
            self._helper.mainUI.disable_input(False)
        else:
            self._helper.mainUI.disable_input(True)

        # Set to true to indicate a flight mode switch
        self.flight_mode_switched = True

        if self.current_flight_mode == FlightModeStates.HOVERING:
            self.statusLabel.setText("Status: Hovering...")
            self.pathButton.setText("Path Mode")
            self.followButton.setText("Follow Mode")
            self.circleButton.setText("Circle Mode")
            self.recordButton.setText("Record Mode")
            self.pathButton.setEnabled(True)
            self.emergencyButton.setEnabled(True)
            self.landButton.setEnabled(True)
            self.followButton.setEnabled(True)
            self.liftButton.setEnabled(False)
            self.circleButton.setEnabled(True)
            self.recordButton.setEnabled(True)
            logger.info('Switching Flight Mode to: Hovering')

        elif self.current_flight_mode == FlightModeStates.DISCONNECTED:
            self.statusLabel.setText("Status: Disabled")
            self.pathButton.setText("Path Mode")
            self.followButton.setText("Follow Mode")
            self.circleButton.setText("Circle Mode")
            self.recordButton.setText("Record Mode")
            self.liftButton.setEnabled(False)
            self.emergencyButton.setEnabled(False)
            self.followButton.setEnabled(False)
            self.landButton.setEnabled(False)
            self.pathButton.setEnabled(False)
            self.circleButton.setEnabled(False)
            self.recordButton.setEnabled(False)
            logger.info('Switching Flight Mode to: Disconnected')

        elif self.current_flight_mode == FlightModeStates.GROUNDED:
            self.statusLabel.setText("Status: Landed")
            self.pathButton.setText("Path Mode")
            self.followButton.setText("Follow Mode")
            self.circleButton.setText("Circle Mode")
            self.recordButton.setText("Record Mode")
            self.liftButton.setEnabled(True)
            self.emergencyButton.setEnabled(True)
            self.followButton.setEnabled(True)
            self.pathButton.setEnabled(True)
            self.landButton.setEnabled(False)
            self.circleButton.setEnabled(True)
            self.recordButton.setEnabled(True)
            logger.info('Switching Flight Mode to: Grounded')

        elif self.current_flight_mode == FlightModeStates.PATH:
            self.statusLabel.setText("Status: Path Mode")
            self.circleButton.setText("Circle Mode")
            self.followButton.setText("Follow Mode")
            self.recordButton.setText("Record Mode")
            self.pathButton.setText("Stop")
            self.pathButton.setEnabled(True)
            self.liftButton.setEnabled(False)
            self.emergencyButton.setEnabled(True)
            self.landButton.setEnabled(True)
            self.followButton.setEnabled(False)
            self.circleButton.setEnabled(False)
            self.recordButton.setEnabled(False)
            logger.info('Switching Flight Mode to: Path Mode')


        elif self.current_flight_mode == FlightModeStates.FOLLOW:
            self.statusLabel.setText("Status: Follow Mode")
            self.pathButton.setText("Path Mode")
            self.circleButton.setText("Circle Mode")
            self.recordButton.setText("Record Mode")
            self.followButton.setText("Stop")
            self.liftButton.setEnabled(False)
            self.emergencyButton.setEnabled(True)
            self.landButton.setEnabled(True)
            self.pathButton.setEnabled(False)
            self.circleButton.setEnabled(False)
            self.recordButton.setEnabled(False)
            logger.info('Switching Flight Mode to: Follow Mode')


        elif self.current_flight_mode == FlightModeStates.LIFT:
            self.statusLabel.setText("Status: Lifting...")
            self.liftButton.setEnabled(False)
            self.emergencyButton.setEnabled(True)
            self.landButton.setEnabled(True)
            self.followButton.setEnabled(False)
            self.pathButton.setEnabled(False)
            self.circleButton.setEnabled(False)
            self.recordButton.setEnabled(False)
            logger.info('Switching Flight Mode to: Lift Mode')

        elif self.current_flight_mode == FlightModeStates.LAND:
            self.statusLabel.setText("Status: Landing...")
            self.liftButton.setEnabled(False)
            self.landButton.setEnabled(False)
            self.emergencyButton.setEnabled(True)
            self.followButton.setEnabled(False)
            self.pathButton.setEnabled(False)
            self.circleButton.setEnabled(False)
            self.recordButton.setEnabled(False)
            logger.info('Switching Flight Mode to: Land Mode')

        elif self.current_flight_mode == FlightModeStates.CIRCLE:
            self.statusLabel.setText("Status: Circle Mode")
            self.pathButton.setText("Path Mode")
            self.followButton.setText("Follow Mode")
            self.recordButton.setText("Record Mode")
            self.circleButton.setText("Stop")
            self.liftButton.setEnabled(False)
            self.emergencyButton.setEnabled(True)
            self.landButton.setEnabled(True)
            self.pathButton.setEnabled(False)
            self.followButton.setEnabled(False)
            self.circleButton.setEnabled(True)
            self.recordButton.setEnabled(False)
            logger.info('Switching Flight Mode to: Cricle Mode')


        elif self.current_flight_mode == FlightModeStates.RECORD:
            self.statusLabel.setText("Status: Record Mode")
            self.pathButton.setText("Path Mode")
            self.followButton.setText("Follow Mode")
            self.circleButton.setText("Circle Mode")
            self.recordButton.setText("Stop")
            self.liftButton.setEnabled(False)
            self.emergencyButton.setEnabled(True)
            self.landButton.setEnabled(False)
            self.pathButton.setEnabled(False)
            self.followButton.setEnabled(False)
            self.circleButton.setEnabled(False)
            self.recordButton.setEnabled(True)
            logger.info('Switching Flight Mode to: Record Mode')


    def send_setpoint(self, scf_, pos):
        # Wraps the send command to the crazyflie

        # The 'send_setpoint' function strangely takes the arguments in the order (Y, X, Yaw, Z)
        # scf_.cf.commander.send_setpoint(pos.y, pos.x, pos.yaw, int(pos.z *1000))
        scf_.cf.commander.send_setpoint(pos.y, pos.x, 0, int(pos.z * 1000))
        pass


class Position:

    def __init__(self, x, y, z, roll=0.0, pitch=0.0, yaw=0.0):
        self.x = x
        self.y = y
        self.z = z
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw

    def distance_to(self, other_point):
        return math.sqrt(math.pow(self.x - other_point.x, 2) + math.pow(self.y - other_point.y, 2) +
                         math.pow(self.z - other_point.z, 2))

    def is_valid(self):
        # Checking if the respective values are nan
        return self.x == self.x and self.y == self.y and self.z == self.z

    def __str__(self):
        return "x: {} y: {} z: {} Roll: {} Pitch: {} Yaw: {}".format(self.x, self.y, self. z,
                                                                     self.roll, self.pitch, self.yaw)
