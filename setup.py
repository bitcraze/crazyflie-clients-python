#!/usr/bin/env python

from distutils.core import setup

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
     )

