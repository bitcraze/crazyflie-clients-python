#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2021 Bitcraze AB
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
Shows data for the Lighthouse Positioning system
"""

import logging

from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtGui import QMessageBox

import cfclient
from cfclient.ui.tab import Tab

from cflib.crazyflie.mem.lighthouse_memory import LighthouseMemHelper

from vispy import scene
import numpy as np
import math

__author__ = 'Bitcraze AB'
__all__ = ['LighthouseTab']

logger = logging.getLogger(__name__)

lighthouse_tab_class = uic.loadUiType(
    cfclient.module_path + "/ui/tabs/lighthouse_tab.ui")[0]

STYLE_RED_BACKGROUND = "background-color: lightpink;"
STYLE_GREEN_BACKGROUND = "background-color: lightgreen;"
STYLE_NO_BACKGROUND = "background-color: none;"


class MarkerPose():
    COL_X_AXIS = 'red'
    COL_Y_AXIS = 'green'
    COL_Z_AXIS = 'blue'

    AXIS_LEN = 0.3

    LABEL_SIZE = 100
    LABEL_OFFSET = np.array((0.0, 0, 0.25))

    def __init__(self, the_scene, color, text=None):
        self._scene = the_scene
        self._color = color
        self._text = text

        self._marker = scene.visuals.Markers(
            pos=np.array([[0, 0, 0]]),
            parent=self._scene,
            face_color=self._color)

        self._x_axis = scene.visuals.Line(
            pos=np.array([[0, 0, 0], [0, 0, 0]]),
            color=self.COL_X_AXIS,
            parent=self._scene)

        self._y_axis = scene.visuals.Line(pos=np.array(
            [[0, 0, 0], [0, 0, 0]]),
            color=self.COL_Y_AXIS,
            parent=self._scene)

        self._z_axis = scene.visuals.Line(
            pos=np.array([[0, 0, 0], [0, 0, 0]]),
            color=self.COL_Z_AXIS,
            parent=self._scene)

        self._label = None
        if self._text:
            self._label = scene.visuals.Text(
                text=self._text,
                font_size=self.LABEL_SIZE,
                pos=self.LABEL_OFFSET,
                parent=self._scene)

    def set_pose(self, position, rot):
        self._marker.set_data(pos=np.array([position]), face_color=self._color)

        if self._label:
            self._label.pos = self.LABEL_OFFSET + position

        x_tip = np.dot(np.array(rot), np.array([self.AXIS_LEN, 0, 0]))
        self._x_axis.set_data(np.array([position, x_tip + position]), color=self.COL_X_AXIS)

        y_tip = np.dot(np.array(rot), np.array([0, self.AXIS_LEN, 0]))
        self._y_axis.set_data(np.array([position, y_tip + position]), color=self.COL_Y_AXIS)

        z_tip = np.dot(np.array(rot), np.array([0, 0, self.AXIS_LEN]))
        self._z_axis.set_data(np.array([position, z_tip + position]), color=self.COL_Z_AXIS)

    def remove(self):
        self._marker.parent = None
        self._x_axis.parent = None
        self._y_axis.parent = None
        self._z_axis.parent = None
        if self._label:
            self._label.parent = None


class Plot3dLighthouse(scene.SceneCanvas):
    POSITION_BRUSH = np.array((0, 0, 1.0))

    VICINITY_DISTANCE = 2.5
    HIGHLIGHT_DISTANCE = 0.5

    LABEL_SIZE = 100
    LABEL_HIGHLIGHT_SIZE = 200

    HIGHLIGHT_SIZE = 20

    TEXT_OFFSET = np.array((0.0, 0, 0.25))

    def __init__(self):
        scene.SceneCanvas.__init__(self, keys=None)
        self.unfreeze()

        self._view = self.central_widget.add_view()
        self._view.bgcolor = '#ffffff'
        self._view.camera = scene.TurntableCamera(
            distance=10.0,
            up='+z',
            center=(0.0, 0.0, 1.0))

        self._cf = None
        self._base_stations = {}

        self.freeze()

        plane_size = 10
        scene.visuals.Plane(
            width=plane_size,
            height=plane_size,
            width_segments=plane_size,
            height_segments=plane_size,
            color=(0.5, 0.5, 0.5, 0.5),
            edge_color="gray",
            parent=self._view.scene)

        self._addArrows(1, 0.02, 0.1, 0.1, self._view.scene)

    def _addArrows(self, length, width, head_length, head_width, parent):
        # The Arrow visual in vispy does not seem to work very good,
        # draw arrows using lines instead.
        w = width / 2
        hw = head_width / 2
        base_len = length - head_length

        # X-axis
        scene.visuals.LinePlot([
            [0, w, 0],
            [base_len, w, 0],
            [base_len, hw, 0],
            [length, 0, 0],
            [base_len, -hw, 0],
            [base_len, -w, 0],
            [0, -w, 0]],
            width=1.0, color='red', parent=parent)

        # Y-axis
        scene.visuals.LinePlot([
            [w, 0, 0],
            [w, base_len, 0],
            [hw, base_len, 0],
            [0, length, 0],
            [-hw, base_len, 0],
            [-w, base_len, 0],
            [-w, 0, 0]],
            width=1.0, color='green', parent=parent)

        # Z-axis
        scene.visuals.LinePlot([
            [0, w, 0],
            [0, w, base_len],
            [0, hw, base_len],
            [0, 0, length],
            [0, -hw, base_len],
            [0, -w, base_len],
            [0, -w, 0]],
            width=1.0, color='blue', parent=parent)

    def update_cf_pose(self, position, rot):
        if not self._cf:
            self._cf = MarkerPose(self._view.scene, self.POSITION_BRUSH)
        self._cf.set_pose(position, rot)

    def update_base_station_geos(self, geos):
        for id, geo in geos.items():
            if (geo is not None) and (id not in self._base_stations):
                self._base_stations[id] = MarkerPose(self._view.scene, self.POSITION_BRUSH, text=f"{id}")

            self._base_stations[id].set_pose(geo.origin, geo.rotation_matrix)

    def clear(self):
        if self._cf:
            self._cf.remove()
            self._cf = None

        for bs in self._base_stations.values():
            bs.remove()
        self._base_stations = {}

    def _mix(self, col1, col2, mix):
        return col1 * mix + col2 * (1.0 - mix)


class LighthouseTab(Tab, lighthouse_tab_class):
    """Tab for plotting Lighthouse data"""

    # Update period of log data in ms
    UPDATE_PERIOD_LOG = 100

    # Frame rate (updates per second)
    FPS = 2

    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)
    _log_error_signal = pyqtSignal(object, str)
    _cb_param_to_detect_lighthouse_deck_signal = pyqtSignal(object, object)

    def __init__(self, tabWidget, helper, *args):
        super(LighthouseTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Lighthouse Positioning"
        self.menuName = "Lighthouse Positioning Tab"
        self.tabWidget = tabWidget

        self._helper = helper

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._connected_signal.connect(self._connected)
        self._disconnected_signal.connect(self._disconnected)
        self._cb_param_to_detect_lighthouse_deck_signal.connect(
            self._cb_param_to_detect_lighthouse_deck)

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(
            self._connected_signal.emit)

        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

        self._set_up_plots()

        self.is_lighthouse_deck_active = False

        self._lh_memory_helper = None
        self._lh_geos = {}

        self._graph_timer = QTimer()
        self._graph_timer.setInterval(1000 / self.FPS)
        self._graph_timer.timeout.connect(self._update_graphics)
        self._graph_timer.start()

        self._update_position_label(self._helper.pose_logger.position)

    def _set_up_plots(self):
        self._plot_3d = Plot3dLighthouse()
        self._plot_layout.addWidget(self._plot_3d.native)

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        logger.info("Crazyflie connected to {}".format(link_uri))
        self._request_param_to_detect_lighthouse_deck()

    def _request_param_to_detect_lighthouse_deck(self):
        """Send a parameter request to detect if the Lighthouse deck is
        installed"""
        group = 'deck'
        param = 'bcLighthouse4'

        if self._is_in_param_toc(group, param):
            logger.info("Requesting lighthouse deck parameter")
            self._helper.cf.param.add_update_callback(
                group=group, name=param,
                cb=self._cb_param_to_detect_lighthouse_deck_signal.emit)

    def _cb_param_to_detect_lighthouse_deck(self, name, value):
        """Callback from the parameter sub system when the Lighthouse deck detection
        parameter has been updated"""
        if value == '1':
            logger.info("Lighthouse deck installed, enabling the tab")
            self._lighthouse_deck_detected()
        else:
            logger.info("No Lighthouse deck installed")

    def _lighthouse_deck_detected(self):
        """Called when the lighthouse deck has been detected. Enables the tab,
        starts logging and polling of the memory sub system as well as starts
        timers for updating graphics"""
        if not self.is_lighthouse_deck_active:
            self.is_lighthouse_deck_active = True

            # Update basestation position
            self._lh_memory_helper = LighthouseMemHelper(self._helper.cf)
            self._lh_memory_helper.read_all_geos(self._geometry_read_cb)

    def _geometry_read_cb(self, geometries):
        # Do something with it ....
        self._lh_geos = geometries

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        logger.debug("Crazyflie disconnected from {}".format(link_uri))
        self._clear_state()
        self._plot_3d.clear()
        self.is_lighthouse_deck_active = False

    def _is_in_param_toc(self, group, param):
        toc = self._helper.cf.param.toc
        return bool(group in toc.toc and param in toc.toc[group])

    def _logging_error(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""
        QMessageBox.about(self, "LighthouseTab error",
                          "Error when using log config",
                          " [{0}]: {1}".format(log_conf.name, msg))

    def _update_graphics(self):
        if self.is_visible() and self.is_lighthouse_deck_active:
            self._plot_3d.update_cf_pose(self._helper.pose_logger.position,
                                         self._rpy_to_rot(self._helper.pose_logger.rpy))
            self._plot_3d.update_base_station_geos(self._lh_geos)
            self._update_position_label(self._helper.pose_logger.position)

    def _update_position_label(self, position):
        if len(position) == 3:
            coordinate = "({:0.2f}, {:0.2f}, {:0.2f})".format(
                position[0], position[1], position[2])
        else:
            coordinate = '(0.00, 0.00, 0.00)'

        self._status_position.setText(coordinate)

    def _clear_state(self):
        self._lh_memory_helper = None
        self._lh_geos = {}

    def _rpy_to_rot(self, rpy):
        # http://planning.cs.uiuc.edu/node102.html
        # Pitch reversed compared to page above
        roll = rpy[0]
        pitch = rpy[1]
        yaw = rpy[2]

        cg = math.cos(roll)
        cb = math.cos(-pitch)
        ca = math.cos(yaw)
        sg = math.sin(roll)
        sb = math.sin(-pitch)
        sa = math.sin(yaw)

        r = [
            [ca * cb, ca * sb * sg - sa * cg, ca * sb * cg + sa * sg],
            [sa * cb, sa * sb * sg + ca * cg, sa * sb * cg - ca * sg],
            [-sb, cb * sg, cb * cg],
        ]

        return np.array(r)
