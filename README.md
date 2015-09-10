# Crazyflie PC client [![Build Status](https://api.travis-ci.org/bitcraze/crazyflie-clients-python.svg)](https://travis-ci.org/bitcraze/crazyflie-clients-python)

The Crazyflie PC client enables flashing and controlling the Crazyflie.
There's also a Python library that can be integrated into other applications
where you would like to use the Crazyflie.

For more info see our [wiki](http://wiki.bitcraze.se/ "Bitcraze Wiki").

Installation
------------

## Linux

To install the Crazyflie PC client in Linux, you can run the setup script with:

```sudo setup_linux.sh```

This will install the Crazyflie PC client systemwide, create a udev entry for
the Crazyradio and setup the permissions so that the current user can use the
radio without root permissions after restarting the computer. For further
instructions on how to run from source see bellow.

## Windows

Follow these steps to install the binary distribution on Windows 7/8/10.
 - Download the latest release [here](https://github.com/bitcraze/crazyflie-clients-python/releases) (named cfclient-win32-install-*.exe)
 - Execute the installer. After the install the application will be added to the Start menu.
 - Install the Crazyradio drivers by following [these instructions](https://wiki.bitcraze.io/doc:crazyradio:install_windows_zadig)

Running from source
-------------------

## Windows (7/8/10)

Install dependencies. With Windows installers (tested using only 32-bit installs on 64-bit OS):
 - [Python 3.4](https://www.python.org/downloads/windows/) (make sure the pip component is selected when installing)
 - [PyQT4 for Python 3.4](http://www.riverbankcomputing.com/software/pyqt/download)
 - [NumPy for Python 3.4](http://sourceforge.net/projects/numpy/files/NumPy)
 - [SDL2](https://www.libsdl.org/download-2.0.php) (copy SDL2.dll into the client source folder)

Then install PyUSB, PyZMQ, PySDL2 and PyQtGraph using pip
```
C:\Users\bitcraze>\Python34\python.exe -m pip install pyusb==1.0.0b2 pyzmq pysdl2 pyqtgraph
```

Finally you run the client using the following command
```
\Python34\python bin\cfclient
```

**NOTE**: To use the Crazyradio you will have to [install the drivers](https://wiki.bitcraze.io/doc:crazyradio:install_windows_zadig)

## Mac OSX

### Using homebrew
**IMPORTANT NOTE**: The following will use
[Homebrew](http://brew.sh/) and its own Python distribution. If
you have a lot of other 3rd party python stuff already running on your system
they might or might not affected of this.

1. [Install the Command Line Tools](https://gist.github.com/derhuerst/1b15ff4652a867391f03#1--install-the-command-line-tools).

1. [Install Homebrew](https://gist.github.com/derhuerst/1b15ff4652a867391f03#2--install-homebrew).

1. Install Homebrew's Python3
    ```
    brew install python3
    ```

    This will also pull [pip3](https://pip.pypa.io/en/latest/), which we will use later to install some Python modules that are not distributed through Homebrew.

1. Install SDL for Python
    ```
    brew install sdl sdl2 sdl_image sdl_mixer sdl_ttf portmidi
    ```

1. Install PyQt

    If you already have pyqt installed for python2 you need to uninstall it first

    ```
    brew uninstall pyqt
    brew install pyqt --with-python3
    ```

1. Install remaining dependencies

    ```
    brew install libusb
    pip3 install pysdl2 pyusb pyqtgraph
    ```

1. You now have all the dependencies needed to run the client. From the source folder, run it with the following command:
    ```
    python bin/cfclient
    ```

### Using MacPorts
1. [Install MacPorts if needed](http://www.macports.org/install.php). Otherwise update your installation with:
    ```
    sudo port selfupdate
    sudo port upgrade outdated
    ```

1. Install dependencies. Note that there are quite a few, so this could take a while:
    ```
    sudo port install libusb python34 py34-pyusb py34-SDL2 py34-pyqt4
    ```
    To enable the plotter tab install pyqtgraph, this takes a lot of time:
    ```
    sudo port install py34-pyqtgraph
    ```
    You can now run the client from source with
    ```
    /opt/local/bin/python3.4 bin/cfclient
    ```

1. To make it easier to run MacPorts, add ```/opt/local/bin``` to your PATH variable.
    The MacPorts installer should take care of that, but take a look at
    ```~/.profile``` to make sure. If you have any issues it could be due to the
    libraries not getting picked up correctly. Fix that by setting
    ```DYLD_LIBRARY_PATH``` to ```/opt/local/lib``` in ```~/.profile```:
    ```
    export DYLD_LIBRARY_PATH=/opt/local/lib
    ```

1. Now you're good to go! Run the client from the source folder with the
    following command:
    ```
    python2.7 bin/cfclient
    ```

## Linux

### Launching the GUI application

To launch the GUI application in the source folder type:
```python bin/cfclient```

To launch the GUI after a systemwide installation, execute ```cfclient```. 

### Dependencies

The Crazyflie PC client has the following dependencies:

* Python 3.4
* PyUSB
* libusb 1.X (works with 0.X as well)
* PyQtGraph
* ZMQ
* PyQt4

Example commands to install these dependencies:

* Fedora (tested for 16 to 18):

    ```sudo yum install pysdl2 pyusb PyQt4```

* Ubuntu (15.04):

    ```sudo apt-get install python3 python3-pip python3-pyqt4 python3-zmq python3-pyqtgraph
    sudo pip3 install pyusb==1.0.0b2```

* OpenSUSE (tested for 11.3):

    ```sudo zypper install python-pysdl2 libusb python-usb```

### Setting udev permissions

The following steps make it possible to use the USB Radio without being root.

Note: If using a fresh Debian install, you may need to install sudo first
(executing exit command to exit from root shell first):

```
su -
apt-get install sudo
```

Now, with sudo installed, you should be able to do the following commands

```
sudo groupadd plugdev
sudo usermod -a -G plugdev <username>
```

Create a file named ```/etc/udev/rules.d/99-crazyradio.rules``` and add the
following:
```
SUBSYSTEM=="usb", ATTRS{idVendor}=="1915", ATTRS{idProduct}=="7777", MODE="0664", GROUP="plugdev"
```

Restart the computer and you are now able to access the USB radio dongle
without being root.
