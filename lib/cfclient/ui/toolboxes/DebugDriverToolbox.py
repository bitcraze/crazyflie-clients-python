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
Toolbox used to interact with the DebugDriver using a designated port. It's
intended to be used for debugging.
"""

__author__ = 'Bitcraze AB'
__all__ = ['DebugDriverToolbox']

import time
import sys

import struct
from cflib.crtp.crtpstack import CRTPPacket, CRTPPort

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import Qt, pyqtSlot, pyqtSignal, QThread, SIGNAL

debugdriver_tab_class = uic.loadUiType(
                           sys.path[0] +
                           "/cfclient/ui/toolboxes/debugDriverToolbox.ui")[0]


class DebugDriverToolbox(QtGui.QWidget, debugdriver_tab_class):
    """Used to interact with the DebugDriver toolbox"""
    connectionDoneSignal = pyqtSignal(str)
    disconnectedSignal = pyqtSignal(str)

    def __init__(self, helper, *args):
        super(DebugDriverToolbox, self).__init__(*args)
        self.setupUi(self)

        self.helper = helper

        # Connected / disconnected signals
        self.helper.cf.connectSetupFinished.add_callback(
                                             self.connectionDoneSignal.emit)
        self.connectionDoneSignal.connect(self.connectionDone)
        self.helper.cf.disconnected.add_callback(self.disconnectedSignal.emit)
        self.disconnectedSignal.connect(self.disconnected)

        self.linkQuality.valueChanged.connect(self.linkQualityChanged)
        self.forceDisconnect.pressed.connect(self.forceDisconnecPressed)

    def forceDisconnecPressed(self):
        if (self.helper.cf.link != None):
            p = CRTPPacket()
            p.set_header(CRTPPort.DEBUGDRIVER, 0)
            p.data = struct.pack('<B', 1)  # Force disconnect
            self.helper.cf.send_packet(p)

    def linkQualityChanged(self, value):
        if (self.helper.cf.link != None):
            p = CRTPPacket()
            p.set_header(CRTPPort.DEBUGDRIVER, 0)
            p.data = struct.pack('<BB', 0, value)  # Set link quality
            self.helper.cf.send_packet(p)

    def disconnected(self, linkURI):
        if ("debug" in linkURI):
            self.linkQuality.setEnabled(False)
            self.forceDisconnect.setEnabled(False)

    def connectionDone(self, linkURI):
        if ("debug" in linkURI):
            self.linkQuality.setEnabled(True)
            self.forceDisconnect.setEnabled(True)

    def getName(self):
        return 'Debug driver'

    def getTabName(self):
        return 'Debug driver'

    def enable(self):
        return

    def disable(self):
        return

    def preferedDockArea(self):
        return Qt.RightDockWidgetArea

