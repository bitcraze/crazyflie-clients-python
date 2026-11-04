# Crazyflie PC client [![CI](https://github.com/bitcraze/crazyflie-clients-python/workflows/CI/badge.svg)](https://github.com/bitcraze/crazyflie-clients-python/actions?query=workflow%3ACI)

This repository contains host applications for the Crazyflie, including the PC client (`cfclient`), headless client (`cfheadless`), firmware loader (`cfloader`), and ZMQ interface (`cfzmq`).
These applications provide graphical and command-line interfaces for firmware flashing, flight control, parameter configuration, real-time data logging and visualization, and more.
All applications are built on [`cflib`](https://github.com/bitcraze/crazyflie-lib-python).

## Installation
See the [installation instructions](docs/installation/install.md) in the GitHub docs folder.

## Official Documentation

Check out the [Bitcraze crazyflie-client-python documentation](https://www.bitcraze.io/documentation/repository/crazyflie-clients-python/master/) on our website.

## Contribute
Before you open a pull request, please read our [General guidelines for code contributions](https://www.bitcraze.io/development/contribute/general-guidelines/).

For other ways to contribute, see the [contribute page](https://www.bitcraze.io/development/contribute/).

### Test code for contribution
Run the automated build locally to test your code

	python3 tools/build/build
