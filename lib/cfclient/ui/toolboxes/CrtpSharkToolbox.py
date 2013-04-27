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
Toolbox for showing packets that is sent via the communication link when debugging.
"""

__author__ = 'Bitcraze AB'
__all__ = ['CrtpSharkBoolbox']

import sys, time

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import Qt, pyqtSlot, pyqtSignal, QThread, SIGNAL

param_tab_class = uic.loadUiType(sys.path[0] + "/cfclient/ui/toolboxes/crtpSharkToolbox.ui")[0]

class CrtpSharkToolbox(QtGui.QWidget, param_tab_class):
    """Show packets that is sent vie the communication link"""
    nameModified = pyqtSignal()
    
    def __init__(self, helper, *args):
        super(CrtpSharkToolbox, self).__init__(*args)
        self.setupUi(self)

        self.helper = helper
        
        #Init the tree widget
        self.logTree.setHeaderLabels(['Port', 'Data'])
        
        #Connect GUI signals
        self.clearButton.clicked.connect(self.clearLog)
        
    def packetIncoming(self, pk):
        if self.masterCheck.isChecked():
           line = QtGui.QTreeWidgetItem()
        
           line.setData(0, Qt.DisplayRole, "(%d,%d,%d)" % ((pk.port>>6), pk.getTask(), pk.getNumber()))
           line.setData(1, Qt.DisplayRole, pk.data.__str__())
            
           self.logTree.addTopLevelItem(line)
           self.logTree.scrollToItem(line)
    
    @pyqtSlot()
    def clearLog(self):
        self.logTree.clear()
    
    def getName(self):
        return 'Crtp sniffer'
    
    def getTabName(self):
        return 'Crtp sniffer'
    
    def enable(self):
        self.helper.cf.receivedPacket.add_callback(self.packetIncoming)
    
    def disable(self):
        self.helper.cf.receivedPacket.remove_callback(self.packetIncoming)
    
    def preferedDockArea(self):
        return Qt.RightDockWidgetArea

