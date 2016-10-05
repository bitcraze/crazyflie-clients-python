Ramp ZMQ client in C
====================

This example implements a simple ZMQ client in C that ramps the
Crazyflie motor thrust. It is equivalent to the thrust.py example
file.

Compiling
---------

To compile the example you need the libzmq development files. Tested
with libzmq 3.1.4 (libzmq3-dev on Ubuntu 16.04). Then just compile
with ```make```.

Running
-------

 - Enable ZMQ input in the client.
 - Set the input device to ZQM.
 - Connect a Crazyflie.
 - Launch ```./ramp```

The thrust should ramp from 0 to 30% in 15 seconds.
