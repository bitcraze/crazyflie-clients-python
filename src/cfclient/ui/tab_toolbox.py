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
from PyQt5.QtCore import pyqtSlot

from cfclient.utils.config import Config

__author__ = 'Bitcraze AB'
__all__ = ['TabToolbox']

logger = logging.getLogger(__name__)


class TabToolbox(QtWidgets.QWidget):
    """Superclass for all tabs that implements common functions."""

    def __init__(self, tab_widget, helper, tab_toolbox_name):
        super(TabToolbox, self).__init__()
        self.tab_widget = tab_widget
        self._helper = helper
        self.tab_toolbox_name = tab_toolbox_name

    @pyqtSlot(bool)
    def toggleVisibility(self, checked):
        """Show or hide the tab."""
        if checked:
            self.tab_widget.addTab(self, self.tab_toolbox_name)
            self._add_to_config(self.tab_toolbox_name)
        else:
            self.tab_widget.removeTab(self.tab_widget.indexOf(self))
            self._remove_from_config(self.tab_toolbox_name)

    def get_tab_toolbox_name(self):
        """Return the name of the tab that will be shown in the tab"""
        return self.tab_toolbox_name

    def is_visible(self):
        return self.tab_widget.currentWidget() == self

    def _add_to_config(self, name):
        tab_config = self.read_tab_config()
        if name not in tab_config:
            tab_config.append(name)
        self._store_tab_config(tab_config)

    def _remove_from_config(self, name):
        tab_config = self.read_tab_config()
        tab_config.remove(name)
        self._store_tab_config(tab_config)

    @staticmethod
    def read_tab_config():
        tab_config = []
        try:
            tab_config = Config().get("open_tabs").split(",")
        except KeyError:
            logger.warning("No tab config found")

        return tab_config

    def _store_tab_config(self, tab_config):
        Config().set("open_tabs", ','.join(tab_config))
