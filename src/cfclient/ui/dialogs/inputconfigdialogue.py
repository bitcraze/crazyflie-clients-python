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
Dialogue used to select and configure an inputdevice. This includes mapping
buttons and axis to match controls for the Crazyflie.
"""
import logging

import cfclient
from PyQt5.QtCore import QThread
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QMessageBox
from cfclient.utils.config_manager import ConfigManager
from PyQt5 import Qt
from PyQt5 import QtWidgets
from PyQt5 import uic
from PyQt5.Qt import *  # noqa

__author__ = 'Bitcraze AB'
__all__ = ['InputConfigDialogue']

logger = logging.getLogger(__name__)

(inputconfig_widget_class, connect_widget_base_class) = (
    uic.loadUiType(cfclient.module_path + '/ui/dialogs/inputconfigdialogue.ui')
)


class InputConfigDialogue(QtWidgets.QWidget, inputconfig_widget_class):

    def __init__(self, joystickReader, *args):
        super(InputConfigDialogue, self).__init__(*args)
        self.setupUi(self)
        self._input = joystickReader

        self._input_device_reader = DeviceReader(self._input)
        self._input_device_reader.start()

        self._input_device_reader.raw_axis_data_signal.connect(
            self._detect_axis)
        self._input_device_reader.raw_button_data_signal.connect(
            self._detect_button)
        self._input_device_reader.mapped_values_signal.connect(
            self._update_mapped_values)

        self.cancelButton.clicked.connect(self.close)
        self.saveButton.clicked.connect(self._save_config)

        self.detectPitch.clicked.connect(
            lambda: self._axis_detect(
                "pitch", "Pitch axis",
                "Center the pitch axis then do max %s pitch",
                ["forward", "backward"]))
        self.detectRoll.clicked.connect(
            lambda: self._axis_detect(
                "roll", "Roll axis",
                "Center the roll axis and then do max %s roll",
                ["right", "left"]))
        self.detectYaw.clicked.connect(
            lambda: self._axis_detect(
                "yaw", "Yaw axis",
                "Center the yaw axis and then do max %s yaw",
                ["right", "left"]))
        self.detectThrust.clicked.connect(
            lambda: self._axis_detect(
                "thrust", "Thrust axis",
                "Center the thrust axis, and then do max thrust"))
        self.detectPitchPos.clicked.connect(
            lambda: self._button_detect(
                "pitchPos", "Pitch Cal Positive",
                "Press the button for Pitch postive calibration"))
        self.detectPitchNeg.clicked.connect(
            lambda: self._button_detect(
                "pitchNeg", "Pitch Cal Negative",
                "Press the button for Pitch negative calibration"))
        self.detectRollPos.clicked.connect(
            lambda: self._button_detect(
                "rollPos", "Roll Cal Positive",
                "Press the button for Roll positive calibration"))
        self.detectRollNeg.clicked.connect(
            lambda: self._button_detect(
                "rollNeg", "Roll Cal Negative",
                "Press the button for Roll negative calibration"))
        self.detectKillswitch.clicked.connect(
            lambda: self._button_detect(
                "killswitch", "Killswitch",
                "Press the button for the killswitch (will disable motors)"))
        self.detectAlt1.clicked.connect(
            lambda: self._button_detect(
                "alt1", "Alternative function 1",
                "The alternative function 1 that will do a callback"))
        self.detectAlt2.clicked.connect(
            lambda: self._button_detect(
                "alt2", "Alternative function 2",
                "The alternative function 2 that will do a callback"))
        self.detectExitapp.clicked.connect(
            lambda: self._button_detect(
                "exitapp", "Exit application",
                "Press the button for exiting the application"))
        self._detect_assisted_control.clicked.connect(
            lambda: self._button_detect(
                "assistedControl", "Assisted control",
                "Press the button for assisted control mode activation "
                "(releasing returns to manual mode)"))
        self.detectMuxswitch.clicked.connect(
            lambda: self._button_detect(
                "muxswitch", "Mux Switch",
                "Press the button for mux switching"))

        self.configButton.clicked.connect(self._start_configuration)
        self.loadButton.clicked.connect(self._load_config_from_file)
        self.deleteButton.clicked.connect(self._delete_configuration)

        self._popup = None
        self._combined_button = None
        self._detection_buttons = [
            self.detectPitch, self.detectRoll,
            self.detectYaw, self.detectThrust,
            self.detectPitchPos, self.detectPitchNeg,
            self.detectRollPos, self.detectRollNeg,
            self.detectKillswitch, self.detectExitapp,
            self._detect_assisted_control, self.detectAlt1,
            self.detectAlt2, self.detectMuxswitch]

        self._button_to_detect = ""
        self._axis_to_detect = ""
        self.combinedDetection = 0
        self._prev_combined_id = None

        self._maxed_axis = []
        self._mined_axis = []

        self._buttonindicators = {}
        self._axisindicators = {}
        self._reset_mapping()

        for d in self._input.available_devices():
            if d.supports_mapping:
                self.inputDeviceSelector.addItem(d.name, d.id)

        if len(self._input.available_devices()) > 0:
            self.configButton.setEnabled(True)

        self._map = {}
        self._saved_open_device = None

    @staticmethod
    def _scale(max_value, value):
        return (value / max_value) * 100

    def _reset_mapping(self):
        self._buttonindicators = {
            "pitchPos": self.pitchPos,
            "pitchNeg": self.pitchNeg,
            "rollPos": self.rollPos,
            "rollNeg": self.rollNeg,
            "killswitch": self.killswitch,
            "alt1": self.alt1,
            "alt2": self.alt2,
            "exitapp": self.exitapp,
            "assistedControl": self._assisted_control,
            "muxswitch": self.muxswitch,
        }

        self._axisindicators = {
            "pitch": self.pitchAxisValue,
            "roll": self.rollAxisValue,
            "yaw": self.yawAxisValue,
            "thrust": self.thrustAxisValue,
        }

    def _cancel_config_popup(self, button):
        self._axis_to_detect = ""
        self._button_to_detect = ""

    def _show_config_popup(self, caption, message, directions=[]):
        self._maxed_axis = []
        self._mined_axis = []
        self._popup = QMessageBox()
        self._popup.directions = directions
        self._combined_button = QtWidgets.QPushButton('Combined Axis ' +
                                                      'Detection')
        self.cancelButton = QtWidgets.QPushButton('Cancel')
        self._popup.addButton(self.cancelButton, QMessageBox.DestructiveRole)
        self._popup.setWindowTitle(caption)
        self._popup.setWindowFlags(Qt.Dialog | Qt.MSWindowsFixedSizeDialogHint)
        if len(directions) > 1:
            self._popup.originalMessage = message
            message = self._popup.originalMessage % directions[0]
            self._combined_button.setCheckable(True)
            self._combined_button.blockSignals(True)
            self._popup.addButton(self._combined_button,
                                  QMessageBox.ActionRole)
        self._popup.setText(message)
        self._popup.show()

    def _start_configuration(self):
        self._input.enableRawReading(
            str(self.inputDeviceSelector.currentText()))
        self._input_device_reader.start_reading()
        self._populate_config_dropdown()
        self.profileCombo.setEnabled(True)
        for b in self._detection_buttons:
            b.setEnabled(True)

    def _detect_axis(self, data):
        if (len(self._axis_to_detect) > 0):
            if (self._combined_button and self._combined_button.isChecked() and
                    self.combinedDetection == 0):
                self._combined_button.setDisabled(True)
                self.combinedDetection = 1
            for a in data:
                # Axis must go low and high before it's accepted as selected
                # otherwise maxed out axis (like gyro/acc) in some controllers
                # will always be selected. Not enforcing negative values makes
                # it possible to detect split axis (like bumpers on PS3
                # controller)
                if a not in self._maxed_axis and abs(data[a]) > 0.8:
                    self._maxed_axis.append(a)
                if a not in self._mined_axis and abs(data[a]) < 0.1:
                    self._mined_axis.append(a)
                if a in self._maxed_axis and a in self._mined_axis and len(
                        self._axis_to_detect) > 0:
                    if self.combinedDetection == 0:
                        if data[a] >= 0:
                            self._map_axis(self._axis_to_detect, a, 1.0)
                        else:
                            self._map_axis(self._axis_to_detect, a, -1.0)
                        self._axis_to_detect = ""
                        self._check_and_enable_saving()
                        if self._popup is not None:
                            self.cancelButton.click()
                    elif self.combinedDetection == 2:  # finished detection
                        # not the same axis again ...
                        if self._prev_combined_id != a:
                            self._map_axis(self._axis_to_detect, a, -1.0)
                            self._axis_to_detect = ""
                            self._check_and_enable_saving()
                            if (self._popup is not None):
                                self.cancelButton.click()
                            self.combinedDetection = 0
                    elif self.combinedDetection == 1:
                        self._map_axis(self._axis_to_detect, a, 1.0)
                        self._prev_combined_id = a
                        self.combinedDetection = 2
                        message = (self._popup.originalMessage %
                                   self._popup.directions[1])
                        self._popup.setText(message)

    def _update_mapped_values(self, mapped_data):
        for v in mapped_data.get_all_indicators():
            if v in self._buttonindicators:
                if mapped_data.get(v):
                    self._buttonindicators[v].setChecked(True)
                else:
                    self._buttonindicators[v].setChecked(False)
            if v in self._axisindicators:
                # The sliders used are set to 0-100 and the values from the
                # input-layer is scaled according to the max settings in
                # the input-layer. So scale the value and place 0 in the middle
                scaled_value = mapped_data.get(v)
                if v == "thrust":
                    scaled_value = InputConfigDialogue._scale(
                        self._input.max_thrust, scaled_value
                    )
                if v == "roll" or v == "pitch":
                    scaled_value = InputConfigDialogue._scale(
                        self._input.max_rp_angle, scaled_value
                    )
                if v == "yaw":
                    scaled_value = InputConfigDialogue._scale(
                        self._input.max_yaw_rate, scaled_value
                    )
                self._axisindicators[v].setValue(scaled_value)

    def _map_axis(self, function, key_id, scale):
        self._map["Input.AXIS-{}".format(key_id)] = {}
        self._map["Input.AXIS-{}".format(key_id)]["id"] = key_id
        self._map["Input.AXIS-{}".format(key_id)]["key"] = function
        self._map["Input.AXIS-{}".format(key_id)]["scale"] = scale
        self._map["Input.AXIS-{}".format(key_id)]["offset"] = 0.0
        self._map["Input.AXIS-{}".format(key_id)]["type"] = "Input.AXIS"
        self._input.set_raw_input_map(self._map)

    def _map_button(self, function, key_id):
        # Duplicate buttons are not allowed, remove if there's already one
        # mapped
        prev_button = None
        for m in self._map:
            if "key" in self._map[m] and self._map[m]["key"] == function:
                prev_button = m
        if prev_button:
            del self._map[prev_button]

        self._map["Input.BUTTON-{}".format(key_id)] = {}
        self._map["Input.BUTTON-{}".format(key_id)]["id"] = key_id
        self._map["Input.BUTTON-{}".format(key_id)]["key"] = function
        self._map["Input.BUTTON-{}".format(key_id)]["scale"] = 1.0
        self._map["Input.BUTTON-{}".format(key_id)]["type"] = "Input.BUTTON"
        self._input.set_raw_input_map(self._map)

    def _detect_button(self, data):
        if len(self._button_to_detect) > 0:
            for b in data:
                if data[b] > 0:
                    self._map_button(self._button_to_detect, b)
                    self._button_to_detect = ""
                    self._check_and_enable_saving()
                    if self._popup is not None:
                        self._popup.close()

    def _check_and_enable_saving(self):
        needed_funcs = ["thrust", "yaw", "roll", "pitch"]

        for m in self._map:
            if self._map[m]["key"] in needed_funcs:
                needed_funcs.remove(self._map[m]["key"])

        if len(needed_funcs) == 0:
            self.saveButton.setEnabled(True)

    def _populate_config_dropdown(self):
        configs = ConfigManager().get_list_of_configs()
        if len(configs):
            self.loadButton.setEnabled(True)
        for c in configs:
            self.profileCombo.addItem(c)

    def _axis_detect(self, varname, caption, message, directions=[]):
        self._axis_to_detect = varname
        self._show_config_popup(caption, message, directions)

    def _button_detect(self, varname, caption, message):
        self._button_to_detect = varname
        self._show_config_popup(caption, message)

    def _show_error(self, caption, message):
        QMessageBox.critical(self, caption, message)

    def _load_config_from_file(self):
        loaded_map = ConfigManager().get_config(
            self.profileCombo.currentText())
        if loaded_map:
            self._input.set_raw_input_map(loaded_map)
            self._map = loaded_map
        else:
            logger.warning("Could not load configfile [%s]",
                           self.profileCombo.currentText())
            self._show_error("Could not load config",
                             "Could not load config [%s]" %
                             self.profileCombo.currentText())
        self._check_and_enable_saving()

    def _delete_configuration(self):
        logger.warning("deleteConfig not implemented")

    def _save_config(self):
        config_name = str(self.profileCombo.currentText())
        ConfigManager().save_config(self._map, config_name)
        self.close()

    def showEvent(self, event):
        """Called when dialog is opened"""
        # self._saved_open_device = self._input.get_device_name()
        # self._input.stop_input()
        self._input.pause_input()

    def closeEvent(self, event):
        """Called when dialog is closed"""
        self._input.stop_raw_reading()
        self._input_device_reader.stop_reading()
        # self._input.start_input(self._saved_open_device)
        self._input.resume_input()


class DeviceReader(QThread):
    """Used for polling data from the Input layer during configuration"""
    raw_axis_data_signal = pyqtSignal(object)
    raw_button_data_signal = pyqtSignal(object)
    mapped_values_signal = pyqtSignal(object)

    def __init__(self, input):
        QThread.__init__(self)

        self._input = input
        self._read_timer = QTimer()
        self._read_timer.setInterval(25)

        self._read_timer.timeout.connect(self._read_input)

    def stop_reading(self):
        """Stop polling data"""
        self._read_timer.stop()

    def start_reading(self):
        """Start polling data"""
        self._read_timer.start()

    def _read_input(self):
        [rawaxis, rawbuttons, mapped_values] = self._input.read_raw_values()
        self.raw_axis_data_signal.emit(rawaxis)
        self.raw_button_data_signal.emit(rawbuttons)
        self.mapped_values_signal.emit(mapped_values)
