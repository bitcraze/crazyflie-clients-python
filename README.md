#Hover Mode
This extends the functionality of the original crazy flie firmware by adding a hover mode.

**Warning:** the code is experimental and far from a final state. It is not really being 
maintained either, but I hope that someone might find it useful.

You will also need the modified [pc client](https://bitbucket.org/bitcraze/crazyflie-pc-client "pc-client OMWDUNKLEY").


See the [original forum post](http://forum.bitcraze.se/viewtopic.php?f=6&t=523&p=3351#p3351 "Original Post")


Hey guys,

some of you might have seen my post here: 
http://forum.bitcraze.se/viewtopic.php?f=6&t=331&start=10#p2405

A while back I was experimenting with using the barometer to implement a hover mode. 
It worked relatively well in stable pressure conditions. I never released the code 
because I wanted to clean it up and do it properly (EKF, etc). However Ive not got 
around to doing that yet so I decided to expose the code. Yes its messy, yes lots 
is redundant, yes lots is suboptimal, but yes it works too:). I not going to 
continue to develop this fork (maybe some minor bug fixes and gui updates), but 
someone might find it useful.

##How to use:
*Set up your hover button from the GUI. By default for PS3_Mode_1 its the L1 button of the PS3 controller.
* When you press this button, it sets the target altitude as the current altitude. 
* Hold the button to remain in hover mode.
* While in hover mode, the throttle can be used to change the target altitude. Eg holding throttle up for a second raises it about a meter.
* Release the button to return to manual mode.
* Next time you enter hover mode, the target altitude is reset to the current altitude again.
* **A good tip:** Let go of the throttle immediately after entering hover mode. Its very easy to forget that one is holding it up and the flie will continue to rise.

##Some details:
The ms5611 driver has been partly rewritten to enable pressure measurements at 50-100hz.

I wrote the code a while ago, but if I remember correctly it sort of works as follows:

All pressure readings are converted to an altitude above sea level.
When entering hover mode, we set the target altitude. 

We can then define a PID controller that should take the flie from its current 
altitude to the target altitude. The P part is just the difference, eg 1 meter too high.
For the D term we use the vertical speed...here the code is ugly. First one needs to 
compute the vertical acceleration, then subtract gravity. This vertical acceleration 
is then integrated to get a speed estimate. To stop it accumulating error forever, 
it converges to the speed estimate from the barometer. This is also computed in a 
non mathematical way: some factor * (super_smoothed_altitude-smoothed_altitude).
The I term is just the integrated error - and is very very very important as it 
makes up for the voltage drop. The P and D term are reset every time hover mode is 
entered, and the I term is only reset when you start charging the flie. The default 
I value right now is set up to be a pretty good value for a stock flie at 80% battery. 
The default values takes around 1-2 to converge on a flie with a depleted battery 
during which time the flie might oscillate within a meter range or so.

Note that hover mode only works well in pressure stable environments. Trying to hover 
with people opening/closing windows/doors or during a thunderstorm does not work very well!

Here are videos of it working:

[StaticExample](http://www.youtube.com/watch?v=aRsvPyRQaFA "Youtube video")
[ManeuoveringExample](http://www.youtube.com/watch?v=0oYzMVUKZKI "Youtube video")



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
