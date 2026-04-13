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
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QTimer

import logging
from enum import Enum
import threading

import cfclient

from cfclient.ui.widgets.info_label import InfoLabel
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
    ORIGIN = ('step_origin.png',
              'Place the crazyflie where you want the origin of your coordinate system to be.',
              'Start measurement',
              "The orientation of the Crazyflie does not matter — only its absolute position.")
    X_AXIS = ('step_x_axis.png',
              'Put the crazyflie on the positive X-axis, 1m from the origin.',
              'Start measurement',
              "A tape measure and visual alignment is accurate enough for most spaces.\n\n"
              "For very large spaces with many base stations, see the documentation for more precise placement advice.")
    XY_PLANE = ('step_xy_plane.png',
                'Put the Crazyflie somewhere in the XY-plane, but not on the X-axis. This sample is used to map the XY-plane to the floor.',
                'Start measurement',
                "This sample maps the XY plane to the floor.\n\n"
                "Taking samples at multiple positions gives a more precise approximation.")
    XYZ_SPACE = ('step_xyz_space.png',
                 'Pick up the crazyflie and take to an area in the flightspace where you expect to fly. Take an XYZ sample by quickly rotating the Crazyflie in a left-right motion about the z-axis. Then wait for confirmation. Repeat the processes in a few key additional areas.',
                 'Sample position',
                 "Hold the Crazyflie still after rotation and wait for confirmation.\n\n"
                 "A sample will fail if the Crazyflie moves after rotation or can only see one base station.")
    VERIFICATION = ('step_verification.png',
                    'Verification samples are taken just like XYZ samples. If the verification sample error is high, then add XYZ samples around the verification sample to reduce the error.',
                    'Sample position',
                    "Verification samples check the accuracy of areas between XYZ sample locations.\n\n"
                    "Low error here means the system works reliably across the full flight space, "
                    "not just at the sampled positions.\n\n"
                    "If the error is high, add more XYZ samples near the verification location.")

    def __init__(self, image, instructions, button_text, info):
        self.image = image
        self.instructions = instructions
        self.button_text = button_text
        self.info = info

        self._order = None

    @property
    def order(self):
        """Get the order of the steps in the collection process"""
        if self._order is None:
            self._order = [self.ORIGIN,
                           self.X_AXIS,
                           self.XY_PLANE,
                           self.XYZ_SPACE,
                           self.VERIFICATION]
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


class _UploadStatus(Enum):
    NOT_STARTED = "not_started"
    UPLOADING_SAMPLE_SOLUTION = "uploading_sample_solution"
    UPLOADING_FILE_CONFIG = "uploading_file_config"
    SAMPLE_SOLUTION_DONE = "sample_solution_done"
    FILE_CONFIG_DONE = "file_config_done"


STYLE_GREEN_BACKGROUND = "background-color: lightgreen;"
STYLE_RED_BACKGROUND = "background-color: lightpink;"
STYLE_YELLOW_BACKGROUND = "background-color: lightyellow;"
STYLE_NO_BACKGROUND = "background-color: none;"

STYLE_GROUPBOX_GREEN = "QGroupBox { background-color: lightgreen; }"
STYLE_GROUPBOX_RED = "QGroupBox { background-color: lightpink; }"
STYLE_GROUPBOX_YELLOW = "QGroupBox { background-color: lightyellow; }"


class GeoEstimatorWidget(QtWidgets.QWidget, geo_estimator_widget_class):
    """Widget for the geometry estimator UI"""

    _timeout_reader_signal = QtCore.pyqtSignal(object)
    _container_updated_signal = QtCore.pyqtSignal()
    _user_notification_signal = QtCore.pyqtSignal(object)
    _start_solving_signal = QtCore.pyqtSignal()
    solution_ready_signal = QtCore.pyqtSignal(object)

    FILE_REGEX_YAML = "Config *.yaml;;All *.*"

    def __init__(self, lighthouse_tab):
        super(GeoEstimatorWidget, self).__init__()
        self.setupUi(self)

        self._lighthouse_tab = lighthouse_tab
        self._helper = lighthouse_tab._helper

        self._step_measure.clicked.connect(self._measure)

        self._clear_all_button.clicked.connect(self._clear_all)
        self._import_samples_button.clicked.connect(lambda: self._load_samples_from_file(use_session_path=True))
        self._export_samples_button.clicked.connect(self._save_samples_to_file)

        self._upload_status = _UploadStatus.NOT_STARTED

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
        self._collected_steps: set[_CollectionStep] = set()
        # self._origin_radio.setChecked(True)

        self._origin_col = self._wrap_column(self.gridLayout, 0, self._origin_icon, self.label_6)
        self._x_axis_col = self._wrap_column(self.gridLayout, 1, self._x_axis_icon, self.label_7)
        self._xy_col = self._wrap_column(self.gridLayout, 2, self._xy_plane_icon, self.label_8)
        self._xyz_col = self._wrap_column(self.gridLayout, 3, self._xyz_space_icon, self.label_10)
        self._verification_col = self._wrap_column(self.gridLayout, 5, self._verification_icon, self.label_9)

        self._start_solving_signal.connect(self._start_solving_cb)
        self.solution_ready_signal.connect(self._solution_ready_cb)
        self._is_solving = False
        self._solver_thread = None

        self._step_instructions_info_label = InfoLabel("Instructions for the current step.", self._step_instructions, position=InfoLabel.Position.BOTTOM_RIGHT)
        self._solution_status_info_label = InfoLabel(
            'A successful upload does not guarantee stable flight.\n'
            'Try to minimize the max sample errors before take off.\n'
            '\n'
            'For more info, see Sample Details.',
            self._solution_status_widget)

        self._update_step_ui()
        self._update_ui_reading(False)
        self._update_solution_info()

        # self._origin_radio.clicked.connect(lambda: self._change_step(_CollectionStep.ORIGIN))
        # self._x_axis_radio.clicked.connect(lambda: self._change_step(_CollectionStep.X_AXIS))
        # self._xy_plane_radio.clicked.connect(lambda: self._change_step(_CollectionStep.XY_PLANE))
        # self._xyz_space_radio.clicked.connect(lambda: self._change_step(_CollectionStep.XYZ_SPACE))
        # self._verification_radio.clicked.connect(lambda: self._change_step(_CollectionStep.VERIFICATION))
        self._previous_sample.clicked.connect(lambda: self._change_step(self._current_step.previous()))
        self._next_sample.clicked.connect(lambda: self._change_step(self._current_step.next()))
        self._hide_details.setChecked(True)  # Hide details by default

    def _start_geo_file_upload(self):
        if self._lighthouse_tab.load_sys_config_user_action():
            self._upload_status = _UploadStatus.UPLOADING_FILE_CONFIG

            # Clear all samples as the new configuration is based on some other (unknown) set of samples
            self.new_session()

    def setVisible(self, visible: bool):
        super(GeoEstimatorWidget, self).setVisible(visible)
        if visible:
            if self._solver_thread is None:
                logger.info("Starting solver thread")
                self._solver_thread = LhGeoEstimationManager.SolverThread(self._container,
                                                                          is_done_cb=self.solution_ready_signal.emit,
                                                                          is_starting_estimation_cb=(
                                                                              self._start_solving_signal.emit))
                self._solver_thread.start()
        else:
            self._action_detector.stop()
            if self._solver_thread is not None:
                logger.info("Stopping solver thread")
                self._solver_thread.stop(do_join=False)
                self._solver_thread = None

    def new_session(self):
        self._collected_steps.clear()
        self._container.clear_all_samples()

    def _clear_all(self):
        if not self.is_container_empty():
            dlg = QMessageBox(self)
            dlg.setWindowTitle("Clear samples Confirmation")
            dlg.setText("Are you sure you want to clear all samples and start over?")
            dlg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            button = dlg.exec()

            if button == QMessageBox.StandardButton.Yes:
                self.new_session()

    def is_container_empty(self) -> bool:
        """Check if the container has any samples"""
        return self._container.is_empty()

    def remove_sample(self, uid: int) -> None:
        """Delete a sample by its unique ID"""
        self._container.remove_sample(uid)

    def convert_to_xyz_space_sample(self, uid: int) -> None:
        """Convert a sample to an xyz-space sample by its unique ID"""
        self._container.convert_to_xyz_space_sample(uid)

    def convert_to_verification_sample(self, uid: int) -> None:
        """Convert a sample to a verification sample by its unique ID"""
        self._container.convert_to_verification_sample(uid)

    def cf_connected_cb(self, link_uri: str):
        """Callback when the Crazyflie has connected"""
        self._upload_status = _UploadStatus.NOT_STARTED
        self._update_solution_info()

    def geometry_has_been_read_back_cb(self):
        """Callback when the geometry has been read back from the Crazyflie after an upload, that is the full
        round-trip is done. Called from the tab."""
        if self._upload_status == _UploadStatus.UPLOADING_SAMPLE_SOLUTION:
            self._upload_status = _UploadStatus.SAMPLE_SOLUTION_DONE
        elif self._upload_status == _UploadStatus.UPLOADING_FILE_CONFIG:
            self._upload_status = _UploadStatus.FILE_CONFIG_DONE

        self._update_solution_info()

    def _load_samples_from_file(self, use_session_path=False):
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

    def _save_samples_to_file(self):
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

    def _change_step(self, step):
        """Update the widget to display the new step"""
        if step != self._current_step:
            self._current_step = step
            self._update_step_ui()
            if step in [_CollectionStep.XYZ_SPACE, _CollectionStep.VERIFICATION]:
                self._action_detector.start()
            else:
                self._action_detector.stop()

    _STEP_COLUMN_WIDGETS = None

    def _step_column_widgets(self):
        """Map each collection step to the layout in its grid column"""
        if not hasattr(self, '_step_column_widgets_cache'):
            self._step_column_widgets_cache = {
                _CollectionStep.ORIGIN: self._origin_col,
                _CollectionStep.X_AXIS: self._x_axis_col,
                _CollectionStep.XY_PLANE: self._xy_col,
                _CollectionStep.XYZ_SPACE: self._xyz_col,
                _CollectionStep.VERIFICATION: self._verification_col,
            }
        return self._step_column_widgets_cache

    def _update_step_ui(self):
        """Populate the widget with the current step's information"""
        step = self._current_step

        self._set_label_icon(self._step_image, step.image)
        self._step_instructions.setText(step.instructions)
        self._step_instructions_info_label.setToolTip(step.info)
        self._step_info.setText('')
        retakeable = {_CollectionStep.ORIGIN, _CollectionStep.X_AXIS, _CollectionStep.XY_PLANE}
        if step in retakeable and step in self._collected_steps:
            self._step_measure.setText('Retake measurement')
        else:
            self._step_measure.setText(step.button_text)
        self._previous_sample.setEnabled(self._current_step.has_previous())
        self._next_sample.setEnabled(self._current_step.has_next())

        self._update_step_highlight()
        self._update_solution_info()

    @staticmethod
    def _wrap_column(grid, col, icon, label):
        """Wrap a bare grid-column layout in a QWidget so it can be styled."""
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        icon.setParent(container)
        label.setParent(container)
        layout.addWidget(icon)
        layout.addWidget(label)
        grid.addWidget(container, 1, col)
        return container

    def _update_step_highlight(self):
        """Highlight the grid column corresponding to the current step"""
        for s, frame in self._step_column_widgets().items():
            style = "QWidget { border: 2px solid gray; border-radius: 4px; padding: 4px; background: transparent; } QLabel { border: none; padding: 4px; background: transparent; }" if s == self._current_step else ""
            frame.setStyleSheet(style)

    _STEP_IMAGE_SIZE = QtCore.QSize(460, 266)

    def _set_label_icon(self, label: QtWidgets.QLabel, icon_file_name: str):
        """Set the icon of a label widget"""
        path = cfclient.module_path + '/ui/widgets/geo_estimator_resources/' + icon_file_name
        pixmap = QtGui.QPixmap(path)
        if icon_file_name.startswith('step_'):
            pixmap = pixmap.scaled(self._STEP_IMAGE_SIZE, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                                   QtCore.Qt.TransformationMode.SmoothTransformation)
        label.setPixmap(pixmap)

    def _update_ui_reading(self, is_reading: bool):
        """Update the UI to reflect whether a reading is in progress, that is enable/disable buttons"""
        is_enabled = not is_reading

        self._step_measure.setEnabled(is_enabled)

        # self._origin_radio.setEnabled(is_enabled)
        # self._x_axis_radio.setEnabled(is_enabled)
        # self._xy_plane_radio.setEnabled(is_enabled)
        # self._xyz_space_radio.setEnabled(is_enabled)
        # self._verification_radio.setEnabled(is_enabled)
        self._previous_sample.setEnabled(is_enabled and self._current_step.has_previous())
        self._next_sample.setEnabled(is_enabled and self._current_step.has_next())

        self._import_samples_button.setEnabled(is_enabled)
        self._export_samples_button.setEnabled(is_enabled)
        self._clear_all_button.setEnabled(is_enabled)

    def _get_step_icon(self, is_valid: bool) -> str:
        """Get the icon file name based on validity"""
        if is_valid:
            return 'checkmark.png'
        else:
            return 'crossmark.png'

    def _update_solution_info(self):
        solution = self._latest_solution

        self._set_label_icon(self._origin_icon, self._get_step_icon(solution.is_origin_sample_valid))
        self._set_label_icon(self._x_axis_icon, self._get_step_icon(solution.is_x_axis_samples_valid))
        self._set_label_icon(self._xy_plane_icon, self._get_step_icon(solution.is_xy_plane_samples_valid))
        self._xyz_space_icon.setText(f'({self._container.xyz_space_sample_count()})')
        self._verification_icon.setText(f'({self._container.verification_sample_count()})')

        if self._is_solving:
            self._solution_status_info.setText('Updating...')
            self._set_background_none(self._solution_status_info)
        else:
            background_color_is_ok = solution.progress_is_ok

            solution_error = '--'
            verification_error = '--'

            if solution.progress_is_ok:
                if self._upload_status == _UploadStatus.UPLOADING_SAMPLE_SOLUTION:
                    self._solution_status_info.setText('Uploading...')
                elif self._upload_status == _UploadStatus.SAMPLE_SOLUTION_DONE:
                    self._solution_status_info.setText('Uploaded')

                solution_error = f'{solution.error_stats.max * 1000:.1f} mm (max)'

                if solution.verification_stats:
                    verification_error = f'{solution.verification_stats.max * 1000:.1f} mm (max)'
            else:
                no_samples = not solution.contains_samples
                if no_samples and self._upload_status == _UploadStatus.FILE_CONFIG_DONE:
                    self._solution_status_info.setText('Uploaded (imported config)')
                    background_color_is_ok = True
                else:
                    self._solution_status_info.setText('Not enough samples')

            self._solution_status_max_error.setText(f'{solution_error}')
            self._solution_status_verification_error.setText(f'{verification_error}')
            self._set_background_color(self._solution_status_info, background_color_is_ok)

    def _notify_user(self, notification_type: _UserNotificationType):
        timeout = 1000
        match notification_type:
            case _UserNotificationType.SUCCESS:
                self._helper.cf.platform.send_user_notification(True)
                self._sample_collection_box.setStyleSheet(STYLE_GROUPBOX_GREEN)
                self._update_ui_reading(False)
                retakeable = {_CollectionStep.ORIGIN, _CollectionStep.X_AXIS, _CollectionStep.XY_PLANE}
                if self._current_step in retakeable:
                    self._collected_steps.add(self._current_step)
                    self._step_measure.setText('Retake measurement')
            case _UserNotificationType.FAILURE:
                self._helper.cf.platform.send_user_notification(False)
                self._sample_collection_box.setStyleSheet(STYLE_GROUPBOX_RED)
                self._update_ui_reading(False)
            case _UserNotificationType.PENDING:
                self._sample_collection_box.setStyleSheet(STYLE_GROUPBOX_YELLOW)
                self._update_ui_reading(True)
                timeout = 3000

        self._user_notification_clear_timer.stop()
        self._user_notification_clear_timer.start(timeout)

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
                self._measure_single_sample()
            case _CollectionStep.VERIFICATION:
                self._measure_single_sample()

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

    def _measure_single_sample(self):
        """Measure a single sample. Used both for xyz-space and verification"""
        logger.debug("Measuring single sample...")
        self._user_notification_signal.emit(_UserNotificationType.PENDING)
        self._matched_reader.start(timeout=1.0)

    def _start_timeout_average_read(self, setter: Callable[[LhCfPoseSample], None]):
        """Start the timeout average angle reader"""
        self._timeout_reader.start()
        self._timeout_reader_result_setter = setter
        self._step_info.setText("Collecting angles...")
        self._update_ui_reading(True)
        self._user_notification_signal.emit(_UserNotificationType.PENDING)

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
        # Called when the solver thread has a new solution ready
        self._is_solving = False
        self._latest_solution = solution

        logger.debug('Solution ready --------------------------------------')
        logger.debug(f'Converged: {solution.has_converged}')
        logger.debug(f'Progress info: {solution.progress_info}')
        logger.debug(f'Progress is ok: {solution.progress_is_ok}')
        logger.debug(f'Origin: {solution.is_origin_sample_valid}, {solution.origin_sample_info}')
        logger.debug(f'X-axis: {solution.is_x_axis_samples_valid}, {solution.x_axis_samples_info}')
        logger.debug(f'XY-plane: {solution.is_xy_plane_samples_valid}, {solution.xy_plane_samples_info}')
        logger.debug(f'XYZ space: {solution.xyz_space_samples_info}')
        logger.debug(f'General info: {solution.general_failure_info}')

        if solution.progress_is_ok:
            no_samples = not solution.contains_samples
            if (self._upload_status == _UploadStatus.UPLOADING_FILE_CONFIG or
                    self._upload_status == _UploadStatus.FILE_CONFIG_DONE) and no_samples:
                # If we imported a config file and started an upload all samples are cleared and we will end up here
                # when the solver is done. We don't want to change the upload status in this case as the status will
                # show that there are no samples.
                pass
            else:
                self._upload_status = _UploadStatus.UPLOADING_SAMPLE_SOLUTION

            self._upload_geometry(solution.bs_poses)

        self._update_solution_info()

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
        self._measure_single_sample()

    def _single_sample_ready_cb(self, sample: LhCfPoseSample):
        self._user_notification_signal.emit(_UserNotificationType.SUCCESS)
        self._container_updated_signal.emit()
        match self._current_step:
            case _CollectionStep.XYZ_SPACE:
                self._container.append_xyz_space_samples([sample])
            case _CollectionStep.VERIFICATION:
                self._container.append_verification_samples([sample])

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
