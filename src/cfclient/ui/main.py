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
#
#  You should have received a copy of the GNU General Public License along with
#  this program; if not, write to the Free Software Foundation, Inc., 51
#  Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""
Main window module for the Crazyflie Python client.

This module provides the main application window (MainUI) and supporting
classes for scanning and connecting to Crazyflie drones:

- UIState: Enum-like class defining connection states (DISCONNECTED, CONNECTING,
  CONNECTED, SCANNING)
- ScannerThread: QThread that scans for available Crazyflie interfaces without
  blocking the UI
- ConnectThread: QThread that handles Crazyflie connection in the background
- MainUI: The main QMainWindow subclass that orchestrates the UI, scanning,
  and connection logic

The UI is loaded dynamically from main.ui using PyQt6's uic module.
"""
import logging
import sys

import cfclient
from pathlib import Path

from cflib import Crazyflie, FileTocCache, LinkContext
from cfclient.ui.connectivity_manager import ConnectivityManager
from cfclient.utils.config import Config
from cfclient.utils.ui import UiUtils

from PyQt6 import QtWidgets, uic
from PyQt6.QtCore import pyqtSignal, QThread
from PyQt6.QtGui import QCloseEvent, QShortcut

__author__ = 'Bitcraze AB'
__all__ = ['MainUI']

logger = logging.getLogger(__name__)

# Dynamically load UI class from .ui file - Pylance can't infer types from this
(main_window_class,
 main_windows_base_class) = uic.loadUiType(cfclient.module_path + '/ui/main.ui')  # type: ignore[arg-type]


class UIState:
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    SCANNING = 3


class ScannerThread(QThread):
    """Thread for scanning interfaces without blocking the UI."""

    interfaceFoundSignal = pyqtSignal(object)

    def __init__(self):
        QThread.__init__(self)
        self._link_context = LinkContext()
        self._address = None
        self._should_scan = False

    def scan(self, address):
        """Request a scan with the given address."""
        self._address = address
        self._should_scan = True
        if not self.isRunning():
            self.start()

    def run(self):
        while self._should_scan:
            self._should_scan = False
            assert self._address is not None, "scan() must be called before run()"
            address_bytes = list(self._address.to_bytes(5, byteorder='big'))
            uris = self._link_context.scan(address=address_bytes)
            # Convert to list of tuples (uri, description) for compatibility
            interfaces = [(uri, "") for uri in uris]
            self.interfaceFoundSignal.emit(interfaces)


class ConnectThread(QThread):
    """Thread for connecting to Crazyflie without blocking the UI."""

    connectionDone = pyqtSignal(object)  # Emits the Crazyflie object
    connectionFailed = pyqtSignal(str)   # Emits error message

    def __init__(self):
        QThread.__init__(self)
        self._uri = None
        self._cf = None
        self._toc_cache = self._init_toc_cache()

    def _init_toc_cache(self):
        """Initialize TOC cache in user's cache directory."""
        cache_dir = Path.home() / ".cache" / "crazyflie" / "toc"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return FileTocCache(str(cache_dir))

    def connect(self, uri):
        """Request connection to the given URI."""
        self._uri = uri
        self.start()

    def run(self):
        try:
            assert self._uri is not None, "connect() must be called before run()"
            self._cf = Crazyflie.connect_from_uri(self._uri, toc_cache=self._toc_cache)
            self.connectionDone.emit(self._cf)
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.connectionFailed.emit(str(e))


class MainUI(QtWidgets.QMainWindow, main_window_class):  # type: ignore[misc]
    """Main window for the Crazyflie client.

    Note: UI elements (interfaceCombo, address, connectButton, etc.) are created
    dynamically by setupUi() from the .ui file, so Pylance can't see them.
    """

    def __init__(self, *args):
        super(MainUI, self).__init__(*args)
        self.setupUi(self)  # type: ignore[attr-defined] # Method from dynamically loaded UI class

        self.cf = None  # Will hold connected Crazyflie
        self.uiState = UIState.DISCONNECTED

        # Restore window size if present in config
        try:
            size = Config().get("window_size")
            self.resize(int(size[0]), int(size[1]))
        except KeyError:
            pass

        # Set up scanner thread
        self.scanner = ScannerThread()
        self.scanner.interfaceFoundSignal.connect(self._interfaces_found)

        # Set up connect thread
        self._connect_thread = ConnectThread()
        self._connect_thread.connectionDone.connect(self._connection_done)
        self._connect_thread.connectionFailed.connect(self._connection_failed)

        # Set up connectivity manager (handles UI state for connect/scan buttons)
        self._connectivity_manager = ConnectivityManager()
        self._connectivity_manager.register_ui_elements(
            ConnectivityManager.UiElementsContainer(
                interface_combo=self.interfaceCombo,  # type: ignore[attr-defined]
                address_spinner=self.address,  # type: ignore[attr-defined]
                connect_button=self.connectButton,  # type: ignore[attr-defined]
                scan_button=self.scanButton))  # type: ignore[attr-defined]

        self._connectivity_manager.connect_button_clicked.connect(self._connect_button_clicked)
        self._connectivity_manager.scan_button_clicked.connect(self._scan)

        # Keyboard shortcut
        self.connect_input = QShortcut(
            "Ctrl+I",
            self.connectButton,  # type: ignore[attr-defined]
            self._connect_button_clicked)

        # Menu actions
        self.menuItemConnect.triggered.connect(  # type: ignore[attr-defined]
            self._connect_button_clicked)
        self.menuItemExit.triggered.connect(self.closeAppRequest)  # type: ignore[attr-defined]

        # Set default address
        self._set_default_address()

        # Initial scan
        self._scan(self._connectivity_manager.get_address())

    def _set_default_address(self):
        """Set the default address from config or use E7E7E7E7E7."""
        try:
            address = Config().get("link_address")
        except KeyError:
            address = 0xE7E7E7E7E7
        self._connectivity_manager.set_address(address)

    def _scan(self, address):
        """Start scanning for Crazyflies."""
        self.uiState = UIState.SCANNING
        self._connectivity_manager.set_state(ConnectivityManager.UIState.SCANNING)
        self.scanner.scan(address)

    def _interfaces_found(self, interfaces):
        """Called when scan completes with found interfaces."""
        formatted_interfaces = []
        for uri, description in interfaces:
            if description:
                formatted_interfaces.append(f"{uri} - {description}")
            else:
                formatted_interfaces.append(uri)

        selected_index = None
        if len(interfaces) == 1:
            selected_index = 0

        self._connectivity_manager.set_interfaces(formatted_interfaces, selected_index)
        self.uiState = UIState.DISCONNECTED
        self._connectivity_manager.set_state(ConnectivityManager.UIState.DISCONNECTED)

    def _connect_button_clicked(self):
        """Handle connect/disconnect button click."""
        if self.uiState == UIState.CONNECTED:
            self._disconnect()
        elif self.uiState == UIState.DISCONNECTED:
            self._connect()
        elif self.uiState == UIState.CONNECTING:
            # Not supported: cflib's connect_from_uri is blocking and cannot be cancelled
            pass

    def _connect(self):
        """Connect to the selected Crazyflie."""
        uri = self._connectivity_manager.get_interface()
        if uri is None:
            return

        # Extract just the URI if it has a description
        if " - " in uri:
            uri = uri.split(" - ")[0]

        logger.info(f"Connecting to {uri}")
        self.uiState = UIState.CONNECTING
        self._connectivity_manager.set_state(ConnectivityManager.UIState.CONNECTING)
        self.setWindowTitle(f"Connecting to {uri}...")

        self._connect_thread.connect(uri)

    def _connection_done(self, cf):
        """Called when connection succeeds."""
        self.cf = cf
        self.uiState = UIState.CONNECTED
        self._connectivity_manager.set_state(ConnectivityManager.UIState.CONNECTED)

        uri = self._connectivity_manager.get_interface()
        self.setWindowTitle(f"Connected to {uri}")
        logger.info(f"Connected to {uri}")

    def _connection_failed(self, message):
        """Called when connection fails."""
        self.uiState = UIState.DISCONNECTED
        self._connectivity_manager.set_state(ConnectivityManager.UIState.DISCONNECTED)
        self.setWindowTitle("Connection failed")
        logger.error(f"Connection failed: {message}")

        QtWidgets.QMessageBox.critical(
            self, "Connection failed",
            f"Could not connect to Crazyflie:\n{message}")

    def _disconnect(self):
        """Disconnect from the Crazyflie."""
        if self.cf is not None:
            logger.info("Disconnecting...")
            self.cf.disconnect()
            self.cf = None

        self.uiState = UIState.DISCONNECTED
        self._connectivity_manager.set_state(ConnectivityManager.UIState.DISCONNECTED)
        self.setWindowTitle("Disconnected")

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        """Handle window close."""
        # Save window size
        Config().set("window_size", [self.width(), self.height()])

        # Disconnect if connected
        if self.cf is not None:
            self.cf.disconnect()

        if a0 is not None:
            a0.accept()

    def closeAppRequest(self):
        """Handle exit menu item."""
        self.close()
        sys.exit(0)

    def set_default_theme(self):
        """Apply the default theme from config."""
        try:
            theme = Config().get('theme')
        except KeyError:
            theme = 'Default'
        app = QtWidgets.QApplication.instance()
        if isinstance(app, QtWidgets.QApplication):
            app.setStyleSheet(UiUtils.select_theme(theme))
