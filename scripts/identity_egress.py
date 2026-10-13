"""Reviewable IPv4 egress repair plan; never opens a firewall by itself.

An IP snapshot is a bounded qualification repair, not a DNS-aware firewall.
TLS hostname validation remains mandatory. DNS changes require a new plan.
"""
import hashlib
import ipaddress
import json
import socket
import time
import uuid

HOSTS = ('login.microsoftonline.com', 'graph.microsoft.com')
NS = 'arcia-identity'
NAME = 'keycloak-microsoft-egress'
PLAN_SECONDS = 600
PUBLIC_NAME = 'keycloak-public-https-egress'


def public_https_policy(network, operation=None):
    excluded = [ipaddress.ip_network(cidr) for cidr in (
        '0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16',
        '172.16.0.0/12', '192.0.0.0/24', '192.0.2.0/24', '192.168.0.0/16',
        '198.18.0.0/15', '198.51.100.0/24', '203.0.113.0/24', '224.0.0.0/4', '240.0.0.0/4')]
    for key in ('pod_cidr', 'service_cidr'):
        cidr = ipaddress.ip_network(network[key])
        if cidr.version != 4 or cidr.prefixlen < 8:
            raise ValueError('IDENTITY_PUBLIC_HTTPS_CLUSTER_CIDR_REFUSED')
        excluded.append(cidr)
    annotations = {'arcia.io/egress-mode': 'public-ipv4-443-upstream-firewall'}
    if operation:
        annotations['arcia.io/operation-id'] = str(uuid.UUID(operation))
    return {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
            'metadata': {'name': PUBLIC_NAME, 'namespace': NS, 'annotations': annotations},
            'spec': {'podSelector': {'matchLabels': {'app': 'keycloak'}}, 'policyTypes': ['Egress'],
                     'egress': [{'to': [{'ipBlock': {'cidr': '0.0.0.0/0',
                        'except': [str(cidr) for cidr in ipaddress.collapse_addresses(excluded)]}}],
                        'ports': [{'port': 443, 'protocol': 'TCP'}]}]}}


def retired_snapshot_policy():
    return {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
            'metadata': {'name': NAME, 'namespace': NS,
                         'annotations': {'arcia.io/egress-mode': 'retired-dns-snapshot'}},
            'spec': {'podSelector': {'matchLabels': {'app': 'keycloak'}},
                     'policyTypes': ['Egress'], 'egress': []}}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_addresses(addresses):
    if not isinstance(addresses, dict) or set(addresses) != set(HOSTS):
        raise ValueError('IDENTITY_EGRESS_DESTINATIONS_REFUSED')
    result = {}
    for host in HOSTS:
        values = addresses[host]
        if not isinstance(values, list) or not 1 <= len(values) <= 64:
            raise ValueError('IDENTITY_EGRESS_ADDRESS_COUNT')
        checked = set()
        for value in values:
            try:
                address = ipaddress.ip_address(value)
            except (ValueError, TypeError):
                raise ValueError('IDENTITY_EGRESS_PUBLIC_IPV4_REQUIRED') from None
            if address.version != 4 or not address.is_global or str(address) != value or address.is_multicast:
                raise ValueError('IDENTITY_EGRESS_PUBLIC_IPV4_REQUIRED')
            checked.add(value)
        result[host] = sorted(checked, key=ipaddress.ip_address)
    return result


def resolve():
    return validate_addresses({host: sorted({r[4][0] for r in socket.getaddrinfo(
        host, 443, socket.AF_INET, socket.SOCK_STREAM)}) for host in HOSTS})


def merge_resolutions(snapshots):
    if not isinstance(snapshots, list) or not 1 <= len(snapshots) <= 12:
        raise ValueError('IDENTITY_EGRESS_SNAPSHOT_COUNT')
    checked = [validate_addresses(value) for value in snapshots]
    return validate_addresses({host: list({ip for value in checked for ip in value[host]}) for host in HOSTS})


def policy(addresses, operation):
    operation = str(uuid.UUID(operation))
    addresses = validate_addresses(addresses)
    ips = sorted({ip for values in addresses.values() for ip in values}, key=ipaddress.ip_address)
    return {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
            'metadata': {'name': NAME, 'namespace': NS,
                         'annotations': {'arcia.io/operation-id': operation,
                                         'arcia.io/egress-mode': 'qualification-ipv4-dns-snapshot'}},
            'spec': {'podSelector': {'matchLabels': {'app': 'keycloak'}},
                     'policyTypes': ['Egress'], 'egress': [{
                         'to': [{'ipBlock': {'cidr': ip + '/32'}} for ip in ips],
                         'ports': [{'port': 443, 'protocol': 'TCP'}]}]}}


def plan(addresses, operation, deployment, existing=None, now=None):
    operation = str(uuid.UUID(operation))
    for resource in [deployment] + ([existing] if existing else []):
        if resource.get('metadata', {}).get('annotations', {}).get('arcia.io/operation-id') != operation:
            raise ValueError('IDENTITY_EGRESS_FOREIGN_RESOURCE')
    if (deployment.get('kind') != 'Deployment' or
            deployment['metadata'].get('name') != 'keycloak' or
            deployment['metadata'].get('namespace') != NS or
            deployment.get('spec', {}).get('selector', {}).get('matchLabels') != {'app': 'keycloak'} or
            deployment.get('spec', {}).get('template', {}).get('metadata', {}).get('labels', {}).get('app') != 'keycloak'):
        raise ValueError('IDENTITY_EGRESS_TARGET_REFUSED')
    if existing and (existing.get('kind') != 'NetworkPolicy' or
                     existing['metadata'].get('name') != NAME or existing['metadata'].get('namespace') != NS):
        raise ValueError('IDENTITY_EGRESS_TARGET_REFUSED')
    created = int(time.time() if now is None else now)
    addresses = validate_addresses(addresses)
    result = {'schema_version': 1, 'operation_id': operation, 'created_at': created,
              'expires_at': created + PLAN_SECONDS, 'addresses': addresses,
              'target_uid': deployment['metadata']['uid'],
              'target_version': deployment['metadata']['resourceVersion'],
              'previous_policy_version': existing['metadata']['resourceVersion'] if existing else None,
              'document': policy(addresses, operation),
              'previous_document': existing,
              'approval_required': 'server_verified_teams',
              'limitations': ['ip_filter_not_hostname_filter', 'dns_rotation_requires_new_plan',
                              'no_automatic_expiry_of_kubernetes_rule', 'full_login_not_verified']}
    result['plan_sha256'] = digest(result)
    return result


def validate_plan(value, operation, deployment, existing=None, now=None):
    now = int(time.time() if now is None else now)
    try:
        expected = plan(value['addresses'], operation, deployment, existing, value['created_at'])
        if value != expected or not value['created_at'] <= now < value['expires_at']:
            raise ValueError('IDENTITY_EGRESS_PLAN_STALE_OR_MODIFIED')
    except (KeyError, TypeError):
        raise ValueError('IDENTITY_EGRESS_PLAN_STALE_OR_MODIFIED') from None
    return expected
