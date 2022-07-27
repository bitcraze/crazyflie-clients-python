#!/usr/bin/env python

from PyQt5 import QtCore
from PyQt5 import QtCore, QtWidgets
from cflib.crazyflie import Crazyflie
from cflib.localization.lighthouse_sweep_angle_reader import LighthouseSweepAngleAverageReader, LighthouseSweepAngleReader
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
    def __init__(self, lighthouse_tab, parent=None, *args):
        super(LighthouseBasestationGeometryWizard, self).__init__(parent)
        self._lighthouse_tab = lighthouse_tab
        self.cf = self._lighthouse_tab._helper.cf
        page1 = Page1(self.cf, self)
        page2 = Page2(self.cf, self)
        page3 = Page3(self.cf, self)
        page4 = Page4(self.cf, self)
        page5 = Page5(page1, page2, page3, page4, self)
        page6 = Page6(self.cf, page5, self)

        self.addPage(page1)
        self.addPage(page2)
        self.addPage(page3)
        self.addPage(page4)
        self.addPage(page5)
        self.addPage(page6)
        self.setWindowTitle("Lighthouse Basestation Geometry Wizard")
        self.resize(640, 480)


class RecordSingleSamplePage(QtWidgets.QWizardPage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(RecordSingleSamplePage, self).__init__(parent)
        self.cf = cf
        self.explanation_text = QtWidgets.QLabel()
        self.explanation_text.setText(' ')
        self.status_text = QtWidgets.QLabel()
        self.status_text.setText('')
        self.start_measurement_button = QtWidgets.QPushButton("Start measurement")
        self.start_measurement_button.clicked.connect(self.btn_clicked)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.explanation_text)
        layout.addWidget(self.start_measurement_button)
        layout.addWidget(self.status_text)
        self.setLayout(layout)
        self.is_done = False
        self.too_few_bs = False
        self.recorded_angles_result = None
        self.timer = QtCore.QTimer()
        self.reader = LighthouseSweepAngleAverageReader(self.cf, self.ready_cb)

    def ready_cb(self, averages):
        recorded_angles = averages
        angles_calibrated = {}
        for bs_id, data in recorded_angles.items():
            angles_calibrated[bs_id] = data[1]
        self.recorded_angles_result = LhCfPoseSample(angles_calibrated=angles_calibrated)
        self.visible_basestations = ', '.join(map(lambda x: str(x + 1), recorded_angles.keys()))
        amount_of_basestations = len(recorded_angles.keys())

        self.start_measurement_button.setText("Restart Measurement")
        self.start_measurement_button.setDisabled(False)

        if amount_of_basestations < 2:
            self.status_text.setText(f'Recording Done! \n Visible Basestations: {self.visible_basestations}\n' +
                                     'Received too few base stations, we need at least two. Please try again!')
            self.too_few_bs = True
            self.is_done = True
        else:
            self.status_text.setText(f'Recording Done! \n Visible Basestations: {self.visible_basestations}\n')
            self.is_done = True
            self.completeChanged.emit()

    def timeout_cb(self):
        if self.is_done is not True:
            self.status_text.setText('No sweep angles recorded! \n' +
                                     'Make sure that the lighthouse basestations are turned on!')
            self.reader.stop_angle_collection()
            self.start_measurement_button.setText("Restart Measurement")
            self.start_measurement_button.setDisabled(False)
        elif self.too_few_bs:
            self.timer.stop()

    def btn_clicked(self):
        self.is_done = False
        self.reader.start_angle_collection()
        self.timer.timeout.connect(self.timeout_cb)
        self.timer.start(TIMEOUT_TIME)
        self.status_text.setText('Collecting sweep angles...')
        self.start_measurement_button.setDisabled(True)

    def isComplete(self):
        return self.is_done and (self.too_few_bs is not True)

    def getSample(self):
        return self.recorded_angles_result


class RecordMultipleSamplePage(QtWidgets.QWizardPage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(RecordMultipleSamplePage, self).__init__(parent)
        self.cf = cf
        self.explanation_text = QtWidgets.QLabel()
        self.explanation_text.setText(' ')
        self.status_text = QtWidgets.QLabel()
        self.status_text.setText('')
        self.start_measurement_button = QtWidgets.QPushButton("Start measurements")
        self.start_measurement_button.clicked.connect(self.btn_clicked)
        self.fill_record_times = QtWidgets.QLineEdit(str(DEFAULT_RECORD_TIME))
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.explanation_text)
        layout.addWidget(self.fill_record_times)
        layout.addWidget(self.start_measurement_button)
        layout.addWidget(self.status_text)
        self.setLayout(layout)
        self.is_done = False
        self.recorded_angles_result: list[LhCfPoseSample] = []
        self.timer = QtCore.QTimer()
        self.reader = LighthouseSweepAngleReader(self.cf, self.ready_cb)
        self.bs_seen = set()

    def ready_cb(self, bs_id: int, angles: LighthouseBsVectors):
        now = time.time()
        measurement = LhMeasurement(timestamp=now, base_station_id=bs_id, angles=angles)
        self.recorded_angles_result.append(measurement)
        self.bs_seen.add(str(bs_id + 1))

    def timer_cb(self):
        self.reader.stop()
        self.status_text.setText(f'Recording Done! Got {len(self.recorded_angles_result)} samples!')
        self.start_measurement_button.setText("Restart Measurements")
        self.start_measurement_button.setDisabled(False)
        self.is_done = True
        self.completeChanged.emit()
        self.timer.stop()

    def btn_clicked(self):
        self.is_done = False
        self.reader.start()
        self.timer.timeout.connect(self.timer_cb)
        self.timer.start(int(self.fill_record_times.text())*1000)
        self.status_text.setText('Collecting sweep angles...')
        self.start_measurement_button.setDisabled(True)

    def isComplete(self):
        return self.is_done

    def getSamples(self):
        return self.recorded_angles_result


class Page1(RecordSingleSamplePage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(Page1, self).__init__(cf, parent)
        self.explanation_text.setText('Step 1. Put the Crazyflie where you want the origin of your coordinate system.')


class Page2(RecordSingleSamplePage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(Page2, self).__init__(cf, parent)
        self.explanation_text.setText(f'Step 2. Put the Crazyflie on the positive X-axis,  exactly {REFERENCE_DIST} meters from the origin.\n ' +
                                      'This position defines the direction of the X-axis, but it is also used for scaling of the system.')


class Page3(RecordSingleSamplePage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(Page3, self).__init__(cf, parent)
        self.explanation_text.setText('Step 3. Put the Crazyflie somehere in the XY-plane, but not on the X-axis. \n')


class Page4(RecordMultipleSamplePage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(Page4, self).__init__(cf, parent)
        self.explanation_text.setText('Step 4. We will now record data from the space you plan to fly in and optimize the base station \n ' +
                                      'geometry based on this data. Move the Crazyflie around, try to cover all of the space, make sure \n ' +
                                      'all the base stations are received and do not move too fast.')


class EstimateGeometryPage(QtWidgets.QWizardPage):
    def __init__(self, page1: Page1, page2: Page2, page3: Page3, page4: Page4, parent=None):
        super(EstimateGeometryPage, self).__init__(parent)
        self.explanation_text = QtWidgets.QLabel()
        self.explanation_text.setText(' ')
        estimate_measurement_button = QtWidgets.QPushButton("Estimate geometry")
        estimate_measurement_button.clicked.connect(self.btn_clicked)
        self.status_text = QtWidgets.QLabel()
        self.status_text.setText('')

        self.page1 = page1
        self.page2 = page2
        self.page3 = page3
        self.page4 = page4

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.explanation_text)
        layout.addWidget(estimate_measurement_button)
        layout.addWidget(self.status_text)

        self.setLayout(layout)
        self.is_done = False
        self.bs_poses = None

    def btn_clicked(self):
        self.status_text.setText('Estimating geometry...')
        origin = self.page1.getSample()
        x_axis = [self.page2.getSample()]
        xy_plane = [self.page3.getSample()]
        samples = self.page4.getSamples()
        self.bs_poses = self.estimate_geometry(origin, x_axis, xy_plane, samples)
        self.is_done = True
        self.status_text.setText('Geometry estimated! \n\n' + self.print_base_stations_poses(self.bs_poses))
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done

    def print_base_stations_poses(self, base_stations: dict[int, Pose]):
        """Pretty print of base stations pose"""
        bs_string = ''
        for bs_id, pose in sorted(base_stations.items()):
            pos = pose.translation
            temp_string = f'    {bs_id + 1}: ({pos[0]}, {pos[1]}, {pos[2]})'
            print(temp_string)
            bs_string += '\n' + temp_string

        return bs_string

    def estimate_geometry(self, origin: LhCfPoseSample,
                          x_axis: list[LhCfPoseSample],
                          xy_plane: list[LhCfPoseSample],
                          samples: list[LhCfPoseSample]) -> dict[int, Pose]:
        """Estimate the geometry of the system based on samples recorded by a Crazyflie"""
        matched_samples = [origin] + x_axis + xy_plane + LighthouseSampleMatcher.match(samples, min_nr_of_bs_in_match=2)
        initial_guess = LighthouseInitialEstimator.estimate(matched_samples, LhDeck4SensorPositions.positions)

        print('Initial guess base stations at:')
        self.print_base_stations_poses(initial_guess.bs_poses)
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
        self.print_base_stations_poses(solution.bs_poses)
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

        print()
        print('Final solution:')
        print('  Base stations at:')
        self.print_base_stations_poses(bs_scaled_poses)

        return bs_scaled_poses

    def get_poses(self):
        return self.bs_poses


class Page5(EstimateGeometryPage):
    def __init__(self, page1: Page1, page2: Page2, page3: Page3, page4: Page4, parent=None):
        super(Page5, self).__init__(page1, page2, page3, page4, parent)
        self.explanation_text.setText('Step 5. We will now estimate Geometry! Press the button.')


class UploadGeometryPage(QtWidgets.QWizardPage):
    def __init__(self, cf: Crazyflie, page5: Page5, parent=None):
        super(UploadGeometryPage, self).__init__(parent)
        self.explanation_text = QtWidgets.QLabel()
        self.explanation_text.setText(' ')
        self.status_text = QtWidgets.QLabel()
        self.status_text.setText('')
        start_upload_button = QtWidgets.QPushButton("Upload geometry to Crazyflie")
        start_upload_button.clicked.connect(self.btn_clicked)
        self.page5 = page5
        self.cf = cf

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.explanation_text)
        layout.addWidget(start_upload_button)
        layout.addWidget(self.status_text)

        self.setLayout(layout)
        self.is_done = False

    def btn_clicked(self):
        bs_poses = self.page5.get_poses()
        self.start_upload_geometry(self.cf, bs_poses)
        self.status_text.setText('Start uploading geometry')
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done

    def data_written_callback(self, _):
        self.is_done = True
        self.completeChanged.emit()
        self.status_text.setText('Geometry is uploaded! Press Finish to close the wizard')

    def start_upload_geometry(self, cf: Crazyflie, bs_poses: dict[int, Pose]):
        """Upload the geometry to the Crazyflie"""
        geo_dict = {}
        for bs_id, pose in bs_poses.items():
            geo = LighthouseBsGeometry()
            geo.origin = pose.translation.tolist()
            geo.rotation_matrix = pose.rot_matrix.tolist()
            geo.valid = True
            geo_dict[bs_id] = geo

        helper = LighthouseConfigWriter(cf)
        helper.write_and_store_config(self.data_written_callback, geos=geo_dict)


class Page6(UploadGeometryPage):
    def __init__(self, cf: Crazyflie, page5: Page5, parent=None):
        super(Page6, self).__init__(cf, page5, parent)
        self.explanation_text.setText(
            'Step 6. Double check the basestations geometry. If it looks good, press the button')


if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    wizard = LighthouseBasestationGeometryWizard()
    wizard.show()
    sys.exit(app.exec_())
