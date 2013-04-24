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
Connection dialogue that will list available Crazyflies and the user can choose which to connect to.
"""

__author__ = 'Bitcraze AB'
__all__ = ['ConnectionDialogue']

import sys

from PyQt4 import Qt, QtCore, QtGui, uic
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qt import *

import cflib.crtp

connect_widget_class, connect_widget_base_class = uic.loadUiType(sys.path[0] + '/cfclient/ui/dialogs/connectiondialogue.ui')

class ConnectDialogue(QtGui.QWidget, connect_widget_class):

    # Outgoing signal for connecting a Crazyflie
    requestConnectionSignal = pyqtSignal(str)

    def __init__(self, *args):
        super(ConnectDialogue, self).__init__(*args)
        self.setupUi(self)
        
        self.scanner = ScannerThread()
        self.scanner.start()

        # Connect signals to slots
        self.connectButton.clicked.connect(self.openConnection)
        self.scanButton.clicked.connect(self.rescan)
        self.cancelButton.clicked.connect(self.cancel)
        self.interfaceList.itemDoubleClicked.connect(self.interfaceSelected)
        self.scanner.interfaceFoundSignal.connect(self.foundInterfaces)
        self.box = None
        self.setWindowModality(Qt.ApplicationModal)

        self.availableInterfaces = []

    def rescan(self):
        self.interfaceList.clear()
        self.interfaceList.addItem("Scanning...")
        self.scanButton.setEnabled(False)
        self.cancelButton.setEnabled(False)
        self.connectButton.setEnabled(False)
        self.scanner.scanSignal.emit()

    def foundInterfaces(self, interfaces):
        self.interfaceList.clear()
        self.availableInterfaces = interfaces
        for i in interfaces:
            if (len(i[1]) > 0):
                self.interfaceList.addItem("%s - %s" % (i[0], i[1]))
            else:
                self.interfaceList.addItem(i[0])
        self.scanButton.setEnabled(True)
        self.cancelButton.setEnabled(True)
        self.connectButton.setEnabled(True)

    def interfaceSelected(self, listItem):
        self.requestConnectionSignal.emit(self.availableInterfaces[self.interfaceList.currentRow()][0])
        self.close()

    def openConnection(self):
        self.interfaceSelected(self.interfaceList.currentItem())

    def cancel(self):
        self.close()

    def showEvent(self, ev):
        self.rescan()

class ScannerThread(QThread):

    scanSignal = pyqtSignal()
    interfaceFoundSignal = pyqtSignal(object)

    def __init__(self):
        QThread.__init__(self)
        self.moveToThread(self)
        self.scanSignal.connect(self.scan)

    @pyqtSlot()
    def scan(self):
        self.interfaceFoundSignal.emit(cflib.crtp.scan_interfaces())

        
