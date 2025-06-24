#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2025 Bitcraze AB
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
Container for the geometry estimation functionality in the lighthouse tab.
"""

from typing import Callable
from PyQt6 import QtCore, QtWidgets, uic, QtGui

import logging
from enum import Enum
import threading

import cfclient

from cflib.crazyflie import Crazyflie
from cflib.crazyflie.mem.lighthouse_memory import LighthouseBsGeometry
from cflib.localization.lighthouse_sweep_angle_reader import LighthouseSweepAngleAverageReader
from cflib.localization.lighthouse_sweep_angle_reader import LighthouseMatchedSweepAngleReader
from cflib.localization.lighthouse_bs_vector import LighthouseBsVectors
from cflib.localization.lighthouse_types import LhDeck4SensorPositions
from cflib.localization.lighthouse_cf_pose_sample import LhCfPoseSample
from cflib.localization.lighthouse_geo_estimation_manager import LhGeoInputContainer, LhGeoEstimationManager
from cflib.localization.lighthouse_geometry_solution import LighthouseGeometrySolution
from cflib.localization.user_action_detector import UserActionDetector

__author__ = 'Bitcraze AB'
__all__ = ['GeoEstimatorWidget']

logger = logging.getLogger(__name__)

(geo_estimator_widget_class, connect_widget_base_class) = (
    uic.loadUiType(cfclient.module_path + '/ui/widgets/geo_estimator.ui'))


REFERENCE_DIST = 1.0


class _CollectionStep(Enum):
    ORIGIN = ('bslh_1.png',
              'Step 1. Origin',
              'Put the Crazyflie where you want the origin of your coordinate system.\n')
    X_AXIS = ('bslh_2.png',
              'Step 2. X-axis',
              'Put the Crazyflie on the positive X-axis,' +
              f'  exactly {REFERENCE_DIST} meters from the origin.\n' +
              'This will be used to define the X-axis as well as scaling of the system.')
    XY_PLANE = ('bslh_3.png',
                'Step 3. XY-plane',
                'Put the Crazyflie somewhere in the XY-plane, but not on the X-axis.\n' +
                'This position is used to map the the XY-plane to the floor.\n' +
                'You can sample multiple positions to get a more precise definition.')
    XYZ_SPACE = ('bslh_4.png',
                 'Step 4. Flight space',
                 'Sample points in the space that will be used.\n' +
                 'Make sure all the base stations are received, you need at least two base \n' +
                 'stations in each sample. Sample by rotating the Crazyflie quickly \n' +
                 'left-right around the Z-axis and then holding it still for a second.\n')

    def __init__(self, image, title, instructions):
        self.image = image
        self.title = title
        self.instructions = instructions

        self._order = None

    @property
    def order(self):
        """Get the order of the steps in the collection process"""
        if self._order is None:
            self._order = [self.ORIGIN,
                           self.X_AXIS,
                           self.XY_PLANE,
                           self.XYZ_SPACE]
        return self._order

    def next(self):
        """Get the next step in the collection process"""
        for i, step in enumerate(self.order):
            if step == self:
                if i + 1 < len(self.order):
                    return self.order[i + 1]
                else:
                    return self

    def has_next(self):
        """Check if there is a next step in the collection process"""
        return self.next() != self

    def previous(self):
        """Get the previous step in the collection process"""
        for i, step in enumerate(self.order):
            if step == self:
                if i - 1 >= 0:
                    return self.order[i - 1]
                else:
                    return self

    def has_previous(self):
        """Check if there is a previous step in the collection process"""
        return self.previous() != self


class GeoEstimatorWidget(QtWidgets.QWidget, geo_estimator_widget_class):
    """Widget for the geometry estimator UI"""

    _timeout_reader_signal = QtCore.pyqtSignal(object)
    _solution_ready_signal = QtCore.pyqtSignal(object)

    def __init__(self, lighthouse_tab):
        super(GeoEstimatorWidget, self).__init__()
        self.setupUi(self)

        self._lighthouse_tab = lighthouse_tab
        self._helper = lighthouse_tab._helper

        self._step_next_button.clicked.connect(lambda: self._update_step(self._current_step.next()))
        self._step_previous_button.clicked.connect(lambda: self._update_step(self._current_step.previous()))
        self._step_measure.clicked.connect(self._measure)

        self._timeout_reader = TimeoutAngleReader(self._helper.cf, self._timeout_reader_signal.emit)
        self._timeout_reader_signal.connect(self._average_available_cb)
        self._timeout_reader_result_setter = None

        self._current_step = _CollectionStep.ORIGIN
        self._populate_step()
        self._update_ui_reading(False)

        self._container = LhGeoInputContainer(LhDeck4SensorPositions.positions)
        self._solution_ready_signal.connect(self._solution_ready_cb)
        self._solver_thread = None

        # TODO krri handĺe disconnects

    def setVisible(self, visible: bool):
        super(GeoEstimatorWidget, self).setVisible(visible)
        if visible:
            if self._solver_thread is None:
                logger.info("Starting solver thread")
                self._solver_thread = LhGeoEstimationManager.SolverThread(self._container,
                                                                          is_done_cb=self._solution_ready_signal.emit)
                self._solver_thread.start()
        else:
            if self._solver_thread is not None:
                logger.info("Stopping solver thread")
                self._solver_thread.stop(do_join=False)
                self._solver_thread = None

    def _update_step(self, step):
        """Update the widget to display the new step"""
        if step != self._current_step:
            self._current_step = step
            self._populate_step()

    def _populate_step(self):
        """Populate the widget with the current step's information"""
        step = self._current_step

        self._step_title.setText(step.title)
        self._step_image.setPixmap(QtGui.QPixmap(
            cfclient.module_path + '/ui/widgets/geo_estimator_resources/' + step.image))
        self._step_instructions.setText(step.instructions)
        self._step_info.setText('')

        self._step_measure.setVisible(step != _CollectionStep.XYZ_SPACE)

        self._step_previous_button.setEnabled(step.has_previous())
        self._step_next_button.setEnabled(step.has_next())

    def _update_ui_reading(self, is_reading: bool):
        """Update the UI to reflect whether a reading is in progress"""
        is_enabled = not is_reading

        self._step_measure.setEnabled(is_enabled)
        self._step_next_button.setEnabled(is_enabled)
        self._step_previous_button.setEnabled(is_enabled)

    def _measure(self):
        """Trigger the measurement for the current step"""
        match self._current_step:
            case _CollectionStep.ORIGIN:
                self._measure_origin()
            case _CollectionStep.X_AXIS:
                self._measure_x_axis()
            case _CollectionStep.XY_PLANE:
                self._measure_xy_plane()
            case _CollectionStep.XYZ_SPACE:
                pass

    def _measure_origin(self):
        """Measure the origin position"""
        # Placeholder for actual measurement logic
        logger.info("Measuring origin position...")
        self._start_timeout_average_read(self._container.set_origin_sample)

    def _measure_x_axis(self):
        """Measure the X-axis position"""
        # Placeholder for actual measurement logic
        logger.info("Measuring X-axis position...")
        self._start_timeout_average_read(self._container.set_x_axis_sample)

    def _measure_xy_plane(self):
        """Measure the XY-plane position"""
        # Placeholder for actual measurement logic
        logger.info("Measuring XY-plane position...")
        self._start_timeout_average_read(self._container.append_xy_plane_sample)

    def _start_timeout_average_read(self, setter: Callable[[LhCfPoseSample], None]):
        """Start the timeout average angle reader"""
        self._timeout_reader.start()
        self._timeout_reader_result_setter = setter
        self._step_info.setText("Collecting angles...")
        self._update_ui_reading(True)

    def _average_available_cb(self, sample: LhCfPoseSample):
        """Callback for when the average angles are available from the reader or after"""

        bs_ids = list(sample.angles_calibrated.keys())
        bs_ids.sort()
        bs_seen = ', '.join(map(lambda x: str(x + 1), bs_ids))
        bs_count = len(bs_ids)

        logger.info("Average angles received: %s", bs_seen)

        self._update_ui_reading(False)

        if bs_count == 0:
            self._step_info.setText("No base stations seen, please try again.")
        elif bs_count < 2:
            self._step_info.setText(f"Only one base station (nr {bs_seen}) was seen, we need at least two. Please try again.")
        else:
            if self._timeout_reader_result_setter is not None:
                self._timeout_reader_result_setter(sample)
            self._step_info.setText(f"Base stations {bs_seen} were seen. Sample stored.")

        self._timeout_reader_result_setter = None

    def _solution_ready_cb(self, solution: LighthouseGeometrySolution):
        logger.info('Solution ready --------------------------------------')
        logger.info(f'Converged: {solution.has_converged}')
        logger.info(f'Progress info: {solution.progress_info}')
        logger.info(f'Progress is ok: {solution.progress_is_ok}')
        logger.info(f'Origin: {solution.is_origin_sample_valid}, {solution.origin_sample_info}')
        logger.info(f'X-axis: {solution.is_x_axis_samples_valid}, {solution.x_axis_samples_info}')
        logger.info(f'XY-plane: {solution.is_xy_plane_samples_valid}, {solution.xy_plane_samples_info}')
        logger.info(f'XYZ space: {solution.xyz_space_samples_info}')
        logger.info(f'General info: {solution.general_failure_info}')

        if solution.progress_is_ok:
            self._upload_geometry(solution.poses.bs_poses)

    def _upload_geometry(self, bs_poses: dict[int, LighthouseBsGeometry]):
        geo_dict = {}
        for bs_id, pose in bs_poses.items():
            geo = LighthouseBsGeometry()
            geo.origin = pose.translation.tolist()
            geo.rotation_matrix = pose.rot_matrix.tolist()
            geo.valid = True
            geo_dict[bs_id] = geo

        logger.info('Uploading geometry to Crazyflie')
        self._lighthouse_tab.write_and_store_geometry(geo_dict)


class TimeoutAngleReader:
    def __init__(self, cf: Crazyflie, ready_cb: Callable[[LhCfPoseSample], None]):
        self._ready_cb = ready_cb

        self.timeout_timer = QtCore.QTimer()
        self.timeout_timer.timeout.connect(self._timeout_cb)
        self.timeout_timer.setSingleShot(True)

        self.reader = LighthouseSweepAngleAverageReader(cf, self._reader_ready_cb)

        self.lock = threading.Lock()
        self.is_collecting = False

    def start(self, timeout=2000):
        with self.lock:
            if self.is_collecting:
                raise RuntimeError("Measurement already in progress!")
            self.is_collecting = True

        self.reader.start_angle_collection()
        self.timeout_timer.start(timeout)
        logger.info("Starting angle collection with timeout of %d ms", timeout)

    def _timeout_cb(self):
        logger.info("Timeout reached, stopping angle collection")
        with self.lock:
            if not self.is_collecting:
                return
            self.is_collecting = False

        self.reader.stop_angle_collection()

        result = LhCfPoseSample({})
        self._ready_cb(result)

    def _reader_ready_cb(self, recorded_angles: dict[int, tuple[int, LighthouseBsVectors]]):
        logger.info("Reader ready with %d base stations", len(recorded_angles))
        with self.lock:
            if not self.is_collecting:
                return
            self.is_collecting = False

        # TODO krri Can not stop the timer from this thread
        # self.timeout_timer.stop()

        angles_calibrated: dict[int, LighthouseBsVectors] = {}
        for bs_id, data in recorded_angles.items():
            angles_calibrated[bs_id] = data[1]

        result = LhCfPoseSample(angles_calibrated)
        self._ready_cb(result)
