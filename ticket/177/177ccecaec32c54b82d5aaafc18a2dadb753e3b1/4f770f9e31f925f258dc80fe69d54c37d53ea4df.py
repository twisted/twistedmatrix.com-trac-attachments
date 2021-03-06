# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{IReactorTCP} and the TCP parts of
L{IReactorSocket}.
"""

__metaclass__ = type

import socket, errno

from zope.interface import implements

from twisted.python.runtime import platform
from twisted.python.failure import Failure
from twisted.python import log

from twisted.trial.unittest import SkipTest, TestCase
from twisted.internet.test.reactormixins import ReactorBuilder, EndpointCreator
from twisted.internet.test.reactormixins import ConnectableProtocol
from twisted.internet.test.reactormixins import runProtocolsWithReactor
from twisted.internet.error import ConnectionLost, UserError, ConnectionRefusedError
from twisted.internet.error import ConnectionDone, ConnectionAborted
from twisted.internet.interfaces import (
    ILoggingContext, IConnector, IReactorFDSet, IReactorSocket)
from twisted.internet.address import IPv4Address, IPv6Address
from twisted.internet.defer import (
    Deferred, DeferredList, maybeDeferred, gatherResults)
from twisted.internet.endpoints import (
    TCP4ServerEndpoint, TCP4ClientEndpoint)
from twisted.internet.protocol import ServerFactory, ClientFactory, Protocol
from twisted.internet.interfaces import (
    IPushProducer, IPullProducer, IHalfCloseableProtocol)
from twisted.internet.tcp import Connection, Server, _resolveIPv6

from twisted.internet.test.connectionmixins import (
    LogObserverMixin, ConnectionTestsMixin, TCPClientTestsMixin, findFreePort)
from twisted.internet.test.test_core import ObjectModelIntegrationMixin
from twisted.test.test_tcp import MyClientFactory, MyServerFactory
from twisted.test.test_tcp import ClosingFactory, ClientStartStopFactory

try:
    from OpenSSL import SSL
except ImportError:
    useSSL = False
else:
    from twisted.internet.ssl import ClientContextFactory
    useSSL = True

try:
    socket.socket(socket.AF_INET6, socket.SOCK_STREAM).close()
except socket.error, e:
    ipv6Skip = str(e)
else:
    ipv6Skip = None



if platform.isWindows():
    from twisted.internet.test import _win32ifaces
    getLinkLocalIPv6Addresses = _win32ifaces.win32GetLinkLocalIPv6Addresses
else:
    try:
        from twisted.internet.test import _posixifaces
    except ImportError:
        getLinkLocalIPv6Addresses = lambda: []
    else:
        getLinkLocalIPv6Addresses = _posixifaces.posixGetLinkLocalIPv6Addresses



def getLinkLocalIPv6Address():
    """
    Find and return a configured link local IPv6 address including a scope
    identifier using the % separation syntax.  If the system has no link local
    IPv6 addresses, raise L{SkipTest} instead.

    @raise SkipTest: if no link local address can be found or if the
        C{netifaces} module is not available.

    @return: a C{str} giving the address
    """
    addresses = getLinkLocalIPv6Addresses()
    if addresses:
        return addresses[0]
    raise SkipTest("Link local IPv6 address unavailable")



def connect(client, (host, port)):
    if '%' in host or ':' in host:
        address = socket.getaddrinfo(host, port)[0][4]
    else:
        address = (host, port)
    client.connect(address)



class FakeSocket(object):
    """
    A fake for L{socket.socket} objects.

    @ivar data: A C{str} giving the data which will be returned from
        L{FakeSocket.recv}.

    @ivar sendBuffer: A C{list} of the objects passed to L{FakeSocket.send}.
    """
    def __init__(self, data):
        self.data = data
        self.sendBuffer = []

    def setblocking(self, blocking):
        self.blocking = blocking

    def recv(self, size):
        return self.data

    def send(self, bytes):
        """
        I{Send} all of C{bytes} by accumulating it into C{self.sendBuffer}.

        @return: The length of C{bytes}, indicating all the data has been
            accepted.
        """
        self.sendBuffer.append(bytes)
        return len(bytes)


    def shutdown(self, how):
        """
        Shutdown is not implemented.  The method is provided since real sockets
        have it and some code expects it.  No behavior of L{FakeSocket} is
        affected by a call to it.
        """


    def close(self):
        """
        Close is not implemented.  The method is provided since real sockets
        have it and some code expects it.  No behavior of L{FakeSocket} is
        affected by a call to it.
        """


    def setsockopt(self, *args):
        """
        Setsockopt is not implemented.  The method is provided since
        real sockets have it and some code expects it.  No behavior of
        L{FakeSocket} is affected by a call to it.
        """


    def fileno(self):
        """
        Return a fake file descriptor.  If actually used, this will have no
        connection to this L{FakeSocket} and will probably cause surprising
        results.
        """
        return 1



class TestFakeSocket(TestCase):
    """
    Test that the FakeSocket can be used by the doRead method of L{Connection}
    """

    def test_blocking(self):
        skt = FakeSocket("someData")
        skt.setblocking(0)
        self.assertEqual(skt.blocking, 0)


    def test_recv(self):
        skt = FakeSocket("someData")
        self.assertEqual(skt.recv(10), "someData")


    def test_send(self):
        """
        L{FakeSocket.send} accepts the entire string passed to it, adds it to
        its send buffer, and returns its length.
        """
        skt = FakeSocket("")
        count = skt.send("foo")
        self.assertEqual(count, 3)
        self.assertEqual(skt.sendBuffer, ["foo"])



class FakeProtocol(Protocol):
    """
    An L{IProtocol} that returns a value from its dataReceived method.
    """
    def dataReceived(self, data):
        """
        Return something other than C{None} to trigger a deprecation warning for
        that behavior.
        """
        return ()



class _FakeFDSetReactor(object):
    """
    A no-op implementation of L{IReactorFDSet}, which ignores all adds and
    removes.
    """
    implements(IReactorFDSet)

    addReader = addWriter = removeReader = removeWriter = (
        lambda self, desc: None)



class TCPServerTests(TestCase):
    """
    Whitebox tests for L{twisted.internet.tcp.Server}.
    """
    def setUp(self):
        self.reactor = _FakeFDSetReactor()
        class FakePort(object):
            _realPortNumber = 3
        self.skt = FakeSocket("")
        self.protocol = Protocol()
        self.server = Server(
            self.skt, self.protocol, ("", 0), FakePort(), None, self.reactor)


    def test_writeAfterDisconnect(self):
        """
        L{Server.write} discards bytes passed to it if called after it has lost
        its connection.
        """
        self.server.connectionLost(
            Failure(Exception("Simulated lost connection")))
        self.server.write("hello world")
        self.assertEqual(self.skt.sendBuffer, [])


    def test_writeAfteDisconnectAfterTLS(self):
        """
        L{Server.write} discards bytes passed to it if called after it has lost
        its connection when the connection had started TLS.
        """
        self.server.TLS = True
        self.test_writeAfterDisconnect()


    def test_writeSequenceAfterDisconnect(self):
        """
        L{Server.writeSequence} discards bytes passed to it if called after it
        has lost its connection.
        """
        self.server.connectionLost(
            Failure(Exception("Simulated lost connection")))
        self.server.writeSequence(["hello world"])
        self.assertEqual(self.skt.sendBuffer, [])


    def test_writeSequenceAfteDisconnectAfterTLS(self):
        """
        L{Server.writeSequence} discards bytes passed to it if called after it
        has lost its connection when the connection had started TLS.
        """
        self.server.TLS = True
        self.test_writeSequenceAfterDisconnect()



class TCPConnectionTests(TestCase):
    """
    Whitebox tests for L{twisted.internet.tcp.Connection}.
    """
    def test_doReadWarningIsRaised(self):
        """
        When an L{IProtocol} implementation that returns a value from its
        C{dataReceived} method, a deprecated warning is emitted.
        """
        skt = FakeSocket("someData")
        protocol = FakeProtocol()
        conn = Connection(skt, protocol)
        conn.doRead()
        warnings = self.flushWarnings([FakeProtocol.dataReceived])
        self.assertEqual(warnings[0]['category'], DeprecationWarning)
        self.assertEqual(
            warnings[0]["message"],
            "Returning a value other than None from "
            "twisted.internet.test.test_tcp.FakeProtocol.dataReceived "
            "is deprecated since Twisted 11.0.0.")
        self.assertEqual(len(warnings), 1)


    def test_noTLSBeforeStartTLS(self):
        """
        The C{TLS} attribute of a L{Connection} instance is C{False} before
        L{Connection.startTLS} is called.
        """
        skt = FakeSocket("")
        protocol = FakeProtocol()
        conn = Connection(skt, protocol)
        self.assertFalse(conn.TLS)


    def test_tlsAfterStartTLS(self):
        """
        The C{TLS} attribute of a L{Connection} instance is C{True} after
        L{Connection.startTLS} is called.
        """
        skt = FakeSocket("")
        protocol = FakeProtocol()
        conn = Connection(skt, protocol, reactor=_FakeFDSetReactor())
        conn._tlsClientDefault = True
        conn.startTLS(ClientContextFactory(), True)
        self.assertTrue(conn.TLS)
    if not useSSL:
        test_tlsAfterStartTLS.skip = "No SSL support available"



class TCPCreator(EndpointCreator):
    """
    Create IPv4 TCP endpoints for L{runProtocolsWithReactor}-based tests.
    """

    interface = "127.0.0.1"

    def server(self, reactor):
        """
        Create a server-side TCP endpoint.
        """
        return TCP4ServerEndpoint(reactor, 0, interface=self.interface)


    def client(self, reactor, serverAddress):
        """
        Create a client end point that will connect to the given address.

        @type serverAddress: L{IPv4Address}
        """
        return TCP4ClientEndpoint(reactor, self.interface, serverAddress.port)



class TCP6Creator(TCPCreator):
    """
    Create IPv6 TCP endpoints for
    C{ReactorBuilder.runProtocolsWithReactor}-based tests.

    The endpoint types in question here are still the TCP4 variety, since
    these simply pass through IPv6 address literals to the reactor, and we are
    only testing address literals, not name resolution (as name resolution has
    not yet been implemented).  See http://twistedmatrix.com/trac/ticket/4470
    for more specific information about new endpoint classes.  The naming is
    slightly misleading, but presumably if you're passing an IPv6 literal, you
    know what you're asking for.
    """
    def __init__(self):
        self.interface = getLinkLocalIPv6Address()



class TCPTransportTestsMixin(object):
    """
    Tests for functionality which is provided by any TCP transport (IPv4, IPv6,
    client, server).
    """
    def test_largeSendBuffer(self):
        """
        Bytes written to a transport are sent reliably and in order even when
        the local send buffer fills up because writes are done more quickly than
        the network can accept them.
        """
        class LargeProtocol(ConnectableProtocol):
            dataLen = 0

            def dataReceived(self,data):
                self.transport.write(data)
                self.dataLen += len(data)

        class LargeClientProtocol(ConnectableProtocol):
            dataBuffer = b''

            def connectionMade(self):
                self.reactor.callLater(
                    1, self.writeData)
                self.checkd = None
                
            def writeData(self):
                for i in range(0, repBlocks):
                    self.transport.write(smallChunk*ops)
                self.checkd = None
                
            def dataReceived(self,data):
                self.dataBuffer += data
                if not self.checkd:
                    self.checkd = self.reactor.callLater(1, self.extraCheck)

            def connectionLost(self, reason):
                if self.checkd:
                    self.checkd.cancel()
                    self.checkd = None
                ConnectableProtocol.connectionLost(self, reason)

            def extraCheck(self):
                if len(self.dataBuffer) == totalLen:
                    self.normal = True
                    self.transport.loseConnection()
                elif len(self.dataBuffer) > totalLen:
                    self.normal = False
                    self.transport.loseConnection()
                else:
                    pass
                self.checkd = None

        smallChunk = b'X'
        smallLen = len(smallChunk)
        ops = 260000
        repBlocks = 100
        totalLen = smallLen * ops * repBlocks

        server = LargeProtocol()
        client = LargeClientProtocol()
        reactor = runProtocolsWithReactor(
            self, server, client, self.endpoints)

        self.assertTrue(
            client.normal,
            "client received data is abnormal "
            "(%d != %d)" % (len(client.dataBuffer), totalLen))



class TCPClientTestsBase(ReactorBuilder, ConnectionTestsMixin,
                            TCPClientTestsMixin, TCPTransportTestsMixin):
    """
    Base class for builders defining tests related to L{IReactorTCP.connectTCP}.
    """
    port = 1234

    @property
    def interface(self):
        """
        Return the interface attribute from the endpoints object.
        """
        return self.endpoints.interface



class TCP4ClientTestsBuilder(TCPClientTestsBase):
    """
    Builder configured with IPv4 parameters for tests related to L{IReactorTCP.connectTCP}.
    """
    fakeDomainName = 'some-fake.domain.example.com'
    family = socket.AF_INET
    addressClass = IPv4Address

    endpoints = TCPCreator()



class TCP6ClientTestsBuilder(TCPClientTestsBase):
    """
    Builder configured with IPv6 parameters for tests related to L{IReactorTCP.connectTCP}.
    """

    if ipv6Skip:
        skip = "Platform does not support ipv6"

    family = socket.AF_INET6
    addressClass = IPv6Address


    def setUp(self):
        # Only create this object here, so that it won't be created if tests
        # are being skipped:
        self.endpoints = TCP6Creator()
        # This is used by test_addresses to test the distinction between the
        # resolved name and the name on the socket itself.  All the same
        # invariants should hold, but giving back an IPv6 address from a
        # resolver is not something the reactor can handle, so instead, we make
        # it so that the connect call for the IPv6 address test simply uses an
        # address literal.
        self.fakeDomainName = self.endpoints.interface



class TCPConnectorTestsBuilder(ReactorBuilder):

    def test_connectorIdentity(self):
        """
        L{IReactorTCP.connectTCP} returns an object which provides
        L{IConnector}.  The destination of the connector is the address which
        was passed to C{connectTCP}.  The same connector object is passed to
        the factory's C{startedConnecting} method as to the factory's
        C{clientConnectionLost} method.
        """
        serverFactory = ClosingFactory()
        reactor = self.buildReactor()
        tcpPort = reactor.listenTCP(0, serverFactory, interface=self.interface)
        serverFactory.port = tcpPort
        portNumber = tcpPort.getHost().port

        seenConnectors = []
        seenFailures = []

        clientFactory = ClientStartStopFactory()
        clientFactory.clientConnectionLost = (
            lambda connector, reason: (seenConnectors.append(connector),
                                       seenFailures.append(reason)))
        clientFactory.startedConnecting = seenConnectors.append

        connector = reactor.connectTCP(self.interface, portNumber,
                                       clientFactory)
        self.assertTrue(IConnector.providedBy(connector))
        dest = connector.getDestination()
        self.assertEqual(dest.type, "TCP")
        self.assertEqual(dest.host, self.interface)
        self.assertEqual(dest.port, portNumber)

        clientFactory.whenStopped.addBoth(lambda _: reactor.stop())

        self.runReactor(reactor)

        seenFailures[0].trap(ConnectionDone)
        self.assertEqual(seenConnectors, [connector, connector])


    def test_userFail(self):
        """
        Calling L{IConnector.stopConnecting} in C{Factory.startedConnecting}
        results in C{Factory.clientConnectionFailed} being called with
        L{error.UserError} as the reason.
        """
        serverFactory = MyServerFactory()
        reactor = self.buildReactor()
        tcpPort = reactor.listenTCP(0, serverFactory, interface=self.interface)
        portNumber = tcpPort.getHost().port

        fatalErrors = []

        def startedConnecting(connector):
            try:
                connector.stopConnecting()
            except Exception:
                fatalErrors.append(Failure())
                reactor.stop()

        clientFactory = ClientStartStopFactory()
        clientFactory.startedConnecting = startedConnecting

        clientFactory.whenStopped.addBoth(lambda _: reactor.stop())

        reactor.callWhenRunning(lambda: reactor.connectTCP(self.interface,
                                                           portNumber,
                                                           clientFactory))

        self.runReactor(reactor)

        if fatalErrors:
            self.fail(fatalErrors[0].getTraceback())
        clientFactory.reason.trap(UserError)
        self.assertEqual(clientFactory.failed, 1)


    def test_reconnect(self):
        """
        Calling L{IConnector.connect} in C{Factory.clientConnectionLost} causes
        a new connection attempt to be made.
        """
        serverFactory = ClosingFactory()
        reactor = self.buildReactor()
        tcpPort = reactor.listenTCP(0, serverFactory, interface=self.interface)
        serverFactory.port = tcpPort
        portNumber = tcpPort.getHost().port

        clientFactory = MyClientFactory()

        def clientConnectionLost(connector, reason):
            connector.connect()
        clientFactory.clientConnectionLost = clientConnectionLost
        reactor.connectTCP(self.interface, portNumber, clientFactory)

        protocolMadeAndClosed = []
        def reconnectFailed(ignored):
            p = clientFactory.protocol
            protocolMadeAndClosed.append((p.made, p.closed))
            reactor.stop()

        clientFactory.failDeferred.addCallback(reconnectFailed)

        self.runReactor(reactor)

        clientFactory.reason.trap(ConnectionRefusedError)
        self.assertEqual(protocolMadeAndClosed, [(1, 1)])



class TCP4ConnectorTestsBuilder(TCPConnectorTestsBuilder):
    interface = '127.0.0.1'
    family = socket.AF_INET
    addressClass = IPv4Address



class TCP6ConnectorTestsBuilder(TCPConnectorTestsBuilder):
    family = socket.AF_INET6
    addressClass = IPv6Address

    if ipv6Skip:
        skip = "Platform does not support ipv6"

    def setUp(self):
        self.interface = getLinkLocalIPv6Address()



def createTestSocket(test, addressFamily, socketType):
    """
    Create a socket for the duration of the given test.

    @param test: the test to add cleanup to.

    @param addressFamily: an C{AF_*} constant

    @param socketType: a C{SOCK_*} constant.

    @return: a socket object.
    """
    skt = socket.socket(addressFamily, socketType)
    test.addCleanup(skt.close)
    return skt



class StreamTransportTestsMixin(LogObserverMixin):
    """
    Mixin defining tests which apply to any port/connection based transport.
    """
    def test_startedListeningLogMessage(self):
        """
        When a port starts, a message including a description of the associated
        factory is logged.
        """
        loggedMessages = self.observe()
        reactor = self.buildReactor()
        class SomeFactory(ServerFactory):
            implements(ILoggingContext)
            def logPrefix(self):
                return "Crazy Factory"
        factory = SomeFactory()
        p = self.getListeningPort(reactor, factory)
        expectedMessage = self.getExpectedStartListeningLogMessage(
            p, "Crazy Factory")
        self.assertEqual((expectedMessage,), loggedMessages[0]['message'])


    def test_connectionLostLogMsg(self):
        """
        When a connection is lost, an informative message should be logged
        (see L{getExpectedConnectionLostLogMsg}): an address identifying
        the port and the fact that it was closed.
        """

        loggedMessages = []
        def logConnectionLostMsg(eventDict):
            loggedMessages.append(log.textFromEventDict(eventDict))

        reactor = self.buildReactor()
        p = self.getListeningPort(reactor, ServerFactory())
        expectedMessage = self.getExpectedConnectionLostLogMsg(p)
        log.addObserver(logConnectionLostMsg)

        def stopReactor(ignored):
            log.removeObserver(logConnectionLostMsg)
            reactor.stop()

        def doStopListening():
            log.addObserver(logConnectionLostMsg)
            maybeDeferred(p.stopListening).addCallback(stopReactor)

        reactor.callWhenRunning(doStopListening)
        reactor.run()

        self.assertIn(expectedMessage, loggedMessages)


    def test_allNewStyle(self):
        """
        The L{IListeningPort} object is an instance of a class with no
        classic classes in its hierarchy.
        """
        reactor = self.buildReactor()
        port = self.getListeningPort(reactor, ServerFactory())
        self.assertFullyNewStyle(port)


class ListenTCPMixin(object):
    """
    Mixin which uses L{IReactorTCP.listenTCP} to hand out listening TCP ports.
    """
    def getListeningPort(self, reactor, factory, port=0, interface=''):
        """
        Get a TCP port from a reactor.
        """
        return reactor.listenTCP(port, factory, interface=interface)



class SocketTCPMixin(object):
    """
    Mixin which uses L{IReactorSocket.adoptStreamPort} to hand out listening TCP
    ports.
    """
    def getListeningPort(self, reactor, factory, port=0, interface=''):
        """
        Get a TCP port from a reactor, wrapping an already-initialized file
        descriptor.
        """
        if IReactorSocket.providedBy(reactor):
            if ':' in interface:
                domain = socket.AF_INET6
                address = socket.getaddrinfo(interface, port)[0][4]
            else:
                domain = socket.AF_INET
                address = (interface, port)
            portSock = socket.socket(domain)
            portSock.bind(address)
            portSock.listen(3)
            portSock.setblocking(False)
            try:
                return reactor.adoptStreamPort(
                    portSock.fileno(), portSock.family, factory)
            finally:
                # The socket should still be open; fileno will raise if it is
                # not.
                portSock.fileno()
                # Now clean it up, because the rest of the test does not need
                # it.
                portSock.close()
        else:
            raise SkipTest("Reactor does not provide IReactorSocket")



class TCPPortTestsMixin(object):
    """
    Tests for L{IReactorTCP.listenTCP}
    """
    def getExpectedStartListeningLogMessage(self, port, factory):
        """
        Get the message expected to be logged when a TCP port starts listening.
        """
        return "%s starting on %d" % (
            factory, port.getHost().port)


    def getExpectedConnectionLostLogMsg(self, port):
        """
        Get the expected connection lost message for a TCP port.
        """
        return "(TCP Port %s Closed)" % (port.getHost().port,)


    def test_portGetHostOnIPv4(self):
        """
        When no interface is passed to L{IReactorTCP.listenTCP}, the returned
        listening port listens on an IPv4 address.
        """
        reactor = self.buildReactor()
        port = self.getListeningPort(reactor, ServerFactory())
        address = port.getHost()
        self.assertIsInstance(address, IPv4Address)


    def test_portGetHostOnIPv6(self):
        """
        When listening on an IPv6 address, L{IListeningPort.getHost} returns
        an L{IPv6Address} with C{host} and C{port} attributes reflecting the
        address the port is bound to.
        """
        reactor = self.buildReactor()
        host, portNumber = findFreePort(
            family=socket.AF_INET6, interface='::1')[:2]
        port = self.getListeningPort(
            reactor, ServerFactory(), portNumber, host)
        address = port.getHost()
        self.assertIsInstance(address, IPv6Address)
        self.assertEqual('::1', address.host)
        self.assertEqual(portNumber, address.port)
    if ipv6Skip:
        test_portGetHostOnIPv6.skip = ipv6Skip


    def test_portGetHostOnIPv6ScopeID(self):
        """
        When a link-local IPv6 address including a scope identifier is passed as
        the C{interface} argument to L{IReactorTCP.listenTCP}, the resulting
        L{IListeningPort} reports its address as an L{IPv6Address} with a host
        value that includes the scope identifier.
        """
        linkLocal = getLinkLocalIPv6Address()
        reactor = self.buildReactor()
        port = self.getListeningPort(reactor, ServerFactory(), 0, linkLocal)
        address = port.getHost()
        self.assertIsInstance(address, IPv6Address)
        self.assertEqual(linkLocal, address.host)
    if ipv6Skip:
        test_portGetHostOnIPv6ScopeID.skip = ipv6Skip


    def _buildProtocolAddressTest(self, client, interface):
        """
        Connect C{client} to a server listening on C{interface} started with
        L{IReactorTCP.listenTCP} and return the address passed to the factory's
        C{buildProtocol} method.

        @param client: A C{SOCK_STREAM} L{socket.socket} created with an address
            family such that it will be able to connect to a server listening on
            C{interface}.

        @param interface: A C{str} giving an address for a server to listen on.
            This should almost certainly be the loopback address for some
            address family supported by L{IReactorTCP.listenTCP}.

        @return: Whatever object, probably an L{IAddress} provider, is passed to
            a server factory's C{buildProtocol} method when C{client}
            establishes a connection.
        """
        class ObserveAddress(ServerFactory):
            def buildProtocol(self, address):
                reactor.stop()
                self.observedAddress = address
                return Protocol()

        factory = ObserveAddress()
        reactor = self.buildReactor()
        port = self.getListeningPort(reactor, factory, 0, interface)
        client.setblocking(False)
        try:
            connect(client, (port.getHost().host, port.getHost().port))
        except socket.error, (errnum, message):
            self.assertIn(errnum, (errno.EINPROGRESS, errno.EWOULDBLOCK))

        self.runReactor(reactor)

        return factory.observedAddress


    def test_buildProtocolIPv4Address(self):
        """
        When a connection is accepted over IPv4, an L{IPv4Address} is passed
        to the factory's C{buildProtocol} method giving the peer's address.
        """
        interface = '127.0.0.1'
        client = createTestSocket(self, socket.AF_INET, socket.SOCK_STREAM)
        observedAddress = self._buildProtocolAddressTest(client, interface)
        self.assertEqual(
            IPv4Address('TCP', *client.getsockname()), observedAddress)


    def test_buildProtocolIPv6Address(self):
        """
        When a connection is accepted to an IPv6 address, an L{IPv6Address} is
        passed to the factory's C{buildProtocol} method giving the peer's
        address.
        """
        interface = '::1'
        client = createTestSocket(self, socket.AF_INET6, socket.SOCK_STREAM)
        observedAddress = self._buildProtocolAddressTest(client, interface)
        self.assertEqual(
            IPv6Address('TCP', *client.getsockname()[:2]), observedAddress)
    if ipv6Skip:
        test_buildProtocolIPv6Address.skip = ipv6Skip


    def test_buildProtocolIPv6AddressScopeID(self):
        """
        When a connection is accepted to a link-local IPv6 address, an
        L{IPv6Address} is passed to the factory's C{buildProtocol} method
        giving the peer's address, including a scope identifier.
        """
        interface = getLinkLocalIPv6Address()
        client = createTestSocket(self, socket.AF_INET6, socket.SOCK_STREAM)
        observedAddress = self._buildProtocolAddressTest(client, interface)
        self.assertEqual(
            IPv6Address('TCP', *client.getsockname()[:2]), observedAddress)
    if ipv6Skip:
        test_buildProtocolIPv6AddressScopeID.skip = ipv6Skip


    def _serverGetConnectionAddressTest(self, client, interface, which):
        """
        Connect C{client} to a server listening on C{interface} started with
        L{IReactorTCP.listenTCP} and return the address returned by one of the
        server transport's address lookup methods, C{getHost} or C{getPeer}.

        @param client: A C{SOCK_STREAM} L{socket.socket} created with an address
            family such that it will be able to connect to a server listening on
            C{interface}.

        @param interface: A C{str} giving an address for a server to listen on.
            This should almost certainly be the loopback address for some
            address family supported by L{IReactorTCP.listenTCP}.

        @param which: A C{str} equal to either C{"getHost"} or C{"getPeer"}
            determining which address will be returned.

        @return: Whatever object, probably an L{IAddress} provider, is returned
            from the method indicated by C{which}.
        """
        class ObserveAddress(Protocol):
            def makeConnection(self, transport):
                reactor.stop()
                self.factory.address = getattr(transport, which)()

        reactor = self.buildReactor()
        factory = ServerFactory()
        factory.protocol = ObserveAddress
        port = self.getListeningPort(reactor, factory, 0, interface)
        client.setblocking(False)
        try:
            connect(client, (port.getHost().host, port.getHost().port))
        except socket.error, (errnum, message):
            self.assertIn(errnum, (errno.EINPROGRESS, errno.EWOULDBLOCK))
        self.runReactor(reactor)
        return factory.address


    def test_serverGetHostOnIPv4(self):
        """
        When a connection is accepted over IPv4, the server
        L{ITransport.getHost} method returns an L{IPv4Address} giving the
        address on which the server accepted the connection.
        """
        interface = '127.0.0.1'
        client = createTestSocket(self, socket.AF_INET, socket.SOCK_STREAM)
        hostAddress = self._serverGetConnectionAddressTest(
            client, interface, 'getHost')
        self.assertEqual(
            IPv4Address('TCP', *client.getpeername()), hostAddress)


    def test_serverGetHostOnIPv6(self):
        """
        When a connection is accepted over IPv6, the server
        L{ITransport.getHost} method returns an L{IPv6Address} giving the
        address on which the server accepted the connection.
        """
        interface = '::1'
        client = createTestSocket(self, socket.AF_INET6, socket.SOCK_STREAM)
        hostAddress = self._serverGetConnectionAddressTest(
            client, interface, 'getHost')
        self.assertEqual(
            IPv6Address('TCP', *client.getpeername()[:2]), hostAddress)
    if ipv6Skip:
        test_serverGetHostOnIPv6.skip = ipv6Skip


    def test_serverGetHostOnIPv6ScopeID(self):
        """
        When a connection is accepted over IPv6, the server
        L{ITransport.getHost} method returns an L{IPv6Address} giving the
        address on which the server accepted the connection, including the scope
        identifier.
        """
        interface = getLinkLocalIPv6Address()
        client = createTestSocket(self, socket.AF_INET6, socket.SOCK_STREAM)
        hostAddress = self._serverGetConnectionAddressTest(
            client, interface, 'getHost')
        self.assertEqual(
            IPv6Address('TCP', *client.getpeername()[:2]), hostAddress)
    if ipv6Skip:
        test_serverGetHostOnIPv6ScopeID.skip = ipv6Skip


    def test_serverGetPeerOnIPv4(self):
        """
        When a connection is accepted over IPv4, the server
        L{ITransport.getPeer} method returns an L{IPv4Address} giving the
        address of the remote end of the connection.
        """
        interface = '127.0.0.1'
        client = createTestSocket(self, socket.AF_INET, socket.SOCK_STREAM)
        peerAddress = self._serverGetConnectionAddressTest(
            client, interface, 'getPeer')
        self.assertEqual(
            IPv4Address('TCP', *client.getsockname()), peerAddress)


    def test_serverGetPeerOnIPv6(self):
        """
        When a connection is accepted over IPv6, the server
        L{ITransport.getPeer} method returns an L{IPv6Address} giving the
        address on the remote end of the connection.
        """
        interface = '::1'
        client = createTestSocket(self, socket.AF_INET6, socket.SOCK_STREAM)
        peerAddress = self._serverGetConnectionAddressTest(
            client, interface, 'getPeer')
        self.assertEqual(
            IPv6Address('TCP', *client.getsockname()[:2]), peerAddress)
    if ipv6Skip:
        test_serverGetPeerOnIPv6.skip = ipv6Skip


    def test_serverGetPeerOnIPv6ScopeID(self):
        """
        When a connection is accepted over IPv6, the server
        L{ITransport.getPeer} method returns an L{IPv6Address} giving the
        address on the remote end of the connection, including the scope
        identifier.
        """
        interface = getLinkLocalIPv6Address()
        client = createTestSocket(self, socket.AF_INET6, socket.SOCK_STREAM)
        peerAddress = self._serverGetConnectionAddressTest(
            client, interface, 'getPeer')
        self.assertEqual(
            IPv6Address('TCP', *client.getsockname()[:2]), peerAddress)
    if ipv6Skip:
        test_serverGetPeerOnIPv6ScopeID.skip = ipv6Skip



class TCPPortTestsBuilder(ReactorBuilder, ListenTCPMixin, TCPPortTestsMixin,
                          ObjectModelIntegrationMixin,
                          StreamTransportTestsMixin):
    pass



class TCPFDPortTestsBuilder(ReactorBuilder, SocketTCPMixin, TCPPortTestsMixin,
                            ObjectModelIntegrationMixin,
                            StreamTransportTestsMixin):
    pass



class StopStartReadingProtocol(Protocol):
    """
    Protocol that pauses and resumes the transport a few times
    """

    def connectionMade(self):
        self.data = ''
        self.pauseResumeProducing(3)


    def pauseResumeProducing(self, counter):
        """
        Toggle transport read state, then count down.
        """
        self.transport.pauseProducing()
        self.transport.resumeProducing()
        if counter:
            self.factory.reactor.callLater(0,
                    self.pauseResumeProducing, counter - 1)
        else:
            self.factory.reactor.callLater(0,
                    self.factory.ready.callback, self)


    def dataReceived(self, data):
        log.msg('got data', len(data))
        self.data += data
        if len(self.data) == 4*4096:
            self.factory.stop.callback(self.data)



class TCPConnectionTestsBuilder(ReactorBuilder):
    """
    Builder defining tests relating to L{twisted.internet.tcp.Connection}.
    """

    def test_stopStartReading(self):
        """
        This test verifies transport socket read state after multiple
        pause/resumeProducing calls.
        """
        sf = ServerFactory()
        reactor = sf.reactor = self.buildReactor()

        skippedReactors = ["Glib2Reactor", "Gtk2Reactor"]
        reactorClassName = reactor.__class__.__name__
        if reactorClassName in skippedReactors and platform.isWindows():
            raise SkipTest(
                "This test is broken on gtk/glib under Windows.")

        sf.protocol = StopStartReadingProtocol
        sf.ready = Deferred()
        sf.stop = Deferred()
        p = reactor.listenTCP(0, sf)
        port = p.getHost().port
        def proceed(protos, port):
            """
            Send several IOCPReactor's buffers' worth of data.
            """
            self.assertTrue(protos[0])
            self.assertTrue(protos[1])
            protos = protos[0][1], protos[1][1]
            protos[0].transport.write('x' * (2 * 4096) + 'y' * (2 * 4096))
            return (sf.stop.addCallback(cleanup, protos, port)
                           .addCallback(lambda ign: reactor.stop()))

        def cleanup(data, protos, port):
            """
            Make sure IOCPReactor didn't start several WSARecv operations
            that clobbered each other's results.
            """
            self.assertEqual(data, 'x'*(2*4096) + 'y'*(2*4096),
                                 'did not get the right data')
            return DeferredList([
                    maybeDeferred(protos[0].transport.loseConnection),
                    maybeDeferred(protos[1].transport.loseConnection),
                    maybeDeferred(port.stopListening)])

        cc = TCP4ClientEndpoint(reactor, '127.0.0.1', port)
        cf = ClientFactory()
        cf.protocol = Protocol
        d = DeferredList([cc.connect(cf), sf.ready]).addCallback(proceed, p)
        self.runReactor(reactor)
        return d


    def test_connectionLostAfterPausedTransport(self):
        """
        Alice connects to Bob.  Alice writes some bytes and then shuts down the
        connection.  Bob receives the bytes from the connection and then pauses
        the transport object.  Shortly afterwards Bob resumes the transport
        object.  At that point, Bob is notified that the connection has been
        closed.

        This is no problem for most reactors.  The underlying event notification
        API will probably just remind them that the connection has been closed.
        It is a little tricky for win32eventreactor (MsgWaitForMultipleObjects).
        MsgWaitForMultipleObjects will only deliver the close notification once.
        The reactor needs to remember that notification until Bob resumes the
        transport.
        """
        class Pauser(ConnectableProtocol):
            def __init__(self):
                self.events = []

            def dataReceived(self, bytes):
                self.events.append("paused")
                self.transport.pauseProducing()
                self.reactor.callLater(0, self.resume)

            def resume(self):
                self.events.append("resumed")
                self.transport.resumeProducing()

            def connectionLost(self, reason):
                # This is the event you have been waiting for.
                self.events.append("lost")
                ConnectableProtocol.connectionLost(self, reason)

        class Client(ConnectableProtocol):
            def connectionMade(self):
                self.transport.write("some bytes for you")
                self.transport.loseConnection()

        pauser = Pauser()
        runProtocolsWithReactor(self, pauser, Client(), TCPCreator())
        self.assertEqual(pauser.events, ["paused", "resumed", "lost"])


    def test_doubleHalfClose(self):
        """
        If one side half-closes its connection, and then the other side of the
        connection calls C{loseWriteConnection}, and then C{loseConnection} in
        {writeConnectionLost}, the connection is closed correctly.

        This rather obscure case used to fail (see ticket #3037).
        """
        class ListenerProtocol(ConnectableProtocol):
            implements(IHalfCloseableProtocol)

            def readConnectionLost(self):
                self.transport.loseWriteConnection()

            def writeConnectionLost(self):
                self.transport.loseConnection()

        class Client(ConnectableProtocol):
            def connectionMade(self):
                self.transport.loseConnection()

        # If test fails, reactor won't stop and we'll hit timeout:
        runProtocolsWithReactor(
            self, ListenerProtocol(), Client(), TCPCreator())



class WriteSequenceTests(ReactorBuilder):
    """
    Test for L{twisted.internet.abstract.FileDescriptor.writeSequence}.

    @ivar client: the connected client factory to be used in tests.
    @type client: L{MyClientFactory}

    @ivar server: the listening server factory to be used in tests.
    @type server: L{MyServerFactory}
    """
    def setUp(self):
        server = MyServerFactory()
        server.protocolConnectionMade = Deferred()
        server.protocolConnectionLost = Deferred()
        self.server = server

        client = MyClientFactory()
        client.protocolConnectionMade = Deferred()
        client.protocolConnectionLost = Deferred()
        self.client = client


    def setWriteBufferSize(self, transport, value):
        """
        Set the write buffer size for the given transport, mananing possible
        differences (ie, IOCP). Bug #4322 should remove the need of that hack.
        """
        if getattr(transport, "writeBufferSize", None) is not None:
            transport.writeBufferSize = value
        else:
            transport.bufferSize = value


    def test_withoutWrite(self):
        """
        C{writeSequence} sends the data even if C{write} hasn't been called.
        """
        client, server = self.client, self.server
        reactor = self.buildReactor()

        port = reactor.listenTCP(0, server)

        def dataReceived(data):
            log.msg("data received: %r" % data)
            self.assertEquals(data, "Some sequence splitted")
            client.protocol.transport.loseConnection()

        def clientConnected(proto):
            log.msg("client connected %s" % proto)
            proto.transport.writeSequence(["Some ", "sequence ", "splitted"])

        def serverConnected(proto):
            log.msg("server connected %s" % proto)
            proto.dataReceived = dataReceived

        d1 = client.protocolConnectionMade.addCallback(clientConnected)
        d2 = server.protocolConnectionMade.addCallback(serverConnected)
        d3 = server.protocolConnectionLost
        d4 = client.protocolConnectionLost
        d = gatherResults([d1, d2, d3, d4])
        def stop(result):
            reactor.stop()
            return result
        d.addBoth(stop)

        reactor.connectTCP("127.0.0.1", port.getHost().port, client)
        self.runReactor(reactor)


    def test_writeSequenceWithUnicodeRaisesException(self):
        """
        C{writeSequence} with an element in the sequence of type unicode raises
        C{TypeError}.
        """
        client, server = self.client, self.server
        reactor = self.buildReactor()

        port = reactor.listenTCP(0, server)

        reactor.connectTCP("127.0.0.1", port.getHost().port, client)

        def serverConnected(proto):
            log.msg("server connected %s" % proto)
            exc = self.assertRaises(
                TypeError,
                proto.transport.writeSequence, [u"Unicode is not kosher"])
            self.assertEquals(str(exc), "Data must not be unicode")

        d = server.protocolConnectionMade.addCallback(serverConnected)
        d.addErrback(log.err)
        d.addCallback(lambda ignored: reactor.stop())

        self.runReactor(reactor)


    def _producerTest(self, clientConnected):
        """
        Helper for testing producers which call C{writeSequence}.  This will set
        up a connection which a producer can use.  It returns after the
        connection is closed.

        @param clientConnected: A callback which will be invoked with a client
            protocol after a connection is setup.  This is responsible for
            setting up some sort of producer.
        """
        reactor = self.buildReactor()

        port = reactor.listenTCP(0, self.server)

        # The following could probably all be much simpler, but for #5285.

        # First let the server notice the connection
        d1 = self.server.protocolConnectionMade

        # Grab the client connection Deferred now though, so we don't lose it if
        # the client connects before the server.
        d2 = self.client.protocolConnectionMade

        def serverConnected(proto):
            # Now take action as soon as the client is connected
            d2.addCallback(clientConnected)
            return d2
        d1.addCallback(serverConnected)

        d3 = self.server.protocolConnectionLost
        d4 = self.client.protocolConnectionLost

        # After the client is connected and does its producer stuff, wait for
        # the disconnection events.
        def didProducerActions(ignored):
            return gatherResults([d3, d4])
        d1.addCallback(didProducerActions)

        def stop(result):
            reactor.stop()
            return result
        d1.addBoth(stop)

        reactor.connectTCP("127.0.0.1", port.getHost().port, self.client)

        self.runReactor(reactor)


    def test_streamingProducer(self):
        """
        C{writeSequence} pauses its streaming producer if too much data is
        buffered, and then resumes it.
        """
        client, server = self.client, self.server

        class SaveActionProducer(object):
            implements(IPushProducer)
            def __init__(self):
                self.actions = []

            def pauseProducing(self):
                self.actions.append("pause")

            def resumeProducing(self):
                self.actions.append("resume")
                # Unregister the producer so the connection can close
                client.protocol.transport.unregisterProducer()
                # This is why the code below waits for the server connection
                # first - so we have it to close here.  We close the server side
                # because win32evenreactor cannot reliably observe us closing
                # the client side (#5285).
                server.protocol.transport.loseConnection()

            def stopProducing(self):
                self.actions.append("stop")

        producer = SaveActionProducer()

        def clientConnected(proto):
            # Register a streaming producer and verify that it gets paused after
            # it writes more than the local send buffer can hold.
            proto.transport.registerProducer(producer, True)
            self.assertEquals(producer.actions, [])
            self.setWriteBufferSize(proto.transport, 500)
            proto.transport.writeSequence(["x" * 50] * 20)
            self.assertEquals(producer.actions, ["pause"])

        self._producerTest(clientConnected)
        # After the send buffer gets a chance to empty out a bit, the producer
        # should be resumed.
        self.assertEquals(producer.actions, ["pause", "resume"])


    def test_nonStreamingProducer(self):
        """
        C{writeSequence} pauses its producer if too much data is buffered only
        if this is a streaming producer.
        """
        client, server = self.client, self.server
        test = self

        class SaveActionProducer(object):
            implements(IPullProducer)
            def __init__(self):
                self.actions = []

            def resumeProducing(self):
                self.actions.append("resume")
                if self.actions.count("resume") == 2:
                    client.protocol.transport.stopConsuming()
                else:
                    test.setWriteBufferSize(client.protocol.transport, 500)
                    client.protocol.transport.writeSequence(["x" * 50] * 20)

            def stopProducing(self):
                self.actions.append("stop")

        producer = SaveActionProducer()

        def clientConnected(proto):
            # Register a non-streaming producer and verify that it is resumed
            # immediately.
            proto.transport.registerProducer(producer, False)
            self.assertEquals(producer.actions, ["resume"])

        self._producerTest(clientConnected)
        # After the local send buffer empties out, the producer should be
        # resumed again.
        self.assertEquals(producer.actions, ["resume", "resume"])


globals().update(TCP4ClientTestsBuilder.makeTestCaseClasses())
globals().update(TCP6ClientTestsBuilder.makeTestCaseClasses())
globals().update(TCPPortTestsBuilder.makeTestCaseClasses())
globals().update(TCPFDPortTestsBuilder.makeTestCaseClasses())
globals().update(TCPConnectionTestsBuilder.makeTestCaseClasses())
globals().update(TCP4ConnectorTestsBuilder.makeTestCaseClasses())
globals().update(TCP6ConnectorTestsBuilder.makeTestCaseClasses())
globals().update(WriteSequenceTests.makeTestCaseClasses())



class ServerAbortsTwice(ConnectableProtocol):
    """
    Call abortConnection() twice.
    """

    def dataReceived(self, data):
        self.transport.abortConnection()
        self.transport.abortConnection()



class ServerAbortsThenLoses(ConnectableProtocol):
    """
    Call abortConnection() followed by loseConnection().
    """

    def dataReceived(self, data):
        self.transport.abortConnection()
        self.transport.loseConnection()



class AbortServerWritingProtocol(ConnectableProtocol):
    """
    Protocol that writes data upon connection.
    """

    def connectionMade(self):
        """
        Tell the client that the connection is set up and it's time to abort.
        """
        self.transport.write("ready")



class ReadAbortServerProtocol(AbortServerWritingProtocol):
    """
    Server that should never receive any data, except 'X's which are written
    by the other side of the connection before abortConnection, and so might
    possibly arrive.
    """

    def dataReceived(self, data):
        if data.replace('X', ''):
            raise Exception("Unexpectedly received data.")



class NoReadServer(ConnectableProtocol):
    """
    Stop reading immediately on connection.

    This simulates a lost connection that will cause the other side to time
    out, and therefore call abortConnection().
    """

    def connectionMade(self):
        self.transport.stopReading()



class EventualNoReadServer(ConnectableProtocol):
    """
    Like NoReadServer, except we Wait until some bytes have been delivered
    before stopping reading. This means TLS handshake has finished, where
    applicable.
    """

    gotData = False
    stoppedReading = False


    def dataReceived(self, data):
        if not self.gotData:
            self.gotData = True
            self.transport.registerProducer(self, False)
            self.transport.write("hello")


    def resumeProducing(self):
        if self.stoppedReading:
            return
        self.stoppedReading = True
        # We've written out the data:
        self.transport.stopReading()


    def pauseProducing(self):
        pass


    def stopProducing(self):
        pass



class BaseAbortingClient(ConnectableProtocol):
    """
    Base class for abort-testing clients.
    """
    inReactorMethod = False

    def connectionLost(self, reason):
        if self.inReactorMethod:
            raise RuntimeError("BUG: connectionLost was called re-entrantly!")
        ConnectableProtocol.connectionLost(self, reason)



class WritingButNotAbortingClient(BaseAbortingClient):
    """
    Write data, but don't abort.
    """

    def connectionMade(self):
        self.transport.write("hello")



class AbortingClient(BaseAbortingClient):
    """
    Call abortConnection() after writing some data.
    """

    def dataReceived(self, data):
        """
        Some data was received, so the connection is set up.
        """
        self.inReactorMethod = True
        self.writeAndAbort()
        self.inReactorMethod = False


    def writeAndAbort(self):
        # X is written before abortConnection, and so there is a chance it
        # might arrive. Y is written after, and so no Ys should ever be
        # delivered:
        self.transport.write("X" * 10000)
        self.transport.abortConnection()
        self.transport.write("Y" * 10000)



class AbortingTwiceClient(AbortingClient):
    """
    Call abortConnection() twice, after writing some data.
    """

    def writeAndAbort(self):
        AbortingClient.writeAndAbort(self)
        self.transport.abortConnection()



class AbortingThenLosingClient(AbortingClient):
    """
    Call abortConnection() and then loseConnection().
    """

    def writeAndAbort(self):
        AbortingClient.writeAndAbort(self)
        self.transport.loseConnection()



class ProducerAbortingClient(ConnectableProtocol):
    """
    Call abortConnection from doWrite, via resumeProducing.
    """

    inReactorMethod = True
    producerStopped = False

    def write(self):
        self.transport.write("lalala" * 127000)
        self.inRegisterProducer = True
        self.transport.registerProducer(self, False)
        self.inRegisterProducer = False


    def connectionMade(self):
        self.write()


    def resumeProducing(self):
        self.inReactorMethod = True
        if not self.inRegisterProducer:
            self.transport.abortConnection()
        self.inReactorMethod = False


    def stopProducing(self):
        self.producerStopped = True


    def connectionLost(self, reason):
        if not self.producerStopped:
            raise RuntimeError("BUG: stopProducing() was never called.")
        if self.inReactorMethod:
            raise RuntimeError("BUG: connectionLost called re-entrantly!")
        ConnectableProtocol.connectionLost(self, reason)



class StreamingProducerClient(ConnectableProtocol):
    """
    Call abortConnection() when the other side has stopped reading.

    In particular, we want to call abortConnection() only once our local
    socket hits a state where it is no longer writeable. This helps emulate
    the most common use case for abortConnection(), closing a connection after
    a timeout, with write buffers being full.

    Since it's very difficult to know when this actually happens, we just
    write a lot of data, and assume at that point no more writes will happen.
    """
    paused = False
    extraWrites = 0
    inReactorMethod = False

    def connectionMade(self):
        self.write()


    def write(self):
        """
        Write large amount to transport, then wait for a while for buffers to
        fill up.
        """
        self.transport.registerProducer(self, True)
        for i in range(100):
            self.transport.write("1234567890" * 32000)


    def resumeProducing(self):
        self.paused = False


    def stopProducing(self):
        pass


    def pauseProducing(self):
        """
        Called when local buffer fills up.

        The goal is to hit the point where the local file descriptor is not
        writeable (or the moral equivalent). The fact that pauseProducing has
        been called is not sufficient, since that can happen when Twisted's
        buffers fill up but OS hasn't gotten any writes yet. We want to be as
        close as possible to every buffer (including OS buffers) being full.

        So, we wait a bit more after this for Twisted to write out a few
        chunks, then abortConnection.
        """
        if self.paused:
            return
        self.paused = True
        # The amount we wait is arbitrary, we just want to make sure some
        # writes have happened and outgoing OS buffers filled up -- see
        # http://twistedmatrix.com/trac/ticket/5303 for details:
        self.reactor.callLater(0.01, self.doAbort)


    def doAbort(self):
        if not self.paused:
            log.err(RuntimeError("BUG: We should be paused a this point."))
        self.inReactorMethod = True
        self.transport.abortConnection()
        self.inReactorMethod = False


    def connectionLost(self, reason):
        # Tell server to start reading again so it knows to go away:
        self.otherProtocol.transport.startReading()
        ConnectableProtocol.connectionLost(self, reason)



class StreamingProducerClientLater(StreamingProducerClient):
    """
    Call abortConnection() from dataReceived, after bytes have been
    exchanged.
    """

    def connectionMade(self):
        self.transport.write("hello")
        self.gotData = False


    def dataReceived(self, data):
        if not self.gotData:
            self.gotData = True
            self.write()


class ProducerAbortingClientLater(ProducerAbortingClient):
    """
    Call abortConnection from doWrite, via resumeProducing.

    Try to do so after some bytes have already been exchanged, so we
    don't interrupt SSL handshake.
    """

    def connectionMade(self):
        # Override base class connectionMade().
        pass


    def dataReceived(self, data):
        self.write()



class DataReceivedRaisingClient(AbortingClient):
    """
    Call abortConnection(), and then throw exception, from dataReceived.
    """

    def dataReceived(self, data):
        self.transport.abortConnection()
        raise ZeroDivisionError("ONO")



class ResumeThrowsClient(ProducerAbortingClient):
    """
    Call abortConnection() and throw exception from resumeProducing().
    """

    def resumeProducing(self):
        if not self.inRegisterProducer:
            self.transport.abortConnection()
            raise ZeroDivisionError("ono!")


    def connectionLost(self, reason):
        # Base class assertion about stopProducing being called isn't valid;
        # if the we blew up in resumeProducing, consumers are justified in
        # giving up on the producer and not calling stopProducing.
        ConnectableProtocol.connectionLost(self, reason)



class AbortConnectionMixin(object):
    """
    Unit tests for L{ITransport.abortConnection}.
    """
    # Override in subclasses, should be a EndpointCreator instance:
    endpoints = None

    def runAbortTest(self, clientClass, serverClass,
                     clientConnectionLostReason=None):
        """
        A test runner utility function, which hooks up a matched pair of client
        and server protocols.

        We then run the reactor until both sides have disconnected, and then
        verify that the right exception resulted.
        """
        clientExpectedExceptions = (ConnectionAborted, ConnectionLost)
        serverExpectedExceptions = (ConnectionLost, ConnectionDone)
        # In TLS tests we may get SSL.Error instead of ConnectionLost,
        # since we're trashing the TLS protocol layer.
        if useSSL:
            clientExpectedExceptions = clientExpectedExceptions + (SSL.Error,)
            serverExpectedExceptions = serverExpectedExceptions + (SSL.Error,)

        client = clientClass()
        server = serverClass()
        client.otherProtocol = server
        server.otherProtocol = client
        reactor = runProtocolsWithReactor(self, server, client, self.endpoints)

        # Make sure everything was shutdown correctly:
        self.assertEqual(reactor.removeAll(), [])
        # The reactor always has a timeout added in runReactor():
        delayedCalls = reactor.getDelayedCalls()
        self.assertEqual(len(delayedCalls), 1, map(str, delayedCalls))

        if clientConnectionLostReason is not None:
            self.assertIsInstance(
                client.disconnectReason.value,
                (clientConnectionLostReason,) + clientExpectedExceptions)
        else:
            self.assertIsInstance(client.disconnectReason.value,
                                  clientExpectedExceptions)
        self.assertIsInstance(server.disconnectReason.value, serverExpectedExceptions)


    def test_dataReceivedAbort(self):
        """
        abortConnection() is called in dataReceived. The protocol should be
        disconnected, but connectionLost should not be called re-entrantly.
        """
        return self.runAbortTest(AbortingClient, ReadAbortServerProtocol)


    def test_clientAbortsConnectionTwice(self):
        """
        abortConnection() is called twice by client.

        No exception should be thrown, and the connection will be closed.
        """
        return self.runAbortTest(AbortingTwiceClient, ReadAbortServerProtocol)


    def test_clientAbortsConnectionThenLosesConnection(self):
        """
        Client calls abortConnection(), followed by loseConnection().

        No exception should be thrown, and the connection will be closed.
        """
        return self.runAbortTest(AbortingThenLosingClient,
                                 ReadAbortServerProtocol)


    def test_serverAbortsConnectionTwice(self):
        """
        abortConnection() is called twice by server.

        No exception should be thrown, and the connection will be closed.
        """
        return self.runAbortTest(WritingButNotAbortingClient, ServerAbortsTwice,
                                 clientConnectionLostReason=ConnectionLost)


    def test_serverAbortsConnectionThenLosesConnection(self):
        """
        Server calls abortConnection(), followed by loseConnection().

        No exception should be thrown, and the connection will be closed.
        """
        return self.runAbortTest(WritingButNotAbortingClient,
                                 ServerAbortsThenLoses,
                                 clientConnectionLostReason=ConnectionLost)


    def test_resumeProducingAbort(self):
        """
        abortConnection() is called in resumeProducing, before any bytes have
        been exchanged. The protocol should be disconnected, but
        connectionLost should not be called re-entrantly.
        """
        self.runAbortTest(ProducerAbortingClient,
                          ConnectableProtocol)


    def test_resumeProducingAbortLater(self):
        """
        abortConnection() is called in resumeProducing, after some
        bytes have been exchanged. The protocol should be disconnected.
        """
        return self.runAbortTest(ProducerAbortingClientLater,
                                 AbortServerWritingProtocol)


    def test_fullWriteBuffer(self):
        """
        abortConnection() triggered by the write buffer being full.

        In particular, the server side stops reading. This is supposed
        to simulate a realistic timeout scenario where the client
        notices the server is no longer accepting data.

        The protocol should be disconnected, but connectionLost should not be
        called re-entrantly.
        """
        self.runAbortTest(StreamingProducerClient,
                          NoReadServer)


    def test_fullWriteBufferAfterByteExchange(self):
        """
        abortConnection() is triggered by a write buffer being full.

        However, this buffer is filled after some bytes have been exchanged,
        allowing a TLS handshake if we're testing TLS. The connection will
        then be lost.
        """
        return self.runAbortTest(StreamingProducerClientLater,
                                 EventualNoReadServer)


    def test_dataReceivedThrows(self):
        """
        dataReceived calls abortConnection(), and then raises an exception.

        The connection will be lost, with the thrown exception
        (C{ZeroDivisionError}) as the reason on the client. The idea here is
        that bugs should not be masked by abortConnection, in particular
        unexpected exceptions.
        """
        self.runAbortTest(DataReceivedRaisingClient,
                          AbortServerWritingProtocol,
                          clientConnectionLostReason=ZeroDivisionError)
        errors = self.flushLoggedErrors(ZeroDivisionError)
        self.assertEquals(len(errors), 1)


    def test_resumeProducingThrows(self):
        """
        resumeProducing calls abortConnection(), and then raises an exception.

        The connection will be lost, with the thrown exception
        (C{ZeroDivisionError}) as the reason on the client. The idea here is
        that bugs should not be masked by abortConnection, in particular
        unexpected exceptions.
        """
        self.runAbortTest(ResumeThrowsClient,
                          ConnectableProtocol,
                          clientConnectionLostReason=ZeroDivisionError)
        errors = self.flushLoggedErrors(ZeroDivisionError)
        self.assertEquals(len(errors), 1)



class AbortConnectionTestCase(ReactorBuilder, AbortConnectionMixin):
    """
    TCP-specific L{AbortConnectionMixin} tests.
    """

    endpoints = TCPCreator()

globals().update(AbortConnectionTestCase.makeTestCaseClasses())



class SimpleUtilityTestCase(TestCase):
    """
    Simple, direct tests for helpers within L{twisted.internet.tcp}.
    """

    skip = ipv6Skip

    def test_resolveNumericHost(self):
        """
        L{_resolveIPv6} raises a L{socket.gaierror} (L{socket.EAI_NONAME}) when
        invoked with a non-numeric host.  (In other words, it is passing
        L{socket.AI_NUMERICHOST} to L{socket.getaddrinfo} and will not
        accidentally block if it receives bad input.)
        """
        err = self.assertRaises(socket.gaierror, _resolveIPv6, "localhost", 1)
        self.assertEqual(err.args[0], socket.EAI_NONAME)


    def test_resolveNumericService(self):
        """
        L{_resolveIPv6} raises a L{socket.gaierror} (L{socket.EAI_NONAME}) when
        invoked with a non-numeric port.  (In other words, it is passing
        L{socket.AI_NUMERICSERV} to L{socket.getaddrinfo} and will not
        accidentally block if it receives bad input.)
        """
        err = self.assertRaises(socket.gaierror, _resolveIPv6, "::1", "http")
        self.assertEqual(err.args[0], socket.EAI_NONAME)

    if platform.isWindows():
        test_resolveNumericService.skip = ("The AI_NUMERICSERV flag is not "
                                           "supported by Microsoft providers.")
        # http://msdn.microsoft.com/en-us/library/windows/desktop/ms738520.aspx


    def test_resolveIPv6(self):
        """
        L{_resolveIPv6} discovers the flow info and scope ID of an IPv6
        address.
        """
        result = _resolveIPv6("::1", 2)
        self.assertEqual(len(result), 4)
        # We can't say anything more useful about these than that they're
        # integers, because the whole point of getaddrinfo is that you can never
        # know a-priori know _anything_ about the network interfaces of the
        # computer that you're on and you have to ask it.
        self.assertIsInstance(result[2], int) # flow info
        self.assertIsInstance(result[3], int) # scope id
        # but, luckily, IP presentation format and what it means to be a port
        # number are a little better specified.
        self.assertEqual(result[:2], ("::1", 2))



