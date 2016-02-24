Warning: Generating windows executable is not working yet with Python3. This is
work in progress in issue #207. Any help is apreciated!

Howto generate cfclient Windows installer
=========================================

The windows installer is generated using the NSIS installer system. The steps
to generate the distribution are:
 - Clone a clean copy of the repos
 - Generate and test Windows executable
 - Generate the installer script
 - Build the installer

All the procedure has to be run on Windows. Tested on Windows 7. A release
version should have the right version written to setup.py (ie. not a
development version).

Prerequisites
-------------
Should be all from source install + the following:
 - [Python 3.4](https://www.python.org/downloads/windows/) (make sure the pip component is selected when installing)
 - [Nsis 2.46](http://nsis.sourceforge.net/Download)
 - [GIT](https://git-scm.com/download/win)

Install the following with pip:
```
\Python34\python.exe -m pip install jinja2 py2exe
```

Procedure
---------
Clone the cfclient repos in a new folder and update it to the (tagged) version you
want to generate.

Locate MSVCP90.dll in your pc and copy it in the source folder. There may be many
version, the good one is 9.0.21022.8 and has a size of 555kB. If not installed
read py2exe doc to download the Microsoft visual C++ 2008 redistributable package.

Run in a command line window:
> cd <path_to_crazyflie_pc_client>
> setup.py py2exe

Test and validate the new executable by running:
> dist\cfclient

Generate the installer configuration:
> cd win32install
> generate_nsis.py
 Found 516 files in 41 folders to install.
 Cfclient version 2013.4.1

Finally open the win32install folder in the file explorer. Right click on
cfclient.nsi, chose "Compile NSIS script (choose compressor)". The NSIS
compiler opens, Select "LZMA (solid)" compressor. After a little while
the script is compiled and "cfclient-win32-install-version.exe" is created
in the script folder.
