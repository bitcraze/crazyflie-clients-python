#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2013 Bitcraze AB
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
The bootloader dialog is used to update the Crazyflie firmware and to
read/write the configuration block in the Crazyflie flash.
"""
import logging

import cfclient
from cflib.crazyflie.mem import MemoryElement

from PyQt5 import QtWidgets
from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal

__author__ = 'Bitcraze AB'
__all__ = ['Cf2ConfigDialog']

logger = logging.getLogger(__name__)

service_dialog_class = uic.loadUiType(cfclient.module_path +
                                      "/ui/dialogs/cf2config.ui")[0]


class Cf2ConfigDialog(QtWidgets.QWidget, service_dialog_class):
    """Tab for update the Crazyflie firmware and for reading/writing the config
    block in flash"""

    connected_signal = pyqtSignal(str)
    disconnected_signal = pyqtSignal(str)

    def __init__(self, helper, *args):
        super(Cf2ConfigDialog, self).__init__(*args)
        self.setupUi(self)

        self._cf = helper.cf

        self.disconnected_signal.connect(self._set_ui_disconnected)
        self.connected_signal.connect(self._set_ui_connected)
        self._cf.disconnected.add_callback(self.disconnected_signal.emit)
        self._cf.connected.add_callback(self.connected_signal.emit)

        self._exit_btn.clicked.connect(self.hide)
        self._write_data_btn.clicked.connect(self._write_data)

    def _write_done(self, mem, addr):
        self._cf.mem.get_mems(
            MemoryElement.TYPE_I2C)[0].update(self._data_updated)

    def _data_updated(self, mem):
        self._roll_trim.setValue(mem.elements["roll_trim"])
        self._pitch_trim.setValue(mem.elements["pitch_trim"])
        self._radio_channel.setValue(mem.elements["radio_channel"])
        self._radio_speed.setCurrentIndex(mem.elements["radio_speed"])
        if "radio_address" in mem.elements:
            self._radio_address.setValue(mem.elements["radio_address"])
        else:
            self._radio_address.setValue(int("0xE7E7E7E7E7", 0))
        self._radio_address.setEnabled(True)
        self._write_data_btn.setEnabled(True)

    def _set_ui_connected(self, link_uri):
        mems = self._cf.mem.get_mems(MemoryElement.TYPE_I2C)
        if len(mems) > 0:
            mems[0].update(self._data_updated)

    def _set_ui_disconnected(self, link_uri):
        self._write_data_btn.setEnabled(False)
        self._roll_trim.setValue(0)
        self._pitch_trim.setValue(0)
        self._radio_channel.setValue(0)
        self._radio_speed.setCurrentIndex(0)
        self._radio_address.setValue(0)
        self._radio_address.setEnabled(False)

    def _write_data(self):
        self._write_data_btn.setEnabled(False)
        mem = self._cf.mem.get_mems(MemoryElement.TYPE_I2C)[0]
        mem.elements["pitch_trim"] = self._pitch_trim.value()
        mem.elements["roll_trim"] = self._roll_trim.value()
        mem.elements["radio_channel"] = self._radio_channel.value()
        mem.elements["radio_speed"] = self._radio_speed.currentIndex()
        if "radio_address" in mem.elements:
            mem.elements["radio_address"] = self._radio_address.value()
        mem.write_data(self._write_done)
