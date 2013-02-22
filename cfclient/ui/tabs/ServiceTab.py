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
The service tab is used to update the Crazyflie firmware and to read/write the
configuration block in the Crazyflie flash.
"""

__author__ = 'Bitcraze AB'
__all__ = ['ServiceTab']

import sys, time, struct

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import Qt, pyqtSlot, pyqtSignal, QThread, SIGNAL

from ui.tab import Tab

import cflib.crtp

from cflib.bootloader.cloader import Cloader

service_tab_class = uic.loadUiType("ui/tabs/serviceTab.ui")[0]

class UIState:
    DISCONNECTED    = 0
    CONNECTING      = 5
    CONNECT_FAILED  = 1
    COLD_CONNECT    = 2
    FLASHING        = 3
    RESET           = 4

class ServiceTab(Tab, service_tab_class):
    """Tab for update the Crazyflie firmware and for reading/writing the config block in flash"""
    def __init__(self, tabWidget, helper, *args):
        super(ServiceTab, self).__init__(*args)
        self.setupUi(self)
        
        self.tabName = "Service"
        self.menuName = "Service"

        self.tabWidget = tabWidget
        self.helper = helper
        
        #self.cf = crazyflie
        self.clt = CrazyloadThread()
        
        #Connecting GUI signals (a pity to do that manually...)
        self.imagePathBrowseButton.clicked.connect(self.pathBrowse)
        self.programButton.clicked.connect(self.programAction)
        self.verifyButton.clicked.connect(self.verifyAction)
        self.coldBootButton.clicked.connect(self.initiateColdboot)
        self.resetButton.clicked.connect(self.resetCopter)
        self.saveConfigblock.clicked.connect(self.writeConfig)        

        #connecting other signals
        self.clt.programmed.connect(self.programDone)
        self.clt.verified.connect(self.verifyDone)
        self.clt.statusChanged.connect(self.statusUpdate)
        #self.clt.updateBootloaderStatusSignal.connect(self.updateBootloaderStatus)        
        self.clt.connectingSignal.connect(lambda: self.setUiState(UIState.CONNECTING))
        self.clt.connectedSignal.connect(lambda: self.setUiState(UIState.COLD_CONNECT))
        self.clt.connectionFailedSignal.connect(lambda: self.setUiState(UIState.CONNECT_FAILED))
        self.clt.disconnectedSignal.connect(lambda: self.setUiState(UIState.DISCONNECTED))
        self.clt.updateConfigSignal.connect(self.updateConfig)
        self.clt.updateCpuIdSignal.connect(lambda cpuid: self.copterId.setText(cpuid))

        self.clt.start()

    def setUiState(self, state):
        if (state == UIState.DISCONNECTED):
            self.resetButton.setEnabled(False)
            self.programButton.setEnabled(False)
            self.setStatusLabel("Disconnected")
            self.coldBootButton.setEnabled(True)
        elif (state == UIState.CONNECTING):
            self.resetButton.setEnabled(False)
            self.programButton.setEnabled(False)
            self.setStatusLabel("Trying to connect cold bootloader, restart the Crazyflie to connect")
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
        self.rollTrim.setText(rollTrim)
        self.pitchTrim.setText(pitchTrim)
        self.radioChannel.setValue(int(channel))
        self.radioSpeed.setCurrentIndex(int(speed))

    @pyqtSlot()
    def pathBrowse(self):
        filename = QtGui.QFileDialog.getOpenFileName()
        if filename != "":
            self.imagePathLine.setText(filename)
        pass
       
    @pyqtSlot()
    def programAction(self):
        #self.setStatusLabel("Initiate programming")
        self.resetButton.setEnabled(False)
        if self.imagePathLine.text() != "":
            self.clt.program.emit(self.imagePathLine.text(), self.verifyCheckBox.isChecked())
        else:
            msgBox = QtGui.QMessageBox()
            msgBox.setText("Please choose an image file to program.");
            
            msgBox.exec_();

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
        self.statusLabel.setText('Status: <b>' + status + '</b>')
        if progress>0:
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
        pitchTrim = float(self.pitchTrim.text())
        rollTrim = float(self.rollTrim.text())
        channel = int(self.radioChannel.value())
        speed = self.radioSpeed.currentIndex()

        self.clt.writeConfigSignal.emit(channel, speed, rollTrim, pitchTrim)

#No run method specified here as the default run implementation is running the
#event loop which is what we want
class CrazyloadThread(QThread):
    #Input signals declaration (not sure it should be used like that...)
    program = pyqtSignal(str, bool)
    verify = pyqtSignal()
    initiateColdBootSignal = pyqtSignal(str)    
    resetCopterSignal = pyqtSignal()
    writeConfigSignal = pyqtSignal(int,int,float,float)
    #Output signals declaration
    programmed = pyqtSignal()
    verified = pyqtSignal()
    statusChanged = pyqtSignal(str, int)
    connectedSignal = pyqtSignal()
    connectingSignal = pyqtSignal()
    connectionFailedSignal = pyqtSignal()
    disconnectedSignal = pyqtSignal()
    updateConfigSignal = pyqtSignal(str, str, str, str)
    updateCpuIdSignal = pyqtSignal(str)

    radioSpeedPos = 2
  
    def __init__(self):
        super(CrazyloadThread, self).__init__()
        
        #Make sure that the signals are handled by this thread event loop
        self.moveToThread(self);
        
        self.program.connect(self.programAction)
        self.writeConfigSignal.connect(self.writeConfigAction)
        self.initiateColdBootSignal.connect(self.initiateColdBoot)
        self.resetCopterSignal.connect(self.resetCopter)
        self.loader = None

    def __del__(self):
        self.quit()
        self.wait()

    def initiateColdBoot(self, linkURI):
        self.connectingSignal.emit()
        self.link = cflib.crtp.getDriver("radio://0/110")
        self.loader = Cloader(self.link, "radio://0/110")
        #self.link = CRTP.getDriver("debug://0/110")
        #self.loader = Cloader(self.link, "debug://0/110")

        if self.loader.coldBoot():
            print "Connected in cold boot mode"
            print "Flash pages: %d | Page size: %d | Buffer pages: %d | Start page: %d" % (self.loader.flashPages, self.loader.pageSize, self.loader.bufferPages, self.loader.startPage)
            print "%d KBytes of flash avaliable for firmware image." % ((self.loader.flashPages-self.loader.startPage)*self.loader.pageSize/1024)
            self.updateCpuIdSignal.emit(self.loader.cpuid)
            self.readConfigAction()
            self.connectedSignal.emit()
        else:
            self.connectionFailedSignal.emit()
            print "No connection"
            self.link.close()

    def programAction(self, filename, verify):
        print "Flashing file [%s]" % filename
        f=open(filename, "rb")
        if not f:
            print "Cannot open image file", filename
            self.link.close()
            return
        image = f.read()
        f.close()
        
        self.loadAndFlash(image, verify)

    def checksum256(self, st):
        return reduce(lambda x,y:x+y, map(ord, st)) % 256        

    def writeConfigAction(self, channel, speed, rollTrim, pitchTrim):
        data = (0x00, channel, speed, pitchTrim, rollTrim)
        image = struct.pack("<BBBff", *data)
        #Adding some magic:
        image = "0xBC" + image
        image += struct.pack("B", 256-self.checksum256(image))

        self.loadAndFlash(image, True, 117)

    def readConfigAction(self):
        self.statusChanged.emit("Reading config block...", 0)
        data = self.loader.readFlashPage(self.loader.startPage + 117)
        self.statusChanged.emit("Reading config block...done!", 100)
        [channel, speed, pitchTrim, rollTrim] = struct.unpack("<BBff", data[5:15]) # Skip 0xBC and version at the beginning
        self.updateConfigSignal.emit(str(channel), str(speed), str(pitchTrim), str(rollTrim))

    def loadAndFlash(self, image, verify = False, startpage = 0):

        factor = ((100.0*self.loader.pageSize)/len(image))
        if (verify == True):
            factor /= 2
        progress = 0
        #For each page
        ctr=0  #Buffer counter
        for i in range(0, int((len(image)-1)/self.loader.pageSize)+1):
            #Load the buffer
            if ((i+1)*self.loader.pageSize)>len(image):
                self.loader.loadBuffer(ctr, 0, image[i*self.loader.pageSize:])
            else:
                self.loader.loadBuffer(ctr, 0, image[i*self.loader.pageSize:(i+1)*self.loader.pageSize])

            ctr += 1

            progress += factor
            self.statusChanged.emit("Uploading buffer...", int(progress))

            #Flash when the complete buffers are full
            if ctr>=self.loader.bufferPages:
                sys.stdout.flush()
                self.statusChanged.emit("Writing buffer...", int(progress))
                firstFlashPage = self.loader.startPage+startpage+i-(ctr-1)
                if not self.loader.flash(0, firstFlashPage, ctr):
                    self.disconnectedSignal.emit()
                    self.statusChanged.emit("Error during flash operation (err code %d)" % self.loader.getErrorCode(), int(progress)) 
                    self.link.close()
                    return
                if (verify == True):
                    for p in range(firstFlashPage, firstFlashPage+ctr):
                        test = self.loader.readFlashPage(p)
                        buffStart = ((p-self.loader.startPage)*self.loader.pageSize)
                        ver = image[buffStart:buffStart+self.loader.pageSize]
                        if (test != ver):
                            self.statusChanged.emit("Verification failed!", int(progress))
                            return
                        progress += factor
                        self.statusChanged.emit("Verifying flashed data...", int(progress))

                ctr = 0

        if ctr>0:
            sys.stdout.write("%d" % ctr)
            sys.stdout.flush()
            self.statusChanged.emit("Writing buffer...", int(progress))
            firstFlashPage = self.loader.startPage+startpage+(int((len(image)-1)/self.loader.pageSize))-(ctr-1)
            if not self.loader.flash(0, firstFlashPage, ctr):
                self.statusChanged.emit("Error during flash operation (err code %d)" % self.loader.getErrorCode(), int(progress)) 
                self.disconnectedSignal.emit() 
                self.link.close()
                return
            if (verify == True):
                for p in range(firstFlashPage, firstFlashPage+ctr):
                    buffStart = ((p-self.loader.startPage)*self.loader.pageSize)
                    ver = image[buffStart:buffStart+self.loader.pageSize]
                    test = self.loader.readFlashPage(p)[0:len(ver)] # We read back more than we should compare..
                    if (test != ver):
                        self.statusChanged.emit("Verification failed!", int(progress))
                        return
                    progress += factor
                    self.statusChanged.emit("Verifying flashed data...", int(progress))

        self.statusChanged.emit("Flashing...done!", 100)

    def resetCopter(self):
        self.disconnectedSignal.emit() 
        self.loader.resetFirmware(self.loader.decodeCpuId("32:00:6e:06:58:37:35:32:60:58:01:43"))
        self.link.close()

