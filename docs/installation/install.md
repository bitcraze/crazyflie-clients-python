---
title: Installation
page_id: install
---

## Requirements

This project requires Python 3.10+.

> **Recommendation**: Use a Python virtual environment to isolate dependencies. See the [official Python venv documentation](https://docs.python.org/3/library/venv.html) for setup instructions.

## Platform Prerequisites

### Ubuntu/Linux

From a fresh Ubuntu 20.04 system and up, running the client from source requires git, pip and libraries for the Qt GUI:

```bash
sudo apt install git python3-pip libxcb-xinerama0 libxcb-cursor0
pip3 install --upgrade pip
```

#### Setting udev permissions

Using Crazyradio on Ubuntu/Linux requires that you set udev permissions. See the cflib [installation guide](https://www.bitcraze.io/documentation/repository/crazyflie-lib-python/master/installation/usb_permissions/) for more information.

### Windows

Install Python 3 using the official Python build from [python.org](https://python.org). Make sure to check the "add to path" checkbox during installation. Verify the installation by opening a cmd or PowerShell terminal:

```bash
python --version
pip --version
```

Upgrade pip:
```bash
pip install --upgrade pip
```

Install Git from the [official Git website](https://git-scm.com/). Make sure it is in PATH, which can be verified with:
```bash
git --version
```

If you're using Python 3.13, you need to install [Visual Studio](https://visualstudio.microsoft.com/downloads/). During the installation process, you only need to select the Desktop Development with C++ workload in the Visual Studio Installer.

#### Install Crazyradio drivers

To use Crazyradio you will need to [install the drivers](https://www.bitcraze.io/documentation/repository/crazyradio-firmware/master/building/usbwindows/).

### macOS

The client requires macOS 11 (Big Sur) or more recent. It works on both x86 and Apple Silicon Macs.

The client works with both the Apple-provided Python 3 (as long as it is Python >= 3.10) and with Python installed via Homebrew.

### Raspberry Pi

The client requires Raspberry Pi Trixie or more recent. On Raspberry Pi Trixie it is required to create a Python venv to install the client. The client GUI works on both the Raspberry Pi 4 and 5, but it is recommended to be used on a Raspberry Pi 5.

USB permissions need to be set as described above for Ubuntu/Linux.

## Installation Methods

### From PyPI (Recommended)

If you plan to use the client to control the Crazyflie, we highly recommend installing the latest release using pip, as this is well tested and stable:

```bash
pip install cfclient
```

For macOS specifically:
```bash
python3 -m pip install cfclient
```

The client can then be launched from a console with `cfclient` or `python3 -m cfclient.gui`.

### From Source (Development)

If you are planning to do development work with the cfclient, install from source.

#### Clone the repository
```bash
git clone https://github.com/bitcraze/crazyflie-clients-python
cd crazyflie-clients-python
```

#### Install the client from source

For basic installation:
```bash
pip install -e .
```

For development (includes additional tools):
```bash
pip install -e .[dev]
```

**Note**: Avoid running pip with sudo, as this would install dependencies system-wide and could cause compatibility problems. If pip requests administrator password, you should run the command with `--user` (for example `python3 -m pip install --user -e .`). This should not be required on modern Python distributions though since the `--user` flag seems to be the default behavior.

## Development Tools (Optional)

### Pre-commit hooks
If you want help maintaining Python coding standards, you can install hooks that verify your style at commit time:

```bash
pip install pre-commit
cd crazyflie-clients-python
pre-commit install
pre-commit run --all-files
```

This will run the lint checkers defined in `.pre-commit-config-yaml` on your proposed changes and alert you if you need to change anything.

### Working with the GUI .ui files

You can edit the .ui files for the GUI with QtCreator. For Windows and Mac you can download the Qt development kit from the [Qt website](https://www.qt.io/download-open-source/). On Linux QtCreator is usually available as package, for example on Ubuntu it can be installed with ```sudo apt install qtcreator```.

### Debugging the client from an IDE

It is convenient to be able to set breakpoints, examine variables and so on from an IDE when debugging the client. To get
this to work you need to run the python module `cfclient.gui` as the debug target in the IDE.

In VSCode for instance, the launch.json should look something like this:

``` json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Crazyflie client",
            "type": "python",
            "request": "launch",
            "module": "cfclient.gui"
        },
    ]
}
```

As noted earlier, it is common that work on the client also involve work in the [crazyflie-lib-python](https://github.com/bitcraze/crazyflie-lib-python).
The `launch.json` documented here can also be used in the crazyflie lib project to debug lib-related code.
