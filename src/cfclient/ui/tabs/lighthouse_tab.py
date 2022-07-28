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
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtWidgets import QLabel

import cfclient
from cfclient.ui.tab import Tab

from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.mem import LighthouseMemHelper
from cflib.localization import LighthouseConfigWriter
from cflib.localization import LighthouseConfigFileManager

from cfclient.ui.dialogs.lighthouse_bs_geometry_dialog import LighthouseBsGeometryDialog
from cfclient.ui.dialogs.basestation_mode_dialog import LighthouseBsModeDialog
from cfclient.ui.dialogs.lighthouse_system_type_dialog import LighthouseSystemTypeDialog

from vispy import scene
import numpy as np
import math
import os

__author__ = 'Bitcraze AB'
__all__ = ['LighthouseTab']

logger = logging.getLogger(__name__)

lighthouse_tab_class = uic.loadUiType(
    cfclient.module_path + "/ui/tabs/lighthouse_tab.ui")[0]

STYLE_RED_BACKGROUND = "background-color: lightpink;"
STYLE_GREEN_BACKGROUND = "background-color: lightgreen;"
STYLE_BLUE_BACKGROUND = "background-color: lightblue;"
STYLE_ORANGE_BACKGROUND = "background-color: orange;"
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

    def set_color(self, color):
        self._color = color
        self._marker.set_data(face_color=self._color)


class Plot3dLighthouse(scene.SceneCanvas):
    POSITION_BRUSH = np.array((0, 0, 1.0))
    BS_BRUSH_VISIBLE = np.array((0.2, 0.5, 0.2))
    BS_BRUSH_NOT_VISIBLE = np.array((0.8, 0.5, 0.5))

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
            width=1.0, color='red', parent=parent, marker_size=0.0)

        # Y-axis
        scene.visuals.LinePlot([
            [w, 0, 0],
            [w, base_len, 0],
            [hw, base_len, 0],
            [0, length, 0],
            [-hw, base_len, 0],
            [-w, base_len, 0],
            [-w, 0, 0]],
            width=1.0, color='green', parent=parent, marker_size=0.0)

        # Z-axis
        scene.visuals.LinePlot([
            [0, w, 0],
            [0, w, base_len],
            [0, hw, base_len],
            [0, 0, length],
            [0, -hw, base_len],
            [0, -w, base_len],
            [0, -w, 0]],
            width=1.0, color='blue', parent=parent, marker_size=0.0)

    def update_cf_pose(self, position, rot):
        if not self._cf:
            self._cf = MarkerPose(self._view.scene, self.POSITION_BRUSH)
        self._cf.set_pose(position, rot)

    def update_base_station_geos(self, geos):
        for id, geo in geos.items():
            if (geo is not None) and (id not in self._base_stations):
                self._base_stations[id] = MarkerPose(self._view.scene, self.BS_BRUSH_NOT_VISIBLE, text=f"{id + 1}")
            self._base_stations[id].set_pose(geo.origin, geo.rotation_matrix)

        geos_to_remove = self._base_stations.keys() - geos.keys()
        for id in geos_to_remove:
            existing = self._base_stations.pop(id)
            existing.remove()

    def update_base_station_visibility(self, visibility):
        for id, bs in self._base_stations.items():
            if id in visibility:
                bs.set_color(self.BS_BRUSH_VISIBLE)
            else:
                bs.set_color(self.BS_BRUSH_NOT_VISIBLE)

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

    STATUS_NOT_RECEIVING = 0
    STATUS_MISSING_DATA = 1
    STATUS_TO_ESTIMATOR = 2

    # TODO change these names to something more logical
    LOG_STATUS = "lighthouse.status"
    LOG_RECEIVE = "lighthouse.bsReceive"
    LOG_CALIBRATION_EXISTS = "lighthouse.bsCalVal"
    LOG_CALIBRATION_CONFIRMED = "lighthouse.bsCalCon"
    LOG_CALIBRATION_UPDATED = "lighthouse.bsCalUd"
    LOG_GEOMETERY_EXISTS = "lighthouse.bsGeoVal"
    LOG_ACTIVE = "lighthouse.bsActive"

    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)
    _log_error_signal = pyqtSignal(object, str)
    _status_report_signal = pyqtSignal(int, object, object)
    _new_system_config_written_to_cf_signal = pyqtSignal(bool)
    _geometry_read_signal = pyqtSignal(object)
    _calibration_read_signal = pyqtSignal(object)

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
        self._log_error_signal.connect(self._logging_error)
        self._status_report_signal.connect(self._status_report_received)
        self._new_system_config_written_to_cf_signal.connect(self._new_system_config_written_to_cf)
        self._geometry_read_signal.connect(self._geometry_read_cb)
        self._calibration_read_signal.connect(self._calibration_read_cb)

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(self._connected_signal.emit)
        self._helper.cf.disconnected.add_callback(self._disconnected_signal.emit)

        self._set_up_plots()

        self.is_lighthouse_deck_active = False

        self._lh_memory_helper = None
        self._lh_config_writer = None
        self._lh_geos = {}
        self._is_geometry_read_ongoing = False

        self._bs_receives_light = set()
        self._bs_calibration_data_exists = set()
        self._bs_calibration_data_confirmed = set()
        self._bs_calibration_data_updated = set()
        self._bs_geometry_data_exists = set()
        self._bs_data_to_estimator = set()

        self._clear_state_indicator()

        self._bs_stats = [
            self._bs_receives_light,
            self._bs_calibration_data_exists,
            self._bs_calibration_data_confirmed,
            self._bs_calibration_data_updated,
            self._bs_geometry_data_exists,
            self._bs_data_to_estimator]

        self._lh_status = self.STATUS_NOT_RECEIVING

        self._graph_timer = QTimer()
        self._graph_timer.setInterval(int(1000 / self.FPS))
        self._graph_timer.timeout.connect(self._update_graphics)
        self._graph_timer.start()

        self._basestation_geometry_dialog = LighthouseBsGeometryDialog(self)
        self._basestation_mode_dialog = LighthouseBsModeDialog(self)
        self._system_type_dialog = LighthouseSystemTypeDialog(helper)

        self._manage_estimate_geometry_button.clicked.connect(self._show_basestation_geometry_dialog)
        self._change_system_type_button.clicked.connect(lambda: self._system_type_dialog.show())
        self._manage_basestation_mode_button.clicked.connect(self._show_basestation_mode_dialog)

        self._load_sys_config_button.clicked.connect(self._load_sys_config_button_clicked)
        self._save_sys_config_button.clicked.connect(self._save_sys_config_button_clicked)

        self._is_connected = False
        self._update_ui()

    def write_and_store_geometry(self, geometries):
        if self._lh_config_writer:
            self._lh_config_writer.write_and_store_config(self._new_system_config_written_to_cf_signal.emit,
                                                          geos=geometries)

    def _new_system_config_written_to_cf(self, success):
        # Reset the bit fields for calibration data status to get a fresh view
        self._helper.cf.param.set_value("lighthouse.bsCalibReset", '1')
        # New geo data has been written and stored in the CF, read it back to update the UI
        self._start_read_of_geo_data()

    def _show_basestation_geometry_dialog(self):
        self._basestation_geometry_dialog.reset()
        self._basestation_geometry_dialog.show()

    def _show_basestation_mode_dialog(self):
        self._basestation_mode_dialog.reset()
        self._basestation_mode_dialog.show()

    def _set_up_plots(self):
        self._plot_3d = Plot3dLighthouse()
        self._plot_layout.addWidget(self._plot_3d.native)

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        logger.info("Crazyflie connected to {}".format(link_uri))

        self._basestation_geometry_dialog.reset()
        self._is_connected = True

        if self._helper.cf.param.get_value('deck.bcLighthouse4') == '1':
            self._lighthouse_deck_detected()

        self._update_ui()

    def _lighthouse_deck_detected(self):
        """Called when the lighthouse deck has been detected. Enables the tab,
        starts logging and polling of the memory sub system as well as starts
        timers for updating graphics"""
        if not self.is_lighthouse_deck_active:
            self.is_lighthouse_deck_active = True

            try:
                self._register_logblock(
                    "lhStatus",
                    [self.LOG_STATUS, self.LOG_RECEIVE, self.LOG_CALIBRATION_EXISTS, self.LOG_CALIBRATION_CONFIRMED,
                        self.LOG_CALIBRATION_UPDATED, self.LOG_GEOMETERY_EXISTS, self.LOG_ACTIVE],
                    self._status_report_signal.emit,
                    self._log_error_signal.emit)
            except KeyError as e:
                logger.warning(str(e))
            except AttributeError as e:
                logger.warning(str(e))

            try:
                bs_available_mask = int(self._helper.cf.param.get_value('lighthouse.bsAvailable'))
            except KeyError as e:
                # Old firmware that does not support lighthouse.bsAvailable, set to bs 1 and 2 for backwards
                # compatibility
                bs_available_mask = 0x3
                logger.warning(str(e))
            self._populate_status_matrix(bs_available_mask)

            # Now that we know we have a lighthouse deck, setup the memory helper and config writer
            self._lh_memory_helper = LighthouseMemHelper(self._helper.cf)
            self._lh_config_writer = LighthouseConfigWriter(self._helper.cf)

    def _start_read_of_geo_data(self):
        if not self._is_geometry_read_ongoing:
            self._is_geometry_read_ongoing = True
            self._lh_memory_helper.read_all_geos(self._geometry_read_signal.emit)

    def _geometry_read_cb(self, geometries):
        # Remove any geo data where the valid flag is False
        self._lh_geos = dict(filter(lambda key_value: key_value[1].valid, geometries.items()))
        self._basestation_geometry_dialog.geometry_updated(self._lh_geos)
        self._is_geometry_read_ongoing = False

    def _is_matching_current_geo_data(self, geometries):
        return geometries == self._lh_geos.keys()

    def _adjust_bitmask(self, bit_mask, bs_list):
        for id in range(16):
            if bit_mask & (1 << id):
                bs_list.add(id)
            else:
                if id in bs_list:
                    bs_list.remove(id)

    def _status_report_received(self, timestamp, data, logconf):
        """Callback from the logging system when the status is updated."""

        if self.LOG_RECEIVE in data:
            bit_mask = data[self.LOG_RECEIVE]
            self._adjust_bitmask(bit_mask, self._bs_receives_light)
        if self.LOG_CALIBRATION_EXISTS in data:
            bit_mask = data[self.LOG_CALIBRATION_EXISTS]
            self._adjust_bitmask(bit_mask, self._bs_calibration_data_exists)
        if self.LOG_CALIBRATION_CONFIRMED in data:
            bit_mask = data[self.LOG_CALIBRATION_CONFIRMED]
            self._adjust_bitmask(bit_mask, self._bs_calibration_data_confirmed)
        if self.LOG_CALIBRATION_UPDATED in data:
            bit_mask = data[self.LOG_CALIBRATION_UPDATED]
            self._adjust_bitmask(bit_mask, self._bs_calibration_data_updated)
        if self.LOG_GEOMETERY_EXISTS in data:
            bit_mask = data[self.LOG_GEOMETERY_EXISTS]
            self._adjust_bitmask(bit_mask, self._bs_geometry_data_exists)
            if not self._is_matching_current_geo_data(self._bs_geometry_data_exists):
                self._start_read_of_geo_data()

        if self.LOG_ACTIVE in data:
            bit_mask = data[self.LOG_ACTIVE]
            self._adjust_bitmask(bit_mask, self._bs_data_to_estimator)

        if self.LOG_STATUS in data:
            self._lh_status = data[self.LOG_STATUS]

        self._update_basestation_status_indicators()

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        logger.debug("Crazyflie disconnected from {}".format(link_uri))
        self._clear_state()
        self._update_graphics()
        self._plot_3d.clear()
        self._basestation_geometry_dialog.close()
        self.is_lighthouse_deck_active = False
        self._is_connected = False
        self._update_ui()

    def _register_logblock(self, logblock_name, variables, data_cb, error_cb,
                           update_period=UPDATE_PERIOD_LOG):
        """Register log data to listen for. One logblock can only contain a limited
        number of parameters."""
        lg = LogConfig(logblock_name, update_period)
        for variable in variables:
            if self._is_in_log_toc(variable):
                lg.add_variable(variable)

        self._helper.cf.log.add_config(lg)
        lg.data_received_cb.add_callback(data_cb)
        lg.error_cb.add_callback(error_cb)
        lg.start()
        return lg

    def _is_in_log_toc(self, variable):
        toc = self._helper.cf.log.toc
        group, param = variable.split('.')
        return group in toc.toc and param in toc.toc[group]

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
                                         self._rpy_to_rot(self._helper.pose_logger.rpy_rad))
            self._plot_3d.update_base_station_geos(self._lh_geos)
            self._plot_3d.update_base_station_visibility(self._bs_data_to_estimator)
            self._update_position_label(self._helper.pose_logger.position)
            self._update_status_label(self._lh_status)

    def _update_ui(self):
        enabled = self._is_connected and self.is_lighthouse_deck_active
        self._manage_estimate_geometry_button.setEnabled(enabled)
        self._change_system_type_button.setEnabled(enabled)
        self._load_sys_config_button.setEnabled(enabled)
        self._save_sys_config_button.setEnabled(enabled)

    def _update_position_label(self, position):
        if len(position) == 3:
            coordinate = "({:0.2f}, {:0.2f}, {:0.2f})".format(
                position[0], position[1], position[2])
        else:
            coordinate = '(0.00, 0.00, 0.00)'

        self._status_position.setText(coordinate)

    def _update_status_label(self, status):
        text = ''
        if status == self.STATUS_NOT_RECEIVING:
            text = 'Not receiving'
        elif status == self.STATUS_MISSING_DATA:
            text = 'No geo/calib'
        elif status == self.STATUS_TO_ESTIMATOR:
            text = 'LH ready'

        self._status_status.setText(text)

    def _clear_state(self):
        self._lh_memory_helper = None
        self._lh_config_writer = None
        self._lh_geos = {}
        self._is_geometry_read_ongoing = False
        self._bs_receives_light.clear()
        self._bs_calibration_data_exists.clear()
        self._bs_calibration_data_confirmed.clear()
        self._bs_calibration_data_updated.clear()
        self._bs_geometry_data_exists.clear()
        self._bs_data_to_estimator.clear()
        self._update_basestation_status_indicators()
        self._clear_state_indicator()
        self._lh_status = self.STATUS_NOT_RECEIVING

    def _clear_state_indicator(self):
        container = self._basestation_stats_container
        for row in range(0, 5):
            for col in range(1, 17):
                item = container.itemAtPosition(row, col)
                if item is not None:
                    item.widget().deleteLater()

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

    def _populate_status_matrix(self, bs_available_mask):
        container = self._basestation_stats_container

        # Find the nr of base stations by looking for the highest bit that is set
        # Assume all bs up to that bit are available
        for bs in range(0, 16):
            if bs_available_mask & (1 << bs) == 0:
                break

            container.addWidget(self._create_label(str(bs + 1)), 0, bs + 1)
            for i in range(1, 5):
                container.addWidget(self._create_label(), i, bs + 1)

    def _create_label(self, text=None):
        label = QLabel()
        label.setMinimumSize(30, 0)
        label.setAlignment(Qt.AlignCenter)

        if text:
            label.setText(str(text))
        else:
            label.setProperty('frameShape', 'QFrame::Box')
            label.setStyleSheet(STYLE_NO_BACKGROUND)

        return label

    def _update_basestation_status_indicators(self):
        """Handling the basestation status label handles to indicate
            the state of received data per basestation"""
        container = self._basestation_stats_container

        # Ports the label number to the first index of the statistic id
        stats_id_port = {1: 0, 2: 1, 3: 4, 4: 5}

        for bs in range(16):
            for stats_indicator_id in range(1, 5):
                bs_indicator_id = bs + 1
                item = container.itemAtPosition(stats_indicator_id, bs_indicator_id)
                if item is not None:
                    label = item.widget()
                    stats_id = stats_id_port.get(stats_indicator_id)
                    temp_set = self._bs_stats[stats_id]

                    if bs in temp_set:
                        # If the status bar for calibration data is handled, have an intermediate status
                        # else just have red or green.
                        if stats_indicator_id == 2:
                            label.setStyleSheet(STYLE_BLUE_BACKGROUND)
                            label.setToolTip('Calibration data from cache')

                            calib_confirm = bs in self._bs_stats[stats_id + 1]
                            calib_updated = bs in self._bs_stats[stats_id + 2]

                            if calib_confirm:
                                label.setStyleSheet(STYLE_GREEN_BACKGROUND)
                                label.setToolTip('Calibration data verified')
                            if calib_updated:
                                label.setStyleSheet(STYLE_ORANGE_BACKGROUND)
                                label.setToolTip('Calibration data updated, the geometry probably needs to be ' +
                                                 're-estimated')
                        else:
                            label.setStyleSheet(STYLE_GREEN_BACKGROUND)
                    else:
                        label.setStyleSheet(STYLE_RED_BACKGROUND)
                        label.setToolTip('')

    def _load_sys_config_button_clicked(self):
        names = QFileDialog.getOpenFileName(self, 'Open file', self._helper.current_folder, "*.yaml;;*.*")

        if names[0] == '':
            return

        self._helper.current_folder = os.path.dirname(names[0])

        if self._lh_config_writer is not None:
            self._lh_config_writer.write_and_store_config_from_file(self._new_system_config_written_to_cf_signal.emit,
                                                                    names[0])

    def _save_sys_config_button_clicked(self):
        # Get calibration data from the Crazyflie to complete the system config data set
        # When the data is ready we get a callback on _calibration_read
        self._lh_memory_helper.read_all_calibs(self._calibration_read_signal.emit)

    def _calibration_read_cb(self, calibs):
        # Got calibration data from the CF, we have the full system configuration
        system_type = self._system_type_dialog.get_system_type()
        self._save_sys_config(self._lh_geos, calibs, system_type)

    def _save_sys_config(self, geos, calibs, system_type):
        names = QFileDialog.getSaveFileName(self, 'Save file', self._helper.current_folder, "*.yaml;;*.*")

        if names[0] == '':
            return

        self._helper.current_folder = os.path.dirname(names[0])

        if not names[0].endswith(".yaml") and names[0].find(".") < 0:
            filename = names[0] + ".yaml"
        else:
            filename = names[0]

        LighthouseConfigFileManager.write(filename, geos=geos, calibs=calibs, system_type=system_type)
