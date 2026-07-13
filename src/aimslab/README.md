# AIMSLab Docs

> Current Crazyflie manual-thrust figure-8 work is documented in the repository
> root: [`MOCAP_MANUAL_FIGURE8.md`](../../MOCAP_MANUAL_FIGURE8.md). This file
> preserves broader lab and historical project notes.

**Overview:**
This a repository containing most of the code written by me over summer 25 for the additive manufacturing REU with Dr. Baidya and Dr. Aqlan. The repo contains links to the ROS2 package needed to receive mocap data on the Starling 2, how to install the VRPN library to receive mocap data, the python instructions to get the crazyflie flying using mocap and the 3D print anomaly detection model I made.

The VRPN library is a library that I used to **receive** the streaned pose data from Optitrack, sending that data to a drone's FCU differs per the drone's architecture. The docs below provide the method used for the crazyflie, m500 and starling 2. Instructions to build the VRPN library are below. If you are going to develop using the library I encourage you to look at the docs here:[ https://sites.google.com/site/vrgeeks/vrpn/tutorial-use-vrpn](url) and to read my code to get a better undestanding of how it works. I only use the vrpn_tracker and vrpn_connection objects in my code. 

Motive-stream is a project I made which will use VRPN to receive the motive stream data and send it to any device on the AIMSnet network via UDP. This project was made for streaming a single drone's pose at a time, however if you were to open multiple terminals and run different pose-streams, it will work and effectively broadcast multiple drone poses.

The crazyflie-clients folder is **Just my code and examples**. That is to say you need to download and follow the crazyflie setup instructions to use my code. I have included the setup instructions below but understand this code will **NOT** work out of the box due to the nature of crazyflie's SDK.

_________________
# Motive Stream Docs

Using stream files in src:

1. To make a new streaming file copy the motive-pose-stream file and edit the rigid body name in this line: ```const std::string tracker_name = "crazyflie";``` to match the rigid body you are tracking. From there you can make any desired changes to the file(i.e chage the serializiaton format, etc.)
2. To change the ip and ports you are sending and receiving from, find the line:
 ```
std::string serverIp = "127.0.0.1";
UDPConnection udpConnection(serverIp, 10443, 10444);
```
To change the IP and ports to what you need.

3. Go to the top of the Cmake file and change the the project name to the desired name for your binary file and change the SOURCES variable to use the specified streaming file.
4. Follow the instructions below to build your file and the binary will be in the bin folder, which can be run as shown below. (./bin/<binary_file>)

motive-pose-stream.cpp (this is the original stream that Ricky created)

Be aware of the data types in Messages.hpp

Instructions to build stream files:

```
cd motive-stream
mkdir build
cd build
cmake ..
make
```
P.S (after instantaiting the make files, you can also build from anywhere by running: ```cmake --build <path/to/build-dir>/build```

then simply exec the binary:

E.g. ```./bin/motive-pose-stream```

_________________

# BUILDING THE VRPN Library (Linux Only)
[https://github.com/vrpn/vrpn](url)

To get the vrpn libraries do the following: 

```
cd motive-stream
sudo apt-get install libusb-1.0-0-dev libboost-all-dev
mkdir dependencies && cd dependencies
git clone https://github.com/vrpn/vrpn.git && cd vrpn
mkdir build && cd build
cmake ..
make -j$(nproc) 
sudo make install  
```
Unfortunately, I was only able to get the library working if you install the object files system wide. That may be an improvement to make in the future. 
__________________

# Current Crazyflie Mocap Flight Status

For the current manually verified OptiTrack/VRPN Crazyflie flight procedure,
read [`MOCAP_MANUAL_FIGURE8.md`](../../MOCAP_MANUAL_FIGURE8.md). It documents
the low-level commander workflow: `R`, then `T`, then `F` after the 3 ft helper
reports ready. [`AIMSLAB_AUTONOMY_RUNBOOK.md`](../../AIMSLAB_AUTONOMY_RUNBOOK.md)
remains the historical HLC and calibration reference. `mocap-extpose-figure8.py`
is not a powered-flight replacement for the manual-thrust workflow.

# CrazyFlie Setup
***Disclaimer: This script has only been tested in Ubuntu so Windows will most likely not work***
1. Install From Source the cfclient: [https://www.bitcraze.io/documentation/repository/crazyflie-clients-python/master/installation/install/](url)
2. In the crazyflie-clients-python directory, run:```cd src``` and ```mkdir aimslab```
3. Transfer all the crazyflie files from this repo into the aimslab directory you just made
4. If you haven't already make a python venv in the crazyflie-clients-python directory using ```python3 -m venv .venv```, activate you venv using: ```source .venv/bin/activate```and run ```pip install -r requirements.txt``` to install dependencies.
5. If for some reason pip installing from the requirements.txt fails, you can use ```pip install motioncapture cflib scipy numpy``` for all necessary dependencies.

To connect to the crazyflie make sure you use theh crazyradio dongle

If you need to dowload the firmware follow these instructions:

  Download the firmware here to change the crazyflie files: https://www.bitcraze.io/documentation/tutorials/getting-started-with-development/
  
  Make sure to download the dependencies to build the firmware:
  https://www.bitcraze.io/documentation/repository/crazyflie-firmware/master/building-and-flashing/build/#dependencies
_______________

# m500 Docs:

The modal m500 should automatically be on AIMSnet as a device
To ssh into the drone, use ssh root@192.168.1.83, the password is default for modalai: oelinux123

The m500 uses ROS1 so my package will not work. This drone will definetely pose the biggest challenge since it is deprecated. The modalai docs are hard to find for this specific drone. However, it should still absolutely be possible to use this drone to fly with optitrack. Additiaonlly, there already exists a ros1 version of VRPN client package which should make life alot easier. Here's the package: [https://github.com/ros-drivers/vrpn_client_ros](url). The idea for getting it to fly with optitrack should be same as the Starling, just the implementation will be different. 

These are the modalAi docs:
https://docs.modalai.com/
______________

# Starling 2 Docs:
To gain access to the firmware use adb shell with a usb cable or use ssh.
To ssh into the drone, use ssh root@192.168.1.151, the password is default for modalai: oelinux123. The drone is already on AIMSnet so you don't have to worry about setting that up. To ssh into it, make sure your device is also on AIMSnet.

The drone box contains, the battery, a power module for the drone to use instead of batteries, the drone and adapters for the XT connections
The charger is seperate from the drone and is in the cabinet in the support lab. It is in a white box in the top left of the cabinet. BEFORE CHARGING/USING ANY OF THE BATTERIES MAKE SURE TO FOLLOW CONVENTIONS FOR CHARGING/USING LiPo/LiIon BATTERIES.

To view the camera overlays of the drone make sure you are on the AIMSnet wifi. Then open your browser and type in the voxls ip (192.168.1.151). You should see the voxl portal with info on the starling's current state. More info on the portal can be found in Modlai docs.

The Ros2 pkg to send vrpn stream info onto starling is here: [https://github.com/RickyMetral/optitrack](url). It should already be on the starling 2 drone in a workspace named aimslab_ws in the root dir. The rest of the docs for the package will be in the repo. Please refer to ModalAi docs before beginning development on the drone. The learning curve is big, but very necessary. Start with the developer bootcamp in their documentation and go from there. 

For the starling to correctly fuse the motive pose estimates, you must first restart the ekf2 estimator while actively sending the pose data. Then you have to wait for the EKF2 to converge with the position it is receiving. I wasn't able to fully test this with VIO so you may have to turn VIO off for the drone to accurately use the motive localization. The voxl technical docs will specify how to do so, but it should be as simple as turning off all the required services by vio. (Ex: systemctl stop voxl-qvio). 

**Note:**
As of August 1, the drone is not arming because QGC cannot detect the drone's voltage for some reason. The ELRS controller is already bound to the drone, but it is not passing its preflight checks because of the voltage issue. 

View modalai techincal docs:
https://docs.modalai.com/mavlink/
