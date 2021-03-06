"""
Build classes specific to the Twisted codebase
"""

from buildbot.process.properties import WithProperties
from buildbot.process.base import Build
from buildbot.process.factory import BuildFactory, s
from buildbot.scheduler import Scheduler
from buildbot.steps import shell, transfer
from buildbot.steps.shell import ShellCommand, SetProperty
from buildbot.steps.source import SVN, Bzr, Mercurial
from buildbot.steps.python import PyFlakes
from pypy_steps import Translate

from twisted_steps import ProcessDocs, ReportPythonModuleVersions, \
    Trial, RemovePYCs, CheckDocumentation, LearnVersion, SetBuildProperty, \
    MasterShellCommand

TRIAL_FLAGS = ["--reporter=bwverbose"]
WARNING_FLAGS = ["--unclean-warnings"]
FORCEGC_FLAGS = ["--force-gc"]

class TwistedBuild(Build):
    workdir = "Twisted" # twisted's bin/trial expects to live in here



class TwistedScheduler(Scheduler):
    def fileIsImportant(self, change):
        for filename in change.files:
            if not filename.startswith("doc/fun/"):
                return 1
        return 0



class TwistedTrial(Trial):
    tests = "twisted"
    # the Trial in Twisted >=2.1.0 has --recurse on by default, and -to
    # turned into --reporter=bwverbose .
    recurse = False
    trialMode = TRIAL_FLAGS
    testpath = None
    trial = "./bin/trial"

class TwistedBaseFactory(BuildFactory):
    """
    @ivar python: The path to the Python executable to use.  This is a
        list, to allow additional arguments to be passed.
    """
    buildClass = TwistedBuild
    # bin/trial expects its parent directory to be named "Twisted": it uses
    # this to add the local tree to PYTHONPATH during tests
    workdir = "Twisted"

    forceGarbageCollection = False

    def _fixPermissions(self, source):
        # Hack for Windows
        haveChmod = transfer.FileDownload(
            mastersrc="dependencies/chmod.bat",
            slavedest="chmod.bat",
            workdir=".")
        source.insert(0, haveChmod)
        # Fix any nasty permissions left over from last time that
        # might cause the cleanup to fail.
        fixPermissions = ShellCommand(
            workdir=".", command=["chmod", "u+rwX", "-f", "-R", "Twisted"])
        source.insert(0, fixPermissions)


    def __init__(self, python, source, uncleanWarnings, trialTests=None, trialMode=None):
        if not isinstance(source, list):
            source = [source]
        else:
            source = list(source)

        # If permissions get messed up on a slave, this can fix it.
        # But it breaks on old slaves so it's not enabled all the time
        # (and it can't fix old slaves, obviously).

        # self._fixPermissions(source)

        BuildFactory.__init__(self, source)

        if type(python) is str:
            python = [python]

        self.python = python
        self.uncleanWarnings = uncleanWarnings
        self.trialMode = trialMode
        if trialTests is None:
            trialTests = [WithProperties("%(test-case-name:-twisted)s")]
        self.trialTests = trialTests

        self.addStep(
            ReportPythonModuleVersions,
            python=self.python,
            moduleInfo=[
                ("Python", "sys", "sys.version"),
                ("OpenSSL", "OpenSSL", "OpenSSL.__version__"),
                ("PyCrypto", "Crypto", "Crypto.__version__"),
                ("gmpy", "gmpy", "gmpy.version()"),
                ("SOAPpy", "SOAPpy", "SOAPpy.__version__"),
                ("ctypes", "ctypes", "ctypes.__version__"),
                ("gtk", "gtk", "gtk.gtk_version"),
                ("pygtk", "gtk", "gtk.pygtk_version"),
                ("pywin32", "win32api",
                 "win32api.GetFileVersionInfo(win32api.__file__, chr(92))['FileVersionLS'] >> 16"),
                ("pyasn1", "pyasn1", "pyasn1.majorVersionId"),
                ],
            pkg_resources=[
                ("subunit", "subunit"),
                ("zope.interface", "zope.interface"),
                ])


    def addTrialStep(self, **kw):
        if self.trialMode is not None:
            trialMode = self.trialMode
        else:
            trialMode = TRIAL_FLAGS

        if self.uncleanWarnings:
            trialMode = trialMode + WARNING_FLAGS
        if self.forceGarbageCollection:
            trialMode = trialMode + FORCEGC_FLAGS
        if 'tests' not in kw:
            kw['tests'] = self.trialTests
        if 'python' not in kw:
            kw['python'] = self.python
        self.addStep(TwistedTrial, trialMode=trialMode, **kw)



class PyFlakesBuildFactory(BuildFactory):
    """
    A build factory which just runs PyFlakes over the specified source.
    """
    def __init__(self, source):
        if not isinstance(source, list):
            source = [source]
        BuildFactory.__init__(self, source)
        self.addStep(
            PyFlakes,
            descriptionDone="PyFlakes", flunkOnFailure=True,
            command=["pyflakes", "."])



class TwistedDocumentationBuildFactory(TwistedBaseFactory):
    treeStableTimer = 5 * 60

    def __init__(self, source, python="python"):
        TwistedBaseFactory.__init__(self, python, source, False)
        self.addStep(CheckDocumentation)
        self.addStep(ProcessDocs)
        self.addStep(
            shell.ShellCommand,
            command=['/bin/tar', 'cjf', 'apidocs.tar.bz2', 'apidocs'])
        self.addStep(
            transfer.FileUpload,
            workdir='.',
            slavesrc='./Twisted/apidocs.tar.bz2',
            masterdest=WithProperties(
                'public_html/builds/apidocs/apidocs-%(revision)s.tar.bz2'))



class TwistedSphinxBuildFactory(TwistedBaseFactory):
    def __init__(self, source, python="python"):
        TwistedBaseFactory.__init__(self, python, source, False)
        # Get rid of the results of the last run
        self.addStep(
            shell.ShellCommand,
            command=['hg', 'clean', '--all', '--exclude', 'lore2sphinx.conf'],
            workdir='lore2sphinx')
        # Get any updates to lore2sphinx
        self.addStep(
            shell.ShellCommand,
            command=['hg', 'pull', '-u'],
            workdir='lore2sphinx')
        # Generate the docs anew
        self.addStep(
            shell.ShellCommand,
            command=self.python + ['l2s_builder.py'],
            workdir='lore2sphinx',
            env={'PYTHONPATH': '.'})
        # Upload the result
        self.addStep(
            transfer.DirectoryUpload,
            workdir='lore2sphinx/profiles/twisted/build',
            slavesrc='html',
            masterdest=WithProperties(
                'public_html/builds/sphinx-html/%(buildnumber)s-%(got_revision)s'),
            blocksize=2 ** 16,
            compress='gz')



class FullTwistedBuildFactory(TwistedBaseFactory):
    treeStableTimer = 5*60

    def __init__(self, source, python="python",
                 runTestsRandomly=False,
                 compileOpts=[], compileOpts2=[],
                 uncleanWarnings=True, trialMode=None,
                 trialTests=None, buildExtensions=True):
        TwistedBaseFactory.__init__(self, python, source, uncleanWarnings, trialTests=trialTests, trialMode=trialMode)

        assert isinstance(compileOpts, list)
        assert isinstance(compileOpts2, list)

        if buildExtensions:
            cmd = (python + compileOpts + ["setup.py", "build_ext"]
                   + compileOpts2 + ["-i"])
            self.addStep(shell.Compile, command=cmd, flunkOnFailure=True)

        self.addStep(RemovePYCs)
        self.addTrialStep(randomly=runTestsRandomly)


class Win32RemovePYCs(ShellCommand):
    name = "remove-.pyc"
    command = 'del /s *.pyc'
    description = ["removing", ".pyc", "files"]
    descriptionDone = ["remove", ".pycs"]


class GoodTwistedBuildFactory(TwistedBaseFactory):
    treeStableTimer = 5 * 60

    def __init__(self, source, python="python",
                 processDocs=False, runTestsRandomly=False,
                 compileOpts=[], compileOpts2=[],
                 uncleanWarnings=True,
                 extraTrialArguments={},
                 forceGarbageCollection=False):
        TwistedBaseFactory.__init__(self, python, source, uncleanWarnings)
        self.forceGarbageCollection = forceGarbageCollection
        if processDocs:
            self.addStep(ProcessDocs)

        assert isinstance(compileOpts, list)
        assert isinstance(compileOpts2, list)
        cmd = (self.python + compileOpts + ["setup.py", "build_ext"]
               + compileOpts2 + ["-i"])

        self.addStep(shell.Compile, command=cmd, flunkOnFailure=True)
        self.addStep(RemovePYCs)
        self.addTrialStep(randomly=runTestsRandomly, **extraTrialArguments)


class TwistedReactorsBuildFactory(TwistedBaseFactory):
    treeStableTimer = 5*60

    def __init__(self, source, RemovePYCs=RemovePYCs,
                 python="python", compileOpts=[], compileOpts2=[],
                 reactors=["select"], uncleanWarnings=True):
        TwistedBaseFactory.__init__(self, python, source, uncleanWarnings)

        assert isinstance(compileOpts, list)
        assert isinstance(compileOpts2, list)
        cmd = (self.python + compileOpts + ["setup.py", "build_ext"]
               + compileOpts2 + ["-i"])

        self.addStep(shell.Compile, command=cmd, warnOnFailure=True)

        for reactor in reactors:
            self.addStep(RemovePYCs)
            self.addTrialStep(
                name=reactor, reactor=reactor, flunkOnFailure=True,
                warnOnFailure=False)


class TwistedEasyInstallFactory(TwistedBaseFactory):
    treeStableTimer = 5*60

    def __init__(self, source, uncleanWarnings, python="python",
                 reactor="epoll", easy_install="easy_install"):
        TwistedBaseFactory.__init__(self, python, source, uncleanWarnings)

        setupCommands = [
            ["rm", "-rf", "install"],
            ["mkdir", "-p", "install/bin", "install/lib"],
            [easy_install, "--install-dir", "install/lib",
                           "--script-dir", "install/bin",
                           "."],
            ]
        for command in setupCommands:
            self.addStep(shell.ShellCommand, command=command,
                         env={"PYTHONPATH": "install/lib"},
                         haltOnFailure=True)
        self.addTrialStep(
            name=reactor,
            reactor=reactor, flunkOnFailure=True,
            warnOnFailure=False, workdir="Twisted/install",
            env={"PYTHONPATH": "lib"})


class TwistedBdistMsiFactory(TwistedBaseFactory):
    treeStableTimer = 5*60

    uploadBase = 'public_html/builds/'
    def __init__(self, source, uncleanWarnings, platform, pyVersion):
        python = self.python(pyVersion)
        TwistedBaseFactory.__init__(self, python, source, uncleanWarnings)
        self.addStep(
            LearnVersion, python=python, package='twisted', workdir='Twisted')

        def transformVersion(build):
            return build.getProperty("version").split("+")[0].split("pre")[0]
        self.addStep(
            SetBuildProperty, property_name='versionMsi', value=transformVersion)
        self.addStep(shell.ShellCommand,
                command=[python, "-c", WithProperties(
                     'version = \'%(versionMsi)s\'; '
                     'f = file(\'twisted\copyright.py\', \'at\'); '
                     'f.write(\'version = \' + repr(version)); '
                     'f.close()')],
                     haltOnFailure=True)
        if pyVersion >= "2.5":
            self.addStep(shell.ShellCommand, command=[python, "setup.py", "bdist_msi"],
                         haltOnFailure=True)
            self.addStep(
                transfer.FileUpload,
                slavesrc=WithProperties('dist/Twisted-%(versionMsi)s.win32-py' + pyVersion + '.msi'),
                masterdest=WithProperties(
                    self.uploadBase + 'twisted-packages/Twisted-%%(version)s.%s-py%s.msi' % (platform, pyVersion)))

        self.addStep(shell.ShellCommand, command=[python, "setup.py", "bdist_wininst"],
                     haltOnFailure=True)
        self.addStep(
            transfer.FileUpload,
            slavesrc=WithProperties('dist/Twisted-%(versionMsi)s.win32-py' + pyVersion + '.exe'),
            masterdest=WithProperties(
                self.uploadBase + 'twisted-packages/Twisted-%%(version)s.%s-py%s.exe' % (platform, pyVersion)))

    def python(self, pyVersion):
        return (
            "c:\\python%s\\python.exe" % (
                pyVersion.replace('.', ''),))


class InterpreterBuilderMixin:
    def buildModule(self, python, basename):
        self.addStep(
            ShellCommand,
            # Can't make workdir build, .. won't resolve properly
            # because build is a symlink.
            workdir=".",
            command=["/bin/tar", "Cxzf", "build", basename + ".tar.gz"])
        self.addStep(
            ShellCommand,
            workdir="build/" + basename,
            command=[python, "setup.py", "clean", "install", "--prefix", "../install"])


    def buildModules(self, python, projects):
        python = "../" + python

        for basename in projects:
            # Send the tarball down
            self.addStep(
                transfer.FileDownload,
                mastersrc="dependencies/" + basename + ".tar.gz",
                slavedest=basename + ".tar.gz",
                workdir=".")

            if "subunit" in basename:
                # Always trying to be special.
                self.buildSubunit(python, basename)
            else:
                self.buildModule(python, basename)

    def buildSubunit(self, python, dirname):
        basename = dirname + '.tar.gz'
        self.addStep(
            ShellCommand,
            workdir=".",
            command=["/bin/tar", "Cxzf", "build", basename])
        self.addStep(
            ShellCommand,
            workdir="build/" + dirname,
            env={"PYTHON": python},
            command="./configure --prefix=${PWD}/../install")
        self.addStep(
            ShellCommand,
            workdir="build/" + dirname,
            command=["make", "install"])



class CPythonBuildFactory(BuildFactory, InterpreterBuilderMixin):
    def __init__(self, branch, python, projects, *a, **kw):
        BuildFactory.__init__(self, *a, **kw)
        self.addStep(
            SVN,
            baseURL="http://svn.python.org/projects/python/",
            defaultBranch=branch,
            mode="copy")
        self.addStep(
            ShellCommand,
            command="./configure --prefix=$PWD/install")
        self.addStep(
            ShellCommand,
            command=["make", "install"])
        pythonc = "install/bin/" + python
        self.buildModules(pythonc, projects)
            


class PyPyTranslationFactory(BuildFactory, InterpreterBuilderMixin):
    def __init__(self, translationArguments, targetArguments, *a, **kw):
        BuildFactory.__init__(self, *a, **kw)
        self.addStep(
            Mercurial,
            repourl="https://bitbucket.org/pypy/pypy")
        self.addStep(
            Translate,
            translationArgs=translationArguments,
            targetArgs=targetArguments)

        # Don't try building these yet.  PyPy doesn't quite work well
        # enough.
        # pypyc = "pypy/translator/goal/pypy-c"
        # self.buildModules(pypyc)



class TwistedPyPyBuildFactory(BuildFactory):
    def __init__(self, *a, **kw):
        BuildFactory.__init__(self, *a, **kw)
#         self.addStep(
#             ShellCommand,
#             workdir="build",
#             command=["../pypy-c", "setup.py", "build_ext", "-i"])

        # This would include CPython site-packages (which might have
        # extension modules, oh no) and our own little site-packages
        # which could include PyCrypto and pyOpenSSL.  PyPy doesn't
        # work that well yet though.
#         PYTHONPATH = "../site-packages:/usr/lib/python2.6/dist-packages"
        PYTHONPATH = "/usr/lib/python2.6/dist-packages"
        self.addStep(
            Trial,
            workdir="build",
            python=["../pypy-c"],
            testpath=None,
            trial="bin/trial",
            tests=["twisted"],
            env={"PATH": "/usr/bin:.", "PYTHONPATH": PYTHONPATH})


class TwistedIronPythonBuildFactory(FullTwistedBuildFactory):
    def __init__(self, source, *a, **kw):
        FullTwistedBuildFactory.__init__(
            self, source, ["ipy"], buildExtensions=False, *a, **kw)


pyOpenSSLSource = s(
    Bzr,
    baseURL="http://bazaar.launchpad.net/~exarkun/pyopenssl/",
    defaultBranch="trunk",
    mode="copy")


class PyOpenSSLBuildFactoryBase(BuildFactory):
    """
    Build and test PyOpenSSL.
    """
    def __init__(self, pyVersion, useTrial=True):
        BuildFactory.__init__(self, [pyOpenSSLSource])
        self.uploadBase = 'public_html/builds/'
        self.useTrial = useTrial
        self.learnVersion(pyVersion)


    def learnVersion(self, pyVersion):
        self.addStep(
            SetProperty,
            command=[
                self.python(pyVersion), 
                # Keep warnings out of the output
                "-Wignore", 
                "setup.py", 
                # Keep extra debug logging out of the output (not
                # entirely successfully though)
                "--quiet",
                # Get the version number, though.
                "--version"],
            property="version",
            workdir='source')


    def addTestStep(self, pyVersion):
        if self.useTrial:
            self.addStep(
                Trial,
                workdir="build/build/lib.%s-%s" % (
                    self.platform(pyVersion), pyVersion),
                python=self.python(pyVersion),
                trial=self.trial(pyVersion),
                tests="OpenSSL",
                testpath=None)
        else:
            self.addTestWithDiscoverStep(pyVersion)


    def addTestWithDiscoverStep(self, pyVersion):
        """
        Add a step to run the test suite using the discover module.
        """
        self.addStep(
            ShellCommand,
            timeout=30,
            workdir="build/build/lib.%s-%s" % (
                self.platform(pyVersion), pyVersion),
            command=[self.python(pyVersion), "-u", "-c", "import discover; discover.main()", "-v", "OpenSSL/test/"])



class LinuxPyOpenSSLBuildFactory(PyOpenSSLBuildFactoryBase):
    """
    Build and test a Linux (or Linux-like) PyOpenSSL package.
    """
    def __init__(self, versions, source, platform=None, bdistEnv=None, useTrial=True):
        PyOpenSSLBuildFactoryBase.__init__(self, versions[0], useTrial)
        
        self._platform = platform
        self.bdistEnv = bdistEnv
        if source:
            self.addStep(
                shell.Compile,
                # Doesn't matter what Python gets used for sdist
                command=["python", "setup.py", "sdist"],
                flunkOnFailure=True)
            self.addStep(
                transfer.FileUpload,
                slavesrc=WithProperties('dist/pyOpenSSL-%(version)s.tar.gz'),
                masterdest=WithProperties(self.uploadBase + 'pyOpenSSL-packages/pyOpenSSL-%(version)s.tar.gz'))
        for pyVersion in versions:
            python = self.python(pyVersion)
            platform = self.platform(pyVersion)
            self.addStep(
                shell.Compile,
                # Try cleaning up what was there before so this is a
                # reproducable build (clean --all doesn't actually
                # work so well, but try anyway).  Then build the
                # extensions without regard for file timestamps (which
                # hopefully also increases reproducability and works
                # around any files the clean step missed).  Last build
                # a binary distribution for upload.  (We don't do this
                # in-place because we can't do that on Windows and
                # being inconsistent would make this more
                # complicated.)
                command=[python, "setup.py", "clean", "--all", "build_ext", "--force", "bdist"],
                env=self.bdistEnv,
                flunkOnFailure=True)
            self.addTestStep(pyVersion)
            self.addStep(
                transfer.FileUpload,
                # This is the name of the file "setup.py bdist" writes.
                slavesrc=WithProperties(
                    'dist/pyOpenSSL-%(version)s.' + platform + '.tar.gz'),
                masterdest=WithProperties(
                    self.uploadBase + 'pyOpenSSL-packages/pyOpenSSL-%(version)s.py' +
                    pyVersion + '.' + platform + '.tar.gz'))


    def trial(self, version):
        """
        Return the path to the trial script for the given version of
        Python.
        """
        return "/usr/bin/trial"


    def platform(self, version):
        return self._platform


    def python(self, version):
        return "python" + version



class OSXPyOpenSSLBuildFactory(LinuxPyOpenSSLBuildFactory):
    """
    Build and test an OS-X PyOpenSSL package.
    """
    def __init__(self, versions, osxVersion, **kw):
        self.osxVersion = osxVersion
        LinuxPyOpenSSLBuildFactory.__init__(self, versions, **kw)


    def trial(self, version):
        """
        Return the path to the trial script in the framework.
        """
        if self.osxVersion == "10.6":
            return "/usr/bin/trial"
        return "/usr/local/bin/trial"


    def platform(self, version):
        if self.osxVersion == "10.4":
            # OS X, you are a hilarious trainwreck of stupidity.
            return "macosx-10.3-i386"
        elif version == "2.5":
            return "macosx-10.5-ppc"
        elif version == "2.4":
            return "macosx-10.5-fat"
        elif self.osxVersion == "10.6":
            return "macosx-10.6-universal"
        else:
            return "UNKNOWN"



class Win32PyOpenSSLBuildFactory(PyOpenSSLBuildFactoryBase):
    """
    Build and test a Win32 PyOpenSSL package.
    """
    def python(self, pyVersion):
        return (
            "c:\\python%s\\python.exe" % (
                pyVersion.replace('.', ''),))


    def __init__(self, platform, compiler, pyVersion, opensslPath, useTrial=False):
        PyOpenSSLBuildFactoryBase.__init__(self, pyVersion, useTrial)
        python = self.python(pyVersion)
        buildCommand = [
            python, "setup.py",
            "build_ext", "--compiler", compiler,
            "--with-openssl", opensslPath,
            "build", "bdist", "bdist_wininst"]
        if pyVersion >= "2.5":
            buildCommand.append("bdist_msi")

        self.addStep(
            shell.Compile,
            command=buildCommand,
            flunkOnFailure=True)

        self.addTestStep(pyVersion)

        self.addStep(
            transfer.FileUpload,
            slavesrc=WithProperties('dist/pyOpenSSL-%(version)s.win32.zip'),
            masterdest=WithProperties(
                self.uploadBase + 'pyOpenSSL-packages/pyOpenSSL-%(version)s.' + platform + '-py' + pyVersion + '.zip'))

        self.addStep(
            transfer.FileUpload,
            slavesrc=WithProperties('dist/pyOpenSSL-%(version)s.win32-py' + pyVersion + '.exe'),
            masterdest=WithProperties(
                self.uploadBase + 'pyOpenSSL-packages/pyOpenSSL-%%(version)s.%s-py%s.exe' % (platform, pyVersion)))

        if pyVersion >= "2.5":
            self.addStep(
                transfer.FileUpload,
                slavesrc=WithProperties('dist/pyOpenSSL-%(version)s.win32-py' + pyVersion + '.msi'),
                masterdest=WithProperties(
                    self.uploadBase + 'pyOpenSSL-packages/pyOpenSSL-%%(version)s.%s-py%s.msi' % (platform, pyVersion)))

        self.addStep(
            shell.Compile,
            command=[python, "-c",
                     "import sys, setuptools; "
                     "sys.argv[0] = 'setup.py'; "
                     "exec(open('setup.py').read(), {'__file__': 'setup.py'})",
                     "build_ext", "--with-openssl", opensslPath, "bdist_egg"],
            flunkOnFailure=True)

        eggName = 'pyOpenSSL-%(version)s-py' + pyVersion + '-win32.egg'
        self.addStep(
            transfer.FileUpload,
            slavesrc=WithProperties('dist/' + eggName),
            masterdest=WithProperties(self.uploadBase + 'pyOpenSSL-packages/' + eggName))


    def platform(self, pyVersion):
        return "win32"


    def trial(self, pyVersion):
        return "c:\\python%s\\scripts\\trial" % (pyVersion.replace('.', ''),)



class GCoverageFactory(TwistedBaseFactory):
    buildClass = Build

    revisionProperty = "revision"

    def __init__(self, python, source):
        TwistedBaseFactory.__init__(self, python, source, False)

        # Clean up any pycs left over since they might be wrong and
        # mess up the test run.
        self.addStep(RemovePYCs)

        # Build the extensions with the necessary gcc tracing flags
        self.addStep(
            shell.Compile,
            command=python + ["setup.py", "build_ext"] + self.BUILD_OPTIONS,
            env={'CFLAGS': '-fprofile-arcs -ftest-coverage'},
            flunkOnFailure=True)

        # Run the tests.
        self.addTestSteps(python)

        # Run geninfo and genhtml - together these generate the coverage report
        self.addStep(
            shell.ShellCommand,
            command=["geninfo", "-b", ".", "."])
        self.addStep(
            shell.ShellCommand,
            command=["bash", "-c", 'genhtml -o coverage-report `find . -name *.info`'])

        # Bundle up the report
        self.addStep(
            shell.ShellCommand,
            command=["tar", "czf", "coverage.tar.gz", "coverage-report"])

        # Upload it to the master
        self.addStep(
            transfer.FileUpload,
            slavesrc='coverage.tar.gz',
            masterdest=WithProperties(
                'public_html/builds/%(project)s-coverage-report/%(project)s-coverage-%%(%(revisionProperty)s)s.tar.gz' % {
                    'project': self.PROJECT,
                    'revisionProperty': self.revisionProperty}))

        # Unarchive it so it can be viewed directly.  WithProperties
        # is not supported by MasterShellCommand.  Joy.  Unbounded joy.
        prefix = 'public_html/builds/%(project)s-coverage-report/%(project)s-coverage-' % {
            'project': self.PROJECT}
        self.addStep(
            MasterShellCommand,
            command=[
                'bash', '-x', '-c',
                'fname=`echo %(prefix)s*.tar.gz`; '
                'tar xzf $fname; '
                'rev=${fname:%(prefixlen)d}; '
                'rev=${rev/%%.tar.gz/}; '
                'rm -rf %(prefix)sreport-r$rev; '
                'mv coverage-report %(prefix)sreport-r$rev; '
                'rm $fname; ' % {'prefix': prefix, 'prefixlen': len(prefix)}])



class PyOpenSSLGCoverageFactory(GCoverageFactory):
    PROJECT = 'pyopenssl'
    TESTS = 'OpenSSL'
    BUILD_OPTIONS = ['-i']

    revisionProperty = 'got_revision'

    def __init__(self, python):
        GCoverageFactory.__init__(self, python, pyOpenSSLSource)


    def addTestSteps(self, python):
        self.addTrialStep(
            trial="/usr/bin/trial",
            tests=self.TESTS)



class TwistedGCoverageFactory(GCoverageFactory):
    PROJECT = 'twisted'
    TESTS = ['twisted.test.test_epoll',
             'twisted.web.test.test_http',
             'twisted.python.test.test_util',
             'twisted.internet.test.test_sigchld']
    BUILD_OPTIONS = ["-i"]

    def addTestSteps(self, python):
        self.addTrialStep(tests=self.TESTS)



class TwistedCoveragePyFactory(TwistedBaseFactory):
    OMIT_PATHS = [
        '/usr',
        '_trial_temp',
        ]

    REPORT_COMMAND = [
        'coverage', 'html', '-d', 'twisted-coverage', 
        '--omit', ','.join(OMIT_PATHS), '-i']
        
    def __init__(self, python, source):
        TwistedBaseFactory.__init__(self, python, source, False)
        self.addStep(
            shell.Compile,
            command=python + ["setup.py", "build_ext", "-i"],
            flunkOnFailure=True)
        self.addTrialStep(python=["coverage", "run", "--branch"])
        self.addStep(
            shell.ShellCommand,
            command=self.REPORT_COMMAND)
        self.addStep(
            transfer.DirectoryUpload,
            workdir='Twisted',
            slavesrc='twisted-coverage',
            masterdest=WithProperties('public_html/builds/twisted-coverage.py/twisted-coverage.py-r%(revision)s'),
            blocksize=2 ** 16,
            compress='gz')


class TwistedBenchmarksFactory(TwistedBaseFactory):
    def __init__(self, python, source):
        TwistedBaseFactory.__init__(self, python, source, False)

        self.addStep(
            shell.ShellCommand,
            env={'PYTHONPATH': '.'},
            command=self.python + [
                "../../../twisted-benchmarks/speedcenter.py",
                "--duration", "3", "--iterations", "30",
                "--url", "http://speed.twistedmatrix.com/result/add/"])
