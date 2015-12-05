Crazyflie Python client/API
===========================

Checks
------
 - Verify that configuration files are still working
 - Verify that params are working
     - Param list shows all params
     - Possible to set a param
 - Verify that log is working
     - Log list shows all loggable variables
     - Possible to create log configuration
     - Possible to plot log configuration
     - Possible to start/stop log configuration
     - Possible to write logged data from log configuration to file
 - Verify that it's possible to connect to the debugdriver
 - Verify that the following works on all OSes supported
     - Verify that input devices are working
         - No input devices
         - One input devices
         - Multiple input devices
         - Map device from scratch and by loading previous configuration
     - Scan and connect to Crazyflie via Crazyradio
     - Scan and connect to Crazyflie via USB
     - Negative tests such as
         - Disconnect Crazyflie via USB when connected
         - Disconnect Crazyradio when connected
     - Showing the Debug tab in the About dialog
 - Verify that it's possible to change the Crazyflie configuration block
 - Verify bootloading, both from UI and cfload
 - Verify that it's possible to connect to a Crazyflie and control it

Preparations
------------
 - Connect to the latest firmware release, download the param/log TOC and commit the cache
 - Make sure that all packages and resources is added to the setup.py ```setup_args```

Build distribution
------------------
 1. Reset tree into a clean tree with "git reset --hard HEAD"
	 - **Warning: this removes all changes from the source tree!**
 2. Tag commit with "year.month[.patch]". For example 2014.12.2 or 2015.2 and push the tag to Github
 3. ```python setup.py sdist```

Distribute
----------
 1. Upload the release from ```dist/cfclient-*``` to Github release for this tag