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

if sys.argv[1] in ('build', 'bdist_msi', 'bdist_mac'):
    from cx_Freeze import setup, Executable  # noqa

    cxfreeze_options = {
        'options': {
            'build_exe': {'includes': ['numpy.core._methods',
                                       'numpy.lib.format',
                                       'pyqtgraph.debug',
                                       'pyqtgraph.ThreadsafeTimer',
                                       ],
                          'packages': ['asyncio'],
                          'excludes': ['tkinter']}
        },
        'executables': [Executable("bin/cfclient", icon='bitcraze.ico')],
    }
else:
    cxfreeze_options = {}
# except:
#     pass

if sys.version_info < (3, 5):
    raise "must use python 3.5 or greater"


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
                     "release packages (either from pip or a binary build).\n")
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
    platform_requires = ['pysdl2~=0.9.6']
if sys.platform == 'win32':
    platform_dev_requires = ['cx_freeze==5.1.1', 'jinja2==2.10.3']

package_data = {
    'cfclient.ui':  relative(glob('src/cfclient/ui/*.ui')),
    'cfclient.ui.tabs': relative(glob('src/cfclient/ui/tabs/*.ui')),
    'cfclient.ui.widgets':  relative(glob('src/cfclient/ui/widgets/*.ui')),
    'cfclient.ui.toolboxes':  relative(glob('src/cfclient/ui/toolboxes/*.ui')),  # noqa
    'cfclient.ui.dialogs':  relative(glob('src/cfclient/ui/dialogs/*.ui')),
    'cfclient':  relative(glob('src/cfclient/configs/*.json'), 'configs/') +  # noqa
                 relative(glob('src/cfclient/configs/input/*.json'), 'configs/input/') +  # noqa
                 relative(glob('src/cfclient/configs/log/*.json'), 'configs/log/') +  # noqa
                 relative(glob('src/cfclient/resources/*'), 'resources/') +  # noqa
                 relative(glob('src/cfclient/ui/icons/*.png'), 'ui/icons/'),  # noqa
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

    install_requires=platform_requires + ['cflib~=0.1.12',
                                          'appdirs~=1.4.0',
                                          'pyzmq~=19.0',
                                          'pyqtgraph~=0.11',
                                          'PyYAML~=5.3',
                                          'quamash~=0.6.1',
                                          'qtm~=2.0.2'],

    # List of dev and qt dependencies
    # Pyqt5 5.12 is the last version that does not cause performance problems
    # on Windows and Mac
    # You can install them by running
    # $ pip install -e .[dev,qt5]
    extras_require={
        'dev': platform_dev_requires + [],
        'qt5': ['pyqt5~=5.12.0']
    },

    package_data=package_data,

    data_files=data_files,

    # cx_freeze options
    **cxfreeze_options
)
