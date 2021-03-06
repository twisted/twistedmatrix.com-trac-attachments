#!/usr/bin/env python

# based on https://github.com/twisted/twisted/blob/trunk/docs/conch/examples/sshsimpleserver.py

# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.cred import portal
from twisted.conch import avatar
from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
from twisted.conch.ssh import factory, userauth, connection, keys, session
from twisted.internet import reactor, protocol
from twisted.python import log
from zope.interface import implements
import sys
log.startLogging(sys.stderr)

if '--ipv6' in sys.argv:
	# adapted from https://github.com/twisted/twisted/blob/trunk/twisted/conch/ssh/forwarding.py
	from twisted.conch.ssh.forwarding import SSHConnectForwardingChannel as OldForwardingChannel, unpackOpen_direct_tcpip, SSHForwardingClient
	from twisted.internet.endpoints import HostnameEndpoint
	class SSHForwardingClientFactory(protocol.Factory):
		channel = None
		def __init__(self, channel):
			self.channel = channel
		def buildProtocol(self, addr):
			return SSHForwardingClient(self.channel)
	class SSHConnectForwardingChannel(OldForwardingChannel):
		def channelOpen(self, specificData):
			log.msg("IPv6 enabled, connecting to %s:%i" % self.hostport)
			#cc = protocol.ClientCreator(reactor, SSHForwardingClient, self)
			#cc.connectTCP(*self.hostport).addCallbacks(self._setClient, self._close)
			ep = HostnameEndpoint(reactor, self.hostport[0], self.hostport[1])
			d = ep.connect(SSHForwardingClientFactory(self))
			d.addCallbacks(self._setClient, self._close)
	def openConnectForwardingClient(remoteWindow, remoteMaxPacket, data, avatar):
		remoteHP, origHP = unpackOpen_direct_tcpip(data)
		return SSHConnectForwardingChannel(remoteHP, 
			remoteWindow=remoteWindow,
			remoteMaxPacket=remoteMaxPacket,
			avatar=avatar)
else:
	from twisted.conch.ssh.forwarding import openConnectForwardingClient

"""
Example of running another protocol over an SSH channel.
log in with username "user" and password "password".
"""

class ExampleAvatar(avatar.ConchUser):

    def __init__(self, username):
        avatar.ConchUser.__init__(self)
        self.username = username
        self.channelLookup.update({'session':session.SSHSession, 'direct-tcpip': openConnectForwardingClient})

class ExampleRealm:
    implements(portal.IRealm)

    def requestAvatar(self, avatarId, mind, *interfaces):
        return interfaces[0], ExampleAvatar(avatarId), lambda: None

class EchoProtocol(protocol.Protocol):
    """this is our example protocol that we will run over SSH
    """
    def dataReceived(self, data):
        if data == '\r':
            data = '\r\n'
        elif data == '\x03': #^C
            self.transport.loseConnection()
            return
        self.transport.write(data)

publicKey = 'ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAGEArzJx8OYOnJmzf4tfBEvLi8DVPrJ3/c9k2I/Az64fxjHf9imyRJbixtQhlH9lfNjUIx+4LmrJH5QNRsFporcHDKOTwTTYLh5KmRpslkYHRivcJSkbh/C+BR3utDS555mV'

privateKey = """-----BEGIN RSA PRIVATE KEY-----
MIIByAIBAAJhAK8ycfDmDpyZs3+LXwRLy4vA1T6yd/3PZNiPwM+uH8Yx3/YpskSW
4sbUIZR/ZXzY1CMfuC5qyR+UDUbBaaK3Bwyjk8E02C4eSpkabJZGB0Yr3CUpG4fw
vgUd7rQ0ueeZlQIBIwJgbh+1VZfr7WftK5lu7MHtqE1S1vPWZQYE3+VUn8yJADyb
Z4fsZaCrzW9lkIqXkE3GIY+ojdhZhkO1gbG0118sIgphwSWKRxK0mvh6ERxKqIt1
xJEJO74EykXZV4oNJ8sjAjEA3J9r2ZghVhGN6V8DnQrTk24Td0E8hU8AcP0FVP+8
PQm/g/aXf2QQkQT+omdHVEJrAjEAy0pL0EBH6EVS98evDCBtQw22OZT52qXlAwZ2
gyTriKFVoqjeEjt3SZKKqXHSApP/AjBLpF99zcJJZRq2abgYlf9lv1chkrWqDHUu
DZttmYJeEfiFBBavVYIF1dOlZT0G8jMCMBc7sOSZodFnAiryP+Qg9otSBjJ3bQML
pSTqy7c3a2AScC/YyOwkDaICHnnD3XyjMwIxALRzl0tQEKMXs6hH8ToUdlLROCrP
EhQ0wahUTCk1gKA4uPD6TMTChavbh4K63OvbKg==
-----END RSA PRIVATE KEY-----"""



class ExampleSession:

    def __init__(self, avatar):
        """
        We don't use it, but the adapter is passed the avatar as its first
        argument.
        """

    def getPty(self, term, windowSize, attrs):
        pass

    def execCommand(self, proto, cmd):
        raise Exception("no executing commands")

    def openShell(self, trans):
        ep = EchoProtocol()
        ep.makeConnection(trans)
        trans.makeConnection(session.wrapProtocol(ep))

    def eofReceived(self):
        pass

    def closed(self):
        pass

from twisted.python import components
components.registerAdapter(ExampleSession, ExampleAvatar, session.ISession)

class ExampleFactory(factory.SSHFactory):
    publicKeys = {
        'ssh-rsa': keys.Key.fromString(data=publicKey)
    }
    privateKeys = {
        'ssh-rsa': keys.Key.fromString(data=privateKey)
    }
    services = {
        'ssh-userauth': userauth.SSHUserAuthServer,
        'ssh-connection': connection.SSHConnection
    }

portal = portal.Portal(ExampleRealm())
passwdDB = InMemoryUsernamePasswordDatabaseDontUse()
passwdDB.addUser('user', 'password')
portal.registerChecker(passwdDB)
ExampleFactory.portal = portal

if __name__ == '__main__':
    reactor.listenTCP(5022, ExampleFactory(), interface='::')
    reactor.run()
