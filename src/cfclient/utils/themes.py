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
QWidget {
    background-color: #f6f7f9;
    color: #1f2933;
    selection-background-color: #2f80ed;
    selection-color: #ffffff;
}
QMainWindow, QDialog, QMenu, QAbstractItemView, QDockWidget {
    background-color: #f6f7f9;
}
QMenuBar, QStatusBar { background-color: #ffffff; border-bottom: 1px solid #d8dde6; }
QStatusBar { border-top: 1px solid #d8dde6; border-bottom: 0; }
QMenuBar::item { background: transparent; padding: 4px 10px; }
QMenuBar::item:selected, QMenu::item:selected {
    background-color: #e8f1ff;
    color: #153b66;
}
QMenu { border: 1px solid #d8dde6; padding: 4px 0; }
QMenu::item { padding: 5px 22px; }
QGroupBox {
    border: 1px solid #d8dde6;
    border-radius: 6px;
    margin-top: 8px;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #52606d;
}
QLabel, QCheckBox, QRadioButton { background-color: transparent; }
QPushButton {
    min-height: 26px;
    padding: 4px 12px;
    border: 1px solid #b8c2cc;
    border-radius: 5px;
    background-color: #ffffff;
    color: #1f2933;
}
QPushButton:hover {
    background-color: #eef4fb;
    border-color: #8aa7c7;
}
QPushButton:pressed {
    background-color: #dce8f5;
}
QPushButton:disabled, QComboBox:disabled, QLineEdit:disabled,
QAbstractSpinBox:disabled {
    color: #9aa5b1;
    background-color: #eef0f3;
    border-color: #d8dde6;
}
QLineEdit, QComboBox, QAbstractSpinBox, QTextEdit, QPlainTextEdit,
QTreeView, QTableView, QListView {
    min-height: 26px;
    border: 1px solid #c3cad6;
    border-radius: 5px;
    background-color: #ffffff;
    color: #1f2933;
}
QLineEdit, QComboBox, QAbstractSpinBox {
    padding: 2px 6px;
}
QComboBox::drop-down {
    width: 24px; border-left: 1px solid #d8dde6;
    border-top-right-radius: 5px; border-bottom-right-radius: 5px;
    background-color: #f8fafc;
}
QComboBox QAbstractItemView {
    border: 1px solid #c3cad6;
    border-radius: 5px;
    background-color: #ffffff;
    color: #1f2933;
    padding: 4px;
    outline: 0;
    selection-background-color: #e8f1ff;
    selection-color: #153b66;
}
QComboBox QAbstractItemView::item { min-height: 24px; padding: 4px 8px; }
QAbstractSpinBox { padding-right: 24px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    width: 22px; border-left: 1px solid #d8dde6;
    background-color: #f8fafc;
}
QAbstractSpinBox::up-button {
    border-top-right-radius: 5px; border-bottom: 1px solid #d8dde6;
}
QAbstractSpinBox::down-button { border-bottom-right-radius: 5px; }
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover { background-color: #eef4fb; }
QHeaderView::section {
    background-color: #edf1f6;
    border: 0;
    border-right: 1px solid #d8dde6;
    border-bottom: 1px solid #d8dde6;
    padding: 5px 6px;
}
QTabWidget::pane {
    border: 1px solid #d8dde6;
    border-top: 0;
    background-color: #ffffff;
}
QTabBar::tab {
    min-height: 24px;
    padding: 6px 12px;
    border: 1px solid #d8dde6;
    border-bottom: 0;
    background-color: #edf1f6;
    color: #52606d;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    color: #1f2933;
}
QTabBar::tab:hover:!selected {
    background-color: #f8fafc;
}
QProgressBar {
    min-height: 18px;
    border: 1px solid #c3cad6;
    border-radius: 5px;
    background-color: #ffffff;
    text-align: center;
    color: #1f2933;
}
QProgressBar::chunk {
    border-radius: 4px;
    background-color: """ + COLOR_BLUE + """;
}
#interfaceCombo { min-width: 260px; }
#connectButton, #scanButton, #esButton { min-height: 22px; max-height: 22px; padding: 4px 12px; }
#flightModeCombo, #_assist_mode_combo { min-width: 130px; max-width: 130px; }
#targetCalRoll, #targetCalPitch, #maxAngle, #maxYawRate, #maxThrust, #minThrust, #slewEnableLimit, #thrustLoweringSlewRateLimit { min-width: 112px; max-width: 112px; }
#batteryLabel, #linkQualityLabel { color: #52606d; font-weight: 600; }
#connectButton { font-weight: 600; }
#scrollArea { border: 0; background-color: transparent; }
#esButton {
    color: #9f1d1d;
    border-color: #efb1b1;
    background-color: #fff7f7;
}
#esButton:enabled:hover { background-color: #ffecec; border-color: #e07171; }
QDockWidget::title {
    background-color: #edf1f6;
    border-bottom: 1px solid #d8dde6;
    padding: 5px;
}
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
