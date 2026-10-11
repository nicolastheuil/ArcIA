"""Private stdin/stdout configuration builder; invoke only through the local GUI."""
import ipaddress
import json
from pathlib import Path
import re
import secrets
import sys
import harness
from ssh_vmware_preflight import verified_nodes
from vmware_deploy import NAMES


def build(payload):
    target, nodes = verified_nodes(payload)
    values, foundation = payload['values'], payload['foundation']
    harness.require(foundation['operation_id'] == payload['operation_id'], 'FOUNDATION_SCOPE')
    root = Path(payload['private_root']).resolve()
    identity = Path(target['ssh_public_key_path']).resolve().with_suffix('')
    harness.require(identity.is_relative_to(root/'ssh') and identity.is_file() and
                    (root/'known_hosts.arcia').is_file(), 'PROTECTED_SSH_FILES_REQUIRED')
    for field in ('api_endpoint', 'public_hostname'):
        value = values[field]
        harness.require(harness.hostname(value) and '.' in value and
                        not re.fullmatch(r'[\d.]+', value), 'ENDPOINT_FQDN_REQUIRED')
    harness.require(values['method'] in ('node_vip', 'existing_load_balancer'), 'ENDPOINT_METHOD_REQUIRED')
    addresses = [ipaddress.ip_address(values[field]) for field in ('api_ip', 'https_ip')]
    networks = [ipaddress.ip_interface(address).network for address in target['addresses']]
    for address in addresses:
        harness.require(address.version == 4 and any(address in ipaddress.ip_network(cidr) for cidr in
            ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')), 'PRIVATE_ENDPOINT_REQUIRED')
        harness.require(str(address) not in [n['address'] for n in nodes] and
                        str(address) != target['gateway'], 'ENDPOINT_ADDRESS_RESERVED')
        if values['method'] == 'node_vip':
            harness.require(len(set(networks)) == 1 and address in networks[0] and
                address not in (networks[0].network_address, networks[0].broadcast_address), 'VIP_L2_REQUIRED')
    harness.require(values['addresses_reserved'] is True, 'ADDRESS_RESERVATION_REQUIRED')
    policies = [p for p in foundation['policies'] if p['id'] == values['policy_id'] and p['compatible'] is True]
    harness.require(len(policies) == 1, 'COMPATIBLE_POLICY_REQUIRED')
    config = {'schema_version': 1, 'synthetic': False,
        'github': {'account': 'nicolastheuil', 'repository': 'arcia-harness', 'visibility': 'private'},
        'nodes': [{'name': name, 'address': nodes[i]['address'], 'ssh_user': target['ssh_user'],
            'ssh_port': 22, 'identity_file': str(identity), 'known_hosts_file': str(root/'known_hosts.arcia')}
            for i, name in enumerate(NAMES)],
        'network': {k: values[k] for k in ('api_endpoint', 'public_hostname', 'pod_cidr', 'service_cidr')},
        'storage': {'storage_class': 'arcia-vsphere', 'policy_ref': policies[0]['id']},
        'gates': {gate: 'pending' for gate in harness.GATES}}
    cidrs = [str(ipaddress.ip_network(cidr.strip(), strict=True)) for cidr in values['existing_cidrs'].split(',') if cidr.strip()]
    config['network'].update(existing_cidrs=list(dict.fromkeys(cidrs+[str(n) for n in networks])), existing_cidrs_reviewed=False)
    harness.validate(config)
    for address in addresses:
        harness.require(not any(address in ipaddress.ip_network(config['network'][key])
            for key in ('pod_cidr', 'service_cidr')), 'ENDPOINT_CIDR_OVERLAP')
    return {'config': config, 'k3s_token': secrets.token_hex(32), 'operation_id': payload['operation_id'],
        'endpoint_design': {'method': values['method'], 'api_ip': str(addresses[0]), 'https_ip': str(addresses[1]),
            'addresses_reserved': True, 'enterprise_vpn_cidrs_attested': False,
            'known_cidrs_reviewed': values['cidrs_reviewed'] is True,
            'inventory_scope': 'current_underlay_and_known_routes',
            'future_networks_unknown': True, 'vpn_activation_requires_route_guard': True},
        'qualification_evidence': {}}


def main():
    try:
        result = {'bundle': build(json.load(sys.stdin)), 'safe': {'status': 'configured', 'code': 'CONFIGURATION_ENCRYPTED_GATES_PENDING'}}
    except harness.Invalid as exc:
        result = {'safe': {'status': 'blocked', 'code': str(exc)}}
    except Exception:
        result = {'safe': {'status': 'blocked', 'code': 'INVALID_LOCAL_CONFIGURATION'}}
    print(json.dumps(result))
    return 0 if 'bundle' in result else 2


if __name__ == '__main__': sys.exit(main())
