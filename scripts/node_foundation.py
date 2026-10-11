"""Fixed guest foundation actions; launched only through protected SSH transport."""
import ipaddress
import json
from pathlib import Path
import re
import socket
import subprocess
import time
import uuid
import hashlib


def run(args, timeout=30):
    return subprocess.run(args, capture_output=True, timeout=timeout, check=True).stdout.decode()


def inspect(values):
    address = str(ipaddress.IPv4Address(values['address']))
    route = json.loads(run(['/usr/sbin/ip', '-j', 'route', 'get', values['peers'][0]]))[0]
    interface = route['dev']
    candidates = {}
    hashes = {}
    for package in ('keepalived', 'iputils-arping'):
        output = run(['/usr/bin/apt-cache', 'policy', package])
        match = re.search(r'^\s*Candidate:\s*(\S+)\s*$', output, re.M)
        candidates[package] = match[1] if match else None
        metadata=run(['/usr/bin/apt-cache','show',package+'='+candidates[package]]) if match else ''
        digest=re.search(r'^SHA256: ([a-f0-9]{64})$',metadata,re.M)
        hashes[package]=digest[1] if digest else None
    listeners = {}
    for port in (443, 6443, 2379, 2380, 10250):
        with socket.socket() as channel:
            channel.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try: channel.bind((address, port)); listeners[str(port)] = False
            except OSError: listeners[str(port)] = True
    return {'interface': interface, 'package_candidates': candidates, 'package_sha256':hashes,
        'k3s_present': Path('/usr/local/bin/k3s').exists(), 'ports_occupied': listeners,
        'keepalived_configuration_present': Path('/etc/keepalived/keepalived.conf').exists()}


def inspect_k3s(values):
    output={}
    for name,args in {
        'unit':['/usr/bin/systemctl','show','k3s','-p','ActiveState','-p','SubState','-p','Result','-p','ExecMainStatus'],
        'journal':['/usr/bin/journalctl','-u','k3s','-n','160','--no-pager','-o','cat'],
        'version':['/usr/local/bin/k3s','--version'],
    }.items():
        if name=='version' and not Path(args[0]).is_file(): output[name]='';continue
        result=subprocess.run(args,capture_output=True,timeout=20)
        output[name]=result.stdout.decode(errors='replace')+result.stderr.decode(errors='replace')
    output['binary_present']=Path('/usr/local/bin/k3s').is_file()
    output['config_present']=Path('/etc/rancher/k3s/config.yaml').is_file()
    return output


def stop_owned_k3s(values):
    directory=Path('/etc/rancher/k3s')
    if not (directory/'arcia-owner.json').is_file(): return {'owned_installation_present':False,'stopped':True}
    owner=json.loads((directory/'arcia-owner.json').read_text())
    config=json.loads((directory/'config.yaml').read_text())
    token=(directory/'cluster-token').read_text().strip()
    if (owner.get('format')!=1 or owner.get('version')!=values['version'] or config!=values['config'] or
            hashlib.sha256(token.encode()).hexdigest()!=owner.get('token_sha256')):
        raise ValueError('K3S_OWNER_OR_CONFIGURATION_CONFLICT')
    run(['/usr/bin/systemctl','disable','--now','k3s'])
    active=subprocess.run(['/usr/bin/systemctl','is-active','k3s'],capture_output=True).stdout.strip()==b'active'
    return {'owned_installation_present':True,'stopped':not active,'enabled':False,'data_removed':False}


def qualification_paths(values):
    operation=str(uuid.UUID(values['operation_id']))
    return Path('/run/arcia/network-'+operation), 'arcia-net-'+operation


def start_listeners(values):
    directory, unit = qualification_paths(values)
    if Path('/usr/local/bin/k3s').exists(): raise ValueError('PREINSTALL_TEST_REQUIRES_NO_K3S')
    plan = {key:values[key] for key in ('operation_id','node','nodes','challenge','expires_at')}
    if not re.fullmatch(r'[a-f0-9]{64}',plan['challenge']) or not time.time()<plan['expires_at']<=time.time()+310:
        raise ValueError('QUALIFICATION_CHALLENGE_INVALID')
    for node in plan['nodes']: ipaddress.IPv4Address(node)
    if directory.exists():
        existing=json.loads((directory/'plan.json').read_text())
        if existing['operation_id'] != plan['operation_id']: raise ValueError('QUALIFICATION_OWNER_CONFLICT')
        subprocess.run(['/usr/bin/systemctl','stop',unit],capture_output=True,timeout=20,check=False)
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    (directory/'plan.json').write_text(json.dumps(plan));(directory/'plan.json').chmod(0o600)
    (directory/'listener.py').write_text(values['listener_source']);(directory/'listener.py').chmod(0o700)
    run(['/usr/bin/systemd-run','--unit='+unit,'--collect','--property=RuntimeMaxSec=300',
         '--property=NoNewPrivileges=yes','--property=ProtectSystem=strict','--property=PrivateTmp=yes',
         '--property=CapabilityBoundingSet=CAP_NET_BIND_SERVICE',
         '/usr/bin/python3',str(directory/'listener.py'),str(directory/'plan.json')])
    time.sleep(0.3)
    active=run(['/usr/bin/systemctl','is-active',unit]).strip()=='active'
    return {'started':active}


def probe_listeners(values):
    checks=[]
    for index,address in enumerate(values['nodes'],1):
        for port in (443,6443,2379,2380,10250,8472):
            try:
                kind=socket.SOCK_DGRAM if port==8472 else socket.SOCK_STREAM
                with socket.socket(type=kind) as channel:
                    channel.settimeout(2);channel.connect((address,port));channel.sendall(values['challenge'].encode())
                    response=json.loads(channel.recv(1024))
                    passed=response=={'operation_id':values['operation_id'],'node':index,'port':port,'challenge':values['challenge']}
            except Exception: passed=False
            checks.append({'node':index,'port':port,'passed':passed})
    return {'checks':checks,'passed':all(c['passed'] for c in checks)}


def stop_listeners(values):
    directory,unit=qualification_paths(values)
    if directory.exists():
        plan=json.loads((directory/'plan.json').read_text())
        if plan['operation_id']!=values['operation_id']: raise ValueError('QUALIFICATION_OWNER_CONFLICT')
        subprocess.run(['/usr/bin/systemctl','stop',unit],capture_output=True,timeout=20,check=False)
        for name in ('listener.py','plan.json'):
            (directory/name).unlink(missing_ok=True)
        directory.rmdir()
    status=subprocess.run(['/usr/bin/systemctl','is-active',unit],capture_output=True,timeout=10)
    return {'stopped':status.stdout.strip()!=b'active'}


if __name__ == '__main__':
    actions={'inspect':inspect,'inspect_k3s':inspect_k3s,'stop_owned_k3s':stop_owned_k3s,'start_listeners':start_listeners,'probe_listeners':probe_listeners,'stop_listeners':stop_listeners}
    if ARCIA_INPUT['action'] not in actions: raise ValueError('UNKNOWN_FOUNDATION_ACTION')
    print(json.dumps(actions[ARCIA_INPUT['action']](ARCIA_INPUT)))
