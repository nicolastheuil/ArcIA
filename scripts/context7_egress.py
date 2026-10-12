"""Internal, bounded GET relay to the fixed public Context7 documentation API.

Not a sanitizer: synthetic/public queries only until the DLP service is qualified.
No credentials, arbitrary destination, forwarding of caller headers, or redirects.
"""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import socket
import ssl
from urllib.parse import parse_qsl, urlsplit


def allowed_path(path):
    parsed=urlsplit(path)
    fields={'/api/v2/libs/search':{'query','libraryName'},
        '/api/v2/context':{'query','libraryId','language'}}
    if len(path)>4096 or parsed.scheme or parsed.netloc or parsed.fragment or parsed.path not in fields:
        return False
    pairs=parse_qsl(parsed.query,keep_blank_values=True)
    keys=[key for key,_ in pairs]
    return bool(pairs) and len(set(keys))==len(keys) and set(keys)<=fields[parsed.path]


class Relay(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def do_GET(self):
        if self.path=='/health':
            self.send_response(200);self.end_headers();self.wfile.write(b'ok');return
        # External documentation queries require a separate qualified DLP adapter.
        self.send_response(403);self.send_header('Content-Length','0');self.end_headers()



if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',8080),Relay).serve_forever()
