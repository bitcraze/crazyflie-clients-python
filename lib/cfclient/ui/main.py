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
#  this program; if not, write to the Free Software Foundation, Inc., 51
#  Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
The main file for the Crazyflie control application.
"""
__author__ = 'Bitcraze AB'
__all__ = ['MainUI']

import sys
import logging

logger = logging.getLogger(__name__)

from PyQt4 import QtGui, uic
from PyQt4.QtCore import pyqtSignal, Qt, pyqtSlot, QDir, QUrl
from PyQt4.QtGui import QLabel, QActionGroup, QMessageBox, QAction, QDesktopServices

from dialogs.connectiondialogue import ConnectDialogue
from dialogs.inputconfigdialogue import InputConfigDialogue
from dialogs.cf2config import Cf2ConfigDialog
from dialogs.cf1config import Cf1ConfigDialog
from cflib.crazyflie import Crazyflie
from dialogs.logconfigdialogue import LogConfigDialogue

from cfclient.utils.input import JoystickReader
from cfclient.utils.guiconfig import GuiConfig
from cfclient.utils.logconfigreader import LogConfigReader
from cfclient.utils.config_manager import ConfigManager

import cfclient.ui.toolboxes
import cfclient.ui.tabs
import cflib.crtp

from cflib.crazyflie.log import Log, LogVariable, LogConfig

from cfclient.ui.dialogs.bootloader import BootloaderDialog
from cfclient.ui.dialogs.about import AboutDialog

(main_window_class,
main_windows_base_class) = (uic.loadUiType(sys.path[0] +
                                           '/cfclient/ui/main.ui'))


class MyDockWidget(QtGui.QDockWidget):
    closed = pyqtSignal()

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
    batteryUpdatedSignal = pyqtSignal(int, object, object)
    connectionDoneSignal = pyqtSignal(str)
    connectionFailedSignal = pyqtSignal(str, str)
    disconnectedSignal = pyqtSignal(str)
    linkQualitySignal = pyqtSignal(int)

    _input_device_error_signal = pyqtSignal(str)
    _input_discovery_signal = pyqtSignal(object)
    _log_error_signal = pyqtSignal(object, str)

    def __init__(self, *args):
        super(MainUI, self).__init__(*args)
        self.setupUi(self)
        
        ######################################################
        ### By lxrocks
        ### 'Skinny Progress Bar' tweak for Yosemite
        ### Tweak progress bar - artistic I am not - so pick your own colors !!!
        ### Only apply to Yosemite
        ######################################################
        import platform
        if platform.system() == 'Darwin':
        
            (Version,junk,machine) =  platform.mac_ver()
            logger.info("This is a MAC - checking if we can apply Progress Bar Stylesheet for Yosemite Skinny Bars ")
            yosemite = (10,10,0)
            tVersion = tuple(map(int, (Version.split("."))))
            
            if tVersion >= yosemite:
                logger.info( "Found Yosemite:")
        
                tcss = """
                    QProgressBar {
                    border: 2px solid grey;
                    border-radius: 5px;
                    text-align: center;
                }
                QProgressBar::chunk {
                     background-color: #05B8CC;
                 }
                 """
                self.setStyleSheet(tcss)
                
            else:
                logger.info( "Pre-Yosemite")
        
        ######################################################
        
        self.cf = Crazyflie(ro_cache=sys.path[0] + "/cflib/cache",
                            rw_cache=sys.path[1] + "/cache")

        cflib.crtp.init_drivers(enable_debug_driver=GuiConfig()
                                                .get("enable_debug_driver"))

        # Create the connection dialogue
        self.connectDialogue = ConnectDialogue()

        # Create and start the Input Reader
        self._statusbar_label = QLabel("Loading device and configuration.")
        self.statusBar().addWidget(self._statusbar_label)

        self.joystickReader = JoystickReader()
        self._active_device = ""
        self.configGroup = QActionGroup(self._menu_mappings, exclusive=True)
        self._load_input_data()
        self._update_input
        ConfigManager().conf_needs_reload.add_callback(self._reload_configs)

        # Connections for the Connect Dialogue
        self.connectDialogue.requestConnectionSignal.connect(self.cf.open_link)

        self.connectionDoneSignal.connect(self.connectionDone)
        self.cf.connection_failed.add_callback(self.connectionFailedSignal.emit)
        self.connectionFailedSignal.connect(self.connectionFailed)
        
        
        self._input_device_error_signal.connect(self.inputDeviceError)
        self.joystickReader.device_error.add_callback(
                        self._input_device_error_signal.emit)
        self._input_discovery_signal.connect(self.device_discovery)
        self.joystickReader.device_discovery.add_callback(
                        self._input_discovery_signal.emit)

        # Connect UI signals
        self.menuItemConnect.triggered.connect(self.connectButtonClicked)
        self.logConfigAction.triggered.connect(self.doLogConfigDialogue)
        self.connectButton.clicked.connect(self.connectButtonClicked)
        self.quickConnectButton.clicked.connect(self.quickConnect)
        self.menuItemQuickConnect.triggered.connect(self.quickConnect)
        self.menuItemConfInputDevice.triggered.connect(self.configInputDevice)
        self.menuItemExit.triggered.connect(self.closeAppRequest)
        self.batteryUpdatedSignal.connect(self.updateBatteryVoltage)
        self._menuitem_rescandevices.triggered.connect(self._rescan_devices)
        self._menuItem_openconfigfolder.triggered.connect(self._open_config_folder)

        self._auto_reconnect_enabled = GuiConfig().get("auto_reconnect")
        self.autoReconnectCheckBox.toggled.connect(
                                              self._auto_reconnect_changed)
        self.autoReconnectCheckBox.setChecked(GuiConfig().get("auto_reconnect"))
        
        # Do not queue data from the controller output to the Crazyflie wrapper
        # to avoid latency
        #self.joystickReader.sendControlSetpointSignal.connect(
        #                                      self.cf.commander.send_setpoint,
        #                                      Qt.DirectConnection)
        self.joystickReader.input_updated.add_callback(
                                         self.cf.commander.send_setpoint)

        # Connection callbacks and signal wrappers for UI protection
        self.cf.connected.add_callback(
                                              self.connectionDoneSignal.emit)
        self.connectionDoneSignal.connect(self.connectionDone)
        self.cf.disconnected.add_callback(self.disconnectedSignal.emit)
        self.disconnectedSignal.connect(
                        lambda linkURI: self.setUIState(UIState.DISCONNECTED,
                                                        linkURI))
        self.cf.connection_lost.add_callback(self.connectionLostSignal.emit)
        self.connectionLostSignal.connect(self.connectionLost)
        self.cf.connection_requested.add_callback(
                                         self.connectionInitiatedSignal.emit)
        self.connectionInitiatedSignal.connect(
                           lambda linkURI: self.setUIState(UIState.CONNECTING,
                                                           linkURI))
        self._log_error_signal.connect(self._logging_error)

        # Connect link quality feedback
        self.cf.link_quality_updated.add_callback(self.linkQualitySignal.emit)
        self.linkQualitySignal.connect(
                   lambda percentage: self.linkQualityBar.setValue(percentage))

        # Set UI state in disconnected buy default
        self.setUIState(UIState.DISCONNECTED)

        # Parse the log configuration files
        self.logConfigReader = LogConfigReader(self.cf)

        # Add things to helper so tabs can access it
        cfclient.ui.pluginhelper.cf = self.cf
        cfclient.ui.pluginhelper.inputDeviceReader = self.joystickReader
        cfclient.ui.pluginhelper.logConfigReader = self.logConfigReader

        self.logConfigDialogue = LogConfigDialogue(cfclient.ui.pluginhelper)
        self._bootloader_dialog = BootloaderDialog(cfclient.ui.pluginhelper)
        self._cf2config_dialog = Cf2ConfigDialog(cfclient.ui.pluginhelper)
        self._cf1config_dialog = Cf1ConfigDialog(cfclient.ui.pluginhelper)
        self.menuItemBootloader.triggered.connect(self._bootloader_dialog.show)
        self._about_dialog = AboutDialog(cfclient.ui.pluginhelper)
        self.menuItemAbout.triggered.connect(self._about_dialog.show)
        self._menu_cf2_config.triggered.connect(self._cf2config_dialog.show)
        self._menu_cf1_config.triggered.connect(self._cf1config_dialog.show)

        # Loading toolboxes (A bit of magic for a lot of automatic)
        self.toolboxes = []
        self.toolboxesMenuItem.setMenu(QtGui.QMenu())
        for t_class in cfclient.ui.toolboxes.toolboxes:
            toolbox = t_class(cfclient.ui.pluginhelper)
            dockToolbox = MyDockWidget(toolbox.getName())
            dockToolbox.setWidget(toolbox)
            self.toolboxes += [dockToolbox, ]

            # Add menu item for the toolbox
            item = QtGui.QAction(toolbox.getName(), self)
            item.setCheckable(True)
            item.triggered.connect(self.toggleToolbox)
            self.toolboxesMenuItem.menu().addAction(item)

            dockToolbox.closed.connect(lambda: self.toggleToolbox(False))

            # Setup some introspection
            item.dockToolbox = dockToolbox
            item.menuItem = item
            dockToolbox.dockToolbox = dockToolbox
            dockToolbox.menuItem = item

        # Load and connect tabs
        self.tabsMenuItem.setMenu(QtGui.QMenu())
        tabItems = {}
        self.loadedTabs = []
        for tabClass in cfclient.ui.tabs.available:
            tab = tabClass(self.tabs, cfclient.ui.pluginhelper)
            item = QtGui.QAction(tab.getMenuName(), self)
            item.setCheckable(True)
            item.toggled.connect(tab.toggleVisibility)
            self.tabsMenuItem.menu().addAction(item)
            tabItems[tab.getTabName()] = item
            self.loadedTabs.append(tab)
            if not tab.enabled:
                item.setEnabled(False)

        # First instantiate all tabs and then open them in the correct order
        try:
            for tName in GuiConfig().get("open_tabs").split(","):
                t = tabItems[tName]
                if (t != None and t.isEnabled()):
                    # Toggle though menu so it's also marked as open there
                    t.toggle()
        except Exception as e:
            logger.warning("Exception while opening tabs [%s]", e)

    def setUIState(self, newState, linkURI=""):
        self.uiState = newState
        if (newState == UIState.DISCONNECTED):
            self.setWindowTitle("Not connected")
            self.menuItemConnect.setText("Connect to Crazyflie")
            self.connectButton.setText("Connect")
            self.menuItemQuickConnect.setEnabled(True)
            self.batteryBar.setValue(3000)
            self._menu_cf2_config.setEnabled(False)
            self.linkQualityBar.setValue(0)
            self.menuItemBootloader.setEnabled(True)
            self.logConfigAction.setEnabled(False)
            if (len(GuiConfig().get("link_uri")) > 0):
                self.quickConnectButton.setEnabled(True)
        if (newState == UIState.CONNECTED):
            s = "Connected on %s" % linkURI
            self.setWindowTitle(s)
            self.menuItemConnect.setText("Disconnect")
            self.connectButton.setText("Disconnect")
            self.logConfigAction.setEnabled(True)
            self._menu_cf2_config.setEnabled(True)
        if (newState == UIState.CONNECTING):
            s = "Connecting to %s ..." % linkURI
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
            self.addDockWidget(dockToolbox.widget().preferedDockArea(),
                               dockToolbox)
            dockToolbox.show()
        elif not display:
            dockToolbox.widget().disable()
            self.removeDockWidget(dockToolbox)
            dockToolbox.hide()
            menuItem.setChecked(False)

    def _rescan_devices(self):
        self._statusbar_label.setText("No inputdevice connected!")
        self._menu_devices.clear()
        self._active_device = ""
        self.joystickReader.stop_input()
        for c in self._menu_mappings.actions():
            c.setEnabled(False)
        devs = self.joystickReader.getAvailableDevices()
        if (len(devs) > 0):
            self.device_discovery(devs)

    def configInputDevice(self):
        self.inputConfig = InputConfigDialogue(self.joystickReader)
        self.inputConfig.show()
        
    def _auto_reconnect_changed(self, checked):
        self._auto_reconnect_enabled = checked 
        GuiConfig().set("auto_reconnect", checked)
        logger.info("Auto reconnect enabled: %s", checked)     

    def doLogConfigDialogue(self):
        self.logConfigDialogue.show()

    def updateBatteryVoltage(self, timestamp, data, logconf):
        self.batteryBar.setValue(int(data["pm.vbat"] * 1000))

    def connectionDone(self, linkURI):
        self.setUIState(UIState.CONNECTED, linkURI)

        GuiConfig().set("link_uri", linkURI)

        lg = LogConfig("Battery", 1000)
        lg.add_variable("pm.vbat", "float")
        self.cf.log.add_config(lg)
        if lg.valid:
            lg.data_received_cb.add_callback(self.batteryUpdatedSignal.emit)
            lg.error_cb.add_callback(self._log_error_signal.emit)
            lg.start()
        else:
            logger.warning("Could not setup loggingblock!")

    def _logging_error(self, log_conf, msg):
        QMessageBox.about(self, "Log error", "Error when starting log config"
                " [%s]: %s" % (log_conf.name, msg))

    def connectionLost(self, linkURI, msg):
        if not self._auto_reconnect_enabled:
            if (self.isActiveWindow()):
                warningCaption = "Communication failure"
                error = "Connection lost to %s: %s" % (linkURI, msg)
                QMessageBox.critical(self, warningCaption, error)
                self.setUIState(UIState.DISCONNECTED, linkURI)
        else:
            self.quickConnect()

    def connectionFailed(self, linkURI, error):
        if not self._auto_reconnect_enabled:
            msg = "Failed to connect on %s: %s" % (linkURI, error)
            warningCaption = "Communication failure"
            QMessageBox.critical(self, warningCaption, msg)
            self.setUIState(UIState.DISCONNECTED, linkURI)
        else:
            self.quickConnect()

    def closeEvent(self, event):
        self.hide()
        self.cf.close_link()
        GuiConfig().save_file()

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
        QMessageBox.critical(self, "Input device error", error)

    def _load_input_data(self):
        self.joystickReader.stop_input()
        # Populate combo box with available input device configurations
        for c in ConfigManager().get_list_of_configs():
            node = QAction(c,
                           self._menu_mappings,
                           checkable=True,
                           enabled=False)
            node.toggled.connect(self._inputconfig_selected)
            self.configGroup.addAction(node)
            self._menu_mappings.addAction(node)

    def _reload_configs(self, newConfigName):
        # remove the old actions from the group and the menu
        for action in self._menu_mappings.actions():
            self.configGroup.removeAction(action)
        self._menu_mappings.clear()

        # reload the conf files, and populate the menu
        self._load_input_data()

        self._update_input(self._active_device, newConfigName)

    def _update_input(self, device="", config=""):
        self.joystickReader.stop_input()
        self._active_config = str(config)
        self._active_device = str(device)

        GuiConfig().set("input_device", self._active_device)
        GuiConfig().get(
                     "device_config_mapping"
                     )[self._active_device] = self._active_config
        self.joystickReader.start_input(self._active_device,
                                       self._active_config)

        # update the checked state of the menu items
        for c in self._menu_mappings.actions():
            c.setEnabled(True)
            if c.text() == self._active_config:
                c.setChecked(True)
        for c in self._menu_devices.actions():
            c.setEnabled(True)
            if c.text() == self._active_device:
                c.setChecked(True)

        # update label
        if device == "" and config == "":
            self._statusbar_label.setText("No input device selected")
        elif config == "":
            self._statusbar_label.setText("Using [%s] - "
                                          "No input config selected" %
                                          (self._active_device))
        else:
            self._statusbar_label.setText("Using [%s] with config [%s]" %
                                          (self._active_device,
                                           self._active_config))

    def _inputdevice_selected(self, checked):
        if (not checked):
            return
        self.joystickReader.stop_input()
        sender = self.sender()
        self._active_device = sender.text()
        device_config_mapping = GuiConfig().get("device_config_mapping")
        if (self._active_device in device_config_mapping.keys()):
            self._current_input_config = device_config_mapping[
                str(self._active_device)]
        else:
            self._current_input_config = self._menu_mappings.actions()[0].text()
        GuiConfig().set("input_device", str(self._active_device))

        for c in self._menu_mappings.actions():
            if (c.text() == self._current_input_config):
                c.setChecked(True)

        self.joystickReader.start_input(str(sender.text()),
                                        self._current_input_config)
        self._statusbar_label.setText("Using [%s] with config [%s]" % (
                                      self._active_device,
                                      self._current_input_config))

    def _inputconfig_selected(self, checked):
        if (not checked):
            return
        self._update_input(self._active_device, self.sender().text())

    def device_discovery(self, devs):
        group = QActionGroup(self._menu_devices, exclusive=True)

        for d in devs:
            node = QAction(d["name"], self._menu_devices, checkable=True)
            node.toggled.connect(self._inputdevice_selected)
            group.addAction(node)
            self._menu_devices.addAction(node)
            if (d["name"] == GuiConfig().get("input_device")):
                self._active_device = d["name"]
        if (len(self._active_device) == 0):
            self._active_device = self._menu_devices.actions()[0].text()

        device_config_mapping = GuiConfig().get("device_config_mapping")
        if (device_config_mapping):
            if (self._active_device in device_config_mapping.keys()):
                self._current_input_config = device_config_mapping[
                    str(self._active_device)]
            else:
                self._current_input_config = self._menu_mappings.actions()[0].text()
        else:
            self._current_input_config = self._menu_mappings.actions()[0].text()

        # Now we know what device to use and what mapping, trigger the events
        # to change the menus and start the input
        for c in self._menu_mappings.actions():
            c.setEnabled(True)
            if (c.text() == self._current_input_config):
                c.setChecked(True)

        for c in self._menu_devices.actions():
            if (c.text() == self._active_device):
                c.setChecked(True)

    def quickConnect(self):
        try:
            self.cf.open_link(GuiConfig().get("link_uri"))
        except KeyError:
            self.cf.open_link("")

    def _open_config_folder(self):
        QDesktopServices.openUrl(QUrl("file:///" + QDir.toNativeSeparators(sys.path[1])))

    def closeAppRequest(self):
        self.close()
        sys.exit(0)
