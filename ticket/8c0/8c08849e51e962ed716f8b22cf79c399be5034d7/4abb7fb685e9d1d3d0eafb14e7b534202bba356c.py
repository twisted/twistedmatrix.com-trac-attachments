# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
FTP tests.
"""

import os
import errno
from StringIO import StringIO
import getpass

from zope.interface import implements
from zope.interface.verify import verifyClass

from twisted.trial import unittest, util
from twisted.python.randbytes import insecureRandom
from twisted.cred.portal import IRealm
from twisted.protocols import basic
from twisted.internet import reactor, task, protocol, defer, error
from twisted.internet.interfaces import IConsumer
from twisted.cred.error import UnauthorizedLogin
from twisted.cred import portal, checkers, credentials
from twisted.python import failure, filepath, runtime
from twisted.test import proto_helpers

from twisted.protocols import ftp, loopback
# from local.protocols import ftp

# TOM: added for logging
from twisted.python import log


class Dummy(basic.LineReceiver):
    logname = None
    def __init__(self):
        self.lines = []
        self.rawData = []
    def connectionMade(self):
        self.f = self.factory   # to save typing in pdb :-)
    def lineReceived(self,line):
        self.lines.append(line)
    def rawDataReceived(self, data):
        self.rawData.append(data)
    def lineLengthExceeded(self, line):
        pass


class _BufferingProtocol(protocol.Protocol):
    def connectionMade(self):
        self.buffer = ''
        self.d = defer.Deferred()
    def dataReceived(self, data):
        self.buffer += data
    def connectionLost(self, reason):
        self.d.callback(self)




class FTPUserServerTestCase(unittest.TestCase):
    """
    Simple tests for an FTP server with anon access and a user account.
    (Slightly modified from FTPServerTestCase)

    @ivar clientFactory: class used as ftp client.
    """
    clientFactory = ftp.FTPClientBasic
    userAnonymous = "anonymous"

    def setUp(self):
        # Create a directory
        self.directory = self.mktemp()
        os.mkdir(self.directory)
        self.dirPath = filepath.FilePath(self.directory)

        # TOM: Create a directory for user 'tom'
        self.usersPath = self.dirPath.child('users')
        self.tomPath = self.usersPath.child('tom')
        self.tomPath.makedirs()

        # Start the server
        p = portal.Portal(ftp.FTPRealm(self.directory, self.usersPath.path))
        p.registerChecker(checkers.AllowAnonymousAccess(),
                          credentials.IAnonymous)

        # TOM: register one special password
        p.registerChecker(checkers.InMemoryUsernamePasswordDatabaseDontUse(tom='tom'),
                          credentials.IUsernamePassword)
        self.factory = ftp.FTPFactory(portal=p,
                                      userAnonymous=self.userAnonymous)
        port = reactor.listenTCP(0, self.factory, interface="127.0.0.1")

        # TOM: I am still debating whether this is rightly part of the test
        self.addCleanup(port.stopListening)

        # Hook the server's buildProtocol to make the protocol instance
        # accessible to tests.
        buildProtocol = self.factory.buildProtocol
        d1 = defer.Deferred()
        def _rememberProtocolInstance(addr):
            # Done hooking this.
            del self.factory.buildProtocol

            protocol = buildProtocol(addr)
            self.serverProtocol = protocol.wrappedProtocol
            def cleanupServer():
                if self.serverProtocol.transport is not None:
                    self.serverProtocol.transport.loseConnection()
            self.addCleanup(cleanupServer)
            d1.callback(None)
            return protocol
        self.factory.buildProtocol = _rememberProtocolInstance

        # Connect a client to it
        portNum = port.getHost().port
        clientCreator = protocol.ClientCreator(reactor, self.clientFactory)
        d2 = clientCreator.connectTCP("127.0.0.1", portNum)
        def gotClient(client):
            self.client = client
            self.addCleanup(self.client.transport.loseConnection)
        d2.addCallback(gotClient)
        return defer.gatherResults([d1, d2])

    def assertCommandResponse(self, command, expectedResponseLines,
                              chainDeferred=None):
        """Asserts that a sending an FTP command receives the expected
        response.

        Returns a Deferred.  Optionally accepts a deferred to chain its actions
        to.
        """
        if chainDeferred is None:
            chainDeferred = defer.succeed(None)

        def queueCommand(ignored):
            d = self.client.queueStringCommand(command)
            def gotResponse(responseLines):
                self.assertEquals(expectedResponseLines, responseLines)
            return d.addCallback(gotResponse)
        return chainDeferred.addCallback(queueCommand)

    def assertCommandFailed(self, command, expectedResponse=None,
                            chainDeferred=None):
        if chainDeferred is None:
            chainDeferred = defer.succeed(None)

        def queueCommand(ignored):
            return self.client.queueStringCommand(command)
        chainDeferred.addCallback(queueCommand)
        self.assertFailure(chainDeferred, ftp.CommandFailed)
        def failed(exception):
            if expectedResponse is not None:
                self.failUnlessEqual(
                    expectedResponse, exception.args[0])
        return chainDeferred.addCallback(failed)

    def _anonymousLogin(self):
        d = self.assertCommandResponse(
            'USER anonymous',
            ['331 Guest login ok, type your email address as password.'])
        return self.assertCommandResponse(
            'PASS test@twistedmatrix.com',
            ['230 Anonymous login ok, access restrictions apply.'],
            chainDeferred=d)



class TimeoutsFTPServerTestCase(FTPUserServerTestCase):
    """
    Tests in this collection exercise conditions under which the
    server should timeout connections and release resources.  Not all
    tests are self-checking yet, but will be eventually.
    """

    def mywait(self, t):
        """Schedule a deferred t seconds from now."""
        d = defer.Deferred()
        reactor.callLater(t, d.callback, 'A string that yells "foo!"')
        return d

    def test_DTPClosed(self):
        """In an FTP session in which a DTP has been established, when
        the FTP timeout occurs the control channel and any open data
        channels close cleanly."""

        # Set the timeout to something small, but greater than DTPTimeout
        self.serverProtocol.timeOut = 15

        # Login
        wfd = defer.waitForDeferred(self._anonymousLogin())
        yield wfd
        wfd.getResult()
        log.msg("Login Anonymous")

        # Issue a PASV command, and extract the host and port from the response
        pasvCmd = defer.waitForDeferred(self.client.queueStringCommand('PASV'))
        yield pasvCmd
        responseLines = pasvCmd.getResult()
        log.msg("PASV responseLines", responseLines)
        host, port = ftp.decodeHostPort(responseLines[-1][4:])

        # Create a connection on the PASV port
        cc = protocol.ClientCreator(reactor, _BufferingProtocol)
        log.msg("pasv client", cc)
        d = cc.connectTCP('127.0.0.1', port)
        log.msg("pasv conn", d)

        # Confirm the client is connected
        def gotClient(dtp_client):
            log.msg("DTP Client established", dtp_client)
            # self.addCleanup(dtp_client.transport.loseConnection)

        d.addCallback(gotClient)
        wait_get_dtp_client = defer.waitForDeferred(d)
        yield wait_get_dtp_client

        # Wait for N seconds, protocol timeOut will fire
        wait1 = defer.waitForDeferred(self.mywait(20))
        yield wait1

        # Assert that the transport and any dtp is closed
        self.assertEqual(self.serverProtocol.transport, None)
        self.assertEqual(self.serverProtocol.dtpPort, None)

        log.msg("disconnected:", self.serverProtocol.disconnected)
        log.msg("transport:", self.serverProtocol.transport)
        log.msg("dtpPort:", self.serverProtocol.dtpPort)
        log.msg("dtpInstance:", self.serverProtocol.dtpInstance)

    test_DTPClosed = defer.deferredGenerator(test_DTPClosed)

    # test_DTPClosed.skip = "skipping"
