#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2021-2023 Bitcraze AB
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
from collections import namedtuple
from PyQt6.QtCore import pyqtSignal, QObject

__author__ = 'Bitcraze AB'
__all__ = ['ConnectivityManager']


class ConnectivityManager(QObject):
    UiElementsContainer = namedtuple('UiElementContainer', [
        'interface_combo',
        'address_spinner',
        'connect_button',
        'scan_button'])

    class UIState:
        DISCONNECTED = 0
        CONNECTING = 1
        CONNECTED = 2
        SCANNING = 3

    INTERFACE_PROMPT_TEXT = 'Select an interface'

    connect_button_clicked = pyqtSignal()
    scan_button_clicked = pyqtSignal(object)
    connection_state_changed = pyqtSignal(object)

    def __init__(self):
        QObject.__init__(self)
        self._ui_elements = []
        self._state = self.UIState.DISCONNECTED
        self._is_enabled = True

    def register_ui_elements(self, ui_elements):
        self._ui_elements.append(ui_elements)

        ui_elements.connect_button.clicked.connect(self._connect_button_click_handler)
        ui_elements.scan_button.clicked.connect(self._scan_button_click_handler)

        ui_elements.address_spinner.valueChanged.connect(self._address_changed_handler)
        ui_elements.address_spinner.editingFinished.connect(self._address_edited_handler)

        ui_elements.interface_combo.currentIndexChanged.connect(self._interface_combo_current_index_changed_handler)

    def set_state(self, state):
        if self._state != state:
            self._state = state
            self._update_ui()

            if self._state == self.UIState.DISCONNECTED:
                self.connection_state_changed.emit(self.UIState.DISCONNECTED)
            elif self._state == self.UIState.CONNECTED:
                self.connection_state_changed.emit(self.UIState.CONNECTED)
            elif self._state == self.UIState.CONNECTING:
                self.connection_state_changed.emit(self.UIState.CONNECTING)
            elif self._state == self.UIState.SCANNING:
                self.connection_state_changed.emit(self.UIState.SCANNING)

    def set_enable(self, enable):
        if self._is_enabled != enable:
            self._is_enabled = enable
            self._update_ui()

    def set_address(self, address):
        for ui_elements in self._ui_elements:
            ui_elements.address_spinner.setValue(address)

    def get_address(self):
        if len(self._ui_elements) > 0:
            return self._ui_elements[0].address_spinner.value()
        else:
            return 0

    def set_interfaces(self, interface_items, index):
        new_index = 0
        if index is not None:
            new_index = index + 1

        for ui_elements in self._ui_elements:
            combo = ui_elements.interface_combo

            combo.clear()
            combo.addItem(self.INTERFACE_PROMPT_TEXT)
            combo.addItems(interface_items)
            combo.setCurrentIndex(new_index)

    def get_interface(self):
        if len(self._ui_elements) > 0:
            interface = self._ui_elements[0].interface_combo.currentText()
            if interface == self.INTERFACE_PROMPT_TEXT:
                self._selected_interface = None
            else:
                return interface
        else:
            return None

    def _connect_button_click_handler(self):
        self.connect_button_clicked.emit()

    def _scan_button_click_handler(self):
        self.scan_button_clicked.emit(self.get_address())

    def _address_changed_handler(self, value):
        for ui_elements in self._ui_elements:
            if value != ui_elements.address_spinner.value():
                ui_elements.address_spinner.setValue(value)

    def _address_edited_handler(self):
        # Find out if one of the addresses has changed and what the new value is
        value = 0
        is_changed = False
        for ui_elements in self._ui_elements:
            if ui_elements.address_spinner.is_text_different_from_value():
                value = ui_elements.address_spinner.value()
                is_changed = True
                break

        # Set the new value
        if is_changed:
            for ui_elements in self._ui_elements:
                if value != ui_elements.address_spinner.value():
                    ui_elements.address_spinner.setValue(value)

    def _interface_combo_current_index_changed_handler(self, interface):
        interface_s = str(interface)
        can_connect = interface != self.INTERFACE_PROMPT_TEXT
        for ui_elements in self._ui_elements:
            combo = ui_elements.interface_combo
            if combo.currentText != interface_s:
                combo.setCurrentText(interface_s)
            ui_elements.connect_button.setEnabled(can_connect)

    def _update_ui(self):
        if self._is_enabled:
            if self._state == self.UIState.DISCONNECTED:
                can_connect = self.get_interface() is not None
                for ui_elements in self._ui_elements:
                    ui_elements.connect_button.setText("Connect")
                    ui_elements.connect_button.setToolTip("Connect to the Crazyflie on the selected interface (Ctrl+I)")
                    ui_elements.connect_button.setEnabled(can_connect)
                    ui_elements.scan_button.setText("Scan")
                    ui_elements.scan_button.setEnabled(True)
                    ui_elements.address_spinner.setEnabled(True)
                    ui_elements.interface_combo.setEnabled(True)
            elif self._state == self.UIState.CONNECTED:
                for ui_elements in self._ui_elements:
                    ui_elements.connect_button.setText("Disconnect")
                    ui_elements.connect_button.setToolTip("Disconnect from the Crazyflie (Ctrl+I)")
                    ui_elements.scan_button.setEnabled(False)
                    ui_elements.address_spinner.setEnabled(False)
                    ui_elements.interface_combo.setEnabled(False)
            elif self._state == self.UIState.CONNECTING:
                for ui_elements in self._ui_elements:
                    ui_elements.connect_button.setText("Cancel")
                    ui_elements.connect_button.setToolTip("Cancel connecting to the Crazyflie")
                    ui_elements.scan_button.setEnabled(False)
                    ui_elements.address_spinner.setEnabled(False)
                    ui_elements.interface_combo.setEnabled(False)
            elif self._state == self.UIState.SCANNING:
                for ui_elements in self._ui_elements:
                    ui_elements.connect_button.setText("Connect")
                    ui_elements.connect_button.setEnabled(False)
                    ui_elements.scan_button.setText("Scanning...")
                    ui_elements.scan_button.setEnabled(False)
                    ui_elements.address_spinner.setEnabled(False)
                    ui_elements.interface_combo.setEnabled(False)
        else:
            for ui_elements in self._ui_elements:
                ui_elements.connect_button.setEnabled(False)
                ui_elements.scan_button.setEnabled(False)
                ui_elements.address_spinner.setEnabled(False)
                ui_elements.interface_combo.setEnabled(False)
