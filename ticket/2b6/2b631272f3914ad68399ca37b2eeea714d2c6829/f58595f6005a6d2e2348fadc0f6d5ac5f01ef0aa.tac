from twisted.internet import protocol
from twisted.application import service, internet
from twisted.conch.insults import insults
from twisted.conch import telnet


class MyTerminalProtocol(insults.TerminalProtocol):
    width = 80
    height = 24
    
    def connectionMade(self):
        self.terminalSize(self.width, self.height)
        self.terminal.write(" world\n")

    def terminalSize(self, width, height):
        self.width, self.height = width, height
        self.terminal.eraseDisplay()
        self.terminal.write("Hello,")
    
    def keystrokeReceived(self, keyID, modifier):
        self.terminal.write("%r %r\n" % (keyID, modifier))


application = service.Application('insults_prototype')
factory = protocol.ServerFactory()
factory.protocol = lambda: telnet.TelnetTransport(
    telnet.TelnetBootstrapProtocol,
    insults.ServerProtocol,
    MyTerminalProtocol)
internet.TCPServer(1977, factory).setServiceParent(application)
