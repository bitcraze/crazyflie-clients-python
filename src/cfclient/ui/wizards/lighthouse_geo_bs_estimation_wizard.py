# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2022-2023 Bitcraze AB
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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.

"""
Wizard to estimate the geometry of the lighthouse base stations.
Used in the lighthouse tab from the manage geometry dialog
"""

from __future__ import annotations

import cfclient
import logging

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


from PyQt6 import QtCore, QtWidgets, QtGui

logger = logging.getLogger(__name__)


REFERENCE_DIST = 1.0
ITERATION_MAX_NR = 2
DEFAULT_RECORD_TIME = 20
TIMEOUT_TIME = 2000
STRING_PAD_TOTAL = 6
WINDOW_STARTING_WIDTH = 780
WINDOW_STARTING_HEIGHT = 720
SPACER_LABEL_HEIGHT = 27
PICTURE_WIDTH = 640


class LighthouseBasestationGeometryWizard(QtWidgets.QWizard):
    def __init__(self, lighthouse_tab, ready_cb, parent=None, *args):
        super(LighthouseBasestationGeometryWizard, self).__init__(parent)
        self.lighthouse_tab = lighthouse_tab
        self.cf = lighthouse_tab._helper.cf
        self.container = LhGeoInputContainer(LhDeck4SensorPositions.positions)
        self.solver_thread = LhGeoEstimationManager.SolverThread(self.container, is_done_cb=self.solution_handler)
        self.ready_cb = ready_cb
        self.wizard_opened_first_time = True
        self.reset()

        logger.info("Wizard started")

    def reset(self):
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowCloseButtonHint)

        if not self.wizard_opened_first_time:
            self.removePage(0)
            self.removePage(1)
            self.removePage(2)
            self.removePage(3)
            del self._origin_page, self._xaxis_page, self._xyplane_page
            del self._xyzspace_page
        else:
            self.wizard_opened_first_time = False

        self._origin_page = RecordOriginSamplePage(self.cf, self.container, self)
        self._xaxis_page = RecordXAxisSamplePage(self.cf, self.container, self)
        self._xyplane_page = RecordXYPlaneSamplesPage(self.cf, self.container, self)
        self._xyzspace_page = RecordXYZSpaceSamplesPage(self.cf, self.container, self)

        self.addPage(self._origin_page)
        self.addPage(self._xaxis_page)
        self.addPage(self._xyplane_page)
        self.addPage(self._xyzspace_page)

        self.setWindowTitle("Lighthouse Base Station Geometry Wizard")
        self.resize(WINDOW_STARTING_WIDTH, WINDOW_STARTING_HEIGHT)

    def solution_handler(self, solution: LighthouseGeometrySolution):
        logger.info('Solution ready --------------------------------------')
        logger.info(f'Converged: {solution.has_converged}')
        logger.info(f'Progress info: {solution.progress_info}')
        logger.info(f'Progress is ok: {solution.progress_is_ok}')
        logger.info(f'Origin: {solution.is_origin_sample_valid}, {solution.origin_sample_info}')
        logger.info(f'X-axis: {solution.is_x_axis_samples_valid}, {solution.x_axis_samples_info}')
        logger.info(f'XY-plane: {solution.is_xy_plane_samples_valid}, {solution.xy_plane_samples_info}')
        logger.info(f'XYZ space: {solution.xyz_space_samples_info}')
        logger.info(f'General info: {solution.general_failure_info}')

        # Upload the geometry to the Crazyflie
        geo_dict = {}
        for bs_id, pose in solution.bs_poses.items():
            geo = LighthouseBsGeometry()
            geo.origin = pose.translation.tolist()
            geo.rotation_matrix = pose.rot_matrix.tolist()
            geo.valid = True
            geo_dict[bs_id] = geo

        logger.info('Uploading geometry to Crazyflie')
        self.lighthouse_tab.write_and_store_geometry(geo_dict)

    def showEvent(self, event):
        self.solver_thread.start()

    def closeEvent(self, event):
        self.solver_thread.stop()


class LighthouseBasestationGeometryWizardBasePage(QtWidgets.QWizardPage):

    def __init__(self, cf: Crazyflie, container: LhGeoInputContainer, show_add_measurements=False, parent=None):
        super(LighthouseBasestationGeometryWizardBasePage, self).__init__(parent)
        self.show_add_measurements = show_add_measurements
        self.cf = cf
        self.container = container
        self.layout = QtWidgets.QVBoxLayout()

        self.explanation_picture = QtWidgets.QLabel()
        self.explanation_picture.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.explanation_picture)

        self.explanation_text = QtWidgets.QLabel()
        self.explanation_text.setText(' ')
        self.explanation_text.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.explanation_text)

        self.layout.addStretch()

        self.extra_layout_field()

        self.status_text = QtWidgets.QLabel()
        self.status_text.setFont(QtGui.QFont('Courier New', 10))
        self.status_text.setText(self.str_pad(''))
        self.status_text.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Plain)
        self.layout.addWidget(self.status_text)

        self.start_action_button = QtWidgets.QPushButton("Start Measurement")
        self.start_action_button.clicked.connect(self._action_btn_clicked)
        action_button_h_box = QtWidgets.QHBoxLayout()
        action_button_h_box.addStretch()
        action_button_h_box.addWidget(self.start_action_button)
        action_button_h_box.addStretch()
        self.layout.addLayout(action_button_h_box)
        self.setLayout(self.layout)
        self.is_done = False
        self.too_few_bs = False
        self.timeout_timer = QtCore.QTimer()
        self.timeout_timer.timeout.connect(self._timeout_cb)
        self.reader = LighthouseSweepAngleAverageReader(self.cf, self._ready_cb)
        self.recorded_angle_result = None
        self.recorded_angles_result: list[LhCfPoseSample] = []

    def isComplete(self):
        return self.is_done and (self.too_few_bs is not True)

    def extra_layout_field(self):
        self.spacer = QtWidgets.QLabel()
        self.spacer.setText(' ')
        self.spacer.setFixedSize(50, SPACER_LABEL_HEIGHT)
        self.layout.addWidget(self.spacer)

    def _action_btn_clicked(self):
        self.is_done = False
        self.reader.start_angle_collection()
        self.timeout_timer.start(TIMEOUT_TIME)
        self.status_text.setText(self.str_pad('Collecting sweep angles...'))
        self.start_action_button.setDisabled(True)

    def _timeout_cb(self):
        if self.is_done is not True:
            self.status_text.setText(self.str_pad('No sweep angles recorded! \n' +
                                     'Make sure that the lighthouse base stations are turned on!'))
            self.reader.stop_angle_collection()
            self.start_action_button.setText("Restart Measurement")
            self.start_action_button.setDisabled(False)
        elif self.too_few_bs:
            self.timeout_timer.stop()

    def _ready_cb(self, averages):
        recorded_angles = averages
        angles_calibrated = {}
        for bs_id, data in recorded_angles.items():
            angles_calibrated[bs_id] = data[1]
        self.visible_basestations = ', '.join(map(lambda x: str(x + 1), recorded_angles.keys()))
        amount_of_basestations = len(recorded_angles.keys())

        if amount_of_basestations < 2:
            self.status_text.setText(self.str_pad('Recording Done!' +
                                                  f' Visible Base stations: {self.visible_basestations}\n' +
                                                  'Received too few base stations,' +
                                                  'we need at least two. Please try again!'))
            self.too_few_bs = True
            self.is_done = True
            if self.show_add_measurements and len(self.recorded_angles_result) > 0:
                self.too_few_bs = False
                self.completeChanged.emit()
            self.start_action_button.setText("Restart Measurement")
            self.start_action_button.setDisabled(False)
        else:
            self.store_sample(angles_calibrated)
            self.too_few_bs = False
            status_text_string = f'Recording Done! Visible Base stations: {self.visible_basestations}\n'
            if self.show_add_measurements:
                self.recorded_angles_result.append(self.get_sample())
                status_text_string += f'Total measurements added: {len(self.recorded_angles_result)}\n'
            self.status_text.setText(self.str_pad(status_text_string))
            self.is_done = True
            self.completeChanged.emit()

            if self.show_add_measurements:
                self.start_action_button.setText("Add more measurements")
                self.start_action_button.setDisabled(False)
            else:
                self.start_action_button.setText("Restart Measurement")
            self.start_action_button.setDisabled(False)

    def store_sample(self, angles: LhCfPoseSample) -> None:
        self.recorded_angle_result = angles

    def get_sample(self):
        return self.recorded_angle_result

    def str_pad(self, string_msg):
        new_string_msg = string_msg

        if string_msg.count('\n') < STRING_PAD_TOTAL:
            for i in range(STRING_PAD_TOTAL-string_msg.count('\n')):
                new_string_msg += '\n'

        return new_string_msg


class RecordOriginSamplePage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, container: LhGeoInputContainer, parent=None):
        super(RecordOriginSamplePage, self).__init__(cf, container)
        self.explanation_text.setText(
            'Step 1. Put the Crazyflie where you want the origin of your coordinate system.\n')
        pixmap = QtGui.QPixmap(cfclient.module_path + "/ui/wizards/bslh_1.png")
        pixmap = pixmap.scaledToWidth(PICTURE_WIDTH)
        self.explanation_picture.setPixmap(pixmap)

    def store_sample(self, angles: LhCfPoseSample) -> None:
        self.container.set_origin_sample(LhCfPoseSample(angles))
        super().store_sample(angles)


class RecordXAxisSamplePage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, container: LhGeoInputContainer, parent=None):
        super(RecordXAxisSamplePage, self).__init__(cf, container)
        self.explanation_text.setText('Step 2. Put the Crazyflie on the positive X-axis,' +
                                      f'  exactly {REFERENCE_DIST} meters from the origin.\n' +
                                      'This will be used to define the X-axis as well as scaling of the system.')
        pixmap = QtGui.QPixmap(cfclient.module_path + "/ui/wizards/bslh_2.png")
        pixmap = pixmap.scaledToWidth(PICTURE_WIDTH)
        self.explanation_picture.setPixmap(pixmap)

    def store_sample(self, angles: LhCfPoseSample) -> None:
        self.container.set_x_axis_sample(LhCfPoseSample(angles))
        super().store_sample(angles)


class RecordXYPlaneSamplesPage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, container: LhGeoInputContainer, parent=None):
        super(RecordXYPlaneSamplesPage, self).__init__(cf, container, show_add_measurements=True)
        self.explanation_text.setText('Step 3. Put the Crazyflie somewhere in the XY-plane, but not on the X-axis.\n' +
                                      'This position is used to map the the XY-plane to the floor.\n' +
                                      'You can sample multiple positions to get a more precise definition.')
        pixmap = QtGui.QPixmap(cfclient.module_path + "/ui/wizards/bslh_3.png")
        pixmap = pixmap.scaledToWidth(PICTURE_WIDTH)
        self.explanation_picture.setPixmap(pixmap)

    def store_sample(self, angles: LighthouseBsVectors) -> None:
        # measurement = LhMeasurement(timestamp=now, base_station_id=bs_id, angles=angles)
        self.container.append_xy_plane_sample(LhCfPoseSample(angles))
        super().store_sample(angles)

    def get_samples(self):
        return self.recorded_angles_result


class RecordXYZSpaceSamplesPage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, container: LhGeoInputContainer, parent=None):
        super(RecordXYZSpaceSamplesPage, self).__init__(cf, container)
        self.explanation_text.setText('Step 4. Sample points in the space that will be used.\n' +
                                      'Make sure all the base stations are received, you need at least two base \n' +
                                      'stations in each sample. Sample by rotating the Crazyflie quickly \n' +
                                      'left-right around the Z-axis and then holding it still for a second.\n')
        pixmap = QtGui.QPixmap(cfclient.module_path + "/ui/wizards/bslh_4.png")
        pixmap = pixmap.scaledToWidth(PICTURE_WIDTH)
        self.explanation_picture.setPixmap(pixmap)

        self.reader = LighthouseMatchedSweepAngleReader(self.cf, self._ready_single_sample_cb)
        self.detector = UserActionDetector(self.cf, cb=self.user_action_cb)

    def _action_btn_clicked(self):
        self.is_done = True
        self.start_action_button.setDisabled(True)
        self.detector.start()

    def user_action_cb(self):
        self.reader.start()

    def _ready_single_sample_cb(self, sample: LhCfPoseSample):
        self.container.append_xyz_space_samples([sample])

    def get_samples(self):
        return self.recorded_angles_result

    def _stop_all(self):
        self.reader.stop()
        if self.detector is not None:
            self.detector.stop()

    def cleanupPage(self):
        self._stop_all()
        super().cleanupPage()
