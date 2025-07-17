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

import os
from typing import Callable
from PyQt6 import QtCore, QtWidgets, uic, QtGui
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtWidgets import QMessageBox, QPushButton
from PyQt6.QtCore import QTimer, QAbstractTableModel, QVariant, Qt, QModelIndex


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
                 'Step 4. XYZ-space',
                 'Sample points in the space that will be used.\n' +
                 'Make sure all the base stations are received, you need at least two base \n' +
                 'stations in each sample. Sample by rotating the Crazyflie quickly \n' +
                 'left-right around the Z-axis and then holding it still for a second, or \n' +
                 'optionally by clicking the sample button below.\n')

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


class _UserNotificationType(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"


STYLE_GREEN_BACKGROUND = "background-color: lightgreen;"
STYLE_RED_BACKGROUND = "background-color: lightpink;"
STYLE_YELLOW_BACKGROUND = "background-color: lightyellow;"
STYLE_NO_BACKGROUND = "background-color: ;"


class GeoEstimatorWidget(QtWidgets.QWidget, geo_estimator_widget_class):
    """Widget for the geometry estimator UI"""

    _timeout_reader_signal = QtCore.pyqtSignal(object)
    _container_updated_signal = QtCore.pyqtSignal()
    _user_notification_signal = QtCore.pyqtSignal(object)
    start_solving_signal = QtCore.pyqtSignal()
    solution_ready_signal = QtCore.pyqtSignal(object)
    sample_selection_changed_signal = QtCore.pyqtSignal(int)

    FILE_REGEX_YAML = "Config *.yaml;;All *.*"

    def __init__(self, lighthouse_tab):
        super(GeoEstimatorWidget, self).__init__()
        self.setupUi(self)

        self._lighthouse_tab = lighthouse_tab
        self._helper = lighthouse_tab._helper

        self._step_next_button.clicked.connect(lambda: self._change_step(self._current_step.next()))
        self._step_previous_button.clicked.connect(lambda: self._change_step(self._current_step.previous()))
        self._step_measure.clicked.connect(self._measure)

        self._clear_all_button.clicked.connect(self._clear_all)
        self._load_button.clicked.connect(lambda: self._load_from_file(use_session_path=False))
        self._restore_button.clicked.connect(lambda: self._load_from_file(use_session_path=True))
        self._save_button.clicked.connect(self._save_to_file)

        self._timeout_reader = TimeoutAngleReader(self._helper.cf, self._timeout_reader_signal.emit)
        self._timeout_reader_signal.connect(self._average_available_cb)
        self._timeout_reader_result_setter = None

        self._container_updated_signal.connect(self._update_solution_info)

        self._user_notification_signal.connect(self._notify_user)
        self._user_notification_clear_timer = QTimer()
        self._user_notification_clear_timer.setSingleShot(True)
        self._user_notification_clear_timer.timeout.connect(self._user_notification_clear)

        self._action_detector = UserActionDetector(self._helper.cf, cb=self._user_action_detected_cb)
        self._matched_reader = LighthouseMatchedSweepAngleReader(self._helper.cf, self._single_sample_ready_cb,
                                                                 timeout_cb=self._single_sample_timeout_cb)

        self._container = LhGeoInputContainer(LhDeck4SensorPositions.positions)
        self._session_path = os.path.join(cfclient.config_path, 'lh_geo_sessions')
        self._container.enable_auto_save(self._session_path)

        self._latest_solution: LighthouseGeometrySolution = LighthouseGeometrySolution([])
        self._current_step = _CollectionStep.ORIGIN

        self.start_solving_signal.connect(self._start_solving_cb)
        self.solution_ready_signal.connect(self._solution_ready_cb)
        self._is_solving = False
        self._solver_thread = None

        self._update_step_ui()
        self._update_ui_reading(False)
        self._update_solution_info()

        self._data_status_origin.clicked.connect(lambda: self._change_step(_CollectionStep.ORIGIN))
        self._data_status_x_axis.clicked.connect(lambda: self._change_step(_CollectionStep.X_AXIS))
        self._data_status_xy_plane.clicked.connect(lambda: self._change_step(_CollectionStep.XY_PLANE))
        self._data_status_xyz_space.clicked.connect(lambda: self._change_step(_CollectionStep.XYZ_SPACE))

        self._samples_details_model = SampleTableModel(self)
        self._samples_table_view.setModel(self._samples_details_model)
        self._samples_table_view.selectionModel().currentRowChanged.connect(self._selection_changed)

        header = self._samples_table_view.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        self._sample_details_checkbox.setChecked(False)
        self._samples_table_view.setVisible(False)
        self._sample_details_checkbox.stateChanged.connect(self._sample_details_checkbox_state_changed)

    def _selection_changed(self, current: QModelIndex, previous: QModelIndex):
        self.sample_selection_changed_signal.emit(current.row())

    def setVisible(self, visible: bool):
        super(GeoEstimatorWidget, self).setVisible(visible)
        if visible:
            if self._solver_thread is None:
                logger.info("Starting solver thread")
                self._solver_thread = LhGeoEstimationManager.SolverThread(self._container,
                                                                          is_done_cb=self.solution_ready_signal.emit,
                                                                          is_starting_estimation_cb=(
                                                                              self.start_solving_signal.emit))
                self._solver_thread.start()
        else:
            self._action_detector.stop()
            if self._solver_thread is not None:
                logger.info("Stopping solver thread")
                self._solver_thread.stop(do_join=False)
                self._solver_thread = None

    def new_session(self):
        self._container.clear_all_samples()

    def _clear_all(self):
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Clear samples Confirmation")
        dlg.setText("Are you sure you want to clear all samples and start over?")
        dlg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        button = dlg.exec()

        if button == QMessageBox.StandardButton.Yes:
            self.new_session()

    def _load_from_file(self, use_session_path=False):
        path = self._session_path if use_session_path else self._helper.current_folder
        names = QFileDialog.getOpenFileName(self, 'Load session', path, self.FILE_REGEX_YAML)

        if names[0] == '':
            return

        if not use_session_path:
            # If not using the session path, update the current folder
            self._helper.current_folder = os.path.dirname(names[0])

        file_name = names[0]
        with open(file_name, 'r', encoding='UTF8') as handle:
            self._container.populate_from_file_yaml(handle)

    def _save_to_file(self):
        """Save the current geometry samples to a file"""
        names = QFileDialog.getSaveFileName(self, 'Save session', self._helper.current_folder, self.FILE_REGEX_YAML)

        if names[0] == '':
            return

        self._helper.current_folder = os.path.dirname(names[0])

        if not names[0].endswith(".yaml") and names[0].find(".") < 0:
            file_name = names[0] + ".yaml"
        else:
            file_name = names[0]

        with open(file_name, 'w', encoding='UTF8') as handle:
            self._container.save_as_yaml_file(handle)

    def _sample_details_checkbox_state_changed(self, state: int):
        enabled = state == Qt.CheckState.Checked.value
        self._samples_table_view.setVisible(enabled)

    def _change_step(self, step):
        """Update the widget to display the new step"""
        if step != self._current_step:
            self._current_step = step
            self._update_step_ui()
            if step == _CollectionStep.XYZ_SPACE:
                self._action_detector.start()
            else:
                self._action_detector.stop()

    def _update_step_ui(self):
        """Populate the widget with the current step's information"""
        step = self._current_step

        self._step_title.setText(step.title)
        self._step_image.setPixmap(QtGui.QPixmap(
            cfclient.module_path + '/ui/widgets/geo_estimator_resources/' + step.image))
        self._step_instructions.setText(step.instructions)
        self._step_info.setText('')

        if step == _CollectionStep.XYZ_SPACE:
            self._step_measure.setText('Sample position')
        else:
            self._step_measure.setText('Start measurement')

        self._step_previous_button.setEnabled(step.has_previous())
        self._step_next_button.setEnabled(step.has_next())

        self._update_solution_info()

    def _update_ui_reading(self, is_reading: bool):
        """Update the UI to reflect whether a reading is in progress, that is enable/disable buttons"""
        is_enabled = not is_reading

        self._step_measure.setEnabled(is_enabled)
        self._step_next_button.setEnabled(is_enabled and self._current_step.has_next())
        self._step_previous_button.setEnabled(is_enabled and self._current_step.has_previous())

        self._data_status_origin.setEnabled(is_enabled)
        self._data_status_x_axis.setEnabled(is_enabled)
        self._data_status_xy_plane.setEnabled(is_enabled)
        self._data_status_xyz_space.setEnabled(is_enabled)

        self._load_button.setEnabled(is_enabled)
        self._save_button.setEnabled(is_enabled)
        self._clear_all_button.setEnabled(is_enabled)

    def _update_solution_info(self):
        solution = self._latest_solution

        match self._current_step:
            case _CollectionStep.ORIGIN:
                self._step_solution_info.setText(
                    'OK' if solution.is_origin_sample_valid else solution.origin_sample_info)
            case _CollectionStep.X_AXIS:
                self._step_solution_info.setText(
                    'OK' if solution.is_x_axis_samples_valid else solution.x_axis_samples_info)
            case _CollectionStep.XY_PLANE:
                if solution.xy_plane_samples_info:
                    text = f'OK, {self._container.xy_plane_sample_count()} sample(s)'
                else:
                    text = solution.xy_plane_samples_info
                self._step_solution_info.setText(text)
            case _CollectionStep.XYZ_SPACE:
                text = f'OK, {self._container.xyz_space_sample_count()} sample(s)'
                if solution.xyz_space_samples_info:
                    text += f', {solution.xyz_space_samples_info}'
                self._step_solution_info.setText(text)

        self._set_background_color(self._data_status_origin, solution.is_origin_sample_valid)
        self._set_background_color(self._data_status_x_axis, solution.is_x_axis_samples_valid)
        self._set_background_color(self._data_status_xy_plane, solution.is_xy_plane_samples_valid)

        if self._is_solving:
            self._solution_status_is_ok.setText('Solving... please wait')
            self._set_background_none(self._solution_status_is_ok)
        else:
            if solution.progress_is_ok:
                self._solution_status_is_ok.setText('Solution is OK')
                self._solution_status_uploaded.setText('Uploaded')
                self._solution_status_max_error.setText(f'Error: {solution.error_stats.max * 1000:.1f} mm')
            else:
                self._solution_status_is_ok.setText('No solution')
                self._solution_status_uploaded.setText('Not uploaded')
                self._solution_status_max_error.setText('Error: --')
            self._set_background_color(self._solution_status_is_ok, solution.progress_is_ok)

        self._solution_status_info.setText(solution.general_failure_info)

    def _notify_user(self, notification_type: _UserNotificationType):
        match notification_type:
            case _UserNotificationType.SUCCESS:
                self._helper.cf.platform.send_user_notification(True)
                self._sample_collection_box.setStyleSheet(STYLE_GREEN_BACKGROUND)
                self._update_ui_reading(False)
            case _UserNotificationType.FAILURE:
                self._helper.cf.platform.send_user_notification(False)
                self._sample_collection_box.setStyleSheet(STYLE_RED_BACKGROUND)
                self._update_ui_reading(False)
            case _UserNotificationType.PENDING:
                self._sample_collection_box.setStyleSheet(STYLE_YELLOW_BACKGROUND)
                self._update_ui_reading(True)

        self._user_notification_clear_timer.stop()
        self._user_notification_clear_timer.start(1000)

    def _user_notification_clear(self):
        self._sample_collection_box.setStyleSheet('')

    def _set_background_none(self, widget: QtWidgets.QWidget):
        widget.setStyleSheet(STYLE_NO_BACKGROUND)

    def _set_background_color(self, widget: QtWidgets.QWidget, is_valid: bool):
        """Set the background color of a widget based on validity"""
        if is_valid:
            widget.setStyleSheet(STYLE_GREEN_BACKGROUND)
        else:
            widget.setStyleSheet(STYLE_RED_BACKGROUND)

        # Force a repaint to ensure the style is applied immediately
        widget.repaint()

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
                self._measure_xyz_space()

    def _measure_origin(self):
        """Measure the origin position"""
        logger.debug("Measuring origin position...")
        self._start_timeout_average_read(self._container.set_origin_sample)

    def _measure_x_axis(self):
        """Measure the X-axis position"""
        logger.debug("Measuring X-axis position...")
        self._start_timeout_average_read(self._container.set_x_axis_sample)

    def _measure_xy_plane(self):
        """Measure the XY-plane position"""
        logger.debug("Measuring XY-plane position...")
        self._start_timeout_average_read(self._container.append_xy_plane_sample)

    def _measure_xyz_space(self):
        """Measure the XYZ-space position"""
        logger.debug("Measuring XYZ-space position...")
        self._user_notification_signal.emit(_UserNotificationType.PENDING)
        self._matched_reader.start(timeout=1.0)

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
            self._user_notification_signal.emit(_UserNotificationType.FAILURE)
        elif bs_count < 2:
            self._step_info.setText(f"Only one base station (nr {bs_seen}) was seen, " +
                                    "we need at least two. Please try again.")
            self._user_notification_signal.emit(_UserNotificationType.FAILURE)
        else:
            if self._timeout_reader_result_setter is not None:
                self._timeout_reader_result_setter(sample)
            self._step_info.setText(f"Base stations {bs_seen} were seen. Sample stored.")
            self._user_notification_signal.emit(_UserNotificationType.SUCCESS)

        self._timeout_reader_result_setter = None

    def _start_solving_cb(self):
        self._is_solving = True
        self._update_solution_info()

    def _solution_ready_cb(self, solution: LighthouseGeometrySolution):
        self._is_solving = False
        self._latest_solution = solution
        self._update_solution_info()

        logger.debug('Solution ready --------------------------------------')
        logger.debug(f'Converged: {solution.has_converged}')
        logger.debug(f'Progress info: {solution.progress_info}')
        logger.debug(f'Progress is ok: {solution.progress_is_ok}')
        logger.debug(f'Origin: {solution.is_origin_sample_valid}, {solution.origin_sample_info}')
        logger.debug(f'X-axis: {solution.is_x_axis_samples_valid}, {solution.x_axis_samples_info}')
        logger.debug(f'XY-plane: {solution.is_xy_plane_samples_valid}, {solution.xy_plane_samples_info}')
        logger.debug(f'XYZ space: {solution.xyz_space_samples_info}')
        logger.debug(f'General info: {solution.general_failure_info}')

        self._samples_details_model.setSolution(self._latest_solution)

        # Add delete buttons
        for row, sample in enumerate(solution.samples):
            button = QPushButton('Delete')
            button.clicked.connect(lambda _, uid=sample.uid: self._container.remove_sample(uid))
            self._samples_table_view.setIndexWidget(self._samples_details_model.index(row, 5), button)

        if solution.progress_is_ok:
            self._upload_geometry(solution.bs_poses)

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

    def _user_action_detected_cb(self):
        self._measure_xyz_space()

    def _single_sample_ready_cb(self, sample: LhCfPoseSample):
        self._user_notification_signal.emit(_UserNotificationType.SUCCESS)
        self._container_updated_signal.emit()
        self._container.append_xyz_space_samples([sample])

    def _single_sample_timeout_cb(self):
        self._user_notification_signal.emit(_UserNotificationType.FAILURE)


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

        # Can not stop the timer from this thread, let it run.
        # self.timeout_timer.stop()

        angles_calibrated: dict[int, LighthouseBsVectors] = {}
        for bs_id, data in recorded_angles.items():
            angles_calibrated[bs_id] = data[1]

        result = LhCfPoseSample(angles_calibrated)
        self._ready_cb(result)


class _TableRowStatus(Enum):
    OK = 0
    INVALID = 1
    LARGE_ERROR = 2


class SampleTableModel(QAbstractTableModel):
    def __init__(self, parent=None, *args):
        QAbstractTableModel.__init__(self, parent)
        self._headers = ['Type', 'X', 'Y', 'Z', 'Err', 'Action']
        self._table_values = []
        self._table_highlights: list[_TableRowStatus] = []

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._table_values)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self._headers)

    def data(self, index: QModelIndex, role: Qt.ItemDataRole) -> QVariant:
        if index.isValid():
            if role == Qt.ItemDataRole.DisplayRole:
                if index.column() < len(self._table_values[index.row()]):
                    value = self._table_values[index.row()][index.column()]
                    return QVariant(value)

            if role == Qt.ItemDataRole.BackgroundRole:
                if self._table_highlights[index.row()] == _TableRowStatus.INVALID:
                    return QVariant(QtGui.QBrush(Qt.GlobalColor.gray))
                elif self._table_highlights[index.row()] == _TableRowStatus.LARGE_ERROR:
                    if index.column() == 4:
                        return QVariant(QtGui.QBrush(Qt.GlobalColor.red))

        return QVariant()

    def headerData(self, col, orientation, role=None):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return QVariant(self._headers[col])
        return QVariant()

    def setSolution(self, solution: LighthouseGeometrySolution):
        """Set the solution and update the table values"""
        self.beginResetModel()
        self._table_values = []
        self._table_highlights = []

        for sample in solution.samples:
            status = _TableRowStatus.OK
            x = y = z = '--'
            error = '--'

            if sample.is_valid:
                if sample.has_pose:
                    error = f'{sample.error_distance * 1000:.1f} mm'
                    pose = sample.pose
                    x = f'{pose.translation[0]:.2f}'
                    y = f'{pose.translation[1]:.2f}'
                    z = f'{pose.translation[2]:.2f}'

                    if sample.is_error_large:
                        status = _TableRowStatus.LARGE_ERROR
            else:
                error = f'{sample.status}'
                status = _TableRowStatus.INVALID

            self._table_values.append([
                f'{sample.sample_type}',
                x,
                y,
                z,
                error,
            ])
            self._table_highlights.append(status)

        self.endResetModel()
