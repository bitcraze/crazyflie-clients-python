---
title: ZMQ implementation of the cfclient
page_id: cfclient_zmq
---


The [Crazyflie Python client](/docs/userguides/userguide_client.md)
runs a number of back-ends where you can set/get information from other
applications via [ZMQ](http://zeromq.org/).

Here\'s a list of the ports/functions available:

 | Port |  Type |  Functionality|
 | ------| ------| --------------|
 | 1213 |  REQ  |  Set parameters|
 | 1214 |  PUSH  | LED-ring memory|
 | 1212 |  PULL |  Input device|

---

## Parameters

The parameter back-end gives access to setting parameters in the
Crazyflie. The back-end is enabled by default.

### Protocol

Available fields:

|  Field  |   Format |  Comments |
|  -------|-- --------| ---------------------------------------------------|
|  version|   int    |  Should be set to 1 |
|  cmd    |   string |  Command to send (currently only set is supported) |
|  name   |   string |  The name of the parameter |
|  value |    string |  The value of the parameter |

 Example of setting the *buzzer.freq*
parameter to 4000.

    {
      "version": 1,
      "cmd": "set",
      "name" : "buzzer.freq",
      "value": "4000"
    }

---

## LED-ring

The LED-ring back-end gives access to the LED-ring memory driver where
the user can write the RGB values for all 12 LEDs on the ring. The
back-end is enabled by default.

### Protocol

 Available fields:

|  Field   |  Format                    |      Comments|
|  ---------| --------------------------|----- ---------|---------------------------------
 | version |  int                           |  Should be set to 1|
 | rgbleds  | array of 3 item arrays of int |  R/G/B value for each LED (starting at 1)|

Example of setting all LEDs off:

    {
      "version": 1,
      "rgbleds": [
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0]
      ]
    }

---

## Input device

If you don\'t want to use the API and you don\'t want to bother about
scanning/connecting/logging/etc or there\'s no API for the environment
you use, there\'s an easy way to control the Crazyflie. Just like you
would control the Crazyflie with a gamepad or joystick connected to a
computer, you can use ZMQ to inject control set-points directly into the
client. You still use the client for connecting/logging/graphing/setting
parameters, it\'s just the control part that\'s broken out.

By default this is disabled in the configuration file and needs to be
enabled. The configuration file parameter is named *enable\_zmq\_input*
(see
[this](/docs/development/dev_info_client.md#user-configuration-file) to
edit the configuration). To enable controlling by the back-end select
the *ZMQ\@127.0.0.1:1212* input device in the *Input device* menu.

### Protocol

Available fields:

| Field  |        Format|   Comments|
|  --------------| --------| ----------|
|  version       | int     | Should be set to 1|
|  client\_name  | string   |Name of the client (currently unused)|
|  ctrl          | dict     |A dictionary with keys and values that match the internal names of controls in the client (see list below)|

Available keys for the *ctrl* dictionary:

 | Field |   Range |  Unit        |     Comments|
|---------|----------|----------------|---------------|
|  roll  |   N/A    | degrees      |
|  pitch |   N/A    | degrees     |
|  yaw   |   N/A    | degrees/second |
|  thrust |  0-100  | Percent  |
|  estop  |  T/F    | boolean  |        Used to stop the Crazyflie and disable the control
|  alt1  |   T/F    | boolean  |        Alt1 is internally mapped to functionality like switching LED-ring effect
|  alt2   |  T/F    | boolean |         Alt2 is internally mapped to functionality like switching LED-ring headlights on/off

Example:

    {
        "version": 1,
        "client_name": "ZMQ client",
        "ctrl": {
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            "thrust": 0.0
        }
    }



**NOTE1**: Altitude hold is currently not working.

**NOTE2**: The values are used at 100Hz in the client, no matter at what
rate they are sent via ZMQ
