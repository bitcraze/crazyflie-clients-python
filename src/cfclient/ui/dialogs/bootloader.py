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
from cflib.bootloader import Bootloader

import logging

from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import pyqtSlot, pyqtSignal, QThread

import cfclient

__author__ = 'Bitcraze AB'
__all__ = ['BootloaderDialog']

logger = logging.getLogger(__name__)

service_dialog_class = uic.loadUiType(cfclient.module_path +
                                      "/ui/dialogs/bootloader.ui")[0]


class UIState:
    DISCONNECTED = 0
    CONNECTING = 5
    CONNECT_FAILED = 1
    COLD_CONNECT = 2
    FLASHING = 3
    RESET = 4


class BootloaderDialog(QtWidgets.QWidget, service_dialog_class):
    """Tab for update the Crazyflie firmware and for reading/writing the config
    block in flash"""

    def __init__(self, helper, *args):
        super(BootloaderDialog, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Service"
        self.menuName = "Service"

        # self.tabWidget = tabWidget
        self.helper = helper

        # self.cf = crazyflie
        self.clt = CrazyloadThread()

        # Connecting GUI signals (a pity to do that manually...)
        self.imagePathBrowseButton.clicked.connect(self.pathBrowse)
        self.programButton.clicked.connect(self.programAction)
        self.verifyButton.clicked.connect(self.verifyAction)
        self.coldBootButton.clicked.connect(self.initiateColdboot)
        self.resetButton.clicked.connect(self.resetCopter)
        self._cancel_bootloading.clicked.connect(self.close)

        # connecting other signals
        self.clt.programmed.connect(self.programDone)
        self.clt.verified.connect(self.verifyDone)
        self.clt.statusChanged.connect(self.statusUpdate)
        # self.clt.updateBootloaderStatusSignal.connect(
        #                                         self.updateBootloaderStatus)
        self.clt.connectingSignal.connect(
            lambda: self.setUiState(UIState.CONNECTING))
        self.clt.connectedSignal.connect(
            lambda: self.setUiState(UIState.COLD_CONNECT))
        self.clt.failed_signal.connect(lambda m: self._ui_connection_fail(m))
        self.clt.disconnectedSignal.connect(
            lambda: self.setUiState(UIState.DISCONNECTED))

        self.clt.start()

    def _ui_connection_fail(self, message):
        self.setStatusLabel(message)
        self.coldBootButton.setEnabled(True)

    def setUiState(self, state):
        if (state == UIState.DISCONNECTED):
            self.resetButton.setEnabled(False)
            self.programButton.setEnabled(False)
            self.setStatusLabel("Not connected")
            self.coldBootButton.setEnabled(True)
            self.progressBar.setTextVisible(False)
            self.progressBar.setValue(0)
            self.statusLabel.setText('Status: <b>IDLE</b>')
            self.imagePathLine.setText("")
        elif (state == UIState.CONNECTING):
            self.resetButton.setEnabled(False)
            self.programButton.setEnabled(False)
            self.setStatusLabel("Trying to connect cold bootloader, restart "
                                "the Crazyflie to connect")
            self.coldBootButton.setEnabled(False)
        elif (state == UIState.CONNECT_FAILED):
            self.setStatusLabel("Connecting to bootloader failed")
            self.coldBootButton.setEnabled(True)
        elif (state == UIState.COLD_CONNECT):
            self.resetButton.setEnabled(True)
            self.programButton.setEnabled(True)
            self.setStatusLabel("Connected to bootloader")
            self.coldBootButton.setEnabled(False)
        elif (state == UIState.RESET):
            self.setStatusLabel("Resetting to firmware, disconnected")
            self.resetButton.setEnabled(False)
            self.programButton.setEnabled(False)
            self.coldBootButton.setEnabled(False)
            self.imagePathLine.setText("")

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

    @pyqtSlot()
    def pathBrowse(self):
        filename = ""
        # Fix for crash in X on Ubuntu 14.04
        filename, _ = QtWidgets.QFileDialog.getOpenFileName()
        if filename != "":
            self.imagePathLine.setText(filename)
        pass

    @pyqtSlot()
    def programAction(self):
        # self.setStatusLabel("Initiate programming")
        self.resetButton.setEnabled(False)
        self.programButton.setEnabled(False)
        self.imagePathBrowseButton.setEnabled(False)
        if self.imagePathLine.text() != "":
            self.clt.program.emit(self.imagePathLine.text(),
                                  self.verifyCheckBox.isChecked())
        else:
            msgBox = QtWidgets.QMessageBox()
            msgBox.setText("Please choose an image file to program.")

            msgBox.exec_()

    @pyqtSlot()
    def verifyAction(self):
        self.statusLabel.setText('Status: <b>Initiate verification</b>')
        pass

    @pyqtSlot(bool)
    def programDone(self, success):
        if success:
            self.statusLabel.setText('Status: <b>Programing complete!</b>')
        else:
            self.statusLabel.setText('Status: <b>Programing failed!</b>')

        self.resetButton.setEnabled(True)
        self.programButton.setEnabled(True)
        self.imagePathBrowseButton.setEnabled(True)

    @pyqtSlot()
    def verifyDone(self):
        self.statusLabel.setText('Status: <b>Verification complete</b>')
        pass

    @pyqtSlot(str, int)
    def statusUpdate(self, status, progress):
        logger.debug("Status: [%s] | %d", status, progress)
        self.statusLabel.setText('Status: <b>' + status + '</b>')
        if progress >= 0:
            self.progressBar.setValue(progress)

    def initiateColdboot(self):
        self.clt.initiateColdBootSignal.emit("radio://0/100")


# No run method specified here as the default run implementation is running the
# event loop which is what we want
class CrazyloadThread(QThread):
    # Input signals declaration (not sure it should be used like that...)
    program = pyqtSignal(str, bool)
    verify = pyqtSignal()
    initiateColdBootSignal = pyqtSignal(str)
    resetCopterSignal = pyqtSignal()
    writeConfigSignal = pyqtSignal(int, int, float, float)
    # Output signals declaration
    programmed = pyqtSignal(bool)
    verified = pyqtSignal()
    statusChanged = pyqtSignal(str, int)
    connectedSignal = pyqtSignal()
    connectingSignal = pyqtSignal()
    failed_signal = pyqtSignal(str)
    disconnectedSignal = pyqtSignal()
    updateConfigSignal = pyqtSignal(int, int, float, float)
    updateCpuIdSignal = pyqtSignal(str)

    radioSpeedPos = 2

    def __init__(self):
        super(CrazyloadThread, self).__init__()

        self._bl = Bootloader()
        self._bl.progress_cb = self.statusChanged.emit

        # Make sure that the signals are handled by this thread event loop
        self.moveToThread(self)

        self.program.connect(self.programAction)
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
        except Exception as e:
            self.failed_signal.emit("{}".format(e))

    def programAction(self, filename, verify):
        targets = {}
        if str(filename).endswith("bin"):
            targets["stm32"] = ("fw",)
        try:
            self._bl.flash(str(filename), targets)
            self.programmed.emit(True)
        except Exception:
            self.programmed.emit(False)

    def resetCopter(self):
        try:
            self._bl.reset_to_firmware()
        except Exception:
            pass
        self._bl.close()
        self.disconnectedSignal.emit()
