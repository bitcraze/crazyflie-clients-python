#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2021 Bitcraze AB
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
import logging
import sys
import usb
from sys import stdout

from cfclient.multicopter_sim import MulticopterSimClient

import cfclient
from cfclient.ui.pose_logger import PoseLogger
from cfclient.ui.tab_toolbox import TabToolbox
import cfclient.ui.tabs
import cflib.crtp
from cfclient.ui.dialogs.about import AboutDialog
from cfclient.ui.dialogs.bootloader import BootloaderDialog
from cfclient.ui.connectivity_manager import ConnectivityManager
from cfclient.utils.config import Config
from cfclient.utils.config_manager import ConfigManager
from cfclient.utils.input import JoystickReader
from cfclient.utils.logconfigreader import LogConfigReader
from cfclient.utils.ui import UiUtils
from cfclient.utils.zmq_led_driver import ZMQLEDDriver
from cfclient.utils.zmq_param import ZMQParamAccess
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.mem import MemoryElement
from PyQt5 import QtWidgets
from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtCore import QDir
from PyQt5.QtCore import QThread
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import QActionGroup
from PyQt5.QtWidgets import QShortcut
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QMessageBox

from .dialogs.cf2config import Cf2ConfigDialog
from .dialogs.inputconfigdialogue import InputConfigDialogue
from .dialogs.logconfigdialogue import LogConfigDialogue


__author__ = 'Bitcraze AB'
__all__ = ['MainUI']

logger = logging.getLogger(__name__)

(main_window_class,
 main_windows_base_class) = (uic.loadUiType(cfclient.module_path +
                                            '/ui/main.ui'))


class UIState:
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    SCANNING = 3


class BatteryStates:
    BATTERY, CHARGING, CHARGED, LOW_POWER = list(range(4))


class MainUI(QtWidgets.QMainWindow, main_window_class):
    connectionLostSignal = pyqtSignal(str, str)
    connectionInitiatedSignal = pyqtSignal(str)
    batteryUpdatedSignal = pyqtSignal(int, object, object)
    connectionDoneSignal = pyqtSignal(str)
    connectionFailedSignal = pyqtSignal(str, str)
    disconnectedSignal = pyqtSignal(str)
    linkQualitySignal = pyqtSignal(float)

    _input_device_error_signal = pyqtSignal(str)
    _input_discovery_signal = pyqtSignal(object)
    _log_error_signal = pyqtSignal(object, str)

    def __init__(self, *args):
        super(MainUI, self).__init__(*args)
        self.setupUi(self)

        self.sim_client = None

        # Restore window size if present in the config file
        try:
            size = Config().get("window_size")
            self.resize(size[0], size[1])
        except KeyError:
            pass

        self.cf = Crazyflie(ro_cache=None,
                            rw_cache=cfclient.config_path + "/cache")

        cflib.crtp.init_drivers()

        zmq_params = ZMQParamAccess(self.cf)
        zmq_params.start()

        zmq_leds = ZMQLEDDriver(self.cf)
        zmq_leds.start()

        self.scanner = ScannerThread()
        self.scanner.interfaceFoundSignal.connect(self.foundInterfaces)
        self.scanner.start()

        # Create and start the Input Reader
        self._statusbar_label = QLabel("No input-device found, insert one to"
                                       " fly.")
        self.statusBar().addWidget(self._statusbar_label)

        #
        # We use this hacky-trick to find out if we are in dark-mode and
        # figure out what bgcolor to set from that. We always use the current
        # palette forgreound.
        #
        self.textColor = self._statusbar_label.palette().color(QPalette.WindowText)
        self.bgColor = self._statusbar_label.palette().color(QPalette.Background)
        self.isDark = self.textColor.value() > self.bgColor.value()

        self.joystickReader = JoystickReader()
        self._active_device = ""
        # self.configGroup = QActionGroup(self._menu_mappings, exclusive=True)

        self._mux_group = QActionGroup(self._menu_inputdevice)
        self._mux_group.setExclusive(True)

        # TODO: Need to reload configs
        # ConfigManager().conf_needs_reload.add_callback(self._reload_configs)

        self.connect_input = QShortcut("Ctrl+I", self.connectButton, self._connect)
        self.cf.connection_failed.add_callback(
            self.connectionFailedSignal.emit)
        self.connectionFailedSignal.connect(self._connection_failed)

        self._input_device_error_signal.connect(
            self._display_input_device_error)
        self.joystickReader.device_error.add_callback(
            self._input_device_error_signal.emit)
        self._input_discovery_signal.connect(self.device_discovery)
        self.joystickReader.device_discovery.add_callback(
            self._input_discovery_signal.emit)

        # Connect UI signals
        self.logConfigAction.triggered.connect(self._show_connect_dialog)
        self.menuItemConnect.triggered.connect(self._connect)
        self.menuItemConfInputDevice.triggered.connect(
            self._show_input_device_config_dialog)
        self.menuItemExit.triggered.connect(self.closeAppRequest)
        self.batteryUpdatedSignal.connect(self._update_battery)
        self._menuitem_rescandevices.triggered.connect(self._rescan_devices)
        self._menuItem_openconfigfolder.triggered.connect(
            self._open_config_folder)

        self._set_address()

        self._connectivity_manager = ConnectivityManager()
        self._connectivity_manager.register_ui_elements(
            ConnectivityManager.UiElementsContainer(
                interface_combo=self.interfaceCombo,
                address_spinner=self.address,
                connect_button=self.connectButton,
                scan_button=self.scanButton))

        self._connectivity_manager.connect_button_clicked.connect(self._connect)
        self._connectivity_manager.scan_button_clicked.connect(self._scan_from_button)

        self._disable_input = False

        self.joystickReader.input_updated.add_callback(
            lambda *args: self._disable_input or
            self.cf.commander.send_setpoint(*args))

        self.joystickReader.assisted_input_updated.add_callback(
            lambda *args: self._disable_input or
            self.cf.commander.send_velocity_world_setpoint(*args))

        self.joystickReader.heighthold_input_updated.add_callback(
            lambda *args: self._disable_input or
            self.cf.commander.send_zdistance_setpoint(*args))

        self.joystickReader.hover_input_updated.add_callback(
            self.cf.commander.send_hover_setpoint)

        # Emergency stop button
        self.esButton.clicked.connect(self._emergency_stop)

        # Connection callbacks and signal wrappers for UI protection
        self.cf.connected.add_callback(self.connectionDoneSignal.emit)
        self.connectionDoneSignal.connect(self._connected)
        self.cf.disconnected.add_callback(self.disconnectedSignal.emit)
        self.disconnectedSignal.connect(self._disconnected)
        self.cf.connection_lost.add_callback(self.connectionLostSignal.emit)
        self.connectionLostSignal.connect(self._connection_lost)
        self.cf.connection_requested.add_callback(
            self.connectionInitiatedSignal.emit)
        self.connectionInitiatedSignal.connect(self._connection_initiated)
        self._log_error_signal.connect(self._logging_error)

        self.batteryBar.setTextVisible(False)
        self.linkQualityBar.setTextVisible(False)

        # Connect link quality feedback
        self.cf.link_quality_updated.add_callback(self.linkQualitySignal.emit)
        self.linkQualitySignal.connect(
            lambda percentage: self.linkQualityBar.setValue(int(percentage)))

        # Parse the log configuration files
        self.logConfigReader = LogConfigReader(self.cf)

        self._current_input_config = None
        self._active_config = None
        self._active_config = None

        self.inputConfig = None

        # Add things to helper so tabs can access it
        cfclient.ui.pluginhelper.cf = self.cf
        cfclient.ui.pluginhelper.inputDeviceReader = self.joystickReader
        cfclient.ui.pluginhelper.logConfigReader = self.logConfigReader
        cfclient.ui.pluginhelper.pose_logger = PoseLogger(self.cf)
        cfclient.ui.pluginhelper.connectivity_manager = self._connectivity_manager
        cfclient.ui.pluginhelper.mainUI = self

        self.logConfigDialogue = LogConfigDialogue(cfclient.ui.pluginhelper)
        self._bootloader_dialog = BootloaderDialog(cfclient.ui.pluginhelper)
        self._cf2config_dialog = Cf2ConfigDialog(cfclient.ui.pluginhelper)
        self.menuItemBootloader.triggered.connect(self._bootloader_dialog.show)
        self._about_dialog = AboutDialog(cfclient.ui.pluginhelper)
        self.menuItemAbout.triggered.connect(self._about_dialog.show)
        self._menu_cf2_config.triggered.connect(self._cf2config_dialog.show)

        self._connectivity_manager.set_address(self.address.value())

        self._initial_scan = True
        self._scan(self._connectivity_manager.get_address())

        self.tabs_menu_item = QMenu("Tabs", self.menuView, enabled=True)
        self.menuView.addMenu(self.tabs_menu_item)

        self.toolboxes_menu_item = QMenu("Toolboxes", self.menuView, enabled=True)
        self.menuView.addMenu(self.toolboxes_menu_item)

        self.loaded_tab_toolboxes = self.create_tab_toolboxes(self.tabs_menu_item,
                                                              self.toolboxes_menu_item,
                                                              self.tab_widget)
        self.read_tab_toolbox_config(self.loaded_tab_toolboxes)

        # References to all the device sub-menus in the "Input device" menu
        self._all_role_menus = ()
        # Used to filter what new devices to add default mapping to
        self._available_devices = ()
        # Keep track of mux nodes so we can enable according to how many
        # devices we have
        self._all_mux_nodes = ()

        # Check which Input muxes are available
        self._mux_group = QActionGroup(self._menu_inputdevice)
        self._mux_group.setExclusive(True)
        for m in self.joystickReader.available_mux():
            node = QAction(m.name,
                           self._menu_inputdevice,
                           checkable=True,
                           enabled=False)
            node.toggled.connect(self._mux_selected)
            self._mux_group.addAction(node)
            self._menu_inputdevice.addAction(node)
            self._all_mux_nodes += (node,)
            mux_subnodes = ()
            for name in m.supported_roles():
                sub_node = QMenu("    {}".format(name),
                                 self._menu_inputdevice,
                                 enabled=False)
                self._menu_inputdevice.addMenu(sub_node)
                mux_subnodes += (sub_node,)
                self._all_role_menus += ({"muxmenu": node,
                                          "rolemenu": sub_node},)
            node.setData((m, mux_subnodes))

        self._mapping_support = True

        # Add checkbuttons for theme-selection.
        self._theme_group = QActionGroup(self.menuThemes)
        self._theme_group.setExclusive(True)
        self._theme_checkboxes = []
        for theme in UiUtils.THEMES:
            node = QAction(theme, self.menuThemes, checkable=True)
            node.setObjectName(theme)
            node.toggled.connect(self._theme_selected)
            self._theme_checkboxes.append(node)
            self._theme_group.addAction(node)
            self.menuThemes.addAction(node)

        # We only want to warn about USB permission once
        self._permission_warned = False

    def create_tab_toolboxes(self, tabs_menu_item, toolboxes_menu_item, tab_widget):
        loaded_tab_toolboxes = {}

        self._debug('**************************** ' + str(cfclient.ui.tabs.FlightTab))

        for tab_class in cfclient.ui.tabs.available:
            tab_toolbox = tab_class(cfclient.ui.pluginhelper)
            loaded_tab_toolboxes[tab_toolbox.get_tab_toolbox_name()] = tab_toolbox

            # Set reference for plot-tab.
            if isinstance(tab_toolbox, cfclient.ui.tabs.PlotTab):
                cfclient.ui.pluginhelper.plotTab = tab_toolbox

            # Add to tabs menu
            tab_action_item = QtWidgets.QAction(tab_toolbox.get_tab_toolbox_name())
            tab_action_item.setCheckable(True)
            tab_action_item.triggered.connect(self.toggle_tab_visibility)
            tab_action_item.tab_toolbox = tab_toolbox
            tab_toolbox.tab_action_item = tab_action_item

            tabs_menu_item.addAction(tab_action_item)

            # Add to toolbox menu
            toolbox_action_item = QtWidgets.QAction(tab_toolbox.get_tab_toolbox_name())
            toolbox_action_item.setCheckable(True)
            toolbox_action_item.triggered.connect(self.toggle_toolbox_visibility)
            toolbox_action_item.tab_toolbox = tab_toolbox
            tab_toolbox.toolbox_action_item = toolbox_action_item
            tab_toolbox.dock_widget.closed.connect(
                    lambda: self.toggle_toolbox_visibility(False))
            tab_toolbox.dock_widget.dockLocationChanged.connect(
                    lambda area: self.set_preferred_dock_area(area))

            toolboxes_menu_item.addAction(toolbox_action_item)

        return loaded_tab_toolboxes

    def read_tab_toolbox_config(self, loaded_tab_toolboxes):
        # Add tabs in the correct order
        for name in TabToolbox.read_open_tab_config():
            if name in loaded_tab_toolboxes.keys():
                self._tab_toolbox_show_as_tab(loaded_tab_toolboxes[name])

        for name in TabToolbox.read_open_toolbox_config():
            if name in loaded_tab_toolboxes.keys():
                self._tab_toolbox_show_as_toolbox(loaded_tab_toolboxes[name])

    def _debug(self, msg):
        print(msg)
        stdout.flush()

    def _set_address(self):
        address = 0xE7E7E7E7E7
        try:
            link_uri = Config().get("link_uri")
            if link_uri.startswith("radio://"):
                if len(link_uri) > 0:
                    parts = link_uri.split('/')
                    # The uri might not contain an address
                    if len(parts) == 6:
                        address = int(parts[-1], 16)
        except Exception as err:
            logger.warn('failed to parse address from config: %s' % str(err))
        finally:
            self.address.setValue(address)

    def _theme_selected(self, *args):
        """ Callback when a theme is selected. """
        for checkbox in self._theme_checkboxes:
            if checkbox.isChecked():
                theme = checkbox.objectName()
                app = QtWidgets.QApplication.instance()
                app.setStyleSheet(UiUtils.select_theme(theme))
                Config().set('theme', theme)

    def _check_theme(self, theme_name):
        # Check the default theme.
        for theme in self._theme_checkboxes:
            if theme.objectName() == theme_name:
                theme.setChecked(True)
                self._theme_selected(True)

    def set_default_theme(self):
        try:
            theme = Config().get('theme')
        except KeyError:
            theme = 'Default'
        self._check_theme(theme)

    def disable_input(self, disable):
        """
        Disable the gamepad input to be able to send setpoint from a tab
        """
        self._disable_input = disable

    def foundInterfaces(self, interfaces):
        selected_interface = self._connectivity_manager.get_interface()

        formatted_interfaces = []
        for i in interfaces:
            if len(i[1]) > 0:
                interface = "%s - %s" % (i[0], i[1])
            else:
                interface = i[0]
            formatted_interfaces.append(interface)

        if self._initial_scan:
            self._initial_scan = False

            try:
                if len(Config().get("link_uri")) > 0:
                    formatted_interfaces.index(Config().get("link_uri"))
                    selected_interface = Config().get("link_uri")
            except KeyError:
                #  The configuration for link_uri was not found
                pass
            except ValueError:
                #  The saved URI was not found while scanning
                pass

        if len(interfaces) == 1 and selected_interface is None:
            selected_interface = interfaces[0][0]

        newIndex = None
        if selected_interface is not None:
            try:
                newIndex = formatted_interfaces.index(selected_interface)
            except ValueError:
                pass

        self._connectivity_manager.set_interfaces(formatted_interfaces, newIndex)

        self.uiState = UIState.DISCONNECTED
        self._update_ui_state()

    def _update_ui_state(self):
        if self.uiState == UIState.DISCONNECTED:
            self.setWindowTitle("Not connected")
            canConnect = self._connectivity_manager.get_interface() is not None
            self.menuItemConnect.setText("Connect to Crazyflie")
            self.menuItemConnect.setEnabled(canConnect)
            self._connectivity_manager.set_state(ConnectivityManager.UIState.DISCONNECTED)
            self.batteryBar.setValue(3000)
            self._menu_cf2_config.setEnabled(False)
            self.linkQualityBar.setValue(0)
            self.logConfigAction.setEnabled(False)
            self.esButton.setStyleSheet("")
            self.esButton.setEnabled(False)
        elif self.uiState == UIState.CONNECTED:
            s = "Connected on %s" % self._connectivity_manager.get_interface()
            self.setWindowTitle(s)
            self.menuItemConnect.setText("Disconnect")
            self.menuItemConnect.setEnabled(True)
            self._connectivity_manager.set_state(ConnectivityManager.UIState.CONNECTED)
            self.logConfigAction.setEnabled(True)
            self.esButton.setEnabled(True)
            self.esButton.setStyleSheet("background-color: red")
            # Find out if there's an I2C EEPROM, otherwise don't show the
            # dialog.
            if len(self.cf.mem.get_mems(MemoryElement.TYPE_I2C)) > 0:
                self._menu_cf2_config.setEnabled(True)
        elif self.uiState == UIState.CONNECTING:
            s = "Connecting to {} ...".format(self._connectivity_manager.get_interface())
            self.setWindowTitle(s)
            self.menuItemConnect.setText("Cancel")
            self.menuItemConnect.setEnabled(True)
            self._connectivity_manager.set_state(ConnectivityManager.UIState.CONNECTING)
        elif self.uiState == UIState.SCANNING:
            self.setWindowTitle("Scanning ...")
            self.menuItemConnect.setEnabled(False)
            self._connectivity_manager.set_state(ConnectivityManager.UIState.SCANNING)

    @pyqtSlot(bool)
    def toggle_tab_visibility(self, checked):
        tab_action_item = self.sender()
        tab_toolbox = tab_action_item.tab_toolbox

        if checked:
            self._tab_toolbox_show_as_tab(tab_toolbox)
        else:
            self._tab_toolbox_hide(tab_toolbox)

    @pyqtSlot(bool)
    def toggle_toolbox_visibility(self, checked):
        toolbox_action_item = self.sender()
        tab_toolbox = toolbox_action_item.tab_toolbox

        if checked:
            self._tab_toolbox_show_as_toolbox(tab_toolbox)
        else:
            self._tab_toolbox_hide(tab_toolbox)

    def _tab_toolbox_show_as_tab(self, tab_toolbox):
        if tab_toolbox.get_display_state() == TabToolbox.DS_TOOLBOX:
            dock_widget = tab_toolbox.dock_widget
            self.removeDockWidget(dock_widget)
            dock_widget.hide()

        if tab_toolbox.get_display_state() != TabToolbox.DS_TAB:
            tab_toolbox_name = tab_toolbox.get_tab_toolbox_name()
            self.tab_widget.addTab(tab_toolbox, tab_toolbox_name)

        tab_toolbox.tab_action_item.setChecked(True)
        tab_toolbox.toolbox_action_item.setChecked(False)
        tab_toolbox.set_display_state(TabToolbox.DS_TAB)

    def _tab_toolbox_show_as_toolbox(self, tab_toolbox):
        dock_widget = tab_toolbox.dock_widget

        if tab_toolbox.get_display_state() == TabToolbox.DS_TAB:
            self.tab_widget.removeTab(self.tab_widget.indexOf(tab_toolbox))

        if tab_toolbox.get_display_state() != TabToolbox.DS_TOOLBOX:
            self.addDockWidget(tab_toolbox.preferred_dock_area(), dock_widget)
            dock_widget.setWidget(tab_toolbox)
            dock_widget.show()

        tab_toolbox.tab_action_item.setChecked(False)
        tab_toolbox.toolbox_action_item.setChecked(True)
        tab_toolbox.set_display_state(TabToolbox.DS_TOOLBOX)

    def _tab_toolbox_hide(self, tab_toolbox):
        dock_widget = tab_toolbox.dock_widget

        if tab_toolbox.get_display_state() == TabToolbox.DS_TAB:
            self.tab_widget.removeTab(self.tab_widget.indexOf(tab_toolbox))
        elif tab_toolbox.get_display_state() == TabToolbox.DS_TOOLBOX:
            self.removeDockWidget(dock_widget)
            dock_widget.hide()
            tab_toolbox.toolbox_action_item.setChecked(False)

        tab_toolbox.tab_action_item.setChecked(False)
        tab_toolbox.toolbox_action_item.setChecked(False)
        tab_toolbox.set_display_state(TabToolbox.DS_HIDDEN)

    @pyqtSlot(Qt.DockWidgetArea)
    def set_preferred_dock_area(self, area):
        dock_widget = self.sender()
        tab_toolbox = dock_widget.tab_toolbox
        tab_toolbox.set_preferred_dock_area(area)

    def _rescan_devices(self):
        self._statusbar_label.setText("No inputdevice connected!")
        self._menu_devices.clear()
        self._active_device = ""
        self.joystickReader.stop_input()

        # for c in self._menu_mappings.actions():
        #    c.setEnabled(False)
        # devs = self.joystickReader.available_devices()
        # if (len(devs) > 0):
        #    self.device_discovery(devs)

    def _show_input_device_config_dialog(self):
        self.inputConfig = InputConfigDialogue(self.joystickReader)
        self.inputConfig.show()

    def _show_connect_dialog(self):
        self.logConfigDialogue.show()

    def _emergency_stop(self):
        # send disarming command
        if (self.uiState == UIState.CONNECTED):
            # Send both emergency stop and disarm
            # TODO krri Disarm?
            self.cf.loc.send_emergency_stop()

    def _update_battery(self, timestamp, data, logconf):
        self.batteryBar.setValue(int(data["pm.vbat"] * 1000))

        color = UiUtils.COLOR_BLUE
        # TODO firmware reports fully-charged state as 'Battery',
        # rather than 'Charged'
        if data["pm.state"] in [BatteryStates.CHARGING, BatteryStates.CHARGED]:
            color = UiUtils.COLOR_GREEN
        elif data["pm.state"] == BatteryStates.LOW_POWER:
            color = UiUtils.COLOR_RED

        self.batteryBar.setStyleSheet(UiUtils.progressbar_stylesheet(color))
        self._aff_volts.setText(("%.3f" % data["pm.vbat"]))

    def _connected(self):
        self.uiState = UIState.CONNECTED
        self._update_ui_state()

        Config().set("link_uri", str(self._connectivity_manager.get_interface()))

        lg = LogConfig("Battery", 1000)
        lg.add_variable("pm.vbat", "float")
        lg.add_variable("pm.state", "int8_t")
        try:
            self.cf.log.add_config(lg)
            lg.data_received_cb.add_callback(self.batteryUpdatedSignal.emit)
            lg.error_cb.add_callback(self._log_error_signal.emit)
            lg.start()
        except KeyError as e:
            logger.warning(str(e))

        mems = self.cf.mem.get_mems(MemoryElement.TYPE_DRIVER_LED)
        if len(mems) > 0:
            mems[0].write_data(self._led_write_done)

    def _disconnected(self):
        self.uiState = UIState.DISCONNECTED
        self._update_ui_state()

    def _connection_initiated(self):
        self.uiState = UIState.CONNECTING
        self._update_ui_state()

    def _led_write_done(self, mem, addr):
        logger.info("LED write done callback")

    def _logging_error(self, log_conf, msg):
        QMessageBox.about(self, "Log error", "Error when starting log config"
                                             " [{}]: {}".format(log_conf.name,
                                                                msg))

    def _connection_lost(self, linkURI, msg):
        if self.isActiveWindow():
            warningCaption = "Communication failure"
            error = "Connection lost to {}: {}".format(linkURI, msg)
            QMessageBox.critical(self, warningCaption, error)
            self.uiState = UIState.DISCONNECTED
            self._update_ui_state()

    def _connection_failed(self, linkURI, error):
        msg = "Failed to connect on {}: {}".format(linkURI, error)
        warningCaption = "Communication failure"
        QMessageBox.critical(self, warningCaption, msg)
        self.uiState = UIState.DISCONNECTED
        self._update_ui_state()

    def closeEvent(self, event):
        Config().save_file()
        self.cf.close_link()
        self.hide()

    def resizeEvent(self, event):
        Config().set("window_size", [event.size().width(),
                                     event.size().height()])

    def setConnectedStatusFromSim(self, is_connected):
        self.connectButton.setText("Disonnect" if is_connected else "Connect")

    def setPoseFromSim(self, x):
        self._debug(x)

    def _connect(self):

        if self.uiState == UIState.CONNECTED:
            if self.sim_client is not None:
                self.sim_client.disconnect()
            else:
                self.cf.close_link()
        elif self.uiState == UIState.CONNECTING:
            self.cf.close_link()
            self.uiState = UIState.DISCONNECTED
            self._update_ui_state()
        else:

            interface = self._connectivity_manager.get_interface()

            if interface == "MulticopterSim":
                self.sim_client = MulticopterSimClient(self)
                if self.sim_client.connect():
                    self.uiState = UIState.CONNECTED
                else:
                    QMessageBox.warning(self, 
                        "Connection error",
                        "Did you start the server first?")

            else:
                self.cf.open_link(interface)

    def _scan(self, address):
        self.uiState = UIState.SCANNING
        self._update_ui_state()
        self.scanner.scanSignal.emit(address)

    def _scan_from_button(self, address):
        #
        # Below we check if we can open the Crazyradio device.
        # If it is there, but we have no permissions we inform the user, once,
        # about how to install the udev rules.
        #
        if not self._permission_warned:
            try:
                radio = cflib.crtp.radiodriver.RadioManager.open(0)
                radio.close()
            except usb.core.USBError as e:
                if e.errno == 13:  # Permission denied
                    link = "<a href='https://www.bitcraze.io/documentation/repository/crazyflie-lib-python/master/installation/usb_permissions/'>Install USB Permissions</a>" # noqa
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Information)
                    msg.setTextFormat(Qt.RichText)
                    msg.setText("Could not access Crazyradio")
                    msg.setInformativeText(link)
                    msg.setWindowTitle("Crazyradio permissions")
                    msg.exec()
                    self._permission_warned = True
            except Exception as e:
                # For other Crazyradio exceptions (for instance if it's not attached)
                # ignore and keep scanning other link drivers.
                logger.warning(e)

        self._scan(address)

    def _display_input_device_error(self, error):
        self.cf.close_link()
        QMessageBox.critical(self, "Input device error", error)

    def _mux_selected(self, checked):
        """Called when a new mux is selected. The menu item contains a
        reference to the raw mux object as well as to the associated device
        sub-nodes"""
        if not checked:
            (mux, sub_nodes) = self.sender().data()
            for s in sub_nodes:
                s.setEnabled(False)
        else:
            (mux, sub_nodes) = self.sender().data()
            for s in sub_nodes:
                s.setEnabled(True)
            self.joystickReader.set_mux(mux=mux)

            # Go though the tree and select devices/mapping that was
            # selected before it was disabled.
            for role_node in sub_nodes:
                for dev_node in role_node.children():
                    if type(dev_node) is QAction and dev_node.isChecked():
                        dev_node.toggled.emit(True)

            self._update_input_device_footer()

    def _get_dev_status(self, device):
        msg = "{}".format(device.name)
        if device.supports_mapping:
            map_name = "No input mapping"
            if device.input_map:
                map_name = device.input_map_name
            msg += " ({})".format(map_name)
        return msg

    def _update_input_device_footer(self):
        """Update the footer in the bottom of the UI with status for the
        input device and its mapping"""

        msg = ""

        if len(self.joystickReader.available_devices()) > 0:
            mux = self.joystickReader._selected_mux
            msg = "Using {} mux with ".format(mux.name)
            for key in list(mux._devs.keys())[:-1]:
                if mux._devs[key]:
                    msg += "{}, ".format(self._get_dev_status(mux._devs[key]))
                else:
                    msg += "N/A, "
            # Last item
            key = list(mux._devs.keys())[-1]
            if mux._devs[key]:
                msg += "{}".format(self._get_dev_status(mux._devs[key]))
            else:
                msg += "N/A"
        else:
            msg = "No input device found"
        self._statusbar_label.setText(msg)

    def _inputdevice_selected(self, checked):
        """Called when a new input device has been selected from the menu. The
        data in the menu object is the associated map menu (directly under the
        item in the menu) and the raw device"""
        (map_menu, device, mux_menu) = self.sender().data()
        if not checked:
            if map_menu:
                map_menu.setEnabled(False)
                # Do not close the device, since we don't know exactly
                # how many devices the mux can have open. When selecting a
                # new mux the old one will take care of this.
        else:
            if map_menu:
                map_menu.setEnabled(True)

            (mux, sub_nodes) = mux_menu.data()
            for role_node in sub_nodes:
                for dev_node in role_node.children():
                    if type(dev_node) is QAction and dev_node.isChecked():
                        if device.id == dev_node.data()[1].id \
                                and dev_node is not self.sender():
                            dev_node.setChecked(False)

            role_in_mux = str(self.sender().parent().title()).strip()
            logger.info("Role of {} is {}".format(device.name,
                                                  role_in_mux))

            Config().set("input_device", str(device.name))

            self._mapping_support = self.joystickReader.start_input(
                device.name,
                role_in_mux)
        self._update_input_device_footer()

    def _inputconfig_selected(self, checked):
        """Called when a new configuration has been selected from the menu. The
        data in the menu object is a reference to the device QAction in parent
        menu. This contains a reference to the raw device."""
        if not checked:
            return

        selected_mapping = str(self.sender().text())
        device = self.sender().data().data()[1]
        self.joystickReader.set_input_map(device.name, selected_mapping)
        self._update_input_device_footer()

    def device_discovery(self, devs):
        """Called when new devices have been added"""
        for menu in self._all_role_menus:
            role_menu = menu["rolemenu"]
            mux_menu = menu["muxmenu"]
            dev_group = QActionGroup(role_menu)
            dev_group.setExclusive(True)
            for d in devs:
                dev_node = QAction(d.name, role_menu, checkable=True,
                                   enabled=True)
                role_menu.addAction(dev_node)
                dev_group.addAction(dev_node)
                dev_node.toggled.connect(self._inputdevice_selected)

                map_node = None
                if d.supports_mapping:
                    map_node = QMenu("    Input map", role_menu, enabled=False)
                    map_group = QActionGroup(role_menu)
                    map_group.setExclusive(True)
                    # Connect device node to map node for easy
                    # enabling/disabling when selection changes and device
                    # to easily enable it
                    dev_node.setData((map_node, d))
                    for c in ConfigManager().get_list_of_configs():
                        node = QAction(c, map_node, checkable=True,
                                       enabled=True)
                        node.toggled.connect(self._inputconfig_selected)
                        map_node.addAction(node)
                        # Connect all the map nodes back to the device
                        # action node where we can access the raw device
                        node.setData(dev_node)
                        map_group.addAction(node)
                        # If this device hasn't been found before, then
                        # select the default mapping for it.
                        if d not in self._available_devices:
                            last_map = Config().get("device_config_mapping")
                            if d.name in last_map and last_map[d.name] == c:
                                node.setChecked(True)
                    role_menu.addMenu(map_node)
                dev_node.setData((map_node, d, mux_menu))

        # Update the list of what devices we found
        # to avoid selecting default mapping for all devices when
        # a new one is inserted
        self._available_devices = ()
        for d in devs:
            self._available_devices += (d,)

        # Only enable MUX nodes if we have enough devies to cover
        # the roles
        for mux_node in self._all_mux_nodes:
            (mux, sub_nodes) = mux_node.data()
            if len(mux.supported_roles()) <= len(self._available_devices):
                mux_node.setEnabled(True)

        # TODO: Currently only supports selecting default mux
        if self._all_mux_nodes[0].isEnabled():
            self._all_mux_nodes[0].setChecked(True)

        # If the previous length of the available devies was 0, then select
        # the default on. If that's not available then select the first
        # on in the list.
        # TODO: This will only work for the "Normal" mux so this will be
        #       selected by default
        if Config().get("input_device") in [d.name for d in devs]:
            for dev_menu in self._all_role_menus[0]["rolemenu"].actions():
                if dev_menu.text() == Config().get("input_device"):
                    dev_menu.setChecked(True)
        else:
            # Select the first device in the first mux (will always be "Normal"
            # mux)
            self._all_role_menus[0]["rolemenu"].actions()[0].setChecked(True)
            logger.info("Select first device")

        self._update_input_device_footer()

    def _open_config_folder(self):
        QDesktopServices.openUrl(
            QUrl("file:///" +
                 QDir.toNativeSeparators(cfclient.config_path)))

    def closeAppRequest(self):
        self.close()
        sys.exit(0)


class ScannerThread(QThread):

    scanSignal = pyqtSignal(object)
    interfaceFoundSignal = pyqtSignal(object)

    def __init__(self):
        QThread.__init__(self)
        self.moveToThread(self)
        self.scanSignal.connect(self.scan)

    def scan(self, address):
        self.interfaceFoundSignal.emit(cflib.crtp.scan_interfaces(address))
