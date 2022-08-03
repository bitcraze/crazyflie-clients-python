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
Superclass for all tabs that implements common functions.
"""

import logging

from PyQt5 import QtWidgets
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtCore import Qt

from cfclient.utils.config import Config

__author__ = 'Bitcraze AB'
__all__ = ['TabToolbox']

logger = logging.getLogger(__name__)


class TabToolbox(QtWidgets.QWidget):
    """Superclass for all tabs that implements common functions."""

    CONF_KEY_TABS = "open_tabs"

    # Display states
    DS_HIDDEN = 0
    DS_TAB = 1
    DS_TOOLBOX = 2

    def __init__(self, helper, tab_toolbox_name):
        super(TabToolbox, self).__init__()
        self._helper = helper
        self.tab_toolbox_name = tab_toolbox_name

        # Dock widget for toolbox behavior
        self.dock_widget = self.MyDockWidget(tab_toolbox_name)
        self.dock_widget.tab_toolbox = self

        self.display_state = self.DS_HIDDEN

    def get_tab_toolbox_name(self):
        """Return the name that will be shown in the tab or toolbox"""
        return self.tab_toolbox_name

    def is_visible(self):
        return self.display_state != self.DS_HIDDEN

    # Override in implementation class if required
    def preferred_dock_area(self):
        return Qt.RightDockWidgetArea

    def _add_to_tab_config(self, name):
        tab_config = self.read_tab_config()
        if name not in tab_config:
            tab_config.append(name)
            self._store_tab_config(tab_config)

    def _remove_from_tab_config(self, name):
        tab_config = self.read_tab_config()
        if name in tab_config:
            tab_config.remove(name)
            self._store_tab_config(tab_config)

    @staticmethod
    def read_tab_config():
        tab_config = []
        try:
            tab_config = Config().get(TabToolbox.CONF_KEY_TABS).split(",")
        except KeyError:
            logger.warning("No tab config found")

        return tab_config

    def _store_tab_config(self, tab_config):
        Config().set(self.CONF_KEY_TABS, ','.join(tab_config))

    class MyDockWidget(QtWidgets.QDockWidget):
        closed = pyqtSignal()

        def closeEvent(self, event):
            super(TabToolbox.MyDockWidget, self).closeEvent(event)
            self.closed.emit()
