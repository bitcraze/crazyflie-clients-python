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

#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
The bootloader dialog is used to update the Crazyflie firmware and to
read/write the configuration block in the Crazyflie flash.
"""

__author__ = 'Bitcraze AB'
__all__ = ['BootloaderDialog']

import struct
import sys
import time

import logging
logger = logging.getLogger(__name__)

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import Qt, pyqtSlot, pyqtSignal, QThread, SIGNAL

from cfclient.ui.tab import Tab

import cflib.crtp

from cflib.bootloader.cloader import Cloader
from cfclient.utils.guiconfig import GuiConfig

service_dialog_class = uic.loadUiType(sys.path[0] +
                                      "/cfclient/ui/dialogs/bootloader.ui")[0]


class UIState:
    DISCONNECTED = 0
    CONNECTING = 5
    CONNECT_FAILED = 1
    COLD_CONNECT = 2
    FLASHING = 3
    RESET = 4


class BootloaderDialog(QtGui.QWidget, service_dialog_class):
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
        self.saveConfigblock.clicked.connect(self.writeConfig)
        self._cancel_bootloading.clicked.connect(self.close)

        # connecting other signals
        self.clt.programmed.connect(self.programDone)
        self.clt.verified.connect(self.verifyDone)
        self.clt.statusChanged.connect(self.statusUpdate)
        # self.clt.updateBootloaderStatusSignal.connect(
        #                                         self.updateBootloaderStatus)
        self.clt.connectingSignal.connect(lambda:
                                          self.setUiState(UIState.CONNECTING))
        self.clt.connectedSignal.connect(lambda:
                                         self.setUiState(UIState.COLD_CONNECT))
        self.clt.failed_signal.connect(lambda m: self._ui_connection_fail(m))
        self.clt.disconnectedSignal.connect(lambda:
                                        self.setUiState(UIState.DISCONNECTED))
        self.clt.updateConfigSignal.connect(self.updateConfig)
        self.clt.updateCpuIdSignal.connect(lambda cpuid:
                                           self.copterId.setText(cpuid))

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
            self.saveConfigblock.setEnabled(False)
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
            self.saveConfigblock.setEnabled(True)
            self.programButton.setEnabled(True)
            self.setStatusLabel("Connected to bootloader")
            self.coldBootButton.setEnabled(False)
        elif (state == UIState.RESET):
            self.setStatusLabel("Resetting to firmware, disconnected")
            self.resetButton.setEnabled(False)
            self.programButton.setEnabled(False)
            self.coldBootButton.setEnabled(False)
            self.rollTrim.setValue(0)
            self.pitchTrim.setValue(0)
            self.radioChannel.setValue(0)
            self.radioSpeed.setCurrentIndex(0)
            self.imagePathLine.setText("")
            self.copterId.setText("")

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
        filename = QtGui.QFileDialog.getOpenFileName()
        if filename != "":
            self.imagePathLine.setText(filename)
        pass

    @pyqtSlot()
    def programAction(self):
        # self.setStatusLabel("Initiate programming")
        self.resetButton.setEnabled(False)
        if self.imagePathLine.text() != "":
            self.clt.program.emit(self.imagePathLine.text(),
                                  self.verifyCheckBox.isChecked())
        else:
            msgBox = QtGui.QMessageBox()
            msgBox.setText("Please choose an image file to program.")

            msgBox.exec_()

    @pyqtSlot()
    def verifyAction(self):
        self.statusLabel.setText('Status: <b>Initiate verification</b>')
        pass

    @pyqtSlot()
    def programDone(self):
        self.statusLabel.setText('Status: <b>Programing complete</b>')
        pass

    @pyqtSlot()
    def verifyDone(self):
        self.statusLabel.setText('Status: <b>Verification complete</b>')
        pass

    @pyqtSlot(str, int)
    def statusUpdate(self, status, progress):
        logger.debug("Status: [%s] | %d", status, progress)
        self.statusLabel.setText('Status: <b>' + status + '</b>')
        if progress >= 0:
            self.progressBar.setTextVisible(True)
            self.progressBar.setValue(progress)
        else:
            self.progressBar.setTextVisible(False)
            self.progressBar.setValue(100)
        if (progress == 100):
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
    program = pyqtSignal(str, bool)
    verify = pyqtSignal()
    initiateColdBootSignal = pyqtSignal(str)
    resetCopterSignal = pyqtSignal()
    writeConfigSignal = pyqtSignal(int, int, float, float)
    # Output signals declaration
    programmed = pyqtSignal()
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

        # Make sure that the signals are handled by this thread event loop
        self.moveToThread(self)

        self.program.connect(self.programAction)
        self.writeConfigSignal.connect(self.writeConfigAction)
        self.initiateColdBootSignal.connect(self.initiateColdBoot)
        self.resetCopterSignal.connect(self.resetCopter)
        self.loader = None
        self.link = None

    def __del__(self):
        self.quit()
        self.wait()

    def initiateColdBoot(self, linkURI):
        self.connectingSignal.emit()
        try:
            self.link = cflib.crtp.get_link_driver("radio://0/110")
        except Exception as e:
            self.failed_signal.emit(str(e))

        if (self.link):
            self.loader = Cloader(self.link, "radio://0/110")

            if self.loader.coldboot():
                logger.info("Connected in coldboot mode ok")
                self.updateCpuIdSignal.emit(self.loader.cpuid)
                self.readConfigAction()
                self.connectedSignal.emit()
            else:
                self.failed_signal.emit("Connection timeout")
                logger.info("Connected in coldboot mode failed")
                self.link.close()

    def programAction(self, filename, verify):
        logger.info("Flashing file [%s]", filename)
        f = open(filename, "rb")
        if not f:
            logger.warning("Cannot open file [%s]", filename)
            self.link.close()
            return
        image = f.read()
        f.close()

        self.loadAndFlash(image, verify)

    def checksum256(self, st):
        return reduce(lambda x, y: x + y, map(ord, st)) % 256

    def writeConfigAction(self, channel, speed, rollTrim, pitchTrim):
        data = (0x00, channel, speed, pitchTrim, rollTrim)
        image = struct.pack("<BBBff", *data)
        # Adding some magic:
        image = "0xBC" + image
        image += struct.pack("B", 256 - self.checksum256(image))

        self.loadAndFlash(image, True, 117)

    def readConfigAction(self):
        self.statusChanged.emit("Reading config block...", 0)
        data = self.loader.read_flash(self.loader.start_page + 117)
        if (data is not None):
            self.statusChanged.emit("Reading config block...done!", 100)
            if data[0:4] == "0xBC":
                # Skip 0xBC and version at the beginning
                [channel,
                 speed,
                 pitchTrim,
                 rollTrim] = struct.unpack("<BBff", data[5:15])
            else:
                channel = GuiConfig().get("default_cf_channel")
                speed = GuiConfig().get("default_cf_speed")
                pitchTrim = GuiConfig().get("default_cf_trim")
                rollTrim = GuiConfig().get("default_cf_trim")
            self.updateConfigSignal.emit(channel, speed, pitchTrim, rollTrim)
        else:
            self.statusChanged.emit("Reading config block failed!", 0)

    def loadAndFlash(self, image, verify=False, startpage=0):

        factor = ((100.0 * self.loader.page_size) / len(image))
        if (verify == True):
            factor /= 2
        progress = 0
        # For each page
        ctr = 0  # Buffer counter
        for i in range(0, int((len(image) - 1) / self.loader.page_size) + 1):
            # Load the buffer
            if ((i + 1) * self.loader.page_size) > len(image):
                self.loader.upload_buffer(ctr, 0,
                                          image[i * self.loader.page_size:])
            else:
                self.loader.upload_buffer(ctr, 0,
                                          image[i *
                                                self.loader.page_size:(i + 1) *
                                                self.loader.page_size])

            ctr += 1

            progress += factor
            self.statusChanged.emit("Uploading buffer...", int(progress))

            # Flash when the complete buffers are full
            if ctr >= self.loader.buffer_pages:
                self.statusChanged.emit("Writing buffer...", int(progress))
                firstFlashPage = (self.loader.start_page + startpage + i -
                                  (ctr - 1))
                if not self.loader.write_flash(0, firstFlashPage, ctr):
                    self.disconnectedSignal.emit()
                    self.statusChanged.emit("Error during flash operation "
                                            "(err code %d)" %
                                            self.loader.error_code,
                                            int(progress))
                    self.link.close()
                    return
                if (verify == True):
                    for p in range(firstFlashPage, firstFlashPage + ctr):
                        test = self.loader.read_flash(p)
                        buffStart = ((p - self.loader.start_page) *
                                     self.loader.page_size)
                        ver = image[buffStart:buffStart +
                                    self.loader.page_size]
                        if (test != ver):
                            self.statusChanged.emit("Verification failed!",
                                                    int(progress))
                            return
                        progress += factor
                        self.statusChanged.emit("Verifying flashed data...",
                                                int(progress))

                ctr = 0

        if ctr > 0:
            self.statusChanged.emit("Writing buffer...", int(progress))
            firstFlashPage = (self.loader.start_page + startpage +
                              (int((len(image) - 1) / self.loader.page_size)) -
                              (ctr - 1))
            if not self.loader.write_flash(0, firstFlashPage, ctr):
                self.statusChanged.emit("Error during flash operation "
                                        "(err code %d)" %
                                        self.loader.error_code,
                                        int(progress))
                self.disconnectedSignal.emit()
                self.link.close()
                return
            if (verify == True):
                for p in range(firstFlashPage, firstFlashPage + ctr):
                    buffStart = ((p - self.loader.start_page) *
                                 self.loader.page_size)
                    ver = image[buffStart:buffStart + self.loader.page_size]
                    # We read back more than we should compare.
                    test = self.loader.read_flash(p)[0:len(ver)]
                    if (test != ver):
                        self.statusChanged.emit("Verification failed!",
                                                int(progress))
                        return
                    progress += factor
                    self.statusChanged.emit("Verifying flashed data...",
                                            int(progress))

        self.statusChanged.emit("Flashing...done!", 100)

    def resetCopter(self):
        self.disconnectedSignal.emit()
        if self.loader:
            self.loader.reset_to_firmware(self.loader.decode_cpu_id(
                                        "32:00:6e:06:58:37:35:32:60:58:01:43"))
        if self.link:
            self.link.close()
