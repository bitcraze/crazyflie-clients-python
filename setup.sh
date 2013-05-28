#!/bin/bash
# Install the Crazyflie PC client and set up permissions so that it can be used
# by the current user immediately
# Caution! This installs the Crazyflie PC client as root to your Python
# site-packages directory. If you wish to install it as a normal user, use the
# instructions on the Wiki at
# http://wiki.bitcraze.se/projects:crazyflie:pc_utils:install
# After installation, the Crazyflie PC client can be started with `cfclient`.
# @author Daniel Lee 2013

# Allow user to use USB radio without root permission
groupadd plugdev
usermod -a -G plugdev $USER
echo SUBSYSTEM==\"usb\", ATTRS{idVendor}==\"1915\", ATTRS{idProduct}==\"7777\", \
MODE=\"0664\", GROUP=\"plugdev\" > /etc/udev/rules.d/99-crazyradio.rules

# Install Crazyflie PC client
python setup.py install

