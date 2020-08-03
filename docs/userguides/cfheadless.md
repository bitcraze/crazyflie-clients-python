---
title: Crazyflie headless client
page_id: cfheadless
---

The *cfheadless* client doesn\'t have a UI, it\'s run directly from the
command line and is suited for headless hosts like the Raspberry Pi.

## cfheadless


The script is located in the *bin* directory in the
*crazyflie-clients-python* repository and client. Here\'s how to use the
script:
```
$ bin/cfheadless -h

usage: cfheadless [-h] [-u URI] [-i INPUT] [-d] [-c CONTROLLER]
              [--controllers] [-x]

optional arguments:
-h, --help            show this help message and exit
-u URI, --uri URI     URI to use for connection to the Crazyradio dongle,
                    defaults to radio://0/10/250K
-i INPUT, --input INPUT
                    Input mapping to use for the controller,defaults to
                    PS3_Mode_1
-d, --debug           Enable debug output
-c CONTROLLER, --controller CONTROLLER
                    Use controller with specified id, id defaults to 0
--controllers         Only display available controllers and exit
```
The client is exited either by taking out the Crazyradio USB dongle or
pressing Ctrl+C

## Examples


Connect to a Crazyflie at channel 100 and speed 250Kbit using input
mapping *PS3\_Mode\_1*
```
crazyflie-clients-python$ bin/cfheadless -u radio://0/100/250K -PS1_Mode_1
```
