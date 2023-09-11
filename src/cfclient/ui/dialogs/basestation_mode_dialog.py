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
#  You should have received a copy of the GNU General Public License along with
#  this program; if not, write to the Free Software Foundation, Inc.,
#  51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""
Toolbox used to interact with the Basestation to set it in a certain channel
"""

from PyQt6 import QtWidgets
from PyQt6 import uic
from PyQt6.QtCore import Qt

import io
import serial
from serial.tools.list_ports import comports
import cfclient
import time


__author__ = 'Bitcraze AB'
__all__ = ['LighthouseBsModeDialog']

(basestation_mode_widget_class, connect_widget_base_class) = uic.loadUiType(
    cfclient.module_path + "/ui/dialogs/basestation_mode_dialog.ui")


class LighthouseBsModeDialog(QtWidgets.QWidget, basestation_mode_widget_class):

    PID = 0x2500
    VID = 0x28de

    def __init__(self, helper, *args):
        super(LighthouseBsModeDialog, self).__init__(*args)

        self.setupUi(self)

        self.helper = helper

        self._set_basestation_button.pressed.connect(self._set_basestation_pressed)
        self._set_channel_spinbox.valueChanged.connect(self._set_channel_number)
        self._scan_basestation_button.pressed.connect(self._set_basestation_dev)

        self._channel = 1
        self._device = None

        self._basestation_port_display.setText('No basestation found!')

        self._basestation_port_display.setText(self._device)

    def _set_basestation_dev(self):
        self._device = self._find_basestation()
        if self._device is None:
            self._basestation_port_display.setText('No basestation found!')
            self._set_basestation_button.setEnabled(False)
            self._display_current_channel.setText('')
            self._display_current_id.setText('')
        else:
            self._basestation_port_display.setText(self._device)
            self._set_basestation_button.setEnabled(True)
            self._check_current_mode()
            self._check_current_id()

    def _check_current_mode(self):
        dev = self._device
        ser = serial.Serial(dev, timeout=0.4)
        sio = io.TextIOWrapper(io.BufferedRWPair(ser, ser))
        sio.write("\r\nmode \r\n")
        sio.flush()
        mode_confirm_lines = sio.readlines()
        for line in mode_confirm_lines:
            if line.startswith('Current mode: '):
                parts = line.split()
                confirm_mode = int(parts[2])
        if confirm_mode == 0:
            self._display_current_channel.setText('0 (not supported)')
        else:
            self._display_current_channel.setText(str(confirm_mode))
        ser.close()

    def _check_current_id(self):
        dev = self._device
        ser = serial.Serial(dev, timeout=0.4)
        sio = io.TextIOWrapper(io.BufferedRWPair(ser, ser))

        sio.write("\r\nid\r\n")
        sio.flush()
        id_lines = sio.readlines()

        uid = id_lines[3].split(': ')[1].strip()
        self._display_current_id.setText(str(uid))
        ser.close()

    def _set_basestation_pressed(self):
        self._set_basestation_button.setEnabled(False)
        dev = self._device
        ser = serial.Serial(dev, timeout=0.4)
        sio = io.TextIOWrapper(io.BufferedRWPair(ser, ser))
        sio.write("\r\nmode " + str(self._channel) + "\r\n")
        sio.flush()
        time.sleep(1)
        sio.write("\r\nparam save\r\n")
        sio.flush()
        time.sleep(1)
        sio.write("\r\nmode\r\n")
        sio.flush()
        mode_confirm_lines = sio.readlines()
        confirm_mode = None
        for line in mode_confirm_lines:
            if line.startswith('Current mode: '):
                parts = line.split()
                confirm_mode = int(parts[2])
        if confirm_mode is self._channel:
            self._basestation_mode_status.setText('Success !')
        else:
            self._basestation_mode_status.setText('Try again !')
        self._display_current_channel.setText(str(confirm_mode))
        self._set_basestation_button.setEnabled(True)
        ser.close()

    def _set_channel_number(self, value):
        self._channel = value

    def getName(self):
        return 'LH Basestation Setup'

    def getTabName(self):
        return 'LH Basestation Setup'

    def enable(self):
        return

    def disable(self):
        return

    def preferedDockArea(self):
        return Qt.DockWidgetArea.RightDockWidgetArea

    def _find_basestation(self):
        ports = comports()

        for port in ports:
            if port.vid == self.VID and port.pid == self.PID:
                return port.device

    def reset(self):
        self._channel = 1
        self._device = None
        self._set_basestation_button.setEnabled(False)
        self._basestation_port_display.setText('No basestation found!')
        self._display_current_channel.setText('')
        self._basestation_mode_status.setText('')
        self._set_channel_spinbox.setValue(self._channel)
        self._display_current_id.setText('')
