---
title: Bootloader the Crazyflie 2.X
page_id: cfloader
---




The Crazyflie can be bootloaded from the commandline using the
*cfloader* script.

**Note:** To enter the bootloader for the Crazyflie 2.X power off the
platform and start it again by pressing the power button for at least
1.5 seconds, but not more than 5.

---

## Programming Crazyflie from firmware projects

When developping with the Crazyflie firmware projects, either
[crazyflie-firmware](https://github.com/bitcraze/crazyflie-firmware) or
[crazyflie2-nrf-firmware](https://github.com/bitcraze/crazyflie2-nrf-firmware)
you can flash your current build with:

    make cload

If you want the Crazyflie to restart automatically in bootloader mode
you can enable the warmboot mode. To do so, edit the file
\'tool/make/config.mk\' and add the address of your Crazyflie:

    CLOAD_CMDS = -w radio://0/80/250K/E7E7E7E7E7

After this, \'make cload\' will restart the Crazyflie in bootlader mode,
flash it and restart it with the new firmware.

In warmboot mode the bootloader is launched
using a random address. This means that multiple Crazyflie can be
programmed at the same time without collision.

**Warning:** If the flashing operation fails or if
the firmware has a bug, it may be impossible to warmboot. In that case
start the bootloader manually and disable warmboot temporarly by
programming with:

    make cload CLOAD_CMDS=

---

## cfloader

The script is located in the *bin* directory in the
*crazyflie-clients-python* repository and client. Here\'s how to use the
script:

    crazyflie-clients-python$ bin/cfclient

    ==============================
     CrazyLoader Flash Utility
    ==============================

     Usage: bin/cfloader [CRTP options] <action> [parameters]

    The CRTP options are described above

    Crazyload option:
       info                    : Print the info of the bootloader and quit.
                                 Will let the target in bootloader mode
       reset                   : Reset the device in firmware mode
       flash <file> [targets]  : flash the <img> binary file from the first
                                 possible  page in flash and reset to firmware
                                 mode.

---

## Crazyflie 2.X examples

Flashing new firmware for the nRF51 MCU:

    crazyflie-clients-python$ bin/cfloader flash cf2_nrf.bin nrf51-fw
    Restart the Crazyflie you want to bootload in the next  10 seconds ...  done!
    Connected to bootloader on Crazyflie 2.0 (version=0x10)
    Target info: nrf51 (0xFE)
    Flash pages: 232 | Page size: 1024 | Buffer pages: 1 | Start page: 88
    144 KBytes of flash avaliable for firmware image.
    Target info: stm32 (0xFF)
    Flash pages: 1024 | Page size: 1024 | Buffer pages: 10 | Start page: 16
    1008 KBytes of flash avaliable for firmware image.

    Flashing 1 of 1 to nrf51 (fw): 25151 bytes (25 pages) .1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1
    Reset in firmware mode ...

Flashing new firmware for the STM32 MCU:

    crazyflie-clients-python$ bin/cfloader flash cflie.bin stm32-fw
    Restart the Crazyflie you want to bootload in the next  10 seconds ...  done!
    Connected to bootloader on Crazyflie 2.0 (version=0x10)
    Target info: nrf51 (0xFE)
    Flash pages: 232 | Page size: 1024 | Buffer pages: 1 | Start page: 88
    144 KBytes of flash avaliable for firmware image.
    Target info: stm32 (0xFF)
    Flash pages: 1024 | Page size: 1024 | Buffer pages: 10 | Start page: 16
    1008 KBytes of flash avaliable for firmware image.

    Flashing 1 of 1 to stm32 (fw): 76435 bytes (75 pages) ..........10..........10..........10..........10..........10..........10..........10.....5
    Reset in firmware mode ...

Flash a new firmware package (containing both nRF51 and STM32 firmware):

    crazyflie-clients-python$ bin/cfloader flash cf2_dev_update.zip
    Restart the Crazyflie you want to bootload in the next  10 seconds ...  done!
    Connected to bootloader on Crazyflie 2.0 (version=0x10)
    Target info: nrf51 (0xFE)
    Flash pages: 232 | Page size: 1024 | Buffer pages: 1 | Start page: 88
    144 KBytes of flash avaliable for firmware image.
    Target info: stm32 (0xFF)
    Flash pages: 1024 | Page size: 1024 | Buffer pages: 10 | Start page: 16
    1008 KBytes of flash avaliable for firmware image.

    Flashing 1 of 2 to stm32 (fw): 76435 bytes (75 pages) ..........10..........10..........10..........10..........10..........10..........10.....5
    Flashing 2 of 2 to nrf51 (fw): 25151 bytes (25 pages) .1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1
    Reset in firmware mode ...
