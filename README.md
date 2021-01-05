# Crazyflie PC client [![CI](https://github.com/bitcraze/crazyflie-clients-python/workflows/CI/badge.svg)](https://github.com/bitcraze/crazyflie-clients-python/actions?query=workflow%3ACI) [![cfclient](https://snapcraft.io//cfclient/badge.svg)](https://snapcraft.io/cfclient)


The Crazyflie PC client enables flashing and controlling the Crazyflie.
It implements the user interface and high-level control (for example gamepad handling).
The communication with Crazyflie and the implementation of the CRTP protocol to control the Crazflie is handled by the [cflib](https://github.com/bitcraze/crazyflie-lib-python) project.

For more info see our [documentation](https://www.bitcraze.io/documentation/repository/crazyflie-clients-python/master/).

# Installing from build

## Linux

The client can be installed and run with snap, it can be found on [snapcraft](https://snapcraft.io/cfclient) (ie. search Crazyflie in Ubuntu software) or installed from command line:
```
snap install --beta cfclient
```

The edge version is currently broken (latest github commit). The last working version has been set to beta. The next release will be pushed in the snapcraft stable channel.

It is still required to set the udev permission with the snap, see the last section of this page.

## Windows

A windows installer is automatically built for each git commit in [appveyor](https://ci.appveyor.com/project/bitcraze/crazyflie-clients-python/build/artifacts).

For each release, the release built is available in the [github release page](https://github.com/bitcraze/crazyflie-clients-python/releases).

To use Crazyradio you will have to [install the drivers](https://github.com/bitcraze/crazyradio-firmware/blob/master/docs/building/usbwindows.md).

## From Pypi (Windows, Mac, Linux, ..., with python3)

Each release of the client is pushed to the [pypi repository](https://pypi.org/project/cfclient/). If you have python >= 3.5, it can be installed with pip:

```
python3 -m pip install cfclient
```

Mac and windows will also need the SDL2 library to be installed (see bellow)

# Running from source

The Crazyflie client requires Python >= 3.5. The followind instruction describe hot to install it from source.

## Pip and Venv

It is good to work within a [python venv](https://docs.python.org/3/library/venv.html), this way you are not installing dependencies in your main python instance.

At the very least you should **never** run pip in sudo, this would install dependencies system wide and could cause compatiblity problems with already installed application. If the ```pip``` of ```python3 -m pip``` command request the administrator password, you should run the command with ```--user``` (for example ```python3 -m pip install --user -e .```). This should not be required on modern python distribution though since the *--user*  flag seems to be the default behaviour.

## Linux

### Prerequisites

From a fresh Ubuntu 20.04 system, running the client form source requires git and pip.

```
sudo apt install git python3-pip
git clone https://github.com/bitcraze/crazyflie-clients-python
cd crazyflie-clients-python
```

### Installing the client

All other dependencies on linux are handled by pip so to install an editable copy simply run:

```
$ python3 -m pip install -e .
```

The client can now be runned using ```cfclient``` if the local pip bin directory is in the path (it should be in a venv or after a reboot), or with ```python3 -m cfclient.gui```.

## Windows (7/8/10)

Running from source on Windows is tested using the official python build from [python.org](https://python.org). The client works with python version >= 3.5. The procedure is tested with 32bit python. It will work with 64bit python but since it is not tested.

To run the client you should install python, make sure to check the "add to path" checkbox during install. You should also have git installed and in your path. Use git to clone the crazyflie client project.

Open a command line window and move to the crazyflie clients folder (the exact command depends of where the project is cloned):
```
cd crazyflie-clients-python
```

Download the SDL2.dll windows library:
```
python3 tools\build\prep_windows
```

Install the client in development mode:
```
pip3 install -e .[dev]
```

You can now run the clients with the following commands:
```
cfclient
cfheadless
cfloader
cfzmq
```

**NOTE:** To use Crazyradio you will have to [install the drivers](https://github.com/bitcraze/crazyradio-firmware/blob/master/docs/building/usbwindows.md)

### Creating Windows installer

Building the windows installer currently only works with python 3.6. This is due to a bug in CX_freeze, see issue #441 for update about this problem.

To build the windows installer you need to install the dev dependencies
```
pip install -e .[dev]
```

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

**Note**: On macOS 11 Big Sur, a recent version of python 3.9 and pip3 from brew is required, make sure your python3 install is up to date and if necessary upgrade pip with ```pip3 install --upgrade pip```.

The supported way to run on Mac is by using the [Homebrew](http://brew.sh/) distribution of python3.

Python3 and required libs can be installed with brew:
```
brew install python3 sdl2 libusb
brew link python3   # This makes sure the latest python3 is used
# if "which python3" does not return "/usr/local/bin/python3", relaunch your terminal
```

To install the client in edit mode:
```
pip3 install -e .
```

The client can now be started with ```cfclient``` or ```python3 -m cfclient.gui```.

## Working with the GUI .ui files

you can edit the .ui files for the GUI with QtCreator. For Windows and Mac You can the Qt development kit from the [Qt website](https://www.qt.io/download-open-source/). On linux QtCreator is usually available as package, for example on Ubuntu it can be installed with ```sudo apt install qtcreator```.


### Setting udev permissions

Using Crazyradio on Linux requires that you set udev permissions. See the cflib
[readme](https://github.com/bitcraze/crazyflie-lib-python#setting-udev-permissions)
for more information.
