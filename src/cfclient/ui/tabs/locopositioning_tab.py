#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2023 Bitcraze AB
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

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from collections.abc import Callable, Iterable, Sequence

import struct

from PySide6.QtUiTools import loadUiType
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget

import cfclient
from cfclient.ui.tab_toolbox import TabToolbox
from cfclient.gui import create_task
from cfclient.ui.pluginhelper import PluginHelper
from cflib2 import Crazyflie
from cflib2.error import DisconnectedError
from cflib2.memory import LocoAnchorData

from cfclient.ui.dialogs.anchor_position_dialog import AnchorPositionDialog

from vispy import scene
import numpy as np

import copy

__author__ = "Bitcraze AB"
__all__ = ["LocoPositioningTab"]

logger = logging.getLogger(__name__)

locopositioning_tab_class = loadUiType(
    cfclient.module_path + "/ui/tabs/locopositioning_tab.ui"
)[0]

STYLE_RED_BACKGROUND = "background-color: lightpink;"
STYLE_GREEN_BACKGROUND = "background-color: lightgreen;"
STYLE_NO_BACKGROUND = "background-color: none;"


class Anchor:
    def __init__(
        self, x: float = 0.0, y: float = 0.0, z: float = 0.0, distance: float = 0.0
    ) -> None:
        self.x = x
        self.y = y
        self.z = z
        self._is_position_valid = False
        self._is_active = False
        self.distance = distance

    def set_position(self, position: Sequence[float]) -> None:
        """Sets the position."""
        self.x = position[0]
        self.y = position[1]
        self.z = position[2]
        self._is_position_valid = True

    def get_position(self) -> tuple[float, float, float]:
        """Returns the position as a vector"""
        return (self.x, self.y, self.z)

    def is_position_valid(self) -> bool:
        return self._is_position_valid

    def set_is_active(self, is_active: bool) -> None:
        self._is_active = is_active

    def is_active(self) -> bool:
        return self._is_active


class LoPoAnchor:
    LPP_TYPE_POSITION = 1
    LPP_TYPE_REBOOT = 2
    LPP_TYPE_MODE = 3

    def __init__(self, cf: Crazyflie) -> None:
        self._lpp = cf.localization().loco_positioning()

    async def set_position(
        self, anchor_id: int, position: tuple[float, float, float]
    ) -> None:
        data = struct.pack("<Bfff", self.LPP_TYPE_POSITION, *position)
        await self._lpp.send_short_lpp_packet(anchor_id, list(data))

    async def set_mode(self, anchor_id: int, mode: int) -> None:
        data = struct.pack("<BB", self.LPP_TYPE_MODE, mode)
        await self._lpp.send_short_lpp_packet(anchor_id, list(data))


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

    def __init__(self) -> None:
        scene.SceneCanvas.__init__(self, keys=None)
        self.unfreeze()

        self._view = self.central_widget.add_view()
        self._view.bgcolor = "#ffffff"
        self._view.camera = scene.TurntableCamera(
            distance=10.0, up="+z", center=(0.0, 0.0, 1.0)
        )

        self._cf = scene.visuals.Markers(
            pos=np.array([[0, 0, 0]]),
            parent=self._view.scene,
            face_color=self.POSITION_BRUSH,
        )
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
            parent=self._view.scene,
        )

        self.addArrows(1, 0.02, 0.1, 0.1, self._view.scene)

    def addArrows(
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

    def update_data(
        self, anchors: dict[int, Anchor], pos: list[float], display_mode: DisplayMode
    ) -> None:
        self._cf.set_data(pos=np.array([pos]), face_color=self.POSITION_BRUSH)

        for id, anchor in anchors.items():
            self._update_anchor(id, anchor, display_mode)

        self._purge_anchors(anchors.keys())

    def _update_anchor(
        self, id: int, anchor: Anchor, display_mode: DisplayMode
    ) -> None:
        if anchor.is_active():
            color = self.ANCHOR_BRUSH
        else:
            color = self.ANCHOR_BRUSH_INVALID

        size = self.ANCHOR_SIZE
        font_size = self.LABEL_SIZE
        distance = anchor.distance
        if display_mode is DisplayMode.identify_anchor:
            if distance < self.VICINITY_DISTANCE:
                amount = (distance - self.HIGHLIGHT_DISTANCE) / (
                    self.VICINITY_DISTANCE - self.HIGHLIGHT_DISTANCE
                )
                color = self._mix(color, self.HIGHLIGHT_ANCHOR_BRUSH, amount)

            if distance < self.HIGHLIGHT_DISTANCE:
                color = self.HIGHLIGHT_ANCHOR_BRUSH
                size = self.HIGHLIGHT_SIZE
                font_size = self.LABEL_HIGHLIGHT_SIZE

        marker_pos = anchor.get_position()
        text_pos = self.TEXT_OFFSET + marker_pos
        if id in self._anchor_contexts:
            self._anchor_contexts[id][0].set_data(
                pos=np.array([marker_pos]), face_color=color, size=size
            )

            text = self._anchor_contexts[id][1]
            text.pos = text_pos
            text.font_size = font_size
        else:
            marker = scene.visuals.Markers(
                pos=np.array([marker_pos]),
                face_color=color,
                size=size,
                parent=self._view.scene,
            )
            text = scene.visuals.Text(
                text=str(id), font_size=font_size, pos=text_pos, parent=self._view.scene
            )
            self._anchor_contexts[id] = [marker, text]

    def _purge_anchors(self, keep: Iterable[int]) -> None:
        to_remove = []
        for id, context in self._anchor_contexts.items():
            if id not in keep:
                to_remove.append(id)
                for visual in context:
                    visual.parent = None
        for id in to_remove:
            self._anchor_contexts.pop(id)

    def _mix(self, col1: np.ndarray, col2: np.ndarray, mix: float) -> np.ndarray:
        return col1 * mix + col2 * (1.0 - mix)


class DisplayMode(Enum):
    identify_anchor = 1
    estimated_position = 2


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

    PARAM_MODE_GR = "loco"
    PARAM_MODE_NM = "mode"
    PARAM_MODE = PARAM_MODE_GR + "." + PARAM_MODE_NM

    # Frame rate (updates per second)
    FPS = 2

    # Max difference (m) for an anchor position to count as already written
    ANCHOR_POSITION_TOLERANCE = 0.005

    def __init__(self, helper: PluginHelper) -> None:
        super(LocoPositioningTab, self).__init__(helper, "Loco Positioning")
        self.setupUi(self)
        self._cf: Crazyflie | None = None
        self._on_connected_task = None
        self._mode_task = None
        self._anchor_mode_task = None
        self._poll_task = None
        self._log_tasks = []
        self._write_positions_task = None

        self._anchors = {}
        self._clear_state()

        self._display_mode = DisplayMode.estimated_position

        self._id_anchor_button.toggled.connect(
            lambda enabled: self._do_when_checked(
                enabled, self._set_display_mode, DisplayMode.identify_anchor
            )
        )

        self._estimated_postion_button.toggled.connect(
            lambda enabled: self._do_when_checked(
                enabled, self._set_display_mode, DisplayMode.estimated_position
            )
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
            lambda enabled: self._send_anchor_mode(self.LOCO_MODE_TWR)
        )
        self._switch_mode_to_tdoa2_button.clicked.connect(
            lambda enabled: self._send_anchor_mode(self.LOCO_MODE_TDOA2)
        )
        self._switch_mode_to_tdoa3_button.clicked.connect(
            lambda enabled: self._send_anchor_mode(self.LOCO_MODE_TDOA3)
        )

        self._clear_anchors_button.clicked.connect(self._clear_anchors)

        self._configure_anchor_positions_button.clicked.connect(
            self._show_anchor_postion_dialog
        )

        self._set_up_plots()

        self.is_loco_deck_active = False

        self._graph_timer = QTimer()
        self._graph_timer.setInterval(int(1000 / self.FPS))
        self._graph_timer.timeout.connect(self._update_graphics)
        self._graph_timer.start()

        self._update_position_label(self._helper.pose_logger.position)

        self._lps_state = self.LOCO_MODE_UNKNOWN
        self._update_lps_state(self.LOCO_MODE_UNKNOWN)

        self._anchor_position_dialog = AnchorPositionDialog(self, helper)
        self._configure_anchor_positions_button.setEnabled(False)

    def _do_when_checked(
        self, enabled: bool, fkn: Callable[[DisplayMode], None], arg: DisplayMode
    ) -> None:
        if enabled:
            fkn(arg)

    def _set_up_plots(self) -> None:
        self._plot_3d = Plot3dLps()
        self._plot_layout.addWidget(self._plot_3d.native)

    def _set_display_mode(self, display_mode: DisplayMode) -> None:
        self._display_mode = display_mode

    def _send_anchor_mode(self, mode: int) -> None:
        if self._cf is not None:
            self._anchor_mode_task = create_task(
                self._send_anchor_mode_async(self._cf, mode)
            )

    async def _send_anchor_mode_async(self, cf: Crazyflie, mode: int) -> None:
        lopo = LoPoAnchor(cf)
        # Set the mode from the last to the first anchor
        # In TDoA 2 mode this ensures that the master anchor is set last
        # Note: We only switch mode of anchor 0 - 7 since this is what is
        # supported in TWR and TDoA 2
        for _ in range(5):
            for anchor_id in reversed(range(8)):
                await lopo.set_mode(anchor_id, mode)

    def _clear_state(self) -> None:
        self._clear_anchors()
        self._update_ranging_status_indicators()
        self._id_anchor_button.setEnabled(True)

    def _clear_anchors(self) -> None:
        self._anchors = {}

    def connected(self, cf: Crazyflie) -> None:
        """Called by TabToolbox when the Crazyflie has been connected"""
        self._cf = cf
        self._on_connected_task = create_task(self._on_connected(cf))

    async def _on_connected(self, cf: Crazyflie) -> None:
        param = cf.param()
        names = param.names()
        deck_present = False

        for name in ("deck.bcLoco", "deck.bcDWM1000"):
            if name in names and int(await param.get(name)) == 1:
                deck_present = True

        if deck_present:
            logger.debug("Loco deck installed, enabling LPS tab")
            self._loco_deck_detected(cf)
            if self.PARAM_MODE in names:
                mode = await param.get(self.PARAM_MODE)
                self._loco_mode_updated(self.PARAM_MODE, mode)
                self._enable_mode_buttons(True)
        else:
            logger.debug("No loco deck installed")

    def _loco_deck_detected(self, cf: Crazyflie) -> None:
        """Called when the loco deck has been detected. Enables the tab,
        starts logging and polling of the memory sub system as well as starts
        timers for updating graphics"""
        if not self.is_loco_deck_active:
            self.is_loco_deck_active = True
            self._log_tasks = [
                create_task(
                    self._stream_log(
                        cf,
                        [f"ranging.distance{i}" for i in range(4)],
                        self.UPDATE_PERIOD_LOG,
                        self._anchor_range_received,
                    )
                ),
                create_task(
                    self._stream_log(
                        cf,
                        [f"ranging.distance{i}" for i in range(4, 8)],
                        self.UPDATE_PERIOD_LOG,
                        self._anchor_range_received,
                    )
                ),
                create_task(
                    self._stream_log(
                        cf,
                        [self.PARAM_MODE],
                        self.UPDATE_PERIOD_LOCO_MODE,
                        self._loco_sys_received,
                    )
                ),
            ]

            self._poll_task = create_task(self._poll_anchors(cf))
            self._configure_anchor_positions_button.setEnabled(True)

    def disconnected(self) -> None:
        """Called by TabToolbox when the Crazyflie has been disconnected"""
        for task in [
            self._on_connected_task,
            self._mode_task,
            self._anchor_mode_task,
            self._poll_task,
            *self._log_tasks,
            self._write_positions_task,
        ]:
            if task is not None:
                task.cancel()
        self._on_connected_task = None
        self._mode_task = None
        self._anchor_mode_task = None
        self._cf = None
        self._poll_task = None
        self._log_tasks = []
        self._write_positions_task = None

        self._clear_state()
        self._update_graphics()
        self.is_loco_deck_active = False
        self._update_lps_state(self.LOCO_MODE_UNKNOWN)
        self._enable_mode_buttons(False)
        self._loco_mode_updated("", self.LOCO_MODE_UNKNOWN)
        self._configure_anchor_positions_button.setEnabled(False)
        QTimer.singleShot(0, self._anchor_position_dialog.close)

    async def _stream_log(
        self,
        cf: Crazyflie,
        variables: list[str],
        period_ms: int,
        handler: Callable[[dict], None],
    ) -> None:
        log = cf.log()
        names = log.names()
        variables = [v for v in variables if v in names]
        if not variables:
            return
        block = await log.create_block()
        for variable in variables:
            await block.add_variable(variable)
        stream = await block.start(period_ms)

        try:
            while True:
                data = await stream.next()
                handler(data.data)
        finally:
            try:
                await asyncio.shield(stream.stop())
            except (DisconnectedError, asyncio.CancelledError):
                pass

    def _anchor_range_received(self, data: dict) -> None:
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

    def _loco_sys_received(self, data: dict) -> None:
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

    def _update_ranging_status_indicators(self) -> None:
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
                label.setProperty("frameShape", "QFrame::Box")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

    async def _poll_anchors(self, cf: Crazyflie) -> None:
        while True:
            lps = await cf.memory().read_loco_anchor_data()
            self._active_id_list_updated(lps.active_anchor_ids)
            self._anchor_data_updated(lps.anchors)
            await asyncio.sleep(self.UPDATE_PERIOD_ANCHOR_STATE / 1000)

    def _active_id_list_updated(self, anchor_list: list[int]) -> None:
        """Called from the anchor polling when we get a list of active
        anchors"""
        for id, anchor_data in self._anchors.items():
            anchor_data.set_is_active(False)

        for id in anchor_list:
            anchor_data = self._get_create_anchor(id)
            anchor_data.set_is_active(True)

        self._update_ranging_status_indicators()

    def _anchor_data_updated(self, position_dict: dict[int, LocoAnchorData]) -> None:
        """Called from the anchor polling when the anchor positions
        are updated"""
        for id, anchor_data in position_dict.items():
            anchor = self._get_create_anchor(id)
            if anchor_data.is_valid:
                anchor.set_position(anchor_data.position)

        self._update_positions_in_config_dialog()

    def _parse_range_param_name(self, name: str) -> tuple[bool, int]:
        """Parse a parameter name for a ranging distance and return the number
        of the anchor. The name is on the format 'ranging.distance4'"""
        valid = False
        anchor = 0
        if name.startswith("ranging.distance"):
            anchor = int(name[-1])
            valid = True
        return (valid, anchor)

    def _get_create_anchor(self, anchor_number: int) -> Anchor:
        if anchor_number not in self._anchors:
            self._anchors[anchor_number] = Anchor()
        return self._anchors[anchor_number]

    def _anchor_exists(self, anchor_number: int) -> bool:
        return anchor_number in self._anchors

    def _update_graphics(self) -> None:
        if self.is_visible() and self.is_loco_deck_active:
            anchors = copy.deepcopy(self._anchors)
            self._plot_3d.update_data(
                anchors, self._helper.pose_logger.position, self._display_mode
            )
            self._update_position_label(self._helper.pose_logger.position)

    def _update_position_label(self, position: list[float]) -> None:
        if len(position) == 3:
            coordinate = "({:0.2f}, {:0.2f}, {:0.2f})".format(
                position[0], position[1], position[2]
            )
        else:
            coordinate = "(0.00, 0.00, 0.00)"

        self._status_position.setText(coordinate)

    def _update_lps_state(self, state: int) -> None:
        if state != self._lps_state:
            self._update_lps_state_indicator(
                self._state_twr, state == self.LOCO_MODE_TWR
            )
            self._update_lps_state_indicator(
                self._state_tdoa2, state == self.LOCO_MODE_TDOA2
            )
            self._update_lps_state_indicator(
                self._state_tdoa3, state == self.LOCO_MODE_TDOA3
            )
        self._lps_state = state

    def _update_lps_state_indicator(self, element: QWidget, active: bool) -> None:
        if active:
            element.setStyleSheet(STYLE_GREEN_BACKGROUND)
        else:
            element.setStyleSheet(STYLE_NO_BACKGROUND)

    def _enable_mode_buttons(self, enabled: bool) -> None:
        self._mode_auto.setEnabled(enabled)
        self._mode_twr.setEnabled(enabled)
        self._mode_tdoa2.setEnabled(enabled)
        self._mode_tdoa3.setEnabled(enabled)

    def _request_mode(self, enabled: bool, mode: int) -> None:
        if enabled:
            if self._cf is not None:
                self._mode_task = create_task(self._set_mode_param(self._cf, mode))

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

    async def _set_mode_param(self, cf: Crazyflie, mode: int) -> None:
        await cf.param().set(self.PARAM_MODE, mode)

    def _loco_mode_updated(self, name: str, value: int | float) -> None:
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

    def _show_anchor_postion_dialog(self) -> None:
        self._anchor_position_dialog.show()

    def _update_positions_in_config_dialog(self) -> None:
        positions: dict[int, tuple[float, float, float]] = {}

        for id, anchor in self._anchors.items():
            if anchor.is_position_valid():
                positions[id] = (anchor.x, anchor.y, anchor.z)

        self._anchor_position_dialog.anchor_postions_updated(positions)

    def write_positions_to_anchors(
        self, anchor_positions: dict[int, tuple[float, float, float]]
    ) -> None:
        if self._cf is None or self._write_positions_task is not None:
            return

        # Anchors that already report the target position don't need a packet
        to_write = {
            anchor_id: position
            for anchor_id, position in anchor_positions.items()
            if not self._anchor_has_position(anchor_id, position)
        }
        logger.info(
            "Writing positions to anchors %s, %d already up to date",
            sorted(to_write),
            len(anchor_positions) - len(to_write),
        )
        if not to_write:
            return

        self._anchor_position_dialog.set_writing(True)
        self._write_positions_task = create_task(
            self._write_positions_to_anchors_async(self._cf, to_write)
        )

    def _anchor_has_position(
        self, anchor_id: int, position: tuple[float, float, float]
    ) -> bool:
        anchor = self._anchors.get(anchor_id)
        if anchor is None or not anchor.is_position_valid():
            return False
        return all(
            abs(current - target) < self.ANCHOR_POSITION_TOLERANCE
            for current, target in zip(anchor.get_position(), position)
        )

    async def _write_positions_to_anchors_async(
        self, cf: Crazyflie, anchor_positions: dict[int, tuple[float, float, float]]
    ) -> None:
        lopo = LoPoAnchor(cf)
        try:
            for _ in range(3):
                for anchor_id, position in anchor_positions.items():
                    await lopo.set_position(anchor_id, position)
                await asyncio.sleep(0.2)
        finally:
            self._write_positions_task = None
            self._anchor_position_dialog.set_writing(False)
