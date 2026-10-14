"""Owned identity installation. Invoked only through encrypted engineer I/O."""
import base64
import json
import secrets
import socket
import subprocess
import time
import urllib.request
import urllib.parse
import urllib.error
import http.client
import ssl
import hashlib
import re
from contextlib import contextmanager

NS = 'arcia-identity'


def kube(*args, document=None, timeout=90):
    result = subprocess.run(['/usr/local/bin/k3s', 'kubectl', *args], capture_output=True,
                            input=json.dumps(document).encode() if document is not None else None, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout.decode()


def owned(kind, name, namespace, operation, optional=False):
    args = ['get', kind, name, '--ignore-not-found', '-o', 'json']
    if namespace:
        args += ['-n', namespace]
    raw = kube(*args)
    if not raw and optional:
        return None
    result = json.loads(raw)
    if result['metadata'].get('annotations', {}).get('arcia.io/operation-id') != operation:
        raise ValueError('IDENTITY_FOREIGN_RESOURCE')
    return result


def apply(documents, operation):
    snapshots = []
    standard = []
    for doc in documents:
        previous = owned(doc['kind'], doc['metadata']['name'], doc['metadata'].get('namespace'), operation, True)
        doc['metadata'].setdefault('annotations', {})['arcia.io/operation-id'] = operation
        if (doc['kind'] == 'NetworkPolicy' and doc['metadata'].get('namespace') == NS and
                doc['metadata']['name'] == 'keycloak-microsoft-egress' and
                doc['metadata']['annotations'].get('arcia.io/egress-mode') == 'retired-dns-snapshot'):
            if doc['spec'] != {'podSelector': {'matchLabels': {'app': 'keycloak'}},
                               'policyTypes': ['Egress'], 'egress': []}:
                raise ValueError('IDENTITY_SNAPSHOT_RETIREMENT_SCOPE')
            snapshots.append((doc, previous))
        else:
            standard.append(doc)
    if standard:
        kube('apply', '--server-side', '--field-manager=arcia-foundation', '-f', '-',
             document={'apiVersion': 'v1', 'kind': 'List', 'items': standard})
    # The initial repair used create/replace. Retire it with a resourceVersion
    # precondition rather than forcing SSA ownership of another manager's fields.
    for doc, previous in snapshots:
        replacement = json.loads(json.dumps(doc))
        if previous:
            metadata = previous['metadata']
            replacement['metadata'].update(resourceVersion=metadata['resourceVersion'],
                labels=metadata.get('labels', {}), annotations={**metadata.get('annotations', {}),
                                                               **doc['metadata']['annotations']})
        kube('replace' if previous else 'create', '-f', '-', document=replacement)


@contextmanager
def forward():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    proc = subprocess.Popen(['/usr/local/bin/k3s', 'kubectl', 'port-forward', '-n', NS,
                             'service/keycloak', f'{port}:8080', '--address=127.0.0.1'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise ValueError('IDENTITY_PORT_FORWARD_FAILED')
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=1):
                    break
            except OSError:
                time.sleep(.3)
        else:
            raise ValueError('IDENTITY_PORT_FORWARD_TIMEOUT')
        yield 'http://127.0.0.1:' + str(port) + '/identity'
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


class Admin:
    def __init__(self, base, host):
        self.base, self.host, self.token = base, host, None

    def request(self, method, path, data=None, form=False):
        headers = {'Host': self.host, 'X-Forwarded-Proto': 'https', 'Accept': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        body = None
        if data is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
            body = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=25) as response:
            content = response.read()
            return json.loads(content) if content else None

    def authenticate(self, credentials, bootstrap=False):
        if bootstrap:
            realm = 'master'
            form = {'grant_type': 'password', 'client_id': 'admin-cli',
                    'username': credentials['bootstrap_username'], 'password': credentials['bootstrap_password']}
        else:
            realm = 'arcia'
            form = {'grant_type': 'client_credentials', 'client_id': 'arcia-reconciler',
                    'client_secret': credentials['reconciler_secret']}
        self.token = self.request('POST', f'/realms/{realm}/protocol/openid-connect/token', form, True)['access_token']

    def resource(self, suffix='', method='GET', data=None):
        return self.request(method, '/admin/realms/arcia' + suffix, data)

    def client(self, client_id):
        values = self.resource('/clients?clientId=' + urllib.parse.quote(client_id, safe=''))
        if len(values) != 1:
            raise ValueError('IDENTITY_CLIENT_AMBIGUOUS')
        return values[0]


def ensure_realm(admin, values):
    scope = {}
    exec(values['realm_source'], scope)
    credentials = values['credentials']
    bootstrap = False
    try:
        admin.authenticate(credentials)
    except urllib.error.HTTPError as exc:
        if exc.code not in (400, 401, 404):
            raise
        admin.token = None
        admin.authenticate(credentials, bootstrap=True)
        bootstrap = True
    try:
        realm = admin.resource()
    except urllib.error.HTTPError as exc:
        if exc.code != 404 or not bootstrap:
            raise
        admin.request('POST', '/admin/realms', scope['realm_definition'](values['operation_id']))
        realm = admin.resource()
    if realm.get('attributes', {}).get('arcia.operation-id') != values['operation_id']:
        raise ValueError('IDENTITY_FOREIGN_REALM')
    # Owned realm: preserve IDs, credentials, users, memberships, IdPs and admin changes.
    for role in scope['ROLES']:
        try:
            admin.resource('/roles/' + role)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            admin.resource('/roles', 'POST', {'name': role})
    clients = admin.resource('/clients?clientId=arcia-reconciler')
    if not clients:
        if not bootstrap:
            raise ValueError('IDENTITY_RECONCILER_BOOTSTRAP_REQUIRED')
        admin.resource('/clients', 'POST', {'clientId': 'arcia-reconciler', 'enabled': True,
            'publicClient': False, 'secret': credentials['reconciler_secret'], 'serviceAccountsEnabled': True,
            'standardFlowEnabled': False, 'directAccessGrantsEnabled': False, 'implicitFlowEnabled': False})
    elif len(clients) != 1:
        raise ValueError('IDENTITY_RECONCILER_AMBIGUOUS')
    reconciler = admin.client('arcia-reconciler')
    realm_client = admin.client('realm-management')
    role = admin.resource('/clients/' + realm_client['id'] + '/roles/realm-admin')
    service_user = admin.resource('/clients/' + reconciler['id'] + '/service-account-user')
    admin.resource('/users/' + service_user['id'] + '/role-mappings/clients/' + realm_client['id'], 'POST', [role])
    admin_name = credentials['admin_username']
    users = admin.resource('/users?username=' + urllib.parse.quote(admin_name, safe='') + '&exact=true')
    if not users:
        if bootstrap:
            admin.resource('/users', 'POST', {'username': admin_name, 'enabled': True,
                'credentials': [{'type': 'password', 'value': credentials['admin_password'], 'temporary': True}],
                'requiredActions': ['UPDATE_PASSWORD', 'CONFIGURE_TOTP']})
            users = admin.resource('/users?username=' + urllib.parse.quote(admin_name, safe='') + '&exact=true')
            admin.resource('/users/' + users[0]['id'] + '/role-mappings/clients/' + realm_client['id'], 'POST', [role])
    if len(users) > 1:
        raise ValueError('IDENTITY_ADMIN_AMBIGUOUS')
    # Verify the durable, realm-scoped technical identity before deleting bootstrap access.
    check = Admin(admin.base, admin.host)
    check.authenticate(credentials)
    check.resource()
    if bootstrap:
        initial = admin.request('GET', '/admin/realms/master/users?username=' +
                                urllib.parse.quote(credentials['bootstrap_username'], safe='') + '&exact=true')
        for user in initial:
            admin.request('DELETE', '/admin/realms/master/users/' + user['id'])
    return {'realm_id': realm['id'], 'admin_id': users[0]['id'] if users else None, 'reconciler_id': reconciler['id']}


def inspect(values):
    operation = values['operation_id']
    cluster = owned('Cluster', 'identity-db', NS, operation)
    deployment = owned('Deployment', 'keycloak', NS, operation)
    result={'database_ready': any(c['type'] == 'Ready' and c['status'] == 'True'
                                  for c in cluster.get('status', {}).get('conditions', [])),
            'keycloak_ready': deployment.get('status', {}).get('availableReplicas', 0) == 1,
            'database_instances': cluster['spec']['instances'], 'ha_qualified': False}
    if values.get('action')=='inspect_identity':
        probes=[]
        for ns in ('arcia-hermes','arcia-hermes-qualification-b'):
            pods=json.loads(kube('get','pods','-n',ns,'-l','app=hermes-pilot','-o','json'))['items']
            pod=next(p for p in pods if not p['metadata'].get('deletionTimestamp') and p['status']['phase']=='Running')
            source="""import os,httpx,json,hashlib,pathlib
r={'binding_present':bool(os.environ.get('ARCIA_IDENTITY_ISSUER'))}
r['provider_sha256']=hashlib.sha256(pathlib.Path('/opt/data/plugins/arcia-identity/__init__.py').read_bytes()).hexdigest()
try:
 u=os.environ['ARCIA_IDENTITY_ISSUER'];d=httpx.get(u+'/.well-known/openid-configuration',timeout=10)
 r['discovery_status']=d.status_code
 r['jwks_status']=httpx.get(d.json()['jwks_uri'],timeout=10).status_code
 t=httpx.get(u+'/protocol/openid-connect/userinfo',headers={'Authorization':'Bearer invalid-synthetic'},timeout=10)
 r['userinfo_status']=t.status_code;r['invalid_token_denied']=t.status_code==401
 r['runtime_client_secret_absent']=not bool(os.environ.get('ARCIA_IDENTITY_CLIENT_SECRET'))
except Exception as e:r['probe_exception_type']=type(e).__name__ if type(e).__name__ in ('ConnectError','ConnectTimeout','ReadTimeout','KeyError') else 'OTHER'
print(json.dumps(r))"""
            probes.append(json.loads(kube('exec',pod['metadata']['name'],'-n',ns,'--','/opt/hermes/.venv/bin/python','-c',source)))
            log=kube('logs',pod['metadata']['name'],'-n',ns,'--tail=80')
            probes[-1]['error_codes']=[code for code in ('ARCIA_LOGIN_REFUSED','ARCIA_USER_ROLE_REQUIRED','ARCIA_IDENTITY_UNAVAILABLE',
                'ARCIA_RUNTIME_OWNER_REQUIRED','ARCIA_RUNTIME_CLIENT_REQUIRED','ARCIA_NONCE_MISMATCH','ARCIA_TOKEN_REFUSED','ARCIA_SESSION_INACTIVE') if code in log]
        result['runtime_probes']=probes
        with forward() as base:
            admin=Admin(base,values['hostname']);admin.authenticate(values['credentials'])
            if admin.resource().get('attributes',{}).get('arcia.operation-id')!=operation:
                raise ValueError('IDENTITY_FOREIGN_REALM')
            clients=[];owners={}
            for name,namespace in (('arcia-runtime-a','arcia-hermes'),('arcia-runtime-b','arcia-hermes-qualification-b')):
                client=admin.client(name)
                binding=owned('Secret','arcia-oidc-runtime',namespace,operation)
                subject=base64.b64decode(binding['data']['ARCIA_IDENTITY_OWNER_SUBJECT']).decode()
                owners[name]=subject
                try:
                    user=admin.resource('/users/'+subject)
                    roles=admin.resource('/users/'+subject+'/role-mappings/realm/composite')
                except urllib.error.HTTPError as exc:
                    if exc.code!=404:raise
                    user={};roles=[]
                clients.append({'public_client':client.get('publicClient') is True,
                    'pkce_s256':client.get('attributes',{}).get('pkce.code.challenge.method')=='S256',
                    'standard_flow':client.get('standardFlowEnabled') is True,
                    'password_grant_disabled':client.get('directAccessGrantsEnabled') is False,
                    'owner_exists':bool(user),
                    'owner_enabled':user.get('enabled') is True,
                    'owner_login_unchanged':user.get('username')=='qualification-'+name[-1],
                    'owner_user_role':any(r['name']=='ArcIA.User' for r in roles),
                    'owner_required_actions_pending':bool(user.get('requiredActions'))})
            result['runtime_client_checks']=clients
            result['recent_auth_events']=[]
            allowed_errors={'invalid_code','expired_code','invalid_redirect_uri','invalid_client_credentials',
                'user_disabled','user_not_found','invalid_user_credentials','user_session_not_found',
                'resolve_required_actions','invalid_request','not_allowed','session_expired'}
            for event in admin.resource('/events?max=40'):
                kind=event.get('type')
                if kind not in ('LOGIN','LOGIN_ERROR','CODE_TO_TOKEN','CODE_TO_TOKEN_ERROR','REFRESH_TOKEN_ERROR'):continue
                client=event.get('clientId')
                client=client if client in ('arcia-runtime-a','arcia-runtime-b','security-admin-console') else 'other'
                error=event.get('error')
                result['recent_auth_events'].append({'type':kind,'client':client,
                    'runtime_owner_matches':event.get('userId')==owners[client] if client in owners else None,
                    'error':error if error in allowed_errors else ('other' if error else None)})
    return result


def personal_cleanup(values):
    operation = values['operation_id']
    owned('Deployment', 'keycloak', NS, operation)
    scope = {}
    exec(values['cleanup_source'], scope)
    with forward() as base:
        admin = Admin(base, values['hostname'])
        admin.authenticate(values['credentials'])
        if values['action'] == 'plan_personal_cleanup':
            return {'plan': scope['plan'](admin, owned, kube, operation)}
        return scope['apply'](admin, owned, kube, operation, values['cleanup_plan'],
                              values['authorized_plan_sha256'], values['approval_mode'])


def plan_microsoft_egress(values):
    # Planning never applies. Administrative repair has a separate entry point.
    operation = values['operation_id']
    deployment = owned('Deployment', 'keycloak', NS, operation)
    previous = owned('NetworkPolicy', 'keycloak-microsoft-egress', NS, operation, True)
    scope = {}
    exec(values['egress_source'], scope)
    addresses = scope['merge_resolutions'](values.get('resolutions', []) + [scope['resolve']()])
    return {'plan': scope['plan'](addresses, operation, deployment, previous),
            'address_count': len({ip for items in addresses.values() for ip in items})}


def identity_access_repair(values):
    operation = values['operation_id']
    owned('Deployment', 'keycloak', NS, operation)
    scope = {}
    exec(values['access_source'], scope)
    with forward() as base:
        admin = Admin(base, values['hostname'])
        admin.authenticate(values['credentials'])
        if values['action'] == 'inspect_identity_access_policy':
            policy = values['policy']
            return scope['tenant_mapper'](admin, operation, policy['provider_alias'], policy['tenant_id'])
        if values['action'] == 'plan_identity_access_repair':
            providers = [p for p in admin.resource('/identity-provider/instances')
                         if p.get('providerId') == 'microsoft' and p.get('enabled')]
            if len(providers) != 1:
                raise ValueError('IDENTITY_ACCESS_PROVIDER_AMBIGUOUS')
            provider = providers[0]
            plan = scope['repair_plan'](admin, operation, values['recovery_username'],
                                       provider['alias'], provider.get('config', {}).get('tenantId'))
            return {'plan': plan}
        if values['action'] != 'apply_identity_access_repair':
            raise ValueError('IDENTITY_ACCESS_UNKNOWN_ACTION')
        result = scope['apply_repair'](admin, operation, values['repair_plan'], values['authorized_plan_sha256'])
        plan = values['repair_plan']
        result['policy'] = {'operation_id': operation, 'provider_alias': plan['provider_alias'],
                            'tenant_id': plan['tenant_id'], 'assigned_role': 'ArcIA.User',
                            'mapper_type': scope['MAPPER_TYPE'], 'mapper_sync_mode': 'FORCE'}
        return result


def resolve_microsoft_egress(values):
    scope = {}
    exec(values['egress_source'], scope)
    return {'resolutions': [scope['resolve']() for _ in range(3)]}


def inspect_microsoft_egress(values):
    operation = values['operation_id']
    owned('Deployment', 'keycloak', NS, operation)
    public = owned('NetworkPolicy', 'keycloak-public-https-egress', NS, operation, True)
    if public:
        scope = {}
        exec(values['egress_source'], scope)
        expected = scope['public_https_policy'](values['network'], operation)
        snapshot = owned('NetworkPolicy', 'keycloak-microsoft-egress', NS, operation, True)
        # The API omits empty lists in its readback representation.
        snapshot_retired = not snapshot or {**snapshot['spec'], 'egress': snapshot['spec'].get('egress', [])} == scope['retired_snapshot_policy']()['spec']
        return {'configured': True, 'bounded_rule': public['spec'] == expected['spec'] and
                    values.get('https_egress_mode') == 'public_ipv4_443' and snapshot_retired,
                'snapshot_retired': snapshot_retired,
                'current_dns_covered': True, 'mode': 'public_ipv4_443',
                'destination_control': 'upstream_firewall', 'resources_modified': False}
    existing = owned('NetworkPolicy', 'keycloak-microsoft-egress', NS, operation, True)
    if not existing:
        return {'configured': False, 'current_dns_covered': None, 'resources_modified': False}
    scope = {}
    exec(values['egress_source'], scope)
    addresses = scope['resolve']()
    spec = existing['spec']
    rule = spec.get('egress', [{}])[0]
    expected_addresses = {ip for items in addresses.values() for ip in items}
    destinations = rule.get('to', [])
    permitted = set()
    bounded = bool(destinations) and len(destinations) <= 128
    for destination in destinations:
        block = destination.get('ipBlock', {})
        try:
            network = __import__('ipaddress').ip_network(block['cidr'])
            address = network.network_address
            bounded = bounded and set(destination) == {'ipBlock'} and set(block) == {'cidr'}
            bounded = bounded and network.prefixlen == 32 and address.is_global and not address.is_multicast
            permitted.add(str(address))
        except (KeyError, ValueError):
            bounded = False
    bounded = bool(bounded and spec.get('podSelector') == {'matchLabels': {'app': 'keycloak'}} and
                   spec.get('policyTypes') == ['Egress'] and len(spec.get('egress', [])) == 1 and
                   rule.get('ports') == [{'port': 443, 'protocol': 'TCP'}])
    return {'configured': True, 'bounded_rule': bounded,
            'current_dns_covered': expected_addresses <= permitted,
            'address_count': len(permitted), 'missing_address_count': len(expected_addresses - permitted),
            'resources_modified': False}


def install_public_https_egress(values):
    operation = values['operation_id']
    owned('Deployment', 'keycloak', NS, operation)
    if values.get('https_egress_mode') != 'public_ipv4_443':
        raise ValueError('IDENTITY_PUBLIC_HTTPS_EXPLICIT_CONFIGURATION_REQUIRED')
    scope = {}
    exec(values['egress_source'], scope)
    public = scope['public_https_policy'](values['network'], operation)
    # Both resources are checked before the first mutation.
    owned('NetworkPolicy', public['metadata']['name'], NS, operation, True)
    owned('NetworkPolicy', 'keycloak-microsoft-egress', NS, operation, True)
    apply([public, scope['retired_snapshot_policy']()], operation)
    installed = owned('NetworkPolicy', public['metadata']['name'], NS, operation)
    retired = owned('NetworkPolicy', 'keycloak-microsoft-egress', NS, operation)
    if installed['spec'] != public['spec'] or retired['spec'].get('egress', []):
        raise ValueError('IDENTITY_PUBLIC_HTTPS_READBACK_FAILED')
    return {'public_https_egress_configured': True, 'target': 'keycloak_only',
            'port': 443, 'protocol': 'TCP', 'destination_control': 'upstream_firewall',
            'snapshot_retired': True, 'keycloak_rollout_triggered': False,
            'credentials_modified': False, 'volumes_modified': False}


def apply_microsoft_egress_repair(values):
    # Explicit operator exception for this named repair. This is NOT Teams approval.
    plan = values['repair_plan']
    if (values.get('approval_mode') != 'operator_exception_for_named_repair' or
            not values.get('authorized_plan_sha256') or
            values['authorized_plan_sha256'] != plan.get('plan_sha256')):
        raise ValueError('IDENTITY_EGRESS_EXPLICIT_EXCEPTION_REQUIRED')
    operation = values['operation_id']
    deployment = owned('Deployment', 'keycloak', NS, operation)
    previous = owned('NetworkPolicy', 'keycloak-microsoft-egress', NS, operation, True)
    scope = {}
    exec(values['egress_source'], scope)
    scope['validate_plan'](plan, operation, deployment, previous)
    current = scope['resolve']()
    if any(not set(current[host]) <= set(plan['addresses'][host]) for host in current):
        raise ValueError('IDENTITY_EGRESS_DNS_CHANGED_REPLAN_REQUIRED')
    document = json.loads(json.dumps(plan['document']))
    if previous:
        document['metadata']['resourceVersion'] = previous['metadata']['resourceVersion']
    # create/replace uses existence/resourceVersion preconditions, no forced adoption.
    kube('replace' if previous else 'create', '-f', '-', document=document)
    installed = owned('NetworkPolicy', 'keycloak-microsoft-egress', NS, operation)
    if installed['spec'] != document['spec']:
        raise ValueError('IDENTITY_EGRESS_REPAIR_READBACK_FAILED')
    return {'installed': True, 'policy_uid': installed['metadata']['uid'],
            'plan_sha256': plan['plan_sha256'], 'approval_mode': values['approval_mode'],
            'teams_approval_verified': False, 'keycloak_rollout_triggered': False,
            'credentials_modified': False, 'volumes_modified': False,
            'address_count': len(document['spec']['egress'][0]['to'])}


def install(values):
    operation = values['operation_id']
    previous = owned('Secret', 'identity-db-auth', NS, operation, True)
    if previous and base64.b64decode(previous['data']['password']).decode() != values['credentials']['db_password']:
        raise ValueError('IDENTITY_DATABASE_CREDENTIAL_DRIFT')
    documents = values['documents']
    existing = owned('Deployment', 'keycloak', NS, operation, True)
    if existing and not any(e['name'].startswith('KC_BOOTSTRAP_ADMIN_')
                            for e in existing['spec']['template']['spec']['containers'][0]['env']):
        remove_bootstrap(documents)
    apply([d for d in documents if d['kind'] != 'Deployment'], operation)
    kube('wait', 'cluster/identity-db', '-n', NS, '--for=condition=Ready', '--timeout=480s', timeout=500)
    apply([d for d in documents if d['kind'] == 'Deployment'], operation)
    kube('rollout', 'status', 'deployment/keycloak', '-n', NS, '--timeout=600s', timeout=620)
    with forward() as base:
        ids = ensure_realm(Admin(base, values['hostname']), values)
    remove_bootstrap(documents)
    apply([d for d in documents if d['kind'] == 'Deployment'], operation)
    kube('rollout', 'status', 'deployment/keycloak', '-n', NS, '--timeout=600s', timeout=620)
    apply(values['ingress'], operation)
    kube('rollout', 'status', 'daemonset/pilot-https', '-n', 'arcia-ingress', '--timeout=180s', timeout=200)
    result = inspect(values)
    result.update(ids)
    result['passed'] = result['database_ready'] and result['keycloak_ready']
    return result


def remove_bootstrap(documents):
    for doc in documents:
        if doc['kind'] == 'Deployment':
            container = doc['spec']['template']['spec']['containers'][0]
            container['env'] = [e for e in container['env'] if not e['name'].startswith('KC_BOOTSTRAP_ADMIN_')]


def verify(values):
    operation = values['operation_id']
    result = inspect(values)
    with forward() as base:
        admin = Admin(base, values['hostname'])
        admin.authenticate(values['credentials'])
        realm = admin.resource()
        checks = {'owned_realm': realm.get('attributes', {}).get('arcia.operation-id') == operation,
                  'self_registration_disabled': realm['registrationAllowed'] is False,
                  'brute_force_enabled': realm['bruteForceProtected'] is True,
                  'admin_event_bodies_disabled': realm['adminEventsDetailsEnabled'] is False,
                  'local_realm_enabled': realm['enabled'] is True}
        name = 'arcia-synthetic-' + secrets.token_hex(8)
        user_id = None
        try:
            admin.resource('/users', 'POST', {'username': name, 'enabled': True,
                'credentials': [{'type': 'password', 'value': secrets.token_urlsafe(24), 'temporary': True}]})
            users = admin.resource('/users?username=' + name + '&exact=true')
            user_id = users[0]['id']
            checks['admin_create_user'] = len(users) == 1 and users[0]['enabled']
            admin.resource('/users/' + user_id, 'PUT', {'enabled': False})
            checks['admin_disable_user'] = admin.resource('/users/' + user_id)['enabled'] is False
            role = admin.resource('/roles/ArcIA.User')
            admin.resource('/users/' + user_id + '/role-mappings/realm', 'POST', [role])
            checks['admin_assign_role'] = any(r['name'] == 'ArcIA.User'
                for r in admin.resource('/users/' + user_id + '/role-mappings/realm'))
            admin.resource('/users/' + user_id + '/reset-password', 'PUT', {
                'type': 'password', 'value': secrets.token_urlsafe(24), 'temporary': True})
            checks['admin_password_reset'] = 'UPDATE_PASSWORD' in admin.resource('/users/' + user_id)['requiredActions']
            admin.resource('/users/' + user_id + '/logout', 'POST')
            checks['admin_revoke_sessions'] = admin.resource('/users/' + user_id + '/sessions') == []
        finally:
            if user_id:
                admin.resource('/users/' + user_id, 'DELETE')
        checks['admin_delete_user'] = admin.resource('/users?username=' + name + '&exact=true') == []
        discovery = admin.request('GET', '/realms/arcia/.well-known/openid-configuration')
        checks['issuer_https_exact'] = discovery['issuer'] == 'https://' + values['hostname'] + '/identity/realms/arcia'
        checks['oidc_pkce_available'] = 'S256' in discovery.get('code_challenge_methods_supported', [])
    checks.update({k: v for k, v in result.items() if k in ('database_ready', 'keycloak_ready')})
    return {'passed': all(checks.values()), 'checks': checks, 'ha_qualified': False,
            'sso_provider_enabled': False, 'hermes_oidc_qualified': False}


def clean(doc):
    doc.pop('status',None)
    doc['metadata']={k:doc['metadata'][k] for k in ('name','namespace','annotations') if k in doc['metadata']}
    return doc


def prepare(values):
    runtimes=[]
    for ns in ('arcia-hermes','arcia-hermes-qualification-b'):
        runtimes.append([clean(owned('Deployment','hermes-pilot',ns,values['operation_id'])),
                         clean(owned('ConfigMap','hermes-pilot-config',ns,values['operation_id']))])
    return {'runtimes':runtimes}


def connect(values):
    operation=values['operation_id'];scope={};exec(values['realm_source'],scope)
    # Validate all current targets before adding bindings or changing authentication.
    for docs in values['prepared']['runtimes']:
        for old in docs:
            current=owned(old['kind'],old['metadata']['name'],old['metadata']['namespace'],operation)
            if current.get('spec',current.get('data'))!=old.get('spec',old.get('data')):
                raise ValueError('IDENTITY_RUNTIME_CONFIG_DRIFT')
    with forward() as base:
        admin=Admin(base,values['hostname']);admin.authenticate(values['credentials'])
        realm=admin.resource()
        if realm.get('attributes',{}).get('arcia.operation-id')!=operation:raise ValueError('IDENTITY_FOREIGN_REALM')
        profile=admin.resource('/users/profile')
        marker='arcia.qualification-owner'
        if not any(a['name']==marker for a in profile.get('attributes',[])):
            profile.setdefault('attributes',[]).append({'name':marker,'displayName':'ArcIA qualification owner',
                'permissions':{'view':['admin'],'edit':['admin']},'multivalued':False,
                'validations':{'length':{'min':36,'max':36}}})
            admin.resource('/users/profile','PUT',profile)
        for ns,name,pilot,prefix in [('arcia-hermes','qualification-a',values['pilot'],''),
                                    ('arcia-hermes-qualification-b','qualification-b',values['second_pilot'],'/qualification-b')]:
            binding=owned('Secret','arcia-oidc-runtime',ns,operation,True)
            users=admin.resource('/users?username='+name+'&exact=true')
            if not users:
                if binding:raise ValueError('IDENTITY_BOUND_USER_REMOVED')
                admin.resource('/users','POST',{'username':name,'enabled':True,
                    'firstName':'Synthetic','lastName':'Qualification '+name[-1].upper(),
                    'email':name+'@example.invalid','emailVerified':True,
                    'attributes':{'arcia.qualification-owner':[operation]},
                    'credentials':[{'type':'password','value':pilot['password'],'temporary':False}]})
                users=admin.resource('/users?username='+name+'&exact=true')
                role=admin.resource('/roles/ArcIA.User')
                admin.resource('/users/'+users[0]['id']+'/role-mappings/realm','POST',[role])
            if len(users)==1:users=[admin.resource('/users/'+users[0]['id'])]
            if len(users)!=1 or users[0].get('attributes',{}).get('arcia.qualification-owner')!=[operation]:
                raise ValueError('IDENTITY_FOREIGN_RUNTIME_USER')
            missing={k:v for k,v in {'firstName':'Synthetic','lastName':'Qualification '+name[-1].upper(),
                                    'email':name+'@example.invalid'}.items() if not users[0].get(k)}
            if missing:admin.resource('/users/'+users[0]['id'],'PUT',missing)
            subject=users[0]['id'];client_id='arcia-runtime-'+name[-1]
            if binding and base64.b64decode(binding['data']['ARCIA_IDENTITY_OWNER_SUBJECT']).decode()!=subject:
                raise ValueError('IDENTITY_SUBJECT_REBIND_REFUSED')
            clients=admin.resource('/clients?clientId='+client_id)
            if not clients:
                admin.resource('/clients','POST',scope['runtime_client'](client_id,
                    'https://'+values['hostname']+prefix+'/auth/callback',secrets.token_urlsafe(32)))
            client=admin.client(client_id)
            if client['redirectUris']!=['https://'+values['hostname']+prefix+'/auth/callback']:
                raise ValueError('IDENTITY_RUNTIME_CLIENT_DRIFT')
            if client.get('publicClient') is not True:
                admin.resource('/clients/'+client['id'],'PUT',{'publicClient':True})
            data={'ARCIA_IDENTITY_ISSUER':'https://'+values['hostname']+'/identity/realms/arcia',
                  'ARCIA_IDENTITY_CLIENT_ID':client_id,
                  'ARCIA_IDENTITY_OWNER_SUBJECT':subject}
            if binding and {k:base64.b64decode(v).decode() for k,v in binding['data'].items() if k!='ARCIA_IDENTITY_CLIENT_SECRET'}!=data:
                raise ValueError('IDENTITY_CLIENT_SECRET_DRIFT')
            apply([{'apiVersion':'v1','kind':'Secret','metadata':{'name':'arcia-oidc-runtime','namespace':ns},
                    'type':'Opaque','stringData':data}],operation)
    dns=owned('ConfigMap','private-dns-records','arcia-privacy',operation)
    records=json.loads(dns['data']['records.json']);old=records.get(values['hostname'])
    if old and old!=values['https_ip']:raise ValueError('IDENTITY_DNS_CONFLICT')
    records[values['hostname']]=values['https_ip'];dns=clean(dns);dns['data']['records.json']=json.dumps(records)
    apply([dns],operation)
    kube('rollout','restart','deployment/private-dns','-n','arcia-privacy')
    kube('rollout','status','deployment/private-dns','-n','arcia-privacy','--timeout=120s',timeout=140)
    # These two resources have historical merge-patch managers. Use an optimistic
    # merge patch on the owned snapshot, rather than forcing SSA ownership conflicts.
    updates=values['runtime_updates']
    apply([d for d in updates if not (d['kind']=='Deployment' or
          (d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config'))],operation)
    for doc in updates:
        if doc['kind']=='Deployment' or (doc['kind']=='ConfigMap' and doc['metadata']['name']=='hermes-pilot-config'):
            ns=doc['metadata']['namespace'];name=doc['metadata']['name']
            current=owned(doc['kind'],name,ns,operation)
            original=next(d for group in values['prepared']['runtimes'] for d in group
                          if d['kind']==doc['kind'] and d['metadata']['namespace']==ns)
            key='spec' if doc['kind']=='Deployment' else 'data'
            if current[key]!=original[key]:raise ValueError('IDENTITY_RUNTIME_CONFIG_DRIFT')
            patch={'metadata':{'resourceVersion':current['metadata']['resourceVersion']},key:doc[key]}
            kube('patch',doc['kind'],name,'-n',ns,'--type=merge','--field-manager=arcia-foundation','-p',json.dumps(patch))
    for ns in ('arcia-hermes','arcia-hermes-qualification-b'):
        kube('rollout','status','deployment/hermes-pilot','-n',ns,'--timeout=300s',timeout=320)
    return {'passed':True,'runtime_count':2,'legacy_password_provider_disabled':True,
            'hermes_oidc_qualified':False}


def cleanup_unbound_fixture(values):
    """Explicit repair of this lot's never-bound fixture after profile validation failure."""
    operation=values['operation_id']
    if owned('Secret','arcia-oidc-runtime','arcia-hermes',operation,True):
        raise ValueError('IDENTITY_BOUND_FIXTURE_CLEANUP_REFUSED')
    with forward() as base:
        admin=Admin(base,values['hostname']);admin.authenticate(values['credentials'])
        if admin.resource().get('attributes',{}).get('arcia.operation-id')!=operation:
            raise ValueError('IDENTITY_FOREIGN_REALM')
        users=admin.resource('/users?username=qualification-a&exact=true')
        if len(users)!=1:raise ValueError('IDENTITY_FIXTURE_CLEANUP_SCOPE')
        user=admin.resource('/users/'+users[0]['id'])
        if (user.get('attributes') or user.get('email') or user.get('firstName') or
            time.time()*1000-user['createdTimestamp']>1800000 or
            admin.resource('/clients?clientId=arcia-runtime-a') or
            admin.resource('/users/'+user['id']+'/federated-identity')):
            raise ValueError('IDENTITY_FIXTURE_CLEANUP_REFUSED')
        admin.resource('/users/'+user['id'],'DELETE')
    return {'passed':True,'unbound_fixture_removed':True}


def qualify_revocation(values):
    """Only our designated synthetic owner; always restore its enabled state."""
    ns='arcia-hermes' if values['who']=='A' else 'arcia-hermes-qualification-b'
    binding=owned('Secret','arcia-oidc-runtime',ns,values['operation_id'])
    subject=base64.b64decode(binding['data']['ARCIA_IDENTITY_OWNER_SUBJECT']).decode()
    with forward() as base:
        admin=Admin(base,values['hostname']);admin.authenticate(values['credentials'])
        user=admin.resource('/users/'+subject)
        if (user.get('attributes',{}).get('arcia.qualification-owner')!=[values['operation_id']]
            or user['enabled'] is not True):raise ValueError('IDENTITY_REVOCATION_FIXTURE_SCOPE')
        try:
            admin.resource('/users/'+subject,'PUT',{'enabled':False})
            context=ssl.create_default_context(cadata=values['pilot']['tls_certificate'])
            connection=http.client.HTTPSConnection(values['hostname'],context=context,timeout=20)
            connection._create_connection=lambda dest,timeout,source_address=None:socket.create_connection((values['https_ip'],443),timeout)
            path=('/qualification-b' if values['who']=='B' else '')+'/api/config'
            connection.request('GET',path,headers={'Cookie':values['session_cookie'],'Origin':'https://'+values['hostname']})
            response=connection.getresponse();response.read();status=response.status;connection.close()
            admin.resource('/users/'+subject+'/logout','POST')
        finally:
            admin.resource('/users/'+subject,'PUT',{'enabled':True})
    return {'passed':status in (401,403),'disabled_session_refused':status in (401,403)}


def prepare_personal_portal(values):
    operation=values['operation_id']
    dns=owned('Service','private-dns','arcia-privacy',operation)['spec']['clusterIP']
    return {'dns_ip':dns}


def reconcile_runtime_network(values):
    """Only the fixed identity policies; no restart, credential or volume mutation."""
    operation=values['operation_id']
    settings=json.loads(owned('ConfigMap','portal-config','arcia-access',operation)['data']['portal.json'])
    namespaces={'arcia-hermes','arcia-hermes-qualification-b'}|{s['namespace'] for s in settings['slots']}
    documents=values['documents']
    if {d['metadata']['namespace'] for d in documents}!=namespaces or len(documents)!=len(namespaces):
        raise ValueError('IDENTITY_RUNTIME_NETWORK_POOL_DRIFT')
    for doc in documents:
        ns=doc['metadata']['namespace']
        if ns not in ('arcia-hermes','arcia-hermes-qualification-b') and not re.fullmatch(r'arcia-user-p(?:0[1-9]|[12][0-9]|3[0-2])',ns):
            raise ValueError('IDENTITY_RUNTIME_NETWORK_SCOPE')
        owned('Deployment','hermes-pilot',ns,operation)
        owned('NetworkPolicy','identity-https-egress',ns,operation)
        if (doc['kind']!='NetworkPolicy' or doc['metadata']['name']!='identity-https-egress' or
                doc['spec']['podSelector']!={'matchLabels':{'app':'hermes-pilot'}}):
            raise ValueError('IDENTITY_RUNTIME_NETWORK_SCOPE')
    apply(documents,operation)
    return {'passed':all(owned('NetworkPolicy',d['metadata']['name'],d['metadata']['namespace'],operation)['spec']==d['spec'] for d in documents),
            'policies_rechecked':len(documents),'runtime_restart_triggered':False,
            'credentials_modified':False,'volumes_modified':False}


def runtime_oidc_probe(namespace, pod):
    source="""import os,json,httpx
r={}
try:
 u=os.environ['ARCIA_IDENTITY_ISSUER'];d=httpx.get(u+'/.well-known/openid-configuration',timeout=8,follow_redirects=False)
 r['discovery_status']=d.status_code;r['issuer_exact']=d.json().get('issuer')==u
 r['jwks_status']=httpx.get(d.json()['jwks_uri'],timeout=8,follow_redirects=False).status_code
 d=httpx.get('http://127.0.0.1:9119/auth/login?provider=arcia',timeout=12,follow_redirects=False)
 r['login_start_status']=d.status_code
except Exception as e:r['exception_type']=type(e).__name__ if type(e).__name__ in ('ConnectError','ConnectTimeout','ReadTimeout','KeyError','ValueError') else 'OTHER'
r['passed']=r.get('discovery_status')==200 and r.get('issuer_exact') is True and r.get('jwks_status')==200 and r.get('login_start_status')==302
print(json.dumps(r))"""
    return json.loads(kube('exec',pod['metadata']['name'],'-n',namespace,'--','/opt/hermes/.venv/bin/python','-c',source,timeout=60))


def inspect_personal_portal(values):
    config=owned('ConfigMap','portal-config','arcia-access',values['operation_id'])
    settings=json.loads(config['data']['portal.json']);slots=[]
    for slot in settings['slots']:
        binding=owned('ConfigMap','slot-binding',slot['namespace'],values['operation_id'])
        job=owned('Job',slot['job'],slot['namespace'],values['operation_id'])
        record={'assigned':bool(json.loads(binding['data']['binding.json'])),'installer_failed':bool(job.get('status',{}).get('failed')),
            'installer_completed':bool(job.get('status',{}).get('succeeded')),'installer_suspended':job['spec'].get('suspend',False)}
        pods=json.loads(kube('get','pods','-n',slot['namespace'],'-o','json'))['items']
        record['containers']=[]
        for pod in pods:
            if (pod['metadata'].get('labels',{}).get('app')=='hermes-pilot' and
                    pod.get('status',{}).get('phase')=='Running' and not pod['metadata'].get('deletionTimestamp')):
                record['oidc_probe']=runtime_oidc_probe(slot['namespace'],pod)
            for status in pod.get('status',{}).get('containerStatuses',[]):
                state=status.get('state',{});reason=next((s.get('reason') for s in state.values()),None)
                record['containers'].append({'ready':status.get('ready'),
                    'reason':reason if reason in ('Completed','Error','OOMKilled','ContainerCreating','CrashLoopBackOff','ErrImagePull','ImagePullBackOff','CreateContainerConfigError','PodInitializing') else None})
            if pod['metadata'].get('labels',{}).get('app')=='hermes-tools-installer':
                try:log=kube('logs',pod['metadata']['name'],'-n',slot['namespace'],'--tail=60')
                except Exception:log=''
                record['installer_error_codes']=sorted(set(re.findall(r'\b(?:HERMES|SKILLS|RTK|NPM|PIP|ARCHIVE)_[A-Z0-9_]{3,60}\b',log)))
                record['installer_exception_types']=sorted(set(re.findall(r'\b([A-Za-z]+(?:Error|Exception)):',log)))
                record['disk_full']='No space left on device' in log
        slots.append(record)
    portal=owned('Deployment','arcia-portal','arcia-access',values['operation_id'])
    logs=kube('logs','deployment/arcia-portal','-n','arcia-access','--tail=40')
    return {'passed':portal.get('status',{}).get('availableReplicas',0)==1 and
            all(s.get('oidc_probe',{}).get('passed',True) for s in slots),'slots':slots,
        'portal_error_codes':sorted(set(re.findall(r'\bARCIA_PORTAL_[A-Z0-9_]{3,80}\b',logs)))}


def prepare_portal_fixtures(values):
    fixtures=[]
    with forward() as base:
        admin=Admin(base,values['hostname']);admin.authenticate(values['credentials'])
        if admin.resource().get('attributes',{}).get('arcia.operation-id')!=values['operation_id']:raise ValueError('IDENTITY_FOREIGN_REALM')
        for fixture in values['fixtures']:
            name=fixture['username'];users=admin.resource('/users?username='+urllib.parse.quote(name,safe='')+'&exact=true')
            if not users:
                if fixture.get('subject'):raise ValueError('PERSONAL_PORTAL_FIXTURE_REMOVED')
                admin.resource('/users','POST',{'username':name,'enabled':True,'firstName':'Synthetic','lastName':'Portal validation',
                    'email':name+'@example.invalid','emailVerified':True,'attributes':{'arcia.qualification-owner':[values['operation_id']]},
                    'credentials':[{'type':'password','value':fixture['password'],'temporary':False}]})
                users=admin.resource('/users?username='+urllib.parse.quote(name,safe='')+'&exact=true')
                role=admin.resource('/roles/ArcIA.User')
                admin.resource('/users/'+users[0]['id']+'/role-mappings/realm','POST',[role])
            if len(users)!=1:raise ValueError('PERSONAL_PORTAL_FIXTURE_AMBIGUOUS')
            user=admin.resource('/users/'+users[0]['id'])
            if user.get('attributes',{}).get('arcia.qualification-owner')!=[values['operation_id']]:raise ValueError('PERSONAL_PORTAL_FOREIGN_FIXTURE')
            if fixture.get('subject') and fixture['subject']!=user['id']:raise ValueError('PERSONAL_PORTAL_FIXTURE_REBIND_REFUSED')
            if not user['enabled']:admin.resource('/users/'+user['id'],'PUT',{'enabled':True})
            fixtures.append({**fixture,'subject':user['id']})
    return {'fixtures':fixtures}


def finish_portal_qualification(values):
    checks={};volumes=[]
    with forward() as base:
        admin=Admin(base,values['hostname']);admin.authenticate(values['credentials'])
        if admin.resource().get('attributes',{}).get('arcia.operation-id')!=values['operation_id']:raise ValueError('IDENTITY_FOREIGN_REALM')
        for item in values['sessions']:
            ns=item['namespace'];subject=item['subject']
            user=admin.resource('/users/'+subject)
            if user.get('attributes',{}).get('arcia.qualification-owner')!=[values['operation_id']]:raise ValueError('PERSONAL_PORTAL_FOREIGN_FIXTURE')
            binding=owned('Secret','arcia-oidc-runtime',ns,values['operation_id'])
            if base64.b64decode(binding['data']['ARCIA_IDENTITY_OWNER_SUBJECT']).decode()!=subject:raise ValueError('PERSONAL_PORTAL_SUBJECT_MISMATCH')
            deployment=owned('Deployment','hermes-pilot',ns,values['operation_id'])
            checks[ns+'_single_owner']=deployment['spec']['replicas']==1 and deployment['spec']['strategy']['type']=='Recreate'
            checks[ns+'_agent_has_no_service_account']=deployment['spec']['template']['spec']['automountServiceAccountToken'] is False
            for name in ('hermes-pilot-state','hermes-tools'):
                pvc=owned('PersistentVolumeClaim',name,ns,values['operation_id'])
                volumes.append(pvc['spec']['volumeName']);checks[ns+'_'+name+'_rwop']=pvc['spec']['accessModes']==['ReadWriteOncePod']
            admin.resource('/users/'+subject,'PUT',{'enabled':False})
            admin.resource('/users/'+subject+'/logout','POST')
            context=ssl.create_default_context(cadata=values['pilot']['tls_certificate'])
            connection=http.client.HTTPSConnection(values['hostname'],context=context,timeout=20)
            connection._create_connection=lambda dest,timeout,source_address=None:socket.create_connection((values['https_ip'],443),timeout)
            connection.request('GET',item['prefix']+'/api/config',headers={'Cookie':item['cookie'],'Origin':'https://'+values['hostname']})
            response=connection.getresponse();response.read();checks[ns+'_disabled_session_denied']=response.status==401;connection.close()
    checks['distinct_state_and_tools_volumes']=len(volumes)==len(set(volumes))==4
    portal=owned('Deployment','arcia-portal','arcia-access',values['operation_id'])
    checks['single_active_portal']=portal['spec']['replicas']==1 and portal['spec']['strategy']['type']=='Recreate'
    checks['no_cluster_role_bound']=not any(b.get('roleRef',{}).get('kind')=='ClusterRole' for slot in values['sessions']
        for b in json.loads(kube('get','rolebindings','-n',slot['namespace'],'-o','json'))['items'])
    return {'checks':checks,'passed':all(checks.values()),'fixture_accounts_disabled':True}


def disable_portal_fixtures(values):
    with forward() as base:
        admin=Admin(base,values['hostname']);admin.authenticate(values['credentials'])
        if admin.resource().get('attributes',{}).get('arcia.operation-id')!=values['operation_id']:raise ValueError('IDENTITY_FOREIGN_REALM')
        for fixture in values['fixtures']:
            try:user=admin.resource('/users/'+fixture['subject'])
            except urllib.error.HTTPError as exc:
                if exc.code==404:continue
                raise
            if user.get('attributes',{}).get('arcia.qualification-owner')!=[values['operation_id']]:raise ValueError('PERSONAL_PORTAL_FOREIGN_FIXTURE')
            admin.resource('/users/'+user['id'],'PUT',{'enabled':False})
            admin.resource('/users/'+user['id']+'/logout','POST')
    return {'disabled':True}


def install_personal_portal(values):
    operation=values['operation_id'];documents=values['documents'];scope={};exec(values['realm_source'],scope)
    existing_pool=json.loads(kube('get','namespaces','-l','arcia.io/personal-pool=true','-o','json'))['items']
    desired={slot['namespace'] for slot in values['slots']}
    if any(ns['metadata']['name'] not in desired for ns in existing_pool):
        raise ValueError('PERSONAL_CAPACITY_SHRINK_REQUIRES_MIGRATION')
    portal=owned('Deployment','arcia-portal','arcia-access',operation,True)
    if portal:
        # Stop allocation while taking/reapplying the pool snapshot. Existing
        # personal runtimes keep serving their independently authenticated users.
        kube('scale','deployment/arcia-portal','-n','arcia-access','--replicas=0')
        kube('wait','pods','-l','app=arcia-portal','-n','arcia-access','--for=delete','--timeout=90s',timeout=100)
    # Explicit removal of an obsolete confidential-client field. SSA stringData
    # alone cannot remove a previously managed Secret.data key.
    for ns in ('arcia-hermes','arcia-hermes-qualification-b'):
        binding=owned('Secret','arcia-oidc-runtime',ns,operation,True)
        if binding and 'ARCIA_IDENTITY_CLIENT_SECRET' in binding.get('data',{}):
            kube('patch','secret','arcia-oidc-runtime','-n',ns,'--type=merge','-p',json.dumps({
                'metadata':{'resourceVersion':binding['metadata']['resourceVersion']},
                'data':{'ARCIA_IDENTITY_CLIENT_SECRET':None}}))
            kube('rollout','restart','deployment/hermes-pilot','-n',ns)
            kube('rollout','status','deployment/hermes-pilot','-n',ns,'--timeout=300s',timeout=320)
    with forward() as base:
        admin=Admin(base,values['hostname']);admin.authenticate(values['credentials'])
        if admin.resource().get('attributes',{}).get('arcia.operation-id')!=operation:raise ValueError('IDENTITY_FOREIGN_REALM')
        for client_id,callback in [('arcia-portal','/portal/callback')]+[
            ('arcia-'+slot['id'],slot['prefix']+'/auth/callback') for slot in values['slots']]:
            expected=scope['runtime_client'](client_id,'https://'+values['hostname']+callback,None)
            matches=admin.resource('/clients?clientId='+client_id)
            if not matches:admin.resource('/clients','POST',expected)
            else:
                client=admin.client(client_id)
                if (client.get('redirectUris')!=expected['redirectUris'] or client.get('publicClient') is not True
                    or client.get('attributes',{}).get('pkce.code.challenge.method')!='S256'):
                    raise ValueError('PERSONAL_PORTAL_CLIENT_DRIFT')
    # Preserve existing bindings, volumes, credentials, scales and install progress.
    preserved_bindings={};preserved_claims={};skip=set()
    for slot in values['slots']:
        ns=slot['namespace'];binding=owned('ConfigMap','slot-binding',ns,operation,True)
        previous_pvc=owned('PersistentVolumeClaim','hermes-pilot-state',ns,operation,True)
        if previous_pvc and not binding:raise ValueError('PERSONAL_SLOT_OWNERSHIP_RECORD_MISSING')
        current_binding=json.loads(binding['data']['binding.json']) if binding else {}
        if binding:
            preserved_bindings[ns]=dict(binding['data']);skip.add(('ConfigMap',ns,'slot-binding'))
        for name in ('hermes-pilot-state','hermes-tools'):
            claim=owned('PersistentVolumeClaim',name,ns,operation,True)
            if claim:preserved_claims[(ns,name)]=(claim['metadata']['uid'],claim['spec'].get('volumeName'))
        previous_job=owned('Job',slot['job'],ns,operation,True)
        if current_binding and not previous_job:raise ValueError('PERSONAL_SLOT_TOOL_MIGRATION_REQUIRED')
        for doc in documents:
            if doc['metadata'].get('namespace')!=ns:continue
            if doc['kind']=='ConfigMap' and doc['metadata']['name']=='slot-binding' and binding:
                doc['data']=dict(binding['data'])
            if doc['kind']=='Secret' and doc['metadata']['name']=='arcia-oidc-runtime':
                old=owned('Secret','arcia-oidc-runtime',ns,operation,True)
                if old:
                    previous_owner=base64.b64decode(old['data'].get('ARCIA_IDENTITY_OWNER_SUBJECT','')).decode()
                    if previous_owner!=current_binding.get('subject',''):raise ValueError('PERSONAL_SLOT_BINDING_DRIFT')
                    expected=doc['stringData']
                    if any(base64.b64decode(old['data'][key]).decode()!=expected[key]
                           for key in ('ARCIA_IDENTITY_ISSUER','ARCIA_IDENTITY_CLIENT_ID')):
                        raise ValueError('PERSONAL_SLOT_ISSUER_CLIENT_DRIFT')
                    skip.add(('Secret',ns,'arcia-oidc-runtime'))
                    doc['stringData']['ARCIA_IDENTITY_OWNER_SUBJECT']=previous_owner
            if doc['kind']=='Deployment':
                old=owned('Deployment',doc['metadata']['name'],ns,operation,True)
                if old and not current_binding and old['spec'].get('replicas',0):
                    raise ValueError('PERSONAL_UNBOUND_WORKLOAD_ACTIVE')
                if old:doc['spec']['replicas']=old['spec']['replicas']
            if doc['kind']=='Job' and previous_job:
                doc['spec']['suspend']=previous_job.get('spec',{}).get('suspend',False)
    documents=[d for d in documents if (d['kind'],d['metadata'].get('namespace'),d['metadata']['name']) not in skip]
    apply([d for d in documents if d['kind']=='Namespace' or
           (d['kind']=='ConfigMap' and d['metadata']['name']=='slot-binding')],operation)
    hmac_secret=owned('Secret','portal-hmac','arcia-access',operation,True)
    if not hmac_secret:
        apply([{'apiVersion':'v1','kind':'Secret','metadata':{'name':'portal-hmac','namespace':'arcia-access'},
                'type':'Opaque','stringData':{'hmac':secrets.token_urlsafe(48)}}],operation)
    for secret_name,service_ns,key in [('knowledge-credentials','arcia-knowledge','tokens.json'),('privacy-policy','arcia-privacy','policy.json')]:
        secret=owned('Secret',secret_name,service_ns,operation)
        content=json.loads(base64.b64decode(secret['data'][key]).decode());before=json.dumps(content,sort_keys=True)
        tokens=content if key=='tokens.json' else content['tokens']
        for slot in values['slots']:
            scope_name='personal-'+slot['id']
            token=next((k for k,v in tokens.items() if v.get('scope')==scope_name and
                        (key!='tokens.json' or v.get('role')=='reader')),None)
            if token is None:
                token=secrets.token_urlsafe(36)
                tokens[token]={'scope':scope_name,**({'role':'reader','read_scopes':[scope_name]} if key=='tokens.json'
                    else {'classification':'synthetic','identifiers':[]})}
            apply([{'apiVersion':'v1','kind':'Secret','metadata':{'name':'knowledge-reader' if key=='tokens.json' else 'privacy-client',
                'namespace':slot['namespace']},'type':'Opaque','stringData':{'token':token}}],operation)
        if json.dumps(content,sort_keys=True)!=before:
            secret=clean(secret);secret['data'][key]=base64.b64encode(json.dumps(content).encode()).decode()
            apply([secret],operation)
            name='knowledge' if key=='tokens.json' else 'privacy'
            kube('rollout','restart','deployment/'+name,'-n',service_ns)
            kube('rollout','status','deployment/'+name,'-n',service_ns,'--timeout=300s',timeout=320)
    # Service-side allowlists admit only the fixed pool label and runtime selector.
    peer={'namespaceSelector':{'matchLabels':{'arcia.io/personal-pool':'true'}},'podSelector':{'matchLabels':{'app':'hermes-pilot'}}}
    for ns,name in [('arcia-knowledge','knowledge-private-only'),('arcia-privacy','local-sanitizer-only'),('arcia-privacy','static-dns-only')]:
        doc=clean(owned('NetworkPolicy',name,ns,operation))
        for rule in doc['spec']['ingress']:
            if peer not in rule['from']:rule['from'].append(peer)
        apply([doc],operation)
    keycloak=clean(owned('NetworkPolicy','keycloak-private-only',NS,operation))
    portal_peer={'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'arcia-access'}},'podSelector':{'matchLabels':{'app':'arcia-portal'}}}
    if portal_peer not in keycloak['spec']['ingress'][0]['from']:keycloak['spec']['ingress'][0]['from'].append(portal_peer)
    apply([keycloak],operation)
    records_doc=clean(owned('ConfigMap','private-dns-records','arcia-privacy',operation))
    records=json.loads(records_doc['data']['records.json'])
    # Deploy immutable renderer output; binding records were applied first.
    apply([d for d in documents if not(d['kind']=='Namespace' or
        (d['kind']=='ConfigMap' and d['metadata']['name']=='slot-binding'))],operation)
    for slot in values['slots']:
        service=owned('Service','context7-docs',slot['namespace'],operation)
        records['context7-docs.'+slot['namespace']+'.svc.cluster.local']=service['spec']['clusterIP']
    records_doc['data']['records.json']=json.dumps(records)
    apply([records_doc],operation)
    kube('rollout','restart','deployment/private-dns','-n','arcia-privacy')
    kube('rollout','status','deployment/private-dns','-n','arcia-privacy','--timeout=120s',timeout=140)
    kube('rollout','status','deployment/arcia-portal','-n','arcia-access','--timeout=180s',timeout=200)
    apply(values['ingress'],operation)
    kube('rollout','status','daemonset/pilot-https','-n','arcia-ingress','--timeout=180s',timeout=200)
    bindings_ok=all(owned('ConfigMap','slot-binding',ns,operation)['data']==data for ns,data in preserved_bindings.items())
    claims_ok=True
    for (ns,name),expected in preserved_claims.items():
        current=owned('PersistentVolumeClaim',name,ns,operation)
        claims_ok=claims_ok and current['metadata']['uid']==expected[0] and (
            expected[1] is None or current['spec'].get('volumeName')==expected[1])
    if not bindings_ok or not claims_ok:raise ValueError('PERSONAL_PORTAL_REAPPLICATION_DRIFT')
    return {'passed':True,'capacity':len(values['slots']),'automatic_first_login':True,'legacy_owners_preserved':True,
            'existing_bindings_preserved':bindings_ok,'existing_pvcs_preserved':claims_ok,
            'bindings_rechecked':len(preserved_bindings),'pvcs_rechecked':len(preserved_claims),
            'sso_provider_enabled':False,'fresh_cluster_rebuilt':False}


if __name__ == '__main__':
    print(json.dumps({'install_identity': install, 'verify_identity': verify,
                      'plan_personal_cleanup': personal_cleanup, 'apply_personal_cleanup': personal_cleanup,
                      'plan_identity_microsoft_egress': plan_microsoft_egress,
                      'plan_identity_access_repair': identity_access_repair,
                      'apply_identity_access_repair': identity_access_repair,
                      'inspect_identity_access_policy': identity_access_repair,
                      'resolve_identity_microsoft_egress': resolve_microsoft_egress,
                      'inspect_identity_microsoft_egress': inspect_microsoft_egress,
                      'install_identity_public_https_egress': install_public_https_egress,
                      'apply_identity_microsoft_egress_repair': apply_microsoft_egress_repair,
                      'inspect_identity': inspect,'prepare_identity':prepare,
                      'connect_identity':connect,'cleanup_identity_fixture':cleanup_unbound_fixture,
                      'prepare_personal_portal':prepare_personal_portal,'install_personal_portal':install_personal_portal,
                      'inspect_personal_portal':inspect_personal_portal,
                      'reconcile_identity_runtime_network':reconcile_runtime_network,
                      'prepare_portal_fixtures':prepare_portal_fixtures,'finish_portal_qualification':finish_portal_qualification,
                      'disable_portal_fixtures':disable_portal_fixtures,
                      'qualify_identity_revocation':qualify_revocation}[ARCIA_INPUT['action']](ARCIA_INPUT)))
