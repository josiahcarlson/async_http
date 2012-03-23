
from collections import namedtuple
from hashlib import sha1
import hmac
import re
import os
import time
import urlparse

from get import DownloadFile

# Some 3rd party OAuth libraries incorrectly handle url parameters combined
# with request bodies. Bypass that crap and include a minimal OAuth1.0a
# request implementation.

OAuthKey = namedtuple("OAuthKey", "key secret")

_oauth_escape_r = re.compile('[^-_~.A-Za-z0-9]')
_oauth_escape_f = lambda c: "%" + c.group().encode('hex').upper()
def oauth_escape(kv):
    # some libraries don't do this part right
    return _oauth_escape_r.sub(_oauth_escape_f, kv.encode('utf-8'))

_oauth_unescape_r = re.compile('%([A-Fa-f0-9]{2})')
_oauth_unescape_f = lambda c: c.group().decode('hex').decode('utf-8')
def oauth_unescape(kv):
    return _oauth_unescape_r.sub(_oauth_unescape_f, kv)

def oauth_unparse(sequence):
    if isinstance(sequence, dict):
        sequence = sequence.items()
    return "&".join(
        "%s=%s"%(oauth_escape(key), oauth_escape(val))
            for key, val in sorted(sequence) if val is not None and key)

def oauth_header(method, parsed, body, consumer, token=None):
    oauth = {
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_version': '1.0',
        'oauth_nonce': os.urandom(12).encode('hex'),
        'oauth_timestamp': str(int(time.time())),
        'oauth_consumer_key': consumer.key,
    }
    if token:
        oauth['oauth_token'] = token.key
    op = dict(oauth)
    if parsed.query:
        # some libraries forget about this part
        op.update(urlparse.parse_qsl(parsed.query, strict_parsing=1))
    if body:
        op.update(urlparse.parse_qsl(body, strict_parsing=1))

    base_url = urlparse.urlunparse(parsed[:3] + ('', '', ''))
    content = '&'.join([
        method.upper(),
        oauth_escape(base_url),
        oauth_escape(oauth_unparse(op))])

    secret = consumer.secret + ('&' + token.secret if token else '')
    oauth['oauth_signature'] = hmac.new(secret, content, sha1) \
        .digest().encode('base-64').rstrip()

    return 'OAuth realm="%s", %s'%(base_url, ', '.join(
        '%s="%s"'%(key, oauth_escape(val))
            for key, val in sorted(oauth.items())))

class OAuthRequest(DownloadFile):
    def __init__(self, url, consumer, token=None):
        self.consumer = consumer
        self.token = token
        DownloadFile.__init__(self, url)

    def http_setup(self):
        if self.consumer:
            request_text = self.http.sock.getvalue()
            method = request_text.partition(' ')[0]
            head, split, body = request_text.partition('\r\n\r\n')
            header = 'Authorization: ' + oauth_header(
                method, self.parsed, body, self.consumer, self.token)

            head += '\r\n' + header
            # need to replace at least the old header tail/body, so we'll just
            # replace it all.
            self.http.sock.seek(0)
            self.http.sock.write(head + split + body)

def main():
    import asyncore
    import sys
    k, sep, s = sys.argv[1].partition(',')
    client = OAuthKey(k, s)
    token = None
    if len(sys.argv) >= 4:
        k, sep, s = sys.argv[2].partition(',')
        token = OAuthKey(k, s)

    OAuthRequest(sys.argv[-1], client, token)
    asyncore.loop(timeout=.25)

if __name__ == '__main__':
    main()
