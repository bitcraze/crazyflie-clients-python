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
from collections import namedtuple

from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal, QTimer, QObject
from PyQt5.QtGui import QFont
from PyQt5.QtGui import QMessageBox

import cfclient
from cfclient.ui.tab import Tab

from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.mem import MemoryElement
from lpslib.lopoanchor import LoPoAnchor

import copy
import sys

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


STYLE_RED_BACKGROUND = "background-color: lightpink;"
STYLE_GREEN_BACKGROUND = "background-color: lightgreen;"
STYLE_NO_BACKGROUND = "background-color: none;"


class Anchor:
    def __init__(self, x=0.0, y=0.0, z=0.0, distance=0.0):
        self.x = x
        self.y = y
        self.z = z
        self.distance = distance

    def set_position(self, position):
        """Sets the position."""
        self.x = position[0]
        self.y = position[1]
        self.z = position[2]

    def get_position(self):
        """Returns the position as a vector"""
        return (self.x, self.y, self.z)


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

    LABEL_SIZE = 15
    LABEL_HIGHLIGHT_SIZE = 30

    ANCHOR_SIZE = 10
    HIGHLIGHT_SIZE = 20

    def __init__(self, title, horizontal, vertical):
        self._horizontal = horizontal
        self._vertical = vertical
        self._depth = self._find_missing_axis(horizontal, vertical)
        self._title = title
        self.widget = pg.PlotWidget(title=title, enableMenu=False)
        self.widget.getPlotItem().hideButtons()
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
        font_size = self.LABEL_SIZE
        if display_mode is DisplayMode.identify_anchor:
            if distance < PlotWrapper.VICINITY_DISTANCE:
                brush = self._mix_brushes(
                    brush,
                    PlotWrapper.HIGHLIGHT_ANCHOR_BRUSH,
                    distance / PlotWrapper.VICINITY_DISTANCE)

            if distance < PlotWrapper.HIGHLIGHT_DISTANCE:
                brush = PlotWrapper.HIGHLIGHT_ANCHOR_BRUSH
                size = PlotWrapper.HIGHLIGHT_SIZE
                font_size = self.LABEL_HIGHLIGHT_SIZE

        self.widget.plot([x], [y], pen=None, symbolBrush=brush,
                         symbolSize=size)

        text = pg.TextItem(text="{}".format(anchor_id))
        font = QFont("Helvetica", font_size)
        text.setFont(font)
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


Range = namedtuple('Range', ['min', 'max'])


class AnchorPosWrapper(QObject):
    """Wraps the UI elements of one anchor position"""

    _spinbox_changed_signal = pyqtSignal(float)
    _SPINNER_THRESHOLD = 0.001

    def __init__(self, x, y, z):
        super(AnchorPosWrapper, self).__init__()
        self._x = x
        self._y = y
        self._z = z

        self._ref_x = 0
        self._ref_y = 0
        self._ref_z = 0

        self._has_ref_set = False

        self._spinbox_changed_signal.connect(self._compare_all_ref_positions)
        self._x.valueChanged.connect(self._spinbox_changed_signal)
        self._y.valueChanged.connect(self._spinbox_changed_signal)
        self._z.valueChanged.connect(self._spinbox_changed_signal)

    def get_position(self):
        """Get the position from the UI elements"""
        return (self._x.value(), self._y.value(), self._z.value())

    def _compare_one_ref_position(self, spinner, ref):
        if (abs(spinner.value() - ref) < self._SPINNER_THRESHOLD):
            spinner.setStyleSheet(STYLE_GREEN_BACKGROUND)
        else:
            spinner.setStyleSheet(STYLE_RED_BACKGROUND)

    def _compare_all_ref_positions(self):
        if self._has_ref_set:
            self._compare_one_ref_position(self._x, self._ref_x)
            self._compare_one_ref_position(self._y, self._ref_y)
            self._compare_one_ref_position(self._z, self._ref_z)

    def set_position(self, position):
        """Set the position in the UI elements"""
        self._x.setValue(position[0])
        self._y.setValue(position[1])
        self._z.setValue(position[2])

    def set_ref_position(self, position):
        """..."""
        self._ref_x = position[0]
        self._ref_y = position[1]
        self._ref_z = position[2]
        self._has_ref_set = True
        self._compare_all_ref_positions()

    def enable(self, enabled):
        """Enable/disable all UI elements for the position"""
        self._x.setEnabled(enabled)
        self._y.setEnabled(enabled)
        self._z.setEnabled(enabled)
        if not enabled:
            self._has_ref_set = False
            self._x.setStyleSheet(STYLE_NO_BACKGROUND)
            self._y.setStyleSheet(STYLE_NO_BACKGROUND)
            self._z.setStyleSheet(STYLE_NO_BACKGROUND)


class LocoPositioningTab(Tab, locopositioning_tab_class):
    """Tab for plotting Loco Positioning data"""

    # Update period of log data in ms
    UPDATE_PERIOD_LOG = 100

    # Update period of anchor position data
    UPDATE_PERIOD_ANCHOR_POS = 5000

    # Frame rate (updates per second)
    FPS = 2

    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)
    _log_error_signal = pyqtSignal(object, str)
    _anchor_range_signal = pyqtSignal(int, object, object)
    _position_signal = pyqtSignal(int, object, object)
    _anchor_position_signal = pyqtSignal(object)

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
        self._anchor_position_signal.connect(self._anchor_positions_updated)

        self._id_anchor_button.clicked.connect(
            lambda enabled:
            self._set_display_mode(DisplayMode.identify_anchor)
        )

        self._estimated_postion_button.clicked.connect(
            lambda enabled:
            self._set_display_mode(DisplayMode.estimated_position)
        )

        self._anchor_pos_ui = {}
        for anchor_nr in range(0, 8):
            self._register_anchor_pos_ui(anchor_nr)

        self._write_pos_to_anhors_button.clicked.connect(
            lambda enabled:
            self._write_positions_to_anchors()
        )

        self._read_pos_from_anhors_button.clicked.connect(
            lambda enabled:
            self._read_positions_from_anchors()
        )

        self._show_all_button.clicked.connect(self._scale_and_center_graphs)

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(
            self._connected_signal.emit)

        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

        self._set_up_plots()

        self._graph_timer = QTimer()
        self._graph_timer.setInterval(1000 / self.FPS)
        self._graph_timer.timeout.connect(self._update_graphics)
        self._graph_timer.start()

        self._anchor_pos_timer = QTimer()
        self._anchor_pos_timer.setInterval(self.UPDATE_PERIOD_ANCHOR_POS)
        self._anchor_pos_timer.timeout.connect(self._poll_anchor_positions)

    def _register_anchor_pos_ui(self, nr):
        x_spin = getattr(self, 'spin_a{}x'.format(nr))
        y_spin = getattr(self, 'spin_a{}y'.format(nr))
        z_spin = getattr(self, 'spin_a{}z'.format(nr))
        self._anchor_pos_ui[nr] = AnchorPosWrapper(x_spin, y_spin, z_spin)

    def _write_positions_to_anchors(self):
        lopo = LoPoAnchor(self._helper.cf)

        for id, anchor_pos in self._anchor_pos_ui.items():
            if id in self._anchors:
                position = anchor_pos.get_position()
                lopo.set_position(id, position)

    def _read_positions_from_anchors(self):
        for id, anchor_pos in self._anchor_pos_ui.items():
            position = (0.0, 0.0, 0.0)
            if id in self._anchors:
                position = self._anchors[id].get_position()

            anchor_pos.set_position(position)

    def _enable_anchor_pos_ui(self):
        for id, anchor_pos in self._anchor_pos_ui.items():
            exists = id in self._anchors
            anchor_pos.enable(exists)

    def _set_up_plots(self):
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

    def _set_display_mode(self, display_mode):
        self._display_mode = display_mode

    def _clear_state(self):
        self._anchors = {}
        self._position = [0.0, 0.0, 0.0]
        for i in range(8):
            label = getattr(self, '_status_a{}'.format(i))
            label.setStyleSheet(STYLE_NO_BACKGROUND)

    def _scale_and_center_graphs(self):
        start_bounds = Range(sys.float_info.max, -sys.float_info.max)
        bounds = {"x": start_bounds, "y": start_bounds,
                  "z": start_bounds}
        for a in self._anchors.values():
            bounds = self._find_min_max_data_range(bounds, [a.x, a.y, a.z])
        bounds = self._find_min_max_data_range(bounds, self._position)

        bounds = self._pad_bounds(bounds)
        self._center_all_data_in_graphs(bounds)
        self._rescale_to_fit_data(bounds)

    def _rescale_to_fit_data(self, bounds):
        [[xy_xmin, xy_xmax],
            [xy_ymin, xy_ymax]] = self._plot_xy.view.viewRange()
        [[yz_xmin, yz_xmax],
            [yz_ymin, yz_ymax]] = self._plot_yz.view.viewRange()
        if not self._is_data_visibile(bounds, self._position):
            if self._will_new_range_zoom_in(Range(xy_xmin, xy_xmax),
                                            bounds["x"]):
                self._plot_xy.view.setRange(xRange=bounds["x"],
                                            padding=0.0, update=True)

        if not self._is_data_visibile(bounds, self._position):
            if self._will_new_range_zoom_in(Range(xy_ymin, xy_ymax),
                                            bounds["y"]):
                self._plot_xy.view.setRange(yRange=bounds["y"],
                                            padding=0.0, update=True)

        if not self._is_data_visibile(bounds, self._position):
            if self._will_new_range_zoom_in(Range(yz_xmin, yz_xmax),
                                            bounds["y"]):
                self._plot_yz.view.setRange(yRange=bounds["y"],
                                            padding=0.0, update=True)

        if not self._is_data_visibile(bounds, self._position):
            if self._will_new_range_zoom_in(Range(yz_ymin, yz_ymax),
                                            bounds["z"]):
                self._plot_yz.view.setRange(yRange=bounds["z"], padding=0.0,
                                            update=True)

    def _pad_bounds(self, ranges):
        new_ranges = ranges

        new_ranges["x"] = Range(new_ranges["x"].min - 1.0,
                                new_ranges["x"].max + 1.0)

        new_ranges["y"] = Range(new_ranges["y"].min - 1.0,
                                new_ranges["y"].max + 1.0)

        new_ranges["z"] = Range(new_ranges["z"].min - 1.0,
                                new_ranges["z"].max + 1.0)

        return new_ranges

    def _center_all_data_in_graphs(self, ranges):
        # Will center data in graphs without taking care of scaling
        self._plot_xy.view.setRange(xRange=ranges["x"], yRange=ranges["y"],
                                    padding=0.0, update=True)
        self._plot_yz.view.setRange(yRange=ranges["z"], padding=0.0,
                                    update=True)

    def _will_new_range_zoom_in(self, old_range, new_range):
        return old_range.min > new_range.min

    def _is_data_visibile(self, ranges, point):
        [[xy_xmin, xy_xmax],
            [xy_ymin, xy_ymax]] = self._plot_xy.view.viewRange()
        [[yz_xmin, yz_xmax],
            [yz_ymin, yz_ymax]] = self._plot_yz.view.viewRange()
        [[xz_xmin, xz_xmax],
            [xz_ymin, xz_ymax]] = self._plot_xz.view.viewRange()

        allVisible = True

        if ranges["x"].min < xy_xmin or ranges["x"].max > xy_xmax:
            allVisible = False

        if ranges["z"].min < yz_ymin or ranges["z"].max > yz_ymax:
            allVisible = False

        if ranges["y"].min < yz_xmin or ranges["y"].max > yz_xmax:
            allVisible = False

        if ranges["y"].min < xy_ymin or ranges["y"].max > xy_ymax:
            allVisible = False

        return allVisible

    def _find_min_max_data_range(self, ranges, point):
        result = ranges

        result["x"] = Range(min(ranges["x"].min, point[0]),
                            max(ranges["x"].max, point[0]))

        result["y"] = Range(min(ranges["y"].min, point[1]),
                            max(ranges["y"].max, point[1]))

        result["z"] = Range(min(ranges["z"].min, point[2]),
                            max(ranges["z"].max, point[2]))

        return result

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        logger.debug("Crazyflie connected to {}".format(link_uri))

        if self._helper.cf.mem.ow_search(vid=0xBC, pid=0x06):
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
                        ("ranging", "state", "uint8_t")
                    ],
                    self._position_signal.emit,
                    self._log_error_signal.emit),
            except KeyError as e:
                logger.warning(str(e))
            except AttributeError as e:
                logger.warning(str(e))

            self._start_polling_anchor_pos(self._helper.cf)

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        logger.debug("Crazyflie disconnected from {}".format(link_uri))
        self._stop_polling_anchor_pos()
        self._clear_state()
        self._update_graphics()

    def _register_logblock(self, logblock_name, variables, data_cb, error_cb):
        """Register log data to listen for. One logblock can contain a limited
        number of parameters (6 for floats)."""
        lg = LogConfig(logblock_name, self.UPDATE_PERIOD_LOG)
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
        self._update_ranging_status_indicators(data["ranging.state"])

    def _update_ranging_status_indicators(self, status):
        for i in range(8):
            label = getattr(self, '_status_a{}'.format(i))
            ok = (status >> i) & 0x01
            exists = i in self._anchors
            if ok:
                label.setStyleSheet(STYLE_GREEN_BACKGROUND)
            elif exists:
                label.setStyleSheet(STYLE_RED_BACKGROUND)

    def _logging_error(self, log_conf, msg):
        """Callback from the log layer when an error occurs"""
        QMessageBox.about(self, "LocoPositioningTab error",
                          "Error when using log config",
                          " [{0}]: {1}".format(log_conf.name, msg))

    def _start_polling_anchor_pos(self, crazyflie):
        """Set up a timer to poll anchor positions from the memory sub
        system"""
        self._anchor_pos_timer.start()

    def _stop_polling_anchor_pos(self):
        self._anchor_pos_timer.stop()

    def _poll_anchor_positions(self):
        mems = self._helper.cf.mem.get_mems(MemoryElement.TYPE_LOCO)
        if len(mems) > 0:
            mems[0].update(self._anchor_position_signal.emit)

    def _anchor_positions_updated(self, mem):
        """Callback from the memory sub system when the anchor positions
         are updated"""
        for anchor_number, anchor_data in enumerate(mem.anchor_data):
            if anchor_data.is_valid:
                anchor = self._get_anchor(anchor_number)
                anchor.set_position(anchor_data.position)
                self._anchor_pos_ui[anchor_number].\
                    set_ref_position(anchor_data.position)

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

    def _get_anchor(self, anchor_number):
        if anchor_number not in self._anchors:
            self._anchors[anchor_number] = Anchor()
        return self._anchors[anchor_number]

    def _update_graphics(self):
        if self.is_visible():
            anchors = copy.deepcopy(self._anchors)
            self._plot_yz.update(anchors, self._position, self._display_mode)
            self._plot_xy.update(anchors, self._position, self._display_mode)
            self._plot_xz.update(anchors, self._position, self._display_mode)
            self._enable_anchor_pos_ui()
