#!/usr/bin/env python

from distutils.core import setup
import glob

try:
    import py2exe
except ImportError:
    print("Warning: py2exe not usable")

setup(name='cfclient',
      description='Bitcraze Cazyflie nano quadcopter client',
      version='2013.3.99.99', # Year.Month.fix  if fix=99.99 means dev version
      author='Bitcraze team',
      author_email='contact@bitcraze.se',
      url='http://www.bitcraze.se',
      package_dir={'':'lib'},
      packages=['cfclient', 'cfclient.ui', 'cfclient.ui.tabs', 'cfclient.ui.toolboxes',
                'cfclient.ui.widgets' ,'cfclient.utils',
                'cflib', 'cflib.bootloader', 'cflib.crazyflie', 'cflib.drivers',
                'cflib.utils', 'cflib.crtp',
               ],
      scripts=['bin/cfclient'],
      
      #Py2exe specifics
      console=['bin/cfclient'],
      data_files=[('cfclient/ui', glob.glob('lib/cfclient/ui/*.ui')),
                  ('cfclient/ui', glob.glob('lib/cfclient/ui/*.py')),
                  ('cfclient/ui/tabs', glob.glob('lib/cfclient/ui/tabs/*.ui')),
                  ('cfclient/ui/tabs', glob.glob('lib/cfclient/ui/tabs/*.py')),
                  ('cfclient/ui/widgets', glob.glob('lib/cfclient/ui/widgets/*.ui')),
                  ('cfclient/ui/widgets', glob.glob('lib/cfclient/ui/widgets/*.py')),
                  ('cfclient/configs', glob.glob('lib/cfclient/configs/*.json')),
                  ('cfclient/configs', glob.glob('lib/cfclient/configs/*.json')),
                  ('cfclient/configs/input', glob.glob('lib/cfclient/configs/input/*.json')),
                  ('cfclient/configs/log', glob.glob('lib/cfclient/configs/log/*.json')),
                  ],
      options={"py2exe" : {"includes" : ["sip", "PyQt4", "cfclient.ui.widgets", "cflib.bootloader.cloader"],
                           "skip_archive": True,
                          }}
     )

