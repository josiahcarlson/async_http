
import os
import urlparse

from _http import AsyncHTTPRequest

class DownloadFile(AsyncHTTPRequest):
    def __init__(self, url, local_path=None, redirect=5):
        if local_path is None:
            parsed = urlparse.urlparse(url)
            local_path = parsed.path.rpartition('/')[-1]
            if not local_path:
                local_path = 'index.html'
        self.url = url
        self.local_path = local_path
        self.redirect = redirect if redirect >= 0 else None
        self.out = open(local_path, 'wb')

        AsyncHTTPRequest.__init__(self, url)

    def http_response(self):
        if self.response.status in (300, 301, 302, 303, 307):
            if self.redirect is not None or self.redirect <= 0:
                self.out.close()
                os.unlink(self.local_path)
                raise Exception("redirect limit reached: %s %r"%(self.response.status, self.url))

            self.out.close()
            DownloadFile(
                self.response.getheader('location'),
                self.local_path,
                self.redirect-1 if self.redirect > 0 else None
            )

    def http_body(self):
        if not self.out.closed:
            self.out.write(self._get_data())

    def http_done(self):
        if not self.out.closed:
            self.out.close()

    def http_close(self):
        if not self.out.closed:
            # failed to download data
            self.out.close()
            os.unlink(self.local_path)

def main():
    import asyncore
    import sys
    map(DownloadFile, sys.argv[1:])
    asyncore.loop(timeout=.25)

if __name__ == '__main__':
    main()
