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

about_widget_class, about_widget_base_class = uic.loadUiType(sys.path[0] + '/cfclient/ui/dialogs/about.ui')

debuginfo = """
<b>Cfclient version:</b> {version}<br>
<b>System:</b> {system}<br>
<br>
<b>Interface status</b><br>
{interface_status}
"""

class AboutDialog(QtGui.QWidget, about_widget_class):

    def __init__(self, helper, *args):
        super(AboutDialog, self).__init__(*args)
        self.setupUi(self)
        self._close_button.clicked.connect(self.close)
        self._name_label.setText(self._name_label.text().replace('#version#', cfclient.VERSION))

    def showEvent(self, ev):
        status_text = ""
        interface_status = cflib.crtp.get_interfaces_status()
        for s in interface_status.keys():
            status_text += "<b>{}</b>: {}<br>\n".format(s, interface_status[s])
        self._debug_out.setHtml(debuginfo.format(version=cfclient.VERSION, 
                                                 system=sys.platform,
                                                 interface_status=status_text))

