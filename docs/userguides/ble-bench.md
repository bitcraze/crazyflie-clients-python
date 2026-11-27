---
title: Experimental BLE bench connection
page_id: ble-bench
---

This opt-in mode uses the [experimental cflib BLE driver](https://github.com/bitcraze/crazyflie-lib-python/pull/611) on macOS.
It provides inspection and telemetry, with flight controls disabled. It has
been exercised with a Crazyflie 2.1 on macOS / Apple Silicon. It is not a validated
flight link, and other platforms have not been tested.

Install the cflib BLE driver branch with its `ble` extra first; a released cflib
without `enable_ble_driver` cannot run this mode. Then run this client branch:

```sh
cfclient --ble
```

Close the mobile app, power the Crazyflie, use **Scan**, select its BLE URI and
connect. Grant Bluetooth permission through the operating system when needed.
Use only one client at a time. The selector preserves the complete URI when Qt emits an integer index-change
signal. Normal startup without `--ble` keeps
the existing radio/USB behavior.

BLE mode scans only BLE. This matters because radio discovery may disable BLE
on the Crazyflie until restart. The scanner reports errors without opening a
radio device. The cflib driver validates the GATT profile and long-packet echo
before downloading TOCs; corrected nRF BLE framing is required. This client
does not flash firmware or enable its bootloader UI in BLE mode.

The enabled tabs provide plotting, log configuration, client logs and TOC inspection. Flight, tuning, LED and
parameter-edit tabs are not loaded; controller callbacks and flight shortcuts
are guarded. The transport independently blocks flight/persistent-write packets.
The bench indicator remains visible, and the input footer does not invite the
user to attach a joystick to fly.

On the tested unit, full initialization took about 250 s without TOC cache and
93 s on reconnection. Reading parameter values still takes time after loading
cached tables. The real GUI displayed battery voltage and completed confirmed
STOP/DELETE cleanup for the log blocks it created. These are bench observations,
not latency/range guarantees.

Do not increase logging rates until the connection is fully initialized. The
driver allows a minimum period of 100 ms and up to four owned log blocks. Stop
logging or disconnect after an experiment. No motor commands are needed for
battery, inertial-sensor or attitude telemetry.
