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

import asyncio
import logging
import sys

import cfclient
from cfclient.gui import create_task
from cfclient.ui.tab_toolbox import TabToolbox
import cfclient.ui.tabs
from cfclient.ui.connectivity_manager import ConnectivityManager
from cfclient.utils.config import Config
from cfclient.utils.ui import UiUtils
from cflib2 import Crazyflie, DisconnectedError, LinkContext, FileTocCache
from PySide6 import QtWidgets
from PySide6.QtUiTools import loadUiType
from PySide6.QtCore import Slot
from PySide6.QtCore import QDir
from PySide6.QtCore import QUrl
from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtGui import QActionGroup
from PySide6.QtGui import QShortcut
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMenu
from PySide6.QtWidgets import QMessageBox

__author__ = "Bitcraze AB"
__all__ = ["MainUI"]

logger = logging.getLogger(__name__)

(main_window_class, main_windows_base_class) = loadUiType(
    cfclient.module_path + "/ui/main.ui"
)  # type: ignore[misc]


class UIState:
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    SCANNING = 3


class MainUI(QtWidgets.QMainWindow, main_window_class):
    def __init__(self, *args):
        super(MainUI, self).__init__(*args)
        self.setupUi(self)

        self.cf = None
        self.uiState = UIState.DISCONNECTED
        self._link_context = LinkContext()
        self._toc_cache = FileTocCache(cfclient.config_path + "/cache")
        self._connect_task = None
        self._disconnect_watch_task = None

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
        self.menuItemConfInputDevice.setEnabled(False)
        self.logConfigAction.setEnabled(False)
        self._menu_inputdevice.setEnabled(False)
        self.esButton.setEnabled(False)

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

        # pluginhelper for tabs
        cfclient.ui.pluginhelper.connectivity_manager = self._connectivity_manager
        cfclient.ui.pluginhelper.mainUI = self

        self._connectivity_manager.set_address(self.address.value())

        self._initial_scan = True
        QTimer.singleShot(
            0, lambda: self._scan(self._connectivity_manager.get_address())
        )

        # Tabs and toolboxes
        self.tabs_menu_item = QMenu("Tabs", self.menuView)
        self.menuView.addMenu(self.tabs_menu_item)

        self.toolboxes_menu_item = QMenu("Toolboxes", self.menuView)
        self.menuView.addMenu(self.toolboxes_menu_item)

        self.loaded_tab_toolboxes = self.create_tab_toolboxes(
            self.tabs_menu_item, self.toolboxes_menu_item, self.tab_widget
        )
        self.read_tab_toolbox_config(self.loaded_tab_toolboxes)

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

    def create_tab_toolboxes(self, tabs_menu_item, toolboxes_menu_item, tab_widget):
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

    def read_tab_toolbox_config(self, loaded_tab_toolboxes):
        for name in TabToolbox.read_open_tab_config():
            if name in loaded_tab_toolboxes.keys():
                self._tab_toolbox_show_as_tab(loaded_tab_toolboxes[name])

        for name in TabToolbox.read_open_toolbox_config():
            if name in loaded_tab_toolboxes.keys():
                self._tab_toolbox_show_as_toolbox(loaded_tab_toolboxes[name])

    def toggle_tab_visibility(self, checked, tab_toolbox):
        if checked:
            self._tab_toolbox_show_as_tab(tab_toolbox)
        else:
            self._tab_toolbox_hide(tab_toolbox)

    def toggle_toolbox_visibility(self, checked, tab_toolbox):
        if checked:
            self._tab_toolbox_show_as_toolbox(tab_toolbox)
        else:
            self._tab_toolbox_hide(tab_toolbox)

    def _tab_toolbox_show_as_tab(self, tab_toolbox):
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

    def _tab_toolbox_show_as_toolbox(self, tab_toolbox):
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

    def _tab_toolbox_hide(self, tab_toolbox):
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
    def set_preferred_dock_area(self, area, tab_toolbox):
        tab_toolbox.set_preferred_dock_area(area)

    # --- Address ---

    def _set_address(self):
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

    def _scan(self, address):
        create_task(self._async_scan(address))

    async def _async_scan(self, address):
        self.uiState = UIState.SCANNING
        self._update_ui_state()

        address_bytes = list(address.to_bytes(5, byteorder="big"))
        uris = await self._link_context.scan(address=address_bytes)
        interfaces = [(uri, "") for uri in uris]

        self._interfaces_found(interfaces)

    def _interfaces_found(self, interfaces):
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

    def _connect(self):
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

    async def _async_connect(self, uri):
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

    async def _watch_disconnect(self):
        try:
            reason = await self.cf.wait_disconnect()
            uri = self.cf.uri
            logger.info(f"Connection lost: {reason}")
            self._notify_tabs_disconnected()
            self.cf = None
            self.uiState = UIState.DISCONNECTED
            self._update_ui_state()
            QMessageBox.critical(
                self, "Communication failure", f"Connection lost to {uri}: {reason}"
            )
        except asyncio.CancelledError:
            pass

    async def _async_disconnect(self):
        if self._disconnect_watch_task is not None:
            self._disconnect_watch_task.cancel()
            self._disconnect_watch_task = None
        if self.cf is not None:
            self._notify_tabs_disconnected()
            await self.cf.disconnect()
            self.cf = None
        self.uiState = UIState.DISCONNECTED
        self._update_ui_state()

    def _notify_tabs_connected(self):
        for tab_toolbox in self.loaded_tab_toolboxes.values():
            tab_toolbox.connected(self.cf)

    def _notify_tabs_disconnected(self):
        for tab_toolbox in self.loaded_tab_toolboxes.values():
            tab_toolbox.disconnected()

    # --- UI state ---

    def _update_ui_state(self):
        if self.uiState == UIState.DISCONNECTED:
            self.setWindowTitle("Not connected")
            canConnect = self._connectivity_manager.get_interface() is not None
            self.menuItemConnect.setText("Connect to Crazyflie")
            self.menuItemConnect.setEnabled(canConnect)
            self._connectivity_manager.set_state(
                ConnectivityManager.UIState.DISCONNECTED
            )
            self.batteryBar.setValue(3000)
            self.linkQualityBar.setValue(0)
        elif self.uiState == UIState.CONNECTED:
            s = "Connected on %s" % self._connectivity_manager.get_interface()
            self.setWindowTitle(s)
            self.menuItemConnect.setText("Disconnect")
            self.menuItemConnect.setEnabled(True)
            self._connectivity_manager.set_state(ConnectivityManager.UIState.CONNECTED)
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

    def _theme_selected(self, *args):
        for checkbox in self._theme_checkboxes:
            if checkbox.isChecked():
                theme = checkbox.objectName()
                app = QtWidgets.QApplication.instance()
                app.setStyleSheet(UiUtils.select_theme(theme))
                Config().set("theme", theme)

    def _check_theme(self, theme_name):
        for theme in self._theme_checkboxes:
            if theme.objectName() == theme_name:
                theme.setChecked(True)
                self._theme_selected(True)

    def set_default_theme(self):
        try:
            theme = Config().get("theme")
        except KeyError:
            theme = "Default"
        self._check_theme(theme)

    # --- Window events ---

    def closeEvent(self, event):
        Config().save_file()
        if self.cf is not None:
            create_task(self._async_disconnect())
        self.hide()

    def resizeEvent(self, event):
        Config().set("window_size", [event.size().width(), event.size().height()])

    # --- Misc ---

    def _open_config_folder(self):
        QDesktopServices.openUrl(
            QUrl("file:///" + QDir.toNativeSeparators(cfclient.config_path))
        )

    def closeAppRequest(self):
        self.close()
        sys.exit(0)
