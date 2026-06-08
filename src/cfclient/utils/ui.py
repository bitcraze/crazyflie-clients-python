# -*- coding: utf-8 -*-
#
#  ,---------,       ____  _ __
#  |  ,-^-,  |      / __ )(_) /_______________ _____  ___
#  | (  O  ) |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  | / ,--´  |    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#     +------`   /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2020-2023 Bitcraze AB
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

from PyQt6.QtGui import QFont

from cfclient.utils import themes

__author__ = 'Bitcraze AB'
__all__ = ['UiUtils']

ICON_PATH = themes.ICON_PATH


class UiUtils:
    COLOR_GREEN = themes.COLOR_GREEN
    COLOR_BLUE = themes.COLOR_BLUE
    COLOR_RED = themes.COLOR_RED
    COLOR_NAVY_BLUE = themes.COLOR_NAVY_BLUE
    COLOR_NAVY_LIGHT_BLUE = themes.COLOR_NAVY_LIGHT_BLUE
    COLOR_LIGHT_GRAY = themes.COLOR_LIGHT_GRAY
    COLOR_LIGHT_GRAY2 = themes.COLOR_LIGHT_GRAY2
    COLOR_HACKER_BLACK = themes.COLOR_HACKER_BLACK
    COLOR_HACKER_GREEN = themes.COLOR_HACKER_GREEN

    FONT = QFont()
    THEMES = list(themes.THEMES.keys())
    _THEMES = themes.THEMES

    @staticmethod
    def set_background_color(obj, red, green, blue):
        obj.setStyleSheet('background-color: rgb(%s, %s, %s)' %
                          (red, green, blue))

    @staticmethod
    def select_theme(theme):
        return UiUtils._THEMES[theme]

    @staticmethod
    def progressbar_stylesheet(color):
        return themes.progressbar_stylesheet(color)
