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

about_widget_class, about_widget_base_class = uic.loadUiType(sys.path[0] + '/cfclient/ui/dialogs/about.ui')

class AboutDialog(QtGui.QWidget, about_widget_class):

    def __init__(self, helper, *args):
        super(AboutDialog, self).__init__(*args)
        self.setupUi(self)
        self._close_button.clicked.connect(self.close)

    def showEvent(self, ev):
        s = "Debug info here"
        self._debug_out.setText(s)
