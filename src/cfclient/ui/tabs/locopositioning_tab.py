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
from enum import Enum

from PyQt4 import uic
from PyQt4.QtCore import pyqtSignal, QTimer
from PyQt4.QtGui import QMessageBox

import cfclient
from cfclient.ui.tab import Tab

from cflib.crazyflie.log import LogConfig

import copy

__author__ = 'Bitcraze AB'
__all__ = ['LocoPositioningTab']

logger = logging.getLogger(__name__)

locopositioning_tab_class = uic.loadUiType(
    cfclient.module_path + "/ui/tabs/locopositioning_tab.ui")[0]

# Try the imports for PyQtGraph to see if it is installed
try:
    import pyqtgraph as pg
    from pyqtgraph import ViewBox  # noqa
    import pyqtgraph.console  # noqa
    import numpy as np  # noqa

    _pyqtgraph_found = True
except Exception:
    import traceback

    logger.warning("PyQtGraph (or dependency) failed to import:\n%s",
                   traceback.format_exc())
    _pyqtgraph_found = False


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


class AxisScaleStep:
    def __init__(self, from_view, from_axis, to_view, to_axis,
                 center_only=False):
        self.from_view = from_view.view
        self.from_axis = from_axis
        self.to_view = to_view.view
        self.to_axis = to_axis
        self.center_only = center_only


class PlotWrapper:
    XAxis = 0
    YAxis = 1
    _refs = []
    _change_lock = False

    axis_dict = {'x': 0, 'y': 1, 'z': 2}

    ANCHOR_BRUSH = (60, 60, 60)
    HIGHLIGHT_ANCHOR_BRUSH = (0, 255, 0)
    POSITION_BRUSH = (0, 0, 255)

    VICINITY_DISTANCE = 2.5
    HIGHLIGHT_DISTANCE = 0.5

    ANCHOR_SIZE = 10
    HIGHLIGHT_SIZE = 20

    def __init__(self, title, horizontal, vertical):
        self._horizontal = horizontal
        self._vertical = vertical
        self._depth = self._find_missing_axis(horizontal, vertical)
        self._title = title
        self.widget = pg.PlotWidget(title=title)
        self._axis_scale_steps = []

        self.widget.setLabel('left', self._vertical, units='m')
        self.widget.setLabel('bottom', self._horizontal, units='m')

        self.widget.setAspectLocked(True, 1)
        self.widget.getViewBox().sigRangeChanged.connect(self._view_changed)
        self.view = self.widget.getViewBox()

    def update(self, anchors, pos, display_mode):
        self.widget.clear()

        # Sort anchors in depth order to add the one closes last
        for (i, anchor) in sorted(
                anchors.items(),
                key=lambda item: getattr(item[1], self._depth), reverse=True):
            anchor_v = getattr(anchor, self._horizontal)
            anchor_h = getattr(anchor, self._vertical)
            self._plot_anchor(anchor_v, anchor_h, i, anchor.distance,
                              display_mode)

        if display_mode is DisplayMode.estimated_position:
            cf_h = pos[PlotWrapper.axis_dict[self._horizontal]]
            cf_v = pos[PlotWrapper.axis_dict[self._vertical]]
            self.widget.plot([cf_h], [cf_v], pen=None,
                             symbolBrush=PlotWrapper.POSITION_BRUSH)

    def _find_missing_axis(self, axis1, axis2):
        all = set(self.axis_dict.keys())
        all.remove(axis1)
        all.remove(axis2)

        return list(all)[0]

    def _plot_anchor(self, x, y, anchor_id, distance, display_mode):
        brush = PlotWrapper.ANCHOR_BRUSH
        size = PlotWrapper.ANCHOR_SIZE
        if display_mode is DisplayMode.identify_anchor:
            if distance < PlotWrapper.VICINITY_DISTANCE:
                brush = self._mix_brushes(
                    brush,
                    PlotWrapper.HIGHLIGHT_ANCHOR_BRUSH,
                    distance / PlotWrapper.VICINITY_DISTANCE)

            if distance < PlotWrapper.HIGHLIGHT_DISTANCE:
                brush = PlotWrapper.HIGHLIGHT_ANCHOR_BRUSH
                size = PlotWrapper.HIGHLIGHT_SIZE

        self.widget.plot([x], [y], pen=None, symbolBrush=brush,
                         symbolSize=size)

        text = pg.TextItem(text="{}".format(anchor_id))
        self.widget.addItem(text)
        text.setPos(x, y)

    def _mix_brushes(self, brush1, brush2, mix):
        if mix < 0.0:
            return brush1
        if mix > 1.0:
            return brush2

        b1 = mix
        b2 = 1.0 - mix
        return (
            brush1[0] * b1 + brush2[0] * b2,
            brush1[1] * b1 + brush2[1] * b2,
            brush1[2] * b1 + brush2[2] * b2,
        )

    def _view_changed(self, view, settings):
        # Ignore all callbacks until this change is processed
        if PlotWrapper._change_lock:
            return
        PlotWrapper._change_lock = True

        for step in self._axis_scale_steps:
            range = step.from_view.viewRange()[step.from_axis]
            new_range = range

            if step.center_only:
                center = (range[0] + range[1]) / 2
                current_range = step.to_view.viewRange()[step.to_axis]
                current_center = (current_range[0] + current_range[1]) / 2
                delta = center - current_center
                new_range = [current_range[0] + delta,
                             current_range[1] + delta]

            if step.to_axis is PlotWrapper.XAxis:
                step.to_view.setRange(xRange=new_range, padding=0.0,
                                      update=True)
            else:
                step.to_view.setRange(yRange=new_range, padding=0.0,
                                      update=True)

        PlotWrapper._change_lock = False

    def set_scale_steps(self, steps):
        self._axis_scale_steps = steps


class DisplayMode(Enum):
    identify_anchor = 1
    estimated_position = 2


class LocoPositioningTab(Tab, locopositioning_tab_class):
    """Tab for plotting Loco Positioning data"""

    # Update period of parameter data in ms
    UPDATE_PERIOD = 100

    # Frame rate
    FPS = 10

    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)
    _log_error_signal = pyqtSignal(object, str)
    _anchor_range_signal = pyqtSignal(int, object, object)
    _position_signal = pyqtSignal(int, object, object)
    _anchor_position_signal = pyqtSignal(object, object)

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
        self._refs = []

        self._display_mode = DisplayMode.estimated_position

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._connected_signal.connect(self._connected)
        self._disconnected_signal.connect(self._disconnected)
        self._anchor_range_signal.connect(self._anchor_range_received)
        self._position_signal.connect(self._position_received)
        self._anchor_position_signal.connect(self._anchor_parameter_updated)

        self._id_anchor_button.clicked.connect(
            lambda enabled:
            self._set_display_mode(DisplayMode.identify_anchor)
        )

        self._estimated_postion_button.clicked.connect(
            lambda enabled:
            self._set_display_mode(DisplayMode.estimated_position)
        )

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(
            self._connected_signal.emit)

        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

        self._plot_xy = PlotWrapper("Top view (X/Y)", "x", "y")
        self._plot_top_left_layout.addWidget(self._plot_xy.widget)

        self._plot_xz = PlotWrapper("Front view (X/Z)", "x", "z")
        self._plot_bottom_left_layout.addWidget(self._plot_xz.widget)

        self._plot_yz = PlotWrapper("Right view (Y/Z)", "y", "z")
        self._plot_bottom_right_layout.addWidget(self._plot_yz.widget)

        self._plot_xy.set_scale_steps([
            AxisScaleStep(self._plot_xy, PlotWrapper.XAxis,
                          self._plot_xz, PlotWrapper.XAxis),
            AxisScaleStep(self._plot_xz, PlotWrapper.YAxis,
                          self._plot_yz, PlotWrapper.YAxis),
            AxisScaleStep(self._plot_xy, PlotWrapper.YAxis,
                          self._plot_yz, PlotWrapper.XAxis, center_only=True)
        ])

        self._plot_xz.set_scale_steps([
            AxisScaleStep(self._plot_xz, PlotWrapper.XAxis,
                          self._plot_xy, PlotWrapper.XAxis),
            AxisScaleStep(self._plot_xz, PlotWrapper.YAxis,
                          self._plot_yz, PlotWrapper.YAxis),
            AxisScaleStep(self._plot_xy, PlotWrapper.YAxis,
                          self._plot_yz, PlotWrapper.XAxis, center_only=True)
        ])

        self._plot_yz.set_scale_steps([
            AxisScaleStep(self._plot_yz, PlotWrapper.YAxis,
                          self._plot_xz, PlotWrapper.YAxis),
            AxisScaleStep(self._plot_xz, PlotWrapper.XAxis,
                          self._plot_xy, PlotWrapper.XAxis),
            AxisScaleStep(self._plot_yz, PlotWrapper.XAxis,
                          self._plot_xy, PlotWrapper.YAxis, center_only=True)
        ])

        self._plot_xy.view.setRange(xRange=(0.0, 5.0))

        self._graph_timer = QTimer()
        self._graph_timer.setInterval(1000 / self.FPS)
        self._graph_timer.timeout.connect(self._update_graphics)
        self._graph_timer.start()

    def _set_display_mode(self, display_mode):
        self._display_mode = display_mode

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
                    ("ranging", "distance0", "float"),
                    ("ranging", "distance1", "float"),
                    ("ranging", "distance2", "float"),
                    ("ranging", "distance3", "float"),
                ],
                self._anchor_range_signal.emit,
                self._log_error_signal.emit)

            self._register_logblock(
                "LoPoTab1",
                [
                    ("ranging", "distance4", "float"),
                    ("ranging", "distance5", "float"),
                    ("ranging", "distance6", "float"),
                    ("ranging", "distance7", "float"),
                ],
                self._anchor_range_signal.emit,
                self._log_error_signal.emit),

            self._register_logblock(
                "LoPoTab2",
                [
                    ("kalman", "stateX", "float"),
                    ("kalman", "stateY", "float"),
                    ("kalman", "stateZ", "float"),
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

    def _register_logblock(self, logblock_name, variables, data_cb, error_cb):
        """Register log data to listen for. One logblock can contain a limited
        number of parameters (6 for floats)."""
        lg = LogConfig(logblock_name, self.UPDATE_PERIOD)
        for variable in variables:
            if self._is_in_toc(variable):
                lg.add_variable('{}.{}'.format(variable[0], variable[1]),
                                variable[2])

        self._helper.cf.log.add_config(lg)
        lg.data_received_cb.add_callback(data_cb)
        lg.error_cb.add_callback(error_cb)
        lg.start()
        return lg

    def _is_in_toc(self, variable):
        toc = self._helper.cf.log.toc
        group = variable[0]
        param = variable[1]
        return group in toc.toc and param in toc.toc[group]

    def _anchor_range_received(self, timestamp, data, logconf):
        """Callback from the logging system when a range is updated."""
        for name, value in data.items():
            valid, anchor_number = self._parse_range_param_name(name)
            if valid:
                self._get_anchor(anchor_number).distance = float(value)

    def _position_received(self, timestamp, data, logconf):
        """Callback from the logging system when the position is updated."""
        for name, value in data.items():
            valid, axis = self._parse_position_param_name(name)
            if valid:
                self._position[axis] = float(value)

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
                group=group, name=name, cb=self._anchor_position_signal.emit)

    def _anchor_parameter_updated(self, name, value):
        """Callback from the param layer when a parameter has been updated"""
        self.set_anchor_position(name, value)

    def set_anchor_position(self, name, value):
        """Set the position of an anchor. If the anchor does not exist yet in
        the anchor dictionary, create it."""
        valid, anchor_number, axis = self._parse_anchor_parameter_name(name)
        if valid:
            self._get_anchor(anchor_number).set_position(axis, float(value))

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
        anchors = copy.deepcopy(self._anchors)
        self._plot_yz.update(anchors, self._position, self._display_mode)
        self._plot_xy.update(anchors, self._position, self._display_mode)
        self._plot_xz.update(anchors, self._position, self._display_mode)
