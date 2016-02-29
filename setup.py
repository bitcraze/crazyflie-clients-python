#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import subprocess
from subprocess import PIPE, Popen
from setuptools import setup, find_packages
from glob import glob
import json
import codecs
import sys

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

    # Py2exe options
    console=['bin/cfclient'],
    py2exe={
        'includes': ['cfclient.ui.widgets.hexspinbox'],
    },

    data_files=[
        ('', ['README.md', 'version.json']),
        ('ui', glob('src/cfclient/ui/*.ui')),
        ('ui/tabs', glob('src/cfclient/ui/tabs/*.ui')),
        ('ui/widgets', glob('src/cfclient/ui/widgets/*.ui')),
        ('ui/toolboxes', glob('src/cfclient/ui/toolboxes/*.ui')),
        ('ui/dialogs', glob('src/cfclient/ui/dialogs/*.ui')),
        ('configs', glob('src/cfclient/configs/*.json')),
        ('configs/input', glob('src/cfclient/configs/input/*.json')),
        ('configs/log', glob('src/cfclient/configs/log/*.json')),
        ('', glob('src/cfclient/*.png')),
        ('resources', glob('src/cfclient/resources/*')),
        ('third_party', glob('src/cfclient/third_party/*')),
    ],
)
