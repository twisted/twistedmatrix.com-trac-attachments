import errno,socket,types

from twisted.trial import unittest
from twisted.internet import error



class GeneralExceptionTests(object): 
    """
    General tests applicable to most exceptions. 
    Subclassed by the actual L{unittest.TestCase}.
    """

    exception_class = None
    exception_bases = ()
    args = ("An error ocourred.",)
    message = args[0]


    def setUp(self):
        self.exception = self.exception_class(*self.args)


    def test_base(self):
        """
        Check the exception has the expected base class.
        """
        self.assertEqual(self.exception.__class__.__bases__, 
            self.exception_bases)


    def test_args(self):
        """
        Check the exception converts to a string as expected.
        """
        self.assertEqual(str(self.exception), self.message)



class TestMulticastJoinError(GeneralExceptionTests, unittest.TestCase):
    """
    Tests for L{error.MulticastJoinError}.
    """
    exception_class = error.MulticastJoinError
    exception_bases = (Exception,)



class TestConnectInProgressError(GeneralExceptionTests, unittest.TestCase):
    """
    Tests for L{error.ConnectInProgressError}.
    """
    exception_class = error.ConnectInProgressError
    exception_bases = (Exception,)



class TestVerifyError(GeneralExceptionTests, unittest.TestCase):
    """
    Tests for L{error.VerifyError}.
    """
    exception_class = error.VerifyError
    exception_bases = (Exception,)



class TestPeerVerifyError(GeneralExceptionTests, unittest.TestCase):
    """
    Tests for L{error.PeerVerifyError}.
    """
    exception_class = error.PeerVerifyError
    exception_bases = (error.VerifyError,)



class TestCertificateError(GeneralExceptionTests, unittest.TestCase):
    """
    Tests for L{error.CertificateError}.
    """
    exception_class = error.CertificateError
    exception_bases = (Exception,)



class TestConnectionClosed(GeneralExceptionTests, unittest.TestCase):
    """
    Tests for L{error.ConnectionClosed}.
    """
    exception_class = error.ConnectionClosed
    exception_bases = (Exception,)



class TestPotentialZombieWarning(GeneralExceptionTests, unittest.TestCase):
    """
    Tests for L{error.PotentialZombieWarning}.
    """
    exception_class = error.PotentialZombieWarning
    exception_bases = (Warning,)

    def setUp(self):
        pass


    def test_base(self):
        """
        Override L{GeneralExceptionTests.test_base} to catch 
        L{DeprecationWarning}.
        """
        func = super(TestPotentialZombieWarning,self).setUp
        self.assertWarns(DeprecationWarning, 
            "twisted.internet.error.PotentialZombieWarning"
            " was deprecated in Twisted 9.0.0", __file__, func)

        super(TestPotentialZombieWarning,self).test_base()


    def test_args(self):
        """
        Override L{GeneralExceptionTests.test_args} to catch 
        L{DeprecationWarning}.
        """
        func = super(TestPotentialZombieWarning,self).setUp
        self.assertWarns(DeprecationWarning,
            "twisted.internet.error.PotentialZombieWarning"
            " was deprecated in Twisted 9.0.0", __file__, func)
        super(TestPotentialZombieWarning,self).test_args()



class TestProcessExitedAlready(GeneralExceptionTests, unittest.TestCase):
    """
    Tests for L{error.ProcessExitedAlready}.
    """
    exception_class = error.ProcessExitedAlready
    exception_bases = (Exception,)



class TestReactorNotRunning(GeneralExceptionTests, unittest.TestCase):
    """
    Tests for L{error.ReactorNotRunning}.
    """
    exception_class = error.ReactorNotRunning
    exception_bases = (RuntimeError,)



class TestReactorAlreadyRunning(GeneralExceptionTests, unittest.TestCase):
    """
    Tests for L{error.ReactorAlreadyRunning}.
    """
    exception_class = error.ReactorAlreadyRunning
    exception_bases = (RuntimeError,)



class TestProcessDone(GeneralExceptionTests, unittest.TestCase):
    """
    Tests for L{error.ProcessDone}.
    """
    exception_class = error.ProcessDone
    exception_bases = (error.ConnectionDone,)
    message = "%s: process finished with exit code 0."


    def test_args(self):
        """
        Override L{GeneralExceptionTests.test_args} to check for
        attributes perticular to L{ProcessDone}.
        """
        self.assertIdentical(self.exception.signal, None)
        self.assertEqual(self.exception.status, self.args[0])
        self.assertEqual(str(self.exception), self.message % (
            self.exception_class.__doc__,)) 

    

class TestProcessTerminated(GeneralExceptionTests, unittest.TestCase):
    """
    Tests for L{error.ProcessTerminated}.
    """
    exception_class = error.ProcessTerminated
    exception_bases = (error.ConnectionLost,)
    args = (1, 2, 3)

    def test_args(self):
        """
        Override L{GeneralExceptionTests.test_args} to check for
        attributes perticular to L{ProcessTerminated}.
        """
        self.assertEqual(self.exception.exitCode, 1)
        self.assertEqual(self.exception.signal, 2)
        self.assertEqual(self.exception.status, 3)
        self.assertEqual(str(self.exception),
            "%s: process ended with exit code 1 by signal 2." % (
                self.exception_class.__doc__,))


    def test_exitCode(self):
        """
        Check for correct string form when only an C{exitCode} is provided.
        """
        exception = self.exception_class(exitCode=42)
        self.assertEqual(exception.exitCode, 42)
        self.assertIdentical(exception.signal, None)
        self.assertIdentical(exception.status, None)
        self.assertEqual(str(exception),
            "%s: process ended with exit code 42." %(
                self.exception_class.__doc__,))


    def test_signal(self):
        """
        Check for correct string form when only an C{signal} is provided.
        """
        exception = self.exception_class(signal=7)
        self.assertIdentical(exception.exitCode, None)
        self.assertEqual(exception.signal, 7)
        self.assertIdentical(exception.status, None)
        self.assertEqual(str(exception),
            "%s: process ended by signal 7." % (
                self.exception_class.__doc__,))



class DocExceptionTests(GeneralExceptionTests):
    """
    Tests applicable to exceptions which construct their string form 
    using thier doc string.
    Subclassed by the actual L{unittest.TestCase}.
    """
    args = ("An", "exception", "occurred")
    message = ' '.join(args)


    def test_no_args(self):
        """
        Check the exception\'s string form is correctly constructed when the 
        exception is created without arguments.
        """
        exception = self.exception_class()

        self.assertNotEqual(getattr(exception, "__doc__", ""), "")
        self.assertEqual(str(exception), "%s." % (exception.__doc__,))


    def test_args(self):
        """
        Check the exception\'s string form is correctly constructed when the 
        exception is created with arguments.
        """
        self.assertNotEqual(getattr(self.exception, "__doc__", ""), "")
        self.assertEqual(str(self.exception), 
            "%s: %s." % (self.exception.__doc__, self.message))



class TestBindError(DocExceptionTests, unittest.TestCase):
    """
    Tests for L{error.BindError}.
    """
    exception_class = error.BindError 
    exception_bases = (Exception,)



class TestMessageLengthError(DocExceptionTests, unittest.TestCase):
    """
    Tests for L{error.MessageLengthError}.
    """
    exception_class = error.MessageLengthError 
    exception_bases = (Exception,)



class TestDNSLookupError(DocExceptionTests, unittest.TestCase):
    """
    Tests for L{error.DNSLookupError}.
    """
    exception_class = error.DNSLookupError
    exception_bases = (IOError,)
    args = ("An", "exception", "occurred")
    message = ' '.join(args[0:2])

    def test_three(self):
        """
        Check for attributes peculiar to subclasses of L{IOError}.
        If three arguments are supplied, filename is set.
        """
        self.assertEqual(self.exception.errno, self.args[0])
        self.assertEqual(self.exception.strerror, self.args[1])
        self.assertEqual(self.exception.filename, self.args[2])
        self.assertEqual(self.exception.args, self.args[0:2])


    def test_two(self):
        """
        Check for attributes peculiar to subclasses of L{IOError}.
        If less than three arguments are supplied, filename is not set.
        """
        args = self.args[0:2]
        exception = self.exception_class(*args)

        self.assertEqual(exception.errno, args[0])
        self.assertEqual(exception.strerror, args[1])
        self.assertIdentical(exception.filename, None)
        self.assertEqual(exception.args, args)


    def test_four(self):
        """
        Check for attributes peculiar to subclasses of L{IOError}.
        If neither two or three arguments are supplied, only args is set.
        """
        args = self.args + ("exta",)
        exception = self.exception_class(*args)

        self.assertIdentical(exception.errno, None)
        self.assertIdentical(exception.strerror, None)
        self.assertIdentical(exception.filename, None)
        self.assertEqual(exception.args, args)



class TestConnectionLost(DocExceptionTests, unittest.TestCase):
    """
    Tests for L{error.ConnectionLost}.
    """
    exception_class = error.ConnectionLost
    exception_bases = (error.ConnectionClosed,)



class TestConnectionDone(DocExceptionTests, unittest.TestCase):
    """
    Tests for L{error.ConnectionDone}.
    """
    exception_class = error.ConnectionDone
    exception_bases = (error.ConnectionClosed,)



class TestAlreadyCalled(DocExceptionTests, unittest.TestCase):
    """
    Tests for L{error.AlreadyCalled}.
    """
    exception_class = error.AlreadyCalled
    exception_bases = (ValueError,)



class TestAlreadyCancelled(DocExceptionTests, unittest.TestCase):
    """
    Tests for L{error.AlreadyCancelled}.
    """
    exception_class = error.AlreadyCancelled
    exception_bases = (ValueError,)



class TestNotConnectingError(DocExceptionTests, unittest.TestCase):
    """
    Tests for L{error.NotConnectingError}.
    """
    exception_class = error.NotConnectingError
    exception_bases = (RuntimeError,)



class TestNotListeningError(DocExceptionTests, unittest.TestCase):
    """
    Tests for L{error.NotListeningError}.
    """
    exception_class = error.NotListeningError
    exception_bases = (RuntimeError,)



class TestConnectionFdescWent(DocExceptionTests, unittest.TestCase):
    """
    Tests for L{error.ConnectionFdescWent}.
    """
    exception_class = error.ConnectionFdescWentAway
    exception_bases = (error.ConnectionLost,)



class ConnectErrorTests(GeneralExceptionTests):
    """
    Tests applicable to exceptions which inherit from L{error.ConnectError}.
    """
    args = ("ENOPONY", "Sadly, no ponies")


    def test_args(self):
        """
        Check the exception\'s string form is correctly constructed when
        the exception is constructed with both C{osError} and C{string}.
        """
        exception = self.exception_class(*self.args)
        self.assertEqual(exception.osError, self.args[0])
        self.assertEqual(exception.args, self.args[1:2])
        self.assertEqual(str(exception),
            "%s: %s: %s." % (exception.__doc__, self.args[0], self.args[1]))


    def test_no_args(self):
        """
        Check the exception\'s string form is correctly constructed when
        the exception is constructed without arguments.
        """
        exception = self.exception_class()
        self.assertIdentical(exception.osError, None)
        self.assertEqual(exception.args, ('',))
        self.assertEqual(str(exception),
            "%s." % (exception.__doc__, ))
        

    def test_osError(self):
        """
        Check the exception\'s string form is correctly constructed when
        the exception is constructed with only C{osError}.
        """
        exception = self.exception_class(osError=self.args[0])
        self.assertEqual(exception.osError, self.args[0])
        self.assertEqual(exception.args, ('',))
        self.assertEqual(str(exception),
            "%s: %s." % (exception.__doc__, self.args[0]))

        
    def test_string(self):
        """
        Check the exception\'s string form is correctly constructed when
        the exception is constructed with only C{string}.
        """
        exception = self.exception_class(string=self.args[1])
        self.assertIdentical(exception.osError, None)
        self.assertEqual(exception.args, self.args[1:2])
        self.assertEqual(str(exception),
            "%s: %s." % (exception.__doc__, self.args[1]))



class TestConnectError(ConnectErrorTests, unittest.TestCase):
    """
    Tests for L{error.ConnectError}.
    """
    exception_class = error.ConnectError
    exception_bases = (Exception,)



class TestConnectBindError(ConnectErrorTests, unittest.TestCase):
    """
    Tests for L{error.ConnectBindError}.
    """
    exception_class = error.ConnectBindError
    exception_bases = (error.ConnectError,)



class TestUnknownHostError(ConnectErrorTests, unittest.TestCase):
    """
    Tests for L{error.UnknownHostError}.
    """
    exception_class = error.UnknownHostError
    exception_bases = (error.ConnectError,)



class TestNoRouteError(ConnectErrorTests, unittest.TestCase):
    """
    Tests for L{error.NoRouteError}.
    """
    exception_class = error.NoRouteError
    exception_bases = (error.ConnectError,)



class TestConnectionRefusedError(ConnectErrorTests, unittest.TestCase):
    """
    Tests for L{error.ConnectionRefusedError}.
    """
    exception_class = error.ConnectionRefusedError
    exception_bases = (error.ConnectError,)



class TestTCPTimedOutError(ConnectErrorTests, unittest.TestCase):
    """
    Tests for L{error.TCPTimedOutError}.
    """
    exception_class = error.TCPTimedOutError
    exception_bases = (error.ConnectError,)



class TestBadFileError(ConnectErrorTests, unittest.TestCase):
    """
    Tests for L{error.BadFileError}.
    """
    exception_class = error.BadFileError
    exception_bases = (error.ConnectError,)



class TestServiceNameUnknownError(ConnectErrorTests, unittest.TestCase):
    """
    Tests for L{error.ServiceNameUnknownError}.
    """
    exception_class = error.ServiceNameUnknownError
    exception_bases = (error.ConnectError,)



class TestUserError(ConnectErrorTests, unittest.TestCase):
    """
    Tests for L{error.UserError}.
    """
    exception_class = error.UserError
    exception_bases = (error.ConnectError,)



class TestTimeoutError(ConnectErrorTests, unittest.TestCase):
    """
    Tests for L{error.TimeoutError}.
    """
    exception_class = error.TimeoutError
    exception_bases = (error.UserError,)



class TestSSLError(ConnectErrorTests, unittest.TestCase):
    """
    Tests for L{error.SSLError}.
    """
    exception_class = error.SSLError
    exception_bases = (error.ConnectError,)



class TestCannotListenError(GeneralExceptionTests, unittest.TestCase):
    """
    Tests for L{error.CannotListenError}.
    """
    exception_class = error.CannotListenError
    exception_bases = (error.BindError,)
    args = ("eth0", 9, "ENOPONIES")
    message = "Couldn't listen on eth0:9: ENOPONIES."


    def test_init(self):
        """
        Check for attributes particular to L{CannotListenError}.
        """
        self.assertEqual(self.exception.interface, self.args[0])
        self.assertEqual(self.exception.port, self.args[1])
        self.assertEqual(self.exception.socketError, self.args[2])


    def test_no_iface(self):
        """
        Check that the string form of L{CannotListenError} is correct
        when no interface is given."
        """
        exception = self.exception_class(None, self.args[1], self.args[2])
        self.assertEqual(str(exception), "Couldn't listen on any:9: ENOPONIES.")



class TestGetConnectError(unittest.TestCase):
    """
    Tests for L{error.getConnectError}.
    """

    def test_string_only(self):
        """
        Call L{error.getConnectError} with a string.
        """
        exception = error.getConnectError("An Error")
        self.assertIsInstance(exception, error.ConnectError)
        self.assertIdentical(exception.osError, None)
        self.assertEqual(exception.args, ("An Error",))
        
    def test_with_gaierror(self):
        """
        Call L{error.getConnectError} with a paramter which matches the type of
        L{socket.gaierror}.
        """
        self.patch(socket, "gaierror", tuple)
        exception = error.getConnectError((-1, "An Error"))
        self.assertIsInstance(exception, error.UnknownHostError)
        self.assertEqual(exception.osError, -1)
        self.assertEqual(exception.args, ("An Error",))

    def test_mapped(self):
        """
        Call L{error.getConnectError} with a tuple.
        """
        exception = error.getConnectError((errno.ENETUNREACH, "An Error"))
        self.assertIsInstance(exception, error.ConnectError)
        self.assertEqual(exception.osError, errno.ENETUNREACH)
        self.assertEqual(exception.args, ("An Error",))
