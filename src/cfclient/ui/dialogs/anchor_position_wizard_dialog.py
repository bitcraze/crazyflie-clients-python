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
#  You should have received a copy of the GNU General Public License along with
#  this program; if not, write to the Free Software Foundation, Inc.,
#  51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""
Dialog box used to estimate LPS anchor positions
"""
import logging
from collections import namedtuple

import cfclient
from PyQt5 import QtWidgets
from PyQt5 import uic
import numpy as np

from .anchor_position_wizard_utils.anchor_pos_solver_twr import \
    AnchorPosSolverTwr
from .anchor_position_wizard_utils.range_recorder import RangeRecorder

__author__ = 'Bitcraze AB'
__all__ = ['AnchorPositionWizardDialog']

logger = logging.getLogger(__name__)

(wizard_widget_class, connect_widget_base_class) = (
    uic.loadUiType(cfclient.module_path +
                   '/ui/dialogs/anchor_position_wizard_dialog.ui')
)


_Step = namedtuple('_Step', ['prev', 'next', 'process', 'text'])


class AnchorPositionWizardDialog(QtWidgets.QWidget, wizard_widget_class):

    def __init__(self, update_period_ms, active_anchors, anchor_pos_ui, *args):
        super(AnchorPositionWizardDialog, self).__init__(*args)
        self.setupUi(self)

        self._anchor_indexes = []
        for i, is_active in enumerate(active_anchors):
            if is_active:
                self._anchor_indexes.append(i)
        self._anchor_count = len(self._anchor_indexes)

        self._range_recorder = RangeRecorder(update_period_ms,
                                             self._anchor_indexes)
        self._anchor_pos_ui = anchor_pos_ui

        self._steps = [
            _Step(prev=False, next=True, process=None,
                  text='This wizard will help you to automatically estimate '
                       'the anchor positions in you system. You will be '
                       'asked to place the Crazyflie in specific places to '
                       'meassure and calculate where the anchors are located '
                       'and to define your coordinate system. Disclaimer: '
                       'this is in beta stage and may or may not work. The '
                       'result may not be useful.'),
            _Step(prev=True, next=True, process=None,
                  text='Start by imagining where you want your coordinate '
                       'sytstem and the orientation of the axis. It might be '
                       'a good idea to mark it on the floor with tape.'),
            _Step(prev=True, next=True, process=self._record_origin,
                  text='Place the Crazyflie where you want your coordinate '
                       'system origin (0, 0, 0).'),
            _Step(prev=True, next=True, process=self._record_x_axis,
                  text='Place the Crazyflie on the X-axis, on the positive '
                       'side (X > 0) as far from (0, 0, 0) as possible but '
                       'within the space of the anchors.'),
            _Step(prev=True, next=True, process=self._record_xy_plane,
                  text='Place the Crazyflie in the XY-plane, Y > 0. Try to '
                       'put it approximately on the Y-axis as far from '
                       '(0, 0, 0) as possible.'),
            _Step(prev=True, next=True, process=self._record_space,
                  text='Click next and move the Crazyflie around in the '
                       'space inside the anchors for 30 seconds. Try to '
                       'cover all parts and approaching all anchors.'),
            _Step(prev=True, next=True, process=self._crunch_numbers,
                  text='Data is recorded. Click next to crunch the numbers '
                       'and set positions in the Loco Positioning tab.'),
            _Step(prev=True, next=True, process=self._close_dialog,
                  text='Done! The result has been transferred to the anchor '
                       'positions in the Loco Positioning tab. Do not '
                       'forget to write the positions to the anchors if you '
                       'want to use them.'),
        ]

        self._previous_button.clicked.connect(
            self._previous_step
        )

        self._next_button.clicked.connect(
            self._next_step
        )

        self._next_processing = None
        self._current_step = 0
        self._error_label.setText('')
        self._update_ui()

        self._ranges_origin = None
        self._ranges_x_axis = None
        self._ranges_xy_plane = None
        self._range_list_space = None

    def range_received(self, anchor, distance, timestamp):
        self._range_recorder.range_received(anchor, distance, timestamp)

    def _update_ui(self):
        step = self._steps[self._current_step]
        self._previous_button.setEnabled(step.prev)
        self._next_button.setEnabled(step.next)
        self._next_processing = step.process
        self._info_label.setText(step.text)
        self._progress_bar.setValue(0)

    def _block_user_action(self):
        self._previous_button.setEnabled(False)
        self._next_button.setEnabled(False)

    def _start_processing(self):
        self._error_label.setText('')
        self._block_user_action()

    def _next_step(self):
        self._error_label.setText('')
        if self._next_processing:
            self._next_processing()
        else:
            self._finalize_next_step()

    def _finalize_next_step(self):
        self._current_step += 1
        self._update_ui()

    def _previous_step(self):
        self._error_label.setText('')
        self._current_step -= 1
        self._update_ui()

    def _record_origin(self):
        self._start_processing()
        self._ranges_origin = []
        self._record_point_ranges(self._ranges_origin)

    def _record_x_axis(self):
        self._start_processing()
        self._ranges_x_axis = []
        self._record_point_ranges(self._ranges_x_axis)

    def _record_xy_plane(self):
        self._start_processing()
        self._ranges_xy_plane = []
        self._record_point_ranges(self._ranges_xy_plane)

    def _record_space(self):
        self._start_processing()
        self.raw_range_list = []
        self._range_recorder.record(
            int(30 * 1000 / self._range_recorder._update_period_ms),
            self.raw_range_list,
            self._record_space_recorded_callback,
            self._update_progress,
            self._error_callback)

    def _record_space_recorded_callback(self):
        desired_count = 100
        actual_count = len(self.raw_range_list)
        if actual_count <= desired_count:
            self.range_list = self.raw_range_list
        else:
            result = np.array(
                self.raw_range_list)[0::(actual_count / desired_count)]
            self._range_list_space = result.tolist()

        self._finalize_next_step()

    def _crunch_numbers(self):
        logger.info("Origin: {}".format(self._ranges_origin))
        logger.info("X-axis: {}".format(self._ranges_x_axis))
        logger.info("XY-plane: {}".format(self._ranges_xy_plane))
        logger.info("Space: {}".format(self._range_list_space))

        solver = AnchorPosSolverTwr()
        positions = solver.solve(self._anchor_count, self._ranges_origin,
                                 self._ranges_x_axis,
                                 self._ranges_xy_plane,
                                 self._range_list_space)

        for i in range(self._anchor_count):
            id = self._anchor_indexes[i]
            self._anchor_pos_ui[id].set_position(positions[i])
        self._finalize_next_step()

    def _record_point_ranges(self, data):
        self._range_recorder.record(
            20,
            data,
            self._finalize_next_step,
            self._update_progress, self._error_callback)

    def _update_progress(self, progress):
        self._progress_bar.setValue(progress * 100)

    def _close_dialog(self):
        self.close()

    def _error_callback(self, e):
        self._error_label.setText(
            'Error: There seems to be a problem! Please check the connection '
            'and that there is good reception from all anchors.')
        self._update_ui()
