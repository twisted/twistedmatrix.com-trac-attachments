# Read from file
from twisted.application import internet, service
from twisted.internet import protocol, reactor, defer
from twisted.protocols import basic

class FingerProtocol(basic.LineReceiver):
    def lineReceived(self, user):
        self.factory.getUser(user
        ).addErrback(lambda _: "Internal error in server"
        ).addCallback(lambda m:
                      (self.transport.write(m+"\r\n"),
                       self.transport.loseConnection()))

class FingerService(service.Service):
    def __init__(self, filename):
        self.users = {}
        self.filename = filename

    def _read(self):
        for line in file(self.filename):
            user, status = line.split(':', 1)
            user=user.strip()
            status=status.strip()
            self.users[user] = status
        self.call = reactor.callLater(30, self._read)
    def startService(self):
        self._read()
        service.Service.startService(self)
    def stopService(self):
        service.Service.stopService(self)
        self.call.cancel()
    def getUser(self, user):
        return defer.succeed(self.users.get(user, "No such user"))
    def getFingerFactory(self):
        f = protocol.ServerFactory()
        f.protocol, f.getUser = FingerProtocol, self.getUser,
        return f

application = service.Application('finger', uid=1, gid=1)
f = FingerService('/etc/users')
finger = internet.TCPServer(79, f.getFingerFactory())

f.setServiceParent(service.IServiceCollection(application)) 
finger.setServiceParent(service.IServiceCollection(application))