# Module:   wsgi
# Date:     6th November 2008
# Author:   James Mills, prologic at shortcircuit dot net dot au

"""WSGI Components

This module implements WSGI Components.
"""

import warnings
from urllib import unquote
from traceback import format_exc

from circuits import handler, Component

from circuits.lib.io import File

import webob
from headers import Headers
from errors import HTTPError
from utils import quoteHTML, url
from dispatchers import Dispatcher
from events import Request, Response
from constants import RESPONSES, DEFAULT_ERROR_MESSAGE, SERVER_VERSION

class Application(Component):

    headerNames = {
            "HTTP_CGI_AUTHORIZATION": "Authorization",
            "CONTENT_LENGTH": "Content-Length",
            "CONTENT_TYPE": "Content-Type",
            "REMOTE_HOST": "Remote-Host",
            "REMOTE_ADDR": "Remote-Addr",
            }

    def __init__(self):
        super(Application, self).__init__()

        Dispatcher().register(self)

    def translateHeaders(self, environ):
        for cgiName in environ:
            # We assume all incoming header keys are uppercase already.
            if cgiName in self.headerNames:
                yield self.headerNames[cgiName], environ[cgiName]
            elif cgiName[:5] == "HTTP_":
                # Hackish attempt at recovering original header names.
                translatedHeader = cgiName[5:].replace("_", "-")
                yield translatedHeader, environ[cgiName]

    def getRequestResponse(self, environ):
        env = environ.get

        headers = Headers(list(self.translateHeaders(environ)))

        protocol = tuple(map(int, env("SERVER_PROTOCOL")[5:].split(".")))
        request = webob.Request(None,
                env("REQUEST_METHOD"),
                env("wsgi.url_scheme"),
                env("PATH_INFO"),
                protocol,
                env("QUERY_STRING"))

        request.remote = webob.Host(env("REMOTE_ADDR"), env("REMTOE_PORT"))

        request.headers = headers
        request.script_name = env("SCRIPT_NAME")
        request.wsgi_environ = environ
        request.body = env("wsgi.input")

        response = webob.Response(None, request)
        response.gzip = "gzip" in request.headers.get("Accept-Encoding", "")

        return request, response

    def setError(self, response, status, message=None, traceback=None):
        try:
            short, long = RESPONSES[status]
        except KeyError:
            short, long = "???", "???"

        if message is None:
            message = short

        explain = long

        content = DEFAULT_ERROR_MESSAGE % {
            "status": status,
            "message": quoteHTML(message),
            "traceback": traceback or ""}

        response.body = content
        response.status = "%s %s" % (status, message)
        response.headers.add_header("Connection", "close")

    def _handleError(self, error):
        response = error.response

        try:
            v = self.send(error, "httperror", self.channel)
        except TypeError:
            v = None

        if v is not None:
            if isinstance(v, basestring):
                response.body = v
                res = Response(response)
                self.send(res, "response", self.channel)
            elif isinstance(v, HTTPError):
                self.send(Response(v.response), "response", self.channel)
            else:
                raise TypeError("wtf is %s (%s) response ?!" % (v, type(v)))

    def response(self, response):
        response.done = True

    def __call__(self, environ, start_response):
        request, response = self.getRequestResponse(environ)

        try:
            req = Request(request, response)

            try:
                v = self.send(req, "request", self.channel, True, False)
            except TypeError:
                v = None

            if v is not None:
                if isinstance(v, basestring):
                    response.body = v
                    res = Response(response)
                    self.send(res, "response", self.channel)
                elif isinstance(v, HTTPError):
                    self._handleError(v)
                elif isinstance(v, webob.Response):
                    res = Response(v)
                    self.send(res, "response", self.channel)
                else:
                    raise TypeError("wtf is %s (%s) response ?!" % (v, type(v)))
            else:
                error = NotFound(request, response)
                self._handleError(error)
        except:
            error = HTTPError(request, response, 500, error=format_exc())
            self._handleError(error)
        finally:
            body = response.process()
            start_response(response.status, response.headers.items())
            return [body]

class WSGIErrors(File):

    def write(self, data):
        pass # Not doing anything with wsgi.errors yet

class Gateway(Component):

    def __init__(self, app, path=None):
        super(Gateway, self).__init__(channel=path)

        self.app = app

        self._errors = WSGIErrors("/dev/stderr", "a")
        self._errors.register(self)

        self._request = self._response = None

    def environ(self):
        environ = {}
        req = self._request
        env = environ.__setitem__

        env("REQUEST_METHOD", req.method)
        env("SERVER_NAME", req.host.split(":", 1)[0])
        env("SERVER_PORT", "%i" % req.server.port)
        env("SERVER_PROTOCOL", "HTTP/%d.%d" % req.server_protocol)
        env("QUERY_STRING", req.qs)
        env("SCRIPT_NAME", req.script_name)
        env("CONTENT_TYPE", req.headers.get("Content-Type", ""))
        env("CONTENT_LENGTH", req.headers.get("Content-Length", ""))
        env("REMOTE_ADDR", req.remote.ip)
        env("REMOTE_PORT", "%i" % req.remote.port)
        env("wsgi.version", (1, 0))
        env("wsgi.input", req.body)
        env("wsgi.errors", self._errors)
        env("wsgi.multithread", False)
        env("wsgi.multiprocess", False)
        env("wsgi.run_once", False)
        env("wsgi.url_scheme", req.scheme)

        if req.path:
            env("PATH_INFO", unquote(req.path))

        for k, v in req.headers.items():
            env("HTTP_%s" % k.upper().replace("-", "_"), v)

        return environ

    def start_response(self, status, headers):
        self._response.status = status
        for header in headers:
            self._response.headers.add_header(*header)

    @handler("request", filter=True)
    def request(self, request, response):
        self._request = request
        self._response = response

        return "".join(self.app(self.environ(), self.start_response))

def Middleware(*args, **kwargs):
    """Alias to Gateway for backward compatibility.

    @deprecated: Middleware will be deprecated in 1.2 Use Gateway insetad.
    """

    warnings.warn("Please use Gateway, Middleware will be deprecated in 1.2")

    return Gateway(*args, **kwargs)
