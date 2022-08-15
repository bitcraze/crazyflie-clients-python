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
from PyQt5.QtCore import QVariant, Qt, QAbstractTableModel, pyqtSignal
from cflib.localization import LighthouseBsGeoEstimator
from cflib.localization import LighthouseSweepAngleAverageReader
from cflib.crazyflie.mem import LighthouseBsGeometry
from cfclient.ui.wizards.lighthouse_geo_bs_estimation_wizard import LighthouseBasestationGeometryWizard

__author__ = 'Bitcraze AB'
__all__ = ['LighthouseBsGeometryDialog']

logger = logging.getLogger(__name__)

(basestation_geometry_widget_class, connect_widget_base_class) = (
    uic.loadUiType(
        cfclient.module_path + '/ui/dialogs/lighthouse_bs_geometry_dialog.ui')
)


class LighthouseBsGeometryTableModel(QAbstractTableModel):
    def __init__(self, headers, parent=None, *args):
        QAbstractTableModel.__init__(self, parent)
        self._headers = headers
        self._table_values = []
        self._current_geos = {}
        self._estimated_geos = {}

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._table_values)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self._headers)

    def data(self, index, role=None):
        if index.isValid():
            value = self._table_values[index.row()][index.column()]
            if role == Qt.DisplayRole:
                return QVariant(value)

        return QVariant()

    def headerData(self, col, orientation, role=None):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return QVariant(self._headers[col])
        return QVariant()

    def _compile_entry(self, current_geo, estimated_geo, index):
        result = 'N/A'
        if current_geo is not None:
            result = '%.2f' % current_geo.origin[index]
        if estimated_geo is not None:
            result += ' -> %.2f' % estimated_geo.origin[index]

        return result

    def _add_table_value(self, current_geo, estimated_geo, id, table_values):
        x = self._compile_entry(current_geo, estimated_geo, 0)
        y = self._compile_entry(current_geo, estimated_geo, 1)
        z = self._compile_entry(current_geo, estimated_geo, 2)

        table_values.append([id + 1, x, y, z])

    def _add_table_value_for_id(self, current_geos, estimated_geos, table_values, id):
        current_geo = None
        if id in current_geos:
            current_geo = current_geos[id]

        estimated_geo = None
        if id in estimated_geos:
            estimated_geo = estimated_geos[id]

        if current_geo is not None or estimated_geo is not None:
            self._add_table_value(current_geo, estimated_geo, id, table_values)

    def _add_table_values(self, current_geos, estimated_geos, table_values):
        current_ids = set(current_geos.keys())
        estimated_ids = set(estimated_geos.keys())
        all_ids = current_ids.union(estimated_ids)

        for id in all_ids:
            self._add_table_value_for_id(current_geos, estimated_geos, table_values, id)

    def _update_table_data(self):
        self.layoutAboutToBeChanged.emit()
        self._table_values = []
        self._add_table_values(self._current_geos, self._estimated_geos, self._table_values)
        self._table_values.sort(key=lambda row: row[0])
        self.layoutChanged.emit()

    def set_estimated_geos(self, geos):
        self._estimated_geos = geos
        self._update_table_data()

    def set_current_geos(self, geos):
        self._current_geos = geos
        self._update_table_data()


class LighthouseBsGeometryDialog(QtWidgets.QWidget, basestation_geometry_widget_class):

    _sweep_angles_received_and_averaged_signal = pyqtSignal(object)
    _base_station_geometery_received_signal = pyqtSignal(object)

    def __init__(self, lighthouse_tab, *args):
        super(LighthouseBsGeometryDialog, self).__init__(*args)
        self.setupUi(self)

        self._lighthouse_tab = lighthouse_tab

        self._estimate_geometry_button.clicked.connect(self._estimate_geometry_button_clicked)
        self._simple_estimator = LighthouseBsGeoEstimator()
        self._estimate_geometry_simple_button.clicked.connect(self._estimate_geometry_simple_button_clicked)
        try:
            if not self._simple_estimator.is_available():
                self._estimate_geometry_simple_button.setEnabled(False)
        except Exception as e:
            print(e)

        self._write_to_cf_button.clicked.connect(self._write_to_cf_button_clicked)

        self._sweep_angles_received_and_averaged_signal.connect(self._sweep_angles_received_and_averaged_cb)
        self._base_station_geometery_received_signal.connect(self._basestation_geometry_received_signal_cb)
        self._close_button.clicked.connect(self.close)

        self._sweep_angle_reader = LighthouseSweepAngleAverageReader(
            self._lighthouse_tab._helper.cf, self._sweep_angles_received_and_averaged_signal.emit)

        self._base_station_geometry_wizard = LighthouseBasestationGeometryWizard(
            self._lighthouse_tab._helper.cf, self._base_station_geometery_received_signal.emit)

        self._lh_geos = None
        self._newly_estimated_geometry = {}

        # Table handlers
        self._headers = ['id', 'x', 'y', 'z']
        self._data_model = LighthouseBsGeometryTableModel(self._headers, self)
        self._table_view.setModel(self._data_model)

        self._table_view.verticalHeader().setVisible(False)

        header = self._table_view.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)

        self._update_ui()

    def reset(self):
        self._newly_estimated_geometry = {}
        self._update_ui()

    def _basestation_geometry_received_signal_cb(self, basestation_geometries):
        self._newly_estimated_geometry = basestation_geometries
        self.show()
        self._update_ui()

    def _sweep_angles_received_and_averaged_cb(self, averaged_angles):
        self._averaged_angles = averaged_angles
        self._newly_estimated_geometry = {}

        for id, average_data in averaged_angles.items():
            sensor_data = average_data[1]
            rotation_bs_matrix, position_bs_vector = self._simple_estimator.estimate_geometry(sensor_data)
            geo = LighthouseBsGeometry()
            geo.rotation_matrix = rotation_bs_matrix
            geo.origin = position_bs_vector
            geo.valid = True
            self._newly_estimated_geometry[id] = geo

        self._update_ui()

    def _estimate_geometry_button_clicked(self):
        self._base_station_geometry_wizard.reset()
        self._base_station_geometry_wizard.show()
        self.hide()

    def _estimate_geometry_simple_button_clicked(self):
        self._sweep_angle_reader.start_angle_collection()
        self._update_ui()

    def _write_to_cf_button_clicked(self):
        if len(self._newly_estimated_geometry) > 0:
            self._lighthouse_tab.write_and_store_geometry(self._newly_estimated_geometry)
            self._newly_estimated_geometry = {}

        self._update_ui()

    def _update_ui(self):
        self._write_to_cf_button.setEnabled(len(self._newly_estimated_geometry) > 0)
        self._data_model.set_estimated_geos(self._newly_estimated_geometry)

    def closeEvent(self, event):
        self._stop_collection()

    def _stop_collection(self):
        self._sweep_angle_reader.stop_angle_collection()

    def geometry_updated(self, geometry):
        self._data_model.set_current_geos(geometry)

        self._update_ui()
