# Crazyflie PC client

The Crazyflie PC client enables flashing and controlling the Crazyflie.
There's also a Python library that can be integrated into other applications
where you would like to use the Crazyflie.

For more info see our [wiki](http://wiki.bitcraze.se/ "Bitcraze Wiki").

Installation
------------

## Linux

To install the Crazyflie PC client in Linux, you can run the setup script with:

```sudo setup.sh```

This will install the Crazyflie PC client systemwide, create a udev entry for
the Crazyradio and setup the permissions so that the current user can use the
radio without root permissions after restarting the computer. For further
instructions on how to run from source see bellow.

## Windows

To install the Crazyflie PC client in Windows, download the installation
program from the [binary download
page](http://wiki.bitcraze.se/projects:crazyflie:binaries:index)."Crazyflie
client" will be added to the start menu.

Running from source
-------------------

## Windows

Install dependencies. With Windows installers (tested with 32Bit versions):
 - Python 2.7 (https://www.python.org/downloads/windows/)
 - PyQT4 for Python 2.7 (http://www.riverbankcomputing.com/software/pyqt/download)
 - Scipy for Python 2.7 (http://sourceforge.net/projects/scipy/files/scipy/)
 - PyQTGraph (http://www.pyqtgraph.org/)

Python libs (to be install by running 'setup.py install'):
 - PyUSB (https://github.com/walac/pyusb/releases)
 - pysdl2 (https://bitbucket.org/marcusva/py-sdl2/downloads)

Download SDL2 from http://libsdl.org/download-2.0.php and copy SDL2.dll in the
crazyflie-clients-python folder.

Run with:
```
C:\Python27\python bin\cfclient
```

## Mac OSX

### Using homebrew
**IMPORTANT NOTE**: The following will use
[Homebrew](http://brew.sh/) and its own Python distribution. If
you have a lot of other 3rd party python stuff already running on your system
they might or might not affected of this.

1. [Install the Command Line Tools](https://gist.github.com/derhuerst/1b15ff4652a867391f03#1--install-the-command-line-tools).

2. [Install Homebrew](https://gist.github.com/derhuerst/1b15ff4652a867391f03#2--install-homebrew).

3. Install Homebrew's Python
```
brew install python
```
This will also pull [pip](https://pip.pypa.io/en/latest/), which we
will use later to install some Python modules that are not distributed through
Homebrew.

3. Make sure the homebrew Python version is used system-wide
To do this we need to prepend this installation to our PYTHONPATH:
```
echo 'export PYTHONPATH=/usr/local/lib/python2.7/site-packages:$PYTHONPATH' >> ~/.bashrc
source ~/.bashrc
```

4. Install SDL for Python
```
brew install sdl sdl2 sdl_image
sdl_mixer sdl_ttf portmidi
```

5. Install remaining dependencies
```
brew install pyqt
brew install libusb
brew install mercurial
pip install pysdl2
pip install pyusb
```

6. You now have all the dependencies needed to run the client. From the source
folder, run it with the following command:
```
python bin/cfclient
```

### Using MacPorts
1. [Install MacPorts if needed](http://www.macports.org/install.php). Otherwise
update your installation with:
```
sudo port selfupdate
sudo port upgrade outdated
```

2. Install dependencies. Note that there are quite a few, so this could take a
while:
```
sudo port install libusb python27 py27-pyusb py27-SDL2 py27-pyqt4
```
To enable the plotter tab install pyqtgraph, this takes a lot of time:
```
sudo port install py27-pyqtgraph
```
You can now run the client from source with
```
/opt/local/bin/python2.7 bin/cfclient
```

3. To make it easier to run MacPorts, add ```/opt/local/bin``` to your PATH variable.
The MacPorts installer should take care of that, but take a look at
```~/.profile``` to make sure. If you have any issues it could be due to the
libraries not getting picked up correctly. Fix that by setting
```DYLD_LIBRARY_PATH``` to ```/opt/local/lib``` in ```~/.profile```:
```
export DYLD_LIBRARY_PATH=/opt/local/lib
```

4. Now you're good to go! Run the client from the source folder with the
following command:
```
python2.7 bin/cfclient
```

## Linux

###Launching the GUI application

To launch the GUI application in the source folder type:
```python bin/cfclient```

To launch the GUI after a systemwide installation, execute ```cfclient```. 

###Dependencies

The Crazyflie PC client has the following dependencies:

* Python 2.7
* PySdl2
* PyUSB
* libusb
* PyQt4

Example commands to install these dependencies:

* Fedora (tested for 16 to 18):

```sudo yum install pysdl2 pyusb PyQt4```

* Ubuntu (tested for 10.04 / 11.10 / 12.04):

```sudo apt-get install python2.7 python-usb python-pysdl2 python-qt4```

* OpenSUSE (tested for 11.3):

```sudo zypper install python-pysdl2 libusb python-usb```

###Setting udev permissions

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
