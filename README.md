# Crazyflie PC client [![CI](https://github.com/bitcraze/crazyflie-clients-python/workflows/CI/badge.svg)](https://github.com/bitcraze/crazyflie-clients-python/actions?query=workflow%3ACI)

This repository contains host applications for the Crazyflie, including the PC client (`cfclient`), headless client (`cfheadless`), firmware loader (`cfloader`), and ZMQ interface (`cfzmq`).
These applications provide graphical and command-line interfaces for firmware flashing, flight control, parameter configuration, real-time data logging and visualization, and more.
All applications are built on [`cflib`](https://github.com/bitcraze/crazyflie-lib-python).

## AIMSLab Mocap Flight Work

This fork also contains AIMSLab's OptiTrack/VRPN Crazyflie experiments. The
current, manually verified flight path is
[`mocap_manual_thrust_assisted_figure8.py`](mocap_manual_thrust_assisted_figure8.py):
manual takeoff and landing thrust, mocap-assisted X/Y and yaw hold, a 3 ft
height helper, and an assisted figure-8 with CSV and optional 3D-path output.

Start with the current operating guide:
[`MOCAP_MANUAL_FIGURE8.md`](MOCAP_MANUAL_FIGURE8.md).

Other root-level `mocap_*.py` files are calibration tools or experiments. They
are not interchangeable with the manual-thrust figure-8 workflow. Generated
flight logs and plots are local artifacts and are intentionally ignored by Git.

## Installation
See the [installation instructions](docs/installation/install.md) in the GitHub docs folder.

## Official Documentation

Check out the [Bitcraze crazyflie-client-python documentation](https://www.bitcraze.io/documentation/repository/crazyflie-clients-python/master/) on our website.

## Contribute
Go to the [contribute page](https://www.bitcraze.io/contribute/) on our website to learn more.

### Test code for contribution
Run the automated build locally to test your code

	python3 tools/build/build
