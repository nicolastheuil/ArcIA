#!/usr/bin/python3
"""Root-only keepalived health; synthetic lease expires automatically."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time


def healthy():
    leases = list(Path('/run/arcia').glob('network-*/plan.json'))
    for lease in leases:
        plan = json.loads(lease.read_text())
        if time.time() < plan['expires_at'] <= time.time()+310:
            with socket.create_connection(('127.0.0.1',6443),timeout=1) as connection:
                connection.sendall(plan['challenge'].encode())
                response=json.loads(connection.recv(1024))
            return response == {'operation_id':plan['operation_id'],'node':plan['node'],
                                'port':6443,'challenge':plan['challenge']}
    if not Path('/usr/local/bin/k3s').is_file(): return False
    result=subprocess.run(['/usr/local/bin/k3s','kubectl','get','--raw=/readyz',
                           '--request-timeout=2s'],capture_output=True,timeout=3)
    return result.returncode == 0 and result.stdout.strip() == b'ok'


if __name__ == '__main__':
    try: sys.exit(0 if healthy() else 1)
    except Exception: sys.exit(1)
