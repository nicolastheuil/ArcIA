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
    for doc in documents:
        owned(doc['kind'], doc['metadata']['name'], doc['metadata'].get('namespace'), operation, True)
        doc['metadata'].setdefault('annotations', {})['arcia.io/operation-id'] = operation
    kube('apply', '--server-side', '--field-manager=arcia-foundation', '-f', '-',
         document={'apiVersion': 'v1', 'kind': 'List', 'items': documents})


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
            source="""import os,httpx,json
r={'binding_present':bool(os.environ.get('ARCIA_IDENTITY_ISSUER'))}
try:
 u=os.environ['ARCIA_IDENTITY_ISSUER'];d=httpx.get(u+'/.well-known/openid-configuration',timeout=10)
 r['discovery_status']=d.status_code
 r['jwks_status']=httpx.get(d.json()['jwks_uri'],timeout=10).status_code
 t=httpx.get(u+'/protocol/openid-connect/userinfo',headers={'Authorization':'Bearer invalid-synthetic'},timeout=10)
 r['userinfo_status']=t.status_code;r['invalid_token_denied']=t.status_code==401
 r['identity_admin_credentials_absent']=not bool(os.environ.get('ARCIA_IDENTITY_CLIENT_SECRET'))
except Exception as e:r['probe_exception_type']=type(e).__name__ if type(e).__name__ in ('ConnectError','ConnectTimeout','ReadTimeout','KeyError') else 'OTHER'
print(json.dumps(r))"""
            probes.append(json.loads(kube('exec',pod['metadata']['name'],'-n',ns,'--','/opt/hermes/.venv/bin/python','-c',source)))
            log=kube('logs',pod['metadata']['name'],'-n',ns,'--tail=80')
            probes[-1]['error_codes']=[code for code in ('ARCIA_LOGIN_REFUSED','ARCIA_USER_ROLE_REQUIRED','ARCIA_IDENTITY_UNAVAILABLE',
                'ARCIA_RUNTIME_OWNER_REQUIRED','ARCIA_RUNTIME_CLIENT_REQUIRED','ARCIA_NONCE_MISMATCH','ARCIA_TOKEN_REFUSED','ARCIA_SESSION_INACTIVE') if code in log]
        result['runtime_probes']=probes
    return result


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


if __name__ == '__main__':
    print(json.dumps({'install_identity': install, 'verify_identity': verify,
                      'inspect_identity': inspect,'prepare_identity':prepare,
                      'connect_identity':connect,'cleanup_identity_fixture':cleanup_unbound_fixture,
                      'qualify_identity_revocation':qualify_revocation}[ARCIA_INPUT['action']](ARCIA_INPUT)))
