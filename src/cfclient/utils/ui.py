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


__author__ = 'Bitcraze AB'
__all__ = ['UiUtils']


class UiUtils:

    COLOR_GREEN = '#7cdb37'
    COLOR_BLUE = '#3399ff'
    COLOR_RED = '#cc0404'

    @staticmethod
    def progressbar_stylesheet(color):
        return """
            QProgressBar {
                border: 1px solid gray;
                border-radius: 2px;
                background-color: transparent;
                text-align: center;
            }

            QProgressBar::chunk {
                border-radius: 2px;
                background-color: """ + color + """;
            }
        """
