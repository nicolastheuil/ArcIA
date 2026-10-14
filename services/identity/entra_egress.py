"""TLS CONNECT relay for the authentication canary; no inference destination."""
import ipaddress
import select
import socket
from socketserver import StreamRequestHandler,ThreadingTCPServer
import time

HOST='login.microsoftonline.com'


def destination(line):
    parts=line.split()
    if parts!=['CONNECT',HOST+':443','HTTP/1.1']:
        raise ValueError('ENTRA_AUTH_DESTINATION_REFUSED')
    return HOST,443


class Handler(StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(15)
        upstream=None
        try:
            line=self.rfile.readline(2049)
            if len(line)>2048:raise ValueError()
            host,port=destination(line.decode('ascii').strip())
            size=0
            while True:
                header=self.rfile.readline(2049);size+=len(header)
                if not header or size>8192 or len(header)>2048:raise ValueError()
                if header in (b'\r\n',b'\n'):break
            addresses=socket.getaddrinfo(host,port,socket.AF_INET,socket.SOCK_STREAM)
            for address in addresses:
                ip=address[4][0]
                if not ipaddress.ip_address(ip).is_global:continue
                try:upstream=socket.create_connection((ip,port),timeout=10);break
                except OSError:continue
            if upstream is None:raise ValueError()
            self.wfile.write(b'HTTP/1.1 200 Connection Established\r\n\r\n');self.wfile.flush()
            self.connection.setblocking(False);upstream.setblocking(False)
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                readable,_,_=select.select([self.connection,upstream],[],[],5)
                for source in readable:
                    data=source.recv(65536)
                    if not data:return
                    target=upstream if source is self.connection else self.connection
                    # Bounded TLS records; sendall on a blocking socket preserves bytes.
                    target.settimeout(15);target.sendall(data);target.setblocking(False)
        except (ValueError,UnicodeError,OSError):
            if upstream is None:
                try:self.wfile.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                except OSError:pass
        finally:
            if upstream:upstream.close()


class Relay(ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True


if __name__=='__main__':
    with Relay(('0.0.0.0',8088),Handler) as server:server.serve_forever()
