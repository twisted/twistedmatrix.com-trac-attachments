#!/usr/bin/python

from twisted.spread import pb
from twisted.cred.portal import IRealm
import zope.interface

class SimplePerspective(pb.Avatar):

    def perspective_ping(self):
        print 'Client pinging'

    def logout(self):
        print "Client logged out"

class SimpleRealm:
    zope.interface.implements(IRealm)

    def requestAvatar(self, avatarId, mind, *interfaces):
        if pb.IPerspective in interfaces:
            avatar = SimplePerspective()
            return pb.IPerspective, avatar, avatar.logout 
        else:
            raise NotImplementedError("no interface")

if __name__ == '__main__':
    
    from twisted.internet import reactor
    from twisted.cred.portal import Portal
    from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
    
    portal = Portal(SimpleRealm())
    checker = InMemoryUsernamePasswordDatabaseDontUse()
    checker.addUser("guest", "guest")
    portal.registerChecker(checker)
    reactor.listenTCP(4242, pb.PBServerFactory(portal))
    reactor.run()
