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
from PyQt5.QtCore import QAbstractTableModel, QVariant, Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import QInputDialog, QFileDialog
import yaml
import os

__author__ = 'Bitcraze AB'
__all__ = ['LighthouseBasestationGeometryDialog']

logger = logging.getLogger(__name__)

(anchor_postiong_widget_class, connect_widget_base_class) = (
    uic.loadUiType(
        cfclient.module_path + '/ui/dialogs/lighthouse_bs_geometry_dialog.ui')
)

class SweepAngleReader():

    def __init__(self, cf):
        self._cf = cf

    def get_averaged_angles(self, ready_cb):
        pass


class LighthouseBsGeometryDialog(QtWidgets.QWidget, anchor_postiong_widget_class):

    def __init__(self, lighthouse_tab, *args):
        super(LighthouseBsGeometryDialog, self).__init__(*args)
        self.setupUi(self)

        self._lighthouse_tab = lighthouse_tab

        self._estimate_geometry_button.clicked.connect(
            self._estimate_geometry_button_clicked)

        self._sweep_angles_received_and_processed_signal = pyqtSignal(object, object)

        self._sweep_angles_received_and_processed_signal.connect(
            self._sweep_angles_received_and_processed)

        self._sweep_angle_reader = SweepAngleReader(self._lighthouse_tab._helper.cf)

    def _sweep_angles_received_and_processed_cb(self):
        """Callback """
        print('cb triggered')
        pass


    def _estimate_geometry_button_clicked(self):
        print('button clicked')
        self._sweep_angle_reader.get_averaged_angles(self._sweep_angles_received_and_processed_cb.emit)


