#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2022-2026 Bitcraze AB
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

from __future__ import annotations

import asyncio
import logging
import math
import os
from collections.abc import Coroutine

import numpy as np
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QResizeEvent, QWheelEvent
from PySide6.QtUiTools import loadUiType
from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox, QPushButton
from vispy import scene
from vispy.util.event import Event

import cfclient
from cfclient.gui import create_task
from cfclient.ui.dialogs.basestation_mode_dialog import LighthouseBsModeDialog
from cfclient.ui.dialogs.lighthouse_system_type_dialog import LighthouseSystemTypeDialog
from cfclient.ui.pluginhelper import PluginHelper
from cfclient.ui.tab_toolbox import TabToolbox
from cfclient.ui.widgets.info_label import InfoLabel
from cfclient.utils.lighthouse_config_writer import write_and_store_config

from cflib2 import Crazyflie
from cflib2.error import (
    CrazyflieError,
    DisconnectedError,
    InvalidArgumentError,
    LogError,
    ParamError,
    VariableNotFoundError,
)
from cflib2.memory import LighthouseBsGeometry, LighthouseConfig

__author__ = "Bitcraze AB"
__all__ = ["LighthouseTab"]

logger = logging.getLogger(__name__)

lighthouse_tab_class = loadUiType(cfclient.module_path + "/ui/tabs/lighthouse_tab.ui")[
    0
]

FILE_REGEX_YAML = "Config *.yaml;;All *.*"

STYLE_RED_BACKGROUND = "background-color: lightpink;"
STYLE_GREEN_BACKGROUND = "background-color: lightgreen;"
STYLE_BLUE_BACKGROUND = "background-color: lightblue;"
STYLE_ORANGE_BACKGROUND = "background-color: orange;"
STYLE_NO_BACKGROUND = "background-color: none;"


class MarkerPose:
    COL_X_AXIS = "red"
    COL_Y_AXIS = "green"
    COL_Z_AXIS = "blue"

    AXIS_LEN = 0.3

    LABEL_SIZE = 100
    LABEL_OFFSET = np.array((0.0, 0, 0.25))

    def __init__(
        self,
        the_scene: scene.Node,
        color: np.ndarray,
        text: str | None = None,
        axis_visible: bool = False,
        symbol: str = "disc",
    ) -> None:
        self._scene = the_scene
        self._color = color
        self._text = text
        self._position = [0.0, 0, 0]
        self._rot = np.identity(3)
        self._symbol = symbol
        self._axis_visible = False
        self._x_axis = None
        self._y_axis = None
        self._z_axis = None

        self._marker = scene.visuals.Markers(
            pos=np.array([[0, 0, 0]]),
            parent=self._scene,
            face_color=self._color,
            symbol=self._symbol,
        )

        self._label = None
        if self._text:
            self._label = scene.visuals.Text(
                text=self._text,
                font_size=self.LABEL_SIZE,
                pos=self.LABEL_OFFSET,
                parent=self._scene,
            )

        self.set_axis_visible(axis_visible)

    def set_axis_visible(self, visible: bool) -> None:
        if visible == self._axis_visible:
            return

        if visible:
            if self._x_axis is None:
                self._x_axis = scene.visuals.Line(
                    pos=np.array([[0, 0, 0], [0, 0, 0]]),
                    color=self.COL_X_AXIS,
                    parent=self._scene,
                )

            if self._y_axis is None:
                self._y_axis = scene.visuals.Line(
                    pos=np.array([[0, 0, 0], [0, 0, 0]]),
                    color=self.COL_Y_AXIS,
                    parent=self._scene,
                )

            if self._z_axis is None:
                self._z_axis = scene.visuals.Line(
                    pos=np.array([[0, 0, 0], [0, 0, 0]]),
                    color=self.COL_Z_AXIS,
                    parent=self._scene,
                )
        else:
            if self._x_axis is not None:
                self._x_axis.parent = None
                self._x_axis = None
            if self._y_axis is not None:
                self._y_axis.parent = None
                self._y_axis = None
            if self._z_axis is not None:
                self._z_axis.parent = None
                self._z_axis = None

        self._axis_visible = visible

        self._update_visuals()

    def set_pose(
        self, position: list[float], rot: np.ndarray | list[list[float]]
    ) -> None:
        if np.array_equal(position, self._position) and np.array_equal(rot, self._rot):
            return

        self._position = position
        self._rot = rot

        self._update_visuals()

    def _update_visuals(self) -> None:
        self._marker.set_data(
            pos=np.array([self._position]), face_color=self._color, symbol=self._symbol
        )

        if self._label:
            self._label.pos = self.LABEL_OFFSET + self._position

        if self._axis_visible:
            x_tip = np.dot(np.array(self._rot), np.array([self.AXIS_LEN, 0, 0]))
            self._x_axis.set_data(
                np.array([self._position, x_tip + self._position]),
                color=self.COL_X_AXIS,
            )
            y_tip = np.dot(np.array(self._rot), np.array([0, self.AXIS_LEN, 0]))
            self._y_axis.set_data(
                np.array([self._position, y_tip + self._position]),
                color=self.COL_Y_AXIS,
            )
            z_tip = np.dot(np.array(self._rot), np.array([0, 0, self.AXIS_LEN]))
            self._z_axis.set_data(
                np.array([self._position, z_tip + self._position]),
                color=self.COL_Z_AXIS,
            )

    def get_position(self) -> list[float]:
        return self._position

    def remove(self) -> None:
        self._marker.parent = None
        if self._x_axis is not None:
            self._x_axis.parent = None
        if self._y_axis is not None:
            self._y_axis.parent = None
        if self._z_axis is not None:
            self._z_axis.parent = None
        if self._label:
            self._label.parent = None

    def set_color(self, color: np.ndarray) -> None:
        self._color = color
        self._marker.set_data(
            pos=np.array([self._position]), face_color=self._color, symbol=self._symbol
        )


class CfMarkerPose(MarkerPose):
    POSITION_BRUSH = np.array((0, 0, 1.0))

    def __init__(self, the_scene: scene.Node) -> None:
        super().__init__(the_scene, self.POSITION_BRUSH, None, axis_visible=True)


class BsMarkerPose(MarkerPose):
    BS_BRUSH_VISIBLE = np.array((0.2, 0.5, 0.2))
    BS_BRUSH_NOT_VISIBLE = np.array((0.8, 0.5, 0.5))

    def __init__(self, the_scene: scene.Node, text: str | None = None) -> None:
        super().__init__(the_scene, self.BS_BRUSH_NOT_VISIBLE, text, axis_visible=True)

    def set_receiving_status(self, visible: bool) -> None:
        self.set_color(self.BS_BRUSH_VISIBLE if visible else self.BS_BRUSH_NOT_VISIBLE)


class Plot3dLighthouse(scene.SceneCanvas):
    DEFAULT_CAMERA_DISTANCE = 10.0

    def __init__(self) -> None:
        # Note: autoswap is disabled since Qt's QOpenGLWidget path already presents
        # the FBO; enabling vispy autoswap here would cause a redundant swap and
        # eglSwapBuffers warnings.
        scene.SceneCanvas.__init__(self, keys=None, autoswap=False)
        self.unfreeze()

        self._view = self.central_widget.add_view()
        self._view.bgcolor = "#ffffff"
        self._view.camera = scene.TurntableCamera(
            distance=self.DEFAULT_CAMERA_DISTANCE, up="+z", center=(0.0, 0.0, 1.0)
        )
        self._view.camera.set_default_state()

        self._cf: CfMarkerPose | None = None
        self._base_stations: dict[int, BsMarkerPose] = {}

        plane_size = 10
        scene.visuals.Plane(
            width=plane_size,
            height=plane_size,
            width_segments=plane_size,
            height_segments=plane_size,
            color=(0.5, 0.5, 0.5, 0.5),
            edge_color="gray",
            parent=self._view.scene,
        )

        self._addArrows(1, 0.02, 0.1, 0.1, self._view.scene)

        self._home_button = QPushButton("Home", self.native)
        self._home_button.clicked.connect(self.move_camera_home)

        self._controls_label = QLabel(
            "Zoom: scroll / pinch   Rotate: click + drag   Pan: shift + drag",
            self.native,
        )
        self._controls_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._controls_label.setStyleSheet(
            "color: #555555; background-color: rgba(255, 255, 255, 160); padding: 2px 6px;"
        )
        self._original_native_resize = self.native.resizeEvent
        self.native.resizeEvent = self._on_native_resize

        _original_wheel = self.native.wheelEvent

        def _wheel_event(event: QWheelEvent) -> None:
            _original_wheel(event)
            event.accept()

        self.native.wheelEvent = _wheel_event

        self.freeze()

    def _on_native_resize(self, event: QResizeEvent) -> None:
        self._original_native_resize(event)
        self._controls_label.adjustSize()
        w = self.native.width()
        h = self.native.height()
        lw = self._controls_label.width()
        lh = self._controls_label.height()
        self._controls_label.move((w - lw) // 2, h - lh - 6)

    def move_camera_home(self) -> None:
        self._view.camera.reset()
        self._view.camera.distance = self.DEFAULT_CAMERA_DISTANCE

    def on_resize(self, event: Event) -> None:
        x = self.native.width() - self._home_button.width() - 5
        y = 5
        self._home_button.move(x, y)

        return super().on_resize(event)

    def _addArrows(
        self,
        length: float,
        width: float,
        head_length: float,
        head_width: float,
        parent: scene.Node,
    ) -> None:
        # The Arrow visual in vispy does not seem to work very good,
        # draw arrows using lines instead.
        w = width / 2
        hw = head_width / 2
        base_len = length - head_length

        # X-axis
        scene.visuals.LinePlot(
            [
                [0, w, 0],
                [base_len, w, 0],
                [base_len, hw, 0],
                [length, 0, 0],
                [base_len, -hw, 0],
                [base_len, -w, 0],
                [0, -w, 0],
            ],
            width=1.0,
            color="red",
            parent=parent,
            marker_size=0.0,
        )

        # Y-axis
        scene.visuals.LinePlot(
            [
                [w, 0, 0],
                [w, base_len, 0],
                [hw, base_len, 0],
                [0, length, 0],
                [-hw, base_len, 0],
                [-w, base_len, 0],
                [-w, 0, 0],
            ],
            width=1.0,
            color="green",
            parent=parent,
            marker_size=0.0,
        )

        # Z-axis
        scene.visuals.LinePlot(
            [
                [0, w, 0],
                [0, w, base_len],
                [0, hw, base_len],
                [0, 0, length],
                [0, -hw, base_len],
                [0, -w, base_len],
                [0, -w, 0],
            ],
            width=1.0,
            color="blue",
            parent=parent,
            marker_size=0.0,
        )

    def update_cf_pose(self, position: list[float], rot: np.ndarray) -> None:
        if not self._cf:
            self._cf = CfMarkerPose(self._view.scene)
        self._cf.set_pose(position, rot)

    def update_base_station_geos(self, geos: dict[int, LighthouseBsGeometry]) -> None:
        for id, geo in geos.items():
            # Add a new base station if it does not exist
            if id not in self._base_stations:
                self._base_stations[id] = BsMarkerPose(
                    self._view.scene, text=f"{id + 1}"
                )

            self._base_stations[id].set_pose(geo.origin, geo.rotation_matrix)

        # Remove any base stations that are no longer present
        geos_to_remove = self._base_stations.keys() - geos.keys()
        for id in geos_to_remove:
            existing = self._base_stations.pop(id)
            existing.remove()

    def update_base_station_visibility(self, visibility: set[int]) -> None:
        for id, bs in self._base_stations.items():
            bs.set_receiving_status(id in visibility)

    def clear(self) -> None:
        if self._cf:
            self._cf.remove()
            self._cf = None

        for bs in self._base_stations.values():
            bs.remove()
        self._base_stations = {}


class LighthouseTab(TabToolbox, lighthouse_tab_class):
    """Tab for plotting Lighthouse data"""

    # Update period of log data in ms
    UPDATE_PERIOD_LOG = 100

    # Frame rate (updates per second)
    FPS = 2

    STATUS_NOT_RECEIVING = 0
    STATUS_MISSING_DATA = 1
    STATUS_TO_ESTIMATOR = 2

    LOG_STATUS = "lighthouse.status"
    LOG_RECEIVE = "lighthouse.bsReceive"
    LOG_CALIBRATION_EXISTS = "lighthouse.bsCalVal"
    LOG_CALIBRATION_CONFIRMED = "lighthouse.bsCalCon"
    LOG_CALIBRATION_UPDATED = "lighthouse.bsCalUd"
    LOG_GEOMETERY_EXISTS = "lighthouse.bsGeoVal"
    LOG_ACTIVE = "lighthouse.bsActive"
    LOG_AVAILABLE = "lighthouse.bsAvailable"

    def __init__(self, helper: PluginHelper) -> None:
        super(LighthouseTab, self).__init__(helper, "Lighthouse Positioning")
        self.setupUi(self)

        # Geometry estimation is not available yet
        self._set_up_button.setVisible(False)

        self._import_config_button.clicked.connect(self._load_sys_config_user_action)
        self._export_config_button.clicked.connect(self._save_sys_config_user_action)

        self._set_up_plots()

        self._cf: Crazyflie | None = None
        self._on_connected_task: asyncio.Task[object] | None = None
        self._status_task: asyncio.Task[object] | None = None
        self._read_geo_task: asyncio.Task[object] | None = None
        self._config_task: asyncio.Task[object] | None = None

        # The lighthouse memory can only be opened by one user at a time, so all
        # reads and writes to it must hold this lock
        self._lh_memory_lock = asyncio.Lock()

        self.is_lighthouse_deck_active = False

        self._lh_geos: dict[int, LighthouseBsGeometry] = {}

        self._bs_receives_light: set[int] = set()
        self._bs_calibration_data_exists: set[int] = set()
        self._bs_calibration_data_confirmed: set[int] = set()
        self._bs_calibration_data_updated: set[int] = set()
        self._bs_geometry_data_exists: set[int] = set()
        self._bs_data_to_estimator: set[int] = set()
        self._bs_available: set[int] = set()

        self._clear_state_indicator()

        self._bs_stats = [
            self._bs_receives_light,
            self._bs_calibration_data_exists,
            self._bs_calibration_data_confirmed,
            self._bs_calibration_data_updated,
            self._bs_geometry_data_exists,
            self._bs_data_to_estimator,
            self._bs_available,
        ]

        self._lh_status = self.STATUS_NOT_RECEIVING

        self._graph_timer = QTimer()
        self._graph_timer.setInterval(int(1000 / self.FPS))
        self._graph_timer.timeout.connect(self._update_graphics)
        self._graph_timer.start()

        self._basestation_mode_dialog = LighthouseBsModeDialog(self)
        self._system_type_dialog = LighthouseSystemTypeDialog()

        self._change_system_type_button.clicked.connect(
            lambda: self._system_type_dialog.show()
        )
        self._manage_basestation_mode_button.clicked.connect(
            self._show_basestation_mode_dialog
        )

        self._is_connected = False
        self._update_ui()

        self._base_stations_info_label = InfoLabel(
            "Receiving: green/red — base station is seen/not seen by the deck.\n"
            "\n"
            "Calibration: data from each base station used to correct manufacturing variation.\n"
            "  Red    — no calibration data received\n"
            "  Orange — received but does not match persistent memory; recreate configuration\n"
            "  Green  — calibration data received\n"
            "  Blue   — using calibration data from persistent memory\n"
            "\n"
            "Geometry: green/red — geometry data is/is not in persistent memory.",
            self._base_station_group_box,
        )
        self._sys_management_info_label = InfoLabel(
            "Set BS Channel: set the channel of a base station\n"
            "Switch BS Version: switch between v1 and v2 base stations\n"
            "Import Config: import an existing configuration\n"
            "Export Config: export a configuration to file",
            self._sys_management_group_box,
        )

    def connected(self, cf: Crazyflie) -> None:
        """Callback when the Crazyflie has been connected"""
        self._cf = cf
        self._is_connected = True
        self._system_type_dialog.connected(cf)
        self._on_connected_task = create_task(self._on_connected(cf))
        self._update_ui()

    def disconnected(self) -> None:
        """Callback for when the Crazyflie has been disconnected"""
        for task in [
            self._on_connected_task,
            self._status_task,
            self._read_geo_task,
            self._config_task,
        ]:
            if task is not None:
                task.cancel()
        self._on_connected_task = None
        self._status_task = None
        self._read_geo_task = None
        self._config_task = None

        self._cf = None
        self._system_type_dialog.disconnected()
        self._clear_state()
        self._update_graphics()
        self._plot_3d.clear()
        self.is_lighthouse_deck_active = False
        self._is_connected = False
        self._update_ui()

    async def _on_connected(self, cf: Crazyflie) -> None:
        try:
            deck_present = int(await cf.param().get("deck.bcLighthouse4")) == 1
        except (ParamError, VariableNotFoundError):
            deck_present = False

        if deck_present:
            self._lighthouse_deck_detected(cf)

        self._update_ui()

    def _lighthouse_deck_detected(self, cf: Crazyflie) -> None:
        """Called when the lighthouse deck has been detected. Enables the tab and
        starts logging of the lighthouse status"""
        if not self.is_lighthouse_deck_active:
            self.is_lighthouse_deck_active = True
            self._populate_status_matrix()
            self._status_task = create_task(self._stream_status(cf))

    async def _stream_status(self, cf: Crazyflie) -> None:
        log = cf.log()
        log_names = log.names()
        variables = [
            self.LOG_STATUS,
            self.LOG_RECEIVE,
            self.LOG_CALIBRATION_EXISTS,
            self.LOG_CALIBRATION_CONFIRMED,
            self.LOG_CALIBRATION_UPDATED,
            self.LOG_GEOMETERY_EXISTS,
            self.LOG_ACTIVE,
            self.LOG_AVAILABLE,
        ]

        try:
            block = await log.create_block()
            for variable in variables:
                if variable in log_names:
                    await block.add_variable(variable)
            stream = await block.start(self.UPDATE_PERIOD_LOG)
        except LogError as e:
            logger.warning("Could not start lighthouse status logging: %s", e)
            return

        try:
            while True:
                data = await stream.next()
                self._status_report_received(data.data)
        finally:
            try:
                await asyncio.shield(stream.stop())
            except (DisconnectedError, asyncio.CancelledError):
                pass

    def _start_read_of_geo_data(self) -> None:
        if self._cf is None:
            return
        if self._read_geo_task is None:
            self._read_geo_task = create_task(self._read_geo_data(self._cf))

    async def _read_geo_data(self, cf: Crazyflie) -> None:
        try:
            async with self._lh_memory_lock:
                # Only base stations with valid geometry data are returned
                self._lh_geos = await cf.memory().read_lighthouse_geometries()
        except DisconnectedError:
            raise
        except CrazyflieError as e:
            logger.warning("Could not read lighthouse geometry: %s", e)
        finally:
            if self._read_geo_task is asyncio.current_task():
                self._read_geo_task = None

    def _is_matching_current_geo_data(self, geometries: set[int]) -> bool:
        return geometries == self._lh_geos.keys()

    def _adjust_bitmask(self, bit_mask: int, bs_list: set[int]) -> None:
        for id in range(16):
            if bit_mask & (1 << id):
                bs_list.add(id)
            else:
                if id in bs_list:
                    bs_list.remove(id)

    def _status_report_received(self, data: dict) -> None:
        """Called when new status data has been logged from the Crazyflie"""

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

        if self.LOG_AVAILABLE in data:
            bit_mask = data[self.LOG_AVAILABLE]
            self._adjust_bitmask(bit_mask, self._bs_available)

        self._update_basestation_status_indicators()

    def _show_basestation_mode_dialog(self) -> None:
        self._basestation_mode_dialog.reset()
        self._basestation_mode_dialog.show()

    def _set_up_plots(self) -> None:
        self._plot_3d = Plot3dLighthouse()
        self._plot_layout.addWidget(self._plot_3d.native)

    def _update_graphics(self) -> None:
        if self.is_visible() and self.is_lighthouse_deck_active:
            pose_logger = self._helper.pose_logger
            self._plot_3d.update_cf_pose(
                pose_logger.position, self._rpy_to_rot(pose_logger.rpy_rad)
            )
            self._plot_3d.update_base_station_geos(self._lh_geos)
            self._plot_3d.update_base_station_visibility(self._bs_data_to_estimator)

            self._update_position_label(pose_logger.position)
            self._update_status_label(self._lh_status)
            self._mask_status_matrix(self._bs_available)

    def _update_ui(self) -> None:
        enabled = (
            self._is_connected
            and self.is_lighthouse_deck_active
            and self._config_task is None
        )
        self._import_config_button.setEnabled(enabled)
        self._export_config_button.setEnabled(enabled)

    def _rpy_to_rot(self, rpy: list[float]) -> np.ndarray:
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

    def _update_position_label(self, position: list[float]) -> None:
        if len(position) == 3:
            coordinate = "({:0.2f}, {:0.2f}, {:0.2f})".format(
                position[0], position[1], position[2]
            )
        else:
            coordinate = "(0.00, 0.00, 0.00)"

        self._status_position.setText(coordinate)

    def _update_status_label(self, status: int) -> None:
        text = ""
        if status == self.STATUS_NOT_RECEIVING:
            text = "Not receiving"
        elif status == self.STATUS_MISSING_DATA:
            text = "No geo/calib"
        elif status == self.STATUS_TO_ESTIMATOR:
            text = "LH ready"

        self._status_status.setText(text)

    def _clear_state(self) -> None:
        self._lh_geos = {}
        self._bs_receives_light.clear()
        self._bs_calibration_data_exists.clear()
        self._bs_calibration_data_confirmed.clear()
        self._bs_calibration_data_updated.clear()
        self._bs_geometry_data_exists.clear()
        self._bs_data_to_estimator.clear()
        self._update_basestation_status_indicators()
        self._clear_state_indicator()
        self._lh_status = self.STATUS_NOT_RECEIVING

    def _clear_state_indicator(self) -> None:
        container = self._basestation_stats_container
        for row in range(0, 4):
            for col in range(1, 17):
                item = container.itemAtPosition(row, col)
                if item is not None:
                    item.widget().deleteLater()

    def _populate_status_matrix(self) -> None:
        container = self._basestation_stats_container

        for bs in range(0, 16):
            container.addWidget(self._create_label(str(bs + 1)), 0, bs + 1)
            for i in range(1, 4):
                container.addWidget(self._create_label(), i, bs + 1)

    def _mask_status_matrix(self, bs_available_mask: set[int]) -> None:
        container = self._basestation_stats_container

        for bs in range(0, 16):
            bs_indicator_id = bs + 1
            for stats_indicator_id in range(0, 4):
                item = container.itemAtPosition(stats_indicator_id, bs_indicator_id)
                if item is not None:
                    label = item.widget()
                    if bs_indicator_id - 1 in bs_available_mask:
                        label.setHidden(False)
                    else:
                        label.setHidden(True)

    def _create_label(self, text: str | None = None) -> QLabel:
        label = QLabel()
        label.setMinimumSize(30, 0)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if text:
            label.setText(str(text))
        else:
            label.setProperty("frameShape", "QFrame::Box")
            label.setStyleSheet(STYLE_NO_BACKGROUND)

        return label

    def _update_basestation_status_indicators(self) -> None:
        """Handling the base station status label handles to indicate
        the state of received data per base station"""
        container = self._basestation_stats_container

        # Ports the label number to the first index of the statistic id
        stats_id_port = {1: 0, 2: 1, 3: 4}

        for bs in range(16):
            for stats_indicator_id in range(1, 4):
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
                            label.setToolTip("Calibration data from cache")

                            calib_confirm = bs in self._bs_stats[stats_id + 1]
                            calib_updated = bs in self._bs_stats[stats_id + 2]

                            if calib_confirm:
                                label.setStyleSheet(STYLE_GREEN_BACKGROUND)
                                label.setToolTip("Calibration data verified")
                            if calib_updated:
                                label.setStyleSheet(STYLE_ORANGE_BACKGROUND)
                                label.setToolTip(
                                    "Calibration data updated, the geometry probably needs to be "
                                    + "re-estimated"
                                )
                        else:
                            label.setStyleSheet(STYLE_GREEN_BACKGROUND)
                    else:
                        label.setStyleSheet(STYLE_RED_BACKGROUND)
                        label.setToolTip("")

    def _load_sys_config_user_action(self) -> None:
        names = QFileDialog.getOpenFileName(
            self, "Open file", self._helper.current_folder, FILE_REGEX_YAML
        )

        if names[0] == "":
            return

        self._helper.current_folder = os.path.dirname(names[0])

        try:
            with open(names[0], "r", encoding="UTF8") as handle:
                config = LighthouseConfig.from_yaml(handle.read())
        except (OSError, InvalidArgumentError) as e:
            self._show_message(
                QMessageBox.Icon.Critical,
                "Import Config",
                f"Could not read the configuration file:\n{e}",
            )
            return

        self._start_config_task(self._write_sys_config(config))

    async def _write_sys_config(self, config: LighthouseConfig) -> None:
        if self._cf is None:
            return

        try:
            async with self._lh_memory_lock:
                result = await write_and_store_config(
                    self._cf,
                    geometries=config.geometries,
                    calibrations=config.calibrations,
                    system_type=config.system_type,
                )

            # Reset the bit fields for calibration data status to get a fresh view
            await self._cf.param().set("lighthouse.bsCalibReset", 1)
        except DisconnectedError:
            raise
        except CrazyflieError as e:
            self._show_message(
                QMessageBox.Icon.Critical,
                "Import Config",
                f"Could not write the configuration to the Crazyflie:\n{e}",
            )
            return

        # New geo data has been written and stored in the CF, read it back to update the UI
        self._start_read_of_geo_data()

        if result.rejected_geometries:
            ids = ", ".join(str(bs_id + 1) for bs_id in result.rejected_geometries)
            self._show_message(
                QMessageBox.Icon.Warning,
                "Import Config",
                f"The configuration has geometry data for base station {ids}, but the "
                "Crazyflie does not support that many base stations. "
                "The geometry data for these base stations was not written.",
            )
        elif not result.persisted:
            self._show_message(
                QMessageBox.Icon.Warning,
                "Import Config",
                "The configuration was written to the Crazyflie, but could not be "
                "stored in permanent memory. It will be lost when the Crazyflie restarts.",
            )

    def _save_sys_config_user_action(self) -> None:
        names = QFileDialog.getSaveFileName(
            self, "Save file", self._helper.current_folder, FILE_REGEX_YAML
        )

        if names[0] == "":
            return

        self._helper.current_folder = os.path.dirname(names[0])

        if not names[0].endswith(".yaml") and names[0].find(".") < 0:
            filename = names[0] + ".yaml"
        else:
            filename = names[0]

        self._start_config_task(self._save_sys_config(filename))

    async def _save_sys_config(self, filename: str) -> None:
        if self._cf is None:
            return

        try:
            # Get calibration data from the Crazyflie to complete the system config data set
            async with self._lh_memory_lock:
                calibs = await self._cf.memory().read_lighthouse_calibrations()
        except DisconnectedError:
            raise
        except CrazyflieError as e:
            self._show_message(
                QMessageBox.Icon.Critical,
                "Export Config",
                f"Could not read the calibration data from the Crazyflie:\n{e}",
            )
            return

        system_type = await self._system_type_dialog.get_system_type()
        config = LighthouseConfig(
            system_type=system_type, geometries=self._lh_geos, calibrations=calibs
        )

        try:
            with open(filename, "w", encoding="UTF8") as handle:
                handle.write(config.to_yaml())
        except OSError as e:
            self._show_message(
                QMessageBox.Icon.Critical,
                "Export Config",
                f"Could not write the configuration file:\n{e}",
            )

    def _start_config_task(self, coro: Coroutine[object, object, None]) -> None:
        """Run an import or export task. The buttons are disabled while it runs."""
        self._config_task = create_task(self._run_config_task(coro))
        self._update_ui()

    async def _run_config_task(self, coro: Coroutine[object, object, None]) -> None:
        try:
            await coro
        finally:
            if self._config_task is asyncio.current_task():
                self._config_task = None
                self._update_ui()

    def _show_message(self, icon: QMessageBox.Icon, title: str, text: str) -> None:
        # Not modal, as this may be called from a task
        msg = QMessageBox(self)
        msg.setIcon(icon)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.show()
