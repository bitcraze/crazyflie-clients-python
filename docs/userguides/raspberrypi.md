---
title: Bitcraze Raspberry Pi SD-card image
page_id: raspberrypi
---




In order to make it easy for users that have a Raspberry Pi to test out
our headless client we prepared an SD-card image that is ready to use
out of the box. The image is based on the
[Raspbian](http://www.raspbian.org/) distribution. The image version
2015.3 is based on Raspbian version 2015-02-16 available on the
[RaspberryPi website](http://www.raspberrypi.org/downloads/).

We haven\'t removed anything from the image, just added our own stuff.
So you can still log in and used the Raspberry Pi as you would with the
Raspbian image, but as an added feature you can also use our stuff.

---

## Download

The SD-card image can be downloaded here (version 2015.3 and onward is
compatible with Raspberrypi 2):

-   Bitcraze Raspbian image 2015.3
    ([direct download](http://files.bitcraze.se/dl/cfpi-2015.3.7z))
    ([mega](https://mega.co.nz/#!uQYSFIDJ!6PwIwxM315B99ejveo_6zlTVWk_oYkMOW0fKQLQ74A0))
-   Bitcraze Raspbian image 0.3
    ([direct download](http://files.bitcraze.se/dl/cfpi-0_3.7z))
-   Bitcraze Raspbian image 0.2
    ([mega](https://mega.co.nz/#!fVoTBIAQ!Akk80haC--oZjklJxCzCaS_nnlg8xVQhUcczPviaawA))
-   Bitcraze Raspbian image 0.1
    ([mega](https://mega.co.nz/#!HJpH2KDJ!bY-EdGtyxIRzOUu6xNVWnid_cco5wS-IQ6ELfc5Y1Q8))

**Note:** Using Torrent is advised, we have
added webseed so it is faster than direct download and guarantee the
file integrity.

---

## Installing in an existing Raspbian sdcard

If you already have a running raspbian system no need to download the
image, connect your raspberrypi and run the following command to install
all packages and dependencies. We are generating the official that way.
You must be logged with the \'pi\' user to launch the command:

    curl https://raw.githubusercontent.com/bitcraze/bitcraze-raspberry-pi/2015.3/bitcraze_raspberrypi.sh | sh

---

## SD-image info

    Size: 4 GB
    User: pi
    Pass: raspberry

(version before 2015.3 had bitcraze/crazyflie as username/password)

---

## What\'s added to the image

There\'s a list of what\'s added:

-   UDEV rules for access to the Crazyradio and NRF bootloader
-   crazyflie-pc-client pre-cloned at latest stable version
-   pyusb
-   UDEV rules to automatically launch the cfheadless client when
    Crazyradio is plugged in
-   Driver for the Xbox 360 wireless controller and automatic start of
    the utilities

---

## Creating the SD-card

First of all you have to write the image to the SD-card. There are good
instructions on how to do this
[here](http://elinux.org/RPi_Easy_SD_Card_Setup#Create_your_own).

---

## How to use the SD-card image

First of all you need to set up what controller and link settings you
are using. This is done by editing the two files in the folder /home/pi
named controller.conf and link.conf. They should only contain one row
each.

To fly first insert the USB controller, then power on the Crazyflie and
lastly insert the Crazyradio. This will start the cfheadless client and
connect to the Crazyflie. In a few seconds you should be ready to fly.

To quit either power off the Crazyflie or pull-out the Crazyradio.

In order to restart flying you have to pull-out the Crazyradio dongle
and insert it again.

---

## Troubleshooting

Try to pull-out and insert the Crazyradio. Then wait up to 10 seconds
before you try to control the Crazyflie.

If you see the LED on the Crazyradio blinking green, then it\'s
connected. If it\'s blinking red it means that it cannot connect to the
Crazyflie.

Check logfile /tmp/cfheadless.log for messages

---

## FAQ

### How do I get the RedOctane Xbox360 controller to work

You will have to edit the `/root/bin/xbox` file to contain the following
to get the RedOctaine xbox360 (1430:f801) controller to work:

    #!/bin/sh
    if test "$ACTION" = "add"
    then
    /usr/bin/xboxdrv --device-by-id 1430:f801 --type xbox360 --axismap X2=X1,Y2=Y1,X1=X2,Y1=Y2 &
    else
    killall -9 xboxdrv
    fi
