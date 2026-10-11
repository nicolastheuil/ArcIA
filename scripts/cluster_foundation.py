"""Typed foundation worker. Never invoke directly with inherited tool stdout."""
import json
from pathlib import Path
import re
import sys
import traceback
import uuid
import secrets
import time
import ipaddress
import subprocess
import harness
from ssh_transport import transport, guest

ROOT = Path(__file__).resolve().parents[1]


def install_k3s(payload,target,nodes,base):
    instance=payload['instance'];lock=json.loads((ROOT/'versions.lock.yaml').read_text())
    config=harness.validate(instance['config'])
    blockers=harness.installation_blockers(config,lock)
    if blockers: raise ValueError('PREINSTALL_QUALIFICATIONS_REQUIRED')
    inventory=harness.render(config,instance['k3s_token'],lock)
    root=Path(payload['private_root']).resolve()
    identity=Path(target['ssh_public_key_path']).resolve().with_suffix('')
    files={str(p.relative_to(ROOT)).replace('\\','/'):p.read_text() for p in (ROOT/'infra/ansible').rglob('*') if p.is_file()}
    files['scripts/node_probe.py']=(ROOT/'scripts/node_probe.py').read_text()
    data={'files':files,'inventory':inventory,'identity':identity.read_text(),
          'known_hosts':(root/'known_hosts.arcia').read_text()}
    process=subprocess.run(['wsl.exe','-e','/home/nicolas/.local/share/arcia-validation/bin/python','-c',
        (ROOT/'scripts/wsl_ansible.py').read_text()],input=json.dumps(data).encode(),capture_output=True,timeout=5100)
    if process.returncode: raise ValueError('PROTECTED_LINUX_CONTROLLER_FAILED')
    result=json.loads(process.stdout)
    passed=result['returncode']==0 and len(result['stats'])==3 and all(s['failures']==0 and s['unreachable']==0 for s in result['stats'])
    return {'private':{'operation_id':payload['operation_id'],'ansible':result},
        'safe':{'status':'installed' if passed else 'blocked','code':'K3S_THREE_SERVERS_INSTALLED' if passed else 'K3S_INSTALLATION_FAILED',
                'k3s_installed':passed,'server_count':len(result['stats']),'k3s_version':lock['components']['k3s']['version'],
                'secrets_encryption_verified':passed,'production_failover_qualified':False,'csi_qualified':False}}


def vip_operation(payload,target,nodes,base):
    operation=payload['operation_id']
    instance=payload['instance']
    if instance['endpoint_design']['method']!='node_vip': raise ValueError('NODE_VIP_DESIGN_REQUIRED')
    if payload['vip_journal']['operation_id']!=operation: raise ValueError('VIP_JOURNAL_SCOPE')
    script=(ROOT/'scripts/node_vip.py').read_bytes()
    addresses=[n['address'] for n in nodes]
    subnet=str(ipaddress.ip_interface(target['addresses'][0]).network)
    common={'operation_id':operation,'nodes':addresses,'subnet':subnet,'gateway':target['gateway'],
        'vips':[instance['endpoint_design']['api_ip'],instance['endpoint_design']['https_ip']],
        'vrid':payload['vip_journal']['vrid'],'password':payload['vip_journal']['password'],
        'health_source':(ROOT/'scripts/vip_health.py').read_text(),
        'packages':json.loads((ROOT/'versions.lock.yaml').read_text())['node_vip']['packages']}
    def call(index,action,**extra):
        return guest(target,nodes[index-1],base,script,{**common,'node':index,'action':action,**extra},root=True,timeout=420)
    if payload['action']=='install_vip':
        preflight=[call(i,'preflight_vip') for i in (1,2,3)]
        installed=[call(i,'install_vip') for i in (1,2,3)]
        return {'private':{'operation_id':operation,'preflight':preflight,'installed':installed},
            'safe':{'status':'installed','code':'NODE_VIP_INSTALLED_NOT_YET_QUALIFIED','node_count':3,
                    'configuration_valid':all(r['configuration_valid'] for r in installed),'firewall_modified':False,
                    'vmac_used':False,'k3s_installed':False}}
    if payload['action']=='inspect_vip':
        states=[call(i,'vip_state') for i in (1,2,3)]
        return {'private':{'operation_id':operation,'states':states},
            'safe':{'status':'inspected','code':'NODE_VIP_STATE_INSPECTED','active_service_count':sum(s['active'] for s in states),
                    'vip_owner_count':sum(s['owns_any_vip'] for s in states)}}
    if payload['action']!='qualify_vip': raise ValueError('UNKNOWN_VIP_ACTION')
    listener=(ROOT/'scripts/node_foundation.py').read_bytes()
    challenge=secrets.token_hex(32)
    lease={'operation_id':operation,'nodes':addresses,'challenge':challenge,'expires_at':time.time()+300}
    started=[];cleanup=[];phases=[];stopped=None;passed=False
    def owner(exclude=None):
        expires=time.monotonic()+20
        while time.monotonic()<expires:
            states=[call(i,'vip_state') for i in (1,2,3)]
            owners=[i for i,s in enumerate(states,1) if s['owns_all_vips']]
            if sum(s['owns_any_vip'] for s in states)>1: raise ValueError('MULTIPLE_VIP_OWNERS')
            if len(owners)==1 and owners[0]!=exclude: return owners[0]
            time.sleep(1)
        raise ValueError('SINGLE_VIP_OWNER_NOT_READY')
    try:
        for index,node in enumerate(nodes,1):
            started.append(node)
            guest(target,node,base,listener,{**lease,'node':index,'action':'start_listeners',
                'listener_source':(ROOT/'scripts/network_listener.py').read_text()},root=True)
        first=owner()
        for phase,expected in (('initial',first),('after_failover',None)):
            if expected is None:
                stopped=first;call(first,'stop_vip');expected=owner(exclude=first)
            checks=[call(i,'probe_vip',challenge=challenge,expected_owner=expected) for i in (1,2,3)]
            phases.append({'phase':phase,'owner':expected,'checks':checks})
            if not all(c['passed'] for c in checks): raise ValueError('VIP_TRANSPORT_PROBE_FAILED')
        call(first,'start_vip');stopped=None
        final=owner()
        passed=final==phases[-1]['owner'] # nopreempt: returning node must not steal the VIP.
    finally:
        if stopped is not None:
            try: call(stopped,'start_vip')
            except Exception: cleanup.append(False)
        for node in started:
            try: cleanup.append(guest(target,node,base,listener,{'action':'stop_listeners','operation_id':operation},root=True)['stopped'])
            except Exception: cleanup.append(False)
        # The synthetic health lease is gone; no production API has been started yet.
        time.sleep(4)
        states=[call(i,'vip_state') for i in (1,2,3)]
        withdrawn=not any(s['owns_any_vip'] for s in states)
        passed=passed and len(cleanup)==3 and all(cleanup) and withdrawn
        if not passed:
            for i in (1,2,3):
                try: call(i,'stop_vip')
                except Exception: pass
    return {'private':{'operation_id':operation,'phases':phases,'cleanup':cleanup,'states_after':states},
        'safe':{'status':'verified' if passed else 'blocked','code':'NODE_VIP_TRANSPORT_FAILOVER_VERIFIED' if passed else 'NODE_VIP_QUALIFICATION_FAILED',
            'node_count':3,'api_and_https_checked':True,'transport_checks':sum(len(c['checks']) for p in phases for c in p['checks']),
            'single_owner_failover':passed,'returning_node_did_not_preempt':passed,'temporary_listeners_stopped':all(cleanup),
            'vip_withdrawn_without_healthy_api':withdrawn,'production_k3s_failover_verified':False,'k3s_installed':False}}


def collect(payload):
    operation = str(uuid.UUID(payload['operation_id']))
    if payload['instance']['operation_id'] != operation: raise ValueError('INSTANCE_SCOPE_MISMATCH')
    action = payload['action']
    if action not in ('inspect','qualify_ports','install_vip','qualify_vip','inspect_vip','install_k3s'): raise ValueError('UNKNOWN_FOUNDATION_ACTION')
    target, nodes, base = transport(payload)
    if action=='install_k3s': return install_k3s(payload,target,nodes,base)
    if action in ('install_vip','qualify_vip','inspect_vip'): return vip_operation(payload,target,nodes,base)
    script = (ROOT/'scripts/node_foundation.py').read_bytes()
    if action == 'qualify_ports':
        challenge=secrets.token_hex(32)
        common={'operation_id':operation,'nodes':[n['address'] for n in nodes],
                'challenge':challenge,'expires_at':time.time()+300}
        results=[];cleanup=[];started=[]
        try:
            for index,node in enumerate(nodes,1):
                started.append(node)
                values={**common,'action':'start_listeners','node':index,
                        'listener_source':(ROOT/'scripts/network_listener.py').read_text()}
                if not guest(target,node,base,script,values,root=True)['started']: raise ValueError('TEMPORARY_LISTENER_NOT_STARTED')
            for node in nodes:
                results.append(guest(target,node,base,script,{**common,'action':'probe_listeners'},root=True))
        finally:
            for node in started:
                try: cleanup.append(guest(target,node,base,script,{'action':'stop_listeners','operation_id':operation},root=True)['stopped'])
                except Exception: cleanup.append(False)
        passed=len(results)==3 and all(r['passed'] for r in results) and len(cleanup)==3 and all(cleanup)
        return {'private':{'operation_id':operation,'nodes':results,'cleanup':cleanup},
            'safe':{'status':'verified' if passed else 'blocked','code':'UNDERLAY_K3S_PORTS_VERIFIED' if passed else 'UNDERLAY_K3S_PORTS_FAILED',
                    'node_count':len(results),'tcp_ports':[443,6443,2379,2380,10250],'udp_ports':[8472],
                    'directional_checks':sum(len(r['checks']) for r in results),
                    'passed_check_count':sum(sum(c['passed'] for c in r['checks']) for r in results),
                    'temporary_listeners_stopped':len(cleanup)==3 and all(cleanup),'firewall_modified':False,'k3s_installed':False}}
    results = []
    for node in nodes:
        values = {'action': action, 'operation_id': operation, 'address': node['address'],
                  'peers': [n['address'] for n in nodes if n != node]}
        results.append(guest(target, node, base, script, values, root=True))
    candidates = [r['package_candidates'] for r in results]
    coherent = all(value == candidates[0] for value in candidates)
    safe_versions = {k: v if isinstance(v,str) and re.fullmatch(r'[0-9][A-Za-z0-9.+:~_-]{0,59}',v) else 'unavailable'
                     for k,v in candidates[0].items()}
    return {'private': {'operation_id': operation, 'nodes': results},
        'safe': {'status': 'inspected', 'code': 'NODE_FOUNDATION_INSPECTED', 'node_count': len(results),
            'package_candidates_consistent': coherent, 'package_candidates': safe_versions,
            'package_sha256':{k:v if isinstance(v,str) and re.fullmatch(r'[a-f0-9]{64}',v) else None for k,v in results[0]['package_sha256'].items()},
            'k3s_present_count': sum(r['k3s_present'] for r in results),
            'existing_keepalived_configuration_count': sum(r['keepalived_configuration_present'] for r in results),
            'occupied_listener_count': sum(sum(r['ports_occupied'].values()) for r in results), 'mutations_performed': False}}


def main():
    try: result = collect(json.load(sys.stdin))
    except Exception as exc:
        result = {'private': {'failure': traceback.format_exc(), 'guest_failure':getattr(exc,'private_output',None)},
                  'safe': {'status': 'blocked', 'code': 'CLUSTER_FOUNDATION_ACTION_FAILED', 'k3s_installed': False}}
    print(json.dumps(result))
    return 2 if result['safe']['status'] == 'blocked' else 0


if __name__ == '__main__': sys.exit(main())
