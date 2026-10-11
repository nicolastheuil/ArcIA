"""Private network worker: strict SSH, no guest changes, no raw output to agent."""
import json
import ipaddress
from pathlib import Path
import subprocess
import sys
import traceback
from ssh_vmware_preflight import verified_nodes

CHECKS = ('node_mesh_ssh_tcp', 'peer_routes_present', 'github_tls', 'registry_tls',
          'vcenter_tls', 'underlay_mtu_at_least_1500', 'cluster_cidrs_avoid_visible_routes')
ROOT = Path(__file__).resolve().parents[1]


def collect(payload):
    target, nodes = verified_nodes(payload)
    root = Path(payload['private_root']).resolve()
    identity = Path(target['ssh_public_key_path']).resolve().with_suffix('')
    if root.is_relative_to(ROOT) or not identity.is_relative_to(root/'ssh') or not identity.is_file():
        raise ValueError('PRIVATE_DIRECTORY_REQUIRED')
    known = root/'known_hosts.arcia'
    expected = ''.join(n['address']+' ssh-ed25519 '+n['key']+'\n' for n in nodes)
    if known.read_text(encoding='utf-8') != expected: raise ValueError('SSH_TRUST_INTEGRITY')
    connection = payload['connection']
    values = {'nodes': [n['address'] for n in nodes], 'vcenter': connection['server'],
        'vcenter_port': connection['port'], 'vcenter_pin': connection.get('certificate_sha256'), 'endpoints': {},
        'flush_dns_cache': payload.get('flush_dns_cache') is True}
    if payload.get('instance'):
        instance = payload['instance']
        values['cluster_cidrs'] = [instance['config']['network'][key] for key in ('pod_cidr', 'service_cidr')]
        for name, hostname, address in (('api', 'api_endpoint', 'api_ip'), ('https', 'public_hostname', 'https_ip')):
            values['endpoints'][name] = {'name': instance['config']['network'][hostname],
                'ip': instance['endpoint_design'][address]}
    probe = ('NETWORK_INPUT = '+repr(values)+'\n').encode()+ (ROOT/'scripts/node_network_probe.py').read_bytes()
    private, safe_nodes = [], []
    for index, node in enumerate(nodes, 1):
        command = ['ssh', '-F', 'NUL' if sys.platform == 'win32' else '/dev/null', '-T',
            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'IdentityAgent=none', '-o', 'PasswordAuthentication=no', '-o', 'KbdInteractiveAuthentication=no',
            '-o', 'HostKeyAlgorithms=ssh-ed25519', '-o', 'UpdateHostKeys=no', '-o', 'ConnectTimeout=10',
            '-o', 'ConnectionAttempts=1', '-o', 'GlobalKnownHostsFile='+('NUL' if sys.platform == 'win32' else '/dev/null'),
            '-o', 'UserKnownHostsFile='+str(known), '-i', str(identity),
            target['ssh_user']+'@'+node['address'], '/usr/bin/python3 -']
        safe = {'node': 'N'+str(index), 'passed': False}
        try:
            process = subprocess.run(command, input=probe, capture_output=True, timeout=90)
            if process.returncode or len(process.stdout) > 65536: raise ValueError('NETWORK_PROBE_FAILED')
            raw = json.loads(process.stdout)
            if set(raw['checks']) != set(CHECKS) or any(type(v) is not bool for v in raw['checks'].values()):
                raise ValueError('PROBE_FORMAT')
            safe.update(checks=raw['checks'], passed=all(raw['checks'].values()))
            safe['dns_cache_flushed'] = raw.get('dns_cache_flushed') is True
            if values['endpoints']:
                safe['endpoint_dns_matches'] = all(raw['endpoints'][name]['dns_matches_reserved_ip'] is True
                                                   for name in ('api', 'https'))
                safe['endpoint_dns'] = {name: {'matches': raw['endpoints'][name]['dns_matches_reserved_ip'],
                    'address_count': len(raw['endpoints'][name]['resolved']),
                    'error_kind': raw['endpoints'][name].get('error_kind', 'none') if raw['endpoints'][name].get('error_kind', 'none') in
                        ('none', 'not_found', 'temporary_failure', 'resolver_error') else 'resolver_error'} for name in ('api', 'https')}
                safe['endpoint_mdns_suffix'] = any(item['name'].lower().endswith('.local') for item in values['endpoints'].values())
                safe['resolver_uses_designated_dns_directly'] = bool(set(raw.get('resolvers', [])) & set(target['dns']))
                safe['resolver_uses_local_stub'] = any(ipaddress.ip_address(address).is_loopback for address in raw.get('resolvers', []))
                safe['resolved_dns_matches_vm_configuration'] = bool(set(raw.get('resolved_dns', [])) & set(target['dns']))
                safe['resolved_dns_includes_authoritative_server'] = bool(set(raw.get('resolved_dns', [])) & set(payload.get('authoritative_dns', [])))
            private.append({'node': node['node'], 'probe': raw})
        except Exception: safe['code'] = 'SSH_OR_NETWORK_PROBE_FAILED'
        safe_nodes.append(safe)
    controller_overlap = False
    for cidr in payload.get('controller_routes', []):
        route = ipaddress.ip_network(cidr, strict=False)
        if route.prefixlen:
            controller_overlap |= any(route.overlaps(ipaddress.ip_network(pool)) for pool in values.get('cluster_cidrs', []))
    passed = all(n['passed'] for n in safe_nodes) and not controller_overlap
    return {'private': {'operation_id': payload['operation_id'], 'nodes': private},
        'safe': {'status': 'verified' if passed else 'blocked',
            'code': 'BASIC_NETWORK_CHECKS_PASSED' if passed else 'BASIC_NETWORK_CHECKS_FAILED',
            'nodes': safe_nodes, 'passed': passed, 'endpoint_dns_checked': bool(values['endpoints']),
            'cluster_cidrs_checked_against_visible_routes': bool(values.get('cluster_cidrs')),
            'controller_routes_overlap': controller_overlap, 'future_networks_qualified': False,
            'endpoint_failover_qualified': False, 'inter_node_k3s_ports_qualified': False, 'k3s_installed': False}}


def main():
    try: result = collect(json.load(sys.stdin))
    except Exception as exc:
        frames = [frame for frame in traceback.extract_tb(exc.__traceback__) if Path(frame.filename).resolve() == Path(__file__).resolve()]
        code = str(exc) if str(exc) in ('PRIVATE_DIRECTORY_REQUIRED', 'SSH_TRUST_INTEGRITY') else 'LOCAL_NETWORK_PREFLIGHT_FAILED'
        result = {'safe': {'status': 'blocked', 'code': code, 'failure_line': frames[-1].lineno if frames else 0, 'k3s_installed': False}}
    print(json.dumps(result))
    return 0 if result['safe']['status'] == 'verified' else 2


if __name__ == '__main__': sys.exit(main())
