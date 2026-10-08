# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2021-2026 Bitcraze AB
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

from __future__ import annotations

import logging

from PySide6 import QtWidgets
from PySide6.QtGui import QShowEvent
from PySide6.QtUiTools import loadUiType

import cfclient
from cfclient.gui import create_task

from cflib2 import Crazyflie
from cflib2.error import ParamError, VariableNotFoundError

__author__ = "Bitcraze AB"
__all__ = ["LighthouseSystemTypeDialog"]

logger = logging.getLogger(__name__)

(lighthouse_system_widget_class, connect_widget_base_class) = loadUiType(
    cfclient.module_path + "/ui/dialogs/lighthouse_system_type_dialog.ui"
)


class LighthouseSystemTypeDialog(QtWidgets.QWidget, lighthouse_system_widget_class):
    PARAM_NAME = "lighthouse.systemType"

    VALUE_V1 = 1
    VALUE_V2 = 2

    def __init__(self, *args: object) -> None:
        super(LighthouseSystemTypeDialog, self).__init__(*args)
        self.setupUi(self)

        self._cf: Crazyflie | None = None

        self._close_button.clicked.connect(self.close)

        self._radio_btn_v1.toggled.connect(self._type_toggled)
        self._radio_btn_v2.toggled.connect(self._type_toggled)

        self._curr_type = 0

    def connected(self, cf: Crazyflie) -> None:
        self._cf = cf

    def disconnected(self) -> None:
        self._cf = None
        self.close()

    async def get_system_type(self) -> int:
        """Read the system type from the Crazyflie. Defaults to Lighthouse V2 if it can not be read."""
        if self._cf is None:
            return self.VALUE_V2

        try:
            return int(await self._cf.param().get(self.PARAM_NAME))
        except (ParamError, VariableNotFoundError) as e:
            logger.warning("Could not read %s: %s", self.PARAM_NAME, e)
            return self.VALUE_V2

    def showEvent(self, event: QShowEvent) -> None:
        create_task(self._show_current_type())

    async def _show_current_type(self) -> None:
        self._curr_type = await self.get_system_type()

        if self._curr_type == self.VALUE_V1:
            self._radio_btn_v1.setChecked(True)
        elif self._curr_type == self.VALUE_V2:
            self._radio_btn_v2.setChecked(True)

    def _type_toggled(self, *args: object) -> None:
        new_type = self.VALUE_V2

        if self._radio_btn_v1.isChecked():
            new_type = self.VALUE_V1
        elif self._radio_btn_v2.isChecked():
            new_type = self.VALUE_V2

        if new_type != self._curr_type:
            self._curr_type = new_type
            create_task(self._set_system_type(new_type))

    async def _set_system_type(self, system_type: int) -> None:
        if self._cf is None:
            return

        try:
            await self._cf.param().set(self.PARAM_NAME, system_type)
        except (ParamError, VariableNotFoundError) as e:
            logger.warning("Could not set %s: %s", self.PARAM_NAME, e)
