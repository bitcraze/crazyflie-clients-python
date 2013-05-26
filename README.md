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
instructions on how to install manually, see below.

## Windows

To install the Crazyflie PC client in Windows, download the installation
program from the [binary download
page](http://wiki.bitcraze.se/projects:crazyflie:binaries:index)."Crazyflie
client" will be added to the start menu.

## Mac OSX

### Using homebrew
**IMPORTANT NOTE**: The following will use
[[http://mxcl.github.io/homebrew/|homebrew]]and its own Python distribution. If
you have a lot of other 3rd party python stuff already running on your system
they might or might not affected of this.

1. Install homebrew

```
ruby -e "$(curl -fsSL https://raw.github.com/mxcl/homebrew/go)"
```
You also need to install Command Line Tools for Xcode or
[Xcode](https://developer.apple.com/xcode/) if you don't already have them
installed.

2. Install hombrew's Python installation
```
brew install python
```
This will also pull [pip](http://www.pip-installer.org/en/latest/), which we
will use later to install some Python modules that are not distributed through
homebrew.

3. Make sure the homebrew Python version is used system-wide
To do this we need to prepend this installation to our PYTHONPATH:
```
echo 'export PYTHONPATH=/usr/local/lib/python2.7/site-packages:$PYTHONPATH' >> ~/.bashrc
source ~/.bashrc
```

4. Install SDL for Python
```
brew install sdl sdl_image
sdl_mixer sdl_ttf portmidi
```

5. Install remaining dependencies
```
brew install pyqt
brew install libusb
brew install mercurial
pip install hg+http://bitbucket.org/pygame/pygame
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
port selfupdate
port upgrade outdated
```
2. Install dependencies. Note that there are quite a few, so this could take a
while:
```
port install libusb
port install py-pyusb-devel
port install py27-pyqt4
port install py27-pygame
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

Launching the GUI application
-----------------------------

To launch the GUI application in the source folder type:
```python bin/cfclient```

To launch the GUI after a systemwide installation, execute ```cfclient```. 

Dependencies
------------

The Crazyflie PC client has the following dependencies:
* Python 2.7
* pyGame
* PyUSB
* libusb
* PyQt4

Example commands to install these dependencies:

* Fedora (tested for 16 to 18):

```sudo yum install pygame pyusb PyQt4```

* Ubuntu (tested for 10.04 / 11.10 / 12.04):

```sudo apt-get install python2.7 python-usb python-pygame python-qt4```

* OpenSUSE (tested for 11.3):

```sudo zypper install python-pygame libusb python-usb```

Setting udev permissions
------------------------

The following steps make it possible to use the USB Radio without being root.

Note: If using a fresh Debian install, you may need to install sudo first
(executing exit command to exit from root shell first):

```su -
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
