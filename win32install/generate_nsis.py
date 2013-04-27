import jinja2
import os

DIST_PATH = "..\dist"

# Get list of files and directory to install/uninstall
install_files = []
install_dirs = []

os.chdir(os.path.join(os.path.dirname(__file__), DIST_PATH))
for root, dirs, files in os.walk("."):
	for f in files:
		install_files += [os.path.join(root[2:], f)]
	install_dirs += [root[2:]]

print "Found {} files in {} folders to install.".format(len(install_files), len(install_dirs))

# Get mercurial tag or version
with os.popen("hg id -t") as hg:
	tag = hg.read().strip()

if tag != "tip":
	version = tag
else:
	with os.popen("hg id -i") as hg:
		version = hg.read().strip()

print "Cfclient vertion {}".format(version)
		
os.chdir(os.path.dirname(__file__))

with open("cfclient.nsi.tmpl", "r") as template_file:
	template = template_file.read()

tmpl = jinja2.Template(template)

with open("cfclient.nsi", "w") as out_file:
	out_file.write(tmpl.render(files=install_files, dirs=install_dirs, version=version))

