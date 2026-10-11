"""Fixed root operations for the designated node VIP, private worker I/O."""
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
import uuid

OWNER=Path('/var/lib/arcia/vip-owner.json')
CONF=Path('/etc/keepalived/keepalived.conf')
HEALTH=Path('/usr/local/libexec/arcia-vip-health')


def run(args,timeout=30):
    return subprocess.run(args,capture_output=True,check=True,timeout=timeout).stdout.decode()


def design(values):
    operation=str(uuid.UUID(values['operation_id']))
    addresses=[str(ipaddress.IPv4Address(a)) for a in values['nodes']]
    if len(addresses)!=3 or len(set(addresses))!=3: raise ValueError('THREE_UNIQUE_NODES_REQUIRED')
    index=values['node']
    if type(index)!=int or index not in (1,2,3): raise ValueError('NODE_INDEX_INVALID')
    network=ipaddress.IPv4Network(values['subnet'])
    vips=list(dict.fromkeys(str(ipaddress.IPv4Address(a)) for a in values['vips']))
    if not vips or any(ipaddress.IPv4Address(a) not in network or a in addresses or
            a in (str(network.network_address),str(network.broadcast_address),values['gateway']) for a in vips):
        raise ValueError('VIP_SCOPE_INVALID')
    if type(values['vrid'])!=int or not 1<=values['vrid']<=255 or not re.fullmatch('[A-Za-z0-9]{8}',values['password']):
        raise ValueError('VRRP_IDENTITY_INVALID')
    interface=json.loads(run(['/usr/sbin/ip','-j','route','get',addresses[index%3]]))[0]['dev']
    if not re.fullmatch('[A-Za-z0-9_.:-]{1,15}',interface): raise ValueError('INTERFACE_INVALID')
    peers='\n'.join('        '+a for a in addresses if a!=addresses[index-1])
    vip_lines='\n'.join('        '+a+'/'+str(network.prefixlen)+' dev '+interface for a in vips)
    content=f'''# ArcIA owner {operation}
global_defs {{
    enable_script_security
    script_user root
}}
vrrp_script arcia_api_ready {{
    script "/usr/local/libexec/arcia-vip-health"
    interval 1
    timeout 4
    fall 2
    rise 2
    init_fail
}}
vrrp_instance ARCIA {{
    state BACKUP
    interface {interface}
    virtual_router_id {values['vrid']}
    priority {160-index*10}
    advert_int 1
    nopreempt
    unicast_src_ip {addresses[index-1]}
    check_unicast_src
    unicast_fault_no_peer
    unicast_peer {{
{peers}
    }}
    authentication {{
        auth_type PASS
        auth_pass {values['password']}
    }}
    virtual_ipaddress {{
{vip_lines}
    }}
    track_script {{
        arcia_api_ready
    }}
}}
'''
    marker={'operation_id':operation,'configuration_sha256':hashlib.sha256(content.encode()).hexdigest(),
        'health_sha256':hashlib.sha256(values['health_source'].encode()).hexdigest(),
        'packages':values['packages']}
    if OWNER.exists():
        if json.loads(OWNER.read_text())!=marker: raise ValueError('VIP_OWNER_OR_PLAN_CONFLICT')
        for path,key in ((CONF,'configuration_sha256'),(HEALTH,'health_sha256')):
            if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()!=marker[key]: raise ValueError('VIP_MANUAL_DRIFT')
    elif CONF.exists() or HEALTH.exists(): raise ValueError('FOREIGN_VIP_CONFIGURATION')
    return marker,content,interface,vips


def preflight(values):
    marker,content,interface,vips=design(values)
    if not OWNER.exists():
        with socket.socket(socket.AF_INET,socket.SOCK_RAW,112) as channel:
            channel.bind((values['nodes'][values['node']-1],0));channel.settimeout(.25)
            expires=time.monotonic()+3
            while time.monotonic()<expires:
                try: packet,_=channel.recvfrom(65535)
                except socket.timeout: continue
                offset=(packet[0]&15)*4
                if len(packet)>offset+1 and packet[offset+1]==values['vrid']:
                    raise ValueError('VRRP_ID_ALREADY_VISIBLE')
    return {'owner_present':OWNER.exists(),'preflight_passed':True}


def install(values):
    marker,content,interface,vips=design(values)
    OWNER.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
    if not OWNER.exists(): OWNER.write_text(json.dumps(marker));OWNER.chmod(0o600)
    for name,pin in values['packages'].items():
        if name not in ('keepalived','iputils-arping') or not re.fullmatch('[a-f0-9]{64}',pin['sha256']):
            raise ValueError('PACKAGE_PIN_INVALID')
        query=subprocess.run(['/usr/bin/dpkg-query','-W','-f=${Status}\t${Version}',name],capture_output=True)
        if query.returncode==0 and query.stdout.startswith(b'install ok installed\t'):
            if query.stdout.decode().split('\t')[1]!=pin['version']: raise ValueError('FOREIGN_PACKAGE_VERSION')
            continue
        # The mask prevents package postinst from starting an unconfigured VIP service.
        run(['/usr/bin/systemctl','mask','keepalived'])
        with tempfile.TemporaryDirectory(prefix='arcia-deb-',dir='/var/cache') as temp:
            process=subprocess.run(['/usr/bin/apt-get','download',name+'='+pin['version']],cwd=temp,capture_output=True,timeout=120)
            if process.returncode: raise ValueError('PINNED_PACKAGE_DOWNLOAD_FAILED')
            packages=list(Path(temp).glob('*.deb'))
            if len(packages)!=1 or hashlib.sha256(packages[0].read_bytes()).hexdigest()!=pin['sha256']:
                raise ValueError('PINNED_PACKAGE_HASH_MISMATCH')
            run(['/usr/bin/apt-get','install','--yes','--no-install-recommends',str(packages[0])],timeout=180)
    # First assignment is preceded by duplicate-address detection on the selected interface.
    if not CONF.exists():
        for address in vips:
            result=subprocess.run(['/usr/bin/arping','-D','-c','3','-w','4','-I',interface,address],capture_output=True,timeout=6)
            if result.returncode!=0: raise ValueError('RESERVED_VIP_ALREADY_IN_USE')
    CONF.parent.mkdir(parents=True,mode=0o755,exist_ok=True)
    HEALTH.parent.mkdir(parents=True,mode=0o755,exist_ok=True)
    HEALTH.write_text(values['health_source']);HEALTH.chmod(0o700)
    CONF.write_text(content);CONF.chmod(0o600)
    run(['/usr/sbin/keepalived','--config-test','--use-file='+str(CONF)])
    run(['/usr/bin/systemctl','unmask','keepalived'])
    run(['/usr/bin/systemctl','enable','--now','keepalived'])
    return {'installed':True,'configuration_valid':True,'vmac_used':False,'firewall_modified':False}


def state(values):
    marker,content,interface,vips=design(values)
    if not OWNER.exists(): raise ValueError('VIP_NOT_OWNED')
    addresses=json.loads(run(['/usr/sbin/ip','-j','address','show','dev',interface]))
    local={a['local'] for link in addresses for a in link.get('addr_info',[]) if a['family']=='inet'}
    active=subprocess.run(['/usr/bin/systemctl','is-active','keepalived'],capture_output=True).stdout.strip()==b'active'
    return {'active':active,'owns_all_vips':all(a in local for a in vips),'owns_any_vip':any(a in local for a in vips)}


def service(values):
    design(values)
    if not OWNER.exists(): raise ValueError('VIP_NOT_OWNED')
    verb={'stop_vip':'stop','start_vip':'start'}[values['action']]
    run(['/usr/bin/systemctl',verb,'keepalived'])
    return {'completed':True}


def probe(values):
    design(values)
    checks=[]
    for address,port in ((values['vips'][0],6443),(values['vips'][-1],443)):
        try:
            with socket.create_connection((address,port),timeout=2) as channel:
                channel.sendall(values['challenge'].encode());response=json.loads(channel.recv(1024))
            passed=(response['operation_id']==values['operation_id'] and response['port']==port and
                    response['node']==values['expected_owner'] and response['challenge']==values['challenge'])
        except Exception: passed=False
        checks.append(passed)
    return {'passed':all(checks),'checks':checks}


if __name__=='__main__':
    actions={'preflight_vip':preflight,'install_vip':install,'vip_state':state,
             'stop_vip':service,'start_vip':service,'probe_vip':probe}
    print(json.dumps(actions[ARCIA_INPUT['action']](ARCIA_INPUT)))
