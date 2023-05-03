---
title: Bootload the Crazyflie 2.X
page_id: cfloader
---

The Crazyflie as well as decks that has a firmware can be bootloaded from the command line using the
*cfloader* script.

**Note:** To enter the bootloader for the Crazyflie 2.X power off the
platform and start it again by pressing the power button for at least
1.5 seconds, but not more than 5.

---

## Programming Crazyflie from firmware projects

When developing with the Crazyflie firmware projects, either
[crazyflie-firmware](https://github.com/bitcraze/crazyflie-firmware) or
[crazyflie2-nrf-firmware](https://github.com/bitcraze/crazyflie2-nrf-firmware)
you can flash your current build with the [STM install instructions](https://www.bitcraze.io/documentation/repository/crazyflie-firmware/master/building-and-flashing/build/#flashing) or the [NRF install instructions](https://www.bitcraze.io/documentation/repository/crazyflie2-nrf-firmware/master/build/build/)


---

## cfloader

The script is located in the *bin* directory in the
*crazyflie-clients-python* repository and client. Here\'s how to use the
script:

    crazyflie-clients-python$ bin/cfloader

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



python3 -m cfloader flash cf2.bin stm32-fw -w radio://0/10/2M/E7E7E7E701

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

    crazyflie-clients-python$ bin/cfloader flash cf2.bin stm32-fw
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

Flashing new firmware for the STM32 MCU with warmbooting with a known uri:

    crazyflie-clients-python$ bin/cfloader flash cf2.bin stm32-fw -w radio://0/10/2M/E7E7E7E701
    Reset to bootloader mode ...
    Connected to bootloader on Crazyflie 2.0 (version=0x10)
    Target info: nrf51 (0xFE)
    Flash pages: 232 | Page size: 1024 | Buffer pages: 1 | Start page: 88
    144 KBytes of flash avaliable for firmware image.
    Target info: stm32 (0xFF)
    Flash pages: 1024 | Page size: 1024 | Buffer pages: 10 | Start page: 16
    1008 KBytes of flash avaliable for firmware image.

    Flashing 1 of 1 to stm32 (fw): 76435 bytes (75 pages) ..........10..........10..........10..........10..........10..........10..........10.....5
    Reset in firmware mode ..

Flash a new firmware package (containing both nRF51, STM32 and deck firmwares):

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

## AI-deck examples

The AI-deck should be mounted on the Crazyflie when running the cfloader.

Flash a new firmware to the ESP on the AI-deck:

    crazyflie-clients-python$ bin/cfloader flash myEspApp.bin deck-bcAI:esp-fw -w radio://0/30/2M
    Reset to bootloader mode ...
    | 4% Writing to bcAI:esp deck memory
    / 9% Writing to bcAI:esp deck memory
    - 14% Writing to bcAI:esp deck memory
    \ 19% Writing to bcAI:esp deck memory
    ...

Flash a new firmware to the GAP8 on the AI-deck:

    crazyflie-clients-python$ bin/cfloader flash myGap8App.bin deck-bcAI:gap8-fw -w radio://0/30/2M
    Reset to bootloader mode ...
    Skipping bcAI:esp
    | 4% Writing to bcAI:gap8 deck memory
    / 9% Writing to bcAI:gap8 deck memory
    - 14% Writing to bcAI:gap8 deck memory
    \ 19% Writing to bcAI:gap8 deck memory
    ...

Flash a new firmware to the ESP on the AI-deck from a release zip.

    crazyflie-clients-python$ bin/cfloader flash a-release.zip deck-bcAI:esp-fw -w radio://0/30/2M
    Reset to bootloader mode ...
    Deck bcAI:esp, reset to bootloader
    | 0% Writing to bcAI:esp deck memory
    / 1% Writing to bcAI:esp deck memory
    - 2% Writing to bcAI:esp deck memory
    ...
