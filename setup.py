#!/usr/bin/env python

from distutils.core import setup
import glob
import os
import sys
from subprocess import Popen, PIPE


#Recover version from Git
try:
    process = Popen(["git", "describe", "--tags"], stdout=PIPE)
    (output, err) = process.communicate()
    exit_code = process.wait()
except OSError:
    raise Exception("Cannot run git: Git is required to generate packages!")

VERSION = output.strip()


toplevel_data_files = ['README.md', 'LICENSE.txt']

#Platform specific settings
if sys.platform.startswith('win32'):
    try:
        import py2exe
    except ImportError:
        print("Warning: py2exe not usable")

    setup_args=dict(
        console=[{
            "script": 'bin/cfclient',
            "icon_resources": [(1, "bitcraze.ico")]
        }],
        options={"py2exe": {"includes": ["sip", "PyQt4",
                                         "cfclient.ui.widgets",
                                         "cflib.bootloader.cloader",
                                         "cfclient.ui.toolboxes.*",
                                         "cfclient.ui.*",
                                         "cfclient.ui.tabs.*",
                                         "cfclient.ui.widgets.*",
                                         "cfclient.ui.dialogs.*"],
                            "excludes": ["AppKit"],
                            "skip_archive": True}})

    toplevel_data_files.append('SDL2.dll')
else:
    setup_args=dict(
        scripts=['bin/cfclient', 'bin/cfheadless'])

#Initial parameters
setup_args=dict(name='cfclient',
      description='Bitcraze Cazyflie nano quadcopter client',
      version=VERSION,
      author='Bitcraze team',
      author_email='contact@bitcraze.se',
      url='http://www.bitcraze.se',
      package_dir={'': 'lib'},
      packages=['cfclient', 'cfclient.ui', 'cfclient.ui.tabs',
                'cfclient.ui.toolboxes', 'cfclient.ui.widgets',
                'cfclient.utils', 'cfclient.ui.dialogs', 'cflib',
                'cflib.bootloader', 'cflib.crazyflie', 'cflib.drivers',
                'cflib.utils', 'cflib.crtp'],
      data_files=[('', toplevel_data_files),
                  ('cfclient/ui',
                   glob.glob('lib/cfclient/ui/*.ui')),
                  ('cfclient/ui/tabs',
                   glob.glob('lib/cfclient/ui/tabs/*.ui')),
                  ('cfclient/ui/widgets',
                   glob.glob('lib/cfclient/ui/widgets/*.ui')),
                  ('cfclient/ui/toolboxes',
                   glob.glob('lib/cfclient/ui/toolboxes/*.ui')),
                  ('cfclient/ui/dialogs',
                   glob.glob('lib/cfclient/ui/dialogs/*.ui')),
                  ('cfclient/configs',
                   glob.glob('lib/cfclient/configs/*.json')),
                  ('cflib/cache',
                   glob.glob('lib/cflib/cache/*.json')),
                  ('cfclient/configs/input',
                   glob.glob('lib/cfclient/configs/input/*.json')),
                  ('cfclient/configs/log',
                   glob.glob('lib/cfclient/configs/log/*.json')),
                  ('cfclient',
                   glob.glob('lib/cfclient/*.png'))],
      **setup_args)



#Fetch values from package.xml when using catkin
if os.getenv('CATKIN_TEST_RESULTS_DIR'):
    from catkin_pkg.python_setup import generate_distutils_setup
    #Delete keys which should not match catkin packaged variant
    for k in ('version', 'url'):
        setup_args.pop(k, None)
    setup_args=generate_distutils_setup(**setup_args)



#Write a temp file to pass verision into script
version_file = os.path.join(os.path.dirname(__file__),
                            "lib", "cfclient", "version.py");
try:
    with open(version_file, "w") as versionpy:
        versionpy.write("VERSION='{}'".format(VERSION))
except:
    print("Warning: Version file cannot be written.")

setup(**setup_args)

if (os.path.isfile(version_file)):
    os.remove(version_file)
