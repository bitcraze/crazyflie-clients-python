# Crazyflie PC client [![Build Status](https://api.travis-ci.org/bitcraze/crazyflie-clients-python.svg)](https://travis-ci.org/bitcraze/crazyflie-clients-python) [![Build status](https://ci.appveyor.com/api/projects/status/u2kejdbc9wrexo31?svg=true)](https://ci.appveyor.com/project/bitcraze/crazyflie-clients-python)


The Crazyflie PC client enables flashing and controlling the Crazyflie.
It implement the user interface and high-level control (for example gamepad handling).
The communication with Crazyflie and the implementation of the CRTP protocol to control the Crazflie is handled by the [cflib](https://github.com/bitcraze/crazyflie-lib-python) project.

For more info see our [wiki](http://wiki.bitcraze.se/ "Bitcraze Wiki").

Running from source
-------------------

The Crazyflie client requires [cflib](https://github.com/bitcraze/crazyflie-lib-python).
If you want to develop with the lib too, follow the cflib readme to install it.

## Windows (7/8/10)

Running from source on Windows is tested using the [miniconda](http://conda.pydata.org/miniconda.html) python distribution. It is possible to run from any distribution as long as the required packages are installed. Building the windows installer requires Python 3.4 (because ```py2exe``` is not distributed for Python 3.5+ yet). The following instructions assumes **Miniconda 32-bit** is installed.

**Note on python version**: Building the windows executable and installer requires Python 3.4. The client has mostly been tested using Python 32Bit but should work on python 64Bits as well. If you are not interested about building the windows installer, just by running the client, you can run on more recent version of python.

Open a command line windows and move to the crazyflie clients folder (the exact command depends of where the project is cloned):
```
cd crazyflie-clients-python
```

Create and activate a Python 3.4 environment with pyqt5:
```
conda create -y -n cfclient python=3.4 pyqt=5
activate cfclient
```

Download the 32bits SDL2.dll windows library:
```
python tools\build\prep_windows
```

Install the client in development mode:
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

**NOTE:** To use Crazyradio you will have to [install the drivers](https://wiki.bitcraze.io/doc:crazyradio:install_windows_zadig)

### Working on the client with PyCharm

Pycharm is an IDE for python. Any IDE or development environment will work for the Crazyflie client. The key here is to use the miniconda python interpreter from the environment created earlier, this can be applied to other development environment.

To work on the Crazyflie firmware with Pycharm, install pycharm comunity edition and open the Crazyflie client folder in it. Then:

 - Go to file>settings
 - Go to "Project: crazyflie-clients-python" > Project interpreter
 - Press the cog on the top right, beside "Project interpreter" and click "add local"
 - Locate the interpreter under \<miniconda_root\>\env\cfclient\python.exe (for example C:\Miniconda3\envs\cfclient\python.exe, see [screenshoot](https://wiki.bitcraze.io/_media/doc:crazyflie:client:pycfclient:cfclient_pycharm_windows_miniconda.png?t=1483971038&w=500&h=358&tok=9e4a0c))
 - Validate with OK two times
 - Open the bin/cfclient file in the pycharm editor and then "Run>Run 'cfclient'" will start the client

You are now able to edit and debug the python code. you can edit the .ui files for the GUI with QtCreator. You can the Qt development kit from the [Qt website](https://www.qt.io/download-open-source/) and open the .ui files in QtCreator.

### Creating Windows installer

When you are able to run from source, you can build the windows executable and installer.

First build the executable
```
python setup.py py2exe
```
**NOTE:** The first time the previous command will fail complaining about a ```PyQt5\uic\port_v2```
folder. Remove this folder with ```rmdir \Q \S path\to\PyQt5\uic\port_v2```,
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

    ```
    brew install pyqt5
    ```

1. Install remaining dependencies

    ```
    brew install libusb
    ```

1. If you want to develop on cflib as well, install cflib from https://github.com/bitcraze/crazyflie-lib-python

1. Install cfclient to run it from source. From the source folder run:
    ```
    pip3 install -e .
    ```

1. You now have all the dependencies needed to run the client. From the source folder, run it with the following command:
    ```
    cfclient
    ```

## Linux

### Launching the GUI application

If you want to develop with the lib, install cflib from https://github.com/bitcraze/crazyflie-lib-python

Cfclient requires Python3, pip and pyqt5 to be installed using the system package manager. For example on Ubuntu/Debian:
```
sudo apt-get install python3 python3-pip python3-pyqt5
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

### Setting udev permissions

Using Crazyradio on Linux requires that you set udev permissions. See the cflib
[readme](https://github.com/bitcraze/crazyflie-lib-python#setting-udev-permissions)
for more information.
