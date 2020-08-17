# -*- coding: utf-8 -*-
#
#  ,---------,       ____  _ __
#  |  ,-^-,  |      / __ )(_) /_______________ _____  ___
#  | (  O  ) |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  | / ,--´  |    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#     +------`   /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2020 Bitcraze AB
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
from PyQt5.QtGui import QFont

import cfclient

__author__ = 'Bitcraze AB'
__all__ = ['UiUtils']

ICON_PATH = os.path.join(cfclient.module_path, 'ui', 'icons')


class UiUtils:

    COLOR_GREEN = '#7cdb37'
    COLOR_BLUE = '#3399ff'
    COLOR_RED = '#cc0404'
    COLOR_NAVY_BLUE = '#23335D'
    COLOR_NAVY_LIGHT_BLUE = '#3c4869'
    COLOR_LIGHT_GRAY = '#C8C8C8'
    COLOR_LIGHT_GRAY2 = '#A3A3A3'
    COLOR_HACKER_BLACK = '#0A0B0B'
    COLOR_HACKER_GREEN = '#00FF2F'

    FONT = QFont('Palantino')

    THEMES = ['Default', 'Navy blue', 'Hacker']

    # Note: progress bar styling is required for all themes to make the bars
    # wider on OSX (default is very thin) and display the text in the bar.
    # In general terms, when styling something, do check on all OSes, it
    # rarely looks the same.

    _THEME_DEFAULT = """
            QProgressBar {
                border: 1px solid gray;
                border-radius: 2px;
                text-align: center;
            }

            QProgressBar::chunk {
                border-radius: 2px;
                background-color: """ + COLOR_BLUE + """;
            }
    """

    _THEME_HACKER = """
            QApplication {
                font: Palantino;
            }

            QProgressBar {
                border: 1px solid gray;
                border-radius: 2px;
                background-color: white;
                text-align: center;
            }

            QProgressBar::chunk {
                border-radius: 2px;
                background-color: """ + COLOR_GREEN + """;
            }

            QWidget {
                background-color: """ + COLOR_HACKER_BLACK + """;
                color: white;
            }

            QPushButton {
                background-color: """ + COLOR_HACKER_BLACK + """;
                color: """ + COLOR_HACKER_GREEN + """;
                border: 1px solid gray;
            }

            QPushButton:hover {
                background-color: """ + COLOR_LIGHT_GRAY + """;
            }

            QComboBox, QAbstractSpinBox, QAbstractSpinBox::Dropdown, QSpinBox {
                background-color: white;
                color: """ + COLOR_HACKER_BLACK + """;
            }

            QComboBox:disabled,
            QAbstractSpinBox:disabled,
            QSpinBox:disabled,
            QAbstractButton:disabled {
                color: gray;
            }

            QLineEdit {
                border-style: outset;
                border-width: 2px;
                border-radius: 10px;
                border-color: white;
                background-color: white;
                color: """ + COLOR_HACKER_BLACK + """;
                margin: 3px;
                border-radius: 2px;
            }

            QMenu::item:selected {
                background-color: """ + COLOR_LIGHT_GRAY + """;
            }

            QTabWidget {
                border: 3px solid white;
            }

            QCheckBox::indicator {
                border: 1px solid white;
                background: """ + COLOR_HACKER_BLACK + """;
            }

            QCheckBox::indicator:checked {
                image: url(""" + ICON_PATH + '/checkmark_white.png' + """);
            }

            QComboBox {
                selection-background-color: white;
                selection-color: """ + COLOR_HACKER_GREEN + """;
                color: """ + COLOR_HACKER_GREEN + """;
                background-color: """ + COLOR_HACKER_BLACK + """;
                border: 1px solid white;
            }

            QComboBox, QAbstractItemView {
                color: """ + COLOR_HACKER_GREEN + """;
                background-color: """ + COLOR_HACKER_BLACK + """;
            }

            .QSlider {
                min-width: 100px;
                max-width: 100px;
            }

            .QSlider::groove:vertical {
                border: 1px solid white;
                width: 10px;
            }

            .QSlider::handle:vertical {
                background: """ + COLOR_GREEN + """;
                border: 5px solid #B5E61D;
                height: 5px;
                border-radius: 30px;
            }

            QTreeView, QTextEdit {
                border-style: outset;
                border-width: 1px;
                border-color: """ + COLOR_LIGHT_GRAY2 + """;
            }

            QTabBar::tab {
                background-color: """ + COLOR_HACKER_BLACK + """;
            }

            QTabBar::tab:hover {
                background-color: """ + COLOR_LIGHT_GRAY + """;
            }

            QTabBar::tab:selected {
                background-color: """ + COLOR_LIGHT_GRAY2 + """;
            }
        """

    _THEME_NAVY = """
            QProgressBar {
                border: 1px solid gray;
                border-radius: 2px;
                background-color: white;
                text-align: center;
            }

            QProgressBar::chunk {
                border-radius: 2px;
                background-color: """ + COLOR_GREEN + """;
            }

            QWidget {
                background-color: """ + COLOR_NAVY_BLUE + """;
                color: white;
            }

            QPushButton {
                background-color: white;
                color: black;
            }

            QPushButton:hover {
                background-color: """ + COLOR_LIGHT_GRAY + """;
            }

            QComboBox, QAbstractSpinBox, QSpinBox {
                background-color: white;
                color: black;
            }

            QComboBox:disabled,
            QAbstractSpinBox:disabled,
            QSpinBox:disabled,
            QAbstractButton:disabled {
                color: gray;
            }

            QLineEdit, QAbstractScrollArea {
                background-color: white;
                color: black;
                border: 1px solid gray;
                margin: 3px;
                border-radius: 2px;
            }

            QMenu::item:selected {
                background-color: """ + COLOR_LIGHT_GRAY + """;
            }

            QTabWidget {
                border: 3px solid white;
            }

            QCheckBox::indicator {
                border: 1px solid white;
                background-color: """ + COLOR_NAVY_BLUE + """;
            }

            QCheckBox::indicator:checked {
                image: url(""" + ICON_PATH + '/checkmark_white.png' + """);
            }

            .QSlider {
                min-width: 100px;
                max-width: 100px;
            }

            QComboBox {
                selection-background-color: """ + COLOR_NAVY_BLUE + """;
                selection-color: white;
                color: black;
            }

            QComboBox, QAbstractItemView {
                color: black;
                background-color: white;
            }

            .QSlider::groove:vertical {
                border: 1px solid white;
                width: 10px;
            }

            .QSlider::handle:vertical {
                background: """ + COLOR_GREEN + """;
                border: 5px solid #B5E61D;
                height: 5px;
                border-radius: 30px;
            }

            QTabBar::tab {
                background-color: """ + COLOR_NAVY_LIGHT_BLUE + """;
            }

            QTabBar::tab:hover {
                background-color: """ + COLOR_LIGHT_GRAY + """;
            }

            QTabBar::tab:selected {
                background-color: """ + COLOR_LIGHT_GRAY2 + """;
            }

            QHeaderView {
                background-color: """ + COLOR_NAVY_LIGHT_BLUE + """;
                border-color: """ + COLOR_NAVY_LIGHT_BLUE + """;
                border-width: 0px;
                color: white;
            }

        """

    _THEMES = {
        'Default': _THEME_DEFAULT,
        'Navy blue': _THEME_NAVY,
        'Hacker': _THEME_HACKER,
        }

    @staticmethod
    def set_background_color(obj, red, green, blue):
        obj.setStyleSheet('background-color: rgb(%s, %s, %s)' %
                          (red, green, blue))

    @staticmethod
    def select_theme(theme):
        return UiUtils._THEMES[theme]

    @staticmethod
    def progressbar_stylesheet(color):

        return """
            QProgressBar {
                border: 1px solid gray;
                border-radius: 2px;
                text-align: center;
            }

            QProgressBar::chunk {
                border-radius: 2px;
                background-color: """ + color + """;
            }
            """
