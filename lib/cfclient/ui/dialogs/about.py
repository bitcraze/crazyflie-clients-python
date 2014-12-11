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
The about dialog.
"""

__author__ = 'Bitcraze AB'
__all__ = ['AboutDialog']

import sys

from PyQt4 import Qt, QtCore, QtGui, uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qt import *

import cfclient

import cflib.crtp

(about_widget_class,
about_widget_base_class) = (uic.loadUiType(sys.path[0] +
                                           '/cfclient/ui/dialogs/about.ui'))

DEBUG_INFO_FORMAT = """
<b>Cfclient</b><br>
Cfclient version: {version}<br>
System: {system}<br>
<br>
<b>Interface status</b><br>
{interface_status}
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
IMU_SENSORS_FORMAT = "{}: {}<br>"
SENSOR_TESTS_FORMAT = "{}: {}<br>"
FIRMWARE_FORMAT = "{:x}{:x} ({})"

CREDITS_FORMAT = U"""
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

# This is temporary and will be fixed during the next release. It should
# be picked up from the CREDITS.txt file
CREDITS_NAMES = U"""
We are very greatful for all the contributions we have received for this project
and below is a list of users that have contributed to the crazyflie-pc-client.
Thanks! <br><br>

Allyn Bauer <br>
Anton Krasovsky <br>
Arnaud Taffanel <br>
Chadwick McHenry <br>
Daniel Lee <br>
David Benes <br>
Gina Häußge <br>
Jannis Redmann <br>
Marcus Eliasson <br>
Marlon Petry <br>
Mike Voytovich <br>
Philipp A. Mohrenweiser <br>
Surrender <br>
Thomas DE BONA <br>
Tobias Antonsson <br>
Tyler Anderson <br>
bitcraze <br>
cstanke <br>
danmark <br>
erget <br>
omwdunkley <br>

<br>
This list of names have been automatically generated using the following command
in the crazyflie-clients-python repository:<br>
git shortlog -s | cut -c8-
"""

class AboutDialog(QtGui.QWidget, about_widget_class):

    _disconnected_signal = pyqtSignal(str)

    """Crazyflie client About box for debugging and information"""
    def __init__(self, helper, *args):
        super(AboutDialog, self).__init__(*args)
        self.setupUi(self)
        self._close_button.clicked.connect(self.close)
        self._name_label.setText(
                             self._name_label.text().replace('#version#',
                                                             cfclient.VERSION))

        self._interface_text = ""
        self._imu_sensors_text = ""
        self._imu_sensor_test_text = ""
        self._uri = None 
        self._fw_rev0 = None
        self._fw_rev1 = None
        self._fw_modified = None

        helper.cf.param.add_update_callback(group="imu_sensors",
                                            cb=self._imu_sensors_update)
        helper.cf.param.add_update_callback(group="imu_tests",
                                            cb=self._imu_sensor_tests_update)
        helper.cf.param.add_update_callback(group="firmware",
                                            cb=self._firmware_update)
        helper.cf.connected.add_callback(self._connected)

        self._disconnected_signal.connect(self._disconnected)
        helper.cf.disconnected.add_callback(self._disconnected_signal.emit)

        self._credits.setHtml(
            CREDITS_FORMAT.format(contribs=CREDITS_NAMES)
        )

    def showEvent(self, event):
        """Event when the about box is shown"""
        self._interface_text = ""
        interface_status = cflib.crtp.get_interfaces_status()
        for key in interface_status.keys():
            self._interface_text += INTERFACE_FORMAT.format(key,
                                                    interface_status[key])
        firmware = None
        if self._uri:
            firmware = FIRMWARE_FORMAT.format(self._fw_rev0, self._fw_rev1,
                                "MODIFIED" if self._fw_modified else "CLEAN")
        self._debug_out.setHtml(
                DEBUG_INFO_FORMAT.format(version=cfclient.VERSION,
                                         system=sys.platform,
                                         interface_status=self._interface_text,
                                         uri = self._uri,
                                         firmware = firmware,
                                         imu_sensors=self._imu_sensors_text,
                                         imu_sensor_tests=
                                            self._imu_sensor_test_text))

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
        """Callback for sensor found paramters"""
        param = name[name.index('.') + 1:]
        if not param in self._imu_sensors_text:
            self._imu_sensors_text += IMU_SENSORS_FORMAT.format(param,
                                                                eval(value))

    def _imu_sensor_tests_update(self, name, value):
        """Callback for sensor test parameters"""
        param = name[name.index('.') + 1:]
        if not param in self._imu_sensor_test_text:
            self._imu_sensor_test_text += SENSOR_TESTS_FORMAT.format(param,
                                                                 eval(value))

    def _disconnected(self, uri):
        """Callback for Crazyflie disconnected"""
        self._interface_text = ""
        self._imu_sensors_text = ""
        self._imu_sensor_test_text = ""
        self._uri = None
        self._fw_rev1 = None
        self._fw_rev0 = None
        self._fw_modified = None
