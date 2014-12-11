import jinja2
import os
from subprocess import Popen, PIPE

DIST_PATH = "..\dist"

# Get list of files and directory to install/uninstall
INSTALL_FILES = []
INSTALL_DIRS = []

os.chdir(os.path.join(os.path.dirname(__file__), DIST_PATH))
for root, dirs, files in os.walk("."):
    for f in files:
        INSTALL_FILES += [os.path.join(root[2:], f)]
    INSTALL_DIRS += [root[2:]]

print "Found {} files in {} folders to install.".format(len(INSTALL_FILES),
                                                        len(INSTALL_DIRS))


# Get git tag or VERSION
try:
    process = Popen(["git", "describe", "--tags"], stdout=PIPE)
    (output, err) = process.communicate()
    exit_code = process.wait()
except OSError:
    raise Exception("Cannot run git: Git is required to generate installer!")

VERSION = output.strip()

print "Cfclient version {}".format(VERSION)

os.chdir(os.path.dirname(__file__))

with open("cfclient.nsi.tmpl", "r") as template_file:
    TEMPLATE = template_file.read()

TMPL = jinja2.Template(TEMPLATE)

with open("cfclient.nsi", "w") as out_file:
    out_file.write(TMPL.render(files=INSTALL_FILES,
                               dirs=INSTALL_DIRS,
                               version=VERSION))
