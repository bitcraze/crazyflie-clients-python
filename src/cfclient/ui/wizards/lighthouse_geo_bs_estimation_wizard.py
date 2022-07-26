#!/usr/bin/env python

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5.QtCore import pyqtProperty
from PyQt5 import QtCore, QtWidgets
from cflib.crazyflie import Crazyflie
from threading import Event
from cflib.localization.lighthouse_types import LhCfPoseSample
from cflib.localization.lighthouse_sweep_angle_reader import LighthouseSweepAngleAverageReader
import cfclient
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
        self.resize(640,480)


class Page1(QtWidgets.QWizardPage):
    def __init__(self, cf:Crazyflie, parent=None):
        super(Page1, self).__init__(parent)
        self.cf = cf
        explanation_text =  QtWidgets.QLabel()
        explanation_text.setText('Step 1. Put the Crazyflie where you want the origin of your coordinate system.')
        self.status_text =  QtWidgets.QLabel()
        self.status_text.setText('')
        self.start_measurement_button = QtWidgets.QPushButton("Start measurement")
        self.start_measurement_button.clicked.connect(self.btn_clicked)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(explanation_text)
        layout.addWidget(self.start_measurement_button)
        layout.addWidget(self.status_text)
        self.setLayout(layout)
        self.is_done = False
        self.is_ready = False
        self.recorded_angles_result = None
        self.visible_basestations = None
        self.amount_of_basestations = None
        self.timer =  QtCore.QTimer()
        self.reader = LighthouseSweepAngleAverageReader(self.cf, self.ready_cb)

    def ready_cb(self, averages):
        recorded_angles = averages
        angles_calibrated = {}
        for bs_id, data in recorded_angles.items():
            angles_calibrated[bs_id] = data[1]
        self.recorded_angles_result = LhCfPoseSample(angles_calibrated=angles_calibrated)
        self.visible_basestations = ', '.join(map(lambda x: str(x + 1), recorded_angles.keys()))
        self.amount_of_basestations = recorded_angles.keys()
        self.is_done = True
        self.completeChanged.emit()
        self.status_text.setText(f'Recording Done! \n Visible Basestations: {self.visible_basestations}\n')
        self.start_measurement_button.setText("Restart Measurement")
        self.start_measurement_button.setDisabled(False)

    def timeout_cb(self):
        if self.is_done is not True:
            self.status_text.setText('No sweep angles recorded! \n' +
                'Make sure that the lighthouse basestations are turned on!')
            self.reader.stop_angle_collection()
            self.start_measurement_button.setText("Restart Measurement")
            self.start_measurement_button.setDisabled(False)
            self.is_done = True
            self.completeChanged.emit()
            self.recorded_angles_result = 22
        self.timer.stop()

    def btn_clicked(self):
        self.is_done = False
        self.reader.start_angle_collection()
        self.timer.timeout.connect(self.timeout_cb)
        self.timer.start(TIMEOUT_TIME) 
        self.status_text.setText('Collecting sweep angles...')
        self.start_measurement_button.setDisabled(True)

    def isComplete(self):
        return self.is_done

    def getOrigin(self):
        return self.recorded_angles_result 

class Page2(QtWidgets.QWizardPage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(Page2, self).__init__(parent)
        explanation_text =  QtWidgets.QLabel()
        explanation_text.setText(f'Step 2. Put the Crazyflie on the positive X-axis,  exactly {REFERENCE_DIST} meters from the origin.\n ' +
              'This position defines the direction of the X-axis, but it is also used for scaling of the system.')
        start_measurement_button = QtWidgets.QPushButton("Start measurement")
        start_measurement_button.clicked.connect(self.btn_clicked)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(explanation_text)
        layout.addWidget(start_measurement_button)
        self.setLayout(layout)
        self.is_done = False

    def btn_clicked(self):
        for it in range(ITERATION_MAX_NR):
            print(it)
            time.sleep(1)
        self.is_done = True
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done

class Page3(QtWidgets.QWizardPage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(Page3, self).__init__(parent)
        explanation_text =  QtWidgets.QLabel()
        explanation_text.setText('Step 3. Put the Crazyflie somehere in the XY-plane, but not on the X-axis. \n')
        start_measurement_button = QtWidgets.QPushButton("Start measurement")
        start_measurement_button.clicked.connect(self.btn_clicked)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(explanation_text)
        layout.addWidget(start_measurement_button)
        self.setLayout(layout)
        self.is_done = False

    def btn_clicked(self):
        for it in range(ITERATION_MAX_NR):
            print(it)
            time.sleep(1)
        self.is_done = True
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done


class Page4(QtWidgets.QWizardPage):
    def __init__(self, cf: Crazyflie, parent=None):
        super(Page4, self).__init__(parent)
        explanation_text =  QtWidgets.QLabel()
        explanation_text.setText('Step 4. We will now record data from the space you plan to fly in and optimize the base station \n ' +
              'geometry based on this data. Move the Crazyflie around, try to cover all of the space, make sure \n ' +
              'all the base stations are received and do not move too fast.')
        start_measurement_button = QtWidgets.QPushButton("Start measurement")
        start_measurement_button.clicked.connect(self.btn_clicked)
        self.fill_record_times = QtWidgets.QLineEdit(str(DEFAULT_RECORD_TIME))


        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(explanation_text)
        layout.addWidget(self.fill_record_times)
        layout.addWidget(start_measurement_button)

        self.setLayout(layout)
        self.is_done = False

    def btn_clicked(self):
        print(self.fill_record_times.text())
        for it in range(ITERATION_MAX_NR):
            print(int(it))
            time.sleep(1)
        self.is_done = True
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done


class Page5(QtWidgets.QWizardPage):
    def __init__(self, page1: Page1, page2: Page2, page3: Page3, page4: Page4, parent=None):
        super(Page5, self).__init__(parent)
        explanation_text =  QtWidgets.QLabel()
        explanation_text.setText('Step 5. We will now estimate Geometry! Press the button.')
        start_measurement_button = QtWidgets.QPushButton("Estimate geometry")
        start_measurement_button.clicked.connect(self.btn_clicked)
        self.page1 = page1

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(explanation_text)
        layout.addWidget(start_measurement_button)

        self.setLayout(layout)
        self.is_done = False

    def btn_clicked(self):
        print('Estimating geometry...')
        print(self.page1.getOrigin())
        for it in range(ITERATION_MAX_NR):
            print(int(it))
            time.sleep(1)
        self.is_done = True
        print('  Geometry estimated!')
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done

class Page6(QtWidgets.QWizardPage):
    def __init__(self, cf: Crazyflie, page5: Page5, parent=None):
        super(Page6, self).__init__(parent)
        explanation_text =  QtWidgets.QLabel()
        explanation_text.setText('Step 6. Double check the basestations geometry. If it looks good, press the button')
        start_measurement_button = QtWidgets.QPushButton("Upload geometry to Crazyflie")
        start_measurement_button.clicked.connect(self.btn_clicked)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(explanation_text)
        layout.addWidget(start_measurement_button)

        self.setLayout(layout)
        self.is_done = False

    def btn_clicked(self):
        print('Geometry uploading...')
        for it in range(ITERATION_MAX_NR):
            print(int(it))
            time.sleep(1)
        self.is_done = True
        print('  Geometry uploaded!')
        self.completeChanged.emit()

    def isComplete(self):
        return self.is_done



if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    wizard = LighthouseBasestationGeometryWizard()
    wizard.show()
    sys.exit(app.exec_())

