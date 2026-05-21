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
#  this program; if not, write to the Free Software Foundation, Inc., 51
#  Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""
The main file for the Crazyflie control application.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable, Coroutine
from concurrent.futures import Future
from typing import Any

import cfclient
from cfclient.gui import create_task
from cfclient.ui.pose_logger import PoseLogger
from cfclient.ui.tab_toolbox import TabToolbox
import cfclient.ui.tabs
from cfclient.ui.connectivity_manager import ConnectivityManager
from cfclient.utils.config import Config
from cfclient.utils.config_manager import ConfigManager
from cfclient.utils.input import JoystickReader
from cfclient.utils.input.inputreaderinterface import InputReaderInterface
from cfclient.utils.ui import UiUtils
from cfclient.ui.dialogs.inputconfigdialogue import InputConfigDialogue
from cflib2 import Crazyflie, LinkContext
from cflib2.error import DisconnectedError
from cflib2.toc_cache import FileTocCache
from PySide6 import QtWidgets
from PySide6.QtUiTools import loadUiType
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot
from PySide6.QtCore import QDir
from PySide6.QtCore import QUrl
from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtGui import QActionGroup
from PySide6.QtGui import QShortcut
from PySide6.QtGui import QCloseEvent
from PySide6.QtGui import QDesktopServices
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QMenu
from PySide6.QtWidgets import QMessageBox

__author__ = "Bitcraze AB"
__all__ = ["MainUI"]

logger = logging.getLogger(__name__)

(main_window_class, main_windows_base_class) = loadUiType(
    cfclient.module_path + "/ui/main.ui"
)  # type: ignore[misc]


UIState = ConnectivityManager.UIState


class BatteryStates:
    BATTERY, CHARGING, CHARGED, LOW_POWER = list(range(4))


class MainUI(QtWidgets.QMainWindow, main_window_class):
    _battery_signal = Signal(float, int)
    _input_device_error_signal = Signal(str)
    _input_discovery_signal = Signal(object)

    def __init__(self, *args: object) -> None:
        super(MainUI, self).__init__(*args)
        self.setupUi(self)

        self.cf = None
        self.uiState = UIState.DISCONNECTED
        self._link_context = LinkContext()
        self._toc_cache = FileTocCache(cfclient.config_path + "/cache")
        self._connect_task = None
        self._disconnect_watch_task = None
        self._battery_task = None
        self._disable_input = False
        self._loop = None

        # Restore window size if present in the config file
        try:
            size = Config().get("window_size")
            self.resize(size[0], size[1])
        except KeyError:
            pass

        # Keyboard shortcut
        self.connect_input = QShortcut("Ctrl+I", self.connectButton, self._connect)

        # Connect UI signals
        self.menuItemConnect.triggered.connect(self._connect)
        self.menuItemExit.triggered.connect(self.closeAppRequest)
        self._menuItem_openconfigfolder.triggered.connect(self._open_config_folder)

        # TODO: migrate these to cflib2
        self.menuItemAbout.setEnabled(False)
        self.menuItemBootloader.setEnabled(False)
        self._menu_cf2_config.setEnabled(False)
        self.logConfigAction.setEnabled(False)

        self.menuItemConfInputDevice.triggered.connect(
            self._show_input_device_config_dialog
        )

        # Emergency stop button
        self.esButton.setEnabled(False)
        self.esButton.clicked.connect(self._emergency_stop)

        self._set_address()

        self._connectivity_manager = ConnectivityManager()
        self._connectivity_manager.register_ui_elements(
            ConnectivityManager.UiElementsContainer(
                interface_combo=self.interfaceCombo,
                address_spinner=self.address,
                connect_button=self.connectButton,
                scan_button=self.scanButton,
            )
        )

        self._connectivity_manager.connect_button_clicked.connect(self._connect)
        self._connectivity_manager.scan_button_clicked.connect(self._scan)

        self.batteryBar.setTextVisible(False)
        self.linkQualityBar.setTextVisible(False)

        # Input device reader (joystick)
        self._joystick_reader = JoystickReader()
        self._active_device = ""

        self._statusbar_label = QLabel("No input-device found, insert one to fly.")
        self.statusBar().addWidget(self._statusbar_label)

        # Connect joystick input to Crazyflie commander
        self._joystick_reader.input_updated.add_callback(self._send_setpoint)
        self._joystick_reader.assisted_input_updated.add_callback(
            self._send_velocity_world
        )
        self._joystick_reader.heighthold_input_updated.add_callback(
            self._send_zdistance
        )
        self._joystick_reader.hover_input_updated.add_callback(self._send_hover)

        # Input device error and discovery signals
        self._input_device_error_signal.connect(self._display_input_device_error)
        self._joystick_reader.device_error.add_callback(
            self._input_device_error_signal.emit
        )
        self._input_discovery_signal.connect(self.device_discovery)
        self._joystick_reader.device_discovery.add_callback(
            self._input_discovery_signal.emit
        )

        # pluginhelper for tabs
        self._pose_logger = PoseLogger()
        cfclient.ui.pluginhelper.inputDeviceReader = self._joystick_reader
        cfclient.ui.pluginhelper.pose_logger = self._pose_logger
        cfclient.ui.pluginhelper.connectivity_manager = self._connectivity_manager
        cfclient.ui.pluginhelper.mainUI = self

        self._connectivity_manager.set_address(self.address.value())

        self._initial_scan = True
        QTimer.singleShot(0, self._on_event_loop_ready)

        # Battery monitoring signal
        self._battery_signal.connect(self._update_battery)

        # Tabs and toolboxes
        self.tabs_menu_item = QMenu("Tabs", self.menuView)
        self.menuView.addMenu(self.tabs_menu_item)

        self.toolboxes_menu_item = QMenu("Toolboxes", self.menuView)
        self.menuView.addMenu(self.toolboxes_menu_item)

        self.loaded_tab_toolboxes = self.create_tab_toolboxes(
            self.tabs_menu_item, self.toolboxes_menu_item, self.tab_widget
        )
        self.read_tab_toolbox_config(self.loaded_tab_toolboxes)

        # Input device mux menu
        self._all_role_menus = ()
        self._available_devices = ()
        self._all_mux_nodes = ()

        self._mux_group = QActionGroup(self._menu_inputdevice)
        self._mux_group.setExclusive(True)
        for m in self._joystick_reader.available_mux():
            node = QAction(
                m.name, self._menu_inputdevice, checkable=True, enabled=False
            )
            node.toggled.connect(self._mux_selected)
            self._mux_group.addAction(node)
            self._menu_inputdevice.addAction(node)
            self._all_mux_nodes += (node,)
            mux_subnodes = ()
            for name in m.supported_roles():
                sub_node = QMenu(
                    "    {}".format(name), self._menu_inputdevice, enabled=False
                )
                self._menu_inputdevice.addMenu(sub_node)
                mux_subnodes += (sub_node,)
                self._all_role_menus += ({"muxmenu": node, "rolemenu": sub_node},)
            node.setData((m, mux_subnodes))

        self._mapping_support = True

        # Theme selection
        self._theme_group = QActionGroup(self.menuThemes)
        self._theme_group.setExclusive(True)
        self._theme_checkboxes = []
        for theme in UiUtils.THEMES:
            node = QAction(theme, self.menuThemes, checkable=True)
            node.setObjectName(theme)
            node.toggled.connect(self._theme_selected)
            self._theme_checkboxes.append(node)
            self._theme_group.addAction(node)
            self.menuThemes.addAction(node)

    # --- Tabs/toolboxes ---

    def create_tab_toolboxes(
        self,
        tabs_menu_item: QMenu,
        toolboxes_menu_item: QMenu,
        tab_widget: QtWidgets.QTabWidget,
    ) -> dict[str, TabToolbox]:
        loaded_tab_toolboxes = {}

        for tab_class in cfclient.ui.tabs.available:
            tab_toolbox = tab_class(cfclient.ui.pluginhelper)
            loaded_tab_toolboxes[tab_toolbox.get_tab_toolbox_name()] = tab_toolbox

            tab_action_item = QAction(tab_toolbox.get_tab_toolbox_name())
            tab_action_item.setCheckable(True)
            tab_action_item.triggered.connect(
                lambda checked, tb=tab_toolbox: self.toggle_tab_visibility(checked, tb)
            )
            tab_toolbox.tab_action_item = tab_action_item
            tabs_menu_item.addAction(tab_action_item)

            toolbox_action_item = QAction(tab_toolbox.get_tab_toolbox_name())
            toolbox_action_item.setCheckable(True)
            toolbox_action_item.triggered.connect(
                lambda checked, tb=tab_toolbox: self.toggle_toolbox_visibility(
                    checked, tb
                )
            )
            tab_toolbox.toolbox_action_item = toolbox_action_item
            tab_toolbox.dock_widget.closed.connect(
                lambda _=None, tb=tab_toolbox: self._tab_toolbox_hide(tb)
            )
            tab_toolbox.dock_widget.dockLocationChanged.connect(
                lambda area, tb=tab_toolbox: self.set_preferred_dock_area(area, tb)
            )
            toolboxes_menu_item.addAction(toolbox_action_item)

        return loaded_tab_toolboxes

    def read_tab_toolbox_config(
        self, loaded_tab_toolboxes: dict[str, TabToolbox]
    ) -> None:
        for name in TabToolbox.read_open_tab_config():
            if name in loaded_tab_toolboxes.keys():
                self._tab_toolbox_show_as_tab(loaded_tab_toolboxes[name])

        for name in TabToolbox.read_open_toolbox_config():
            if name in loaded_tab_toolboxes.keys():
                self._tab_toolbox_show_as_toolbox(loaded_tab_toolboxes[name])

    def toggle_tab_visibility(self, checked: bool, tab_toolbox: TabToolbox) -> None:
        if checked:
            self._tab_toolbox_show_as_tab(tab_toolbox)
        else:
            self._tab_toolbox_hide(tab_toolbox)

    def toggle_toolbox_visibility(self, checked: bool, tab_toolbox: TabToolbox) -> None:
        if checked:
            self._tab_toolbox_show_as_toolbox(tab_toolbox)
        else:
            self._tab_toolbox_hide(tab_toolbox)

    def _tab_toolbox_show_as_tab(self, tab_toolbox: TabToolbox) -> None:
        if tab_toolbox.get_display_state() == TabToolbox.DS_TOOLBOX:
            dock_widget = tab_toolbox.dock_widget
            self.removeDockWidget(dock_widget)
            dock_widget.hide()

        if tab_toolbox.get_display_state() != TabToolbox.DS_TAB:
            tab_toolbox_name = tab_toolbox.get_tab_toolbox_name()
            self.tab_widget.addTab(tab_toolbox, tab_toolbox_name)

        tab_toolbox.tab_action_item.setChecked(True)
        tab_toolbox.toolbox_action_item.setChecked(False)
        tab_toolbox.set_display_state(TabToolbox.DS_TAB)

    def _tab_toolbox_show_as_toolbox(self, tab_toolbox: TabToolbox) -> None:
        dock_widget = tab_toolbox.dock_widget

        if tab_toolbox.get_display_state() == TabToolbox.DS_TAB:
            self.tab_widget.removeTab(self.tab_widget.indexOf(tab_toolbox))

        if tab_toolbox.get_display_state() != TabToolbox.DS_TOOLBOX:
            self.addDockWidget(tab_toolbox.preferred_dock_area(), dock_widget)
            dock_widget.setWidget(tab_toolbox)
            dock_widget.show()

        tab_toolbox.tab_action_item.setChecked(False)
        tab_toolbox.toolbox_action_item.setChecked(True)
        tab_toolbox.set_display_state(TabToolbox.DS_TOOLBOX)

    def _tab_toolbox_hide(self, tab_toolbox: TabToolbox) -> None:
        dock_widget = tab_toolbox.dock_widget

        if tab_toolbox.get_display_state() == TabToolbox.DS_TAB:
            self.tab_widget.removeTab(self.tab_widget.indexOf(tab_toolbox))
        elif tab_toolbox.get_display_state() == TabToolbox.DS_TOOLBOX:
            self.removeDockWidget(dock_widget)
            dock_widget.hide()
            tab_toolbox.toolbox_action_item.setChecked(False)

        tab_toolbox.tab_action_item.setChecked(False)
        tab_toolbox.toolbox_action_item.setChecked(False)
        tab_toolbox.set_display_state(TabToolbox.DS_HIDDEN)

    @Slot(Qt.DockWidgetArea)
    def set_preferred_dock_area(
        self, area: Qt.DockWidgetArea, tab_toolbox: TabToolbox
    ) -> None:
        tab_toolbox.set_preferred_dock_area(area)

    # --- Event loop ---

    def _on_event_loop_ready(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._scan(self._connectivity_manager.get_address())

    # --- Commander pipeline ---

    async def _safe_send(
        self, coro_fn: Callable[[], Coroutine[Any, Any, None]]
    ) -> None:
        try:
            await coro_fn()
        except DisconnectedError:
            pass

    def _commander_future_cb(self, future: Future[None]) -> None:
        """Log unexpected exceptions from commander coroutines."""
        try:
            future.result()
        except DisconnectedError:
            pass
        except Exception:
            logger.error("Unhandled exception in commander coroutine", exc_info=True)

    def _send_setpoint(
        self, roll: float, pitch: float, yaw: float, thrust: float
    ) -> None:
        cf = self.cf
        if self._disable_input or cf is None or self._loop is None:
            return
        future = asyncio.run_coroutine_threadsafe(
            self._safe_send(
                lambda: cf.commander().send_setpoint_rpyt(roll, pitch, yaw, int(thrust))
            ),
            self._loop,
        )
        future.add_done_callback(self._commander_future_cb)

    def _send_velocity_world(
        self, vx: float, vy: float, vz: float, yawrate: float
    ) -> None:
        cf = self.cf
        if self._disable_input or cf is None or self._loop is None:
            return
        future = asyncio.run_coroutine_threadsafe(
            self._safe_send(
                lambda: cf.commander().send_setpoint_velocity_world(vx, vy, vz, yawrate)
            ),
            self._loop,
        )
        future.add_done_callback(self._commander_future_cb)

    def _send_zdistance(
        self, roll: float, pitch: float, yawrate: float, zdistance: float
    ) -> None:
        cf = self.cf
        if self._disable_input or cf is None or self._loop is None:
            return
        future = asyncio.run_coroutine_threadsafe(
            self._safe_send(
                lambda: cf.commander().send_setpoint_zdistance(
                    roll, pitch, yawrate, zdistance
                )
            ),
            self._loop,
        )
        future.add_done_callback(self._commander_future_cb)

    def _send_hover(
        self, vx: float, vy: float, yawrate: float, zdistance: float
    ) -> None:
        cf = self.cf
        if self._disable_input or cf is None or self._loop is None:
            return
        future = asyncio.run_coroutine_threadsafe(
            self._safe_send(
                lambda: cf.commander().send_setpoint_hover(vx, vy, yawrate, zdistance)
            ),
            self._loop,
        )
        future.add_done_callback(self._commander_future_cb)

    def disable_input(self, disable: bool) -> None:
        """Disable gamepad input to allow a tab to send setpoints directly."""
        self._disable_input = disable

    # --- Emergency stop ---

    def _emergency_stop(self) -> None:
        if self.cf is not None:
            create_task(self.cf.localization().emergency().send_emergency_stop())

    # --- Address ---

    def _set_address(self) -> None:
        address = 0xE7E7E7E7E7
        try:
            link_uri = Config().get("link_uri")
            if link_uri.startswith("radio://"):
                parts = link_uri.split("/")
                if len(parts) == 6:
                    address = int(parts[-1], 16)
        except KeyError:
            pass
        except ValueError as err:
            logger.warning("failed to parse address from config: %s", err)
        finally:
            self.address.setValue(address)

    # --- Scanning ---

    def _scan(self, address: int) -> None:
        create_task(self._async_scan(address))

    async def _async_scan(self, address: int) -> None:
        self.uiState = UIState.SCANNING
        self._update_ui_state()

        address_bytes = list(address.to_bytes(5, byteorder="big"))
        uris = await self._link_context.scan(address=address_bytes)
        interfaces = [(uri, "") for uri in uris]

        self._interfaces_found(interfaces)

    def _interfaces_found(self, interfaces: list[tuple[str, str]]) -> None:
        selected_interface = self._connectivity_manager.get_interface()

        formatted_interfaces = []
        for uri, description in interfaces:
            if description:
                formatted_interfaces.append(f"{uri} - {description}")
            else:
                formatted_interfaces.append(uri)

        if self._initial_scan:
            self._initial_scan = False
            try:
                saved_uri = Config().get("link_uri")
                if saved_uri and len(saved_uri) > 0:
                    formatted_interfaces.index(saved_uri)
                    selected_interface = saved_uri
            except (KeyError, ValueError):
                pass

        if len(interfaces) == 1 and selected_interface is None:
            selected_interface = interfaces[0][0]

        newIndex = None
        if selected_interface is not None:
            try:
                newIndex = formatted_interfaces.index(selected_interface)
            except ValueError:
                pass

        self._connectivity_manager.set_interfaces(formatted_interfaces, newIndex)
        self.uiState = UIState.DISCONNECTED
        self._update_ui_state()

    # --- Connect / Disconnect ---

    def _connect(self) -> None:
        if self.uiState == UIState.CONNECTED:
            create_task(self._async_disconnect())
        elif self.uiState == UIState.CONNECTING:
            if self._connect_task is not None:
                self._connect_task.cancel()
        else:
            uri = self._connectivity_manager.get_interface()
            if uri is None:
                return
            if " - " in uri:
                uri = uri.split(" - ")[0]
            self._connect_task = create_task(self._async_connect(uri))

    async def _async_connect(self, uri: str) -> None:
        self.uiState = UIState.CONNECTING
        self._update_ui_state()

        try:
            self.cf = await Crazyflie.connect_from_uri(
                self._link_context, uri, toc_cache=self._toc_cache
            )
            self.uiState = UIState.CONNECTED
            self._update_ui_state()
            self._notify_tabs_connected()
            self._disconnect_watch_task = create_task(self._watch_disconnect())
            Config().set("link_uri", uri)
            logger.info(f"Connected to {uri}")
        except asyncio.CancelledError:
            logger.info("Connection cancelled")
            self.uiState = UIState.DISCONNECTED
            self._update_ui_state()
        except DisconnectedError as e:
            logger.error(f"Connection failed: {e}")
            QMessageBox.critical(
                self, "Connection failed", f"Could not connect to Crazyflie:\n{e}"
            )
            self.uiState = UIState.DISCONNECTED
            self._update_ui_state()
        finally:
            self._connect_task = None

    async def _watch_disconnect(self) -> None:
        try:
            reason = await self.cf.wait_disconnect()
            uri = self.cf.uri
            logger.info(f"Connection lost: {reason}")
            self._notify_tabs_disconnected()
            self.cf = None
            self.uiState = UIState.DISCONNECTED
            self._update_ui_state()
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("Communication failure")
            msg.setText(f"Connection lost to {uri}: {reason}")
            msg.show()
        except asyncio.CancelledError:
            pass

    async def _async_disconnect(self) -> None:
        if self._disconnect_watch_task is not None:
            self._disconnect_watch_task.cancel()
            self._disconnect_watch_task = None
        if self.cf is not None:
            logger.info(f"Disconnected from {self.cf.uri}")
            self._notify_tabs_disconnected()
            await self.cf.disconnect()
            self.cf = None
        self.uiState = UIState.DISCONNECTED
        self._update_ui_state()

    def _notify_tabs_connected(self) -> None:
        self._pose_logger.start(self.cf)
        self._battery_task = create_task(self._stream_battery(self.cf))
        for tab_toolbox in self.loaded_tab_toolboxes.values():
            tab_toolbox.connected(self.cf)

    def _notify_tabs_disconnected(self) -> None:
        self._pose_logger.stop()
        if self._battery_task is not None:
            self._battery_task.cancel()
            self._battery_task = None
        for tab_toolbox in self.loaded_tab_toolboxes.values():
            tab_toolbox.disconnected()

    async def _stream_battery(self, cf: Crazyflie) -> None:
        log = cf.log()
        stream = None
        try:
            block = await log.create_block()
            await block.add_variable("pm.vbat")
            await block.add_variable("pm.state")
            stream = await block.start(1000)
            while True:
                data = await stream.next()
                self._battery_signal.emit(
                    data.data["pm.vbat"], int(data.data["pm.state"])
                )
        finally:
            if stream is not None:
                try:
                    await asyncio.shield(stream.stop())
                except (DisconnectedError, asyncio.CancelledError):
                    pass

    def _update_battery(self, vbat: float, state: int) -> None:
        self.batteryBar.setValue(int(vbat * 1000))

        color = UiUtils.COLOR_BLUE
        # TODO firmware reports fully-charged state as 'Battery',
        # rather than 'Charged'
        if state in [BatteryStates.CHARGING, BatteryStates.CHARGED]:
            color = UiUtils.COLOR_GREEN
        elif state == BatteryStates.LOW_POWER:
            color = UiUtils.COLOR_RED

        self.batteryBar.setStyleSheet(UiUtils.progressbar_stylesheet(color))
        self._aff_volts.setText("%.3f" % vbat)

    # --- UI state ---

    def _update_ui_state(self) -> None:
        if self.uiState == UIState.DISCONNECTED:
            self.setWindowTitle("Not connected")
            canConnect = self._connectivity_manager.get_interface() is not None
            self.menuItemConnect.setText("Connect to Crazyflie")
            self.menuItemConnect.setEnabled(canConnect)
            self._connectivity_manager.set_state(
                ConnectivityManager.UIState.DISCONNECTED
            )
            self.batteryBar.setValue(3000)
            # TODO: cflib2 does not expose link quality statistics
            self.linkQualityBar.setValue(0)
            self.esButton.setEnabled(False)
            self.esButton.setStyleSheet("")
        elif self.uiState == UIState.CONNECTED:
            s = "Connected on %s" % self._connectivity_manager.get_interface()
            self.setWindowTitle(s)
            self.menuItemConnect.setText("Disconnect")
            self.menuItemConnect.setEnabled(True)
            self._connectivity_manager.set_state(ConnectivityManager.UIState.CONNECTED)
            self.esButton.setEnabled(True)
            self.esButton.setStyleSheet("background-color: red")
        elif self.uiState == UIState.CONNECTING:
            s = "Connecting to {} ...".format(
                self._connectivity_manager.get_interface()
            )
            self.setWindowTitle(s)
            self.menuItemConnect.setText("Cancel")
            self.menuItemConnect.setEnabled(True)
            self._connectivity_manager.set_state(ConnectivityManager.UIState.CONNECTING)
        elif self.uiState == UIState.SCANNING:
            self.setWindowTitle("Scanning ...")
            self.menuItemConnect.setEnabled(False)
            self._connectivity_manager.set_state(ConnectivityManager.UIState.SCANNING)

    # --- Theme ---

    def _theme_selected(self, *args: object) -> None:
        for checkbox in self._theme_checkboxes:
            if checkbox.isChecked():
                theme = checkbox.objectName()
                app = QtWidgets.QApplication.instance()
                app.setStyleSheet(UiUtils.select_theme(theme))
                Config().set("theme", theme)

    def _check_theme(self, theme_name: str) -> None:
        for theme in self._theme_checkboxes:
            if theme.objectName() == theme_name:
                theme.setChecked(True)
                self._theme_selected(True)

    def set_default_theme(self) -> None:
        try:
            theme = Config().get("theme")
        except KeyError:
            theme = "Default"
        self._check_theme(theme)

    # --- Input device menu ---

    def _show_input_device_config_dialog(self) -> None:
        self.inputConfig = InputConfigDialogue(self._joystick_reader)
        self.inputConfig.show()

    def _display_input_device_error(self, error: str) -> None:
        if self.cf is not None:
            create_task(self._async_disconnect())
        QMessageBox.critical(self, "Input device error", error)

    def _mux_selected(self, checked: bool) -> None:
        if not checked:
            (mux, sub_nodes) = self.sender().data()
            for s in sub_nodes:
                s.setEnabled(False)
        else:
            (mux, sub_nodes) = self.sender().data()
            for s in sub_nodes:
                s.setEnabled(True)
            self._joystick_reader.set_mux(mux=mux)

            # Go though the tree and select devices/mapping that was
            # selected before it was disabled.
            for role_node in sub_nodes:
                for dev_node in role_node.children():
                    if type(dev_node) is QAction and dev_node.isChecked():
                        dev_node.toggled.emit(True)

            self._update_input_device_footer()

    def _get_dev_status(self, device: InputReaderInterface) -> str:
        msg = "{}".format(device.name)
        if device.supports_mapping:
            map_name = "No input mapping"
            if device.input_map:
                map_name = device.input_map_name
            msg += " ({})".format(map_name)
        return msg

    def _update_input_device_footer(self) -> None:
        msg = ""

        if len(self._joystick_reader.available_devices()) > 0:
            mux = self._joystick_reader._selected_mux
            msg = "Using {} mux with ".format(mux.name)
            for key in list(mux._devs.keys())[:-1]:
                if mux._devs[key]:
                    msg += "{}, ".format(self._get_dev_status(mux._devs[key]))
                else:
                    msg += "N/A, "
            key = list(mux._devs.keys())[-1]
            if mux._devs[key]:
                msg += "{}".format(self._get_dev_status(mux._devs[key]))
            else:
                msg += "N/A"
        else:
            msg = "No input device found"
        self._statusbar_label.setText(msg)

    def _inputdevice_selected(self, checked: bool) -> None:
        (map_menu, device, mux_menu) = self.sender().data()
        if not checked:
            if map_menu:
                map_menu.setEnabled(False)
        else:
            if map_menu:
                map_menu.setEnabled(True)

            (mux, sub_nodes) = mux_menu.data()
            for role_node in sub_nodes:
                for dev_node in role_node.children():
                    if type(dev_node) is QAction and dev_node.isChecked():
                        if (
                            device.id == dev_node.data()[1].id
                            and dev_node is not self.sender()
                        ):
                            dev_node.setChecked(False)

            role_in_mux = str(self.sender().parent().title()).strip()
            logger.info("Role of {} is {}".format(device.name, role_in_mux))

            Config().set("input_device", str(device.name))

            self._mapping_support = self._joystick_reader.start_input(
                device.name, role_in_mux
            )
        self._update_input_device_footer()

    def _inputconfig_selected(self, checked: bool) -> None:
        if not checked:
            return

        selected_mapping = str(self.sender().text())
        device = self.sender().data().data()[1]
        self._joystick_reader.set_input_map(device.name, selected_mapping)
        self._update_input_device_footer()

    def device_discovery(self, devs: list[InputReaderInterface]) -> None:
        """Called when new devices have been added"""
        for menu in self._all_role_menus:
            role_menu = menu["rolemenu"]
            mux_menu = menu["muxmenu"]
            dev_group = QActionGroup(role_menu)
            dev_group.setExclusive(True)
            for d in devs:
                dev_node = QAction(d.name, role_menu, checkable=True, enabled=True)
                role_menu.addAction(dev_node)
                dev_group.addAction(dev_node)
                dev_node.toggled.connect(self._inputdevice_selected)

                map_node = None
                if d.supports_mapping:
                    map_node = QMenu("    Input map", role_menu, enabled=False)
                    map_group = QActionGroup(role_menu)
                    map_group.setExclusive(True)
                    dev_node.setData((map_node, d))
                    for c in ConfigManager().get_list_of_configs():
                        node = QAction(c, map_node, checkable=True, enabled=True)
                        node.toggled.connect(self._inputconfig_selected)
                        map_node.addAction(node)
                        node.setData(dev_node)
                        map_group.addAction(node)
                        if d not in self._available_devices:
                            last_map = Config().get("device_config_mapping")
                            if d.name in last_map and last_map[d.name] == c:
                                node.setChecked(True)
                    role_menu.addMenu(map_node)
                dev_node.setData((map_node, d, mux_menu))

        # Update the list of what devices we found
        self._available_devices = ()
        for d in devs:
            self._available_devices += (d,)

        # Only enable MUX nodes if we have enough devices to cover
        # the roles
        for mux_node in self._all_mux_nodes:
            (mux, sub_nodes) = mux_node.data()
            if len(mux.supported_roles()) <= len(self._available_devices):
                mux_node.setEnabled(True)

        # Select default mux
        if self._all_mux_nodes[0].isEnabled():
            self._all_mux_nodes[0].setChecked(True)

        # Select previously used device or first available
        if Config().get("input_device") in [d.name for d in devs]:
            for dev_menu in self._all_role_menus[0]["rolemenu"].actions():
                if dev_menu.text() == Config().get("input_device"):
                    dev_menu.setChecked(True)
        else:
            self._all_role_menus[0]["rolemenu"].actions()[0].setChecked(True)
            logger.info("Select first device")

        self._update_input_device_footer()

    # --- Window events ---

    def closeEvent(self, event: QCloseEvent) -> None:
        Config().save_file()
        if self.cf is not None:
            create_task(self._async_disconnect())
        self.hide()

    def resizeEvent(self, event: QResizeEvent) -> None:
        Config().set("window_size", [event.size().width(), event.size().height()])

    # --- Misc ---

    def _open_config_folder(self) -> None:
        QDesktopServices.openUrl(
            QUrl("file:///" + QDir.toNativeSeparators(cfclient.config_path))
        )

    def closeAppRequest(self) -> None:
        self.close()
        sys.exit(0)
