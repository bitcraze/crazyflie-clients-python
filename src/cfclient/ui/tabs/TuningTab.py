# -*- coding: utf-8 -*-
#
# ,---------,       ____  _ __
# |  ,-^-,  |      / __ )(_) /_______________ _____  ___
# | (  O  ) |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
# | / ,--'  |    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#    +------`   /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
# Copyright (C) 2022 Bitcraze AB
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, in version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""
Tab for tuning PID controller, mainly for larger quads.
"""

import logging

from PyQt5 import QtGui, uic
from PyQt5.QtCore import pyqtSignal
from PyQt5 import QtWidgets
import time

import cfclient
from cfclient.ui.tab import Tab
from cfclient.utils.ui import UiUtils
from cfclient.ui.widgets.super_slider import SuperSlider
from cflib.crazyflie import Crazyflie

__author__ = 'Bitcraze AB'
__all__ = ['TuningTab']

logger = logging.getLogger(__name__)

tuning_tab_class = uic.loadUiType(cfclient.module_path + "/ui/tabs/tuningTab.ui")[0]

class SliderParamMapper:
    def __init__(self, slider: SuperSlider, group: str, name: str):
        self.param_group = group
        self.param_name = name
        self.full_param_name = f'{group}.{name}'

        self.slider = slider
        self.slider.value_changed_cb.add_callback(self.slider_changed)
        self.slider.setEnabled(False)

        # Prevents param changes that comes back from the CF to set the parameter and create a feedback loop
        self.receive_block_time = 0.0

        self.cf = None

    def connected(self, cf: Crazyflie):
        self.cf = cf
        self.cf.param.add_update_callback(group=self.param_group, name=self.param_name, cb=self._param_updated_cb)
        self.slider.setEnabled(True)

    def disconnected(self):
        self.cf = None
        self.slider.setEnabled(False)

    # Called when the user has modified the value in the UI
    def slider_changed(self, value):
        if self.cf is not None:
            if self.cf.is_connected():
                self.receive_block_time = time.time() + 0.4
                self.cf.param.set_value(self.full_param_name, value)

    # Called when a parameter in the CF has changed, this is also true if we initiated the param update
    def _param_updated_cb(self, full_param_name, value):
        if time.time() > self.receive_block_time:
            self.slider.set_value(float(value))


class TuningTab(Tab, tuning_tab_class):
    """Tab for plotting logging data"""

    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)

    def __init__(self, tabWidget, helper, *args):
        super(TuningTab, self).__init__(*args)
        self.setupUi(self)

        self.tabName = "Tuning"
        self.menuName = "Tuning tab"
        self.tabWidget = tabWidget

        self._helper = helper

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._connected_signal.connect(self._connected)
        self._disconnected_signal.connect(self._disconnected)

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(
            self._connected_signal.emit)

        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

        self.mappers: list[SliderParamMapper] = []

        # Rate PID
        self.mappers.append(self._create_slider(self.grid_rate, 1, 1, 0, 1000, 'pid_rate', 'roll_kp'))
        self.mappers.append(self._create_slider(self.grid_rate, 1, 2, 0, 1000, 'pid_rate', 'roll_ki'))
        self.mappers.append(self._create_slider(self.grid_rate, 1, 3, 0, 10, 'pid_rate', 'roll_kd'))

        self.mappers.append(self._create_slider(self.grid_rate, 2, 1, 0, 1000, 'pid_rate', 'pitch_kp'))
        self.mappers.append(self._create_slider(self.grid_rate, 2, 2, 0, 1000, 'pid_rate', 'pitch_ki'))
        self.mappers.append(self._create_slider(self.grid_rate, 2, 3, 0, 10, 'pid_rate', 'pitch_kd'))

        self.mappers.append(self._create_slider(self.grid_rate, 3, 1, 0, 200, 'pid_rate', 'yaw_kp'))
        self.mappers.append(self._create_slider(self.grid_rate, 3, 2, 0, 100, 'pid_rate', 'yaw_ki'))
        self.mappers.append(self._create_slider(self.grid_rate, 3, 3, 0, 10, 'pid_rate', 'yaw_kd'))

        # Attitude PID
        self.mappers.append(self._create_slider(self.grid_attitude, 1, 1, 0, 10, 'pid_attitude', 'roll_kp'))
        self.mappers.append(self._create_slider(self.grid_attitude, 1, 2, 0, 10, 'pid_attitude', 'roll_ki'))
        self.mappers.append(self._create_slider(self.grid_attitude, 1, 3, 0, 10, 'pid_attitude', 'roll_kd'))

        self.mappers.append(self._create_slider(self.grid_attitude, 2, 1, 0, 10, 'pid_attitude', 'pitch_kp'))
        self.mappers.append(self._create_slider(self.grid_attitude, 2, 2, 0, 10, 'pid_attitude', 'pitch_ki'))
        self.mappers.append(self._create_slider(self.grid_attitude, 2, 3, 0, 10, 'pid_attitude', 'pitch_kd'))

        self.mappers.append(self._create_slider(self.grid_attitude, 3, 1, 0, 10, 'pid_attitude', 'yaw_kp'))
        self.mappers.append(self._create_slider(self.grid_attitude, 3, 2, 0, 10, 'pid_attitude', 'yaw_ki'))
        self.mappers.append(self._create_slider(self.grid_attitude, 3, 3, 0, 10, 'pid_attitude', 'yaw_kd'))

        # Position control PID
        self.mappers.append(self._create_slider(self.grid_pos_ctrl, 1, 1, 0, 10, 'posCtlPid', 'xKp'))
        self.mappers.append(self._create_slider(self.grid_pos_ctrl, 1, 2, 0, 10, 'posCtlPid', 'xKi'))
        self.mappers.append(self._create_slider(self.grid_pos_ctrl, 1, 3, 0, 10, 'posCtlPid', 'xKd'))

        self.mappers.append(self._create_slider(self.grid_pos_ctrl, 2, 1, 0, 10, 'posCtlPid', 'yKp'))
        self.mappers.append(self._create_slider(self.grid_pos_ctrl, 2, 2, 0, 10, 'posCtlPid', 'yKi'))
        self.mappers.append(self._create_slider(self.grid_pos_ctrl, 2, 3, 0, 10, 'posCtlPid', 'yKd'))

        self.mappers.append(self._create_slider(self.grid_pos_ctrl, 3, 1, 0, 10, 'posCtlPid', 'zKp'))
        self.mappers.append(self._create_slider(self.grid_pos_ctrl, 3, 2, 0, 10, 'posCtlPid', 'zKi'))
        self.mappers.append(self._create_slider(self.grid_pos_ctrl, 3, 3, 0, 10, 'posCtlPid', 'zKd'))

        self.mappers.append(self._create_slider(self.grid_pos_ctrl, 5, 1, 0, 65536, 'posCtlPid', 'thrustBase'))

        # Velocity control PID
        self.mappers.append(self._create_slider(self.grid_vel_ctrl, 1, 1, 0, 50, 'velCtlPid', 'vxKp'))
        self.mappers.append(self._create_slider(self.grid_vel_ctrl, 1, 2, 0, 50, 'velCtlPid', 'vxKi'))
        self.mappers.append(self._create_slider(self.grid_vel_ctrl, 1, 3, 0, 10, 'velCtlPid', 'vxKd'))
        self.mappers.append(self._create_slider(self.grid_vel_ctrl, 1, 4, 0, 10, 'velCtlPid', 'vxKFF'))

        self.mappers.append(self._create_slider(self.grid_vel_ctrl, 2, 1, 0, 50, 'velCtlPid', 'vyKp'))
        self.mappers.append(self._create_slider(self.grid_vel_ctrl, 2, 2, 0, 50, 'velCtlPid', 'vyKi'))
        self.mappers.append(self._create_slider(self.grid_vel_ctrl, 2, 3, 0, 10, 'velCtlPid', 'vyKd'))
        self.mappers.append(self._create_slider(self.grid_vel_ctrl, 2, 4, 0, 10, 'velCtlPid', 'vyKFF'))

        self.mappers.append(self._create_slider(self.grid_vel_ctrl, 3, 1, 0, 50, 'velCtlPid', 'vzKp'))
        self.mappers.append(self._create_slider(self.grid_vel_ctrl, 3, 2, 0, 50, 'velCtlPid', 'vzKi'))
        self.mappers.append(self._create_slider(self.grid_vel_ctrl, 3, 3, 0, 10, 'velCtlPid', 'vzKd'))

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        for mapper in self.mappers:
            mapper.connected(self._helper.cf)

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        for mapper in self.mappers:
            mapper.disconnected()
        # TODO set default value?

    def _create_slider(self, gridLayout, row, col, min_val, max_val, param_group:str, param_name: str):
        initial_val = (min_val + max_val) / 2.0
        slider = SuperSlider(min_val, max_val, initial_val)
        gridLayout.addWidget(slider, row, col)

        return SliderParamMapper(slider, param_group, param_name)
