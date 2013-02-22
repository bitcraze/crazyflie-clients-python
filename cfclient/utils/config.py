#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __                           
#  +------+      / __ )(_) /_______________ _____  ___ 
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2013 Bitcraze AB
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
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
Handle the main configuration file for the Crazyflie control client.
"""

__author__ = 'Bitcraze AB'
__all__ = ['ConfigParams','Config']

import sys, time
import pygame

import json
import struct
import math
from pprint import pprint

def Singleton(cls):
    instances = {}
    def getinstance():
        if cls not in instances:
            instances[cls] = cls()
        return instances[cls]
    return getinstance

class ConfigParams():
    LAST_CONNECT_URI = "last_connect_uri"

    FLIGHT_MODE = "flightmode"
    THRUST_MODE = "thrustmode"
    CONTROLLER_MODE = "controllermode"

    CRAZY_MAX_RP_ANGLE = "crazy_max_rp_angle"
    CRAZY_MAX_YAWRATE = "crazy_max_yawrate"
    CRAZY_MAX_THRUST = "crazy_max_thrust"
    CRAZY_MIN_THRUST = "crazy_min_thrust"
    CRAZY_IMU_TYPE = "crazy_imu_type"
    CRAZY_SLEW_LIMIT = "crazy_slew_limit"
    CRAZY_SLEW_RATE = "crazy_slew_rate"

    CAL_ROLL = "cal_roll"
    CAL_PITCH = "cal_pitch"

    INPUT_SELECT = "selected_input_name"
    OPEN_TABS = "open_tabs"

@Singleton
class Config():

    def __init__( self ):
        self.data = dict()
        self.readFile()

    def setParam(self, key, value):
        self.data[key] = str(value)

    def getParam(self, key):
        return self.data[key]

    def saveFile(self):
        json_data=open('configs/config.json', 'w')
        json_data.write(json.dumps(self.data, indent=2))
        json_data.close()

    def readFile(self):
        try:
            json_data=open('configs/config.json')
            self.data = json.load(json_data)
            json_data.close()        
        except:
            print "No configfile found, it will be created as changes are made.."

    def __del__(self):
        print "Should close file"


