#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2026 Bitcraze AB
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
Container for the geometry estimation functionality in the lighthouse tab.
"""

import logging
from enum import Enum

from PyQt6 import QtCore, QtWidgets, uic, QtGui
from PyQt6.QtCore import QAbstractTableModel, QVariant, Qt, QModelIndex, QItemSelection

from cflib.localization.lighthouse_cf_pose_sample import LhCfPoseSampleType
from cflib.localization.lighthouse_geometry_solution import LighthouseGeometrySolution
import cfclient

__author__ = 'Bitcraze AB'
__all__ = ['GeoEstimatorDetailsWidget']

logger = logging.getLogger(__name__)

(geo_estimator_details_widget_class, connect_widget_base_class) = (
    uic.loadUiType(cfclient.module_path + '/ui/widgets/geo_estimator_details.ui'))


class GeoEstimatorDetailsWidget(QtWidgets.QWidget, geo_estimator_details_widget_class):
    """Widget for the samples and base stations details of the geometry estimator UI"""

    sample_selection_changed_signal = QtCore.pyqtSignal(int)
    base_station_selection_changed_signal = QtCore.pyqtSignal(int)
    do_remove_sample_signal = QtCore.pyqtSignal(int)
    do_convert_to_xyz_space_sample_signal = QtCore.pyqtSignal(int)
    do_convert_to_verification_sample_signal = QtCore.pyqtSignal(int)

    def __init__(self):
        super(GeoEstimatorDetailsWidget, self).__init__()
        self.setupUi(self)

        # Create sample details table
        self._samples_details_model = SampleTableModel(self)
        self._samples_table_view.setModel(self._samples_details_model)
        self._samples_table_view.selectionModel().selectionChanged.connect(self._sample_selection_changed)

        header_samples = self._samples_table_view.horizontalHeader()
        header_samples.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_samples.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_samples.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_samples.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        self._samples_table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._samples_table_view.customContextMenuRequested.connect(self._create_sample_table_context_menu)

        # Create base station details table
        self._base_stations_details_model = BaseStationTableModel(self)
        self._base_stations_table_view.setModel(self._base_stations_details_model)
        self._base_stations_table_view.selectionModel().selectionChanged.connect(self._base_station_selection_changed)

        header_base_stations = self._base_stations_table_view.horizontalHeader()
        header_base_stations.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_base_stations.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_base_stations.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_base_stations.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_base_stations.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        self._samples_widget.setVisible(False)
        self._base_stations_widget.setVisible(False)

    def _create_sample_table_context_menu(self, point):
        menu = QtWidgets.QMenu()

        delete_action = None

        item = self._samples_table_view.indexAt(point)
        row = item.row()
        if row >= 0:
            uid = self._samples_details_model.get_uid_of_row(item.row())
            sample_type = self._samples_details_model.get_sample_type_of_row(row)

            delete_action = menu.addAction('Delete sample')
            if sample_type == LhCfPoseSampleType.VERIFICATION:
                change_action = menu.addAction('Change to XYZ-space sample')
            else:
                change_action = menu.addAction('Change to verification sample')

            action = menu.exec(self._samples_table_view.mapToGlobal(point))

            if action == delete_action:
                self.do_remove_sample_signal.emit(uid)
            elif action == change_action:
                if sample_type == LhCfPoseSampleType.VERIFICATION:
                    self.do_convert_to_xyz_space_sample_signal.emit(uid)
                else:
                    self.do_convert_to_verification_sample_signal.emit(uid)

    def _sample_selection_changed(self, current: QItemSelection, previous: QItemSelection):
        # Called from the sample details table when the selection changes
        model_indexes = current.indexes()

        if len(model_indexes) > 0:
            #  model_indexes contains one index per column, just take the first one
            row = model_indexes[0].row()
            self.sample_selection_changed_signal.emit(row)

            self._base_stations_table_view.clearSelection()
        else:
            self.sample_selection_changed_signal.emit(-1)

    def _base_station_selection_changed(self, current: QItemSelection, previous: QItemSelection):
        # Called from the base station details table when the selection changes
        model_indexes = current.indexes()

        if len(model_indexes) > 0:
            #  model_indexes contains one index per column, just take the first one
            row = model_indexes[0].row()
            bs_id = self._base_stations_details_model.get_bs_id_of_row(row)
            self.base_station_selection_changed_signal.emit(bs_id)

            self._samples_table_view.clearSelection()
        else:
            self.base_station_selection_changed_signal.emit(-1)

    def solution_ready_cb(self, solution: LighthouseGeometrySolution):
        self._samples_details_model.set_solution(solution)
        self._base_stations_details_model.set_solution(solution)

        # There seems to be some issues with the selection when updating the model. Reset the 3D-graph selection to avoid problems.
        self.sample_selection_changed_signal.emit(-1)
        self.base_station_selection_changed_signal.emit(-1)

    def set_selected_sample(self, index: int):
        # Called from the 3D-graph when the selected sample changes
        self._base_stations_table_view.clearSelection()

        if index >= 0:
            self._samples_table_view.selectRow(index)
        else:
            self._samples_table_view.clearSelection()

    def set_selected_base_station(self, bs_id: int):
        # Called from the 3D-graph when the selected base station changes
        self._samples_table_view.clearSelection()

        if bs_id >= 0:
            row = self._base_stations_details_model.get_row_of_bs_id(bs_id)
            self._base_stations_table_view.selectRow(row)
        else:
            self._base_stations_table_view.clearSelection()

    def details_checkbox_state_changed(self, state: int):
        enabled = state == Qt.CheckState.Checked.value
        self._samples_widget.setVisible(enabled)
        self._base_stations_widget.setVisible(enabled)


class _TableRowStatus(Enum):
    INVALID = 1
    LARGE_ERROR = 2
    VERIFICATION = 3
    TOO_FEW_LINKS = 4


class SampleTableModel(QAbstractTableModel):
    def __init__(self, parent=None, *args):
        QAbstractTableModel.__init__(self, parent)
        self._headers = ['Type', 'X', 'Y', 'Z', 'Err']
        self._table_values = []
        self._uids: list[int] = []
        self._sample_types: list[LhCfPoseSampleType] = []
        self._table_highlights: list[set[_TableRowStatus]] = []

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._table_values)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self._headers)

    def data(self, index: QModelIndex, role: Qt.ItemDataRole) -> QVariant:
        if index.isValid():
            if role == Qt.ItemDataRole.DisplayRole:
                if index.column() < len(self._table_values[index.row()]):
                    value = self._table_values[index.row()][index.column()]
                    return QVariant(value)

            if role == Qt.ItemDataRole.BackgroundRole:
                color = None
                if _TableRowStatus.VERIFICATION in self._table_highlights[index.row()]:
                    color = QtGui.QColor(255, 255, 230)
                if _TableRowStatus.INVALID in self._table_highlights[index.row()]:
                    color = Qt.GlobalColor.gray
                if _TableRowStatus.LARGE_ERROR in self._table_highlights[index.row()]:
                    if index.column() == 4:
                        color = QtGui.QColor(255, 182, 193)

                if color:
                    return QVariant(QtGui.QBrush(color))

        return QVariant()

    def headerData(self, col, orientation, role=None):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return QVariant(self._headers[col])
        return QVariant()

    def set_solution(self, solution: LighthouseGeometrySolution):
        """Set the solution and update the table values"""
        self.beginResetModel()
        self._table_values = []
        self._uids = []
        self._sample_types = []
        self._table_highlights = []

        for sample in solution.samples:
            status: set[_TableRowStatus] = set()
            x = y = z = '--'
            error = '--'

            if sample.sample_type == LhCfPoseSampleType.VERIFICATION:
                status.add(_TableRowStatus.VERIFICATION)

            if sample.is_valid:
                if sample.has_pose:
                    error = f'{sample.error_distance * 1000:.1f} mm'
                    pose = sample.pose
                    x = f'{pose.translation[0]:.2f}'
                    y = f'{pose.translation[1]:.2f}'
                    z = f'{pose.translation[2]:.2f}'

                    if sample.is_error_large:
                        status.add(_TableRowStatus.LARGE_ERROR)
            else:
                error = f'{sample.status}'
                status.add(_TableRowStatus.INVALID)

            self._table_values.append([
                f'{sample.sample_type}',
                x,
                y,
                z,
                error,
            ])
            self._uids.append(sample.uid)
            self._sample_types.append(sample.sample_type)
            self._table_highlights.append(status)

        self.endResetModel()

    def get_uid_of_row(self, row: int) -> int:
        """Get the sample UID for a given row"""
        if 0 <= row < len(self._uids):
            return self._uids[row]

        raise IndexError("Row index out of range")

    def get_sample_type_of_row(self, row: int) -> LhCfPoseSampleType:
        """Get the sample type for a given row"""
        if 0 <= row < len(self._sample_types):
            return self._sample_types[row]

        raise IndexError("Row index out of range")


class BaseStationTableModel(QAbstractTableModel):
    def __init__(self, parent=None, *args):
        QAbstractTableModel.__init__(self, parent)
        self._headers = ['Id', 'X', 'Y', 'Z', 'Samples', 'Links']
        self._table_values = []
        self._table_highlights: list[set[_TableRowStatus]] = []

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._table_values)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self._headers)

    def data(self, index: QModelIndex, role: Qt.ItemDataRole) -> QVariant:
        if index.isValid():
            if role == Qt.ItemDataRole.DisplayRole:
                if index.column() < len(self._table_values[index.row()]):
                    value = self._table_values[index.row()][index.column()]
                    return QVariant(value)

            if role == Qt.ItemDataRole.BackgroundRole:
                color = None
                if _TableRowStatus.TOO_FEW_LINKS in self._table_highlights[index.row()]:
                    if index.column() == 5:
                        color = QtGui.QColor(255, 182, 193)

                if color:
                    return QVariant(QtGui.QBrush(color))

        return QVariant()

    def headerData(self, col, orientation, role=None):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return QVariant(self._headers[col])
        return QVariant()

    def set_solution(self, solution: LighthouseGeometrySolution):
        """Set the solution and update the table values"""
        self.beginResetModel()
        self._table_values = []
        self._table_highlights = []

        # Dictionary keys may not be ordered, sort by base station ID
        for bs_id, pose in sorted(solution.bs_poses.items()):
            status: set[_TableRowStatus] = set()

            x = f'{pose.translation[0]:.2f}'
            y = f'{pose.translation[1]:.2f}'
            z = f'{pose.translation[2]:.2f}'

            link_count = len(solution.link_count[bs_id])
            if link_count < solution.link_count_ok_threshold:
                status.add(_TableRowStatus.TOO_FEW_LINKS)

            samples_containing_bs = solution.bs_sample_count[bs_id]

            self._table_values.append([
                bs_id + 1,
                x,
                y,
                z,
                samples_containing_bs,
                link_count,
            ])
            self._table_highlights.append(status)

        self.endResetModel()

    def get_bs_id_of_row(self, row: int) -> int:
        """Get the base station ID for a given row"""
        if 0 <= row < len(self._table_values):
            bs_id = self._table_values[row][0] - 1  # IDs are 1-based in the table
            return bs_id

        return -1

    def get_row_of_bs_id(self, bs_id: int) -> int:
        """Get the row index for a given base station ID"""
        for row, values in enumerate(self._table_values):
            if values[0] - 1 == bs_id:  # IDs are 1-based in the table
                return row

        return -1
