---
title: Installation Instructions
page_id: install
---
# Prerequisites installation

## Debian


For <  Ubuntu 20.04 you will need to check first if which version your python is on and if you have 'python3' on your system.

From a fresh Ubuntu 20.04 system, running the client form source requires git and pip.

```
sudo apt install git python3-pip
pip3 install --upgrade pip.
```
### Setting udev permissions

Using Crazyradio on Linux requires that you set udev permissions. See the cflib
[readme](https://github.com/bitcraze/crazyflie-lib-python#setting-udev-permissions)
for more information.

## Windows

Install Python3 using the official python build from [python.org](https://python.org). Make sure to check the "add to path" checkbox during install. Make sure to check if it works by opening a cmd or powershell terminal:
```
python --version
pip --version
```

upgrade pip as well:
```
pip3 install --upgrade pip.
```

Install git from the [official git website](https://git-scm.com/). Make sure it is in PATH as well, which can be checked also with:
```
git --version
```

### Install crazyradio drivers

To use Crazyradio you will have to [install the drivers](https://github.com/bitcraze/crazyradio-firmware/blob/master/docs/building/usbwindows.md)

## Mac

Python3 and required libs can be installed with brew:
```
brew install python3 libusb
brew link python3   # This makes sure the latest python3 is used
# if "which python3" does not return "/usr/local/bin/python3", relaunch your terminal
pip3 install --upgrade pip.
```

# Installing from latest release

## From Pypi (Windows, Mac, Linux, ..., with python3)

Each release of the client is pushed to the [pypi repository](https://pypi.org/project/cfclient/). If you have python >= 3.6, it can be installed with pip:

```
pip install cfclient
```
# Installing from source

The Crazyflie client requires Python >= 3.6. The following instructions describe hot to install it from source.

## Pip and Venv

It is good to work within a [python venv](https://docs.python.org/3/library/venv.html), this way you are not installing dependencies in your main python instance. For those that prefer it, you could also use Anaconda.

## Linux
Clone the repository with git

```
git clone https://github.com/bitcraze/crazyflie-clients-python
cd crazyflie-clients-python
```

### Installing the client

All other dependencies on linux are handled by pip so to install an editable copy simply run:

```
$ pip3 install -e .
```

If you plan to do development on the client you should run:
```
$ pip3 -e .[dev]
```

The client can now be runned using ```cfclient``` if the local pip bin directory is in the path (it should be in a venv or after a reboot), or with ```python3 -m cfclient.gui```.

At the very least you should **never** run pip in sudo, this would install dependencies system wide and could cause compatiblity problems with already installed application. If the ```pip``` of ```python3 -m pip``` command request the administrator password, you should run the command with ```--user``` (for example ```python3 -m pip install --user -e .```). This should not be required on modern python distribution though since the *--user*  flag seems to be the default behaviour.

## Windows (7/8/10)


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

You can now run the clients with the following commands:
```
cfclient
cfheadless
cfloader
cfzmq
```


## Mac OSX

To install the client in edit mode:
```
pip3 install -e .
```

The client can now be started with ```cfclient``` or ```python3 -m cfclient.gui```.

# Extra 

## Pre commit hooks
If you want some extra help with keeping to the mandated python coding style you can install hooks that verify your style at commit time. This is done by running:
```
$ pre-commit install
```
This will run the lint checkers defined in `.pre-commit-config-yaml` on your proposed changes and alert you if you need to change anything.

## Working with the GUI .ui files

you can edit the .ui files for the GUI with QtCreator. For Windows and Mac You can the Qt development kit from the [Qt website](https://www.qt.io/download-open-source/). On linux QtCreator is usually available as package, for example on Ubuntu it can be installed with ```sudo apt install qtcreator```.


