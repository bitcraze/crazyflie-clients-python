# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2018-2023 Bitcraze AB
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

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import cfclient
from PySide6 import QtWidgets
from PySide6.QtUiTools import loadUiType
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QInputDialog, QFileDialog
import yaml
import os

from cfclient.ui.pluginhelper import PluginHelper

if TYPE_CHECKING:
    from cfclient.ui.tabs.locopositioning_tab import LocoPositioningTab

__author__ = "Bitcraze AB"
__all__ = ["AnchorPositionDialog"]

logger = logging.getLogger(__name__)

FILE_REGEX_YAML = "Config *.yaml;;All *.*"

Position = tuple[float, float, float]

(anchor_postiong_widget_class, connect_widget_base_class) = loadUiType(
    cfclient.module_path + "/ui/dialogs/anchor_position_dialog.ui"
)


class AnchorPositionConfigTableModel(QAbstractTableModel):
    def __init__(self, headers: list[str], parent: QObject | None = None) -> None:
        QAbstractTableModel.__init__(self, parent)
        self._anchor_positions = []
        self._headers = headers
        self._latest_known_anchor_positions = {}

        self._green_brush = QBrush(QColor(200, 255, 200))
        self._red_brush = QBrush(QColor(255, 200, 200))

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._anchor_positions)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._headers)

    def data(
        self, index: QModelIndex, role: int | None = None
    ) -> int | float | str | QBrush | None:
        value = self._anchor_positions[index.row()][index.column()]
        if index.isValid():
            if index.column() == 0:
                if role == Qt.ItemDataRole.CheckStateRole:
                    return value
            elif index.column() == 1:
                if role == Qt.ItemDataRole.DisplayRole:
                    return value
            else:
                if role == Qt.ItemDataRole.DisplayRole:
                    return "%.2f" % (value)
                elif role == Qt.ItemDataRole.EditRole:
                    return value
                elif role == Qt.ItemDataRole.BackgroundRole:
                    return self._get_background(index.row(), index.column())

        return

    def setData(
        self, index: QModelIndex, value: float, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        if not index.isValid():
            return False

        self._anchor_positions[index.row()][index.column()] = value
        return True

    def headerData(
        self, col: int, orientation: Qt.Orientation, role: int | None = None
    ) -> str | None:
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            return self._headers[col]
        return

    def flags(self, index: QModelIndex) -> Qt.ItemFlag | None:
        if not index.isValid():
            return None

        if index.column() == 0:
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
        elif index.column() == 1:
            return Qt.ItemFlag.ItemIsEnabled
        else:
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable

    def add_anchor(
        self, anchor_id: int, x: float = 0.0, y: float = 0.0, z: float = 0.0
    ) -> None:
        if not self._id_exist(anchor_id):
            self.layoutAboutToBeChanged.emit()
            self._anchor_positions.append([0, anchor_id, x, y, z])
            self._anchor_positions.sort(key=lambda row: row[1])
            self.layoutChanged.emit()

    def replace_anchors_from_latest_known_positions(self) -> None:
        self.replace_anchor_positions(self._latest_known_anchor_positions)

    def replace_anchor_positions(self, anchor_positions: dict[int, Position]) -> None:
        self.layoutAboutToBeChanged.emit()
        self._anchor_positions = []
        for id, position in anchor_positions.items():
            self.add_anchor(id, x=position[0], y=position[1], z=position[2])
        self.layoutChanged.emit()

    def get_anchor_postions(self) -> dict[int, Position]:
        result = {}
        for row in self._anchor_positions:
            result[row[1]] = (row[2], row[3], row[4])
        return result

    def anchor_postions_updated(self, anchor_positions: dict[int, Position]) -> None:
        self.layoutAboutToBeChanged.emit()
        self._latest_known_anchor_positions = anchor_positions
        self.layoutChanged.emit()

    def remove_selected_anchors(self) -> None:
        self.layoutAboutToBeChanged.emit()
        self._anchor_positions = list(
            filter(lambda row: row[0] == 0, self._anchor_positions)
        )
        self.layoutChanged.emit()

    def _id_exist(self, anchor_id: int) -> bool:
        for anchor in self._anchor_positions:
            if anchor[1] == anchor_id:
                return True
        return False

    def _get_background(self, row: int, col: int) -> QBrush | None:
        id = self._anchor_positions[row][1]
        if id in self._latest_known_anchor_positions:
            current_value = self._anchor_positions[row][col]
            latest_value = self._latest_known_anchor_positions[id][col - 2]

            if abs(current_value - latest_value) < 0.005:
                return self._green_brush
            else:
                return self._red_brush

        return


class AnchorPositionDialog(QtWidgets.QWidget, anchor_postiong_widget_class):
    def __init__(self, lps_tab: LocoPositioningTab, helper: PluginHelper) -> None:
        super(AnchorPositionDialog, self).__init__()
        self.setupUi(self)

        self._lps_tab = lps_tab
        self._helper = helper

        self._headers = ["", "id", "x", "y", "z"]
        self._data_model = AnchorPositionConfigTableModel(self._headers, self)
        self._table_view.setModel(self._data_model)

        self._table_view.verticalHeader().setVisible(False)

        header = self._table_view.horizontalHeader()
        header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Stretch)

        self._add_anchor_button.clicked.connect(self._add_anchor_button_clicked)
        self._remove_anchors_button.clicked.connect(
            self._data_model.remove_selected_anchors
        )
        self._get_from_anchors_button.clicked.connect(
            self._get_from_anchors_button_clicked
        )
        self._write_to_anchors_button.clicked.connect(
            self._write_to_anchors_button_clicked
        )
        self._close_button.clicked.connect(self.close)
        self._load_button.clicked.connect(self._load_button_clicked)
        self._save_button.clicked.connect(self._save_button_clicked)

    def _add_anchor_button_clicked(self) -> None:
        anchor_id, ok = QInputDialog.getInt(
            self, "New anchor", "Enter id", min=0, max=255
        )
        if ok:
            self._data_model.add_anchor(anchor_id)

    def _get_from_anchors_button_clicked(self) -> None:
        self._data_model.replace_anchors_from_latest_known_positions()

    def _write_to_anchors_button_clicked(self) -> None:
        anchor_positions = self._data_model.get_anchor_postions()
        self._lps_tab.write_positions_to_anchors(anchor_positions)

    def anchor_postions_updated(self, anchor_positions: dict[int, Position]) -> None:
        self._data_model.anchor_postions_updated(anchor_positions)

    def set_writing(self, writing: bool) -> None:
        """Disable the write button while positions are being written"""
        self._write_to_anchors_button.setEnabled(not writing)

    def _load_button_clicked(self) -> None:
        names = QFileDialog.getOpenFileName(
            self, "Open file", self._helper.current_folder, FILE_REGEX_YAML
        )

        if names[0] == "":
            return

        self._helper.current_folder = os.path.dirname(names[0])

        f = open(names[0], "r")
        with f:
            data = yaml.safe_load(f)

            anchor_positions = {}
            for id, pos in data.items():
                anchor_positions[id] = (pos["x"], pos["y"], pos["z"])
            self._data_model.replace_anchor_positions(anchor_positions)

    def _save_button_clicked(self) -> None:
        anchor_positions = self._data_model.get_anchor_postions()
        data = {}
        for id, pos in anchor_positions.items():
            data[id] = {"x": pos[0], "y": pos[1], "z": pos[2]}

        names = QFileDialog.getSaveFileName(
            self, "Save file", self._helper.current_folder, FILE_REGEX_YAML
        )

        if names[0] == "":
            return

        self._helper.current_folder = os.path.dirname(names[0])

        if not names[0].endswith(".yaml") and names[0].find(".") < 0:
            filename = names[0] + ".yaml"
        else:
            filename = names[0]

        f = open(filename, "w")
        with f:
            yaml.dump(data, f)
