#coding=utf-8
from twisted.internet import iocpreactor
iocpreactor.install()
from twisted.internet import reactor,defer,task
from twisted.spread import pb,jelly

class MathRpc(pb.Root):
    def remote_ok(self,a):
        return a
        
    def remote_bad(self, a):
        d = defer.Deferred()
        reactor.callLater(0,d.callback,a)
        return d

if __name__ == "__main__":
    reactor.listenTCP(12345, pb.PBServerFactory(MathRpc()))
    reactor.run()
