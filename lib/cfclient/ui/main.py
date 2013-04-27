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
The main file for the Crazyflie control application.
"""

__author__ = 'Bitcraze AB'
__all__ = ['MainUI']

import sys
import os
import logging

logger = logging.getLogger(__name__)

from PyQt4 import Qt, QtCore, QtGui, uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qt import *

from dialogs.connectiondialogue import ConnectDialogue
from dialogs.inputconfigdialogue import InputConfigDialogue
from cflib.crazyflie import Crazyflie
from dialogs.logconfigdialogue import LogConfigDialogue

from cfclient.utils.input import JoystickReader
from cfclient.utils.config import Config
from cflib.crazyflie.log import Log
from cfclient.utils.logconfigreader import LogConfigReader, LogVariable, LogConfig

import cfclient.ui.dialogs
import cfclient.ui.toolboxes
import cfclient.ui.tabs
import cfclient.ui
import cflib.crtp

from cfclient.ui.dialogs.bootloader import BootloaderDialog
from cfclient.ui.dialogs.about import AboutDialog

main_window_class, main_windows_base_class = uic.loadUiType(sys.path[0] + '/cfclient/ui/main.ui')

class MyDockWidget(QtGui.QDockWidget):
    closed = pyqtSignal()

    def __init__(self, *args):
        super(MyDockWidget, self).__init__(*args)
    
    def closeEvent(self, event):
        super(MyDockWidget, self).closeEvent(event)
        self.closed.emit()

class UIState:
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2

class MainUI(QtGui.QMainWindow, main_window_class):

    connectionLostSignal = pyqtSignal(str, str)
    connectionInitiatedSignal = pyqtSignal(str)
    batteryUpdatedSignal = pyqtSignal(object)
    connectionDoneSignal = pyqtSignal(str)
    connectionFailedSignal = pyqtSignal(str, str)
    disconnectedSignal = pyqtSignal(str)
    linkQualitySignal = pyqtSignal(int)

    def __init__(self, *args):
        super(MainUI, self).__init__(*args)
        self.setupUi(self) 

        self.cfg = Config()
        self.cf = Crazyflie()

        cflib.crtp.init_drivers()

        # Create the connection dialogue
        self.connectDialogue = ConnectDialogue()

        # Create and start the Input Reader
        self.joystickReader = JoystickReader()
        self.joystickReader.start()
        
        # Connections for the Connect Dialogue
        self.connectDialogue.requestConnectionSignal.connect(self.cf.open_link)

        self.connectionDoneSignal.connect(self.connectionDone)
        self.cf.connectionFailed.add_callback(self.connectionFailedSignal.emit)
        self.connectionFailedSignal.connect(self.connectionFailed)
        self.joystickReader.inputDeviceErrorSignal.connect(self.inputDeviceError)
        
        # Connect UI signals
        self.menuItemConnect.triggered.connect(self.connectButtonClicked)
        self.logConfigAction.triggered.connect(self.doLogConfigDialogue)
        self.connectButton.clicked.connect(self.connectButtonClicked)
        self.quickConnectButton.clicked.connect(self.quickConnect)
        self.menuItemQuickConnect.triggered.connect(self.quickConnect)
        self.menuItemConfInputDevice.triggered.connect(self.configInputDevice)
        self.menuItemExit.triggered.connect(self.closeAppRequest)
        self.batteryUpdatedSignal.connect(self.updateBatteryVoltage)                    
        
        # Do not queue data from the controller output to the Crazyflie wrapper to avoid latency
        self.joystickReader.sendControlSetpointSignal.connect(self.cf.commander.send_setpoint, Qt.DirectConnection)

        # Connection callbacks and signal wrappers for UI protection
        self.cf.connectSetupFinished.add_callback(self.connectionDoneSignal.emit)
        self.connectionDoneSignal.connect(self.connectionDone)
        self.cf.disconnected.add_callback(self.disconnectedSignal.emit)
        self.disconnectedSignal.connect(lambda linkURI: self.setUIState(UIState.DISCONNECTED, linkURI))
        self.cf.connectionLost.add_callback(self.connectionLostSignal.emit)
        self.connectionLostSignal.connect(self.connectionLost)
        self.cf.connectionInitiated.add_callback(self.connectionInitiatedSignal.emit)
        self.connectionInitiatedSignal.connect(lambda linkURI: self.setUIState(UIState.CONNECTING, linkURI))

        # Connect link quality feedback
        self.cf.linkQuality.add_callback(self.linkQualitySignal.emit)
        self.linkQualitySignal.connect(lambda percentage: self.linkQualityBar.setValue(percentage))

        # Set UI state in disconnected buy default
        self.uiState = UIState.DISCONNECTED

        self.inputDeviceSelector.currentIndexChanged.connect(self.newInputConfigSelected)

        # Parse the log configuration files
        self.logConfigReader = LogConfigReader()
        self.logConfigReader.readConfigFiles()

        # Add things to helper so tabs can access it
        cfclient.ui.pluginhelper.cf = self.cf
        cfclient.ui.pluginhelper.inputDeviceReader = self.joystickReader
        cfclient.ui.pluginhelper.logConfigReader = self.logConfigReader
        
        self.logConfigDialogue = LogConfigDialogue(cfclient.ui.pluginhelper)
        self._bootloader_dialog = BootloaderDialog(cfclient.ui.pluginhelper)
        self.menuItemBootloader.triggered.connect(self._bootloader_dialog.show)
        self._about_dialog = AboutDialog(cfclient.ui.pluginhelper)
        self.menuItemAbout.triggered.connect(self._about_dialog.show)
        #Loading toolboxes (A bit of magic for a lot of automatic)
        self.toolboxes = []
        self.toolboxesMenuItem.setMenu(QtGui.QMenu())
        for t_class in cfclient.ui.toolboxes.toolboxes:
            toolbox = t_class(cfclient.ui.pluginhelper)
            dockToolbox = MyDockWidget(toolbox.getName())
            dockToolbox.setWidget(toolbox)
            self.toolboxes += [dockToolbox, ]
            
            #Add menu item for the toolbox
            item = QtGui.QAction(toolbox.getName(), self)
            item.setCheckable(True)
            item.triggered.connect(self.toggleToolbox)
            self.toolboxesMenuItem.menu().addAction(item)
            
            dockToolbox.closed.connect(lambda :self.toggleToolbox(False))
            
            #Setup some introspection
            item.dockToolbox = dockToolbox
            item.menuItem = item
            dockToolbox.dockToolbox = dockToolbox
            dockToolbox.menuItem = item

        # Load and connect tabs
        self.tabsMenuItem.setMenu(QtGui.QMenu())
        tmpTabList = {}
        for newTab in cfclient.ui.tabs.available:
            t = newTab(self.tabs, cfclient.ui.pluginhelper)
            item = QtGui.QAction(t.getMenuName(), self)
            item.setCheckable(True)
            item.toggled.connect(t.toggleVisibility)
            self.tabsMenuItem.menu().addAction(item)
            tmpTabList[t.getTabName()] = item
            # TODO: Fix this dirty hack!
            # Without this the signal never arrives is t.toggleVisibility when
            # clicked in menu ?!
            t.fakeIt()
        # First instantiate all the tabs and then open them in the correct order
        try:
            for tName in Config().get("open_tabs").split(","):
                t = tmpTabList[tName]
                if (t != None):
                    t.toggle() # Toggle though menu so it's also marked as open there
        except Exception as e:
            logger.warning("Exception while opening tabs [%s]", e)

        # Populate combo box with available input device configurations
        for c in self.joystickReader.getListOfConfigs():
            self.inputDeviceSelector.addItem(c)

        # Select saved input device configuration and enable combo box if any input device connected
        if (len(self.joystickReader.getAvailableDevices()) > 0):
            try:
                inputIndex = self.inputDeviceSelector.findText(Config().get("inputconfig"))
                if (inputIndex != -1):
                    self.inputDeviceSelector.setCurrentIndex(inputIndex)
                else:
                    # If we can't find it in the list save a new config using the current item
                    Config().set("inputconfig", self.inputDeviceSelector.currentText())
            except Exception as e:
                logger.warning("Exception while setting input config")
            self.inputDeviceSelector.setEnabled(True)

    def setUIState(self, newState, linkURI=""):
        self.uiState = newState
        if (newState == UIState.DISCONNECTED):
            self.setWindowTitle("Not connected")
            self.menuItemConnect.setText("Connect to Crazyflie")
            self.connectButton.setText("Connect")
            self.quickConnectButton.setEnabled(True)
            self.menuItemQuickConnect.setEnabled(True)
            self.batteryBar.setValue(3000)
            self.linkQualityBar.setValue(0)
            self.menuItemBootloader.setEnabled(True)
            self.logConfigAction.setEnabled(False)
        if (newState == UIState.CONNECTED):
            s = "Connected on %s" % linkURI
            self.setWindowTitle(s)
            self.menuItemConnect.setText("Disconnect")
            self.connectButton.setText("Disconnect")
            self.logConfigAction.setEnabled(True)
        if (newState == UIState.CONNECTING):
            s = "Connecting to %s" % linkURI
            self.setWindowTitle(s)
            self.menuItemConnect.setText("Cancel")
            self.connectButton.setText("Cancel")
            self.quickConnectButton.setEnabled(False)
            self.menuItemBootloader.setEnabled(False)
            self.menuItemQuickConnect.setEnabled(False)
    
    @pyqtSlot(bool)
    def toggleToolbox(self, display):
        menuItem = self.sender().menuItem
        dockToolbox = self.sender().dockToolbox
    
        if display and not dockToolbox.isVisible():
            dockToolbox.widget().enable()
            self.addDockWidget(dockToolbox.widget().preferedDockArea(), dockToolbox)
            dockToolbox.show()
        elif not display:
            dockToolbox.widget().disable()
            self.removeDockWidget(dockToolbox)
            dockToolbox.hide()
            menuItem.setChecked(False)

    def configInputDevice(self):
        self.inputConfig = InputConfigDialogue(self.joystickReader)
        self.inputConfig.show()

    def newInputConfigSelected(self, index):
        # Hardcoded to use index 0 joystick since no more are detected
        if (len(self.joystickReader.getAvailableDevices()) > 0):
            self.joystickReader.startInputSignal.emit(0, self.inputDeviceSelector.itemText(index))
        # To avoid saving settings while populating the combo box
        if (self.inputDeviceSelector.isEnabled()):
            Config().set("inputconfig", self.inputDeviceSelector.itemText(index))

    def doLogConfigDialogue(self):
        self.logConfigDialogue.show()

    def updateBatteryVoltage(self, data):
        self.batteryBar.setValue(int(data["pm.vbat"] * 1000))

    def connectionDone(self, linkURI):
        self.setUIState(UIState.CONNECTED, linkURI)

        Config().set("link_uri", linkURI)

        lg = LogConfig ("Battery", 1000)
        lg.addVariable(LogVariable("pm.vbat", "float"))
        self.log = self.cf.log.create_log_packet(lg)
        if (self.log != None):
            self.log.dataReceived.add_callback(self.batteryUpdatedSignal.emit)
            self.log.error.add_callback(self.loggingError)
            self.log.start()
        else:
            logger.warning("Could not setup loggingblock!")

    def loggingError(self, error):
        logger.warn("logging error %s", error)

    def connectionLost(self, linkURI, msg):
        if (self.isActiveWindow()):
            warningCaption = "Communication failure"
            error = "Connection lost to %s: %s" % (linkURI, msg)
            QMessageBox.critical(self,warningCaption, error)
        self.setUIState(UIState.DISCONNECTED, linkURI)   

    def connectionFailed(self, linkURI, error):
        msg =  "Failed to connect on %s: %s" % (linkURI, error)
        warningCaption = "Communication failure"
        QMessageBox.critical(self,warningCaption, msg)
        self.setUIState(UIState.DISCONNECTED, linkURI)

    def closeEvent(self, event):
        self.hide()
        self.cf.close_link()
        Config().save_file()

    def connectButtonClicked(self):
        if (self.uiState == UIState.CONNECTED):
            self.cf.close_link()
        elif (self.uiState == UIState.CONNECTING):
            self.cf.close_link()
            self.setUIState(UIState.DISCONNECTED)
        else:
            self.connectDialogue.show()

    def inputDeviceError(self, error):
        self.cf.close_link()
        QMessageBox.critical(self,"Input device error", error)      

    def quickConnect(self):
        try:
            self.cf.open_link(Config().get("link_uri"))
        except KeyError:
            self.cf.open_link("")    

    def closeAppRequest(self):
        self.close()
        app.exit(0);

