# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2022 Bitcraze AB
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

from cflib.crazyflie import Crazyflie
from cflib.crazyflie.mem.lighthouse_memory import LighthouseBsGeometry
from cflib.localization.lighthouse_sweep_angle_reader import LighthouseSweepAngleAverageReader
from cflib.localization.lighthouse_sweep_angle_reader import LighthouseSweepAngleReader
from cflib.localization.lighthouse_bs_vector import LighthouseBsVectors
from cflib.localization.lighthouse_initial_estimator import LighthouseInitialEstimator
from cflib.localization.lighthouse_sample_matcher import LighthouseSampleMatcher
from cflib.localization.lighthouse_system_aligner import LighthouseSystemAligner
from cflib.localization.lighthouse_geometry_solver import LighthouseGeometrySolver
from cflib.localization.lighthouse_system_scaler import LighthouseSystemScaler
from cflib.localization.lighthouse_types import Pose, LhDeck4SensorPositions, LhMeasurement, LhCfPoseSample

from PyQt5 import QtCore, QtWidgets, QtGui
import time


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
    def __init__(self, cf, ready_cb, parent=None, *args):
        super(LighthouseBasestationGeometryWizard, self).__init__(parent)
        self.cf = cf
        self.ready_cb = ready_cb
        self.wizard_opened_first_time = True
        self.reset()

        self.button(QtWidgets.QWizard.FinishButton).clicked.connect(self._finish_button_clicked_callback)

    def _finish_button_clicked_callback(self):
        self.ready_cb(self.get_geometry_page.get_geometry())

    def reset(self):
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowCloseButtonHint)

        if not self.wizard_opened_first_time:
            self.removePage(0)
            self.removePage(1)
            self.removePage(2)
            self.removePage(3)
            self.removePage(4)
            del self.get_origin_page, self.get_xaxis_page, self.get_xyplane_page
            del self.get_xyzspace_page, self.get_geometry_page
        else:
            self.wizard_opened_first_time = False

        self.get_origin_page = RecordOriginSamplePage(self.cf, self)
        self.get_xaxis_page = RecordXAxisSamplePage(self.cf, self)
        self.get_xyplane_page = RecordXYPlaneSamplesPage(self.cf, self)
        self.get_xyzspace_page = RecordXYZSpaceSamplesPage(self.cf, self)
        self.get_geometry_page = EstimateBSGeometryPage(
            self.cf, self.get_origin_page, self.get_xaxis_page, self.get_xyplane_page, self.get_xyzspace_page, self)

        self.addPage(self.get_origin_page)
        self.addPage(self.get_xaxis_page)
        self.addPage(self.get_xyplane_page)
        self.addPage(self.get_xyzspace_page)
        self.addPage(self.get_geometry_page)

        self.setWindowTitle("Lighthouse Base Station Geometry Wizard")
        self.resize(WINDOW_STARTING_WIDTH, WINDOW_STARTING_HEIGHT)


class LighthouseBasestationGeometryWizardBasePage(QtWidgets.QWizardPage):

    def __init__(self, cf: Crazyflie, show_add_measurements=False, parent=None):
        super(LighthouseBasestationGeometryWizardBasePage, self).__init__(parent)
        self.show_add_measurements = show_add_measurements
        self.cf = cf
        self.layout = QtWidgets.QVBoxLayout()

        self.explanation_picture = QtWidgets.QLabel()
        self.explanation_picture.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.explanation_picture)

        self.explanation_text = QtWidgets.QLabel()
        self.explanation_text.setText(' ')
        self.explanation_text.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.explanation_text)

        self.layout.addStretch()

        self.extra_layout_field()

        self.status_text = QtWidgets.QLabel()
        self.status_text.setFont(QtGui.QFont('Courier New', 10))
        self.status_text.setText(self.str_pad(''))
        self.status_text.setFrameStyle(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Plain)
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
        print(self.show_add_measurements)
        recorded_angles = averages
        angles_calibrated = {}
        for bs_id, data in recorded_angles.items():
            angles_calibrated[bs_id] = data[1]
        self.recorded_angle_result = LhCfPoseSample(angles_calibrated=angles_calibrated)
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

    def get_sample(self):
        return self.recorded_angle_result

    def str_pad(self, string_msg):
        new_string_msg = string_msg

        if string_msg.count('\n') < STRING_PAD_TOTAL:
            for i in range(STRING_PAD_TOTAL-string_msg.count('\n')):
                new_string_msg += '\n'

        return new_string_msg


class RecordOriginSamplePage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(RecordOriginSamplePage, self).__init__(cf)
        self.explanation_text.setText(
            'Step 1. Put the Crazyflie where you want the origin of your coordinate system.\n')
        pixmap = QtGui.QPixmap(cfclient.module_path + "/ui/wizards/bslh_1.png")
        pixmap = pixmap.scaledToWidth(PICTURE_WIDTH)
        self.explanation_picture.setPixmap(pixmap)


class RecordXAxisSamplePage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(RecordXAxisSamplePage, self).__init__(cf)
        self.explanation_text.setText('Step 2. Put the Crazyflie on the positive X-axis,' +
                                      f'  exactly {REFERENCE_DIST} meters from the origin.\n' +
                                      'This will be used to define the X-axis as well as scaling of the system.')
        pixmap = QtGui.QPixmap(cfclient.module_path + "/ui/wizards/bslh_2.png")
        pixmap = pixmap.scaledToWidth(PICTURE_WIDTH)
        self.explanation_picture.setPixmap(pixmap)


class RecordXYPlaneSamplesPage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(RecordXYPlaneSamplesPage, self).__init__(cf, show_add_measurements=True)
        self.explanation_text.setText('Step 3. Put the Crazyflie somewhere in the XY-plane, but not on the X-axis.\n' +
                                      'This position is used to map the the XY-plane to the floor.\n' +
                                      'You can sample multiple positions to get a more precise definition.')
        pixmap = QtGui.QPixmap(cfclient.module_path + "/ui/wizards/bslh_3.png")
        pixmap = pixmap.scaledToWidth(PICTURE_WIDTH)
        self.explanation_picture.setPixmap(pixmap)

    def get_samples(self):
        return self.recorded_angles_result


class RecordXYZSpaceSamplesPage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(RecordXYZSpaceSamplesPage, self).__init__(cf)
        self.explanation_text.setText('Step 4. Move the Crazyflie around, try to cover all of the flying space,\n' +
                                      'make sure all the base stations are received.\n' +
                                      'Avoid moving too fast, you can increase the record time if needed.\n')
        pixmap = QtGui.QPixmap(cfclient.module_path + "/ui/wizards/bslh_4.png")
        pixmap = pixmap.scaledToWidth(PICTURE_WIDTH)
        self.explanation_picture.setPixmap(pixmap)

        self.record_timer = QtCore.QTimer()
        self.record_timer.timeout.connect(self._record_timer_cb)
        self.record_time_total = DEFAULT_RECORD_TIME
        self.record_time_current = 0
        self.reader = LighthouseSweepAngleReader(self.cf, self._ready_single_sample_cb)
        self.bs_seen = set()

    def extra_layout_field(self):
        h_box = QtWidgets.QHBoxLayout()
        self.seconds_explanation_text = QtWidgets.QLabel()
        self.fill_record_times_line_edit = QtWidgets.QLineEdit(str(DEFAULT_RECORD_TIME))
        self.seconds_explanation_text.setText('Enter the number of seconds you want to record:')
        h_box.addStretch()
        h_box.addWidget(self.seconds_explanation_text)
        h_box.addWidget(self.fill_record_times_line_edit)
        h_box.addStretch()
        self.layout.addLayout(h_box)

    def _record_timer_cb(self):
        self.record_time_current += 1
        self.status_text.setText(self.str_pad('Collecting sweep angles...' +
                                 f' seconds remaining: {self.record_time_total-self.record_time_current}'))

        if self.record_time_current == self.record_time_total:
            self.reader.stop()
            self.status_text.setText(self.str_pad(
                'Recording Done!'+f' Got {len(self.recorded_angles_result)} samples!'))
            self.start_action_button.setText("Restart measurements")
            self.start_action_button.setDisabled(False)
            self.is_done = True
            self.completeChanged.emit()
            self.record_timer.stop()

    def _action_btn_clicked(self):
        self.is_done = False
        self.reader.start()
        self.record_time_current = 0
        self.record_time_total = int(self.fill_record_times_line_edit.text())
        self.record_timer.start(1000)
        self.status_text.setText(self.str_pad('Collecting sweep angles...' +
                                 f' seconds remaining: {self.record_time_total}'))

        self.start_action_button.setDisabled(True)

    def _ready_single_sample_cb(self, bs_id: int, angles: LighthouseBsVectors):
        now = time.time()
        measurement = LhMeasurement(timestamp=now, base_station_id=bs_id, angles=angles)
        self.recorded_angles_result.append(measurement)
        self.bs_seen.add(str(bs_id + 1))

    def get_samples(self):
        return self.recorded_angles_result


class EstimateGeometryThread(QtCore.QObject):
    finished = QtCore.pyqtSignal()
    failed = QtCore.pyqtSignal()

    def __init__(self, origin, x_axis, xy_plane, samples):
        super(EstimateGeometryThread, self).__init__()

        self.origin = origin
        self.x_axis = x_axis
        self.xy_plane = xy_plane
        self.samples = samples
        self.bs_poses = {}

    def run(self):
        try:
            self.bs_poses = self._estimate_geometry(self.origin, self.x_axis, self.xy_plane, self.samples)
            self.finished.emit()
        except Exception as ex:
            print(ex)
            self.failed.emit()

    def get_poses(self):
        return self.bs_poses

    def _estimate_geometry(self, origin: LhCfPoseSample,
                           x_axis: list[LhCfPoseSample],
                           xy_plane: list[LhCfPoseSample],
                           samples: list[LhCfPoseSample]) -> dict[int, Pose]:
        """Estimate the geometry of the system based on samples recorded by a Crazyflie"""
        matched_samples = [origin] + x_axis + xy_plane + LighthouseSampleMatcher.match(samples, min_nr_of_bs_in_match=2)
        initial_guess, cleaned_matched_samples = LighthouseInitialEstimator.estimate(matched_samples,
                                                                                     LhDeck4SensorPositions.positions)

        solution = LighthouseGeometrySolver.solve(initial_guess,
                                                  cleaned_matched_samples,
                                                  LhDeck4SensorPositions.positions)
        if not solution.success:
            raise Exception("No lighthouse base station geometry solution could be found!")

        start_x_axis = 1
        start_xy_plane = 1 + len(x_axis)
        origin_pos = solution.cf_poses[0].translation
        x_axis_poses = solution.cf_poses[start_x_axis:start_x_axis + len(x_axis)]
        x_axis_pos = list(map(lambda x: x.translation, x_axis_poses))
        xy_plane_poses = solution.cf_poses[start_xy_plane:start_xy_plane + len(xy_plane)]
        xy_plane_pos = list(map(lambda x: x.translation, xy_plane_poses))

        # Align the solution
        bs_aligned_poses, transformation = LighthouseSystemAligner.align(
            origin_pos, x_axis_pos, xy_plane_pos, solution.bs_poses)

        cf_aligned_poses = list(map(transformation.rotate_translate_pose, solution.cf_poses))

        # Scale the solution
        bs_scaled_poses, cf_scaled_poses, scale = LighthouseSystemScaler.scale_fixed_point(bs_aligned_poses,
                                                                                           cf_aligned_poses,
                                                                                           [REFERENCE_DIST, 0, 0],
                                                                                           cf_aligned_poses[1])

        return bs_scaled_poses


class EstimateBSGeometryPage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, origin_page: RecordOriginSamplePage, xaxis_page: RecordXAxisSamplePage,
                 xyplane_page: RecordXYPlaneSamplesPage, xyzspace_page: RecordXYZSpaceSamplesPage, parent=None):

        super(EstimateBSGeometryPage, self).__init__(cf)
        self.explanation_text.setText('Step 5. Press the button to estimate the geometry and check the result.\n' +
                                      'If the positions of the base stations look reasonable, press finish to close ' +
                                      'the wizard,\n' +
                                      'if not restart the wizard.')
        pixmap = QtGui.QPixmap(cfclient.module_path + "/ui/wizards/bslh_5.png")
        pixmap = pixmap.scaledToWidth(640)
        self.explanation_picture.setPixmap(pixmap)
        self.start_action_button.setText('Estimate Geometry')
        self.origin_page = origin_page
        self.xaxis_page = xaxis_page
        self.xyplane_page = xyplane_page
        self.xyzspace_page = xyzspace_page
        self.bs_poses = {}

    def _action_btn_clicked(self):
        self.start_action_button.setDisabled(True)
        self.status_text.setText(self.str_pad('Estimating geometry...'))
        origin = self.origin_page.get_sample()
        x_axis = [self.xaxis_page.get_sample()]
        xy_plane = self.xyplane_page.get_samples()
        samples = self.xyzspace_page.get_samples()
        self.thread_estimator = QtCore.QThread()
        self.worker = EstimateGeometryThread(origin, x_axis, xy_plane, samples)
        self.worker.moveToThread(self.thread_estimator)
        self.thread_estimator.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread_estimator.quit)
        self.worker.finished.connect(self._geometry_estimated_finished)
        self.worker.failed.connect(self._geometry_estimated_failed)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread_estimator.finished.connect(self.thread_estimator.deleteLater)
        self.thread_estimator.start()

    def _geometry_estimated_finished(self):
        self.bs_poses = self.worker.get_poses()
        self.start_action_button.setDisabled(False)
        self.status_text.setText(self.str_pad('Geometry estimated! (X,Y,Z) in meters \n' +
                                 self._print_base_stations_poses(self.bs_poses)))
        self.is_done = True
        self.completeChanged.emit()

    def _geometry_estimated_failed(self):
        self.bs_poses = self.worker.get_poses()
        self.status_text.setText(self.str_pad('Geometry estimate failed! \n' +
                                              'Hit Cancel to close the wizard and start again'))

    def _print_base_stations_poses(self, base_stations: dict[int, Pose]):
        """Pretty print of base stations pose"""
        bs_string = ''
        for bs_id, pose in sorted(base_stations.items()):
            pos = pose.translation
            temp_string = f'    {bs_id + 1}: ({pos[0]}, {pos[1]}, {pos[2]})'
            bs_string += '\n' + temp_string

        return bs_string

    def get_geometry(self):
        geo_dict = {}
        for bs_id, pose in self.bs_poses.items():
            geo = LighthouseBsGeometry()
            geo.origin = pose.translation.tolist()
            geo.rotation_matrix = pose.rot_matrix.tolist()
            geo.valid = True
            geo_dict[bs_id] = geo

        return geo_dict


if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    wizard = LighthouseBasestationGeometryWizard()
    wizard.show()
    sys.exit(app.exec_())
