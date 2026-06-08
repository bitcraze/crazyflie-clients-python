# -*- coding: utf-8 -*-
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

#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.

import os

import cfclient

ICON_PATH = os.path.join(cfclient.module_path, 'ui', 'icons')

COLOR_GREEN = '#7cdb37'
COLOR_BLUE = '#3399ff'
COLOR_RED = '#cc0404'
COLOR_NAVY_BLUE = '#23335D'
COLOR_NAVY_LIGHT_BLUE = '#3c4869'
COLOR_LIGHT_GRAY = '#C8C8C8'
COLOR_LIGHT_GRAY2 = '#A3A3A3'
COLOR_HACKER_BLACK = '#0A0B0B'
COLOR_HACKER_GREEN = '#00FF2F'

_CHECKMARK_WHITE = ICON_PATH + '/checkmark_white.png'


THEME_DEFAULT = """
QWidget { background-color: #f6f7f9; color: #1c2024; selection-background-color: #3b7dd8; selection-color: #ffffff; }
QMainWindow, QDialog, QDockWidget { background-color: #f6f7f9; }
QMenuBar, QStatusBar { background-color: #ffffff; border-bottom: 1px solid #dde1e6; }
QStatusBar { border-top: 1px solid #dde1e6; border-bottom: 0; color: #9ca3af; }
QMenuBar::item { background: transparent; padding: 5px 10px; }
QMenuBar::item:selected, QMenu::item:selected { background-color: #e8f0fb; color: #1d4f91; }
QMenu { background-color: #ffffff; border: 1px solid #dde1e6; padding: 4px 0; }
QMenu::item { padding: 5px 22px; background-color: transparent; }
QGroupBox { border: 1px solid #dde1e6; border-radius: 5px; margin-top: 14px; background-color: #ffffff; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #5c6370; font-weight: 600; text-transform: uppercase; }
QLabel, QCheckBox, QRadioButton { background-color: transparent; }
QPushButton { min-height: 28px; padding: 4px 11px; border: 1px solid #cfd5dd; border-radius: 4px; background-color: #ffffff; color: #1c2024; }
QPushButton:hover { background-color: #f0f2f5; border-color: #aeb7c2; }
QPushButton:pressed { background-color: #e5e9ef; }
QPushButton:disabled, QComboBox:disabled, QLineEdit:disabled, QAbstractSpinBox:disabled { color: #9ca3af; background-color: #f0f2f5; border-color: #dde1e6; }
QLineEdit, QComboBox, QAbstractSpinBox, QTextEdit, QPlainTextEdit, QTreeView, QTableView, QListView { min-height: 26px; border: 1px solid #cfd5dd; border-radius: 4px; background-color: #ffffff; color: #1c2024; }
QLineEdit, QComboBox, QAbstractSpinBox { padding: 2px 7px; }
QComboBox::drop-down { width: 24px; border-left: 1px solid #dde1e6; border-top-right-radius: 4px; border-bottom-right-radius: 4px; background-color: #fafbfc; }
QComboBox QAbstractItemView { border: 1px solid #cfd5dd; border-radius: 4px; background-color: #ffffff; color: #1c2024; padding: 4px; outline: 0; selection-background-color: #e8f0fb; selection-color: #1d4f91; }
QComboBox QAbstractItemView::item { min-height: 24px; padding: 4px 8px; }
QAbstractSpinBox { padding-right: 24px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { width: 22px; border-left: 1px solid #dde1e6; background-color: #fafbfc; }
QAbstractSpinBox::up-button { border-top-right-radius: 4px; border-bottom: 1px solid #dde1e6; }
QAbstractSpinBox::down-button { border-bottom-right-radius: 4px; }
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover { background-color: #f0f2f5; }
QHeaderView::section { background-color: #fafbfc; border: 0; border-right: 1px solid #dde1e6; border-bottom: 1px solid #dde1e6; padding: 5px 6px; color: #5c6370; }
QTabWidget::pane { border: 0; border-top: 0; background-color: #f6f7f9; }
QTabBar::tab { min-height: 32px; padding: 0 14px; border: 0; border-bottom: 2px solid transparent; background-color: #ffffff; color: #5c6370; }
QTabBar::tab:selected { background-color: #ffffff; color: #3b7dd8; border-bottom: 2px solid #3b7dd8; }
QTabBar::tab:hover:!selected { color: #1c2024; }
QProgressBar { min-height: 18px; border: 0; border-radius: 4px; background-color: #ebedf0; text-align: center; color: #1c2024; }
QProgressBar::chunk { border-radius: 4px; background-color: #3b7dd8; }
#interfaceCombo { min-width: 260px; }
#connectButton, #scanButton, #esButton { min-height: 28px; max-height: 28px; padding: 4px 12px; }
#connectButton { color: #ffffff; background-color: #3b7dd8; border-color: #3b7dd8; font-weight: 600; }
#connectButton:enabled:hover { background-color: #3571c4; border-color: #3571c4; }
#flightModeCombo, #_assist_mode_combo { min-width: 150px; max-width: 150px; }
#targetCalRoll, #targetCalPitch, #maxAngle, #maxYawRate, #maxThrust, #minThrust, #slewEnableLimit, #thrustLoweringSlewRateLimit { min-width: 118px; max-width: 118px; }
#batteryLabel, #linkQualityLabel { color: #5c6370; font-weight: 600; }
#scrollArea { border: 0; background-color: transparent; }
#esButton { color: #ffffff; border-color: #d1242f; background-color: #d1242f; font-weight: 600; }
#esButton:enabled:hover { background-color: #b91c24; border-color: #b91c24; }
#groupBox { border: 0; margin-top: 0; background-color: #f6f7f9; }
#groupBox::title { color: transparent; padding: 0; }
#groupBox_2, #groupBox_3, #commanderBox { border-left: 0; border-right: 0; border-radius: 0; margin-top: 14px; }
#label_14, #label_20, #label_6, #M1label, #M2label, #M3label, #M4label, #_supervisor_label1, #_supervisor_label2 { color: #5c6370; font-weight: 600; }
#inputThrustLabel, #inputPitchLabel, #inputRollLabel, #inputYawLabel, #inputHeightLabel { color: #5c6370; padding-left: 8px; }
#commanderTakeOffButton { color: #2ea44f; background-color: #e6f4ea; border-color: #b8dfc3; font-weight: 600; }
#commanderLandButton { color: #d1242f; background-color: #fce8ea; border-color: #f0c4c7; font-weight: 600; }
#commanderLeftButton, #commanderRightButton, #commanderForwardButton, #commanderBackButton, #commanderUpButton, #commanderDownButton { color: #5c6370; background-color: #ffffff; border-color: #dde1e6; }
QDockWidget::title { background-color: #fafbfc; border-bottom: 1px solid #dde1e6; padding: 5px; }
"""


THEME_NAVY = THEME_DEFAULT + """
QWidget, QMainWindow, QDialog, QMenu, QAbstractItemView, QDockWidget {
    background-color: #eef3f8;
}
QGroupBox, QLineEdit, QComboBox, QAbstractSpinBox, QTextEdit, QPlainTextEdit,
QTreeView, QTableView, QListView, QTabWidget::pane {
    background-color: #ffffff;
    color: #1f2933;
    border-color: #b7c4d8;
}
QComboBox:disabled, QLineEdit:disabled, QAbstractSpinBox:disabled,
QPushButton:disabled {
    background-color: #e3eaf3;
    color: #75849a;
    border-color: #b7c4d8;
}
QComboBox::drop-down, QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    background-color: #edf3f9;
    border-color: #b7c4d8;
}
QComboBox QAbstractItemView { background-color: #ffffff; border-color: #b7c4d8; }
QGroupBox::title, #batteryLabel, #linkQualityLabel { color: #44566d; }
QLabel, QCheckBox, QRadioButton { background-color: transparent; }
QMenuBar, QStatusBar, QTabBar::tab:selected { background-color: #ffffff; color: #1f2933; }
QMenuBar::item:selected, QMenu::item:selected { background-color: #dbe8f6; color: #23335d; }
QTabBar::tab { background-color: #e4ebf4; color: #2f3f55; }
QProgressBar::chunk { background-color: """ + COLOR_NAVY_LIGHT_BLUE + """; }
"""

THEME_HACKER = THEME_DEFAULT + """
QWidget, QMainWindow, QDialog, QMenu, QAbstractItemView, QDockWidget {
    background-color: #101418;
    color: #d7f7dd;
}
QGroupBox, QLineEdit, QComboBox, QAbstractSpinBox, QTextEdit, QPlainTextEdit,
QTreeView, QTableView, QListView, QTabWidget::pane {
    background-color: #151b20;
    color: #d7f7dd;
    border-color: #2c3a36;
}
QComboBox:disabled, QLineEdit:disabled, QAbstractSpinBox:disabled,
QPushButton:disabled {
    background-color: #11171b;
    color: #61756b;
    border-color: #26332f;
}
QComboBox::drop-down, QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    background-color: #101418;
    border-color: #2c3a36;
}
QComboBox QAbstractItemView { background-color: #151b20; color: #d7f7dd; border-color: #2c3a36; }
QGroupBox::title, #batteryLabel, #linkQualityLabel { color: """ + COLOR_HACKER_GREEN + """; }
QMenuBar, QStatusBar, QHeaderView::section, QTabBar::tab {
    background-color: #151b20;
    color: #d7f7dd;
}
QMenuBar::item:selected, QMenu::item:selected { background-color: #20302a; color: """ + COLOR_HACKER_GREEN + """; }
QPushButton { background-color: #192128; color: #d7f7dd; border-color: #2c3a36; }
QPushButton:hover, QTabBar::tab:hover:!selected { background-color: #20302a; }
QTabBar::tab:selected { background-color: #101418; color: """ + COLOR_HACKER_GREEN + """; }
QProgressBar { background-color: #151b20; color: #d7f7dd; border-color: #2c3a36; }
QProgressBar::chunk { background-color: """ + COLOR_HACKER_GREEN + """; }
"""

THEMES = {
    'Default': THEME_DEFAULT,
    'Navy blue': THEME_NAVY,
    'Hacker': THEME_HACKER,
}


def progressbar_stylesheet(color):
    return """
QProgressBar {
    border: 1px solid #c3cad6;
    border-radius: 5px;
    background-color: #ffffff;
    text-align: center;
    color: #1f2933;
}
QProgressBar::chunk {
    border-radius: 4px;
    background-color: """ + color + """;
}
"""
