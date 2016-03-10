#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import subprocess
from subprocess import PIPE, Popen
from setuptools import setup, find_packages
from glob import glob
import json
import codecs
import sys
import os

try:
    import py2exe  # noqa
except:
    pass

if sys.version_info < (3, 4):
    raise "must use python 3.4 or greater"


# Recover version from Git
def get_version():
    try:
        process = Popen(["git", "describe", "--tags"], stdout=PIPE)
        (output, err) = process.communicate()
        process.wait()
    except OSError:
        raise Exception("Cannot run git: " +
                        "Git is required to generate packages!")

    version = output.strip().decode("UTF-8")

    if subprocess.call(["git", "diff-index", "--quiet", "HEAD"]) != 0:
        version += "_modified"

    return version

VERSION = get_version()

with codecs.open('version.json', 'w', encoding='utf8') as f:
    f.write(json.dumps({'version': VERSION}))

platform_requires = []
platform_dev_requires = []
if sys.platform == 'win32' or sys.platform == 'darwin':
    platform_requires = ['pysdl2']
if sys.platform == 'win32':
    platform_dev_requires = ['py2exe', 'jinja2']


def relative(lst, base=''):
    return list(map(lambda x: base + os.path.basename(x), lst))

# Initial parameters
setup(
    name='cfclient',
    description='Bitcraze Cazyflie quadcopter client',
    version=VERSION,
    author='Bitcraze team',
    author_email='contact@bitcraze.se',
    url='http://www.bitcraze.io',

    classifiers=[
        'License :: OSI Approved :: GPLv2 License',

        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],

    keywords='quadcopter crazyflie',

    package_dir={'': 'src'},
    packages=find_packages('src'),

    entry_points={
        'console_scripts': [
            'cfclient=cfclient.gui:main',
            'cfheadless=cfclient.headless:main',
            'cfloader=cfloader:main',
            'cfzmq=cfzmq:main'
        ],
    },

    install_requires=platform_requires + ['cflib', 'appdirs'],

    # List of dev dependencies
    # You can install them by running
    # $ pip install -e .[dev]
    extras_require={
        'dev': platform_dev_requires + []
    },

    package_data={
        'cfclient.ui':  relative(glob('src/cfclient/ui/*.ui')),
        'cfclient.ui.tabs': relative(glob('src/cfclient/ui/tabs/*.ui')),
        'cfclient.ui.widgets':  relative(glob('src/cfclient/ui/widgets/*.ui')),
        'cfclient.ui.toolboxes':  relative(glob('src/cfclient/ui/toolboxes/*.ui')),  # noqa
        'cfclient.ui.dialogs':  relative(glob('src/cfclient/ui/dialogs/*.ui')),
        'cfclient':  relative(glob('src/cfclient/configs/*.json'), 'configs/') +  # noqa
                     relative(glob('src/cfclient/configs/input/*.json'), 'configs/input/') +  # noqa
                     relative(glob('src/cfclient/configs/log/*.json'), 'configs/log/') +  # noqa
                     relative(glob('src/cfclient/resources/*'), 'resources/') +
                     relative(glob('src/cfclient/*.png')),
    },

    # Py2exe options
    console=[
        {
            'script': 'bin/cfclient',
            'icon_resources': [(0, 'bitcraze.ico')]
        }
    ],
    py2exe={
        'includes': ['cfclient.ui.widgets.hexspinbox'],
        'bundle_files': 3,
        'skip_archive': True,
    },

    data_files=[
        ('', ['README.md', 'version.json']),
        ('third_party', glob('src/cfclient/third_party/*')),
    ],
)
