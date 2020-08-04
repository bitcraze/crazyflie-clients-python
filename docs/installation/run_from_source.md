---
title: Running from source
page_id: run_from_source
---

The Crazyflie client requires [cflib](https://github.com/bitcraze/crazyflie-lib-python).
If you want to develop with the lib too, follow the cflib readme to install it.

## Windows (7/8/10)

Running from source on Windows is tested using the official python build from [python.org](https://python.org). The client works with python version >= 3.5. The procedure is tested with 32bit python. It should work with 64bit python but since it is not tested it can be broken (if so, do not hesitate to send a fix ;-).

To run the client you should install python, make sure to check the "add to path" checkbox during install. You should also have git installed and in your path. Use git to clone the crazyflie client project.

Open a command line window and move to the crazyflie clients folder (the exact command depends of where the project is cloned):
```
cd crazyflie-clients-python
```

Download the SDL2.dll windows library:
```
python tools\build\prep_windows
```

Install the client in development mode:
```
pip install -e .[dev,qt5]
```

You can now run the clients with the following commands:
```
cfclient
cfheadless
cfloader
cfzmq
```

**NOTE:** To use Crazyradio you will have to [install the drivers](https://github.com/bitcraze/crazyradio-firmware/blob/master/docs/building/usbwindows.md)

### Working on the client with PyCharm

Pycharm is an IDE for python. Any Python IDE or development environment will work for the Crazyflie client. To work on the Crazyflie firmware with Pycharm, install pycharm community edition and open the Crazyflie client folder in it. Pycharm will automatically detect the python installation.

To run the client, open and run the file ```bin/cfclient```.

You are now able to edit and debug the python code. you can edit the .ui files for the GUI with QtCreator. You can the Qt development kit from the [Qt website](https://www.qt.io/download-open-source/) and open the .ui files in QtCreator.

### Creating Windows installer

When you are able to run from source, you can build the windows executable and installer.

First build the executable
```
python setup.py build
```

Now you can run the client with ```build\exe.win32-3.6\cfclient.exe```.

To generate the installer you need [nsis](http://nsis.sourceforge.net/) installed and in the path. If you
are a user of [chocolatey](https://chocolatey.org/) you can install it with ```choco install nsis.portable -version 2.50```,
otherwise you can just download it and install it manually.

To create the installer:
```
python win32install\generate_nsis.py
makensis win32install\cfclient.nsi
```

## Mac OSX

Unlike for Windows, there is no build for mac yet.
It should be possible to package the client as a mac app and [help is wanted](https://github.com/bitcraze/crazyflie-clients-python/issues/231).
In the mean time you can run the client by installing python and pulling the client python package.

### Using the official python distribution

The easiest to get the client running on Mac if you do not already have Homebrew installed is to use the official Python distribution.
If you are using Homebrew look at the next section.
If you are using Anaconda/Conda, the procedure should be very similar but you can skip the python installation.

 1) Download and install python from [python.org](https://python.org)
 2) [Download sdl2](https://www.libsdl.org/download-2.0.php) for Mac OSX and copy SDL2.framework into /Lirary/Frameworks
 3) Open a console and install the client with ```python3 -m pip install cfclient[qt5] pysdl2```. This will install the latest release.

You can now launch the client with ```python3 -m cfclient.gui```

If you want to develop and modify the client, you can clone this repos, uninstall cfclient with ```python3 -m pip uninstall cfclient``` and install it in development mode by navigating into the repos root folder and installing the client in edit mode: ```python3 -m pip install -e .```.

### Using homebrew
**IMPORTANT NOTE**: The following will use
[Homebrew](http://brew.sh/) and its own Python distribution. If
you have a lot of other 3rd party python stuff already running on your system
they might or might not be affected by this.

1. Install homebrew

    See [the Homebrew site](https://brew.sh/)

1. Install the brew bottles needed
    ```
    brew install python3 sdl sdl2 sdl_image sdl_mixer sdl_ttf libusb portmidi pyqt5
    ```

1. Install the client

    * If you only want to use the client to fly the Crazyflie and don't care about coding
    ```
    pip3 install cfclient
    ```

    * If you want to develop the client and play with the source code. From the source folder run
    ```
    pip3 install -e .
    ```
    If you want to develop on cflib as well, install cflib from <https://github.com/bitcraze/crazyflie-lib-python>

1. You now have all the dependencies needed to run the client. The client can now be started from any location by:
    ```
    cfclient
    ```

## Linux

### Launching the GUI application

If you want to develop with the lib, install cflib from https://github.com/bitcraze/crazyflie-lib-python

Cfclient requires Python3, pip and pyqt5 to be installed using the system package manager. For example on Ubuntu/Debian:
```
sudo apt-get install python3 python3-pip python3-pyqt5 python3-pyqt5.qtsvg
```

Install cfclient to run it from source. From the source folder run (to install
for your user only you can add ```--user``` to the command):
```
pip3 install -e .
```
To launch the GUI application in the source folder type:
```python3 bin/cfclient```

To launch the GUI after a systemwide installation, execute ```cfclient```.

### Dependencies

The Crazyflie PC client has the following dependencies:

* Installed from system packages
  * Python 3.4+
  * PyQt5
  * A pyusb backend: libusb 0.X/1.X
* Installed from PyPI using PIP:
  * cflib
  * PyUSB
  * PyQtGraph
  * ZMQ
  * appdirs
  * PyYAML

### Setting udev permissions

Using Crazyradio on Linux requires that you set udev permissions. See the cflib
[readme](https://github.com/bitcraze/crazyflie-lib-python#setting-udev-permissions)
for more information.
