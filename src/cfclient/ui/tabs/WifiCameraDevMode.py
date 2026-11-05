# ============================================================================
# DEV MODE ONLY - REMOVE BEFORE PUSHING!
#
# To remove: delete this file and delete the block marked DEV-MODE-START /
# DEV-MODE-END in WifiCameraTab.py.
#
# Shows a small window that fakes the camera deck state so the Wifi Camera tab
# can be tested without hardware. Only appears when the client is started with
# the environment variable CFCLIENT_WIFI_CAMERA_DEV=1
# ============================================================================

import os
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QFormLayout, QLabel, QLineEdit, QSlider,
                             QVBoxLayout, QWidget)

ENV_VAR = 'CFCLIENT_WIFI_CAMERA_DEV'


def maybe_show_dev_panel(tab):
    if os.environ.get(ENV_VAR) != '1':
        return
    tab._dev_panel = WifiCameraDevPanel(tab)
    tab._dev_panel.show()


class WifiCameraDevPanel(QWidget):
    def __init__(self, tab):
        super().__init__(tab, Qt.WindowType.Window)
        self._tab = tab
        self.setWindowTitle('Wifi Camera DEV MODE (remove before commit)')

        self._deck = QCheckBox('Wifi connected to camera deck')
        self._pc = QCheckBox('Wifi connection on PC')
        self._ssid = QLineEdit('Crazyflie-Network')

        self._signal_valid = QCheckBox('Signal known')
        self._signal = QSlider(Qt.Orientation.Horizontal)
        self._signal.setRange(-100, -30)
        self._signal.setValue(-50)
        self._signal_label = QLabel()

        self._stream = QCheckBox('Stream button enabled')
        self._streaming = QCheckBox('Streaming (enables Record button)')
        self._recording = QCheckBox('Recording (only while streaming)')
        self._recording.setEnabled(False)
        self._flight = QCheckBox('Flight controls enabled')

        form = QFormLayout()
        form.addRow(self._deck)
        form.addRow(self._pc)
        form.addRow('SSID', self._ssid)
        form.addRow(self._signal_valid)
        form.addRow(self._signal_label, self._signal)
        form.addRow(self._stream)
        form.addRow(self._streaming)
        form.addRow(self._recording)
        form.addRow(self._flight)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Fakes camera state, not connected to anything.'))
        layout.addLayout(form)

        for box in (self._deck, self._pc, self._signal_valid, self._stream, self._flight):
            box.toggled.connect(self._apply)
        self._ssid.textChanged.connect(self._apply)
        self._signal.valueChanged.connect(self._apply)
        self._streaming.toggled.connect(self._apply_streaming)
        self._recording.toggled.connect(self._apply_recording)

        self._apply()

    def _apply(self, *_):
        tab = self._tab
        tab.set_camera_status(self._deck.isChecked(), self._pc.isChecked(), self._ssid.text() or None)

        dbm = self._signal.value()
        self._signal_label.setText('%d dBm' % dbm)
        if self._deck.isChecked() and self._signal_valid.isChecked():
            tab.set_signal_strength(dbm)
        else:
            tab.set_signal_strength(None)

        tab.streamButton.setEnabled(self._stream.isChecked())
        tab.commanderBox.setEnabled(self._flight.isChecked())
        tab.armButton.setEnabled(self._flight.isChecked())

    def _apply_streaming(self, streaming):
        self._tab.set_streaming(streaming)
        self._recording.setEnabled(streaming)
        if not streaming:
            self._recording.setChecked(False)

    def _apply_recording(self, recording):
        self._tab.set_recording(recording)
        if not recording:
            # Fake the downloaded file that the lib will report when a recording stops
            name = 'rec%s_1.jpeg' % time.strftime('%y%m%d')
            self._tab.set_recording_saved(os.path.join(os.path.expanduser('~'), name))
