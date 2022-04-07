
# Copyright (c) 2001-2004 Twisted Matrix Laboratories.
# See LICENSE for details.


from OpenSSL import SSL
from twisted.internet.protocol import Factory
from twisted.internet import ssl, reactor
from twisted.python import log

class ServerContextFactory:
    
    def getContext(self):
        """Create an SSL context.
        
        This is a sample implementation that loads a certificate from a file 
        called 'server.pem'."""
        ctx = SSL.Context(SSL.SSLv23_METHOD)
        ctx.use_certificate_file('nfdclient.pem')
        ctx.use_privatekey_file('nfdclient.pem')
        return ctx


if __name__ == '__main__':
    import echoserv, sys
    log.startLogging(sys.stdout)
    factory = Factory()
    factory.protocol = echoserv.Echo
    port =int(sys.argv[1])
    reactor.listenSSL(port, factory, ServerContextFactory())
    reactor.run()
