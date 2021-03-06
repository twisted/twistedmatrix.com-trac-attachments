# Copyright (c) 2005 Divmod, Inc.
# Copyright (c) 2007-2009 Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.protocols.amp}.
"""

from zope.interface.verify import verifyObject

from twisted.python import filepath
from twisted.python.failure import Failure
from twisted.protocols import amp
from twisted.trial import unittest
from twisted.internet import protocol, defer, error, reactor, interfaces
from twisted.test import iosim
from twisted.test.proto_helpers import StringTransport

try:
    from twisted.internet import ssl
except ImportError:
    ssl = None
if ssl and not ssl.supported:
    ssl = None

if ssl is None:
    skipSSL = "SSL not available"
else:
    skipSSL = None


class TestProto(protocol.Protocol):
    def __init__(self, onConnLost, dataToSend):
        self.onConnLost = onConnLost
        self.dataToSend = dataToSend

    def connectionMade(self):
        self.data = []
        self.transport.write(self.dataToSend)

    def dataReceived(self, bytes):
        self.data.append(bytes)
        # self.transport.loseConnection()

    def connectionLost(self, reason):
        self.onConnLost.callback(self.data)



class SimpleSymmetricProtocol(amp.AMP):

    def sendHello(self, text):
        return self.callRemoteString(
            "hello",
            hello=text)

    def amp_HELLO(self, box):
        return amp.Box(hello=box['hello'])

    def amp_HOWDOYOUDO(self, box):
        return amp.QuitBox(howdoyoudo='world')



class UnfriendlyGreeting(Exception):
    """Greeting was insufficiently kind.
    """

class DeathThreat(Exception):
    """Greeting was insufficiently kind.
    """

class UnknownProtocol(Exception):
    """Asked to switch to the wrong protocol.
    """


class TransportPeer(amp.Argument):
    # this serves as some informal documentation for how to get variables from
    # the protocol or your environment and pass them to methods as arguments.
    def retrieve(self, d, name, proto):
        return ''

    def fromStringProto(self, notAString, proto):
        return proto.transport.getPeer()

    def toBox(self, name, strings, objects, proto):
        return



class Hello(amp.Command):

    commandName = 'hello'

    arguments = [('hello', amp.String()),
                 ('optional', amp.Boolean(optional=True)),
                 ('print', amp.Unicode(optional=True)),
                 ('from', TransportPeer(optional=True)),
                 ('mixedCase', amp.String(optional=True)),
                 ('dash-arg', amp.String(optional=True)),
                 ('underscore_arg', amp.String(optional=True))]

    response = [('hello', amp.String()),
                ('print', amp.Unicode(optional=True))]

    errors = {UnfriendlyGreeting: 'UNFRIENDLY'}

    fatalErrors = {DeathThreat: 'DEAD'}

class NoAnswerHello(Hello):
    commandName = Hello.commandName
    requiresAnswer = False

class FutureHello(amp.Command):
    commandName = 'hello'

    arguments = [('hello', amp.String()),
                 ('optional', amp.Boolean(optional=True)),
                 ('print', amp.Unicode(optional=True)),
                 ('from', TransportPeer(optional=True)),
                 ('bonus', amp.String(optional=True)), # addt'l arguments
                                                       # should generally be
                                                       # added at the end, and
                                                       # be optional...
                 ]

    response = [('hello', amp.String()),
                ('print', amp.Unicode(optional=True))]

    errors = {UnfriendlyGreeting: 'UNFRIENDLY'}

class WTF(amp.Command):
    """
    An example of an invalid command.
    """


class BrokenReturn(amp.Command):
    """ An example of a perfectly good command, but the handler is going to return
    None...
    """

    commandName = 'broken_return'

class Goodbye(amp.Command):
    # commandName left blank on purpose: this tests implicit command names.
    response = [('goodbye', amp.String())]
    responseType = amp.QuitBox

class Howdoyoudo(amp.Command):
    commandName = 'howdoyoudo'
    # responseType = amp.QuitBox

class WaitForever(amp.Command):
    commandName = 'wait_forever'

class GetList(amp.Command):
    commandName = 'getlist'
    arguments = [('length', amp.Integer())]
    response = [('body', amp.AmpList([('x', amp.Integer())]))]

class SecuredPing(amp.Command):
    # XXX TODO: actually make this refuse to send over an insecure connection
    response = [('pinged', amp.Boolean())]

class TestSwitchProto(amp.ProtocolSwitchCommand):
    commandName = 'Switch-Proto'

    arguments = [
        ('name', amp.String()),
        ]
    errors = {UnknownProtocol: 'UNKNOWN'}

class SingleUseFactory(protocol.ClientFactory):
    def __init__(self, proto):
        self.proto = proto
        self.proto.factory = self

    def buildProtocol(self, addr):
        p, self.proto = self.proto, None
        return p

    reasonFailed = None

    def clientConnectionFailed(self, connector, reason):
        self.reasonFailed = reason
        return

THING_I_DONT_UNDERSTAND = 'gwebol nargo'
class ThingIDontUnderstandError(Exception):
    pass

class FactoryNotifier(amp.AMP):
    factory = None
    def connectionMade(self):
        if self.factory is not None:
            self.factory.theProto = self
            if hasattr(self.factory, 'onMade'):
                self.factory.onMade.callback(None)

    def emitpong(self):
        from twisted.internet.interfaces import ISSLTransport
        if not ISSLTransport.providedBy(self.transport):
            raise DeathThreat("only send secure pings over secure channels")
        return {'pinged': True}
    SecuredPing.responder(emitpong)


class SimpleSymmetricCommandProtocol(FactoryNotifier):
    maybeLater = None
    def __init__(self, onConnLost=None):
        amp.AMP.__init__(self)
        self.onConnLost = onConnLost

    def sendHello(self, text):
        return self.callRemote(Hello, hello=text)

    def sendUnicodeHello(self, text, translation):
        return self.callRemote(Hello, hello=text, Print=translation)

    greeted = False

    def cmdHello(self, hello, From, optional=None, Print=None,
                 mixedCase=None, dash_arg=None, underscore_arg=None):
        assert From == self.transport.getPeer()
        if hello == THING_I_DONT_UNDERSTAND:
            raise ThingIDontUnderstandError()
        if hello.startswith('fuck'):
            raise UnfriendlyGreeting("Don't be a dick.")
        if hello == 'die':
            raise DeathThreat("aieeeeeeeee")
        result = dict(hello=hello)
        if Print is not None:
            result.update(dict(Print=Print))
        self.greeted = True
        return result
    Hello.responder(cmdHello)

    def cmdGetlist(self, length):
        return {'body': [dict(x=1)] * length}
    GetList.responder(cmdGetlist)

    def waitforit(self):
        self.waiting = defer.Deferred()
        return self.waiting
    WaitForever.responder(waitforit)

    def howdo(self):
        return dict(howdoyoudo='world')
    Howdoyoudo.responder(howdo)

    def saybye(self):
        return dict(goodbye="everyone")
    Goodbye.responder(saybye)

    def switchToTestProtocol(self, fail=False):
        if fail:
            name = 'no-proto'
        else:
            name = 'test-proto'
        p = TestProto(self.onConnLost, SWITCH_CLIENT_DATA)
        return self.callRemote(
            TestSwitchProto,
            SingleUseFactory(p), name=name).addCallback(lambda ign: p)

    def switchit(self, name):
        if name == 'test-proto':
            return TestProto(self.onConnLost, SWITCH_SERVER_DATA)
        raise UnknownProtocol(name)
    TestSwitchProto.responder(switchit)

    def donothing(self):
        return None
    BrokenReturn.responder(donothing)


class DeferredSymmetricCommandProtocol(SimpleSymmetricCommandProtocol):
    def switchit(self, name):
        if name == 'test-proto':
            self.maybeLaterProto = TestProto(self.onConnLost, SWITCH_SERVER_DATA)
            self.maybeLater = defer.Deferred()
            return self.maybeLater
        raise UnknownProtocol(name)
    TestSwitchProto.responder(switchit)

class BadNoAnswerCommandProtocol(SimpleSymmetricCommandProtocol):
    def badResponder(self, hello, From, optional=None, Print=None,
                     mixedCase=None, dash_arg=None, underscore_arg=None):
        """
        This responder does nothing and forgets to return a dictionary.
        """
    NoAnswerHello.responder(badResponder)

class NoAnswerCommandProtocol(SimpleSymmetricCommandProtocol):
    def goodNoAnswerResponder(self, hello, From, optional=None, Print=None,
                              mixedCase=None, dash_arg=None, underscore_arg=None):
        return dict(hello=hello+"-noanswer")
    NoAnswerHello.responder(goodNoAnswerResponder)

def connectedServerAndClient(ServerClass=SimpleSymmetricProtocol,
                             ClientClass=SimpleSymmetricProtocol,
                             *a, **kw):
    """Returns a 3-tuple: (client, server, pump)
    """
    return iosim.connectedServerAndClient(
        ServerClass, ClientClass,
        *a, **kw)

class TotallyDumbProtocol(protocol.Protocol):
    buf = ''
    def dataReceived(self, data):
        self.buf += data

class LiteralAmp(amp.AMP):
    def __init__(self):
        self.boxes = []

    def ampBoxReceived(self, box):
        self.boxes.append(box)
        return

class ParsingTest(unittest.TestCase):

    def test_booleanValues(self):
        """
        Verify that the Boolean parser parses 'True' and 'False', but nothing
        else.
        """
        b = amp.Boolean()
        self.assertEquals(b.fromString("True"), True)
        self.assertEquals(b.fromString("False"), False)
        self.assertRaises(TypeError, b.fromString, "ninja")
        self.assertRaises(TypeError, b.fromString, "true")
        self.assertRaises(TypeError, b.fromString, "TRUE")
        self.assertEquals(b.toString(True), 'True')
        self.assertEquals(b.toString(False), 'False')

    def test_pathValueRoundTrip(self):
        """
        Verify the 'Path' argument can parse and emit a file path.
        """
        fp = filepath.FilePath(self.mktemp())
        p = amp.Path()
        s = p.toString(fp)
        v = p.fromString(s)
        self.assertNotIdentical(fp, v) # sanity check
        self.assertEquals(fp, v)


    def test_sillyEmptyThing(self):
        """
        Test that empty boxes raise an error; they aren't supposed to be sent
        on purpose.
        """
        a = amp.AMP()
        return self.assertRaises(amp.NoEmptyBoxes, a.ampBoxReceived, amp.Box())


    def test_ParsingRoundTrip(self):
        """
        Verify that various kinds of data make it through the encode/parse
        round-trip unharmed.
        """
        c, s, p = connectedServerAndClient(ClientClass=LiteralAmp,
                                           ServerClass=LiteralAmp)

        SIMPLE = ('simple', 'test')
        CE = ('ceq', ': ')
        CR = ('crtest', 'test\r')
        LF = ('lftest', 'hello\n')
        NEWLINE = ('newline', 'test\r\none\r\ntwo')
        NEWLINE2 = ('newline2', 'test\r\none\r\n two')
        BLANKLINE = ('newline3', 'test\r\n\r\nblank\r\n\r\nline')
        BODYTEST = ('body', 'blah\r\n\r\ntesttest')

        testData = [
            [SIMPLE],
            [SIMPLE, BODYTEST],
            [SIMPLE, CE],
            [SIMPLE, CR],
            [SIMPLE, CE, CR, LF],
            [CE, CR, LF],
            [SIMPLE, NEWLINE, CE, NEWLINE2],
            [BODYTEST, SIMPLE, NEWLINE]
            ]

        for test in testData:
            jb = amp.Box()
            jb.update(dict(test))
            jb._sendTo(c)
            p.flush()
            self.assertEquals(s.boxes[-1], jb)



class FakeLocator(object):
    """
    This is a fake implementation of the interface implied by
    L{CommandLocator}.
    """
    def __init__(self):
        """
        Remember the given keyword arguments as a set of responders.
        """
        self.commands = {}


    def locateResponder(self, commandName):
        """
        Look up and return a function passed as a keyword argument of the given
        name to the constructor.
        """
        return self.commands[commandName]


class FakeSender:
    """
    This is a fake implementation of the 'box sender' interface implied by
    L{AMP}.
    """
    def __init__(self):
        """
        Create a fake sender and initialize the list of received boxes and
        unhandled errors.
        """
        self.sentBoxes = []
        self.unhandledErrors = []
        self.expectedErrors = 0


    def expectError(self):
        """
        Expect one error, so that the test doesn't fail.
        """
        self.expectedErrors += 1


    def sendBox(self, box):
        """
        Accept a box, but don't do anything.
        """
        self.sentBoxes.append(box)


    def unhandledError(self, failure):
        """
        Deal with failures by instantly re-raising them for easier debugging.
        """
        self.expectedErrors -= 1
        if self.expectedErrors < 0:
            failure.raiseException()
        else:
            self.unhandledErrors.append(failure)



class CommandDispatchTests(unittest.TestCase):
    """
    The AMP CommandDispatcher class dispatches converts AMP boxes into commands
    and responses using Command.responder decorator.

    Note: Originally, AMP's factoring was such that many tests for this
    functionality are now implemented as full round-trip tests in L{AMPTest}.
    Future tests should be written at this level instead, to ensure API
    compatibility and to provide more granular, readable units of test
    coverage.
    """

    def setUp(self):
        """
        Create a dispatcher to use.
        """
        self.locator = FakeLocator()
        self.sender = FakeSender()
        self.dispatcher = amp.BoxDispatcher(self.locator)
        self.dispatcher.startReceivingBoxes(self.sender)


    def test_receivedAsk(self):
        """
        L{CommandDispatcher.ampBoxReceived} should locate the appropriate
        command in its responder lookup, based on the '_ask' key.
        """
        received = []
        def thunk(box):
            received.append(box)
            return amp.Box({"hello": "goodbye"})
        input = amp.Box(_command="hello",
                        _ask="test-command-id",
                        hello="world")
        self.locator.commands['hello'] = thunk
        self.dispatcher.ampBoxReceived(input)
        self.assertEquals(received, [input])


    def test_sendUnhandledError(self):
        """
        L{CommandDispatcher} should relay its unhandled errors in responding to
        boxes to its boxSender.
        """
        err = RuntimeError("something went wrong, oh no")
        self.sender.expectError()
        self.dispatcher.unhandledError(Failure(err))
        self.assertEqual(len(self.sender.unhandledErrors), 1)
        self.assertEqual(self.sender.unhandledErrors[0].value, err)


    def test_unhandledSerializationError(self):
        """
        Errors during serialization ought to be relayed to the sender's
        unhandledError method.
        """
        err = RuntimeError("something undefined went wrong")
        def thunk(result):
            class BrokenBox(amp.Box):
                def _sendTo(self, proto):
                    raise err
            return BrokenBox()
        self.locator.commands['hello'] = thunk
        input = amp.Box(_command="hello",
                        _ask="test-command-id",
                        hello="world")
        self.sender.expectError()
        self.dispatcher.ampBoxReceived(input)
        self.assertEquals(len(self.sender.unhandledErrors), 1)
        self.assertEquals(self.sender.unhandledErrors[0].value, err)


    def test_callRemote(self):
        """
        L{CommandDispatcher.callRemote} should emit a properly formatted '_ask'
        box to its boxSender and record an outstanding L{Deferred}.  When a
        corresponding '_answer' packet is received, the L{Deferred} should be
        fired, and the results translated via the given L{Command}'s response
        de-serialization.
        """
        D = self.dispatcher.callRemote(Hello, hello='world')
        self.assertEquals(self.sender.sentBoxes,
                          [amp.AmpBox(_command="hello",
                                      _ask="1",
                                      hello="world")])
        answers = []
        D.addCallback(answers.append)
        self.assertEquals(answers, [])
        self.dispatcher.ampBoxReceived(amp.AmpBox({'hello': "yay",
                                                   'print': "ignored",
                                                   '_answer': "1"}))
        self.assertEquals(answers, [dict(hello="yay",
                                         Print=u"ignored")])


class SimpleGreeting(amp.Command):
    """
    A very simple greeting command that uses a few basic argument types.
    """
    commandName = 'simple'
    arguments = [('greeting', amp.Unicode()),
                 ('cookie', amp.Integer())]
    response = [('cookieplus', amp.Integer())]


class TestLocator(amp.CommandLocator):
    """
    A locator which implements a responder to a 'hello' command.
    """
    def __init__(self):
        self.greetings = []


    def greetingResponder(self, greeting, cookie):
        self.greetings.append((greeting, cookie))
        return dict(cookieplus=cookie + 3)
    greetingResponder = SimpleGreeting.responder(greetingResponder)



class OverrideLocatorAMP(amp.AMP):
    def __init__(self):
        amp.AMP.__init__(self)
        self.customResponder = object()
        self.expectations = {"custom": self.customResponder}
        self.greetings = []


    def lookupFunction(self, name):
        """
        Override the deprecated lookupFunction function.
        """
        if name in self.expectations:
            result = self.expectations[name]
            return result
        else:
            return super(OverrideLocatorAMP, self).lookupFunction(name)


    def greetingResponder(self, greeting, cookie):
        self.greetings.append((greeting, cookie))
        return dict(cookieplus=cookie + 3)
    greetingResponder = SimpleGreeting.responder(greetingResponder)




class CommandLocatorTests(unittest.TestCase):
    """
    The CommandLocator should enable users to specify responders to commands as
    functions that take structured objects, annotated with metadata.
    """

    def test_responderDecorator(self):
        """
        A method on a L{CommandLocator} subclass decorated with a L{Command}
        subclass's L{responder} decorator should be returned from
        locateResponder, wrapped in logic to serialize and deserialize its
        arguments.
        """
        locator = TestLocator()
        responderCallable = locator.locateResponder("simple")
        result = responderCallable(amp.Box(greeting="ni hao", cookie="5"))
        def done(values):
            self.assertEquals(values, amp.AmpBox(cookieplus='8'))
        return result.addCallback(done)


    def test_lookupFunctionDeprecatedOverride(self):
        """
        Subclasses which override locateResponder under its old name,
        lookupFunction, should have the override invoked instead.  (This tests
        an AMP subclass, because in the version of the code that could invoke
        this deprecated code path, there was no L{CommandLocator}.)
        """
        locator = OverrideLocatorAMP()
        customResponderObject = self.assertWarns(
            PendingDeprecationWarning,
            "Override locateResponder, not lookupFunction.",
            __file__, lambda : locator.locateResponder("custom"))
        self.assertEquals(locator.customResponder, customResponderObject)
        # Make sure upcalling works too
        normalResponderObject = self.assertWarns(
            PendingDeprecationWarning,
            "Override locateResponder, not lookupFunction.",
            __file__, lambda : locator.locateResponder("simple"))
        result = normalResponderObject(amp.Box(greeting="ni hao", cookie="5"))
        def done(values):
            self.assertEquals(values, amp.AmpBox(cookieplus='8'))
        return result.addCallback(done)


    def test_lookupFunctionDeprecatedInvoke(self):
        """
        Invoking locateResponder under its old name, lookupFunction, should
        emit a deprecation warning, but do the same thing.
        """
        locator = TestLocator()
        responderCallable = self.assertWarns(
            PendingDeprecationWarning,
            "Call locateResponder, not lookupFunction.", __file__,
            lambda : locator.lookupFunction("simple"))
        result = responderCallable(amp.Box(greeting="ni hao", cookie="5"))
        def done(values):
            self.assertEquals(values, amp.AmpBox(cookieplus='8'))
        return result.addCallback(done)



SWITCH_CLIENT_DATA = 'Success!'
SWITCH_SERVER_DATA = 'No, really.  Success.'


class BinaryProtocolTests(unittest.TestCase):
    """
    Tests for L{amp.BinaryBoxProtocol}.

    @ivar _boxSender: After C{startReceivingBoxes} is called, the L{IBoxSender}
        which was passed to it.
    """

    def setUp(self):
        """
        Keep track of all boxes received by this test in its capacity as an
        L{IBoxReceiver} implementor.
        """
        self.boxes = []
        self.data = []


    def startReceivingBoxes(self, sender):
        """
        Implement L{IBoxReceiver.startReceivingBoxes} to just remember the
        value passed in.
        """
        self._boxSender = sender


    def ampBoxReceived(self, box):
        """
        A box was received by the protocol.
        """
        self.boxes.append(box)

    stopReason = None
    def stopReceivingBoxes(self, reason):
        """
        Record the reason that we stopped receiving boxes.
        """
        self.stopReason = reason


    # fake ITransport
    def getPeer(self):
        return 'no peer'


    def getHost(self):
        return 'no host'


    def write(self, data):
        self.data.append(data)


    def test_startReceivingBoxes(self):
        """
        When L{amp.BinaryBoxProtocol} is connected to a transport, it calls
        C{startReceivingBoxes} on its L{IBoxReceiver} with itself as the
        L{IBoxSender} parameter.
        """
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(None)
        self.assertIdentical(self._boxSender, protocol)


    def test_sendBoxInStartReceivingBoxes(self):
        """
        The L{IBoxReceiver} which is started when L{amp.BinaryBoxProtocol} is
        connected to a transport can call C{sendBox} on the L{IBoxSender}
        passed to it before C{startReceivingBoxes} returns and have that box
        sent.
        """
        class SynchronouslySendingReceiver:
            def startReceivingBoxes(self, sender):
                sender.sendBox(amp.Box({'foo': 'bar'}))

        transport = StringTransport()
        protocol = amp.BinaryBoxProtocol(SynchronouslySendingReceiver())
        protocol.makeConnection(transport)
        self.assertEqual(
            transport.value(),
            '\x00\x03foo\x00\x03bar\x00\x00')


    def test_receiveBoxStateMachine(self):
        """
        When a binary box protocol receives:
            * a key
            * a value
            * an empty string
        it should emit a box and send it to its boxReceiver.
        """
        a = amp.BinaryBoxProtocol(self)
        a.stringReceived("hello")
        a.stringReceived("world")
        a.stringReceived("")
        self.assertEquals(self.boxes, [amp.AmpBox(hello="world")])


    def test_firstBoxFirstKeyExcessiveLength(self):
        """
        L{amp.BinaryBoxProtocol} drops its connection if the length prefix for
        the first a key it receives is larger than 255.
        """
        transport = StringTransport()
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(transport)
        protocol.dataReceived('\x01\x00')
        self.assertTrue(transport.disconnecting)


    def test_firstBoxSubsequentKeyExcessiveLength(self):
        """
        L{amp.BinaryBoxProtocol} drops its connection if the length prefix for
        a subsequent key in the first box it receives is larger than 255.
        """
        transport = StringTransport()
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(transport)
        protocol.dataReceived('\x00\x01k\x00\x01v')
        self.assertFalse(transport.disconnecting)
        protocol.dataReceived('\x01\x00')
        self.assertTrue(transport.disconnecting)


    def test_subsequentBoxFirstKeyExcessiveLength(self):
        """
        L{amp.BinaryBoxProtocol} drops its connection if the length prefix for
        the first key in a subsequent box it receives is larger than 255.
        """
        transport = StringTransport()
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(transport)
        protocol.dataReceived('\x00\x01k\x00\x01v\x00\x00')
        self.assertFalse(transport.disconnecting)
        protocol.dataReceived('\x01\x00')
        self.assertTrue(transport.disconnecting)


    def test_excessiveKeyFailure(self):
        """
        If L{amp.BinaryBoxProtocol} disconnects because it received a key
        length prefix which was too large, the L{IBoxReceiver}'s
        C{stopReceivingBoxes} method is called with a L{TooLong} failure.
        """
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(StringTransport())
        protocol.dataReceived('\x01\x00')
        protocol.connectionLost(
            Failure(error.ConnectionDone("simulated connection done")))
        self.stopReason.trap(amp.TooLong)
        self.assertTrue(self.stopReason.value.isKey)
        self.assertFalse(self.stopReason.value.isLocal)
        self.assertIdentical(self.stopReason.value.value, None)
        self.assertEquals(self.stopReason.value.keyName, None)


    def test_receiveBoxData(self):
        """
        When a binary box protocol receives the serialized form of an AMP box,
        it should emit a similar box to its boxReceiver.
        """
        a = amp.BinaryBoxProtocol(self)
        a.dataReceived(amp.Box({"testKey": "valueTest",
                                "anotherKey": "anotherValue"}).serialize())
        self.assertEquals(self.boxes,
                          [amp.Box({"testKey": "valueTest",
                                    "anotherKey": "anotherValue"})])


    def test_receiveLongerBoxData(self):
        """
        An L{amp.BinaryBoxProtocol} can receive serialized AMP boxes with
        values of up to (2 ** 16 - 1) bytes.
        """
        length = (2 ** 16 - 1)
        value = 'x' * length
        transport = StringTransport()
        protocol = amp.BinaryBoxProtocol(self)
        protocol.makeConnection(transport)
        protocol.dataReceived(amp.Box({'k': value}).serialize())
        self.assertEqual(self.boxes, [amp.Box({'k': value})])
        self.assertFalse(transport.disconnecting)


    def test_sendBox(self):
        """
        When a binary box protocol sends a box, it should emit the serialized
        bytes of that box to its transport.
        """
        a = amp.BinaryBoxProtocol(self)
        a.makeConnection(self)
        aBox = amp.Box({"testKey": "valueTest",
                        "someData": "hello"})
        a.makeConnection(self)
        a.sendBox(aBox)
        self.assertEquals(''.join(self.data), aBox.serialize())


    def test_connectionLostStopSendingBoxes(self):
        """
        When a binary box protocol loses its connection, it should notify its
        box receiver that it has stopped receiving boxes.
        """
        a = amp.BinaryBoxProtocol(self)
        a.makeConnection(self)
        aBox = amp.Box({"sample": "data"})
        a.makeConnection(self)
        connectionFailure = Failure(RuntimeError())
        a.connectionLost(connectionFailure)
        self.assertIdentical(self.stopReason, connectionFailure)


    def test_protocolSwitch(self):
        """
        L{BinaryBoxProtocol} has the capacity to switch to a different protocol
        on a box boundary.  When a protocol is in the process of switching, it
        cannot receive traffic.
        """
        otherProto = TestProto(None, "outgoing data")
        test = self
        class SwitchyReceiver:
            switched = False
            def startReceivingBoxes(self, sender):
                pass
            def ampBoxReceived(self, box):
                test.assertFalse(self.switched,
                                 "Should only receive one box!")
                self.switched = True
                a._lockForSwitch()
                a._switchTo(otherProto)
        a = amp.BinaryBoxProtocol(SwitchyReceiver())
        anyOldBox = amp.Box({"include": "lots",
                             "of": "data"})
        a.makeConnection(self)
        # Include a 0-length box at the beginning of the next protocol's data,
        # to make sure that AMP doesn't eat the data or try to deliver extra
        # boxes either...
        moreThanOneBox = anyOldBox.serialize() + "\x00\x00Hello, world!"
        a.dataReceived(moreThanOneBox)
        self.assertIdentical(otherProto.transport, self)
        self.assertEquals("".join(otherProto.data), "\x00\x00Hello, world!")
        self.assertEquals(self.data, ["outgoing data"])
        a.dataReceived("more data")
        self.assertEquals("".join(otherProto.data),
                          "\x00\x00Hello, world!more data")
        self.assertRaises(amp.ProtocolSwitched, a.sendBox, anyOldBox)


    def test_protocolSwitchInvalidStates(self):
        """
        In order to make sure the protocol never gets any invalid data sent
        into the middle of a box, it must be locked for switching before it is
        switched.  It can only be unlocked if the switch failed, and attempting
        to send a box while it is locked should raise an exception.
        """
        a = amp.BinaryBoxProtocol(self)
        a.makeConnection(self)
        sampleBox = amp.Box({"some": "data"})
        a._lockForSwitch()
        self.assertRaises(amp.ProtocolSwitched, a.sendBox, sampleBox)
        a._unlockFromSwitch()
        a.sendBox(sampleBox)
        self.assertEquals(''.join(self.data), sampleBox.serialize())
        a._lockForSwitch()
        otherProto = TestProto(None, "outgoing data")
        a._switchTo(otherProto)
        self.assertRaises(amp.ProtocolSwitched, a._unlockFromSwitch)


    def test_protocolSwitchLoseConnection(self):
        """
        When the protocol is switched, it should notify its nested protocol of
        disconnection.
        """
        class Loser(protocol.Protocol):
            reason = None
            def connectionLost(self, reason):
                self.reason = reason
        connectionLoser = Loser()
        a = amp.BinaryBoxProtocol(self)
        a.makeConnection(self)
        a._lockForSwitch()
        a._switchTo(connectionLoser)
        connectionFailure = Failure(RuntimeError())
        a.connectionLost(connectionFailure)
        self.assertEquals(connectionLoser.reason, connectionFailure)


    def test_protocolSwitchLoseClientConnection(self):
        """
        When the protocol is switched, it should notify its nested client
        protocol factory of disconnection.
        """
        class ClientLoser:
            reason = None
            def clientConnectionLost(self, connector, reason):
                self.reason = reason
        a = amp.BinaryBoxProtocol(self)
        connectionLoser = protocol.Protocol()
        clientLoser = ClientLoser()
        a.makeConnection(self)
        a._lockForSwitch()
        a._switchTo(connectionLoser, clientLoser)
        connectionFailure = Failure(RuntimeError())
        a.connectionLost(connectionFailure)
        self.assertEquals(clientLoser.reason, connectionFailure)



class AMPTest(unittest.TestCase):

    def test_interfaceDeclarations(self):
        """
        The classes in the amp module ought to implement the interfaces that
        are declared for their benefit.
        """
        for interface, implementation in [(amp.IBoxSender, amp.BinaryBoxProtocol),
                                          (amp.IBoxReceiver, amp.BoxDispatcher),
                                          (amp.IResponderLocator, amp.CommandLocator),
                                          (amp.IResponderLocator, amp.SimpleStringLocator),
                                          (amp.IBoxSender, amp.AMP),
                                          (amp.IBoxReceiver, amp.AMP),
                                          (amp.IResponderLocator, amp.AMP)]:
            self.failUnless(interface.implementedBy(implementation),
                            "%s does not implements(%s)" % (implementation, interface))


    def test_helloWorld(self):
        """
        Verify that a simple command can be sent and its response received with
        the simple low-level string-based API.
        """
        c, s, p = connectedServerAndClient()
        L = []
        HELLO = 'world'
        c.sendHello(HELLO).addCallback(L.append)
        p.flush()
        self.assertEquals(L[0]['hello'], HELLO)


    def test_wireFormatRoundTrip(self):
        """
        Verify that mixed-case, underscored and dashed arguments are mapped to
        their python names properly.
        """
        c, s, p = connectedServerAndClient()
        L = []
        HELLO = 'world'
        c.sendHello(HELLO).addCallback(L.append)
        p.flush()
        self.assertEquals(L[0]['hello'], HELLO)


    def test_helloWorldUnicode(self):
        """
        Verify that unicode arguments can be encoded and decoded.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        HELLO = 'world'
        HELLO_UNICODE = 'wor\u1234ld'
        c.sendUnicodeHello(HELLO, HELLO_UNICODE).addCallback(L.append)
        p.flush()
        self.assertEquals(L[0]['hello'], HELLO)
        self.assertEquals(L[0]['Print'], HELLO_UNICODE)


    def test_unknownCommandLow(self):
        """
        Verify that unknown commands using low-level APIs will be rejected with an
        error, but will NOT terminate the connection.
        """
        c, s, p = connectedServerAndClient()
        L = []
        def clearAndAdd(e):
            """
            You can't propagate the error...
            """
            e.trap(amp.UnhandledCommand)
            return "OK"
        c.callRemoteString("WTF").addErrback(clearAndAdd).addCallback(L.append)
        p.flush()
        self.assertEquals(L.pop(), "OK")
        HELLO = 'world'
        c.sendHello(HELLO).addCallback(L.append)
        p.flush()
        self.assertEquals(L[0]['hello'], HELLO)


    def test_unknownCommandHigh(self):
        """
        Verify that unknown commands using high-level APIs will be rejected with an
        error, but will NOT terminate the connection.
        """
        c, s, p = connectedServerAndClient()
        L = []
        def clearAndAdd(e):
            """
            You can't propagate the error...
            """
            e.trap(amp.UnhandledCommand)
            return "OK"
        c.callRemote(WTF).addErrback(clearAndAdd).addCallback(L.append)
        p.flush()
        self.assertEquals(L.pop(), "OK")
        HELLO = 'world'
        c.sendHello(HELLO).addCallback(L.append)
        p.flush()
        self.assertEquals(L[0]['hello'], HELLO)


    def test_brokenReturnValue(self):
        """
        It can be very confusing if you write some code which responds to a
        command, but gets the return value wrong.  Most commonly you end up
        returning None instead of a dictionary.

        Verify that if that happens, the framework logs a useful error.
        """
        L = []
        SimpleSymmetricCommandProtocol().dispatchCommand(
            amp.AmpBox(_command=BrokenReturn.commandName)).addErrback(L.append)
        blr = L[0].trap(amp.BadLocalReturn)
        self.failUnlessIn('None', repr(L[0].value))


    def test_unknownArgument(self):
        """
        Verify that unknown arguments are ignored, and not passed to a Python
        function which can't accept them.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        HELLO = 'world'
        # c.sendHello(HELLO).addCallback(L.append)
        c.callRemote(FutureHello,
                     hello=HELLO,
                     bonus="I'm not in the book!").addCallback(
            L.append)
        p.flush()
        self.assertEquals(L[0]['hello'], HELLO)


    def test_simpleReprs(self):
        """
        Verify that the various Box objects repr properly, for debugging.
        """
        self.assertEquals(type(repr(amp._SwitchBox('a'))), str)
        self.assertEquals(type(repr(amp.QuitBox())), str)
        self.assertEquals(type(repr(amp.AmpBox())), str)
        self.failUnless("AmpBox" in repr(amp.AmpBox()))


    def test_simpleSSLRepr(self):
        """
        L{amp._TLSBox.__repr__} returns a string.
        """
        self.assertEquals(type(repr(amp._TLSBox())), str)

    test_simpleSSLRepr.skip = skipSSL


    def test_keyTooLong(self):
        """
        Verify that a key that is too long will immediately raise a synchronous
        exception.
        """
        c, s, p = connectedServerAndClient()
        L = []
        x = "H" * (0xff+1)
        tl = self.assertRaises(amp.TooLong,
                               c.callRemoteString, "Hello",
                               **{x: "hi"})
        self.failUnless(tl.isKey)
        self.failUnless(tl.isLocal)
        self.assertEquals(tl.keyName, None)
        self.failUnlessIdentical(tl.value, x)
        self.failUnless(str(len(x)) in repr(tl))
        self.failUnless("key" in repr(tl))


    def test_valueTooLong(self):
        """
        Verify that attempting to send value longer than 64k will immediately
        raise an exception.
        """
        c, s, p = connectedServerAndClient()
        L = []
        x = "H" * (0xffff+1)
        tl = self.assertRaises(amp.TooLong, c.sendHello, x)
        p.flush()
        self.failIf(tl.isKey)
        self.failUnless(tl.isLocal)
        self.assertEquals(tl.keyName, 'hello')
        self.failUnlessIdentical(tl.value, x)
        self.failUnless(str(len(x)) in repr(tl))
        self.failUnless("value" in repr(tl))
        self.failUnless('hello' in repr(tl))


    def test_helloWorldCommand(self):
        """
        Verify that a simple command can be sent and its response received with
        the high-level value parsing API.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        HELLO = 'world'
        c.sendHello(HELLO).addCallback(L.append)
        p.flush()
        self.assertEquals(L[0]['hello'], HELLO)


    def test_helloErrorHandling(self):
        """
        Verify that if a known error type is raised and handled, it will be
        properly relayed to the other end of the connection and translated into
        an exception, and no error will be logged.
        """
        L=[]
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        HELLO = 'fuck you'
        c.sendHello(HELLO).addErrback(L.append)
        p.flush()
        L[0].trap(UnfriendlyGreeting)
        self.assertEquals(str(L[0].value), "Don't be a dick.")


    def test_helloFatalErrorHandling(self):
        """
        Verify that if a known, fatal error type is raised and handled, it will
        be properly relayed to the other end of the connection and translated
        into an exception, no error will be logged, and the connection will be
        terminated.
        """
        L=[]
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        HELLO = 'die'
        c.sendHello(HELLO).addErrback(L.append)
        p.flush()
        L.pop().trap(DeathThreat)
        c.sendHello(HELLO).addErrback(L.append)
        p.flush()
        L.pop().trap(error.ConnectionDone)



    def test_helloNoErrorHandling(self):
        """
        Verify that if an unknown error type is raised, it will be relayed to
        the other end of the connection and translated into an exception, it
        will be logged, and then the connection will be dropped.
        """
        L=[]
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        HELLO = THING_I_DONT_UNDERSTAND
        c.sendHello(HELLO).addErrback(L.append)
        p.flush()
        ure = L.pop()
        ure.trap(amp.UnknownRemoteError)
        c.sendHello(HELLO).addErrback(L.append)
        cl = L.pop()
        cl.trap(error.ConnectionDone)
        # The exception should have been logged.
        self.failUnless(self.flushLoggedErrors(ThingIDontUnderstandError))



    def test_lateAnswer(self):
        """
        Verify that a command that does not get answered until after the
        connection terminates will not cause any errors.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        HELLO = 'world'
        c.callRemote(WaitForever).addErrback(L.append)
        p.flush()
        self.assertEquals(L, [])
        s.transport.loseConnection()
        p.flush()
        L.pop().trap(error.ConnectionDone)
        # Just make sure that it doesn't error...
        s.waiting.callback({})
        return s.waiting


    def test_requiresNoAnswer(self):
        """
        Verify that a command that requires no answer is run.
        """
        L=[]
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        HELLO = 'world'
        c.callRemote(NoAnswerHello, hello=HELLO)
        p.flush()
        self.failUnless(s.greeted)


    def test_requiresNoAnswerFail(self):
        """
        Verify that commands sent after a failed no-answer request do not complete.
        """
        L=[]
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        HELLO = 'fuck you'
        c.callRemote(NoAnswerHello, hello=HELLO)
        p.flush()
        # This should be logged locally.
        self.failUnless(self.flushLoggedErrors(amp.RemoteAmpError))
        HELLO = 'world'
        c.callRemote(Hello, hello=HELLO).addErrback(L.append)
        p.flush()
        L.pop().trap(error.ConnectionDone)
        self.failIf(s.greeted)


    def test_noAnswerResponderBadAnswer(self):
        """
        Verify that responders of requiresAnswer=False commands have to return
        a dictionary anyway.

        (requiresAnswer is a hint from the _client_ - the server may be called
        upon to answer commands in any case, if the client wants to know when
        they complete.)
        """
        c, s, p = connectedServerAndClient(
            ServerClass=BadNoAnswerCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        c.callRemote(NoAnswerHello, hello="hello")
        p.flush()
        le = self.flushLoggedErrors(amp.BadLocalReturn)
        self.assertEquals(len(le), 1)


    def test_noAnswerResponderAskedForAnswer(self):
        """
        Verify that responders with requiresAnswer=False will actually respond
        if the client sets requiresAnswer=True.  In other words, verify that
        requiresAnswer is a hint honored only by the client.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=NoAnswerCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        c.callRemote(Hello, hello="Hello!").addCallback(L.append)
        p.flush()
        self.assertEquals(len(L), 1)
        self.assertEquals(L, [dict(hello="Hello!-noanswer",
                                   Print=None)])  # Optional response argument


    def test_ampListCommand(self):
        """
        Test encoding of an argument that uses the AmpList encoding.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)
        L = []
        c.callRemote(GetList, length=10).addCallback(L.append)
        p.flush()
        values = L.pop().get('body')
        self.assertEquals(values, [{'x': 1}] * 10)


    def test_failEarlyOnArgSending(self):
        """
        Verify that if we pass an invalid argument list (omitting an argument), an
        exception will be raised.
        """
        okayCommand = Hello(hello="What?")
        self.assertRaises(amp.InvalidSignature, Hello)


    def test_doubleProtocolSwitch(self):
        """
        As a debugging aid, a protocol system should raise a
        L{ProtocolSwitched} exception when asked to switch a protocol that is
        already switched.
        """
        serverDeferred = defer.Deferred()
        serverProto = SimpleSymmetricCommandProtocol(serverDeferred)
        clientDeferred = defer.Deferred()
        clientProto = SimpleSymmetricCommandProtocol(clientDeferred)
        c, s, p = connectedServerAndClient(ServerClass=lambda: serverProto,
                                           ClientClass=lambda: clientProto)
        def switched(result):
            self.assertRaises(amp.ProtocolSwitched, c.switchToTestProtocol)
            self.testSucceeded = True
        c.switchToTestProtocol().addCallback(switched)
        p.flush()
        self.failUnless(self.testSucceeded)


    def test_protocolSwitch(self, switcher=SimpleSymmetricCommandProtocol,
                            spuriousTraffic=False,
                            spuriousError=False):
        """
        Verify that it is possible to switch to another protocol mid-connection and
        send data to it successfully.
        """
        self.testSucceeded = False

        serverDeferred = defer.Deferred()
        serverProto = switcher(serverDeferred)
        clientDeferred = defer.Deferred()
        clientProto = switcher(clientDeferred)
        c, s, p = connectedServerAndClient(ServerClass=lambda: serverProto,
                                           ClientClass=lambda: clientProto)

        if spuriousTraffic:
            wfdr = []           # remote
            wfd = c.callRemote(WaitForever).addErrback(wfdr.append)
        switchDeferred = c.switchToTestProtocol()
        if spuriousTraffic:
            self.assertRaises(amp.ProtocolSwitched, c.sendHello, 'world')

        def cbConnsLost(((serverSuccess, serverData),
                         (clientSuccess, clientData))):
            self.failUnless(serverSuccess)
            self.failUnless(clientSuccess)
            self.assertEquals(''.join(serverData), SWITCH_CLIENT_DATA)
            self.assertEquals(''.join(clientData), SWITCH_SERVER_DATA)
            self.testSucceeded = True

        def cbSwitch(proto):
            return defer.DeferredList(
                [serverDeferred, clientDeferred]).addCallback(cbConnsLost)

        switchDeferred.addCallback(cbSwitch)
        p.flush()
        if serverProto.maybeLater is not None:
            serverProto.maybeLater.callback(serverProto.maybeLaterProto)
            p.flush()
        if spuriousTraffic:
            # switch is done here; do this here to make sure that if we're
            # going to corrupt the connection, we do it before it's closed.
            if spuriousError:
                s.waiting.errback(amp.RemoteAmpError(
                        "SPURIOUS",
                        "Here's some traffic in the form of an error."))
            else:
                s.waiting.callback({})
            p.flush()
        c.transport.loseConnection() # close it
        p.flush()
        self.failUnless(self.testSucceeded)


    def test_protocolSwitchDeferred(self):
        """
        Verify that protocol-switching even works if the value returned from
        the command that does the switch is deferred.
        """
        return self.test_protocolSwitch(switcher=DeferredSymmetricCommandProtocol)


    def test_protocolSwitchFail(self, switcher=SimpleSymmetricCommandProtocol):
        """
        Verify that if we try to switch protocols and it fails, the connection
        stays up and we can go back to speaking AMP.
        """
        self.testSucceeded = False

        serverDeferred = defer.Deferred()
        serverProto = switcher(serverDeferred)
        clientDeferred = defer.Deferred()
        clientProto = switcher(clientDeferred)
        c, s, p = connectedServerAndClient(ServerClass=lambda: serverProto,
                                           ClientClass=lambda: clientProto)
        L = []
        switchDeferred = c.switchToTestProtocol(fail=True).addErrback(L.append)
        p.flush()
        L.pop().trap(UnknownProtocol)
        self.failIf(self.testSucceeded)
        # It's a known error, so let's send a "hello" on the same connection;
        # it should work.
        c.sendHello('world').addCallback(L.append)
        p.flush()
        self.assertEqual(L.pop()['hello'], 'world')


    def test_trafficAfterSwitch(self):
        """
        Verify that attempts to send traffic after a switch will not corrupt
        the nested protocol.
        """
        return self.test_protocolSwitch(spuriousTraffic=True)


    def test_errorAfterSwitch(self):
        """
        Returning an error after a protocol switch should record the underlying
        error.
        """
        return self.test_protocolSwitch(spuriousTraffic=True,
                                        spuriousError=True)


    def test_quitBoxQuits(self):
        """
        Verify that commands with a responseType of QuitBox will in fact
        terminate the connection.
        """
        c, s, p = connectedServerAndClient(
            ServerClass=SimpleSymmetricCommandProtocol,
            ClientClass=SimpleSymmetricCommandProtocol)

        L = []
        HELLO = 'world'
        GOODBYE = 'everyone'
        c.sendHello(HELLO).addCallback(L.append)
        p.flush()
        self.assertEquals(L.pop()['hello'], HELLO)
        c.callRemote(Goodbye).addCallback(L.append)
        p.flush()
        self.assertEquals(L.pop()['goodbye'], GOODBYE)
        c.sendHello(HELLO).addErrback(L.append)
        L.pop().trap(error.ConnectionDone)


    def test_basicLiteralEmit(self):
        """
        Verify that the command dictionaries for a callRemoteN look correct
        after being serialized and parsed.
        """
        c, s, p = connectedServerAndClient()
        L = []
        s.ampBoxReceived = L.append
        c.callRemote(Hello, hello='hello test', mixedCase='mixed case arg test',
                     dash_arg='x', underscore_arg='y')
        p.flush()
        self.assertEquals(len(L), 1)
        for k, v in [('_command', Hello.commandName),
                     ('hello', 'hello test'),
                     ('mixedCase', 'mixed case arg test'),
                     ('dash-arg', 'x'),
                     ('underscore_arg', 'y')]:
            self.assertEquals(L[-1].pop(k), v)
        L[-1].pop('_ask')
        self.assertEquals(L[-1], {})


    def test_basicStructuredEmit(self):
        """
        Verify that a call similar to basicLiteralEmit's is handled properly with
        high-level quoting and passing to Python methods, and that argument
        names are correctly handled.
        """
        L = []
        class StructuredHello(amp.AMP):
            def h(self, *a, **k):
                L.append((a, k))
                return dict(hello='aaa')
            Hello.responder(h)
        c, s, p = connectedServerAndClient(ServerClass=StructuredHello)
        c.callRemote(Hello, hello='hello test', mixedCase='mixed case arg test',
                     dash_arg='x', underscore_arg='y').addCallback(L.append)
        p.flush()
        self.assertEquals(len(L), 2)
        self.assertEquals(L[0],
                          ((), dict(
                    hello='hello test',
                    mixedCase='mixed case arg test',
                    dash_arg='x',
                    underscore_arg='y',

                    # XXX - should optional arguments just not be passed?
                    # passing None seems a little odd, looking at the way it
                    # turns out here... -glyph
                    From=('file', 'file'),
                    Print=None,
                    optional=None,
                    )))
        self.assertEquals(L[1], dict(Print=None, hello='aaa'))

class PretendRemoteCertificateAuthority:
    def checkIsPretendRemote(self):
        return True

class IOSimCert:
    verifyCount = 0

    def options(self, *ign):
        return self

    def iosimVerify(self, otherCert):
        """
        This isn't a real certificate, and wouldn't work on a real socket, but
        iosim specifies a different API so that we don't have to do any crypto
        math to demonstrate that the right functions get called in the right
        places.
        """
        assert otherCert is self
        self.verifyCount += 1
        return True

class OKCert(IOSimCert):
    def options(self, x):
        assert x.checkIsPretendRemote()
        return self

class GrumpyCert(IOSimCert):
    def iosimVerify(self, otherCert):
        self.verifyCount += 1
        return False

class DroppyCert(IOSimCert):
    def __init__(self, toDrop):
        self.toDrop = toDrop

    def iosimVerify(self, otherCert):
        self.verifyCount += 1
        self.toDrop.loseConnection()
        return True

class SecurableProto(FactoryNotifier):

    factory = None

    def verifyFactory(self):
        return [PretendRemoteCertificateAuthority()]

    def getTLSVars(self):
        cert = self.certFactory()
        verify = self.verifyFactory()
        return dict(
            tls_localCertificate=cert,
            tls_verifyAuthorities=verify)
    amp.StartTLS.responder(getTLSVars)



class TLSTest(unittest.TestCase):
    def test_startingTLS(self):
        """
        Verify that starting TLS and succeeding at handshaking sends all the
        notifications to all the right places.
        """
        cli, svr, p = connectedServerAndClient(
            ServerClass=SecurableProto,
            ClientClass=SecurableProto)

        okc = OKCert()
        svr.certFactory = lambda : okc

        cli.callRemote(
            amp.StartTLS, tls_localCertificate=okc,
            tls_verifyAuthorities=[PretendRemoteCertificateAuthority()])

        # let's buffer something to be delivered securely
        L = []
        d = cli.callRemote(SecuredPing).addCallback(L.append)
        p.flush()
        # once for client once for server
        self.assertEquals(okc.verifyCount, 2)
        L = []
        d = cli.callRemote(SecuredPing).addCallback(L.append)
        p.flush()
        self.assertEqual(L[0], {'pinged': True})


    def test_startTooManyTimes(self):
        """
        Verify that the protocol will complain if we attempt to renegotiate TLS,
        which we don't support.
        """
        cli, svr, p = connectedServerAndClient(
            ServerClass=SecurableProto,
            ClientClass=SecurableProto)

        okc = OKCert()
        svr.certFactory = lambda : okc

        cli.callRemote(amp.StartTLS,
                       tls_localCertificate=okc,
                       tls_verifyAuthorities=[PretendRemoteCertificateAuthority()])
        p.flush()
        cli.noPeerCertificate = True # this is totally fake
        self.assertRaises(
            amp.OnlyOneTLS,
            cli.callRemote,
            amp.StartTLS,
            tls_localCertificate=okc,
            tls_verifyAuthorities=[PretendRemoteCertificateAuthority()])


    def test_negotiationFailed(self):
        """
        Verify that starting TLS and failing on both sides at handshaking sends
        notifications to all the right places and terminates the connection.
        """

        badCert = GrumpyCert()

        cli, svr, p = connectedServerAndClient(
            ServerClass=SecurableProto,
            ClientClass=SecurableProto)
        svr.certFactory = lambda : badCert

        cli.callRemote(amp.StartTLS,
                       tls_localCertificate=badCert)

        p.flush()
        # once for client once for server - but both fail
        self.assertEquals(badCert.verifyCount, 2)
        d = cli.callRemote(SecuredPing)
        p.flush()
        self.assertFailure(d, iosim.NativeOpenSSLError)


    def test_negotiationFailedByClosing(self):
        """
        Verify that starting TLS and failing by way of a lost connection
        notices that it is probably an SSL problem.
        """

        cli, svr, p = connectedServerAndClient(
            ServerClass=SecurableProto,
            ClientClass=SecurableProto)
        droppyCert = DroppyCert(svr.transport)
        svr.certFactory = lambda : droppyCert

        secure = cli.callRemote(amp.StartTLS,
                                tls_localCertificate=droppyCert)

        p.flush()

        self.assertEquals(droppyCert.verifyCount, 2)

        d = cli.callRemote(SecuredPing)
        p.flush()

        # it might be a good idea to move this exception somewhere more
        # reasonable.
        self.assertFailure(d, error.PeerVerifyError)

    skip = skipSSL



class TLSNotAvailableTest(unittest.TestCase):
    """
    Tests what happened when ssl is not available in current installation.
    """

    def setUp(self):
        """
        Disable ssl in amp.
        """
        self.ssl = amp.ssl
        amp.ssl = None


    def tearDown(self):
        """
        Restore ssl module.
        """
        amp.ssl = self.ssl


    def test_callRemoteError(self):
        """
        Check that callRemote raises an exception when called with a
        L{amp.StartTLS}.
        """
        cli, svr, p = connectedServerAndClient(
            ServerClass=SecurableProto,
            ClientClass=SecurableProto)

        okc = OKCert()
        svr.certFactory = lambda : okc

        return self.assertFailure(cli.callRemote(
            amp.StartTLS, tls_localCertificate=okc,
            tls_verifyAuthorities=[PretendRemoteCertificateAuthority()]),
            RuntimeError)


    def test_messageReceivedError(self):
        """
        When a client with SSL enabled talks to a server without SSL, it
        should return a meaningful error.
        """
        svr = SecurableProto()
        okc = OKCert()
        svr.certFactory = lambda : okc
        box = amp.Box()
        box['_command'] = 'StartTLS'
        box['_ask'] = '1'
        boxes = []
        svr.sendBox = boxes.append
        svr.makeConnection(StringTransport())
        svr.ampBoxReceived(box)
        self.assertEquals(boxes,
            [{'_error_code': 'TLS_ERROR',
              '_error': '1',
              '_error_description': 'TLS not available'}])



class InheritedError(Exception):
    """
    This error is used to check inheritance.
    """



class OtherInheritedError(Exception):
    """
    This is a distinct error for checking inheritance.
    """



class BaseCommand(amp.Command):
    """
    This provides a command that will be subclassed.
    """
    errors = {InheritedError: 'INHERITED_ERROR'}



class InheritedCommand(BaseCommand):
    """
    This is a command which subclasses another command but does not override
    anything.
    """



class AddErrorsCommand(BaseCommand):
    """
    This is a command which subclasses another command but adds errors to the
    list.
    """
    arguments = [('other', amp.Boolean())]
    errors = {OtherInheritedError: 'OTHER_INHERITED_ERROR'}



class NormalCommandProtocol(amp.AMP):
    """
    This is a protocol which responds to L{BaseCommand}, and is used to test
    that inheritance does not interfere with the normal handling of errors.
    """
    def resp(self):
        raise InheritedError()
    BaseCommand.responder(resp)



class InheritedCommandProtocol(amp.AMP):
    """
    This is a protocol which responds to L{InheritedCommand}, and is used to
    test that inherited commands inherit their bases' errors if they do not
    respond to any of their own.
    """
    def resp(self):
        raise InheritedError()
    InheritedCommand.responder(resp)



class AddedCommandProtocol(amp.AMP):
    """
    This is a protocol which responds to L{AddErrorsCommand}, and is used to
    test that inherited commands can add their own new types of errors, but
    still respond in the same way to their parents types of errors.
    """
    def resp(self, other):
        if other:
            raise OtherInheritedError()
        else:
            raise InheritedError()
    AddErrorsCommand.responder(resp)



class CommandInheritanceTests(unittest.TestCase):
    """
    These tests verify that commands inherit error conditions properly.
    """

    def errorCheck(self, err, proto, cmd, **kw):
        """
        Check that the appropriate kind of error is raised when a given command
        is sent to a given protocol.
        """
        c, s, p = connectedServerAndClient(ServerClass=proto,
                                           ClientClass=proto)
        d = c.callRemote(cmd, **kw)
        d2 = self.failUnlessFailure(d, err)
        p.flush()
        return d2


    def test_basicErrorPropagation(self):
        """
        Verify that errors specified in a superclass are respected normally
        even if it has subclasses.
        """
        return self.errorCheck(
            InheritedError, NormalCommandProtocol, BaseCommand)


    def test_inheritedErrorPropagation(self):
        """
        Verify that errors specified in a superclass command are propagated to
        its subclasses.
        """
        return self.errorCheck(
            InheritedError, InheritedCommandProtocol, InheritedCommand)


    def test_inheritedErrorAddition(self):
        """
        Verify that new errors specified in a subclass of an existing command
        are honored even if the superclass defines some errors.
        """
        return self.errorCheck(
            OtherInheritedError, AddedCommandProtocol, AddErrorsCommand, other=True)


    def test_additionWithOriginalError(self):
        """
        Verify that errors specified in a command's superclass are respected
        even if that command defines new errors itself.
        """
        return self.errorCheck(
            InheritedError, AddedCommandProtocol, AddErrorsCommand, other=False)


def _loseAndPass(err, proto):
    # be specific, pass on the error to the client.
    err.trap(error.ConnectionLost, error.ConnectionDone)
    del proto.connectionLost
    proto.connectionLost(err)


class LiveFireBase:
    """
    Utility for connected reactor-using tests.
    """

    def setUp(self):
        """
        Create an amp server and connect a client to it.
        """
        from twisted.internet import reactor
        self.serverFactory = protocol.ServerFactory()
        self.serverFactory.protocol = self.serverProto
        self.clientFactory = protocol.ClientFactory()
        self.clientFactory.protocol = self.clientProto
        self.clientFactory.onMade = defer.Deferred()
        self.serverFactory.onMade = defer.Deferred()
        self.serverPort = reactor.listenTCP(0, self.serverFactory)
        self.addCleanup(self.serverPort.stopListening)
        self.clientConn = reactor.connectTCP(
            '127.0.0.1', self.serverPort.getHost().port,
            self.clientFactory)
        self.addCleanup(self.clientConn.disconnect)
        def getProtos(rlst):
            self.cli = self.clientFactory.theProto
            self.svr = self.serverFactory.theProto
        dl = defer.DeferredList([self.clientFactory.onMade,
                                 self.serverFactory.onMade])
        return dl.addCallback(getProtos)

    def tearDown(self):
        """
        Cleanup client and server connections, and check the error got at
        C{connectionLost}.
        """
        L = []
        for conn in self.cli, self.svr:
            if conn.transport is not None:
                # depend on amp's function connection-dropping behavior
                d = defer.Deferred().addErrback(_loseAndPass, conn)
                conn.connectionLost = d.errback
                conn.transport.loseConnection()
                L.append(d)
        return defer.gatherResults(L
            ).addErrback(lambda first: first.value.subFailure)


def show(x):
    import sys
    sys.stdout.write(x+'\n')
    sys.stdout.flush()


def tempSelfSigned():
    from twisted.internet import ssl

    sharedDN = ssl.DN(CN='shared')
    key = ssl.KeyPair.generate()
    cr = key.certificateRequest(sharedDN)
    sscrd = key.signCertificateRequest(
        sharedDN, cr, lambda dn: True, 1234567)
    cert = key.newCertificate(sscrd)
    return cert

if ssl is not None:
    tempcert = tempSelfSigned()


class LiveFireTLSTestCase(LiveFireBase, unittest.TestCase):
    clientProto = SecurableProto
    serverProto = SecurableProto
    def test_liveFireCustomTLS(self):
        """
        Using real, live TLS, actually negotiate a connection.

        This also looks at the 'peerCertificate' attribute's correctness, since
        that's actually loaded using OpenSSL calls, but the main purpose is to
        make sure that we didn't miss anything obvious in iosim about TLS
        negotiations.
        """

        cert = tempcert

        self.svr.verifyFactory = lambda : [cert]
        self.svr.certFactory = lambda : cert
        # only needed on the server, we specify the client below.

        def secured(rslt):
            x = cert.digest()
            def pinged(rslt2):
                # Interesting.  OpenSSL won't even _tell_ us about the peer
                # cert until we negotiate.  we should be able to do this in
                # 'secured' instead, but it looks like we can't.  I think this
                # is a bug somewhere far deeper than here.
                self.failUnlessEqual(x, self.cli.hostCertificate.digest())
                self.failUnlessEqual(x, self.cli.peerCertificate.digest())
                self.failUnlessEqual(x, self.svr.hostCertificate.digest())
                self.failUnlessEqual(x, self.svr.peerCertificate.digest())
            return self.cli.callRemote(SecuredPing).addCallback(pinged)
        return self.cli.callRemote(amp.StartTLS,
                                   tls_localCertificate=cert,
                                   tls_verifyAuthorities=[cert]).addCallback(secured)

    skip = skipSSL



class SlightlySmartTLS(SimpleSymmetricCommandProtocol):
    """
    Specific implementation of server side protocol with different
    management of TLS.
    """
    def getTLSVars(self):
        """
        @return: the global C{tempcert} certificate as local certificate.
        """
        return dict(tls_localCertificate=tempcert)
    amp.StartTLS.responder(getTLSVars)


class PlainVanillaLiveFire(LiveFireBase, unittest.TestCase):

    clientProto = SimpleSymmetricCommandProtocol
    serverProto = SimpleSymmetricCommandProtocol

    def test_liveFireDefaultTLS(self):
        """
        Verify that out of the box, we can start TLS to at least encrypt the
        connection, even if we don't have any certificates to use.
        """
        def secured(result):
            return self.cli.callRemote(SecuredPing)
        return self.cli.callRemote(amp.StartTLS).addCallback(secured)

    skip = skipSSL



class WithServerTLSVerification(LiveFireBase, unittest.TestCase):
    clientProto = SimpleSymmetricCommandProtocol
    serverProto = SlightlySmartTLS

    def test_anonymousVerifyingClient(self):
        """
        Verify that anonymous clients can verify server certificates.
        """
        def secured(result):
            return self.cli.callRemote(SecuredPing)
        return self.cli.callRemote(amp.StartTLS,
                                   tls_verifyAuthorities=[tempcert]
            ).addCallback(secured)

    skip = skipSSL



class ProtocolIncludingArgument(amp.Argument):
    """
    An L{amp.Argument} which encodes its parser and serializer
    arguments *including the protocol* into its parsed and serialized
    forms.
    """

    def fromStringProto(self, string, protocol):
        """
        Don't decode anything; just return all possible information.

        @return: A two-tuple of the input string and the protocol.
        """
        return (string, protocol)

    def toStringProto(self, obj, protocol):
        """
        Encode identifying information about L{object} and protocol
        into a string for later verification.

        @type obj: L{object}
        @type protocol: L{amp.AMP}
        """
        return "%s:%s" % (id(obj), id(protocol))



class ProtocolIncludingCommand(amp.Command):
    """
    A command that has argument and response schemas which use
    L{ProtocolIncludingArgument}.
    """
    arguments = [('weird', ProtocolIncludingArgument())]
    response = [('weird', ProtocolIncludingArgument())]



class MagicSchemaCommand(amp.Command):
    """
    A command which overrides L{parseResponse}, L{parseArguments}, and
    L{makeResponse}.
    """
    def parseResponse(self, strings, protocol):
        """
        Don't do any parsing, just jam the input strings and protocol
        onto the C{protocol.parseResponseArguments} attribute as a
        two-tuple. Return the original strings.
        """
        protocol.parseResponseArguments = (strings, protocol)
        return strings
    parseResponse = classmethod(parseResponse)


    def parseArguments(cls, strings, protocol):
        """
        Don't do any parsing, just jam the input strings and protocol
        onto the C{protocol.parseArgumentsArguments} attribute as a
        two-tuple. Return the original strings.
        """
        protocol.parseArgumentsArguments = (strings, protocol)
        return strings
    parseArguments = classmethod(parseArguments)


    def makeArguments(cls, objects, protocol):
        """
        Don't do any serializing, just jam the input strings and protocol
        onto the C{protocol.makeArgumentsArguments} attribute as a
        two-tuple. Return the original strings.
        """
        protocol.makeArgumentsArguments = (objects, protocol)
        return objects
    makeArguments = classmethod(makeArguments)



class NoNetworkProtocol(amp.AMP):
    """
    An L{amp.AMP} subclass which overrides private methods to avoid
    testing the network. It also provides a responder for
    L{MagicSchemaCommand} that does nothing, so that tests can test
    aspects of the interaction of L{amp.Command}s and L{amp.AMP}.

    @ivar parseArgumentsArguments: Arguments that have been passed to any
    L{MagicSchemaCommand}, if L{MagicSchemaCommand} has been handled by
    this protocol.

    @ivar parseResponseArguments: Responses that have been returned from a
    L{MagicSchemaCommand}, if L{MagicSchemaCommand} has been handled by
    this protocol.

    @ivar makeArgumentsArguments: Arguments that have been serialized by any
    L{MagicSchemaCommand}, if L{MagicSchemaCommand} has been handled by
    this protocol.
    """
    def _sendBoxCommand(self, commandName, strings, requiresAnswer):
        """
        Return a Deferred which fires with the original strings.
        """
        return defer.succeed(strings)

    MagicSchemaCommand.responder(lambda s, weird: {})



class MyBox(dict):
    """
    A unique dict subclass.
    """



class ProtocolIncludingCommandWithDifferentCommandType(
    ProtocolIncludingCommand):
    """
    A L{ProtocolIncludingCommand} subclass whose commandType is L{MyBox}
    """
    commandType = MyBox



class CommandTestCase(unittest.TestCase):
    """
    Tests for L{amp.Argument} and L{amp.Command}.
    """
    def test_argumentInterface(self):
        """
        L{Argument} instances provide L{amp.IArgumentType}.
        """
        self.assertTrue(verifyObject(amp.IArgumentType, amp.Argument()))


    def test_parseResponse(self):
        """
        There should be a class method of Command which accepts a
        mapping of argument names to serialized forms and returns a
        similar mapping whose values have been parsed via the
        Command's response schema.
        """
        protocol = object()
        result = 'whatever'
        strings = {'weird': result}
        self.assertEqual(
            ProtocolIncludingCommand.parseResponse(strings, protocol),
            {'weird': (result, protocol)})


    def test_callRemoteCallsParseResponse(self):
        """
        Making a remote call on a L{amp.Command} subclass which
        overrides the C{parseResponse} method should call that
        C{parseResponse} method to get the response.
        """
        client = NoNetworkProtocol()
        thingy = "weeoo"
        response = client.callRemote(MagicSchemaCommand, weird=thingy)
        def gotResponse(ign):
            self.assertEquals(client.parseResponseArguments,
                              ({"weird": thingy}, client))
        response.addCallback(gotResponse)
        return response


    def test_parseArguments(self):
        """
        There should be a class method of L{amp.Command} which accepts
        a mapping of argument names to serialized forms and returns a
        similar mapping whose values have been parsed via the
        command's argument schema.
        """
        protocol = object()
        result = 'whatever'
        strings = {'weird': result}
        self.assertEqual(
            ProtocolIncludingCommand.parseArguments(strings, protocol),
            {'weird': (result, protocol)})


    def test_responderCallsParseArguments(self):
        """
        Making a remote call on a L{amp.Command} subclass which
        overrides the C{parseArguments} method should call that
        C{parseArguments} method to get the arguments.
        """
        protocol = NoNetworkProtocol()
        responder = protocol.locateResponder(MagicSchemaCommand.commandName)
        argument = object()
        response = responder(dict(weird=argument))
        response.addCallback(
            lambda ign: self.assertEqual(protocol.parseArgumentsArguments,
                                         ({"weird": argument}, protocol)))
        return response


    def test_makeArguments(self):
        """
        There should be a class method of L{amp.Command} which accepts
        a mapping of argument names to objects and returns a similar
        mapping whose values have been serialized via the command's
        argument schema.
        """
        protocol = object()
        argument = object()
        objects = {'weird': argument}
        self.assertEqual(
            ProtocolIncludingCommand.makeArguments(objects, protocol),
            {'weird': "%d:%d" % (id(argument), id(protocol))})


    def test_makeArgumentsUsesCommandType(self):
        """
        L{amp.Command.makeArguments}'s return type should be the type
        of the result of L{amp.Command.commandType}.
        """
        protocol = object()
        objects = {"weird": "whatever"}

        result = ProtocolIncludingCommandWithDifferentCommandType.makeArguments(
            objects, protocol)
        self.assertIdentical(type(result), MyBox)


    def test_callRemoteCallsMakeArguments(self):
        """
        Making a remote call on a L{amp.Command} subclass which
        overrides the C{makeArguments} method should call that
        C{makeArguments} method to get the response.
        """
        client = NoNetworkProtocol()
        argument = object()
        response = client.callRemote(MagicSchemaCommand, weird=argument)
        def gotResponse(ign):
            self.assertEqual(client.makeArgumentsArguments,
                             ({"weird": argument}, client))
        response.addCallback(gotResponse)
        return response


    def test_extraArgumentsDisallowed(self):
        """
        L{Command.makeArguments} raises L{amp.InvalidSignature} if the objects
        dictionary passed to it includes a key which does not correspond to the
        Python identifier for a defined argument.
        """
        self.assertRaises(
            amp.InvalidSignature,
            Hello.makeArguments,
            dict(hello="hello", bogusArgument=object()), None)


    def test_wireSpellingDisallowed(self):
        """
        If a command argument conflicts with a Python keyword, the
        untransformed argument name is not allowed as a key in the dictionary
        passed to L{Command.makeArguments}.  If it is supplied,
        L{amp.InvalidSignature} is raised.

        This may be a pointless implementation restriction which may be lifted.
        The current behavior is tested to verify that such arguments are not
        silently dropped on the floor (the previous behavior).
        """
        self.assertRaises(
            amp.InvalidSignature,
            Hello.makeArguments,
            dict(hello="required", **{"print": "print value"}),
            None)



if not interfaces.IReactorSSL.providedBy(reactor):
    skipMsg = 'This test case requires SSL support in the reactor'
    TLSTest.skip = skipMsg
    LiveFireTLSTestCase.skip = skipMsg
    PlainVanillaLiveFire.skip = skipMsg
    WithServerTLSVerification.skip = skipMsg

