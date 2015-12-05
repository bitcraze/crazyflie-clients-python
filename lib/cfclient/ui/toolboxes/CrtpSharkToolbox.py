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
Toolbox for showing packets that is sent via the communication link when
debugging.
"""

import sys
import os

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import Qt, pyqtSlot, pyqtSignal, QThread, SIGNAL
from time import time

__author__ = 'Bitcraze AB'
__all__ = ['CrtpSharkBoolbox']

param_tab_class = uic.loadUiType(
    sys.path[0] + "/cfclient/ui/toolboxes/crtpSharkToolbox.ui")[0]


class CrtpSharkToolbox(QtGui.QWidget, param_tab_class):
    """Show packets that is sent vie the communication link"""
    nameModified = pyqtSignal()
    _incoming_packet_signal = pyqtSignal(object)
    _outgoing_packet_signal = pyqtSignal(object)

    def __init__(self, helper, *args):
        super(CrtpSharkToolbox, self).__init__(*args)
        self.setupUi(self)

        self.helper = helper

        # Init the tree widget
        self.logTree.setHeaderLabels(['ms', 'Direction', 'Port/Chan', 'Data'])

        # Connect GUI signals
        self.clearButton.clicked.connect(self.clearLog)
        self.saveButton.clicked.connect(self._save_data)

        self._incoming_packet_signal.connect(lambda p: self._packet("IN", p))
        self._outgoing_packet_signal.connect(lambda p: self._packet("OUT", p))
        self._ms_offset = int(round(time() * 1000))

        self._data = []

    def _packet(self, dir, pk):
        if self.masterCheck.isChecked():
            line = QtGui.QTreeWidgetItem()

            ms_diff = int(round(time() * 1000)) - self._ms_offset
            line.setData(0, Qt.DisplayRole, "%d" % ms_diff)
            line.setData(1, Qt.DisplayRole, "%s" % dir)
            line.setData(2, Qt.DisplayRole, "%d/%d" % (pk.port, pk.channel))
            line.setData(3, Qt.DisplayRole, pk.data.decode("UTF-8"))

            s = "%d, %s, %d/%d, %s" % (ms_diff, dir, pk.port, pk.channel,
                                       pk.data.decode("UTF-8"))
            self._data.append(s)

            self.logTree.addTopLevelItem(line)
            self.logTree.scrollToItem(line)

    @pyqtSlot()
    def clearLog(self):
        self.logTree.clear()
        self._data = []

    def getName(self):
        return 'Crtp sniffer'

    def getTabName(self):
        return 'Crtp sniffer'

    def enable(self):
        self.helper.cf.packet_received.add_callback(
            self._incoming_packet_signal.emit)
        self.helper.cf.packet_sent.add_callback(
            self._outgoing_packet_signal.emit)

    def disable(self):
        self.helper.cf.packet_received.remove_callback(
            self._incoming_packet_signal.emit)
        self.helper.cf.packet_sent.remove_callback(
            self._outgoing_packet_signal.emit)

    def preferedDockArea(self):
        return Qt.RightDockWidgetArea

    def _save_data(self):
        dir = os.path.join(sys.path[1], "logdata")
        fname = os.path.join(dir, "shark_data.csv")
        if not os.path.exists(dir):
            os.makedirs(dir)
        f = open(fname, 'w')
        for s in self._data:
            f.write("%s\n" % s)
        f.close()
