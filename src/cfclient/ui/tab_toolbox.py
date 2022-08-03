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
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCloseEvent

from cfclient.utils.config import Config

__author__ = 'Bitcraze AB'
__all__ = ['TabToolbox']

logger = logging.getLogger(__name__)


class TabToolbox(QtWidgets.QWidget):
    """Superclass for all tabs that implements common functions."""

    CONF_KEY_OPEN_TABS = "open_tabs"
    CONF_KEY_OPEN_TOOLBOXES = "open_toolboxes"
    CONF_KEY_TOOLBOX_AREAS = "toolbox_areas"

    # Display states
    DS_HIDDEN = 0
    DS_TAB = 1
    DS_TOOLBOX = 2

    def __init__(self, helper, tab_toolbox_name):
        super(TabToolbox, self).__init__()
        self._helper = helper
        self.tab_toolbox_name = tab_toolbox_name

        # Dock widget for toolbox behavior
        self.dock_widget = self.ClosingDockWidget(tab_toolbox_name)
        self.dock_widget.tab_toolbox = self

        self._display_state = self.DS_HIDDEN

        self._dock_area = self._get_toolbox_area_config()

    def get_tab_toolbox_name(self):
        """Return the name that will be shown in the tab or toolbox"""
        return self.tab_toolbox_name

    def is_visible(self):
        return self._display_state != self.DS_HIDDEN

    def get_display_state(self):
        return self._display_state

    def set_display_state(self, new_display_state):
        if new_display_state != self._display_state:
            self._display_state = new_display_state
            self._update_open_config(new_display_state)

            if new_display_state == self.DS_HIDDEN:
                self.disable()
            else:
                self.enable()

    def preferred_dock_area(self):
        return self._dock_area

    def set_preferred_dock_area(self, area):
        self._dock_area = area
        self._store_toolbox_area_config(area)

    def enable(self):
        pass

    def disable(self):
        pass

    @classmethod
    def read_open_tab_config(cls):
        return cls._read_open_config(TabToolbox.CONF_KEY_OPEN_TABS)

    @classmethod
    def read_open_toolbox_config(cls):
        return TabToolbox._read_open_config(TabToolbox.CONF_KEY_OPEN_TOOLBOXES)

    @classmethod
    def _read_open_config(cls, key):
        config = []
        try:
            value = Config().get(key)
            # Python will return a list of an empty string if value is empty, filter it
            config = list(filter(None, value.split(",")))
        except KeyError:
            logger.info(f'No config found for {key}')

        return config

    def _update_open_config(self, display_state):
        if display_state == self.DS_HIDDEN:
            self._remove_from_open_config(TabToolbox.CONF_KEY_OPEN_TABS)
            self._remove_from_open_config(TabToolbox.CONF_KEY_OPEN_TOOLBOXES)
        elif display_state == self.DS_TAB:
            self._add_to_open_config(TabToolbox.CONF_KEY_OPEN_TABS)
            self._remove_from_open_config(TabToolbox.CONF_KEY_OPEN_TOOLBOXES)
        elif display_state == self.DS_TOOLBOX:
            self._remove_from_open_config(TabToolbox.CONF_KEY_OPEN_TABS)
            self._add_to_open_config(TabToolbox.CONF_KEY_OPEN_TOOLBOXES)

    def _add_to_open_config(self, key):
        config = self._read_open_config(key)
        name = self.tab_toolbox_name

        if name not in config:
            config.append(name)
            self._store_open_config(key, config)

    def _remove_from_open_config(self, key):
        config = self._read_open_config(key)
        name = self.tab_toolbox_name

        if name in config:
            config.remove(name)
            self._store_open_config(key, config)

    def _store_open_config(self, key, config):
        value = ','.join(config)
        Config().set(key, value)

    def _get_toolbox_area_config(self):
        result = Qt.RightDockWidgetArea

        config = self._read_toolbox_area_config()

        if self.tab_toolbox_name in config.keys():
            result = config[self.tab_toolbox_name]

        return result

    def _store_toolbox_area_config(self, area):
        config = self._read_toolbox_area_config()
        config[self.tab_toolbox_name] = area
        self._write_toolbox_area_config(config)

    def _read_toolbox_area_config(self):
        composite_config = []
        try:
            key = self.CONF_KEY_TOOLBOX_AREAS
            value = Config().get(key)
            # Python will return a list of an empty string if value is empty, filter it
            composite_config = list(filter(None, value.split(",")))
        except KeyError:
            logger.info(f'No config found for {key}')

        config = {}
        for composite in composite_config:
            try:
                parts = composite.split(':')
                config[parts[0]] = int(parts[1])
            except KeyError:
                logger.info(f'Can not understand config {composite}')

        return config

    def _write_toolbox_area_config(self, config):
        key = self.CONF_KEY_TOOLBOX_AREAS
        value = ','.join(map(lambda item: f'{item[0]}:{item[1]}', config.items()))
        Config().set(key, value)

    class ClosingDockWidget(QtWidgets.QDockWidget):
        closed = pyqtSignal()

        def closeEvent(self, event: QCloseEvent) -> None:
            super(TabToolbox.ClosingDockWidget, self).closeEvent(event)
            self.closed.emit()
