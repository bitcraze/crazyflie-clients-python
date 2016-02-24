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
The about dialog.
"""
import sys

import cfclient
import cflib.crtp
from PyQt4 import Qt
from PyQt4 import QtCore
from PyQt4 import QtGui
from PyQt4 import uic
from PyQt4.Qt import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *

__author__ = 'Bitcraze AB'
__all__ = ['AboutDialog']

(about_widget_class,
 about_widget_base_class) = (uic.loadUiType(sys.path[0] +
                                            '/cfclient/ui/dialogs/about.ui'))

DEBUG_INFO_FORMAT = """
<b>Cfclient</b><br>
Cfclient version: {version}<br>
System: {system}<br>
Python: {pmajor}.{pminor}.{pmicro}<br>
<br>
<b>Interface status</b><br>
{interface_status}
<br>
<b>Input readers</b><br>
{input_readers}
<br>
<b>Input devices</b><br>
{input_devices}
<br>
<b>Crazyflie</b><br>
Connected: {uri}<br>
Firmware: {firmware}<br>
<b>Sensors found</b><br>
{imu_sensors}
<b>Sensors tests</b><br>
{imu_sensor_tests}
"""

INTERFACE_FORMAT = "{}: {}<br>"
INPUT_READER_FORMAT = "{} ({} devices connected)<br>"
DEVICE_FORMAT = "{}: ({}) {}<br>"
IMU_SENSORS_FORMAT = "{}: {}<br>"
SENSOR_TESTS_FORMAT = "{}: {}<br>"
FIRMWARE_FORMAT = "{:x}{:x} ({})"

CREDITS_FORMAT = """
<b>Contributions</b><br>
{contribs}
<br><br>
<b>Used libraries</b><br>
<a href="http://qt-project.org/">QT</a><br>
<a href="http://www.riverbankcomputing.co.uk/software/pyqt/intro">PyQT</a><br>
<a href="http://pysdl2.readthedocs.org">PySDL2</a><br>
<a href="http://www.pyqtgraph.org/">PyQtGraph</a><br>
<a href="http://marble.kde.org/">KDE Marble</a><br>
<a href="http://sourceforge.net/projects/pyusb/">PyUSB</a><br>
<a href="http://www.python.org/">Python</a><br>
"""


class AboutDialog(QtGui.QWidget, about_widget_class):
    _disconnected_signal = pyqtSignal(str)

    """Crazyflie client About box for debugging and information"""

    def __init__(self, helper, *args):
        super(AboutDialog, self).__init__(*args)
        self.setupUi(self)
        self._close_button.clicked.connect(self.close)
        self._name_label.setText(
            self._name_label.text().replace('#version#', cfclient.VERSION))

        self._interface_text = ""
        self._imu_sensors_text = ""
        self._imu_sensor_test_text = ""
        self._uri = None
        self._fw_rev0 = None
        self._fw_rev1 = None
        self._fw_modified = None
        self._helper = helper

        helper.cf.param.add_update_callback(
            group="imu_sensors", cb=self._imu_sensors_update)
        helper.cf.param.add_update_callback(
            group="imu_tests", cb=self._imu_sensor_tests_update)
        helper.cf.param.add_update_callback(
            group="firmware", cb=self._firmware_update)
        helper.cf.connected.add_callback(self._connected)

        self._disconnected_signal.connect(self._disconnected)
        helper.cf.disconnected.add_callback(self._disconnected_signal.emit)

        # Open the Credits file and show it in the UI
        credits = ""
        try:
            with open("CREDITS.txt", 'r') as f:
                for line in f:
                    credits += "{}<br>".format(line)
        except IOError:
            credits = ""

        self._credits.setHtml(
            CREDITS_FORMAT.format(contribs=credits)
        )

    def showEvent(self, event):
        """Event when the about box is shown"""
        self._interface_text = ""
        interface_status = cflib.crtp.get_interfaces_status()
        for key in list(interface_status.keys()):
            self._interface_text += INTERFACE_FORMAT.format(
                key, interface_status[key])
        firmware = None

        self._device_text = ""
        devs = self._helper.inputDeviceReader.available_devices()
        for d in devs:
            self._device_text += DEVICE_FORMAT.format(
                d.reader_name, d.id, d.name)
        if len(self._device_text) == 0:
            self._device_text = "None<br>"

        self._input_readers_text = ""
        # readers = self._helper.inputDeviceReader.getAvailableDevices()
        for reader in cfclient.utils.input.inputreaders.initialized_readers:
            self._input_readers_text += INPUT_READER_FORMAT.format(
                reader.name, len(reader.devices()))
        if len(self._input_readers_text) == 0:
            self._input_readers_text = "None<br>"

        if self._uri:
            firmware = FIRMWARE_FORMAT.format(
                self._fw_rev0,
                self._fw_rev1,
                "MODIFIED" if self._fw_modified else "CLEAN")
        self._debug_out.setHtml(
            DEBUG_INFO_FORMAT.format(
                version=cfclient.VERSION,
                system=sys.platform,
                pmajor=sys.version_info.major,
                pminor=sys.version_info.minor,
                pmicro=sys.version_info.micro,
                interface_status=self._interface_text,
                input_devices=self._device_text,
                input_readers=self._input_readers_text,
                uri=self._uri,
                firmware=firmware,
                imu_sensors=self._imu_sensors_text,
                imu_sensor_tests=self._imu_sensor_test_text))

    def _connected(self, uri):
        """Callback when Crazyflie is connected"""
        self._uri = uri

    def _firmware_update(self, name, value):
        """Callback for firmware parameters"""
        if "revision0" in name:
            self._fw_rev0 = eval(value)
        if "revision1" in name:
            self._fw_rev1 = eval(value)
        if "modified" in name:
            self._fw_modified = eval(value)

    def _imu_sensors_update(self, name, value):
        """Callback for sensor found parameters"""
        param = name[name.index('.') + 1:]
        if param not in self._imu_sensors_text:
            self._imu_sensors_text += IMU_SENSORS_FORMAT.format(
                param, eval(value))

    def _imu_sensor_tests_update(self, name, value):
        """Callback for sensor test parameters"""
        param = name[name.index('.') + 1:]
        if param not in self._imu_sensor_test_text:
            self._imu_sensor_test_text += SENSOR_TESTS_FORMAT.format(
                param, eval(value))

    def _disconnected(self, uri):
        """Callback for Crazyflie disconnected"""
        self._interface_text = ""
        self._imu_sensors_text = ""
        self._imu_sensor_test_text = ""
        self._uri = None
        self._fw_rev1 = None
        self._fw_rev0 = None
        self._fw_modified = None
