# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2021 Bitcraze AB
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
Dialog box used to configure base station geometry. Used from the lighthouse tab.
"""
import logging

import cfclient
from PyQt5 import QtWidgets
from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import QInputDialog, QFileDialog
import yaml
import os
from cflib.localization.lighthouse_bs_vector import LighthouseBsVector
from cflib.localization.lighthouse_bs_geo import LighthouseBsGeoEstimator
from cflib.crazyflie.mem import LighthouseBsGeometry

__author__ = 'Bitcraze AB'
__all__ = ['LighthouseBasestationGeometryDialog']

logger = logging.getLogger(__name__)

(anchor_postiong_widget_class, connect_widget_base_class) = (
    uic.loadUiType(
        cfclient.module_path + '/ui/dialogs/lighthouse_bs_geometry_dialog.ui')
)


class LighthouseSweepAngleReader():
    ANGLE_STREAM_PARAM = 'locSrv.enLhAngleStream'
    NR_OF_SENSORS = 4

    def __init__(self, cf, data_recevied_cb):
        self._cf = cf
        self._cb = data_recevied_cb

    def start(self):
        self._cf.loc.receivedLocationPacket.add_callback(self._packet_received_cb)
        self._angle_stream_activate(True)

    def stop(self):
        self._cf.loc.receivedLocationPacket.remove_callback(self._packet_received_cb)
        self._angle_stream_activate(False)

    def _angle_stream_activate(self, is_active):
        value = 0
        if is_active:
            value = 1
        self._cf.param.set_value(self.ANGLE_STREAM_PARAM, value)

    def _packet_received_cb(self, packet):
        if packet.type != self._cf.loc.LH_ANGLE_STREAM:
            return

        if self._cb:
            base_station_id = packet.data["basestation"]
            horiz_angles = packet.data['x']
            vert_angles = packet.data['y']

            result = []
            for i in range(self.NR_OF_SENSORS):
                result.append(LighthouseBsVector(horiz_angles[i], vert_angles[i]))

            self._cb(base_station_id, result)


class LighthouseSweepAngleAverageReader():
    def __init__(self, cf, ready_cb):
        self._reader = LighthouseSweepAngleReader(cf, self._data_recevied_cb)
        self._ready_cb = ready_cb
        self.nr_of_samples_required = 50

        # We store all samples in the storage for averaging when data is collected
        # The storage is a dictionary keyed on the base station channel
        # Each entry is a list of 4 lists, one per sensor.
        # Each list contains LighthouseBsVector objects, representing the sampled sweep angles
        self._sample_storage = None

    def start_angle_collection(self):
        self._sample_storage = {}
        self._reader.start()

    def is_collecting(self):
        return self._sample_storage is not None

    def _data_recevied_cb(self, base_station_id, bs_vectors):
        self._store_sample(base_station_id, bs_vectors, self._sample_storage)
        if self._has_collected_enough_data(self._sample_storage):
            self._reader.stop()
            if self._ready_cb:
                averages = self._average_all_lists(self._sample_storage)
                self._ready_cb(averages)
            self._sample_storage = None

    def _store_sample(self, base_station_id, bs_vectors, storage):
        if not base_station_id in storage:
            # TODO fix, use const
            storage[base_station_id] = [[], [], [], []]

        for sensor in range(self._reader.NR_OF_SENSORS):
            storage[base_station_id][sensor].append(bs_vectors[sensor])

    def _has_collected_enough_data(self, storage):
        for sample_list in storage.values():
            if len(sample_list[0]) >= self.nr_of_samples_required:
                return True
        return False

    def _average_all_lists(self, storage):
        result = {}

        for id, sample_lists in storage.items():
            averages = self._average_sample_lists(sample_lists)
            count = len(sample_lists[0])
            result[id] = (count, averages)

        return result

    def _average_sample_lists(self, sample_lists):
        result = []

        for i in range(self._reader.NR_OF_SENSORS):
            result.append(self._average_sample_list(sample_lists[i]))

        return result

    def _average_sample_list(self, sample_list):
        sum_horiz = 0.0
        sum_vert = 0.0

        for bs_vector in sample_list:
            sum_horiz += bs_vector.lh_v1_horiz_angle
            sum_vert += bs_vector.lh_v1_vert_angle

        count = len(sample_list)
        return LighthouseBsVector(sum_horiz / count, sum_vert / count)


class LighthouseBsGeometryDialog(QtWidgets.QWidget, anchor_postiong_widget_class):

    _sweep_angles_received_and_averaged_signal = pyqtSignal(object)

    def __init__(self, lighthouse_tab, *args):
        super(LighthouseBsGeometryDialog, self).__init__(*args)
        self.setupUi(self)

        self._lighthouse_tab = lighthouse_tab

        self._estimate_geometry_button.clicked.connect(
            self._estimate_geometry_button_clicked)

        self._sweep_angles_received_and_averaged_signal.connect(self._sweep_angles_received_and_averaged_cb)
        self._close_button.clicked.connect(self.close)

        self._sweep_angle_reader = LighthouseSweepAngleAverageReader(self._lighthouse_tab._helper.cf, self._sweep_angles_received_and_averaged_signal.emit)

        self._averaged_angles = None

        self._newly_estimated_geometry = None

        self._update_ui()

    def _sweep_angles_received_and_averaged_cb(self, averaged_angles):
        self._averaged_angles = averaged_angles
        estimator = LighthouseBsGeoEstimator()
        self._newly_estimated_geometry = {}
        
        for id, average_data in averaged_angles.items():
            nr_samples = average_data[0]
            sensor_data = average_data[1]
            rotation_bs_matrix, position_bs_vector = estimator.estimate_geometry(sensor_data)
            geo = LighthouseBsGeometry()
            geo.rotation_matrix = rotation_bs_matrix
            geo.origin = position_bs_vector
            geo.valid = True
            self._newly_estimated_geometry[id] = geo

        self._update_ui()

    def _estimate_geometry_button_clicked(self):
        self._sweep_angle_reader.start_angle_collection()
        self._update_ui()

    def _update_ui(self):
        self._estimate_geometry_button.setEnabled(not self._sweep_angle_reader.is_collecting())
