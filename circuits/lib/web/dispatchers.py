# Module:   dispatcher
# Date:     13th September 2007
# Author:   James Mills, prologic at shortcircuit dot net dot au

"""Dispatchers

This module implements URL dispatchers.
"""

import os

from circuits.core import Component

from cgifs import FieldStorage
from tools import expires, serve_file
from errors import HTTPError, NotFound
from utils import parseQueryString, dictform
from events import Request, Response

class DefaultDispatcher(Component):

    def __init__(self, docroot=None, defaults=None, **kwargs):
        super(DefaultDispatcher, self).__init__(**kwargs)

        if not docroot:
            self.docroot = os.getcwd()

        if not defaults:
            self.defaults = ["index.html"]

    def __params__(self, request, response):
        body = request.body
        headers = request.headers

        if "Content-Type" not in headers:
            headers["Content-Type"] = ""

        try:
            form = FieldStorage(fp=body,
                headers=headers,
                environ={"REQUEST_METHOD": "POST"},
                keep_blank_values=True)
        except Exception, e:
            if e.__class__.__name__ == 'MaxSizeExceeded':
                # Post data is too big
                return HTTPError(request, response, 413)
            else:
                raise

        if form.file:
            return form.file
        else:
            return dictform(form)

    def __channel__(self, request):
        """__channel__(request) -> channel

        Find and return an appropiate channel
        for the given request.

        The channel is found by traversing the system's event channels,
        and matching path components to successive channels in the system.

        If a channel cannot be found for a given path, but there is
        a default channel, then this will be used.

        The following is an example mappiny of path to channel given
        the following channels:

        Channels:
         /:index
         /foo:index
         /foo:hello
         /bar:GET
         /bar:POST
         /foo/bar/hello

        Method    Path                   Channel            VPath
        ---------------------------------------------------------
        GET       /                      /                  []
        GET       /1/2/3                 /                  [1, 2, 3]
        GET       /foo                   /foo               []
        GET       /foo/hello             /foo/hello         []
        GET       /foo/1/2/3             /foo               [1, 2, 3]
        GET       /foo/hello/1/2/3       /foo/hello         [1, 2, 3]
        GET       /bar                   /bar               []
        GET       /bar/1/2/3             /bar               [1, 2, 3]
        POST      /bar                   /bar               []
        POST      /bar/1/2/3             /bar               [1, 2, 3]
        GET       /foo/bar/hello         /foo/bar/hello     []
        GET       /foo/bar/hello/1/2/3   /foo/bar/hello     [1, 2, 3]
        """

        path = request.path
        method = request.method.upper()
        defaults = ["index", method, "request"]

        if not "/" in path:
            for default in defaults:
                k = "/:%s" % default
                if k in self.manager.channels:
                    return k, []
            return None, []

        names = [x for x in path.strip("/").split("/") if x]

        targets = set([x.split(":")[0] for x in self.manager.channels if x and \
                ":" in x and x[0] == "/"])

        i = 0
        matches = [""]
        candidates = []
        while i <= len(names):
            x = "/".join(matches) or "/"
            if x in targets:
                candidates.append([i, x])
                if i < len(names):
                    matches.append(names[i])
            else:
                break
            i += 1

        if not candidates:
            return None, []

        i, candidate = candidates.pop()

        if i < len(names):
            channels = [names[i], "index", method, "request"]
        else:
            channels = ["index", method, "request"]

        vpath = []
        channel = None
        for ch in channels:
            x = "%s:%s" % (candidate, ch)
            found = x in self.manager.channels
            if found:
                if i < len(names) and ch == names[i]:
                    i += 1
                channel = x
                break

        if channel is not None:
            if i < len(names):
                vpath = [x.replace("%2F", "/") for x in names[i:]]
            else:
                vpath = []

        return channel, vpath

    def request(self, request, response):
        path = request.path.strip("/")
        if path:
            filename = os.path.abspath(os.path.join(self.docroot, path))
        else:
            for default in self.defaults:
                filename = os.path.abspath(os.path.join(self.docroot, default))
                if os.path.exists(filename):
                    break
                else:
                    filename = None

        if filename and os.path.exists(filename):
            expires(request, response, 3500*24*30)
            return serve_file(request, response, filename)

        channel, vpath = self.__channel__(request)

        if channel:
            params = parseQueryString(request.qs)
            x = self.__params__(request, response)
            if not x:
                return
            elif type(x) == dict:
                params.update(x)
            else:
                request.body = x

            req = Request(request, response, *vpath, **params)

            try:
                v = [x for x in self.iter(req, channel) if x]
            except Exception, error:
                raise
            if v:
                if isinstance(v[0], basestring):
                    return v[0]
            else:
                return NotFound(request, response)
        else:
            return NotFound(request, response)

class FileDispatcher(Component):

   template = """\
<html>
 <head>
  <title>Index of %(path)s</title>
 </head>
 <body>
  <h1>Index of %(path)s</h1>
%(files)s
 </body>
</html>"""

   def __init__(self, path=None, **kwargs):
      super(FileDispatcher, self).__init__(**kwargs)

      if not path:
         self.path = os.getcwd()

   def request(self, request, response):
      print request
      path = request.path.strip("/")
      print path

      if args:
         path = os.path.join("/", *args)
         real = os.path.join(self.path, *args)
      else:
         path = ""
         real = self.path

      if isfile(real):
         response.body = open(real, "r")
         return self.send(Response(request, response), "response")

      data = {}
      data["path"] = path or "/"

      files = []

      if path:
         href = os.path.join(self.channel, path.lstrip("/"), "..")
         files.append("<li class=\"dir\"><a href=\"%s\">..</a>" % href)

      for file in listdir(real):
         href = os.path.join(self.channel, path.lstrip("/"), file)
         name = ("%s/" % file if isdir(file) else file)
         files.append("   <li class=\"dir\"><a href=\"%s\">%s</a>" % (
            href, name))

      data["files"] = "  <ul>\n%s\n  </ul>" % "\n".join(files)

      response.headers["Content-Type"] = "text/html"
      return self.template % data

Dispatcher = DefaultDispatcher
FileServer = FileDispatcher