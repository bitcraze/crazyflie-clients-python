#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2025 Bitcraze AB
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
The Wifi Camera Tab shows stream, settings and controls for the Wifi Camera deck.
"""

import html
import logging
import os
import time
from enum import Enum

from PyQt6 import uic
from PyQt6.QtCore import QPoint, QSize, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMessageBox

import cfclient

from cflib.crazyflie.log import LogConfig

from cfclient.utils.config import Config
from cfclient.utils.input import JoystickReader

from cfclient.ui.tab_toolbox import TabToolbox
from cfclient.ui.widgets.camera_settings import CameraSettingsPanel

__author__ = 'Bitcraze AB'
__all__ = ['WifiCameraTab']

logger = logging.getLogger(__name__)

wifi_camera_tab_class = uic.loadUiType(cfclient.module_path +
                                       "/ui/tabs/wifiCameraTab.ui")[0]

ICON_PATH = os.path.join(cfclient.module_path, 'ui', 'icons')

# Signal strength (dBm) at or above which the signal is considered good/medium
SIGNAL_GOOD_DBM = -60
SIGNAL_MEDIUM_DBM = -75

COLOR_RED = '#F01111'
COLOR_STREAM = '#5CC059'
COLOR_CAMERA = '#CCCCCC'
COLOR_ICON_ENABLED = '#202020'
COLOR_ICON_DISABLED = '#B4B4B4'
TINT_OPACITY = 0.15
RECORDING_DIM_OPACITY = TINT_OPACITY
RECORDING_BLINK_MS = 500
RECORDING_SAVED_BAR_MS = 10000


def _rgba(color, opacity):
    """A color with opacity as a stylesheet rgba() string"""
    c = QColor(color)
    return 'rgba(%d, %d, %d, %d%%)' % (c.red(), c.green(), c.blue(), round(opacity * 100))


def _stream_button_style(fill, border):
    # No text color on purpose, so it follows the theme (white on dark themes)
    return (
        'QPushButton#streamButton:enabled {'
        ' background-color: %s; border: 1px solid %s; border-radius: 2px; padding: 4px 10px; }'
        % (fill, border))


STYLE_STREAM_BUTTON = _stream_button_style(_rgba(COLOR_STREAM, TINT_OPACITY), COLOR_STREAM)
STYLE_STOP_BUTTON = _stream_button_style(_rgba(COLOR_RED, TINT_OPACITY), COLOR_RED)


def _tinted_pixmap(name, color, size, opacity=1.0):
    """Load an icon SVG (drawn with currentColor) and fill it with a single color"""
    pixmap = QIcon(os.path.join(ICON_PATH, name)).pixmap(QSize(size, size))
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    fill = QColor(color)
    fill.setAlphaF(opacity)
    painter.fillRect(pixmap.rect(), fill)
    painter.end()
    return pixmap


def _padded_pixmap(pixmap, top):
    """Add transparent space above a pixmap, to nudge the icon down within its button"""
    padded = QPixmap(pixmap.width(), pixmap.height() + top)
    padded.fill(QColor(0, 0, 0, 0))
    painter = QPainter(padded)
    painter.drawPixmap(0, top, pixmap)
    painter.end()
    return padded


def _tinted_icon(name, color, disabled_color=None, size=16, top_padding=0):
    """Build an icon that Qt switches to disabled_color when its widget is disabled"""
    icon = QIcon()
    for mode, fill in ((QIcon.Mode.Normal, color), (QIcon.Mode.Disabled, disabled_color or color)):
        pixmap = _tinted_pixmap(name, fill, size)
        icon.addPixmap(_padded_pixmap(pixmap, top_padding) if top_padding else pixmap, mode)
    return icon


UP_DOWN_ICON_TOP_PADDING = 3


class CommanderAction(Enum):
    TAKE_OFF = 1
    LAND = 2
    UP = 3
    DOWN = 4
    LEFT = 5
    RIGHT = 6
    FORWARD = 7
    BACK = 8


class WifiCameraTab(TabToolbox, wifi_camera_tab_class):
    _log_data_signal = pyqtSignal(int, object, object)
    _log_error_signal = pyqtSignal(object, str)

    connectionFinishedSignal = pyqtSignal(str)
    disconnectedSignal = pyqtSignal(str)

    LOG_NAME_CAN_FLY = 'sys.canfly'
    LOG_NAME_SUPERVISOR_INFO = 'supervisor.info'

    def __init__(self, helper):
        super(WifiCameraTab, self).__init__(helper, 'Wifi Camera')
        self.setupUi(self)

        self.disconnectedSignal.connect(self.disconnected)
        self.connectionFinishedSignal.connect(self.connected)
        # Incomming signals
        self._helper.cf.connected.add_callback(
            self.connectionFinishedSignal.emit)
        self._helper.cf.disconnected.add_callback(self.disconnectedSignal.emit)

        self._log_data_signal.connect(self._log_data_received)
        self._log_error_signal.connect(self._logging_error)

        self._isConnected = False

        # Command Based Flight Control
        self._can_fly_deprecated = 0
        self.commanderTakeOffButton.clicked.connect(lambda: self._flight_command(CommanderAction.TAKE_OFF))
        self.commanderLandButton.clicked.connect(lambda: self._flight_command(CommanderAction.LAND))
        self.commanderLeftButton.clicked.connect(lambda: self._flight_command(CommanderAction.LEFT))
        self.commanderRightButton.clicked.connect(lambda: self._flight_command(CommanderAction.RIGHT))
        self.commanderForwardButton.clicked.connect(lambda: self._flight_command(CommanderAction.FORWARD))
        self.commanderBackButton.clicked.connect(lambda: self._flight_command(CommanderAction.BACK))
        self.commanderUpButton.clicked.connect(lambda: self._flight_command(CommanderAction.UP))
        self.commanderDownButton.clicked.connect(lambda: self._flight_command(CommanderAction.DOWN))
        self._update_flight_commander(False)

        # Supervisor
        self._supervisor_info_bitfield = 0
        self.armButton.clicked.connect(self.updateArm)
        self._update_supervisor_and_arming(False)

        self._helper.cf.param.all_updated.add_callback(self._all_params_updated)

        self._signal_icons = {
            'good': QPixmap(os.path.join(ICON_PATH, 'good-signal.png')),
            'medium': QPixmap(os.path.join(ICON_PATH, 'medium-signal.png')),
            'bad': QPixmap(os.path.join(ICON_PATH, 'bad-signal.png')),
            'disabled': QPixmap(os.path.join(ICON_PATH, 'disabled-signal.png')),
        }
        self.set_signal_strength(None)

        self._status_icons = {
            True: QIcon(os.path.join(ICON_PATH, 'check-circle-fill.svg')).pixmap(16, 16),
            False: QIcon(os.path.join(ICON_PATH, 'x-circle-fill.svg')).pixmap(16, 16),
        }
        self._camera_pixmaps = {
            True: _tinted_pixmap('camera-video.svg', COLOR_CAMERA, 48),
            False: _tinted_pixmap('camera-video-off.svg', COLOR_CAMERA, 48),
        }
        self.set_camera_status(False, False)
        self.recordingSavedIconLabel.setPixmap(self._status_icons[True])

        self.streamButton.setIcon(_tinted_icon('play-fill.svg', COLOR_STREAM, COLOR_ICON_DISABLED))
        self._record_icon_idle = _tinted_icon('record-fill.svg', COLOR_ICON_ENABLED, COLOR_ICON_DISABLED)
        self._record_icon_on = _tinted_icon('record-fill.svg', COLOR_RED)
        self._record_icon_dim = QIcon(_tinted_pixmap('record-fill.svg', COLOR_RED, 16, RECORDING_DIM_OPACITY))
        self.recordButton.setIcon(self._record_icon_idle)

        self._streaming = False
        self._stop_icon = _tinted_icon('stop-fill.svg', COLOR_RED, COLOR_ICON_DISABLED)
        self._stream_icon = self.streamButton.icon()
        self.streamButton.setStyleSheet(STYLE_STREAM_BUTTON)
        self.streamButton.clicked.connect(self._on_stream_clicked)

        self._recording = False
        self._recording_start = 0.0
        self._recording_timer = QTimer(self)
        self._recording_timer.setInterval(RECORDING_BLINK_MS)
        self._recording_timer.timeout.connect(self._recording_tick)
        self.recordButton.clicked.connect(self._on_record_clicked)

        self._recording_path = None
        self.openFolderButton.clicked.connect(self._open_recording_folder)
        self.recordingSavedCloseButton.clicked.connect(self.recordingSavedBar.hide)
        self._recording_saved_timer = QTimer(self)
        self._recording_saved_timer.setSingleShot(True)
        self._recording_saved_timer.setInterval(RECORDING_SAVED_BAR_MS)
        self._recording_saved_timer.timeout.connect(self.recordingSavedBar.hide)
        self.commanderUpButton.setIcon(
            _tinted_icon('chevron-double-up.svg', COLOR_ICON_ENABLED, COLOR_ICON_DISABLED,
                         top_padding=UP_DOWN_ICON_TOP_PADDING))
        self.commanderDownButton.setIcon(
            _tinted_icon('chevron-double-down.svg', COLOR_ICON_ENABLED, COLOR_ICON_DISABLED,
                         top_padding=UP_DOWN_ICON_TOP_PADDING))

        # The icon sits closer to the top edge than the label does to the bottom, so nudge it down
        icon_size = QSize(16, 16 + UP_DOWN_ICON_TOP_PADDING)
        self.commanderUpButton.setIconSize(icon_size)
        self.commanderDownButton.setIconSize(icon_size)

        self._setup_camera_settings()

        # DEV-MODE-START: remove this block and WifiCameraDevMode.py before committing!
        from cfclient.ui.tabs.WifiCameraDevMode import maybe_show_dev_panel
        maybe_show_dev_panel(self)
        # DEV-MODE-END

    def _on_stream_clicked(self):
        # TODO: start/stop the actual video stream through the camera lib
        self.set_streaming(not self._streaming)

    def set_streaming(self, streaming):
        """Show the streaming state. Recording is only possible while streaming"""
        self._streaming = streaming
        if streaming:
            self.streamButton.setIcon(self._stop_icon)
            self.streamButton.setStyleSheet(STYLE_STOP_BUTTON)
        else:
            self.streamButton.setIcon(self._stream_icon)
            self.streamButton.setStyleSheet(STYLE_STREAM_BUTTON)
            self.set_recording(False)
        self.recordButton.setEnabled(streaming)

    def _on_record_clicked(self):
        # TODO: start/stop the actual recording through the camera lib
        self.set_recording(not self._recording)

    def set_recording(self, recording):
        """Show the recording state: a flashing red dot and an elapsed time"""
        if recording and not self._streaming:
            logger.warning('Cannot record when not streaming')
            return
        self._recording = recording
        if recording:
            self._recording_saved_timer.stop()
            self.recordingSavedBar.hide()
            self._recording_start = time.monotonic()
            self._recording_blink_on = True
            self._recording_tick()
            self._recording_timer.start()
        else:
            self._recording_timer.stop()
            self.recordButton.setIcon(self._record_icon_idle)
            self.recordButton.setText('Record')

    def set_recording_saved(self, path):
        """Show that a finished recording has been downloaded to path"""
        self._recording_path = path
        name = html.escape(os.path.basename(path))
        self.recordingSavedLabel.setText('Recording <b>%s</b> downloaded!' % name)
        self.recordingSavedBar.show()
        self.recordingSavedBar.raise_()
        self._place_recording_saved_bar()
        self._recording_saved_timer.start()

    def _place_recording_saved_bar(self):
        """The bar floats over the video, just below the Record button"""
        bar = self.recordingSavedBar
        if not bar.isVisible():
            return
        box = self.videoStreamBox
        bar.adjustSize()
        x = self.recordButton.mapTo(box, QPoint(0, 0)).x()
        y = self.streamToolbar.mapTo(box, QPoint(0, self.streamToolbar.height())).y() + 4
        # Keep it inside the box also when the window is narrow
        x = max(0, min(x, box.width() - bar.width() - 8))
        bar.move(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_recording_saved_bar()

    def _open_recording_folder(self):
        if self._recording_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(os.path.abspath(self._recording_path))))

    def _recording_tick(self):
        elapsed = int(time.monotonic() - self._recording_start)
        hours, rest = divmod(elapsed, 3600)
        minutes, seconds = divmod(rest, 60)
        if hours:
            elapsed_text = '%d:%02d:%02d' % (hours, minutes, seconds)
        else:
            elapsed_text = '%02d:%02d' % (minutes, seconds)
        self.recordButton.setText('Recording  %s' % elapsed_text)

        self.recordButton.setIcon(self._record_icon_on if self._recording_blink_on else self._record_icon_dim)
        self._recording_blink_on = not self._recording_blink_on

    def set_camera_status(self, deck_connected, pc_connected, ssid=None):
        """Update the status strip and the video placeholder checklist"""
        self.connectionIconLabel.setPixmap(self._status_icons[deck_connected])
        if deck_connected:
            self.connectionStatusLabel.setText('Connected to: %s' % ssid if ssid else 'Connected')
        else:
            self.connectionStatusLabel.setText('Not connected to camera deck')
            self.set_signal_strength(None)

        self.wifiDeckIconLabel.setPixmap(self._status_icons[deck_connected])
        self.wifiPcIconLabel.setPixmap(self._status_icons[pc_connected])

        ready = deck_connected and pc_connected
        self.videoPlaceholderIconLabel.setPixmap(self._camera_pixmaps[ready])
        self.videoPlaceholderTitleLabel.setText('Camera Ready:' if ready else 'Camera Not Ready:')
        self.videoPlaceholderHintLabel.setVisible(ready)

    def set_signal_strength(self, dbm):
        """Update the signal icon and label, None means no signal (not connected)"""
        if dbm is None:
            self.signalIconLabel.setPixmap(self._signal_icons['disabled'])
            self.signalStrengthLabel.setText('Signal Strength: -- dBm')
            return

        if dbm >= SIGNAL_GOOD_DBM:
            quality = 'good'
        elif dbm >= SIGNAL_MEDIUM_DBM:
            quality = 'medium'
        else:
            quality = 'bad'
        self.signalIconLabel.setPixmap(self._signal_icons[quality])
        self.signalStrengthLabel.setText('Signal Strength: %d dBm' % dbm)

    def _setup_camera_settings(self):
        panel = CameraSettingsPanel()
        panel.settingChanged.connect(self._apply_camera_setting)
        self.cameraSettingsLayout.addWidget(panel)

    def _apply_camera_setting(self, name, value):
        # TODO: send the setting to the camera through the lib
        logger.info('Camera setting [%s] changed to [%s]', name, value)

    def _flight_command(self, action):
        current_z = self._helper.pose_logger.position[2]
        move_dist = 0.5
        move_vel = 0.5

        if action == CommanderAction.TAKE_OFF:
            self._helper.cf.param.set_value('commander.enHighLevel', '1')
            z_target = current_z + move_dist
            self._helper.cf.high_level_commander.takeoff(z_target, move_dist / move_vel)
        elif action == CommanderAction.LAND:
            self._helper.cf.high_level_commander.land(0, current_z / move_vel)
        elif action == CommanderAction.LEFT:
            self._helper.cf.high_level_commander.go_to(0, move_dist, 0, 0, move_dist / move_vel, relative=True)
        elif action == CommanderAction.RIGHT:
            self._helper.cf.high_level_commander.go_to(0, -move_dist, 0, 0, move_dist / move_vel, relative=True)
        elif action == CommanderAction.FORWARD:
            self._helper.cf.high_level_commander.go_to(move_dist, 0, 0, 0, move_dist / move_vel, relative=True)
        elif action == CommanderAction.BACK:
            self._helper.cf.high_level_commander.go_to(-move_dist, 0, 0, 0, move_dist / move_vel, relative=True)
        elif action == CommanderAction.UP:
            self._helper.cf.high_level_commander.go_to(0, 0, move_dist, 0, move_dist / move_vel, relative=True)
        elif action == CommanderAction.DOWN:
            self._helper.cf.high_level_commander.go_to(0, 0, -move_dist, 0, move_dist / move_vel, relative=True)

    def _logging_error(self, log_conf, msg):
        QMessageBox.about(self, "Log error",
                          "Error when starting log config [%s]: %s" % (
                              log_conf.name, msg))

    def _log_data_received(self, timestamp, data, logconf):
        if self.isVisible() and self._isConnected:
            if data[self.LOG_NAME_CAN_FLY] != self._can_fly_deprecated:
                self._can_fly_deprecated = data[self.LOG_NAME_CAN_FLY]
                self._update_flight_commander(True)

            if self.LOG_NAME_SUPERVISOR_INFO in data:
                self._supervisor_info_bitfield = data[self.LOG_NAME_SUPERVISOR_INFO]

            self._update_supervisor_and_arming(True)

    def _update_supervisor_and_arming(self, connected):
        if not connected:
            self.armButton.setStyleSheet("")
            self.armButton.setText("Arm")
            self.armButton.setEnabled(False)
            return

        if self._is_locked():
            self.armButton.setText("")
            self.armButton.setEnabled(False)
            self.armButton.setStyleSheet("")
            return

        if self._is_crashed():
            self.armButton.setText("Recover")
            if self._is_tumbled():
                self.armButton.setEnabled(False)
                self.armButton.setStyleSheet("")
            else:
                self.armButton.setEnabled(True)
                self.armButton.setStyleSheet("background-color: %s" % COLOR_RED)
            return

        if self._is_flying():
            self.armButton.setEnabled(True)
            self.armButton.setText("Emergency stop")
            self.armButton.setStyleSheet("background-color: %s" % COLOR_RED)
            return

        if self._is_armed():
            self.armButton.setStyleSheet("background-color: %s" % COLOR_RED)
            if self._auto_arming():
                self.armButton.setEnabled(False)
                self.armButton.setText("Auto armed")
            else:
                self.armButton.setEnabled(True)
                self.armButton.setText("Disarm")
        else:
            self.armButton.setText("Arm")
            if self._can_arm():
                self.armButton.setEnabled(True)
                self.armButton.setStyleSheet("background-color: lightgreen")
            else:
                self.armButton.setStyleSheet("")
                self.armButton.setEnabled(False)

    def _update_flight_commander(self, connected):
        self.commanderBox.setToolTip(str())
        if not connected:
            self.commanderBox.setEnabled(False)
            return

        if self._can_fly_deprecated == 0:
            self.commanderBox.setEnabled(False)
            self.commanderBox.setToolTip('The Crazyflie reports that flight is not possible')
            return

        # We cannot know if we have a positioning deck until we get params
        if not self._helper.cf.param.is_updated:
            self.commanderBox.setEnabled(False)
            return

        #                  flowV1    flowV2     LightHouse       LPS
        position_decks = ['bcFlow', 'bcFlow2', 'bcLighthouse4', 'bcLoco', 'bcDWM1000']
        for deck in position_decks:
            if int(self._helper.cf.param.values['deck'][deck]) == 1:
                self.commanderBox.setEnabled(True)
                break
        else:
            self.commanderBox.setToolTip('You need a positioning deck to use Command Based Flight')
            self.commanderBox.setEnabled(False)
            return

        # To prevent conflicting commands from the controller and the flight panel
        if JoystickReader().available_devices():
            self.commanderBox.setToolTip(
                'Cannot use both a controller and Command Based Flight'
            )
            self.commanderBox.setEnabled(False)
            return

    def connected(self, linkURI):
        self._isConnected = True
        lg = LogConfig("WifiCamera", Config().get("ui_update_period"))
        lg.add_variable(self.LOG_NAME_CAN_FLY)

        # Add supervisor info if it exists to keep backwards compatibility
        if self._helper.cf.log.toc.get_element_by_complete_name(self.LOG_NAME_SUPERVISOR_INFO):
            lg.add_variable(self.LOG_NAME_SUPERVISOR_INFO)

        try:
            self._helper.cf.log.add_config(lg)
            lg.data_received_cb.add_callback(self._log_data_signal.emit)
            lg.error_cb.add_callback(self._log_error_signal.emit)
            lg.start()
        except KeyError as e:
            logger.warning(str(e))
        except AttributeError as e:
            logger.warning(str(e))

    def disconnected(self, linkURI):
        self._isConnected = False

        self._update_flight_commander(False)

        self._supervisor_info_bitfield = 0
        self._update_supervisor_and_arming(False)

    def _can_arm(self):
        return bool(self._supervisor_info_bitfield & 0x0001)

    def _is_armed(self):
        return bool(self._supervisor_info_bitfield & 0x0002)

    def _auto_arming(self):
        return bool(self._supervisor_info_bitfield & 0x0004)

    def _can_fly(self):
        return bool(self._supervisor_info_bitfield & 0x0008)

    def _is_flying(self):
        return bool(self._supervisor_info_bitfield & 0x0010)

    def _is_tumbled(self):
        return bool(self._supervisor_info_bitfield & 0x0020)

    def _is_locked(self):
        return bool(self._supervisor_info_bitfield & 0x0040)

    def _is_crashed(self):
        return bool(self._supervisor_info_bitfield & 0x0080)

    def updateArm(self):
        if self._is_flying():
            self._helper.cf.supervisor.send_emergency_stop()
        elif self._is_crashed():
            self._helper.cf.supervisor.send_crash_recovery_request()
        elif self._is_armed():
            self._helper.cf.supervisor.send_arming_request(False)
        elif self._can_arm():
            self.armButton.setStyleSheet("background-color: orange")
            self._helper.cf.supervisor.send_arming_request(True)

    def _all_params_updated(self):
        self._update_flight_commander(True)
        self._update_supervisor_and_arming(True)
