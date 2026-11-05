#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2026 Bitcraze AB
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
The WiFi camera dialog is used to connect to and control WiFi cameras.
"""

import logging

from PyQt6 import QtWidgets, uic
from PyQt6.QtWidgets import QPushButton

import cfclient

__author__ = 'Bitcraze AB'
__all__ = ['WifiCameraDialog']

logger = logging.getLogger(__name__)

wifi_camera_dialog_class = uic.loadUiType(cfclient.module_path +
                                          "/ui/dialogs/wifi_dialog.ui")[0]


class WifiCameraDialog(QtWidgets.QWidget, wifi_camera_dialog_class):
    """Dialog for connecting to and controlling WiFi cameras"""

    def __init__(self, helper, *args):
        super(WifiCameraDialog, self).__init__(*args)
        self.setupUi(self)

        self._helper = helper

        self.scanButton.clicked.connect(self._on_scan_clicked)
        self.connectButton.clicked.connect(self._on_connect_clicked)
        self.networkNameEdit.textChanged.connect(self._update_connect_button)

        self.set_status('Not Connected')
        # TODO: placeholder networks to show the design, replace with the saved networks from the lib
        self.set_saved_networks(['Network 1', 'Network 2', 'Network 3'])

    def _on_scan_clicked(self):
        # TODO: scan for networks through the camera lib and call set_scan_results()
        logger.info('Scan for networks clicked')

    def _on_connect_clicked(self):
        # TODO: connect to the network through the camera lib
        logger.info('Connect clicked for network [%s]', self.networkNameEdit.text())

    def _on_saved_network_clicked(self, name):
        # TODO: connect to the saved network through the camera lib
        logger.info('Saved network [%s] clicked', name)

    def _update_connect_button(self):
        self.connectButton.setEnabled(bool(self.networkNameEdit.text()))

    def set_status(self, text):
        self.statusLabel.setText('Status: <b>%s</b>' % text)

    def set_scan_results(self, names):
        """Show the networks found by a scan"""
        self._fill_layout(self.scanResultsLayout, names)

    def set_saved_networks(self, names):
        """Show the saved networks as buttons"""
        self._fill_layout(self.savedNetworksLayout, names)
        self.savedNetworksLayout.addStretch()

    def _fill_layout(self, layout, names):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        for name in names:
            button = QPushButton(name)
            button.clicked.connect(lambda checked=False, n=name: self._on_saved_network_clicked(n))
            layout.addWidget(button)
