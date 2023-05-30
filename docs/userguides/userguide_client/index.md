---
title: Userguide cfclient GUI
page_id: userguide_client
sort_order: 1
---

This page is intended to give an overview on how to use the Crazyflie
client, not for installing it. For install instructions go
[here](https://github.com/bitcraze/crazyflie-clients-python/blob/develop/README.md).

The Crazyflie client is used for controlling the Crazyflie, flashing
firmware, setting parameters and logging data. The main UI is built up
of a number of [tabs](index.md#tabs-and-toolboxes), where each tab is used for a specific
functionality.

This page uses the terms
[roll/pitch/yaw](http://en.wikipedia.org/wiki/Flight_dynamics_(fixed_wing_aircraft))
extensively. For that to make any sense for a quadcopter we need to know
where the front is, so you will need to know [Crazyflie's coordinate system](https://www.bitcraze.io/documentation/system/platform/cf2-coordinate-system/)

---

## How to get flying with a controller

-   Start up the application
-   Insert the joystick and Crazyradio (PA)
-   Before you connect to the Crazyflie make sure that the joystick is
    working as expected and that the **thrust is zero**. The joystick
    values should be visible in the flight data box under target.
-   Press *Scan*
-   Wait for the scanning to complete
-   In the drop-down menu to the left of the Connect button select the
    Crazyflie you want to connect to. Connect to the URI e.g.
    radio://0/80/250k.
-   The client will now connect to the Crazyflie and handshake
-   When the handshake is done you can start flying the Crazyflie.
    Remember the most tricky part is the thrust so start out easy\...

For more info on LED indicators etc. have a look at the [Crazyflie 2.X](https://www.bitcraze.io/documentation/tutorials/getting-started-with-crazyflie-2-x/#understanding-leds) user guide.

---

## Main UI

![CF client main](/docs/images/cf_client_1.png)

1.  The window title will show the connection status
2.  Connect/disconnect, scan and the drop-down connection list as well
    as Address and auto reconnect.
       * *Scan:* Will scan for availible Crazyflies within the chosen address.
       * *Connect:* Will connect to the selected URI in the connection list
       * *Disconnect:* Will disconnect the current Crazyflie
       * *Address:* The address to scan for. If you didn't change this [in the configuration]( #firmware-configuration), then leave the default of 0xE7E7E7E7E7
3. Battery and link quality (from 0% to 100%)
4. Tabs with specific functionality (see below for details)
5. The content for the active tab
6. Toolboxes can be docked to the edges, making their content visible all the time.
7. The selected and used input interface
8. Emergency stop button. The motors will stop when clicked.

### Tabs and toolboxes

The main interface is built up of different tabs that can be shown/hidden from the *View-\>Tabs* menu. The tabs can
also be used as toolboxes, that is small windows that can be docked to the sides of the main window. This makes it possible
to display multiple windows at the same time, the console log can for instance be visible as a toolbox at the same time
as the parameter tab is open to set a value. To open a toolbox, use the *View-\>Toolboxes* menu, if the toolbox is
already open as a tab, the tab will be removed and it will be opened as a toolbox instead.

The following tabs/toolboxes are currently available:

{% sub_page_menu %}
---

## Functionality

Below are a few guides on how to accomplish specific tasks with the
client.

### Firmware upgrade

For updating the Crazyflie firmware you can keep being connected to the crazyflie. This will open up a separate dialog
that will guide you through the process.

Please note that you need to use a Crazyradio dongle to connect to the Crazyflie when doing firmware upgrades.
Upgrading using USB is **not** possible.

#### Deck firmware

Some decks have a CPUs or other chips that runs firmware that needs to be updated from time to time as well. The Crazyflie
firmware verifies that it is compatible with the deck firmware during start up. If the firmware in a deck that is
installed needs to be upgraded this will be logged in the console log. Deck firmware is upgraded as a part of the
Crazyflie firmware upgrade process, just make sure the deck is mounted when you run the upgrade.


![CFclient bootloading](/docs/images/firmware-upgrade.png)

To update the firmware in the Crazyflie 2.X do the following:

-   Make sure to have any decks you will be using attached during the update, since some of
the decks contain their own firmware which will also be updated during the firmware update. Also make sure there is a battery attached.
-   Go to the menu *Connect-\>Bootloader*
-   Connect to the crazyflie in this dialog, if it is not already connected in the flighttab.
-   Chose what to flash
    - Use the "From release" tab to automatically use an [official release](https://github.com/bitcraze/crazyflie-release/releases). Make sure to select the right platform (cf2 is the Crazyflie 2.X)
    - Use the "From file" tab if you have some other release file you want to flash.
-   Click \"Program\" and wait for both the STM, NRF and decks to be flashed. Note: the Crazyflie may restart multiple times during this process.
-   Your crazyflie will automatically restart a couple of times.
-   Do not touch or restart your crazyflie untill all flashing is done and you see \"status: idle\" at the bottom.
- To check the firmware version, under the *View* menu, open up *Tabs-\>Console* tab and look at the output when connecting to the
Crazyflie 2.X.

If you accidently restarted your crazyflie during flashing or anything else happend which caused your crazyflie to not start up properly, follow [the instructions for recovery mode](/docs/userguides/recovery-mode.md).

### Firmware configuration

It is possible to set another channel to communicate with the Crazyflie 2.X. It can be wise to do this if there exist other wireless
networks that can interfere, especially WiFi. It is also possible to
permanently store the trim values for pitch and roll.

It is currently possible to change the following parameters which are
stored in a none volatile memory:

-   **Pitch trim** Can be programmed permanently with the trim values
    found to work good in the flight tab.
-   **Roll trim** Can be programmed permanently with the trim values
    found to work good in the flight tab.
-   **Radio channel** Can be set to anything between 0 and 125,
    correspond to a frequency from 2400MHz to 2525MHz. In most countries
    channel 0 to 80 is OK to use but this should be checked with you
    local regulations. If using 2M datarate, the copter channels should
    be 2 apart (2MHz).
-   **Radio bandwidth** This can set the radio bandwidth to 250k, 1M or
    2M. A lower bandwidth has longer range but has higher chance of
    collision. When used inside sometimes it is better to use 1M or 2M
    as it decreases the risk of collision with WiFi.
-   **Radio address** (advanced) will set the shock burst address used
    for communicating. Note that if you change this then you will have
    to set the address correctly in the connect dialog.

The procedure is described below and the parameters can be changed again
any time the same way.

First connect to the Crazyflie 2.X with the normal connect button. Then open "Connect->Configure 2.X" to reach the configure 2.X dialog

![CF2 config](/docs/images/cfclient_cf2_config.png){:width="500"}

Once the settings has been made press the write button to save them permanently in the Crazyflie 2.X EEPROM.  Then restart the Crazyflie and connect to the new address.

### Logging

The Crazyflie logging framework allows to log the state of Crazyflie
variables in real-time. This subsystem is used by the client to show
information like pose or battery level.

The list of log variable can be seen in the \"log TOC\" tab in the
client.

Variables are logged in block: one log block is a list of variable that
are logged at the same time. You can setup custom log blocks that can be
plotted in the plotter and saved to file in the log block tab.

To setup a new log block click on the menu \"settings/logging
configuration\", You then see the following toolbox:

![cfclient logging configuration](/docs/images/client_log-configuration_anotated.png){:align-center}

1.  List of log variable in the Crazyflie
2.  Log variables in the current log block
3.  Add the selected Crazyflie log variable in the log block
4.  Remove the selected log block variable from the log block
5.  Period at which the variables are sampled and the block is send by
    the Crazyflie to the client. The minimum possible period is 10ms
    (100Hz) and it can be set by step of 10ms up to 2550ms.
6.  Bytes used by the variables in the log block.
7.  File-tree structure where you can sort the log-blocks into categories.
8.  Create/delete a category or a log-configuration. This can also
    be done by right-clicking anywhere in the category-tree.
9.  Save log block configuration

### Flight settings

By using the settings on the [Flight control tab](./flightcontrol_tab.md) you can set
things such as the max roll/pitch and thrust.

### Input devices

In order to control the Crazyflie you are connected to you will need
some input-device. Normally this would be a gamepad, but any
input-device with at least 4 analog axis will do. Here\'s
[a list](/docs/userguides/inputdevices.md) of some input-devices
that are used.

In order to make sense of the input from the device a mapping has to be
supplied. This mapping will convert raw axis values on the input-device
to useful values like roll/pitch/yaw/thrust. There\'s a few default
mappings shipped with the client, but it\'s easy to create your own.

### Creating new mappings

The software comes bundled with mappings for Xbox and PS3/4 controllers,
but if you have another input-device then it\'s quick to create your own
configuration. Go to the menu *Input device -\> Configure device
mapping*.

![cfclient configure device](/docs/images/cfclient_devconfig_select.png){:align-center
width="700"}

Select the device you would like to configure and press *Configure*.

![cfclient configure device axis](/docs/images/cfclient_devconfig_axis.png){:align-center
width="700"}

For each functionality that can be mapped there\'s a *Detect* button, by
pressing it the following dialog will appear.

![cfclient configure device detect](/docs/images/cfclient_devconfig_dialog.png){:align-center
width="300"}

Follow the instructions to detect the axis or button that you would like
to map to the functionality. If you would like to map the functionality
to two axis (like right/left shoulder-button) then select *Combined axis
detection* and follow the instructions.

Go though all the functionality you would like to map by pressing the
*Detect* button for each. To be able to save the mapping you will at
least have to map roll, pitch, yaw and thrust.

![cfclient configure device feedback](/docs/images/cfclient_devconfig_feedback.png){:align-center
width="700"}

Once you have mapped functionality you will be able to see the feedback
directly in the configuration dialog (when you\'re not detecting a
button). Make sure to check that the response is what you intended. When
you are finished with the mapping then enter the map name and press
save.

If you would like to start from a previous configuration and change it
(either to update or to create a new one) then select the appropriate
mapping in the drop-down and press *Load*. Once you have made the
changes you would like to do then either press *Save* without changing
the name to update the mapping or enter a new name and press *Save* to
create a new one.

### Selecting device

The current input device and mapping can be selected from the *Input
device* menu.

The *Input device* menu contains a number of different \"modes\" that
can be used for controlling a Crazyflie. Currently there\'s thee to
choose from. The alternatives will only be enabled if there\'s enough
input devices connected to use them.

-   *Normal:* Just like it says this is the normal mode using only one
    controller to control a Crazyflie
-   *Teacher (RP):* This mode requires two input-devices, where one will
    be configured for roll and pitch and the other one for the rest of
    the functionality. By using the *Mux switch* functionality (mapped
    in the configuration) the second controller can take over roll and
    pitch as well
-   *Teacher (RPYT):* This mode requires two input-devices, where one
    will be configured for roll, pitch yaw and thrust, and the other one
    for the rest of the functionality. By using the *Mux switch*
    functionality (mapped in the configuration) the second controller
    can take over roll, pitch, yaw and thrust as well

For normal usage just enter the *Normal* menu, select the device you
would like to use and the correct mapping. As a device is selected the
list of mappings are enabled.

![cfclient devices normal](/docs/images/cfclient_input_normal.png){:align-center
width="700"}

If more than one input device is connected then it\'s possible to switch
to one of the teacher modes.

![cfclient devices mux select](/docs/images/cfclient_input_mux_select.png){:align-center
width="700"}

First select the device that should be used for the teacher and then
it\'s mapping.

![cfclient input teacher](/docs/images/cfclient_input_teacher.png){:align-center
width="700"}

Then select the device that should be used for the student and then
it\'s mapping.

![cfclient input student](/docs/images/cfclient_input_student.png){:align-center
width="700"}

Once this is done you will be able to see the open devices and
configurations at the bottom of the user interface.

![cfclient input mux configured](/docs/images/cfclient_input_mux_configured.png){:align-center
width="700"}



---

## ZMQ backends

The UI is normally used to get/set parameters, view logged data and send
control commands to the Crazyflie. Aside from this there\'s also the
possibility to connect via ZMQ to the client and control several things:

-   [Parameters](/docs/functional-areas/cfclient_zmq.md#parameters):
    Get/set parameters by name
-   [LED-ring memory](/docs/functional-areas/cfclient_zmq.md#led-ring):
    Write LED ring memory
-   [Input-device](/docs/functional-areas/cfclient_zmq.md#input-device):
    Act as an input device

The benefit of using this approach instead of the stand-alone ZMQ
server is that you will not have to
take care of everything, just the parts you are interested in for the
moment.
