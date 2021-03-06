# A setup script showing advanced features.
#
# Note that for the NT service to build correctly, you need at least
# win32all build 161, for the COM samples, you need build 163.
# Requires wxPython, and Tim Golden's WMI module.

from distutils.core import setup
import py2exe
import sys

# If run without args, build executables, in quiet mode.
if len(sys.argv) == 1:
    sys.argv.append("py2exe")
    sys.argv.append("-q")

class Target:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        # for the versioninfo resources
        self.version = "0.0.1"
        self.company_name = "No Company"
        self.copyright = "no copyright"
        self.name = "twistd application server"

test_twisted = Target(
    # used for the versioninfo resource
    description = "A twisted server implementation",

    # what to build
    script = "wrap_twistw.py",
    dest_base = "twistd")

includes = ["twisted.scripts._twistw", "dispatcher"]

setup(
    options = {"py2exe": {# create a compressed zip archive
                          "compressed": 1,
                          "optimize": 2,
                          "includes": includes}},
    # The lib directory contains everything except the executables and the python dll.
    # Can include a subdirectory name.
    zipfile = "lib/shared.zip",

    console = [test_twisted]
    )
