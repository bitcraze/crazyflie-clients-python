#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2026 Bitcraze AB
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
The console tab is used as a console for printouts from the Crazyflie. With more than one console,
for example with the WiFi camera deck, there is a segment for each of them and one for all of them.
"""

import logging

from PyQt6 import uic
from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QWIDGETSIZE_MAX

import cfclient
from cfclient.ui.tab_toolbox import TabToolbox
from cfclient.ui.widgets.segmented_control import Segment
from cfclient.utils.console_backend import ConsoleBackend
from cfclient.utils.console_model import ALL, STM32_PATH, ConsoleModel, segment_label, split_path

__author__ = 'Bitcraze AB'
__all__ = ['ConsoleTab']

logger = logging.getLogger(__name__)

console_tab_class = uic.loadUiType(cfclient.module_path +
                                   "/ui/tabs/consoleTab.ui")[0]

# Width of the right column when there are several consoles
SIDE_COLUMN_WIDTH = 250


class ConsoleTab(TabToolbox, console_tab_class):
    """Console tab for showing printouts from Crazyflie"""
    _link_established_signal = pyqtSignal(str)
    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)

    def __init__(self, helper):
        super(ConsoleTab, self).__init__(helper, 'Console')
        self.setupUi(self)

        self._model = ConsoleModel()
        self._backend = ConsoleBackend(self)
        # Generation of the connection the backend signals are accepted from
        self._generation = None
        self._segment_keys = None
        self._segment_signature = None
        self._error_path = None
        self._open_for_all = set()
        self._log_dirty = True

        self._build_ui()

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._link_established_signal.connect(self._link_established)
        self._connected_signal.connect(self._connected)
        self._disconnected_signal.connect(self._disconnected)

        self._helper.cf.connected.add_callback(self._connected_signal.emit)
        self._helper.cf.link_established.add_callback(self._link_established_signal.emit)
        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

        self._clearButton.clicked.connect(self.clear)
        self._dumpSystemLoadButton.clicked.connect(
            lambda enabled:
            self._helper.cf.param.set_value("system.taskDump", '1'))
        self._dumpAssertInformation.clicked.connect(
            lambda enabled:
            self._helper.cf.param.set_value_raw("system.assertInfo", 0x08, 1))
        self._propellerTestButton.clicked.connect(
            lambda enabled:
            self._helper.cf.param.set_value("health.startPropTest", '1'))
        self._batteryTestButton.clicked.connect(
            lambda enabled:
            self._helper.cf.param.set_value("health.startBatTest", '1'))
        self._storageStatsButton.clicked.connect(
            lambda enabled:
            self._helper.cf.param.set_value("system.storageStats", '1'))

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        backend = self._backend
        backend.catalog.connect(self._on_catalog)
        backend.catalog_failed.connect(self._on_catalog_failed)
        backend.opened.connect(self._on_opened)
        backend.open_failed.connect(self._on_open_failed)
        backend.chunk.connect(self._on_chunk)

        self._refresh_layout()
        self._view_changed()

    def _build_ui(self):
        self._segments.set_equal_width(False)
        self._segments.currentIndexChanged.connect(self._segment_changed)
        self._errorPanel.retry_requested.connect(self._request_open)
        self._errorPanel.dismissed.connect(self._dismiss_error)
        self._allBox.select_requested.connect(self._select)

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        self._dumpSystemLoadButton.setEnabled(True)
        self._propellerTestButton.setEnabled(True)
        self._batteryTestButton.setEnabled(True)
        self._storageStatsButton.setEnabled(True)

        # Show cf:stm32 now, with its history to get the startup messages, and read the list in the background
        self._model.reconnect()
        self._open_for_all.clear()
        self._error_path = None
        self._generation = self._backend.start(self._helper.cf.console)
        self._model.begin_open(STM32_PATH)
        self._backend.open(STM32_PATH)
        self._backend.request_list()
        self._set_switcher_enabled(True)
        self._refresh_layout()
        self._view_changed()

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        self._dumpSystemLoadButton.setEnabled(False)
        self._dumpAssertInformation.setEnabled(False)
        self._propellerTestButton.setEnabled(False)
        self._batteryTestButton.setEnabled(False)
        self._storageStatsButton.setEnabled(False)

        # The streams have ended, the last output stays on screen
        self._backend.stop()
        self._generation = None
        self._set_switcher_enabled(False)

    def _link_established(self, link_uri):
        """Callback when the first packet on a new link is received"""
        # Enable the assert dump button as early as possible. After an assert we will never get the connected() cb.
        self._dumpAssertInformation.setEnabled(True)

    def _set_switcher_enabled(self, enabled):
        self._segments.setEnabled(enabled)
        self._errorPanel.set_enabled(enabled)

    @property
    def _is_connected(self):
        return self._generation is not None

    def _current(self, generation):
        return generation == self._generation

    def _on_catalog(self, generation, paths):
        if not self._current(generation):
            return
        self._model.set_catalog(paths)
        self._refresh_layout()

    def _on_catalog_failed(self, generation, errno, message):
        # Not shown, the tab stays without other consoles
        if self._current(generation):
            logger.warning('Could not read the console list: %s (errno %s)', message, errno)

    def _on_chunk(self, generation, path, text):
        if not self._current(generation):
            return
        self._model.feed(path, text)
        self._log_dirty = True

    def _on_opened(self, generation, path):
        if not self._current(generation):
            return
        self._model.mark_open(path)
        if path != STM32_PATH and path not in self._open_for_all:
            self._model.select(path)
        self._open_for_all.discard(path)
        self._refresh_layout()
        self._view_changed()

    def _on_open_failed(self, generation, path, errno, message):
        if not self._current(generation):
            return
        logger.warning('Could not open console %s: %s (errno %s)', path, message, errno)
        self._model.mark_open_failed(path)
        self._open_for_all.discard(path)
        self._error_path = path
        self._errorPanel.show_error(path, errno, message)
        self._refresh_layout()
        self._view_changed()

    def _request_open(self, path):
        if not self._is_connected:
            return
        self._error_path = None
        self._model.begin_open(path)
        self._backend.open(path)
        self._refresh_layout()
        self._view_changed()

    def _dismiss_error(self, path):
        self._error_path = None
        self._view_changed()

    def _select(self, key):
        self._model.select(key)
        self._error_path = None
        self._refresh_layout()
        self._view_changed()

    def _segment_changed(self, index):
        if self._segment_keys is None or index >= len(self._segment_keys):
            return
        key = self._segment_keys[index]
        if key == ALL:
            self._open_all()
        if key == ALL or self._model.states[key].is_open:
            self._select(key)
            return
        # Open it, and select it when it has opened
        self._segments.set_current_index(self._segment_keys.index(self._model.selected), emit=False)
        if not self._model.states[key].opening:
            self._request_open(key)

    def _open_all(self):
        # All shows the open consoles, and stays selected when they have opened
        for path in self._model.other_paths:
            state = self._model.states[path]
            if not state.is_open and not state.opening:
                self._open_for_all.add(path)
                self._request_open(path)

    def clear(self):
        self._model.clear(self._model.selected)
        self._view_changed()

    def _refresh_layout(self):
        switcher = bool(self._model.other_paths)
        self._switchRow.setVisible(switcher)

        if switcher:
            self._sideStack.setFixedWidth(SIDE_COLUMN_WIDTH)
            self._rebuild_segments()
        else:
            self._segment_keys = None
            self._segment_signature = None
            self._sideStack.setMinimumWidth(0)
            self._sideStack.setMaximumWidth(QWIDGETSIZE_MAX)

    def _rebuild_segments(self):
        model = self._model
        keys = [ALL] + model.catalog
        signature = [ALL] + [(p, model.states[p].is_open) for p in model.catalog]
        if signature != self._segment_signature:
            self._segment_signature = signature
            self._segment_keys = keys
            segments = ['All']
            for path in model.catalog:
                state = model.states[path]
                label = segment_label(path)
                if label:
                    segments.append(Segment(label, color=state.color, dimmed=not state.is_open))
                else:
                    prefix, name = split_path(path)
                    segments.append(Segment(name, prefix, state.color, monospace=True, dimmed=not state.is_open))
            self._segments.set_segments(segments, keys.index(model.selected), emit=False)
        else:
            self._segments.set_current_index(keys.index(model.selected), emit=False)
        self._update_badges()

    def _update_badges(self):
        if self._segment_keys is None:
            return
        for index, key in enumerate(self._segment_keys):
            if key != ALL and self._model.states[key].is_open:
                # No badges in All
                unread = 0 if self._model.selected == ALL else self._model.states[key].unread
                self._segments.set_badge(index, unread)

    def _view_changed(self):
        model = self._model
        key = model.selected

        if self._segment_keys is not None and key in self._segment_keys:
            self._segments.set_current_index(self._segment_keys.index(key), emit=False)

        if key == ALL:
            self._sideStack.setCurrentWidget(self._allBox)
            self._allBox.show_consoles(model)
        elif key == STM32_PATH:
            self._sideStack.setCurrentWidget(self._commandsPage)
        else:
            self._sideStack.setCurrentWidget(self._emptyPage)

        self._logStack.setCurrentWidget(self._errorPanel if self._error_path else self.console)
        self.console.reset()
        self._log_dirty = True
        self._update_badges()

    def _tick(self):
        if self._log_dirty:
            self._log_dirty = False
            self.console.refresh(self._model)
        if self._segment_keys is not None:
            self._update_badges()
