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
Dialog box used to change lighthouse system type. Used from the lighthouse tab.
"""
import logging

import cfclient
from PyQt5 import QtWidgets
from PyQt5 import uic

__author__ = 'Bitcraze AB'
__all__ = ['LighthouseSystemTypeDialog']

logger = logging.getLogger(__name__)

(lighthouse_system_widget_class, connect_widget_base_class) = (
    uic.loadUiType(
        cfclient.module_path + '/ui/dialogs/lighthouse_system_type_dialog.ui')
)


class LighthouseSystemTypeDialog(QtWidgets.QWidget, lighthouse_system_widget_class):

    PARAM_GROUP = 'lighthouse'
    PARAM_NAME = 'systemType'

    VALUE_V1 = 1
    VALUE_V2 = 2

    def __init__(self, helper, *args):
        super(LighthouseSystemTypeDialog, self).__init__(*args)
        self.setupUi(self)

        self._helper = helper

        self._close_button.clicked.connect(self.close)

        self._radio_btn_v1.toggled.connect(self._type_toggled)
        self._radio_btn_v2.toggled.connect(self._type_toggled)

        self._curr_type = 0

    def get_system_type(self):
        system_type = self.VALUE_V2

        values = self._helper.cf.param.values
        if self.PARAM_NAME in values[self.PARAM_GROUP]:
            system_type = int(values[self.PARAM_GROUP][self.PARAM_NAME])

        return system_type

    def showEvent(self, event):
        self._curr_type = self.get_system_type()

        if self._curr_type == self.VALUE_V1:
            self._radio_btn_v1.setChecked(True)
        elif self._curr_type == self.VALUE_V2:
            self._radio_btn_v2.setChecked(True)

    def _type_toggled(self, *args):
        new_type = self.VALUE_V2

        if self._radio_btn_v1.isChecked():
            new_type = self.VALUE_V1
        elif self._radio_btn_v2.isChecked():
            new_type = self.VALUE_V2

        if new_type != self._curr_type:
            self._curr_type = new_type
            self._helper.cf.param.set_value(self.PARAM_GROUP + '.' + self.PARAM_NAME, self._curr_type)
