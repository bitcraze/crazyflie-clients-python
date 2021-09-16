---
title: ZMQ Server
page_id: zmq-server
---

The [ZMQ](http://zeromq.org/) framework (actually ØMQ) is used to interconnect applications or parts of applications to
other applications via a range of interfaces. It's really nice since there's lots of language support and it's easy to use.

The application uses 4 ports for communicating:
  * 2000: Main command/response socket (server/client)
  * 2001: Logging data and events (publish)
  * 2002: Param events and values(publish)
  * 2003: Connection events (publish)
  * 2004: Control data (pull)

All communication is done using JSON. To test the implementation we have a
[test client](https://github.com/bitcraze/crazyflie-clients-python/blob/develop/examples/zmqsrvtest.py) that could be
useful to have a look at. Each message sent contains a _version_ field that should always be included.

## cfzmq

The client is run using the command line:
```
$ bin/cfzmq -h
usage: cfzmq [-h] [-u URL] [-d]

optional arguments:
  -h, --help         show this help message and exit
  -u URL, --url URL  URL where ZMQ will accept connections
  -d, --debug        Enable debug output
```


The default URL is set to only allow local connections:
```
tcp://127.0.0.1
```


The following commandline will allow remote control:
```
$bin/cfqmq --url "tcp://*"
```



## Command socket

The command messages are implemented as server/client, where each request to the server is answered with a response.
Each message to the server contains version, command and fields related to the command, Each response from the server
will contain version and status, where status 0 means everything was ok. This makes all the calls on this port
synchronous, where the server will not reply until the action is completed or it fails.


Example command:
```
{
  "version": 1,
  "cmd": "command",
  "arg1": "some argument",
  "arg2": "some other argument"
}
```

Example response of **successful** command:
```
{
  "version": 1,
  "status": 0
}
```



For each command there's an enumerated set of statuses that will be used (see blow) and each message where
status != 0 will contain the field _msg_ detailing the error.

Example response of **unsuccessful** command:

```
{
  "version": 1,
  "status": 1,
  "msg": "Something went wrong..."
}
```

## scan

The scan command will trigger a scanning of all of the available interfaces on the server (USB and Crazyradio) and
return all the Crazyflies found. If no interfaces are available (no Crazyradio or Crazyflie) the command will
return an empty list. Therefore there's no error conditions for this command, status will always be 0.


Example command:
```
{
  "version": 1,
  "cmd": "scan"
}
```

Example response:
```
{
  "version": 1,
  "status": 0,
  "interfaces":
    [
      {
        "uri": "radio://0/100/250K",
        "info": "This is a Crazyflie"
      },
      {
        "uri": "debug://0/0",
        "info": "Normal connection"
      }
    ]
}

```

## connect

The connect command will connect to the supplied URI, download the logging TOC and parameter TOC/values and return
everything. There's a timeout on the server-side that will be hit if the server can't connect to a Crazyflie on the
supplied URI (of if there's some other error).

The log TOC will be found in the _log_ dictionary, where the first level is group, the second level is name and the
third is the attributes (see below). So the type of _altHold.target_ will be found in _log->altHold->target->type_.

The param TOC will be found in the _param_ dictionary, where the first level is group, the second level is name and
the third is the attributes (see blow). So the RO/RW attribute for _altHold.aslAlpha_ will be found in _param->altHold->aslAlpha->access_.


Example command:
```
{
  "version": 1,
  "cmd": "connect",
  "uri": "radio://0/10/250K"
}
```

Example response of **successful** command:
```
{
  "version": 1,
  "status": 0,
  "log": {
    "acc": {
      "mag2": {"type": "float"},
      "x": {"type": "float"},
      "y": {"type": "float"},
      "z": {"type": "float"},
      "zw": {"type": "float"}
    },
    "altHold": {
      "err": {"type": "float"},
      "target": {"type": "float"},
      "vSpeed": {"type": "float"},
      "vSpeedASL": {"type": "float"},
      "vSpeedAcc": {"type": "float"},
      "zSpeed": {"type": "float"}
    },
    "baro": {
      "asl": {"type": "float"},
      "aslLong": {"type": "float"},
      "aslRaw": {"type": "float"},
      "pressure": {"type": "float"},
      "temp": {"type": "float"}
    },
    "gyro": {
      "x": {"type": "float"},
      "y": {"type": "float"},
      "z": {"type": "float"}
    },
    "mag": {
      "x": {"type": "float"},
      "y": {"type": "float"},
      "z": {"type": "float"}
    },
    "mag_raw": {
      "x": {"type": "int16_t"},
      "y": {"type": "int16_t"},
      "z": {"type": "int16_t"}
    },
    "motor": {
      "m1": {"type": "int32_t"},
      "m2": {"type": "int32_t"},
      "m3": {"type": "int32_t"},
      "m4": {"type": "int32_t"}
    }
},
"param": {
  "altHold": {
    "altHoldChangeSens": {
      "access": "RW",
      "type": "float",
      "value": "200.0"
    },
    "altHoldErrMax": {
      "access": "RW",
      "type": "float",
      "value": "1.0"
    },
    "aslAlpha": {
      "access": "RW",
      "type": "float",
      "value": "0.920000016689"
    }
  }
}
```



If no Crazyflie is found status 1 will be returned and an error message will be supplied from the driver.

Example response of **unsuccessful** command:

```
{
  "version": 1,
  "status": 1,
  "msg": "Too many packages lost"
}

```

For the log variables (found in _log_) the following attributes are set:

| Field | Type   | Comment                            |
| ----- | ------ | ---------------------------------- |
| type  | string | (u)int8, (u)int16, (u)int32, float |

For the parameters (found in _param_) the following attributes are set:

| Field  | Type   |  Comment                                             |
| ------ | ------ | ---------------------------------------------------- |
| access | string | RO for read only parameters, RW for writable         |
| type   | string | (u)int8_t, (u)int16_t, (u)int32_t, float             |
| value  | string | String representation of the current parameter value |

## log

Logging data from the Crazyflie is done by setting up log configurations that will push log data at a specified
interval ([more info here](https://www.bitcraze.io/documentation/repository/crazyflie-firmware/master/userguides/logparam/)).
There are four command associated with log configurations: _create_, _start_, _stop_ and _delete_. Create and delete
handles if the log configuration is stored in the Crazyflie memory or not. Start and stop handles if the log data is
actually being sent or not from the Crazyflie to the host. Before a log config can be started is has to be created,
before it can be stopped it has to be started and before it can be deleted is has to be created. Note that log block
are automatically started once they have been created.

**Note**: When a host connects to a Crazyflie the log configurations are all deleted. So if you connect, set up log
configurations, disconnect and then connect again the configurations will be deleted.

Below is an example for creating a logging configuration and starting it. The configuration contains the two
variables _pm.vbat_ and _stabilizer.roll_ that will be sent at 1 Hz. Data will be published to the [log socket](#log-socket).

Each action for log configurations (create, start, stop, delete) will be broadcasted on the log data socket. Log
data will also be broadcasted on the same socket.


First create the configuration:
```
{
  "version": 1,
  "cmd": "log",
  "action": "create",
  "name": "Test log block",
  "period": 1000,
  "variables": [
      "pm.vbat",
      "stabilizer.roll"
  ]
}
```

Example response:
```
{
  "version": 1,
  "status": 0
}
```

Then start the configuration:
```
{
  "version": 1,
  "cmd": "log",
  "action": "start",
  "name": "Test log block"
}
```

Example response:
```
{
  "version": 1,
  "status": 0
}
```

The following attributes should be set in the request packet:

| Field     | Type   | Comment                            | Mandatory for |
| --------- | ------ | ---------------------------------- | ------------- |
| name      | string | Name of configuration              | all           |
| action    | string | create, start, stop, delete        | all           |
| period    | int    | Period (in ms) for data to be sent | create        |
| variables | list   | List of variables "group.name"     | create        |

The following errors can be seen in the response packet:

| Action            | Status | Comment                                                             |
| ----------------- | ------ | ------------------------------------------------------------------- |
| create            | 0x01   | One or more variables were not found in the TOC                     |
| create            | 0x02   | The period is either too small/large of the configuration too large |
| create            | 0x03   | Timeout was hit when performing action.                             |
| start/stop/delete | 0x01   | Config name not found                                               |
| start/stop/delete | 0x02   | Timeout was hit when performing action                              |


**note:** The Python API supports logging variables using different types than what the variables is declared
as in the firmware. I.e you can log a uint32_t as a uint8_t, retaining the 8 MSB
([more info here](https://www.bitcraze.io/documentation/repository/crazyflie-firmware/master/userguides/logparam/)).
This is still not implemented.

## param

During run-time it's possible to set parameters that are mapped directly to variables in the
firmware([more info here](https://www.bitcraze.io/documentation/repository/crazyflie-firmware/master/userguides/logparam/)).
Each parameter update is also published on the param socket.

Below is an example command to set the _flightctrl.xmode_ parameter.


Example command:
```
{
    "version": 1,
    "cmd": "param",
    "name": "flightctrl.xmode",
    "value": True
}
```

Example response of **successful** command:
```
{
    "version": 1,
    "status": 0,
    "name": "flightctrl.xmode",
    "value": "1"
}
```

The following errors can be seen in the response packet:

| Status | Comment                                |
| ------ | -------------------------------------- |
| 0x01   | The parameter was not found in the TOC |
| 0x02   | The parameter is RO and cannot be set  |
| 0x03   | The timeout was reached                |

Example response of **un-successful** command:
```
{
    "version": 1,
    "status": 1,
    "msg": "Could not find flightctrl.xmode in TOC"
}
```

The API accepts values as unsigned/signed/float/bool. Booleans are stored as uint8_t and will be converted
to a number (0 for false, 1 for true). The type should match the type that is in the TOC (i.e don't try to
set a float for a uint_8 variable).


| Field | Type                       | Comment                                          |
| ----- | -------------------------- | ------------------------------------------------ |
| name  | string                     | Name of parameter (group.name)                   |
| value | unsigned/signed/float/bool | When received a string is created from the value |

## Log socket

This socket is used for sending log configuration events as well as log data. The events that are sent is
for creating, starting, stopping and deleting a configuration. For every started configuration the log data
will be sent over this socket. To control this see the [log configuration above](#log).

Each message contains an _event_ field (see below) and a _name_ field referring to the log configuration name.


The following events are sent:

| Event   | Comment                         |
| ------- | ------------------------------- |
| created | When a configuration is created |
| started | When a configuration is started |
| stopped | When a configuration is stopped |
| deleted | When a configuration is deleted |
| data    | Log data (see below)            |


Example of a _started_ event:
```
{
  "version": 1,
  "name": "Test log block",
  "event": "started"
}
```



 The following fields is in the data event:

| Field     | Type   | Comment                                                                                          |
| --------- | ------ | ------------------------------------------------------------------------------------------------ |
| name      | string | Name of the config that triggered the data                                                       |
| timestamp | int    | Time since system start (in ms)                                                                  |
| variables | dict   | Dictionary where the keys are variable names (group.name) and the values are the variable values |


Example of a data event:
```
{
  "version": 1,
  "name": "Test log block",
  "event": "data",
  "timestamp": 1004,
  "variables":
    {
      "pm.vbat": 3.5,
      "stabilizer.roll": -80.0
    }
}
```


## Param socket

This socket is used to broadcast parameter updates done on the [command socket](#command-socket)

For each update the variable name and value is sent.


```
{
    "version": 1,
    "name": "flightctrl.xmode",
    "value": "1"
}
```



## Connection socket

This socket is used to broadcast changes in the connection state as events. Connecting the Crazyflie is a synchronous
call to the [command socket](#command-socket) but for instance a lost connection will be asynchronous and broadcasted
on this socket.

Each event has a name and uri, there might also be an optional message. Note that disconnected is always sent no
matter the reason. So a requested disconnect will send a _disconnected_ event, and a lost connection will send a
_lost_ event as well as a _disconnected_ event.


There's a number of different events:

| Event        | Comment                                                         | Msg field |
| ------------ | --------------------------------------------------------------- | --------- |
| requested    | A connection has been requested                                 | No        |
| connected    | A Crazyflie has been connected and the TOCs has been downloaded | No        |
| failed       | A connection request has failed                                 | Yes       |
| disconnected | A Crazyflie has been disconnected                               | No        |
| lost         | An open connection has been lost                                | Yes       |


Example of a lost connection:
```
{
    "version": 1,
    "event": "failed",
    "uri": "radio://0/10/250K",
    "msg": "Too many packets lost!"
}
```


## Control socket

Control commands can be sent at any time after the Crazyflie has been connected and has the following scaling/format:

```
{
  "version": 1,
  "roll": 0.0,
  "pitch": 0.0,
  "yaw": 0.0,
  "thrust": 0.0
}
```


| Param  | Unit      | Limit           |
| ------ | --------- | --------------- |
| roll   | degrees   | N/A             |
| pitch  | degrees   | N/A             |
| yaw    | degrees/s | N/A             |
| thrust | PWM       | 20 000 - 60 000 |
