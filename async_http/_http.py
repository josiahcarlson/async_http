
import asynchat
import httplib
import socket
import ssl
from StringIO import StringIO
import time
import urllib
import urlparse
import zlib

HEADER = object()
CHUNKED = object()
CHUNK = object()
BODY = object()
PORTS = {'http':80, 'https':443}

__all__ = ['AsyncHTTPRequest']

class StringBuffer(StringIO):
    # cStringIO can't be subclassed in some Python versions
    def makefile(self, *args, **kwargs):
        return self
    def sendall(self, arg):
        self.write(arg)

class GzipDecoder(object):
    # derived from http://effbot.org/zone/consumer-gzip.htm
    def __init__(self):
        self.decoder = None
        self.head = ""

    def feed(self, data):
        if self.decoder is None:
            # check if we have a full gzip header
            data = self.head + data
            try:
                if data[:3] != "\x1f\x8b\x08":
                    raise IOError("invalid gzip data")
                i = 10
                flag = ord(data[3])
                if flag & 4:
                    i += 2 + ord(data[i]) + 256*ord(data[i+1])
                if flag & 8:
                    i = data.index('\0', i) + 1
                if flag & 16:
                    i = data.index('\0', i) + 1
                if flag & 2:
                    i += 2
                if i > len(data):
                    raise IndexError("not enough data")
            except (IndexError, ValueError):
                self.head = data
                return ""
            self.head = ""
            data = data[i:]
            self.decoder = zlib.decompressobj(-zlib.MAX_WBITS)
        return self.decoder.decompress(data)

    def flush(self):
        return self.decoder.flush()

class AsyncHTTPRequest(asynchat.async_chat):
    state = HEADER
    response = None
    established = False
    want_read = want_write = True
    gzip = None
    def __init__(self, url, data=None, method=None, timeout=30):
        self.last_read = time.time()
        self.timeout = timeout
        self.set_terminator('\r\n\r\n')

        # parse the url and set everything up
        self.url = url
        self.parsed = parsed = urlparse.urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            raise httplib.UnknownProtocol("Can only access http[s] urls")
        self.method = None
        self.established = parsed.scheme == 'http'
        if method and method.upper() in ('GET', 'POST'):
            self.method = method.upper()
        else:
            self.method = 'POST' if data is not None else 'GET'

        # prepare the http request itself
        post_body = urllib.urlencode(data) if data is not None else None
        host, _, port = parsed.netloc.partition(':')
        self.http = http = httplib.HTTPConnection(host)
        http.sock = StringBuffer()
        path = parsed.path
        if parsed.params:
            path += ';' + parsed.params
        if parsed.query:
            path += '?' + parsed.query
        http.request(self.method, path, post_body, {'Accept-Encoding':'gzip'})
        self.http_setup() # allow for subsequent manipulation of body/header/etc.

        # connect to the host asynchronously
        port = int(port, 10) if port else PORTS[parsed.scheme]
        asynchat.async_chat.__init__(self)
        self.push(http.sock.getvalue())
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect((host, port))

    def collect_incoming_data(self, data):
        self.last_read = time.time()
        if self.gzip:
            data = self.gzip.feed(data)
        self.incoming.append(data)

        if self.state is BODY:
            self.http_body()

    def found_terminator(self):
        self.last_read = time.time()
        if self.state is HEADER:
            self.state = BODY
            header_data = StringBuffer(self._get_data().rstrip() + '\r\n\r\n')
            self.response = httplib.HTTPResponse(header_data, method=self.method)
            self.response.begin()
            self.http_response()

            # error or otherwise...
            if self.response.status != 200:
                return self.found_terminator()

            # chunked transfer encoding: useful for twitter, google, etc.
            content = self.response.getheader('Content-Encoding', '').lower()
            transfer = self.response.getheader('Transfer-Encoding', '').lower()
            if 'gzip' in (content, transfer):
                self.gzip = GzipDecoder()
            if transfer == 'chunked':
                self.set_terminator('\r\n')
                self.state = CHUNKED
            else:
                self.set_terminator(self.response.length)

        elif self.state is CHUNKED:
            ch, sep, header = self._get_data().rstrip().partition(';')
            if not ch:
                # it's probably the spare \r\n between chunks...
                return
            if header:
                # chunked transfer encodings also pass headers
                name, sep, value = header.partition('=')
                if sep:
                    self.request.msg.addheader(name, value)

            self.set_terminator(int(ch, 16))
            if self.terminator == 0:
                # no more chunks...
                self.state = BODY
                return self.found_terminator()
            self.state = CHUNK

        elif self.state is CHUNK:
            self.http_body()
            self.http_chunk()
            # prepare for the next chunk
            self.set_terminator('\r\n')
            self.state = CHUNKED

        else:
            if self.gzip:
                data = self.gzip.flush()
                if data:
                    self.incoming.append(data)
                    self.http_body()
            # body is done being received, close the socket
            self.http_body = lambda *args: None
            self.terminator = None
            self.http_done()
            self.handle_close()

    def handle_close(self):
        if self.parsed.scheme == 'https':
            self.socket = self._socket

        asynchat.async_chat.handle_close(self)
        self.http_close()

    # we need to jump through some hoops for https support
    def readable(self):
        if time.time() - self.last_read > self.timeout:
            self.state = BODY
            self.found_terminator()
            return False
        return self.want_read and asynchat.async_chat.readable(self)

    def writable(self):
        if time.time() - self.last_read > self.timeout:
            return False
        return self.want_write and asynchat.async_chat.writable(self)

    def _handshake(self):
        try:
            self.socket.do_handshake()
        except ssl.SSLError as err:
            self.want_read = self.want_write = False
            if err.args[0] == ssl.SSL_ERROR_WANT_READ:
                self.want_read = True
            elif err.args[0] == ssl.SSL_ERROR_WANT_WRITE:
                self.want_write = True
            else:
                raise
        else:
            self.want_read = self.want_write = True
            self.established = True

    def handle_write(self):
        if self.established:
            return self.initiate_send()

        self._handshake()

    def handle_read(self):
        if self.established:
            return asynchat.async_chat.handle_read(self)

        self._handshake()

    def handle_connect(self):
        if self.parsed.scheme == 'https':
            self._socket = self.socket
            self.socket = ssl.wrap_socket(self._socket, do_handshake_on_connect=False)

    # subclass callback support
    def http_setup(self):
        '''
        Called just before the connection is set up. You can manipulate
        headers, request body, etc.
        '''

    def http_response(self):
        '''
        Called after the response is read. You can handle redirects, perform
        additional logging, start a reply in a proxy, etc.
        '''

    def http_body(self):
        '''
        Called at the end of every chunk with chunked transfer encoding, and
        any time data is read for the body otherwise.
        '''

    def http_chunk(self):
        '''
        Called after every chunk with the chunked transfer encoding,
        immediately after the body callback.
        '''

    def http_done(self):
        '''
        Called when the body has finshed being transferred. This will not be
        called when there is an error.
        '''

    def http_close(self):
        '''
        Called when the connection has been closed.
        '''
