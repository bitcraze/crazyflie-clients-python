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
This tab givies the user an interface where the regulation parameters for the
Crazyflie can be viewed and updated.
"""

__author__ = 'Bitcraze AB'
__all__ = ['RegulationTab']

import sys, time

from PyQt4 import QtCore, QtGui, uic
from PyQt4.QtCore import Qt, pyqtSlot, pyqtSignal, QThread, SIGNAL

from ui.tab import Tab

regulation_tab_class = uic.loadUiType("ui/tabs/regulationTab.ui")[0]

class RegulationTab(Tab, regulation_tab_class):
    """Show and update the regulation parameters in the Crazyflie"""
    paramUpdatedSignal = pyqtSignal(str, str)
    connectionDoneSignal = pyqtSignal(str)
    disconnectedSignal = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        super(RegulationTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Regulation"
        self.menuName = "Regulation"

        self.helper = helper
        self.tabWidget = tabWidget

        self.sendPID.clicked.connect(self.sendPIDValues)

        self.paramUpdatedSignal.connect(self.paramUpdated)

        self.helper.cf.connectSetupFinished.add_callback(self.connectionDoneSignal.emit)
        self.connectionDoneSignal.connect(self.connectionDone)
        self.helper.cf.disconnected.add_callback(self.disconnectedSignal.emit)
        self.disconnectedSignal.connect(self.disconnected)
        
        self.paramList = []
        self.paramList.append({"paramname":"rpid.prp", "spinner": self.rpRP})
        self.paramList.append({"paramname":"rpid.pyaw", "spinner": self.rpYaw})
        self.paramList.append({"paramname":"rpid.irp", "spinner": self.riRP})
        self.paramList.append({"paramname":"rpid.iyaw", "spinner": self.riYaw})
        self.paramList.append({"paramname":"rpid.drp", "spinner": self.rdRP})
        self.paramList.append({"paramname":"rpid.dyaw", "spinner": self.rdYaw})

        self.paramList.append({"paramname":"apid.prp", "spinner": self.apRP})
        self.paramList.append({"paramname":"apid.pyaw", "spinner": self.apYaw})
        self.paramList.append({"paramname":"apid.irp", "spinner": self.aiRP})
        self.paramList.append({"paramname":"apid.iyaw", "spinner": self.aiYaw})
        self.paramList.append({"paramname":"apid.drp", "spinner": self.adRP})
        self.paramList.append({"paramname":"apid.dyaw", "spinner": self.adYaw})

        # Add callbacks for all the parameters. No need to request fetch, will be done by ParamTocTab
        for p in self.paramList:
            self.helper.cf.param.add_update_callback(p["paramname"], self.paramUpdatedSignal.emit)

    def connectionDone(self):
        self.sendPID.setEnabled(True)

    def disconnected(self):
        self.sendPID.setEnabled(False)

    def paramUpdated(self, paramname, value):
        for p in self.paramList:
            if (p["paramname"] == paramname):
                p["spinner"].setValue(float(value))

    def sendPIDValues(self):
        # TODO: Handle exception for non-existant param toc entry        
        for p in self.paramList:
            self.helper.cf.param.set_value(p["paramname"], str(p["spinner"].value()))
       

