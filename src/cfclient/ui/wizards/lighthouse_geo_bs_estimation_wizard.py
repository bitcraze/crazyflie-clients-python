#!/usr/bin/env python

from PyQt5 import QtCore, QtWidgets
from cflib.crazyflie import Crazyflie
from cflib.localization.lighthouse_sweep_angle_reader import LighthouseSweepAngleAverageReader
from cflib.localization.lighthouse_sweep_angle_reader import LighthouseSweepAngleReader
from cflib.localization.lighthouse_bs_vector import LighthouseBsVectors
from cflib.localization.lighthouse_initial_estimator import LighthouseInitialEstimator
from cflib.localization.lighthouse_sample_matcher import LighthouseSampleMatcher
from cflib.localization.lighthouse_system_aligner import LighthouseSystemAligner
from cflib.localization.lighthouse_geometry_solver import LighthouseGeometrySolver
from cflib.localization.lighthouse_system_scaler import LighthouseSystemScaler
from cflib.crazyflie.mem.lighthouse_memory import LighthouseBsGeometry
from cflib.localization.lighthouse_config_manager import LighthouseConfigWriter
from cflib.localization.lighthouse_types import Pose, LhDeck4SensorPositions, LhMeasurement, LhCfPoseSample

import time


REFERENCE_DIST = 1.0
ITERATION_MAX_NR = 2
DEFAULT_RECORD_TIME = 20
TIMEOUT_TIME = 2000


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

        if not self.wizard_opened_first_time:
            self.removePage(0)
            self.removePage(1)
            self.removePage(2)
            self.removePage(3)
            self.removePage(4)
            del self.get_origin_page, self.get_xaxis_page, self.get_xyplane_page, self.get_xyzspace_page, self.get_geometry_page
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

        self.setWindowTitle("Lighthouse Basestation Geometry Wizard")
        self.resize(640, 480)


class LighthouseBasestationGeometryWizardBasePage(QtWidgets.QWizardPage):

    def __init__(self, cf: Crazyflie, show_fill_in_field, parent=None):
        super(LighthouseBasestationGeometryWizardBasePage, self).__init__(parent)
        self.cf = cf
        self.explanation_text = QtWidgets.QLabel()
        self.explanation_text.setText(' ')
        self.status_text = QtWidgets.QLabel()
        self.status_text.setText('')
        self.start_action_button = QtWidgets.QPushButton("Start Measurement")
        self.start_action_button.clicked.connect(self._action_btn_clicked)
        self.fill_record_times_line_edit = QtWidgets.QLineEdit(str(DEFAULT_RECORD_TIME))
        self.layout = QtWidgets.QVBoxLayout()
        self.layout.addWidget(self.explanation_text)
        if show_fill_in_field:
            self.layout.addWidget(self.fill_record_times_line_edit)
        self.layout.addStretch()

        self.layout.addWidget(self.start_action_button)
        self.layout.addStretch()

        self.layout.addWidget(self.status_text)
        self.layout.addStretch()

        self.setLayout(self.layout)
        self.is_done = False
        self.too_few_bs = False
        self.timeout_timer = QtCore.QTimer()
        self.timeout_timer.timeout.connect(self._timeout_cb)
        self.reader = LighthouseSweepAngleAverageReader(self.cf, self._ready_cb)
        self.recorded_angle_result = None

    # def isComplete(self):
    #    return self.is_done and (self.too_few_bs is not True)

    def _action_btn_clicked(self):
        self.is_done = False
        self.reader.start_angle_collection()
        self.timeout_timer.start(TIMEOUT_TIME)
        self.status_text.setText('Collecting sweep angles...')
        self.start_action_button.setDisabled(True)

    def _timeout_cb(self):
        if self.is_done is not True:
            self.status_text.setText('No sweep angles recorded! \n' +
                                     'Make sure that the lighthouse basestations are turned on!')
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
        self.recorded_angle_result = LhCfPoseSample(angles_calibrated=angles_calibrated)
        self.visible_basestations = ', '.join(map(lambda x: str(x + 1), recorded_angles.keys()))
        amount_of_basestations = len(recorded_angles.keys())

        self.start_action_button.setText("Restart Measurement")
        self.start_action_button.setDisabled(False)

        if amount_of_basestations < 2:
            self.status_text.setText(f'Recording Done! \n Visible Basestations: {self.visible_basestations}\n' +
                                     'Received too few base stations, we need at least two. Please try again!')
            self.too_few_bs = True
            self.is_done = True
        else:
            self.status_text.setText(f'Recording Done! \n Visible Basestations: {self.visible_basestations}\n')
            self.is_done = True
            self.completeChanged.emit()

    def get_sample(self):
        return self.recorded_angle_result


class RecordOriginSamplePage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(RecordOriginSamplePage, self).__init__(cf, False, parent)
        self.explanation_text.setText('Step 1. Put the Crazyflie where you want the origin of your coordinate system.')


class RecordXAxisSamplePage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(RecordXAxisSamplePage, self).__init__(cf, False, parent)
        self.explanation_text.setText('Step 2. Put the Crazyflie on the positive X-axis, \n' +
                                      f'  exactly {REFERENCE_DIST}  meters from the origin. \n\n ' +
                                      'This position defines the direction of the X-axis, \n' +
                                      '  but it is also used for scaling of the system.')


class RecordXYPlaneSamplesPage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(RecordXYPlaneSamplesPage, self).__init__(cf, False, parent)
        self.explanation_text.setText('Step 3. Put the Crazyflie somehere in the XY-plane, but not on the X-axis. \n')
        self.add_measurement_btn = QtWidgets.QPushButton("Add more measurements")
        self.add_measurement_btn.clicked.connect(self._add_measurement_btn_clicked)
        self.layout.addWidget(self.add_measurement_btn)
        self.setLayout(self.layout)
        self.recorded_angles_result: list[LhCfPoseSample] = []

    def _add_measurement_btn_clicked(self):
        self._action_btn_clicked()
        self.recorded_angles_result.append(self.get_sample())

    def get_samples(self):
        return self.recorded_angles_result


class RecordXYZSpaceSamplesPage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(RecordXYZSpaceSamplesPage, self).__init__(cf, True, parent)
        self.explanation_text.setText('Step 4.TODO \n')
        self.recorded_angles_result: list[LhCfPoseSample] = []
        self.show_fill_in_field = True
        self.record_timer = QtCore.QTimer()
        self.record_timer.timeout.connect(self._record_timer_cb)
        self.reader = LighthouseSweepAngleReader(self.cf, self._ready_single_sample_cb)
        self.bs_seen = set()

    def _record_timer_cb(self):
        self.reader.stop()
        self.status_text.setText(f'Recording Done! Got {len(self.recorded_angles_result)} samples!')
        self.start_action_button.setText("Restart Measurements")
        self.start_action_button.setDisabled(False)
        self.is_done = True
        self.completeChanged.emit()
        self.record_timer.stop()

    def _action_btn_clicked(self):
        self.is_done = False
        self.reader.start()
        self.record_timer.start(int(self.fill_record_times_line_edit.text())*1000)
        self.status_text.setText('Collecting sweep angles...')
        self.start_action_button.setDisabled(True)

    def _ready_single_sample_cb(self, bs_id: int, angles: LighthouseBsVectors):
        now = time.time()
        measurement = LhMeasurement(timestamp=now, base_station_id=bs_id, angles=angles)
        self.recorded_angles_result.append(measurement)
        self.bs_seen.add(str(bs_id + 1))

    def get_samples(self):
        return self.recorded_angles_result


class EstimateBSGeometryPage(LighthouseBasestationGeometryWizardBasePage):
    def __init__(self, cf: Crazyflie, origin_page: RecordOriginSamplePage, xaxis_page: RecordXAxisSamplePage,
                 xyplane_page: RecordXYPlaneSamplesPage, xyzspace_page: RecordXYZSpaceSamplesPage, parent=None):

        super(EstimateBSGeometryPage, self).__init__(cf, False, parent)
        self.explanation_text.setText('Step 5.TODO \n')

        self.start_action_button.setText('Estimate Geometry')
        self.origin_page = origin_page
        self.xaxis_page = xaxis_page
        self.xyplane_page = xyplane_page
        self.xyzspace_page = xyzspace_page

    def _action_btn_clicked(self):
        self.status_text.setText('Estimating geometry...')
        origin = self.origin_page.get_sample()
        x_axis = [self.xaxis_page.get_sample()]
        xy_plane = self.xyplane_page.get_samples()
        samples = self.xyzspace_page.get_samples()
        self.bs_poses = self._estimate_geometry(origin, x_axis, xy_plane, samples)
        self.is_done = True
        self.status_text.setText('Geometry estimated! \n\n' + self._print_base_stations_poses(self.bs_poses))
        self.completeChanged.emit()

    def _print_base_stations_poses(self, base_stations: dict[int, Pose]):
        """Pretty print of base stations pose"""
        bs_string = ''
        for bs_id, pose in sorted(base_stations.items()):
            pos = pose.translation
            temp_string = f'    {bs_id + 1}: ({pos[0]}, {pos[1]}, {pos[2]})'
            print(temp_string)
            bs_string += '\n' + temp_string

        return bs_string

    def _estimate_geometry(self, origin: LhCfPoseSample,
                           x_axis: list[LhCfPoseSample],
                           xy_plane: list[LhCfPoseSample],
                           samples: list[LhCfPoseSample]) -> dict[int, Pose]:
        """Estimate the geometry of the system based on samples recorded by a Crazyflie"""
        matched_samples = [origin] + x_axis + xy_plane + LighthouseSampleMatcher.match(samples, min_nr_of_bs_in_match=2)
        initial_guess = LighthouseInitialEstimator.estimate(matched_samples, LhDeck4SensorPositions.positions)

        print('Initial guess base stations at:')
        self._print_base_stations_poses(initial_guess.bs_poses)
        print(f'{len(matched_samples)} samples will be used')

        solution = LighthouseGeometrySolver.solve(initial_guess, matched_samples, LhDeck4SensorPositions.positions)
        if not solution.success:
            print('Solution did not converge, it might not be good!')

        start_x_axis = 1
        start_xy_plane = 1 + len(x_axis)
        origin_pos = solution.cf_poses[0].translation
        x_axis_poses = solution.cf_poses[start_x_axis:start_x_axis + len(x_axis)]
        x_axis_pos = list(map(lambda x: x.translation, x_axis_poses))
        xy_plane_poses = solution.cf_poses[start_xy_plane:start_xy_plane + len(xy_plane)]
        xy_plane_pos = list(map(lambda x: x.translation, xy_plane_poses))

        print('Raw solution:')
        print('  Base stations at:')
        self._print_base_stations_poses(solution.bs_poses)
        print('  Solution match per base station:')
        for bs_id, value in solution.error_info['bs'].items():
            print(f'    {bs_id + 1}: {value}')

        # Align the solution
        bs_aligned_poses, transformation = LighthouseSystemAligner.align(
            origin_pos, x_axis_pos, xy_plane_pos, solution.bs_poses)

        cf_aligned_poses = list(map(transformation.rotate_translate_pose, solution.cf_poses))

        # Scale the solution
        bs_scaled_poses, cf_scaled_poses, scale = LighthouseSystemScaler.scale_fixed_point(bs_aligned_poses,
                                                                                           cf_aligned_poses,
                                                                                           [REFERENCE_DIST, 0, 0],
                                                                                           cf_aligned_poses[1])

        self.is_done = True
        self.completeChanged.emit()

        print()
        print('Final solution:')
        print('  Base stations at:')
        self._print_base_stations_poses(bs_scaled_poses)

        return bs_scaled_poses

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
