#!/usr/bin/env python

from distutils.core import setup
import glob
import os

VERSION = '2013.4.2'  # Year.Month.fix  if fix=99 means dev version

try:
    import py2exe
except ImportError:
    print("Warning: py2exe not usable")

with open(os.path.join(os.path.dirname(__file__),
                       "lib",
                       "cfclient",
                       "version.py"), "w") as versionpy:
    versionpy.write("VERSION='{}'".format(VERSION))

setup(name='cfclient',
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
      scripts=['bin/cfclient'],

      # Py2exe specifics
      console=['bin/cfclient'],
      data_files=[('', ['README.md', 'LICENSE.txt']),
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
                   glob.glob('lib/cfclient/configs/log/*.json'))],
      options={"py2exe": {"includes": ["sip", "PyQt4",
                                         "cfclient.ui.widgets",
                                         "cflib.bootloader.cloader",
                                         "cfclient.ui.toolboxes.*",
                                         "cfclient.ui.*", "cfclient.ui.tabs.*",
                                         "cfclient.ui.widgets.*",
                                         "cfclient.ui.dialogs.*",
                                         "pygame._view"],
                           "excludes": ["AppKit"],
                           "skip_archive": True}})

os.remove(os.path.join(os.path.dirname(__file__),
                       "lib",
                       "cfclient",
                       "version.py"))
