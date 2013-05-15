# -*- coding: utf-8 -*-
#
#    ||          ____  _ __                           
# +------+      / __ )(_) /_______________ _____  ___ 
# | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
# +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#  ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
# Crazyflie client software
#
# Copyright (C) 2011-2012 Bitcraze AB
#

def Singleton(cls):
    """ Class for creating singletons """
    instances = {}
    def getinstance():
        """ Get the singleton instance or create it """
        if cls not in instances:
            instances[cls] = cls()
        return instances[cls]
    return getinstance
