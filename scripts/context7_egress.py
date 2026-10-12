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
        if not allowed_path(self.path):
            self.send_error(403);return
        connection=None
        try:
            addresses=socket.getaddrinfo('context7.com',443,type=socket.SOCK_STREAM)
            address=next(item[4][0] for item in addresses if ipaddress.ip_address(item[4][0]).is_global)
            connection=http.client.HTTPSConnection('context7.com',443,timeout=30,context=ssl.create_default_context())
            # Pin this connection to the checked public IP while retaining TLS SNI.
            connection._create_connection=lambda destination,timeout,source_address=None:socket.create_connection((address,443),timeout)
            connection.request('GET',self.path,headers={'Accept':'application/json,text/plain','User-Agent':'arcia-public-docs-relay/1'})
            response=connection.getresponse();body=response.read(4*1024*1024+1)
            if len(body)>4*1024*1024 or 300<=response.status<400:
                self.send_error(502);return
            self.send_response(response.status)
            self.send_header('Content-Type',response.getheader('Content-Type','text/plain'))
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        except Exception:
            self.send_error(502)
        finally:
            if connection: connection.close()


if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',8080),Relay).serve_forever()
