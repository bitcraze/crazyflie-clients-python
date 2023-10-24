---
title: Installation Instructions
page_id: install
---

## Prerequisites

This project requires Python 3.7+.

There are a few things to sort out on your machine before you can install the client. Please see the appropriate
section depending on your environment.

### Debian/Ubuntu

For <  Ubuntu 20.04 you will need to check first if which version your python is on and if you have 'python3' on your system.

From a fresh Ubuntu 20.04 system, running the client form source requires git, pip and a lib for the Qt GUI.

```
sudo apt install git python3-pip libxcb-xinerama0
pip3 install --upgrade pip
```

> For some versions of Ubuntu 22.04 you might need to install more packes like `libxcb-cursor0`. Check out [QT6 package dependency list]( https://doc.qt.io/qt-6/linux-requirements.html).

#### Setting udev permissions

Using Crazyradio on Linux requires that you set udev permissions. See the cflib
[installation guide](https://www.bitcraze.io/documentation/repository/crazyflie-lib-python/master/installation/usb_permissions/)
for more information.

### Windows

Install Python3 using the official python build from [python.org](https://python.org). Make sure to check the "add to path" checkbox during install. Make sure to check if it works by opening a cmd or powershell terminal:
```
python --version
pip --version
```

upgrade pip as well:
```
pip3 install --upgrade pip
```

Install git from the [official git website](https://git-scm.com/). Make sure it is in PATH as well, which can be checked also with:
```
git --version
```

#### Install crazyradio drivers

To use Crazyradio you will have to [install the drivers](https://www.bitcraze.io/documentation/repository/crazyradio-firmware/master/building/usbwindows/)

### Mac

#### Intel X86

Python3 and required libs can be installed with brew:
```
brew install python3 libusb
brew link python3   # This makes sure the latest python3 is used
# if "which python3" does not return "/usr/local/bin/python3", relaunch your terminal
pip3 install --upgrade pip.
```

#### Apple M1

On Apple M1 Macs, care should be taken to use the X86 version of Brew since not all required dependencies compiles for the native `arm64` architecture of the M1 macs. This can be done by using the `arch` commands when installing brew:
``` bash
# Installing brew for x86_64, it will be installed in /usr/local by default
arch --x86_64 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# Now we have to use brew and then python from /usr/local ...
arch --x86_64 brew install python@3.9 libusb
# The arch command is not required anymore since everything brew installed are x86 executables
```

From there, you can either add `/usr/local/bin` up in your path variable or run `/usr/local/bin/pip3` and `/usr/local/bin/python3` instead of `pip3` and `python3`.

## Installing from latest release

If you plan to use the client to control the Crazyflie, we highly recommend you to install the latest release using pip,
as this is a well tested and stable. Please see next section.

On the other hand, if you intend to do development work on the client and modify the source code, please see
[Installing from source](#installing-from-source) bellow.

### From Pypi (Windows, Mac, Linux, ..., with python3)

Each release of the client is pushed to the [pypi repository](https://pypi.org/project/cfclient/), so it can be installed with pip:

```
pip3 install cfclient
```
## Installing from source

If you are planning to do development work with the cfclient, you are at right spot!

The sections bellow describes how to install the client from source on various platforms.

Make sure to also install the [cflib](https://github.com/bitcraze/crazyflie-lib-python) from source as it is common to
modify or examine this code as well when working with the client.

When you have installed the client according to the instructions below, you can run the clients with the following commands:
```
cfclient
cfheadless
cfloader
cfzmq
```

or with

```python3 -m cfclient.gui```

It is good to work within a [python venv](https://docs.python.org/3/library/venv.html), this way you are not installing
dependencies in your main python instance. For those that prefer it, you could also use Anaconda.

### Linux
Clone the repository with git

```
git clone https://github.com/bitcraze/crazyflie-clients-python
cd crazyflie-clients-python
```

#### Installing the client

All other dependencies on linux are handled by pip so to install an editable copy simply run:

```
$ pip3 install -e .
```

If you plan to do development on the client you should run:
```
$ pip3 install -e .[dev]
```

The client can now be run if the local pip bin directory is in the path (it should be in a
venv or after a reboot).

Avoid running pip in sudo, this would install dependencies system wide and could cause
compatibility problems with already installed applications. If the ```pip``` of ```python3 -m pip``` command request
the administrator password, you should run the command with ```--user```
(for example ```python3 -m pip install --user -e .```). This should not be required on modern python distribution
though since the *--user*  flag seems to be the default behavior.

### Windows (7/8/10/11)

Assuming git is installed such that you can use it from powershell/cmd, cd to a desired folder and git clone the project:

```
git clone https://github.com/bitcraze/crazyflie-clients-python
cd crazyflie-clients-python
```
Install the client from source
```
pip3 install -e .
```

or install the client in development mode:
```
pip install -e .[dev]
```

### Mac OSX

```
git clone https://github.com/bitcraze/crazyflie-clients-python
cd crazyflie-clients-python
```

To install the client in edit mode:
```
pip3 install -e .
```

## Extra

### Pre commit hooks (ubuntu)
If you want some extra help with keeping to the mandated python coding style you can install hooks that verify your style at commit time. This is done by running:
```
$ pip3 install pre-commit
```
go to crazyflie-lib-python root folder and run
```
$ pre-commit install
$ pre-commit run --all-files
```
This will run the lint checkers defined in `.pre-commit-config-yaml` on your proposed changes and alert you if you need to change anything.

### Working with the GUI .ui files

you can edit the .ui files for the GUI with QtCreator. For Windows and Mac You can the Qt development kit from the [Qt website](https://www.qt.io/download-open-source/). On linux QtCreator is usually available as package, for example on Ubuntu it can be installed with ```sudo apt install qtcreator```.

### Debugging the client from an IDE

It is convenient to be able to set breakpoints, examine variables and so on from an IDE when debugging the client. To get
this to work you need to run the python module `cfclient.gui` as the debug target in the IDE.

In VSCode for instance, the launch.json should look something like this:

``` json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Crazyflie client",
            "type": "python",
            "request": "launch",
            "module": "cfclient.gui"
        },
    ]
}
```

As noted earlier, it is common that work on the client also involve work in the [crazyflie-lib-python](https://github.com/bitcraze/crazyflie-lib-python).
The `launch.json` documented here can also be used in the crazyflie lib project to debug lib-related code.
