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


# Recover version from Git.
# Returns None if git is not installed or if we are running outside of the git
# tree
def get_version():
    try:
        process = Popen(["git", "describe", "--tags"], stdout=PIPE)
        (output, err) = process.communicate()
        process.wait()
    except OSError:
        return None

    if process.returncode != 0:
        return None

    version = output.strip().decode("UTF-8")

    if subprocess.call(["git", "diff-index", "--quiet", "HEAD"]) != 0:
        version += "_modified"

    return version


def relative(lst, base=''):
    return list(map(lambda x: base + os.path.basename(x), lst))


VERSION = get_version()

if not VERSION and not os.path.isfile('src/cfclient/version.json'):
    sys.stderr.write("Git is required to install from source.\n" +
                     "Please clone the project with Git or use one of the\n" +
                     "release pachages (either from pip or a binary build).\n")
    raise Exception("Git required.")

if not VERSION:
    versionfile = open('src/cfclient/version.json', 'r', encoding='utf8')
    VERSION = json.loads(versionfile.read())['version']
else:
    with codecs.open('src/cfclient/version.json', 'w', encoding='utf8') as f:
        f.write(json.dumps({'version': VERSION}))

platform_requires = []
platform_dev_requires = []
if sys.platform == 'win32' or sys.platform == 'darwin':
    platform_requires = ['pysdl2']
if sys.platform == 'win32':
    platform_dev_requires = ['py2exe', 'jinja2']

# Make a special case when running py2exe to be able to access resources
if sys.platform == 'win32' and sys.argv[1] == 'py2exe':
    package_data = {}
    qwindows = os.path.join(os.path.dirname(sys.executable),
                            "Library\\plugins\\platforms\\qwindows.dll")
    data_files = [
        ('', ['README.md', 'src/cfclient/version.json']),
        ('platforms', [qwindows]),
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
    ]
else:
    package_data = {
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
        '': ['README.md']
    }
    data_files = [
        ('third_party', glob('src/cfclient/third_party/*')),
    ]


# Initial parameters
setup(
    name='cfclient',
    description='Bitcraze Cazyflie quadcopter client',
    version=VERSION,
    author='Bitcraze team',
    author_email='contact@bitcraze.se',
    url='http://www.bitcraze.io',

    classifiers=[
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',  # noqa
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

    install_requires=platform_requires + ['cflib>=0.1.1', 'appdirs==1.4.0',
                                          'pyzmq', 'pyqtgraph>=0.10'],

    # List of dev dependencies
    # You can install them by running
    # $ pip install -e .[dev]
    extras_require={
        'dev': platform_dev_requires + []
    },

    package_data=package_data,

    # Py2exe options
    console=[
        {
            'script': 'bin/cfclient',
            'icon_resources': [(0, 'bitcraze.ico')]
        }
    ],
    options={
        "py2exe": {
            'includes': ['cfclient.ui.widgets.hexspinbox',
                         'zmq.backend.cython'],
            'bundle_files': 3,
            'skip_archive': True,
        },
    },

    data_files=data_files
)

# Fixing the zmq lib in the windows binary dist folder
if sys.platform == 'win32' and sys.argv[1] == 'py2exe':
    print("Renaming zmq dll")
    if os.path.isfile('dist/zmq.libzmq.pyd') and \
       not os.path.isfile('dist/libzmq.pyd'):
        os.rename('dist/zmq.libzmq.pyd', 'dist/libzmq.pyd')
