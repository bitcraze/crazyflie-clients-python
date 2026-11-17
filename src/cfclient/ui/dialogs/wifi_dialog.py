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
import os

from PyQt6 import QtWidgets, uic
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QPushButton

import cfclient
from cfclient.ui.widgets.segmented_control import SegmentedControl
from cfclient.utils.wifi_mode import WifiMode

__author__ = 'Bitcraze AB'
__all__ = ['WifiCameraDialog']

logger = logging.getLogger(__name__)

ICON_PATH = os.path.join(cfclient.module_path, 'ui', 'icons')
STATUS_ICON_SIZE = 16

# The ways the camera deck can be connected, in the order they are shown. The second
# description line is shown in bold, as the thing the user has to take care of.
MODES = [WifiMode.JOIN, WifiMode.CREATE, WifiMode.BOTH]
MODE_NAMES = ['Join a network\n(Recommended)', 'Create a network', 'Both']
MODE_DESCRIPTIONS = [
    ('The Wifi Camera deck joins an existing Wifi network, such as a router.',
     'This computer must be on the same network.'),
    ('The Wifi Camera deck creates its own Wifi network, useful where there is no router.',
     'This computer must join the deck\'s network, and loses its other Wifi connection.'),
    ('The Wifi Camera deck joins an existing network and also creates its own.',
     'Not tested on the camera deck yet.'),
]

# TODO: the channels allowed depend on the region, get them from the camera lib
CHANNELS = list(range(1, 14))
DEFAULT_CHANNEL = 6
PASSWORD_MIN_LENGTH = 8

wifi_camera_dialog_class = uic.loadUiType(cfclient.module_path +
                                          "/ui/dialogs/wifi_dialog.ui")[0]


class WifiCameraDialog(QtWidgets.QWidget, wifi_camera_dialog_class):
    """Dialog for connecting to and controlling WiFi cameras"""

    def __init__(self, helper, *args):
        super(WifiCameraDialog, self).__init__(*args)
        self.setupUi(self)

        self._helper = helper

        # Text uses the client's default font size, only the key labels are bold
        for label in (self.modeHeadingLabel, self.statusLabel):
            font = label.font()
            font.setBold(True)
            label.setFont(font)
        self.statusIconLabel.setFixedSize(STATUS_ICON_SIZE, STATUS_ICON_SIZE)

        self._mode_selector = SegmentedControl(MODE_NAMES)
        self.modeSelectorLayout.addWidget(self._mode_selector)
        self._mode_selector.currentIndexChanged.connect(self._on_mode_changed)

        for channel in CHANNELS:
            self.createChannelCombo.addItem(str(channel), channel)
        self.createChannelCombo.setCurrentIndex(CHANNELS.index(DEFAULT_CHANNEL))

        self.scanButton.clicked.connect(self._on_scan_clicked)
        self.connectButton.clicked.connect(self._on_connect_clicked)
        self.networkNameEdit.textChanged.connect(self._update_connect_button)

        self.createButton.clicked.connect(self._on_create_clicked)
        self.createNameEdit.textChanged.connect(self._update_create_button)
        self.createPasswordEdit.textChanged.connect(self._update_create_button)
        self.createSecurityCombo.currentIndexChanged.connect(self._update_create_button)
        self.createNameEdit.textChanged.connect(self._update_create_instruction)

        self._update_create_button()
        self._width_fixed = False
        self._on_mode_changed(self._mode_selector.current_index())

        self.set_status('Not Connected')

    def showEvent(self, event):
        super().showEvent(event)
        if not self._width_fixed:
            # Measured when first shown, as the widths are only right after the style and fonts are applied
            self._width_fixed = True
            self._fix_width_across_modes()

    def _fix_width_across_modes(self):
        """Make the dialog as wide as its widest mode, so it doesn't change width when switching"""
        current = self._mode_selector.current_index()
        width = 0
        for mode in range(len(MODE_NAMES)):
            self._on_mode_changed(mode)
            self.layout().invalidate()
            self.layout().activate()
            width = max(width, self.sizeHint().width())
        self.setMinimumWidth(width)
        self._on_mode_changed(current)
        self.resize(self.sizeHint())

    def _on_mode_changed(self, mode):
        # TODO: apply the mode through the camera lib
        logger.info('Connection mode [%s]', MODE_NAMES[mode].replace('\n', ' '))
        description, emphasis = MODE_DESCRIPTIONS[mode]
        self.modeDescriptionLabel.setText('<p>%s</p><p><b>%s</b></p>' % (description, emphasis))
        wifi_mode = MODES[mode]
        self.joinPanel.setVisible(wifi_mode in (WifiMode.JOIN, WifiMode.BOTH))
        self.createPanel.setVisible(wifi_mode in (WifiMode.CREATE, WifiMode.BOTH))
        self.createInstructionLabel.setVisible(wifi_mode != WifiMode.BOTH)
        self._update_create_instruction()
        # The layout is updated lazily, so make it current before resizing to its size
        self.layout().invalidate()
        self.layout().activate()
        self.adjustSize()

    def _on_create_clicked(self):
        # TODO: create the network through the camera lib
        logger.info('Create network [%s] on channel [%s]', self.createNameEdit.text(),
                    self.createChannelCombo.currentData())

    def _update_create_button(self):
        is_open = self.createSecurityCombo.currentIndex() == 1
        self.createPasswordEdit.setEnabled(not is_open)
        self.createPasswordLabel.setEnabled(not is_open)
        password_ok = is_open or len(self.createPasswordEdit.text()) >= PASSWORD_MIN_LENGTH
        self.createButton.setEnabled(bool(self.createNameEdit.text()) and password_ok)

    def _update_create_instruction(self):
        name = self.createNameEdit.text() or 'the new network'
        self.createInstructionLabel.setText(
            'After the network is created, connect this computer to <b>%s</b> in the '
            'WiFi settings of your operating system.' % name)

    def _on_scan_clicked(self):
        # TODO: scan for networks through the camera lib and call set_scan_results()
        logger.info('Scan for networks clicked')

    def _on_connect_clicked(self):
        # TODO: connect to the network through the camera lib
        logger.info('Connect clicked for network [%s]', self.networkNameEdit.text())

    def _on_scan_result_clicked(self, name):
        self.networkNameEdit.setText(name)
        self.passwordEdit.setFocus()

    def _update_connect_button(self):
        self.connectButton.setEnabled(bool(self.networkNameEdit.text()))

    def set_status(self, text, connected=False):
        self.statusLabel.setText(text)
        icon = 'check-circle-fill.svg' if connected else 'x-circle-fill.svg'
        self.statusIconLabel.setPixmap(
            QIcon(os.path.join(ICON_PATH, icon)).pixmap(STATUS_ICON_SIZE, STATUS_ICON_SIZE))

    def set_scan_results(self, names):
        """Show the networks found by a scan"""
        self._fill_layout(self.scanResultsLayout, names)

    def _fill_layout(self, layout, names):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        for name in names:
            button = QPushButton(name)
            button.clicked.connect(lambda checked=False, n=name: self._on_scan_result_clicked(n))
            layout.addWidget(button)
