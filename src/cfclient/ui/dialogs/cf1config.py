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

import struct
from cflib.bootloader import Bootloader

import logging

from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import pyqtSlot, pyqtSignal, QThread

import cfclient
from cfclient.utils.config import Config
from functools import reduce

__author__ = 'Bitcraze AB'
__all__ = ['Cf1ConfigDialog']

logger = logging.getLogger(__name__)

service_dialog_class = uic.loadUiType(cfclient.module_path +
                                      "/ui/dialogs/cf1config.ui")[0]


class UIState:
    DISCONNECTED = 0
    CONNECTING = 5
    CONNECT_FAILED = 1
    COLD_CONNECT = 2
    FLASHING = 3
    RESET = 4


class Cf1ConfigDialog(QtWidgets.QWidget, service_dialog_class):
    """Tab for update the Crazyflie firmware and for reading/writing the config
    block in flash"""

    def __init__(self, helper, *args):
        super(Cf1ConfigDialog, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "CF1 Config"
        self.menuName = "CF1 Config"

        # self.tabWidget = tabWidget
        self.helper = helper

        # self.cf = crazyflie
        self.clt = CrazyloadThread()

        # Connecting GUI signals (a pity to do that manually...)
        self.coldBootButton.clicked.connect(self.initiateColdboot)
        self.resetButton.clicked.connect(self.resetCopter)
        self.saveConfigblock.clicked.connect(self.writeConfig)
        self._cancel_bootloading.clicked.connect(self.close)

        self.clt.statusChanged.connect(self.statusUpdate)
        self.clt.connectingSignal.connect(
            lambda: self.setUiState(UIState.CONNECTING))
        self.clt.connectedSignal.connect(
            lambda: self.setUiState(UIState.COLD_CONNECT))
        self.clt.failed_signal.connect(lambda m: self._ui_connection_fail(m))
        self.clt.disconnectedSignal.connect(
            lambda: self.setUiState(UIState.DISCONNECTED))
        self.clt.updateConfigSignal.connect(self.updateConfig)

        self.clt.start()

    def _ui_connection_fail(self, message):
        self.setStatusLabel(message)
        self.coldBootButton.setEnabled(True)

    def setUiState(self, state):
        if (state == UIState.DISCONNECTED):
            self.resetButton.setEnabled(False)
            self.setStatusLabel("Not connected")
            self.coldBootButton.setEnabled(True)
            self.progressBar.setTextVisible(False)
            self.progressBar.setValue(0)
            self.statusLabel.setText('Status: <b>IDLE</b>')
            self.saveConfigblock.setEnabled(False)
        elif (state == UIState.CONNECTING):
            self.resetButton.setEnabled(False)
            self.setStatusLabel("Trying to connect cold bootloader, restart "
                                "the Crazyflie to connect")
            self.coldBootButton.setEnabled(False)
        elif (state == UIState.CONNECT_FAILED):
            self.setStatusLabel("Connecting to bootloader failed")
            self.coldBootButton.setEnabled(True)
        elif (state == UIState.COLD_CONNECT):
            self.resetButton.setEnabled(True)
            self.saveConfigblock.setEnabled(True)
            self.setStatusLabel("Connected to bootloader")
            self.coldBootButton.setEnabled(False)
        elif (state == UIState.RESET):
            self.setStatusLabel("Resetting to firmware, disconnected")
            self.resetButton.setEnabled(False)
            self.coldBootButton.setEnabled(False)
            self.rollTrim.setValue(0)
            self.pitchTrim.setValue(0)
            self.radioChannel.setValue(0)
            self.radioSpeed.setCurrentIndex(0)

    def setStatusLabel(self, text):
        self.connectionStatus.setText("Status: <b>%s</b>" % text)

    def connected(self):
        self.setUiState(UIState.COLD_CONNECT)

    def connectionFailed(self):
        self.setUiState(UIState.CONNECT_FAILED)

    def resetCopter(self):
        self.clt.resetCopterSignal.emit()
        self.setUiState(UIState.RESET)

    def updateConfig(self, channel, speed, rollTrim, pitchTrim):
        self.rollTrim.setValue(rollTrim)
        self.pitchTrim.setValue(pitchTrim)
        self.radioChannel.setValue(channel)
        self.radioSpeed.setCurrentIndex(speed)

    def closeEvent(self, event):
        self.setUiState(UIState.RESET)
        self.clt.resetCopterSignal.emit()

    @pyqtSlot(str, int)
    def statusUpdate(self, status, progress):
        logger.debug("Status: [%s] | %d", status, progress)
        self.statusLabel.setText('Status: <b>' + status + '</b>')
        if progress >= 0 and progress < 100:
            self.progressBar.setTextVisible(True)
            self.progressBar.setValue(progress)
        else:
            self.progressBar.setTextVisible(False)
            self.progressBar.setValue(100)
        if progress >= 100:
            self.resetButton.setEnabled(True)

    def initiateColdboot(self):
        self.clt.initiateColdBootSignal.emit("radio://0/100")

    def writeConfig(self):
        pitchTrim = self.pitchTrim.value()
        rollTrim = self.rollTrim.value()
        channel = self.radioChannel.value()
        speed = self.radioSpeed.currentIndex()

        self.clt.writeConfigSignal.emit(channel, speed, rollTrim, pitchTrim)


# No run method specified here as the default run implementation is running the
# event loop which is what we want
class CrazyloadThread(QThread):
    # Input signals declaration (not sure it should be used like that...)
    initiateColdBootSignal = pyqtSignal(str)
    resetCopterSignal = pyqtSignal()
    writeConfigSignal = pyqtSignal(int, int, float, float)
    # Output signals declaration
    statusChanged = pyqtSignal(str, int)
    connectedSignal = pyqtSignal()
    connectingSignal = pyqtSignal()
    failed_signal = pyqtSignal(str)
    disconnectedSignal = pyqtSignal()
    updateConfigSignal = pyqtSignal(int, int, float, float)

    def __init__(self):
        super(CrazyloadThread, self).__init__()

        # Make sure that the signals are handled by this thread event loop
        self.moveToThread(self)
        self._bl = Bootloader()
        self._bl.progress_cb = self.statusChanged.emit

        self.writeConfigSignal.connect(self.writeConfigAction)
        self.initiateColdBootSignal.connect(self.initiateColdBoot)
        self.resetCopterSignal.connect(self.resetCopter)

    def __del__(self):
        self.quit()
        self.wait()

    def initiateColdBoot(self, linkURI):
        self.connectingSignal.emit()

        try:
            success = self._bl.start_bootloader(warm_boot=False)
            if not success:
                self.failed_signal.emit("Could not connect to bootloader")
            else:
                self.connectedSignal.emit()
                self.readConfigAction()
        except Exception as e:
            self.failed_signal.emit("{}".format(e))

    def checksum256(self, st):
        return reduce(lambda x, y: x + y, list(st)) % 256

    def writeConfigAction(self, channel, speed, rollTrim, pitchTrim):
        data = (0x00, channel, speed, pitchTrim, rollTrim)
        image = struct.pack("<BBBff", *data)
        # Adding some magic:
        image = bytearray("0xBC".encode('ISO-8859-1')) + image
        image += struct.pack("B", 256 - self.checksum256(image))

        self._bl.write_cf1_config(image)

    def readConfigAction(self):
        self.statusChanged.emit("Reading config block...", 0)
        data = self._bl.read_cf1_config()
        if (data is not None):
            if data[0:4] == bytearray("0xBC".encode('ISO-8859-1')):
                # Skip 0xBC and version at the beginning
                [channel,
                 speed,
                 pitchTrim,
                 rollTrim] = struct.unpack("<BBff", data[5:15])
                self.statusChanged.emit("Reading config block...done!", 100)
            else:
                channel = Config().get("default_cf_channel")
                speed = Config().get("default_cf_speed")
                pitchTrim = Config().get("default_cf_trim")
                rollTrim = Config().get("default_cf_trim")
                self.statusChanged.emit(
                    "Could not find config block, showing defaults", 100)
            self.updateConfigSignal.emit(channel, speed, rollTrim, pitchTrim)
        else:
            self.statusChanged.emit("Reading config block failed!", 0)

    def resetCopter(self):
        try:
            self._bl.reset_to_firmware()
        except Exception:
            pass
        self._bl.close()
        self.disconnectedSignal.emit()
