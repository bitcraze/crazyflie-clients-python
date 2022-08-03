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

#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#  02110-1301, USA.

"""
Shows data for the Loco Positioning system
"""

import logging
from enum import Enum
from collections import namedtuple

import time
from PyQt5 import uic
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtWidgets import QLabel

import cfclient
from cfclient.ui.tab_toolbox import TabToolbox

from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.mem import MemoryElement
from lpslib.lopoanchor import LoPoAnchor

from cfclient.ui.dialogs.anchor_position_dialog import AnchorPositionDialog

from vispy import scene
import numpy as np

import copy

__author__ = 'Bitcraze AB'
__all__ = ['LocoPositioningTab']

logger = logging.getLogger(__name__)

locopositioning_tab_class = uic.loadUiType(cfclient.module_path + "/ui/tabs/locopositioning_tab.ui")[0]

STYLE_RED_BACKGROUND = "background-color: lightpink;"
STYLE_GREEN_BACKGROUND = "background-color: lightgreen;"
STYLE_NO_BACKGROUND = "background-color: none;"


class Anchor:
    def __init__(self, x=0.0, y=0.0, z=0.0, distance=0.0):
        self.x = x
        self.y = y
        self.z = z
        self._is_position_valid = False
        self._is_active = False
        self.distance = distance

    def set_position(self, position):
        """Sets the position."""
        self.x = position[0]
        self.y = position[1]
        self.z = position[2]
        self._is_position_valid = True

    def get_position(self):
        """Returns the position as a vector"""
        return (self.x, self.y, self.z)

    def is_position_valid(self):
        return self._is_position_valid

    def set_is_active(self, is_active):
        self._is_active = is_active

    def is_active(self):
        return self._is_active


class AxisScaleStep:
    def __init__(self, from_view, from_axis, to_view, to_axis,
                 center_only=False):
        self.from_view = from_view.view
        self.from_axis = from_axis
        self.to_view = to_view.view
        self.to_axis = to_axis
        self.center_only = center_only


class Plot3dLps(scene.SceneCanvas):
    ANCHOR_BRUSH = np.array((0.2, 0.5, 0.2))
    ANCHOR_BRUSH_INVALID = np.array((0.8, 0.5, 0.5))
    HIGHLIGHT_ANCHOR_BRUSH = np.array((0, 1, 0))
    POSITION_BRUSH = np.array((0, 0, 1.0))

    VICINITY_DISTANCE = 2.5
    HIGHLIGHT_DISTANCE = 0.5

    LABEL_SIZE = 100
    LABEL_HIGHLIGHT_SIZE = 200

    ANCHOR_SIZE = 10
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

        self._cf = scene.visuals.Markers(
            pos=np.array([[0, 0, 0]]),
            parent=self._view.scene,
            face_color=self.POSITION_BRUSH)
        self._anchor_contexts = {}

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

        self.addArrows(1, 0.02, 0.1, 0.1, self._view.scene)

    def addArrows(self, length, width, head_length, head_width, parent):
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

    def update_data(self, anchors, pos, display_mode):
        self._cf.set_data(pos=np.array([pos]), face_color=self.POSITION_BRUSH)

        for id, anchor in anchors.items():
            self._update_anchor(id, anchor, display_mode)

        self._purge_anchors(anchors.keys())

    def _update_anchor(self, id, anchor, display_mode):
        if anchor.is_active():
            color = self.ANCHOR_BRUSH
        else:
            color = self.ANCHOR_BRUSH_INVALID

        size = self.ANCHOR_SIZE
        font_size = self.LABEL_SIZE
        distance = anchor.distance
        if display_mode is DisplayMode.identify_anchor:
            if distance < self.VICINITY_DISTANCE:
                amount = (distance - self.HIGHLIGHT_DISTANCE) / \
                    (self.VICINITY_DISTANCE - self.HIGHLIGHT_DISTANCE)
                color = self._mix(color, self.HIGHLIGHT_ANCHOR_BRUSH, amount)

            if distance < self.HIGHLIGHT_DISTANCE:
                color = self.HIGHLIGHT_ANCHOR_BRUSH
                size = self.HIGHLIGHT_SIZE
                font_size = self.LABEL_HIGHLIGHT_SIZE

        marker_pos = anchor.get_position()
        text_pos = self.TEXT_OFFSET + marker_pos
        if id in self._anchor_contexts:
            self._anchor_contexts[id][0].set_data(
                pos=np.array([marker_pos]),
                face_color=color,
                size=size)

            text = self._anchor_contexts[id][1]
            text.pos = text_pos
            text.font_size = font_size
        else:
            marker = scene.visuals.Markers(
                pos=np.array([marker_pos]),
                face_color=color,
                size=size,
                parent=self._view.scene)
            text = scene.visuals.Text(
                text=str(id),
                font_size=font_size,
                pos=text_pos,
                parent=self._view.scene)
            self._anchor_contexts[id] = [marker, text]

    def _purge_anchors(self, keep):
        to_remove = []
        for id, context in self._anchor_contexts.items():
            if id not in keep:
                to_remove.append(id)
                for visual in context:
                    visual.parent = None
        for id in to_remove:
            self._anchor_contexts.pop(id)

    def _mix(self, col1, col2, mix):
        return col1 * mix + col2 * (1.0 - mix)


class DisplayMode(Enum):
    identify_anchor = 1
    estimated_position = 2


Range = namedtuple('Range', ['min', 'max'])


class AnchorStateMachine:
    GET_ACTIVE = 0
    GET_IDS = 1
    GET_DATA = 2
    STEPS = [
        GET_ACTIVE,
        GET_ACTIVE,
        GET_IDS,
        GET_ACTIVE,
        GET_ACTIVE,
        GET_DATA,
        GET_ACTIVE,
        GET_ACTIVE,
    ]

    def __init__(self, mem_sub, cb_active_id_list, cb_id_list, cb_data):
        self._current_step = 0
        self._waiting_for_response = False
        self._mem = self._get_mem(mem_sub)

        self._cb_active_id_list = cb_active_id_list
        self._cb_id_list = cb_id_list
        self._cb_data = cb_data

    def poll(self):
        if not self._waiting_for_response:
            self._next_step()
            self._waiting_for_response = self._request_step()

    def _next_step(self):
        self._current_step += 1
        if self._current_step >= len(AnchorStateMachine.STEPS):
            self._current_step = 0

    def _request_step(self):
        result = True

        action = AnchorStateMachine.STEPS[self._current_step]
        if action == AnchorStateMachine.GET_ACTIVE:
            self._mem.update_active_id_list(self._cb_active_id_list_updated)
        elif action == AnchorStateMachine.GET_IDS:
            self._mem.update_id_list(self._cb_id_list_updated)
        else:
            if self._mem.nr_of_anchors > 0:
                # Only request anchor data if we actually have anchors, otherwise the callback will never be called
                self._mem.update_data(self._cb_data_updated)
            else:
                result = False

        return result

    def _get_mem(self, mem_sub):
        mem = mem_sub.get_mems(MemoryElement.TYPE_LOCO2)
        if len(mem) > 0:
            return mem[0]
        return None

    def _cb_active_id_list_updated(self, mem_data):
        self._waiting_for_response = False
        if self._cb_active_id_list:
            self._cb_active_id_list(mem_data.active_anchor_ids)

    def _cb_id_list_updated(self, mem_data):
        self._waiting_for_response = False
        if self._cb_id_list:
            self._cb_id_list(mem_data.anchor_ids)

    def _cb_data_updated(self, mem_data):
        self._waiting_for_response = False
        if self._cb_data:
            self._cb_data(mem_data.anchor_data)


class LocoPositioningTab(TabToolbox, locopositioning_tab_class):
    """Tab for plotting Loco Positioning data"""

    # Update period of log data in ms
    UPDATE_PERIOD_LOG = 100

    # Update period of anchor position data
    UPDATE_PERIOD_ANCHOR_STATE = 1000

    UPDATE_PERIOD_LOCO_MODE = 1000

    LOCO_MODE_UNKNOWN = -1
    LOCO_MODE_AUTO = 0
    LOCO_MODE_TWR = 1
    LOCO_MODE_TDOA2 = 2
    LOCO_MODE_TDOA3 = 3

    PARAM_MDOE_GR = 'loco'
    PARAM_MODE_NM = 'mode'
    PARAM_MODE = PARAM_MDOE_GR + '.' + PARAM_MODE_NM

    # Frame rate (updates per second)
    FPS = 2

    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)
    _log_error_signal = pyqtSignal(object, str)
    _anchor_range_signal = pyqtSignal(int, object, object)
    _loco_sys_signal = pyqtSignal(int, object, object)
    _cb_param_to_detect_loco_deck_signal = pyqtSignal(object, object)

    _anchor_active_id_list_updated_signal = pyqtSignal(object)
    _anchor_data_updated_signal = pyqtSignal(object)

    def __init__(self, helper):
        super(LocoPositioningTab, self).__init__(helper, 'Loco Positioning')
        self.setupUi(self)

        self._anchors = {}
        self._clear_state()
        self._refs = []

        self._display_mode = DisplayMode.estimated_position

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._connected_signal.connect(self._connected)
        self._disconnected_signal.connect(self._disconnected)
        self._anchor_range_signal.connect(self._anchor_range_received)
        self._loco_sys_signal.connect(self._loco_sys_received)
        self._cb_param_to_detect_loco_deck_signal.connect(
            self._cb_param_to_detect_loco_deck)

        self._anchor_active_id_list_updated_signal.connect(
            self._active_id_list_updated)
        self._anchor_data_updated_signal.connect(
            self._anchor_data_updated)

        self._id_anchor_button.toggled.connect(
            lambda enabled:
            self._do_when_checked(
                enabled,
                self._set_display_mode,
                DisplayMode.identify_anchor)
        )

        self._estimated_postion_button.toggled.connect(
            lambda enabled:
            self._do_when_checked(
                enabled,
                self._set_display_mode,
                DisplayMode.estimated_position)
        )

        self._mode_auto.toggled.connect(
            lambda enabled: self._request_mode(enabled, self.LOCO_MODE_AUTO)
        )

        self._mode_twr.toggled.connect(
            lambda enabled: self._request_mode(enabled, self.LOCO_MODE_TWR)
        )

        self._mode_tdoa2.toggled.connect(
            lambda enabled: self._request_mode(enabled, self.LOCO_MODE_TDOA2)
        )

        self._mode_tdoa3.toggled.connect(
            lambda enabled: self._request_mode(enabled, self.LOCO_MODE_TDOA3)
        )

        self._enable_mode_buttons(False)

        self._switch_mode_to_twr_button.setEnabled(False)
        self._switch_mode_to_tdoa2_button.setEnabled(False)
        self._switch_mode_to_tdoa3_button.setEnabled(False)

        self._switch_mode_to_twr_button.clicked.connect(
            lambda enabled:
            self._send_anchor_mode(self.LOCO_MODE_TWR)
        )
        self._switch_mode_to_tdoa2_button.clicked.connect(
            lambda enabled:
            self._send_anchor_mode(self.LOCO_MODE_TDOA2)
        )
        self._switch_mode_to_tdoa3_button.clicked.connect(
            lambda enabled:
            self._send_anchor_mode(self.LOCO_MODE_TDOA3)
        )

        self._clear_anchors_button.clicked.connect(self._clear_anchors)

        self._configure_anchor_positions_button.clicked.connect(
            self._show_anchor_postion_dialog)

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(
            self._connected_signal.emit)

        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

        self._set_up_plots()

        self.is_loco_deck_active = False

        self._graph_timer = QTimer()
        self._graph_timer.setInterval(int(1000 / self.FPS))
        self._graph_timer.timeout.connect(self._update_graphics)
        self._graph_timer.start()

        self._anchor_state_timer = QTimer()
        self._anchor_state_timer.setInterval(self.UPDATE_PERIOD_ANCHOR_STATE)
        self._anchor_state_timer.timeout.connect(self._poll_anchor_state)
        self._anchor_state_machine = None

        self._update_position_label(self._helper.pose_logger.position)

        self._lps_state = self.LOCO_MODE_UNKNOWN
        self._update_lps_state(self.LOCO_MODE_UNKNOWN)

        self._anchor_position_dialog = AnchorPositionDialog(self, helper)
        self._configure_anchor_positions_button.setEnabled(False)

    def _do_when_checked(self, enabled, fkn, arg):
        if enabled:
            fkn(arg)

    def _set_up_plots(self):
        self._plot_3d = Plot3dLps()
        self._plot_layout.addWidget(self._plot_3d.native)

    def _set_display_mode(self, display_mode):
        self._display_mode = display_mode

    def _send_anchor_mode(self, mode):
        lopo = LoPoAnchor(self._helper.cf)

        mode_translation = {
            self.LOCO_MODE_TWR: lopo.MODE_TWR,
            self.LOCO_MODE_TDOA2: lopo.MODE_TDOA,
            self.LOCO_MODE_TDOA3: lopo.MODE_TDOA3,
        }

        # Set the mode from the last to the first anchor
        # In TDoA 2 mode this ensures that the master anchor is set last
        # Note: We only switch mode of anchor 0 - 7 since this is what is
        # supported in TWR and TDoA 2
        for j in range(5):
            for i in reversed(range(8)):
                lopo.set_mode(i, mode_translation[mode])

    def _clear_state(self):
        self._clear_anchors()
        self._update_ranging_status_indicators()
        self._id_anchor_button.setEnabled(True)

    def _clear_anchors(self):
        self._anchors = {}

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        logger.info("Crazyflie connected to {}".format(link_uri))
        self._request_param_to_detect_loco_deck()

    def _request_param_to_detect_loco_deck(self):
        """Send a parameter request to detect if the Loco deck is installed"""
        group = 'deck'
        param = 'bcDWM1000'

        if self._is_in_param_toc(group, param):
            logger.info("Requesting loco deck parameter")
            self._helper.cf.param.add_update_callback(
                group=group, name=param,
                cb=self._cb_param_to_detect_loco_deck_signal.emit)

    def _cb_param_to_detect_loco_deck(self, name, value):
        """Callback from the parameter sub system when the Loco deck detection
        parameter has been updated"""
        if value == '1':
            logger.info("Loco deck installed, enabling LPS tab")
            self._loco_deck_detected()
        else:
            logger.info("No Loco deck installed")

    def _loco_deck_detected(self):
        """Called when the loco deck has been detected. Enables the tab,
        starts logging and polling of the memory sub system as well as starts
        timers for updating graphics"""
        if not self.is_loco_deck_active:
            self.is_loco_deck_active = True
            try:
                self._register_logblock(
                    "LoPoTab0",
                    [
                        ("ranging", "distance0", "float"),
                        ("ranging", "distance1", "float"),
                        ("ranging", "distance2", "float"),
                        ("ranging", "distance3", "float"),
                    ],
                    self._anchor_range_signal.emit,
                    self._log_error_signal.emit)

                self._register_logblock(
                    "LoPoTab1",
                    [
                        ("ranging", "distance4", "float"),
                        ("ranging", "distance5", "float"),
                        ("ranging", "distance6", "float"),
                        ("ranging", "distance7", "float"),
                    ],
                    self._anchor_range_signal.emit,
                    self._log_error_signal.emit)

                self._register_logblock(
                    "LoPoSys",
                    [
                        ("loco", "mode", "uint8_t")
                    ],
                    self._loco_sys_signal.emit,
                    self._log_error_signal.emit,
                    update_period=self.UPDATE_PERIOD_LOCO_MODE)
            except KeyError as e:
                logger.warning(str(e))
            except AttributeError as e:
                logger.warning(str(e))

            self._start_polling_anchor_pos(self._helper.cf)
            self._enable_mode_buttons(True)
            self._configure_anchor_positions_button.setEnabled(True)

            self._helper.cf.param.add_update_callback(
                group=self.PARAM_MDOE_GR,
                name=self.PARAM_MODE_NM,
                cb=self._loco_mode_updated)

            if self.PARAM_MDOE_GR in self._helper.cf.param.values:
                if self.PARAM_MODE_NM in \
                        self._helper.cf.param.values[self.PARAM_MDOE_GR]:
                    self._loco_mode_updated(
                        self.PARAM_MODE,
                        self._helper.cf.param.values[self.PARAM_MDOE_GR][
                            self.PARAM_MODE_NM])

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        logger.debug("Crazyflie disconnected from {}".format(link_uri))
        self._stop_polling_anchor_pos()
        self._clear_state()
        self._update_graphics()
        self.is_loco_deck_active = False
        self._update_lps_state(self.LOCO_MODE_UNKNOWN)
        self._enable_mode_buttons(False)
        self._loco_mode_updated('', self.LOCO_MODE_UNKNOWN)
        self._configure_anchor_positions_button.setEnabled(False)
        self._anchor_position_dialog.close()

    def _register_logblock(self, logblock_name, variables, data_cb, error_cb,
                           update_period=UPDATE_PERIOD_LOG):
        """Register log data to listen for. One logblock can contain a limited
        number of parameters (6 for floats)."""
        lg = LogConfig(logblock_name, update_period)
        for variable in variables:
            if self._is_in_log_toc(variable):
                lg.add_variable('{}.{}'.format(variable[0], variable[1]),
                                variable[2])

        self._helper.cf.log.add_config(lg)
        lg.data_received_cb.add_callback(data_cb)
        lg.error_cb.add_callback(error_cb)
        lg.start()
        return lg

    def _is_in_log_toc(self, variable):
        toc = self._helper.cf.log.toc
        group = variable[0]
        param = variable[1]
        return group in toc.toc and param in toc.toc[group]

    def _is_in_param_toc(self, group, param):
        toc = self._helper.cf.param.toc
        return bool(group in toc.toc and param in toc.toc[group])

    def _anchor_range_received(self, timestamp, data, logconf):
        """Callback from the logging system when a range is updated."""
        for name, value in data.items():
            valid, anchor_number = self._parse_range_param_name(name)
            # Only set distance on anchors that we have seen through other
            # messages to avoid creating anchor 0-7 even if they do not exist
            # in a TDoA3 set up for instance
            if self._anchor_exists(anchor_number):
                if valid:
                    anchor = self._get_create_anchor(anchor_number)
                    anchor.distance = float(value)

    def _loco_sys_received(self, timestamp, data, logconf):
        """Callback from the logging system when the loco pos sys config
        is updated."""
        if self.PARAM_MODE in data:
            lps_state = data[self.PARAM_MODE]
            if lps_state == self.LOCO_MODE_TDOA2:
                if self._id_anchor_button.isEnabled():
                    if self._id_anchor_button.isChecked():
                        self._estimated_postion_button.setChecked(True)
                    self._id_anchor_button.setEnabled(False)
            else:
                if not self._id_anchor_button.isEnabled():
                    self._id_anchor_button.setEnabled(True)
            self._update_lps_state(lps_state)

    def _update_ranging_status_indicators(self):
        container = self._anchor_stats_container

        ids = sorted(self._anchors.keys())

        # Update existing labels or add new if needed
        count = 0
        for id in ids:
            col = count % 8
            row = int(count / 8)

            if count < container.count():
                label = container.itemAtPosition(row, col).widget()
            else:
                label = QLabel()
                label.setMinimumSize(30, 0)
                label.setProperty('frameShape', 'QFrame::Box')
                label.setAlignment(Qt.AlignCenter)
                container.addWidget(label, row, col)

            label.setText(str(id))

            if self._anchors[id].is_active():
                label.setStyleSheet(STYLE_GREEN_BACKGROUND)
            else:
                label.setStyleSheet(STYLE_RED_BACKGROUND)

            count += 1

        # Remove labels if there are too many
        for i in range(count, container.count()):
            col = i % 8
            row = int(i / 8)

            label = container.itemAtPosition(row, col).widget()
            label.deleteLater()

    def _logging_error(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""
        QMessageBox.about(self, "LocoPositioningTab error",
                          "Error when using log config",
                          " [{0}]: {1}".format(log_conf.name, msg))

    def _start_polling_anchor_pos(self, crazyflie):
        """Set up a timer to poll anchor positions from the memory sub
        system"""
        if not self._anchor_state_machine:
            self._anchor_state_machine = AnchorStateMachine(
                crazyflie.mem,
                self._anchor_active_id_list_updated_signal.emit,
                None,
                self._anchor_data_updated_signal.emit
            )
        self._anchor_state_timer.start()

    def _stop_polling_anchor_pos(self):
        self._anchor_state_timer.stop()
        self._anchor_state_machine = None

    def _poll_anchor_state(self):
        if self._anchor_state_machine:
            self._anchor_state_machine.poll()

    def _active_id_list_updated(self, anchor_list):
        """Callback from the anchor state machine when we get a list of active
        anchors"""
        for id, anchor_data in self._anchors.items():
            anchor_data.set_is_active(False)

        for id in anchor_list:
            anchor_data = self._get_create_anchor(id)
            anchor_data.set_is_active(True)

        self._update_ranging_status_indicators()

    def _anchor_data_updated(self, position_dict):
        """Callback from the anchor state machine when the anchor positions
         are updated"""
        for id, anchor_data in position_dict.items():
            anchor = self._get_create_anchor(id)
            if anchor_data.is_valid:
                anchor.set_position(anchor_data.position)

        self._update_positions_in_config_dialog()

    def _parse_range_param_name(self, name):
        """Parse a parameter name for a ranging distance and return the number
           of the anchor. The name is on the format 'ranging.distance4' """
        valid = False
        anchor = 0
        if name.startswith('ranging.distance'):
            anchor = int(name[-1])
            valid = True
        return (valid, anchor)

    def _parse_position_param_name(self, name):
        """Parse a parameter name for a position and return the
           axis (0=x, 1=y, 2=z).
           The param name is on the format 'kalman.stateY' """
        valid = False
        axis = 0
        if name.startswith('kalman.state'):
            axis = {'X': 0, 'Y': 1, 'Z': 2}[name[-1]]
            valid = True
        return (valid, axis)

    def _get_create_anchor(self, anchor_number):
        if anchor_number not in self._anchors:
            self._anchors[anchor_number] = Anchor()
        return self._anchors[anchor_number]

    def _anchor_exists(self, anchor_number):
        return anchor_number in self._anchors

    def _update_graphics(self):
        if self.is_visible() and self.is_loco_deck_active:
            anchors = copy.deepcopy(self._anchors)
            self._plot_3d.update_data(
                anchors,
                self._helper.pose_logger.position,
                self._display_mode)
            self._update_position_label(self._helper.pose_logger.position)

    def _update_position_label(self, position):
        if len(position) == 3:
            coordinate = "({:0.2f}, {:0.2f}, {:0.2f})".format(
                position[0], position[1], position[2])
        else:
            coordinate = '(0.00, 0.00, 0.00)'

        self._status_position.setText(coordinate)

    def _update_lps_state(self, state):
        if state != self._lps_state:
            self._update_lps_state_indicator(self._state_twr,
                                             state == self.LOCO_MODE_TWR)
            self._update_lps_state_indicator(self._state_tdoa2,
                                             state == self.LOCO_MODE_TDOA2)
            self._update_lps_state_indicator(self._state_tdoa3,
                                             state == self.LOCO_MODE_TDOA3)
        self._lps_state = state

    def _update_lps_state_indicator(self, element, active):
        if active:
            element.setStyleSheet(STYLE_GREEN_BACKGROUND)
        else:
            element.setStyleSheet(STYLE_NO_BACKGROUND)

    def _enable_mode_buttons(self, enabled):
        self._mode_auto.setEnabled(enabled)
        self._mode_twr.setEnabled(enabled)
        self._mode_tdoa2.setEnabled(enabled)
        self._mode_tdoa3.setEnabled(enabled)

    def _request_mode(self, enabled, mode):
        if enabled:
            self._helper.cf.param.set_value(self.PARAM_MODE, str(mode))

            if mode == self.LOCO_MODE_TWR:
                self._switch_mode_to_twr_button.setEnabled(False)
                self._switch_mode_to_tdoa2_button.setEnabled(True)
                self._switch_mode_to_tdoa3_button.setEnabled(True)
            elif mode == self.LOCO_MODE_TDOA2:
                self._switch_mode_to_twr_button.setEnabled(True)
                self._switch_mode_to_tdoa2_button.setEnabled(False)
                self._switch_mode_to_tdoa3_button.setEnabled(True)
            elif mode == self.LOCO_MODE_TDOA3:
                self._switch_mode_to_twr_button.setEnabled(True)
                self._switch_mode_to_tdoa2_button.setEnabled(True)
                self._switch_mode_to_tdoa3_button.setEnabled(False)
            else:
                self._switch_mode_to_twr_button.setEnabled(False)
                self._switch_mode_to_tdoa2_button.setEnabled(False)
                self._switch_mode_to_tdoa3_button.setEnabled(False)

    def _loco_mode_updated(self, name, value):
        mode = int(value)
        if mode == self.LOCO_MODE_AUTO:
            if not self._mode_auto.isChecked():
                self._mode_auto.setChecked(True)
        elif mode == self.LOCO_MODE_TWR:
            if not self._mode_twr.isChecked():
                self._mode_twr.setChecked(True)
        elif mode == self.LOCO_MODE_TDOA2:
            if not self._mode_tdoa2.isChecked():
                self._mode_tdoa2.setChecked(True)
        elif mode == self.LOCO_MODE_TDOA3:
            if not self._mode_tdoa3.isChecked():
                self._mode_tdoa3.setChecked(True)
        else:
            self._mode_auto.setChecked(False)
            self._mode_twr.setChecked(False)
            self._mode_tdoa2.setChecked(False)
            self._mode_tdoa3.setChecked(False)

    def _show_anchor_postion_dialog(self):
        self._anchor_position_dialog.show()

    def _update_positions_in_config_dialog(self):
        positions = {}

        for id, anchor in self._anchors.items():
            if anchor.is_position_valid():
                positions[id] = (anchor.x, anchor.y, anchor.z)

        self._anchor_position_dialog.anchor_postions_updated(positions)

    def write_positions_to_anchors(self, anchor_positions):
        lopo = LoPoAnchor(self._helper.cf)

        for _ in range(3):
            for id, position in anchor_positions.items():
                lopo.set_position(id, position)
            time.sleep(0.2)
