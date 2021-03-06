import urllib, os, sys

from twisted.internet import defer, reactor
from twisted.web import resource, server
from twisted.web2 import wsgi

headerNameTranslation = ''.join([c.isalnum() and c.upper() or '_' for c in map(chr, range(256))])

def createCGIEnvironment(request):
    env = {}
    
    # MUST provide:
    clength = request.headers.get('content-length', False)
    if clength:
        env["CONTENT_LENGTH"] = clength
    
    ctype = request.headers['content-type']
    if ctype:
        env["CONTENT_TYPE"] = ctype
    
    env["GATEWAY_INTERFACE"] = "CGI/1.1"
    
    if request.postpath:
        # Should we raise an exception if this contains "/" chars?
        env["PATH_INFO"] = '/' + '/'.join(request.postpath)
    
    # MUST always be present, even if no query
    qindex = request.uri.find('?')
    if qindex != -1:
        qs = env['QUERY_STRING'] = request.uri[qindex+1:]
        if '=' in qs:
            qargs = []
        else:
            qargs = [urllib.unquote(x) for x in qs.split('+')]
    else:
        env['QUERY_STRING'] = ''
        qargs = []
    
    #env["REMOTE_ADDR"] = remotehost.host
    client = request.getClient()
    if client is not None:
        env['REMOTE_HOST'] = client
    ip = request.getClientIP()
    if ip is not None:
        env['REMOTE_ADDR'] = ip
    
    env["REQUEST_METHOD"] = request.method
    # Should we raise an exception if this contains "/" chars?
    if request.prepath:
        env["SCRIPT_NAME"] = '/' + '/'.join(request.prepath)
    else:
        env["SCRIPT_NAME"] = ''
    
    env["SERVER_NAME"] = request.getRequestHostname().split(':')[0]
    env["SERVER_PORT"] = str(request.getHost().port)
    
    env["SERVER_PROTOCOL"] = request.clientproto
    env["SERVER_SOFTWARE"] = server.version
    
    # SHOULD provide
    # env["AUTH_TYPE"] # FIXME: add this
    # env["REMOTE_HOST"] # possibly dns resolve?
    
    # MAY provide
    # env["PATH_TRANSLATED"] # Completely worthless
    # env["REMOTE_IDENT"] # Completely worthless
    # env["REMOTE_USER"] # FIXME: add this
    
    # Unofficial, but useful and expected by applications nonetheless
    env["REMOTE_PORT"] = str(request.client.port)
    env["REQUEST_URI"] = request.uri
    
    scheme = ('http', 'https')[request.isSecure()]
    env["REQUEST_SCHEME"] = scheme
    env["HTTPS"] = ("off", "on")[scheme == "https"]
    env["SERVER_PORT_SECURE"] = ("0", "1")[scheme == "https"]
    
    # Propagate HTTP headers
    for title in request.headers:
        header = request.headers[title]
        envname = title.translate(headerNameTranslation)
        # Don't send headers we already sent otherwise, and don't
        # send authorization headers, because that's a security
        # issue.
        if title not in ('content-type', 'content-length',
                         'authorization', 'proxy-authorization'):
            envname = "HTTP_" + envname
        env[envname] = header
    
    for k,v in env.items():
        if type(k) is not str:
            print "is not string:",k
        if type(v) is not str:
            print k, "is not string:",v
    return env


class WSGIResource(resource.Resource):
    isLeaf = True
    
    def __init__(self, application):
        self.application = application
    
    def render(self, request):
        handler = WSGIHandler(self.application, request)
        handler.responseDeferred.addCallback(self._finish, request)
        
        # Run it in a thread
        reactor.callInThread(handler.run)
        return server.NOT_DONE_YET
    
    def _write(self, content, request):
        request.write(content)
        request.finish()
    
    def _finish(self, response, request):
        for key, values in response.headers.getAllRawHeaders():
            for value in values:
                request.setHeader(key, value)
        
        content = response.stream.read()
        if(isinstance(content, defer.Deferred)):
            content.addCallback(self._write, request)
        else:
            self._write(content, request)


class WSGIHandler(wsgi.WSGIHandler):
    def setupEnvironment(self, request):
        # Called in IO thread
        env = createCGIEnvironment(request)
        env['wsgi.version']      = (1, 0)
        env['wsgi.url_scheme']   = env['REQUEST_SCHEME']
        env['wsgi.input']        = wsgi.InputStream(request.content)
        env['wsgi.errors']       = wsgi.ErrorStream()
        env['wsgi.multithread']  = True
        env['wsgi.multiprocess'] = False
        env['wsgi.run_once']     = False
        env['wsgi.file_wrapper'] = wsgi.FileWrapper
        self.environment = env
