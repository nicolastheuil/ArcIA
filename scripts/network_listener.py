"""Temporary synthetic listeners. No client access; systemd caps lifetime at 300s."""
import json
from pathlib import Path
import socket
import sys
import threading
import time


def serve(plan):
    peers = set(plan['nodes']) | {'127.0.0.1'}
    sockets = []
    def tcp_listener(channel, port):
        while time.time() < plan['expires_at']:
            try:
                connection, peer = channel.accept()
                with connection:
                    connection.settimeout(2)
                    if peer[0] not in peers: continue
                    request = connection.recv(256).decode()
                    if request == plan['challenge']:
                        connection.sendall(json.dumps({'operation_id': plan['operation_id'],
                            'node': plan['node'], 'port': port, 'challenge': plan['challenge']}).encode())
            except (OSError, UnicodeError): pass
    def udp_listener(channel):
        while time.time() < plan['expires_at']:
            try:
                request, peer = channel.recvfrom(256)
                if peer[0] in peers and request.decode() == plan['challenge']:
                    channel.sendto(json.dumps({'operation_id': plan['operation_id'], 'node': plan['node'],
                        'port': 8472, 'challenge': plan['challenge']}).encode(), peer)
            except (OSError, UnicodeError): pass
    try:
        for port in (443,6443,2379,2380,10250):
            channel=socket.socket();channel.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            channel.bind(('0.0.0.0',port));channel.listen(16);channel.settimeout(1);sockets.append(channel)
            threading.Thread(target=tcp_listener,args=(channel,port),daemon=True).start()
        channel=socket.socket(type=socket.SOCK_DGRAM);channel.bind(('0.0.0.0',8472));channel.settimeout(1);sockets.append(channel)
        threading.Thread(target=udp_listener,args=(channel,),daemon=True).start()
        while time.time() < plan['expires_at']: time.sleep(0.5)
    finally:
        for channel in sockets: channel.close()


if __name__ == '__main__': serve(json.loads(Path(sys.argv[1]).read_text()))
