# Crazyflie PC client [![Build Status](https://api.travis-ci.org/bitcraze/crazyflie-clients-python.svg)](https://travis-ci.org/bitcraze/crazyflie-clients-python) [![Build status](https://ci.appveyor.com/api/projects/status/u2kejdbc9wrexo31?svg=true)](https://ci.appveyor.com/project/bitcraze/crazyflie-clients-python)


The Crazyflie PC client enables flashing and controlling the Crazyflie.
There's also a Python library that can be integrated into other applications
where you would like to use the Crazyflie.

For more info see our [wiki](http://wiki.bitcraze.se/ "Bitcraze Wiki").

Note. The project is currently being reorganized, which means that This
documentation might become inacurate. You can track the reorganisation work in
the ticket #227.

Running from source
-------------------

The Crazyflie client requires [cflib](https://github.com/bitcraze/crazyflie-lib-python).
Follow the cflib readme to install it.

## Windows (7/8/10)

Running from source on Windows is tested using the [miniconda](http://conda.pydata.org/miniconda.html) python distribution. It is possible to run from any distribution as long as the required packages are installed. Building the windows installer requires Python 3.4 (because ```py2exe``` is not distributed for Python 3.5 yet). The following instructions assumes **Miniconda 32-bit** is installed.

Open a command line windows and move to the crazyflie clients folder (the exact command depends of where the project is cloned):
```
cd crazyflie-clients-python
```

Create and activate a Python 3.4 environment with numpy pyqt and pyqtgraph from conda (it is the packages we cannot easily install with pip):
```
conda create -y -n cfclient python=3.4 numpy=1.10.1 pyqt pyqtgraph
activate cfclient
```

Download the SDL2.dll windows library:
```
python tools\build\prep_windows
```

Install the client in development mode:
```
pip install -e .[dev]
```

You can now run the clients:
```
cfclient
cfheadless
cfloader
cfzmq
```

**NOTE:** To use the Crazyradio you will have to [install the drivers](https://wiki.bitcraze.io/doc:crazyradio:install_windows_zadig)

### Creating Windows installer

When you are able to run from source, you can build the windows executable and installer.

First build the executable
```
python setup.py py2exe
```
**NOTE:** The first time the previous command will fail complaining about a ```PyQt4\uic\port_v2```
folder. Remove this folder with ```rmdir \Q \S path\to\PyQt4\uic\port_v2```,
you can copy-paste the folder path from the py2exe error message.


Now you can run the client with ```dist\cfclient.exe```.

To generate the installer you need [nsis](http://nsis.sourceforge.net/) installed and in the path. If you
are a user of [chocolatey](https://chocolatey.org/) you can install it with ```choco install nsis.portable -version 2.50```,
otherwise you can just download it and install it manually.

To create the installer:
```
python win32install\generate_nsis.py
makensis win32install\cfclient.nsi
```

## Mac OSX

### Using homebrew
**IMPORTANT NOTE**: The following will use
[Homebrew](http://brew.sh/) and its own Python distribution. If
you have a lot of other 3rd party python stuff already running on your system
they might or might not be affected by this.

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
    pip3 install pysdl2 pyusb pyqtgraph appdirs
    ```

1. Install cflib from https://github.com/bitcraze/crazyflie-lib-python

1. Install cfclient to run it from source. From the source folder run:
    ```
    pip3 install -e .
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
    sudo port install libusb python34 py34-SDL2 py34-pyqt4 py34-pip
    ```
    To make the MacPorts ```python``` and ```pip``` the default commands:
    ```
    sudo port select --set python python34
    sudo port select --set python3 python34
    sudo port select --set pip pip34
    ```
    To install ```pyusb``` from ```pip```, use:
    ```
    sudo pip install pyusb appdirs
    ```
    To enable the plotter tab install pyqtgraph, this takes a lot of time:
    ```
    sudo port install py34-pyqtgraph
    ```
    Install cflib from https://github.com/bitcraze/crazyflie-lib-python

    Install cfclient to run it from source. From the source folder run:
    ```
    pip install -e .
    ```
    You can now run the client from the source folder with
    ```
    python bin/cfclient
    ```
    Or, if you did not run the ```port select``` command to set the MacPorts ```python``` as the default, use:
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

## Linux

### Launching the GUI application

Install cflib from https://github.com/bitcraze/crazyflie-lib-python

Install cfclient to run it from source. From the source folder run (to install
for your user only you can add ```--user``` to the command):
```
pip3 install -e .
```
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
* appdirs

Example commands to install these dependencies:

* Fedora:

    ```
    TODO Please contribute
    ```


* Ubuntu (14.04):

    ```
    sudo apt-get install python3 python3-pip python3-pyqt4 python3-zmq
    pip3 install pyusb==1.0.0b2
    pip3 install pyqtgraph appdirs
    ```

* Ubuntu (15.04):

    ```
    sudo apt-get install python3 python3-pip python3-pyqt4 python3-zmq python3-pyqtgraph
    sudo pip3 install pyusb==1.0.0b2
    sudo pip3 install appdirs
    ```

* OpenSUSE:

    ```
    TODO Please contribute
    ```

### Setting udev permissions

Using Crazyradio on Linux requires that you set udev permissions. See the cflib
[readme](https://github.com/bitcraze/crazyflie-lib-python#setting-udev-permissions)
for more information.
