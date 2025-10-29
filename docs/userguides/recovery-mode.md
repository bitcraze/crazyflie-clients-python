---
title: Recovery firmware flashing
page_id: recovery-mode
---

> _**Only use this type of firmware flashing if your Crazyflie is not booting up properly. Check [the cfclient userguide](/docs/userguides/userguide_client/index.md) for the official instructions on how to upgrade your firmware.**_

For updating the Crazyflie firmware there\'s the possibility to enter
bootloader mode and flash [new
firmware](https://github.com/bitcraze/crazyflie-release/releases) from within the
client. The bootloader mode is accessed from the menu
*Connect-\>Bootloader*. If there is any problem during the flashing or
a wrong firmware is flashed the process can just be started again.

![CFclient Recovery Bootloading](/docs/images/recovery_bootloader_dialog.png)

To update the firmware in the Crazyflie 2.x do the following:

-   Make sure that the Crazyflie is disconnected from the client and
    powered off.
-   Go to the menu *Crazyflie-\>Bootloader*
-   Select the \"Cold boot (recovery)\" tab in the dialog.
-   Press and hold the power button on the Crazyflie for about 3 seconds. The blue LED (M2) starts to blink to indicate
    the Crazyflie is in bootloader mode.
    - If this does not work, for example if a wrong nRF51 firmware has been flashed, try starting from an un-powered state. Do this by holding the power button and then connecting to power (connecting the battery).
-   Click \"Initiate bootloader cold boot\" in the client
-   Select the latest release from the drop down menu or the file if you have downloaded it from the [Github release page](https://github.com/bitcraze/crazyflie-release/releases).
-   Press \"Program\" and wait (do not restart the Crazyflie until it is finished.)
-   Press \"Restart in firmware mode\"

_Be aware that no deck firmware be updated in this mode, so please use the [the cfclient userguide](/docs/userguides/userguide_client/index.md) after you have recovered Crazyflie._
