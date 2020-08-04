---
title: Input-devices for the Crazyflie client
page_id: inputdevices
---

The Crazyflie graphical control client needs an input-device (joystick)
with a minimum of 4 analogue axes to be able to pilot the Crazyflie. The
Playstation 3 controller is supported out of the box but the application
supports creating new configurations that uses other controllers. This
page details what controllers are supported out of the box, how to
create a new configurations and how to debug problems.

---

## Steps to get the controller working

Here\'s a few steps that you have to go though in order to get the
input-device working. If any of the steps are not working then the
input-device will not be usable for piloting the Crazyflie:

-   The input-device needs to be recognized by the host operating
    system. This means that it should be seen in the operating system
    and be usable in other applications or utilities.
-   When using the Crazyflie graphical control client you need at least
    the correct mappings for roll/pitch/yaw/thrust. This can be checked
    by opening the *Flight Data* tab. If the input-device is found and
    opened then you should see values in the *Target* fields for
    *Roll*,*Pitch*,*Yaw* and *Thrust*. Moving the analogue axis should
    show you output here. Make sure that you get the full span according
    to the settings on the left side of the tab. I.e if the setting for
    *Max roll/pitch* is 20 then you should be able to get from -20 to +
    20 in the target field (and the same for yaw and thrust). Also make
    sure that none of the axis interact (like moving roll will also move
    pitch).
-   If you aren\'t getting any output at all and you are using the
    Playstation 3 controller, then press the \"Playstation\" button in
    the middle on the controller once.
-   If the mappings are not correct in the previous point go to the menu
    *Input-device-\>Configure device mapping*, select the device you
    would like to configure and go though the configuration by clicking
    detect on each of the items in the dialog (everything has to be
    configured). Lastly enter the name of the configuration (without
    file extension) and press save. Now restart the application and try
    again.

**Please note!!** In the 2013.4.1 and previous versions there\'s a bug
where the loading of a previous configuration will not work correctly.
The values are not loaded but the configuration call still be saved.
This results in a configuration file that will not work and an error
will be shown when trying to use it. In order to fix this manually
delete the contents of the user config folder (win:
*C:\\Users\\your\_user\\AppData\\Roaming\\cfclient*, linux:
*\~/.config/cfclient*) and create a new configuration from scratch as
described above.

---

## Input device overview

Below is a list of controllers and the status for different OSs. The
list is far from complete so if you have more info please edit or drop
us an email.

 | **Controller**    |        **Linux USB**       |                                                        **Linux BT**  |                                                                    **Win XP USB**  | **Win XP BT**  |                                                                    **Win7 USB**     |                                                                      **Win7 BT**        |                                                                          **Win8 USB**         |                                                             **Mac OSX USB**  | **Mac OSX BT**|
|--|--|--|--|--|--|--|--|--|--|--|
 | Playstation 3 (or copy)  | Works           |                                                            Works |  Works       |     Works | Works  | Works  | Works,  |  Works     |        Works|
  Xbox 360 (or copy)      |  Works  | N/A                  |                                                             Works    |        N/A                       |                                                                                                                                                Works        |                                                                                N/A            |                                                                   Not tested    |    Not tested|


### Playstation 3 controller

#### Linux using Bluetooth

[How to set up Sixaxis on
Ubuntu](https://help.ubuntu.com/community/Sixaxis) (tested on Ubuntu
13.10)

#### Win7 using USB

There\'s support for this using MotionJoy, **but** the mapping of the
axis is not the same as for Windows XP/Linux and has to be configured.
**TODO** Insert instructions for re-mapping.

[Video on how to get started with
MotionJoy](http://youtu.be/b2lUxNShIDs).

#### Win7 using Bluetooth

Should work using MotionJoy but this needs confirmation.

#### Win8 USB
[Instructions](http://www.wikihow.com/Set-Up-USB-Game-Controllers-on-Windows-8)

#### Mac OSX with Bluetooth

To pair the controller follow the steps outlined
[here](https://gist.github.com/statico/3172711). **TODO**: This
procedure is somewhat shaky. Figure out and add a solid set of steps
here.

**NOTE**: To shut down the controller you need to disconnect the
controller from OSX. This is easiest done if you enable in in System
Preferences -\> Bluetooth enable Show Bluetooth status in menu bar. From
the menu bar item you can easily disconnect it.

---

### Xbox 360 controller

#### Linux using USB

**INFO:** All modern Linux distribution now have a kernel driver for the x-box
gamepad. Thus it is unlikely the *xboxdrv* user-space driver is needed.


If you are having problems getting this to work the userspace driver
`xboxdrv` might be needed. It can be installed (on Ubuntu) by running:

    sudo apt-get install xboxdrv

And then started by running:

    sudo xboxdrv

More info about the `xboxdrv` is available
[here](https://xboxdrv.gitlab.io/).
