"""Read-only guest probe. Inputs are prepended by the protected worker."""
import hashlib
import ipaddress
import json
import socket
import ssl
import subprocess
from pathlib import Path


def tcp(host, port):
    try:
        with socket.create_connection((host, port), timeout=3): return True
    except OSError: return False


def tls(host, port=443, fingerprint=None):
    context = ssl.create_default_context()
    if fingerprint:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=3) as connection:
            connection.settimeout(5)
            with context.wrap_socket(connection, server_hostname=host) as channel:
                return (hashlib.sha256(channel.getpeercert(binary_form=True)).hexdigest() == fingerprint
                        if fingerprint else True)
    except (OSError, ValueError): return False


def route(host):
    try:
        result = subprocess.run(['/usr/sbin/ip', '-j', 'route', 'get', host],
                                capture_output=True, timeout=3, check=True)
        return json.loads(result.stdout)[0]
    except Exception: return {}


def probe(values):
    cache_flushed = False
    if values.get('flush_dns_cache') is True:
        try:
            subprocess.run(['/usr/bin/sudo', '-n', '/usr/bin/resolvectl', 'flush-caches'],
                           capture_output=True, timeout=10, check=True)
            cache_flushed = True
        except Exception: pass
    routes = [route(host) for host in values['nodes']]
    checks = {'node_mesh_ssh_tcp': all(tcp(host, 22) for host in values['nodes']),
        'peer_routes_present': all(value.get('dev') for value in routes) is True,
        'github_tls': tls('github.com'), 'registry_tls': tls('registry.k8s.io'),
        'vcenter_tls': tls(values['vcenter'], values['vcenter_port'], values.get('vcenter_pin'))}
    # Preserve raw routing only in the encrypted result, never the safe summary.
    try:
        links = json.loads(subprocess.run(['/usr/sbin/ip', '-j', 'link'], capture_output=True,
                                          timeout=3, check=True).stdout)
        interfaces = {value.get('dev') for value in routes}
        selected = [link for link in links if link['ifname'] in interfaces and link['ifname'] != 'lo']
        checks['underlay_mtu_at_least_1500'] = bool(selected) and all(link['mtu'] >= 1500 for link in selected)
    except Exception: checks['underlay_mtu_at_least_1500'] = False
    visible_routes = []
    try:
        visible_routes = json.loads(subprocess.run(['/usr/sbin/ip', '-j', '-4', 'route', 'show', 'table', 'all'],
            capture_output=True, timeout=3, check=True).stdout)
        destinations = [ipaddress.ip_network(item['dst'], strict=False) for item in visible_routes
                        if item.get('dst') and item['dst'] != 'default']
        pools = [ipaddress.ip_network(pool) for pool in values.get('cluster_cidrs', [])]
        checks['cluster_cidrs_avoid_visible_routes'] = all(not pool.overlaps(route) for pool in pools
            for route in destinations if route.prefixlen > 0)
    except Exception: checks['cluster_cidrs_avoid_visible_routes'] = False
    endpoints = {}
    for name, item in values.get('endpoints', {}).items():
        try:
            addresses = {entry[4][0] for entry in socket.getaddrinfo(item['name'], None, socket.AF_INET)}
            endpoints[name] = {'dns_matches_reserved_ip': addresses == {item['ip']}, 'resolved': sorted(addresses)}
        except socket.gaierror as exc:
            endpoints[name] = {'dns_matches_reserved_ip': False, 'resolved': [],
                'error_kind': 'not_found' if exc.errno == socket.EAI_NONAME else 'temporary_failure' if exc.errno == socket.EAI_AGAIN else 'resolver_error'}
        except OSError: endpoints[name] = {'dns_matches_reserved_ip': False, 'resolved': [], 'error_kind': 'resolver_error'}
    resolver_text = Path('/etc/resolv.conf').read_text()
    resolvers = [line.split()[1] for line in resolver_text.splitlines() if line.startswith('nameserver ') and len(line.split()) > 1]
    resolved_dns = []
    try:
        dns_text = subprocess.run(['/usr/bin/resolvectl', 'dns'], capture_output=True, check=True, timeout=5).stdout.decode()
        for line in dns_text.splitlines():
            for value in line.partition(':')[2].split():
                try: resolved_dns.append(str(ipaddress.ip_address(value.split('#')[0])))
                except ValueError: pass
    except Exception: dns_text = ''
    return {'checks': checks, 'routes': routes, 'visible_routes': visible_routes, 'endpoints': endpoints,
            'resolvers': resolvers, 'resolver_text': resolver_text, 'resolved_dns': resolved_dns, 'resolved_dns_text': dns_text,
            'dns_cache_flushed': cache_flushed}


if __name__ == '__main__': print(json.dumps(probe(NETWORK_INPUT)))
