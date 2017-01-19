#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2017 Bitcraze AB
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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#  02110-1301, USA.

"""
Shows data for the Loco Positioning system
"""

import logging

from PyQt4 import uic
from PyQt4.QtCore import pyqtSignal
from PyQt4.QtGui import QMessageBox

import cfclient
from cfclient.ui.tab import Tab

from cfclient.utils.config import Config
from cflib.crazyflie.log import LogConfig

__author__ = 'Bitcraze AB'
__all__ = ['LocoPositioningTab']

logger = logging.getLogger(__name__)

locopositioning_tab_class = uic.loadUiType(
    cfclient.module_path + "/ui/tabs/locopositioning_tab.ui")[0]


class Anchor:
    def __init__(self, x=0.0, y=0.0, z=0.0, distance=0.0):
        self.x = x
        self.y = y
        self.z = z
        self.distance = distance

    def set_position(self, axis, value):
        """Sets one coordinate of the position. axis is represented by the
           characters 'x', 'y' or 'z'"""
        if axis in {'x', 'y', 'z'}:
            setattr(self, axis, value)
        else:
            raise ValueError('"{}" is an unknown axis'.format(axis))


class LocoPositioningTab(Tab, locopositioning_tab_class):
    """Tab for plotting Loco Positioning data"""

    # Update period in ms
    UPDATE_PERIOD = 100

    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)
    _log_error_signal = pyqtSignal(object, str)
    _anchor_range_signal = pyqtSignal(int, object, object)
    _position_signal = pyqtSignal(int, object, object)

    def __init__(self, tabWidget, helper, *args):
        super(LocoPositioningTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Loco Positioning"
        self.menuName = "Loco Positioning Tab"
        self.tabWidget = tabWidget

        self._helper = helper

        self._anchors = {}
        self._position = []
        self._clear_state()

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._connected_signal.connect(self._connected)
        self._disconnected_signal.connect(self._disconnected)
        self._anchor_range_signal.connect(self._anchor_range_received)
        self._position_signal.connect(self._position_received)

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(
            self._connected_signal.emit)

        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

    def _clear_state(self):
        self._anchors = {}
        self._position = [0.0, 0.0, 0.0]

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        logger.debug("Crazyflie connected to {}".format(link_uri))

        self._clear_state()

        try:
            self._register_logblock(
                "LoPoTab0",
                [
                    ("ranging.distance1", "float"),
                    ("ranging.distance2", "float"),
                    ("ranging.distance3", "float"),
                    ("ranging.distance4", "float"),
                ],
                self._anchor_range_signal.emit,
                self._log_error_signal.emit)

            self._register_logblock(
                "LoPoTab1",
                [
                    ("ranging.distance5", "float"),
                    ("ranging.distance6", "float"),
                    ("ranging.distance7", "float"),
                    ("ranging.distance8", "float"),
                ],
                self._anchor_range_signal.emit,
                self._log_error_signal.emit),
            self._register_logblock(
                "LoPoTab2",
                [
                    ("kalman.stateX", "float"),
                    ("kalman.stateY", "float"),
                    ("kalman.stateZ", "float"),
                ],
                self._position_signal.emit,
                self._log_error_signal.emit),
        except KeyError as e:
            logger.warning(str(e))
        except AttributeError as e:
            logger.warning(str(e))

        self._subscribe_to_parameters(self._helper.cf)

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        logger.debug("Crazyflie disconnected from {}".format(link_uri))
        self._update_graphics()

    def _register_logblock(self, logblock_name, variables, data_cb, error_cb):
        """Register log data to listen for. One logblock can contain a limited
        number of parameters (6 for floats)."""
        lg = LogConfig(logblock_name, self.UPDATE_PERIOD)
        for variable in variables:
            lg.add_variable(variable[0], variable[1])

        self._helper.cf.log.add_config(lg)
        lg.data_received_cb.add_callback(data_cb)
        lg.error_cb.add_callback(error_cb)
        lg.start()
        return lg

    def _anchor_range_received(self, timestamp, data, logconf):
        """Callback from the logging system when a range is updated."""
        is_updated = False
        for name, value in data.items():
            valid, anchor_number = self._parse_range_param_name(name)
            if valid:
                self._get_anchor(anchor_number).distance = value
                is_updated = True

        if is_updated:
            self._update_graphics()

    def _position_received(self, timestamp, data, logconf):
        """Callback from the logging system when the position is updated."""
        is_updated = False
        for name, value in data.items():
            valid, axis = self._parse_position_param_name(name)
            if valid:
                self._position[axis] = value
                is_updated = True

        if is_updated:
            self._update_graphics()

    def _logging_error(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""
        QMessageBox.about(self, "LocoPositioningTab error",
                          "Error when using log config",
                          " [{0}]: {1}".format(log_conf.name, msg))

    def _subscribe_to_parameters(self, crazyflie):
        """Get anchor positions from the TOC and set up subscription for
        changes in positions"""
        group = 'anchorpos'
        toc = crazyflie.param.toc.toc
        anchor_group = toc[group]
        for name in anchor_group.keys():
            crazyflie.param.add_update_callback(
                group=group, name=name, cb=self._anchor_parameter_updated)

    def _anchor_parameter_updated(self, name, value):
        """Callback from the param layer when a parameter has been updated"""
        self.set_anchor_position(name, value)

    def set_anchor_position(self, name, value):
        """Set the position of an anchor. If the anchor does not exist yet in
        the anchor dictionary, create it."""
        valid, anchor_number, axis = self._parse_anchor_parameter_name(name)
        if valid:
            self._get_anchor(anchor_number).set_position(axis, value)
            self._update_graphics()

    def _parse_range_param_name(self, name):
        """Parse a parameter name for a ranging distance and return the number
           of the anchor. The name is on the format 'ranging.distance4' """
        valid = False
        anchor = 0
        if name.startswith('ranging.distance'):
            anchor = int(name[-1])
            valid = True
        return (valid, anchor)

    def _parse_position_param_name(self, name):
        """Parse a parameter name for a position and return the
           axis (0=x, 1=y, 2=z).
           The param name is on the format 'kalman.stateY' """
        valid = False
        axis = 0
        if name.startswith('kalman.state'):
            axis = {'X': 0, 'Y': 1, 'Z': 2}[name[-1]]
            valid = True
        return (valid, axis)

    def _parse_anchor_parameter_name(self, name):
        """Parse an anchor position parameter name and extract anchor number
           and axis. The format is 'anchorpos.anchor0y'."""
        valid = False
        anchor = 0
        axis = 0
        if name.startswith('anchorpos.anchor'):
            anchor = int(name[16])
            axis = name[17]
            valid = True
        return (valid, anchor, axis)

    def _get_anchor(self, anchor_number):
        if anchor_number not in self._anchors:
            self._anchors[anchor_number] = Anchor()
        return self._anchors[anchor_number]

    def _update_graphics(self):
        pass
        # TODO krri Implement
