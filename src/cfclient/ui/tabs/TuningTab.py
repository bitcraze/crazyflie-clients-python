# -*- coding: utf-8 -*-
#
# ,---------,       ____  _ __
# |  ,-^-,  |      / __ )(_) /_______________ _____  ___
# | (  O  ) |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
# | / ,--'  |    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#    +------`   /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
# Copyright (C) 2022-2023 Bitcraze AB
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

from PyQt6 import QtWidgets
from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal, Qt
import time

import cfclient
from cfclient.ui.tab_toolbox import TabToolbox
from cfclient.ui.widgets.super_slider import SuperSlider
from cflib.crazyflie import Crazyflie, Param
from cflib.utils.callbacks import Syncer

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

        # Prevents param changes that comes back from the CF to set the parameter and create a feedback loop
        self.receive_block_time = 0.0

        self.linked_mapper = None
        self.linked_checkbox: QtWidgets.QCheckBox = None

        self.cf = None

    def connected(self, cf: Crazyflie):
        self.cf = cf
        return self.param_group, self.param_name

    def disconnected(self):
        self.cf = None

    def link_with(self, other_mapper: 'SliderParamMapper', checkbox: QtWidgets.QCheckBox):
        self.linked_mapper = other_mapper
        self.linked_checkbox = checkbox

        other_mapper.linked_mapper = self
        other_mapper.linked_checkbox = checkbox

    def enable_ui(self, enabled):
        self.slider.setEnabled(enabled)

    # Called when the user has modified the value in the UI
    def slider_changed(self, value):
        if self.cf is not None:
            if self.cf.is_connected():
                self.receive_block_time = time.time() + 0.4
                self.cf.param.set_value(self.full_param_name, value)

        if self.linked_mapper is not None:
            self.linked_mapper.linked_update(value)

    # Called when a parameter in the CF has changed, this is also true if we initiated the param update
    def param_updated_cb(self, full_param_name, value):
        if time.time() > self.receive_block_time:
            self.slider.set_value(float(value))

            if self.linked_mapper is not None:
                self.linked_mapper.linked_update(value)

    # Called by another SliderParamMapper that is linked
    def linked_update(self, value):
        if self.linked_checkbox is not None and self.linked_checkbox.checkState() == Qt.CheckState.Checked:
            self.slider.set_value(float(value))
            if self.cf is not None and self.cf.is_connected():
                self.receive_block_time = time.time() + 0.4
                self.cf.param.set_value(self.full_param_name, value)


class TuningTab(TabToolbox, tuning_tab_class):
    """Tab for plotting logging data"""

    _connected_signal = pyqtSignal(str)
    _disconnected_signal = pyqtSignal(str)

    _param_updated_signal = pyqtSignal(str, object)

    def __init__(self, helper):
        super(TuningTab, self).__init__(helper, 'Tuning')
        self.setupUi(self)

        # Always wrap callbacks from Crazyflie API though QT Signal/Slots
        # to avoid manipulating the UI when rendering it
        self._connected_signal.connect(self._connected)
        self._disconnected_signal.connect(self._disconnected)
        self._param_updated_signal.connect(self._param_updated_cb)

        # Connect the Crazyflie API callbacks to the signals
        self._helper.cf.connected.add_callback(
            self._connected_signal.emit)

        self._helper.cf.disconnected.add_callback(
            self._disconnected_signal.emit)

        # A dictionary mapping the full param name to a SliderParamMapper
        self.mappers = self._set_up_param_mappings()

        self.store_button.clicked.connect(self._store_button_clicked)
        self.clear_stored_button.clicked.connect(self._clear_stored_button_clicked)
        self.default_values_button.clicked.connect(self._default_values_button_clicked)
        self._enable_ui_objects(False)

    def _set_up_param_mappings(self):
        mappers: dict[str, SliderParamMapper] = {}

        # Rate PID
        mappers.update(self._create_slider(self.grid_rate, 1, 1, 0, 1000, 'pid_rate', 'roll_kp'))
        mappers.update(self._create_slider(self.grid_rate, 1, 2, 0, 1000, 'pid_rate', 'roll_ki'))
        mappers.update(self._create_slider(self.grid_rate, 1, 3, 0, 10, 'pid_rate', 'roll_kd'))

        mappers.update(self._create_slider(self.grid_rate, 2, 1, 0, 1000, 'pid_rate', 'pitch_kp'))
        mappers.update(self._create_slider(self.grid_rate, 2, 2, 0, 1000, 'pid_rate', 'pitch_ki'))
        mappers.update(self._create_slider(self.grid_rate, 2, 3, 0, 10, 'pid_rate', 'pitch_kd'))

        mappers.update(self._create_slider(self.grid_rate, 3, 1, 0, 200, 'pid_rate', 'yaw_kp'))
        mappers.update(self._create_slider(self.grid_rate, 3, 2, 0, 100, 'pid_rate', 'yaw_ki'))
        mappers.update(self._create_slider(self.grid_rate, 3, 3, 0, 10, 'pid_rate', 'yaw_kd'))

        self._link(mappers, 'pid_rate.roll_kp', 'pid_rate.pitch_kp', self.rate_link_checkbox)
        self._link(mappers, 'pid_rate.roll_ki', 'pid_rate.pitch_ki', self.rate_link_checkbox)
        self._link(mappers, 'pid_rate.roll_kd', 'pid_rate.pitch_kd', self.rate_link_checkbox)

        # Attitude PID
        mappers.update(self._create_slider(self.grid_attitude, 1, 1, 0, 10, 'pid_attitude', 'roll_kp'))
        mappers.update(self._create_slider(self.grid_attitude, 1, 2, 0, 10, 'pid_attitude', 'roll_ki'))
        mappers.update(self._create_slider(self.grid_attitude, 1, 3, 0, 10, 'pid_attitude', 'roll_kd'))

        mappers.update(self._create_slider(self.grid_attitude, 2, 1, 0, 10, 'pid_attitude', 'pitch_kp'))
        mappers.update(self._create_slider(self.grid_attitude, 2, 2, 0, 10, 'pid_attitude', 'pitch_ki'))
        mappers.update(self._create_slider(self.grid_attitude, 2, 3, 0, 10, 'pid_attitude', 'pitch_kd'))

        mappers.update(self._create_slider(self.grid_attitude, 3, 1, 0, 10, 'pid_attitude', 'yaw_kp'))
        mappers.update(self._create_slider(self.grid_attitude, 3, 2, 0, 10, 'pid_attitude', 'yaw_ki'))
        mappers.update(self._create_slider(self.grid_attitude, 3, 3, 0, 10, 'pid_attitude', 'yaw_kd'))

        self._link(mappers, 'pid_attitude.roll_kp', 'pid_attitude.pitch_kp', self.attitude_link_checkbox)
        self._link(mappers, 'pid_attitude.roll_ki', 'pid_attitude.pitch_ki', self.attitude_link_checkbox)
        self._link(mappers, 'pid_attitude.roll_kd', 'pid_attitude.pitch_kd', self.attitude_link_checkbox)

        # Position control PID
        mappers.update(self._create_slider(self.grid_pos_ctrl, 1, 1, 0, 10, 'posCtlPid', 'xKp'))
        mappers.update(self._create_slider(self.grid_pos_ctrl, 1, 2, 0, 10, 'posCtlPid', 'xKi'))
        mappers.update(self._create_slider(self.grid_pos_ctrl, 1, 3, 0, 10, 'posCtlPid', 'xKd'))

        mappers.update(self._create_slider(self.grid_pos_ctrl, 2, 1, 0, 10, 'posCtlPid', 'yKp'))
        mappers.update(self._create_slider(self.grid_pos_ctrl, 2, 2, 0, 10, 'posCtlPid', 'yKi'))
        mappers.update(self._create_slider(self.grid_pos_ctrl, 2, 3, 0, 10, 'posCtlPid', 'yKd'))

        mappers.update(self._create_slider(self.grid_pos_ctrl, 3, 1, 0, 10, 'posCtlPid', 'zKp'))
        mappers.update(self._create_slider(self.grid_pos_ctrl, 3, 2, 0, 10, 'posCtlPid', 'zKi'))
        mappers.update(self._create_slider(self.grid_pos_ctrl, 3, 3, 0, 10, 'posCtlPid', 'zKd'))

        mappers.update(self._create_slider(self.grid_pos_ctrl, 5, 1, 0, 65536, 'posCtlPid', 'thrustBase'))

        self._link(mappers, 'posCtlPid.xKp', 'posCtlPid.yKp', self.position_link_checkbox)
        self._link(mappers, 'posCtlPid.xKi', 'posCtlPid.yKi', self.position_link_checkbox)
        self._link(mappers, 'posCtlPid.xKd', 'posCtlPid.yKd', self.position_link_checkbox)

        # Velocity control PID
        mappers.update(self._create_slider(self.grid_vel_ctrl, 1, 1, 0, 50, 'velCtlPid', 'vxKp'))
        mappers.update(self._create_slider(self.grid_vel_ctrl, 1, 2, 0, 50, 'velCtlPid', 'vxKi'))
        mappers.update(self._create_slider(self.grid_vel_ctrl, 1, 3, 0, 10, 'velCtlPid', 'vxKd'))
        mappers.update(self._create_slider(self.grid_vel_ctrl, 1, 4, 0, 10, 'velCtlPid', 'vxKFF'))

        mappers.update(self._create_slider(self.grid_vel_ctrl, 2, 1, 0, 50, 'velCtlPid', 'vyKp'))
        mappers.update(self._create_slider(self.grid_vel_ctrl, 2, 2, 0, 50, 'velCtlPid', 'vyKi'))
        mappers.update(self._create_slider(self.grid_vel_ctrl, 2, 3, 0, 10, 'velCtlPid', 'vyKd'))
        mappers.update(self._create_slider(self.grid_vel_ctrl, 2, 4, 0, 10, 'velCtlPid', 'vyKFF'))

        mappers.update(self._create_slider(self.grid_vel_ctrl, 3, 1, 0, 50, 'velCtlPid', 'vzKp'))
        mappers.update(self._create_slider(self.grid_vel_ctrl, 3, 2, 0, 50, 'velCtlPid', 'vzKi'))
        mappers.update(self._create_slider(self.grid_vel_ctrl, 3, 3, 0, 10, 'velCtlPid', 'vzKd'))

        self._link(mappers, 'velCtlPid.vxKp', 'velCtlPid.vyKp', self.velocity_link_checkbox)
        self._link(mappers, 'velCtlPid.vxKi', 'velCtlPid.vyKi', self.velocity_link_checkbox)
        self._link(mappers, 'velCtlPid.vxKd', 'velCtlPid.vyKd', self.velocity_link_checkbox)
        self._link(mappers, 'velCtlPid.vxKFF', 'velCtlPid.vyKFF', self.velocity_link_checkbox)

        return mappers

    def _connected(self, link_uri):
        """Callback when the Crazyflie has been connected"""
        for mapper in self.mappers.values():
            param_group, param_name = mapper.connected(self._helper.cf)
            self._helper.cf.param.add_update_callback(
                group=param_group, name=param_name, cb=self._param_updated_signal.emit)

        self._enable_ui_objects(True)

    def _disconnected(self, link_uri):
        """Callback for when the Crazyflie has been disconnected"""
        for mapper in self.mappers.values():
            mapper.disconnected()

        self._enable_ui_objects(False)
        # TODO set default values?

    def _create_slider(self, gridLayout, row, col, min_val, max_val, param_group: str, param_name: str):
        initial_val = (min_val + max_val) / 2.0
        slider = SuperSlider(min_val, max_val, initial_val)
        gridLayout.addWidget(slider, row, col)

        slider_mapper = SliderParamMapper(slider, param_group, param_name)

        return {slider_mapper.full_param_name: slider_mapper}

    def _param_updated_cb(self, full_param_name, value):
        if full_param_name in self.mappers:
            self.mappers[full_param_name].param_updated_cb(full_param_name, value)

    def _link(self, mappers, first, other, checkbox):
        first_mapper = mappers[first]
        other_mapper = mappers[other]

        first_mapper.link_with(other_mapper, checkbox)

    def _store_button_clicked(self):
        param: Param = self._helper.cf.param
        for full_param_name in self.mappers.keys():
            # syncer = Syncer()
            param.persistent_store(full_param_name)

    def _clear_stored_button_clicked(self):
        param: Param = self._helper.cf.param
        for full_param_name in self.mappers.keys():
            param.persistent_clear(full_param_name)

    def _default_values_button_clicked(self):
        param: Param = self._helper.cf.param
        for full_param_name in self.mappers.keys():
            # For some reason we run into problems if we try to get all params in one go. Pace by getting them
            # one by one.
            syncer = Syncer()
            param.get_default_value(full_param_name, syncer.success_cb)
            syncer.wait()
            self._param_updated_cb(*syncer.success_args)

    def _enable_ui_objects(self, enabled):
        objects = [
            self.rate_link_checkbox,
            self.attitude_link_checkbox,
            self.position_link_checkbox,
            self.velocity_link_checkbox,
            self.store_button,
            self.clear_stored_button,
            self.default_values_button,
        ]

        for item in objects:
            item.setEnabled(enabled)

        for mapper in self.mappers.values():
            mapper.enable_ui(enabled)
