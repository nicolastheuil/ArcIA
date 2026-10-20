"""Recette agentgateway OSS réelle, isolée, sans donnée privée ni fournisseur cloud.

Cette première porte qualifie bootstrap/JWT/CEL ; elle n'atteste ni Presidio,
ni la conversion du chat vers A2A, ni les artefacts Hermes.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import yaml
import deploy

ROOT = Path(__file__).resolve().parents[1]
AUTH_CHECKS = ('valid_a', 'valid_b', 'wrong_tenant', 'wrong_user', 'missing_grant', 'anonymous',
               'forged_headers', 'invalid_signature', 'expired', 'wrong_audience', 'wrong_issuer',
               'missing_exp', 'missing_sub')


def require_owned_namespace(runner, namespace, nonce):
    if len(nonce) != 32 or any(c not in '0123456789abcdef' for c in nonce) or namespace != 'arcia-qual-gateway-' + nonce[:12]:
        raise ValueError('Namespace de qualification non conforme')
    rc, output, _ = runner.run(['get', 'namespace', namespace, '-o', 'json'], timeout=20)
    if rc or json.loads(output).get('metadata', {}).get('annotations', {}).get('arcia.io/qualification') != nonce:
        raise ValueError('Namespace non possédé par cette exécution')


def jwt_qualification_config():
    return {'binds': [{'port': 3000, 'listeners': [{'routes': [{'policies': {
        'jwtAuth': {'mode': 'strict', 'issuer': 'https://issuer.synthetic.invalid',
            'audiences': ['arcia-qualification'], 'jwks': {'file': '/etc/agentgateway/jwks.json'},
            'jwtValidationOptions': {'requiredClaims': ['iss', 'sub', 'exp', 'aud']}},
        'authorization': {'rules': [{'require': 'jwt.arcia_tenant_id == request.headers["x-arcia-tenant"] '
            '&& jwt.sub == request.headers["x-arcia-user"] && "invoke" in jwt.arcia_grants'}]}},
        'backends': [{'host': 'gateway-witness:9900'}]}]}]}]}


def build_capability_report(checks, *, bootstrap_closed):
    authenticated = bool(checks) and all(checks.get(name) is True for name in AUTH_CHECKS)
    capabilities = {'bootstrap_closed': {'qualified': bootstrap_closed is True},
                    'jwt_cel': {'qualified': authenticated}}
    for name in ('llm_inference', 'presidio', 'mcp_acl', 'chat_a2a', 'hermes_artifacts', 'budgets', 'recovery'):
        capabilities[name] = {'qualified': False, 'reason': 'not_tested'}
    return {'implementation': 'agentgateway', 'schema_version': 1, 'capabilities': capabilities,
            'activation_allowed': False, 'security_release_ready': False}


def signing_material():
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()

    def encoded(number):
        return base64.urlsafe_b64encode(number.to_bytes((number.bit_length() + 7) // 8, 'big')).rstrip(b'=').decode()

    return key, {'keys': [{'kty': 'RSA', 'kid': 'qualification', 'alg': 'RS256', 'use': 'sig',
                           'n': encoded(numbers.n), 'e': encoded(numbers.e)}]}


def qualification_tokens(key):
    import jwt
    now = int(time.time())
    claims = {'iss': 'https://issuer.synthetic.invalid', 'aud': 'arcia-qualification', 'sub': 'alice',
              'exp': now + 300, 'arcia_tenant_id': 'tenant-a', 'arcia_grants': ['invoke']}
    variants = {'valid_a': {}, 'valid_b': {'sub': 'bob', 'arcia_tenant_id': 'tenant-b'},
        'missing_grant': {'arcia_grants': []}, 'expired': {'exp': now - 3600},
        'wrong_audience': {'aud': 'another-api'}, 'wrong_issuer': {'iss': 'https://other.synthetic.invalid'},
        'missing_exp': {}, 'missing_sub': {}, 'invalid_signature': {}}
    other_key, _ = signing_material()
    tokens = {}
    for name, changes in variants.items():
        body = dict(claims, **changes)
        if name in ('missing_exp', 'missing_sub'):
            body.pop(name.removeprefix('missing_'))
        tokens[name] = jwt.encode(body, other_key if name == 'invalid_signature' else key,
                                  algorithm='RS256', headers={'kid': 'qualification'})
    return tokens


def runner_for(config):
    k = config.get('kubernetes', {})
    s = k.get('remote_ssh', {})
    identity, known = deploy.find_harness_ssh()
    configured = os.path.expandvars(os.path.expanduser(s.get('ssh_key', '')))
    return deploy.K8sRunner(mode=k.get('mode', 'local'), kubeconfig=k.get('kubeconfig', ''), context=k.get('context', ''),
        ssh_node=s.get('node_ip', '127.0.0.1'), ssh_user=s.get('ssh_user', 'debian'), ssh_port=s.get('ssh_port', 22),
        ssh_key=configured if configured and Path(configured).is_file() else identity,
        known_hosts=known or s.get('known_hosts_file', ''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--report', default='artifacts/agentgateway-qualification.json')
    args = parser.parse_args()
    runner = runner_for(deploy.parse_yaml_or_env(args.config))
    versions = json.loads((ROOT / 'deploy/versions.json').read_text(encoding='utf-8'))['components']
    nonce = uuid.uuid4().hex
    namespace = 'arcia-qual-gateway-' + nonce[:12]
    report = {'implementation': 'agentgateway', 'namespace': namespace, 'passed': False,
        'production_modified': False, 'cloud_provider': False, 'cleanup_verified': False,
        'image': versions['agentgateway']['image'], 'scope': 'synthetic_http_jwt_cel',
        'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    stage = 'bootstrap'

    def apply(obj):
        runner.apply_manifest(obj if isinstance(obj, str) else json.dumps(obj))

    def configmap(config, jwks=None):
        data = {'config.yaml': yaml.safe_dump(config)}
        if jwks is not None:
            data['jwks.json'] = json.dumps(jwks)
        apply({'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'agentgateway-config', 'namespace': namespace}, 'data': data})

    def rollout(name):
        rc, _, _ = runner.run(['rollout', 'status', 'deployment/' + name, '-n', namespace, '--timeout=180s'], timeout=200)
        if rc:
            raise RuntimeError('Workload de qualification indisponible')

    def probe(payload):
        source = 'import io,sys\nsys.stdin=io.StringIO(' + repr(json.dumps(payload)) + ')\n'
        source += (ROOT / 'tests/fixtures/agentgateway_auth_probe.py').read_text(encoding='utf-8')
        rc, output, _ = runner.run(['exec', '-i', 'deployment/gateway-witness', '-n', namespace, '--', 'python3', '-'],
                                  stdin_input=source, timeout=150)
        prefix = 'ARCIA_AGENTGATEWAY='
        if rc or not any(line.startswith(prefix) for line in output.splitlines()):
            raise RuntimeError('Sonde native indisponible')
        return json.loads(next(line[len(prefix):] for line in output.splitlines() if line.startswith(prefix)))

    try:
        print('Création du namespace synthétique agentgateway.', flush=True)
        apply({'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': namespace, 'annotations': {'arcia.io/qualification': nonce}}})
        require_owned_namespace(runner, namespace, nonce)
        apply({'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy', 'metadata': {'name': 'qualification-isolation', 'namespace': namespace},
            'spec': {'podSelector': {}, 'policyTypes': ['Ingress', 'Egress'],
                'ingress': [{'from': [{'podSelector': {}}]}],
                'egress': [{'to': [{'podSelector': {}}]}, {'to': [{'namespaceSelector': {}, 'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
                    'ports': [{'protocol': 'UDP', 'port': 53}, {'protocol': 'TCP', 'port': 53}]}]}})
        configmap(yaml.safe_load((ROOT / 'deploy/agentgateway/config.yaml').read_text(encoding='utf-8')))
        apply(deploy.adapt_manifest_namespace((ROOT / 'deploy/manifests/05-agentgateway.yaml').read_text(encoding='utf-8'), namespace))
        # Dans cette seule qualification, le témoin peut joindre le gateway ;
        # le DenyAll du manifeste reste la base des futures instances.
        apply({'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy', 'metadata': {'name': 'qualification-gateway-access', 'namespace': namespace},
            'spec': {'podSelector': {'matchLabels': {'app': 'agentgateway'}}, 'policyTypes': ['Ingress', 'Egress'],
                'ingress': [{'from': [{'podSelector': {'matchLabels': {'app': 'gateway-witness'}}}], 'ports': [{'port': 3000}]}],
                'egress': [{'to': [{'podSelector': {'matchLabels': {'app': 'gateway-witness'}}}], 'ports': [{'port': 9900}]}]}})
        pod = {'automountServiceAccountToken': False, 'containers': [{'name': 'witness', 'image': versions['hermes-agent']['image'],
            'command': ['python3', '-m', 'http.server', '9900'], 'resources': {'requests': {'cpu': '50m', 'memory': '64Mi'},
            'limits': {'cpu': '200m', 'memory': '256Mi'}}, 'readinessProbe': {'tcpSocket': {'port': 9900}, 'periodSeconds': 2}}]}
        apply({'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': 'gateway-witness', 'namespace': namespace},
            'spec': {'replicas': 1, 'selector': {'matchLabels': {'app': 'gateway-witness'}},
                     'template': {'metadata': {'labels': {'app': 'gateway-witness'}}, 'spec': pod}}})
        apply({'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': 'gateway-witness', 'namespace': namespace},
               'spec': {'selector': {'app': 'gateway-witness'}, 'ports': [{'port': 9900}]}})
        for name in ('agentgateway', 'gateway-witness'):
            rollout(name)
        stage = 'closed_bootstrap'
        report['bootstrap_closed'] = probe({'mode': 'closed'}).get('bootstrap_closed') is True
        stage = 'jwt_cel'
        print('Recette native JWT/CEL : deux identités et refus croisés.', flush=True)
        key, jwks = signing_material()
        configmap(jwt_qualification_config(), jwks)
        runner.run(['rollout', 'restart', 'deployment/agentgateway', '-n', namespace], timeout=20)
        rollout('agentgateway')
        result = probe({'mode': 'jwt', 'tokens': qualification_tokens(key)})
        report.update(result)
        report['gateway_capabilities'] = build_capability_report(result['checks'], bootstrap_closed=report['bootstrap_closed'])
        report['passed'] = report['bootstrap_closed'] and report['gateway_capabilities']['capabilities']['jwt_cel']['qualified']
    except Exception as error:
        import traceback
        report.update(passed=False, failed_stage=stage, error_type=type(error).__name__,
            error_locations=[{'file': Path(f.filename).name, 'line': f.lineno} for f in traceback.extract_tb(error.__traceback__)])
        print('Qualification interrompue : ' + type(error).__name__, flush=True)
    finally:
        try:
            require_owned_namespace(runner, namespace, nonce)
            runner.run(['delete', 'namespace', namespace, '--wait=true', '--timeout=45s'], timeout=55)
            rc, output, _ = runner.run(['get', 'namespace', namespace, '--ignore-not-found', '-o', 'name'], timeout=20)
            report['cleanup_verified'] = rc == 0 and not output.strip()
        except Exception:
            report['cleanup_verified'] = False
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Qualification limitée : ' + ('réussie' if report['passed'] else 'échec') +
          ' ; activation métier toujours interdite.', flush=True)
    return 0 if report['passed'] and report['cleanup_verified'] else 1


if __name__ == '__main__':
    sys.exit(main())
