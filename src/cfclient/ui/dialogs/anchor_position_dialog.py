# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2018 Bitcraze AB
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
Dialog box used to configure anchor positions. Used from the LPS tab.
"""
import logging

import cfclient
from PyQt5 import QtWidgets
from PyQt5 import uic
from PyQt5.QtCore import QAbstractTableModel, QVariant, Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import QInputDialog, QFileDialog
import yaml
import os

__author__ = 'Bitcraze AB'
__all__ = ['AnchorPositionDialog']

logger = logging.getLogger(__name__)

(anchor_postiong_widget_class, connect_widget_base_class) = (
    uic.loadUiType(
        cfclient.module_path + '/ui/dialogs/anchor_position_dialog.ui')
)


class AnchorPositionConfigTableModel(QAbstractTableModel):
    def __init__(self, headers, parent=None, *args):
        QAbstractTableModel.__init__(self, parent)
        self._anchor_positions = []
        self._headers = headers
        self._latest_known_anchor_positions = {}

        self._green_brush = QBrush(QColor(200, 255, 200))
        self._red_brush = QBrush(QColor(255, 200, 200))

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._anchor_positions)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self._headers)

    def data(self, index, role=None):
        value = self._anchor_positions[index.row()][index.column()]
        if index.isValid():
            if index.column() == 0:
                if role == Qt.CheckStateRole:
                    return QVariant(value)
            elif index.column() == 1:
                if role == Qt.DisplayRole:
                    return QVariant(value)
            else:
                if role == Qt.DisplayRole:
                    return QVariant('%.2f' % (value))
                elif role == Qt.EditRole:
                    return QVariant(value)
                elif role == Qt.BackgroundRole:
                    return self._get_background(index.row(), index.column())

        return QVariant()

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False

        self._anchor_positions[index.row()][index.column()] = value
        return True

    def headerData(self, col, orientation, role=None):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return QVariant(self._headers[col])
        return QVariant()

    def flags(self, index):
        if not index.isValid():
            return None

        if index.column() == 0:
            return Qt.ItemIsEnabled | Qt.ItemIsUserCheckable
        elif index.column() == 1:
            return Qt.ItemIsEnabled
        else:
            return Qt.ItemIsEnabled | Qt.ItemIsEditable

    def add_anchor(self, anchor_id, x=0.0, y=0.0, z=0.0):
        if not self._id_exist(anchor_id):
            self.layoutAboutToBeChanged.emit()
            self._anchor_positions.append([0, anchor_id, x, y, z])
            self._anchor_positions.sort(key=lambda row: row[1])
            self.layoutChanged.emit()

    def replace_anchors_from_latest_known_positions(self):
        self.replace_anchor_positions(self._latest_known_anchor_positions)

    def replace_anchor_positions(self, anchor_positions):
        self.layoutAboutToBeChanged.emit()
        self._anchor_positions = []
        for id, position in anchor_positions.items():
            self.add_anchor(id, x=position[0], y=position[1], z=position[2])
        self.layoutChanged.emit()

    def get_anchor_postions(self):
        result = {}
        for row in self._anchor_positions:
            result[row[1]] = (row[2], row[3], row[4])
        return result

    def anchor_postions_updated(self, anchor_positions):
        self.layoutAboutToBeChanged.emit()
        self._latest_known_anchor_positions = anchor_positions
        self.layoutChanged.emit()

    def remove_selected_anchors(self):
        self.layoutAboutToBeChanged.emit()
        self._anchor_positions = list(filter(
            lambda row: row[0] == 0, self._anchor_positions))
        self.layoutChanged.emit()

    def _id_exist(self, anchor_id):
        for anchor in self._anchor_positions:
            if anchor[1] == anchor_id:
                return True
        return False

    def _get_background(self, row, col):
        id = self._anchor_positions[row][1]
        if id in self._latest_known_anchor_positions:
            current_value = self._anchor_positions[row][col]
            latest_value = self._latest_known_anchor_positions[id][col - 2]

            if abs(current_value - latest_value) < 0.005:
                return self._green_brush
            else:
                return self._red_brush

        return QVariant()


class AnchorPositionDialog(QtWidgets.QWidget, anchor_postiong_widget_class):

    def __init__(self, lps_tab, *args):
        super(AnchorPositionDialog, self).__init__(*args)
        self.setupUi(self)

        self._current_folder = os.path.expanduser('~')

        self._lps_tab = lps_tab

        self._headers = ['', 'id', 'x', 'y', 'z']
        self._data_model = AnchorPositionConfigTableModel(self._headers, self)
        self._table_view.setModel(self._data_model)

        self._table_view.verticalHeader().setVisible(False)

        header = self._table_view.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)

        self._add_anchor_button.clicked.connect(
            self._add_anchor_button_clicked)
        self._remove_anchors_button.clicked.connect(
            self._data_model.remove_selected_anchors)
        self._get_from_anchors_button.clicked.connect(
            self._get_from_anchors_button_clicked)
        self._write_to_anchors_button.clicked.connect(
            self._write_to_anchors_button_clicked)
        self._close_button.clicked.connect(self.close)
        self._load_button.clicked.connect(
            self._load_button_clicked)
        self._save_button.clicked.connect(
            self._save_button_clicked)

    def _add_anchor_button_clicked(self):
        anchor_id, ok = QInputDialog.getInt(
            self, "New anchor", "Enter id", min=0, max=255)
        if ok:
            self._data_model.add_anchor(anchor_id)

    def _get_from_anchors_button_clicked(self):
        self._data_model.replace_anchors_from_latest_known_positions()

    def _write_to_anchors_button_clicked(self):
        anchor_positions = self._data_model.get_anchor_postions()
        self._lps_tab.write_positions_to_anchors(anchor_positions)

    def anchor_postions_updated(self, anchor_positions):
        self._data_model.anchor_postions_updated(anchor_positions)

    def _load_button_clicked(self):
        names = QFileDialog.getOpenFileName(self, 'Open file',
                                            self._current_folder,
                                            "*.yaml;;*.*")

        if names[0] == '':
            return

        self._current_folder = os.path.dirname(names[0])

        f = open(names[0], 'r')
        with f:
            data = yaml.load(f)

            anchor_positions = {}
            for id, pos in data.items():
                anchor_positions[id] = (pos['x'], pos['y'], pos['z'])
            self._data_model.replace_anchor_positions(anchor_positions)

    def _save_button_clicked(self):
        anchor_positions = self._data_model.get_anchor_postions()
        data = {}
        for id, pos in anchor_positions.items():
            data[id] = {'x': pos[0], 'y': pos[1], 'z': pos[2]}

        names = QFileDialog.getSaveFileName(self, 'Save file',
                                            self._current_folder,
                                            "*.yaml;;*.*")

        if names[0] == '':
            return

        self._current_folder = os.path.dirname(names[0])

        if not names[0].endswith(".yaml") and names[0].find(".") < 0:
            filename = names[0] + ".yaml"
        else:
            filename = names[0]

        f = open(filename, 'w')
        with f:
            yaml.dump(data, f)
