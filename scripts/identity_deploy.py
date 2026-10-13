"""Fixed Keycloak identity portal; no instance names or credentials in Git."""
import copy
import hashlib
import json
from pathlib import Path
import re
import ipaddress
import kubernetes_apps

ROOT = Path(__file__).resolve().parents[1]
NS = 'arcia-identity'


def payload(lock, config, credentials, pilot):
    host = config['network']['public_hostname']
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]+[a-z0-9]', host):
        raise ValueError('IDENTITY_HOST_INVALID')
    image = lock['components']['keycloak']['image']
    if not re.fullmatch(r'quay.io/keycloak/keycloak@sha256:[a-f0-9]{64}', image):
        raise ValueError('IDENTITY_IMAGE_NOT_PINNED')
    def resource(kind, name, spec):
        return {'apiVersion': 'v1' if kind in ('Secret', 'Service', 'ConfigMap') else 'networking.k8s.io/v1',
                'kind': kind, 'metadata': {'name': name, 'namespace': NS}, **spec}
    dns = {'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                   'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
           'ports': [{'port': 53, 'protocol': p} for p in ('UDP', 'TCP')]}
    docs = [kubernetes_apps.namespace(NS), kubernetes_apps.deny_all(NS),
            kubernetes_apps.quota(NS, {'pods': '6', 'requests.cpu': '3', 'requests.memory': '6Gi',
                                      'limits.cpu': '8', 'limits.memory': '12Gi',
                                      'persistentvolumeclaims': '3', 'requests.storage': '60Gi'}),
            resource('Secret', 'identity-db-auth', {'type': 'kubernetes.io/basic-auth',
                     'stringData': {'username': 'keycloak', 'password': credentials['db_password']}}),
            resource('Secret', 'identity-bootstrap', {'type': 'Opaque', 'stringData': {
                'username': credentials['bootstrap_username'], 'password': credentials['bootstrap_password']}}),
            resource('Service', 'keycloak', {'spec': {'selector': {'app': 'keycloak'},
                                                     'ports': [{'port': 8080, 'targetPort': 8080}]}})]
    database = {'apiVersion': 'postgresql.cnpg.io/v1', 'kind': 'Cluster',
                'metadata': {'name': 'identity-db', 'namespace': NS}, 'spec': {
                    'instances': 1, 'imageName': lock['components']['postgres_pgvector']['image'],
                    'enableSuperuserAccess': False, 'storage': {'size': '20Gi', 'storageClass': 'arcia-vsphere'},
                    'resources': {'requests': {'cpu': '250m', 'memory': '512Mi'},
                                  'limits': {'cpu': '2000m', 'memory': '2Gi'}},
                    'bootstrap': {'initdb': {'database': 'keycloak', 'owner': 'keycloak',
                                            'secret': {'name': 'identity-db-auth'}}}}}
    docs.append(database)
    docs += [resource('NetworkPolicy', 'keycloak-private-only', {'spec': {
        'podSelector': {'matchLabels': {'app': 'keycloak'}}, 'policyTypes': ['Ingress', 'Egress'],
        'ingress': [{'from': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'arcia-ingress'}},
                              'podSelector': {'matchLabels': {'app': 'pilot-https'}}}],
                     'ports': [{'port': 8080, 'protocol': 'TCP'}]}],
        'egress': [dns, {'to': [{'podSelector': {'matchLabels': {'cnpg.io/cluster': 'identity-db'}}}],
                         'ports': [{'port': 5432, 'protocol': 'TCP'}]}]}}),
        resource('NetworkPolicy', 'identity-postgres', {'spec': {
            'podSelector': {'matchLabels': {'cnpg.io/cluster': 'identity-db'}},
            'policyTypes': ['Ingress', 'Egress'],
            'ingress': [{'from': [{'podSelector': {'matchLabels': {'app': 'keycloak'}}}],
                         'ports': [{'port': 5432, 'protocol': 'TCP'}]},
                        {'from': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'cnpg-system'}}}],
                         'ports': [{'port': 8000, 'protocol': 'TCP'}]}],
            'egress': [dns, {'to': [{'ipBlock': {'cidr': n['address'] + '/32'}} for n in config['nodes']],
                            'ports': [{'port': 6443, 'protocol': 'TCP'}]},
                       {'to': [{'ipBlock': {'cidr': str(ipaddress.ip_network(config['network']['service_cidr']).network_address + 1) + '/32'}}],
                        'ports': [{'port': 443, 'protocol': 'TCP'}]}]}})]
    env = { 'KC_DB': 'postgres',
            'KC_DB_URL': 'jdbc:postgresql://identity-db-rw:5432/keycloak?sslmode=verify-full&sslrootcert=/db-ca/ca.crt',
            'KC_DB_USERNAME': 'keycloak', 'KC_HOSTNAME': 'https://' + host + '/identity',
            'KC_HTTP_RELATIVE_PATH': '/identity', 'KC_HTTP_MANAGEMENT_RELATIVE_PATH': '/',
            'KC_HTTP_ENABLED': 'true', 'KC_PROXY_HEADERS': 'xforwarded',
            'KC_CACHE': 'local', 'KC_HEALTH_ENABLED': 'true',
            'KC_SPI_CONNECTIONS_JPA__QUARKUS__ASYNC_COMMIT': 'false'}
    sec = {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}
    deployment = {'apiVersion': 'apps/v1', 'kind': 'Deployment',
        'metadata': {'name': 'keycloak', 'namespace': NS}, 'spec': {
            'replicas': 1, 'strategy': {'type': 'Recreate'}, 'selector': {'matchLabels': {'app': 'keycloak'}},
            'template': {'metadata': {'labels': {'app': 'keycloak'}}, 'spec': {
                'automountServiceAccountToken': False,
                'securityContext': {'runAsNonRoot': True, 'runAsUser': 1000, 'runAsGroup': 1000,
                                    'fsGroup': 1000, 'seccompProfile': {'type': 'RuntimeDefault'}},
                'containers': [{'name': 'keycloak', 'image': image, 'args': ['start'],
                    'securityContext': sec,
                    'env': [{'name': k, 'value': v} for k, v in env.items()] + [
                        {'name': 'KC_DB_PASSWORD', 'valueFrom': {'secretKeyRef': {'name': 'identity-db-auth', 'key': 'password'}}},
                        *[{'name': 'KC_BOOTSTRAP_ADMIN_' + suffix, 'valueFrom': {
                            'secretKeyRef': {'name': 'identity-bootstrap', 'key': key}}}
                          for suffix, key in [('USERNAME', 'username'), ('PASSWORD', 'password')]]],
                    'ports': [{'containerPort': 8080}, {'containerPort': 9000}],
                    'startupProbe': {'httpGet': {'path': '/health/ready', 'port': 9000}, 'periodSeconds': 5, 'failureThreshold': 90},
                    'readinessProbe': {'httpGet': {'path': '/health/ready', 'port': 9000}, 'periodSeconds': 10},
                    'livenessProbe': {'httpGet': {'path': '/health/live', 'port': 9000}, 'periodSeconds': 30},
                    'resources': {'requests': {'cpu': '500m', 'memory': '1Gi'}, 'limits': {'cpu': '2000m', 'memory': '2Gi'}},
                    'volumeMounts': [{'name': 'db-ca', 'mountPath': '/db-ca', 'readOnly': True}]}],
                'volumes': [{'name': 'db-ca', 'secret': {'secretName': 'identity-db-ca',
                              'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}}]}}}}
    docs.append(deployment)
    mode = config.get('identity', {}).get('https_egress_mode', 'disabled')
    if mode not in ('disabled', 'public_ipv4_443'):
        raise ValueError('IDENTITY_HTTPS_EGRESS_MODE_INVALID')
    if mode == 'public_ipv4_443':
        import identity_egress
        docs.extend([identity_egress.public_https_policy(config['network']), identity_egress.retired_snapshot_policy()])
    return {'documents': docs, 'ingress': kubernetes_apps.ingress(lock, config, pilot),
            'credentials': credentials, 'hostname': host,
            'realm_source': (ROOT / 'services/identity/realm.py').read_text(encoding='utf-8')}


def augment_hermes(docs):
    """Bindings are namespace-local Secrets. Empty seed runtimes stay in qualification mode."""
    import yaml
    deployment = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'] == 'hermes-pilot')
    ns = deployment['metadata']['namespace']
    source = (ROOT / 'services/identity/provider.py').read_text(encoding='utf-8')
    descriptor = 'name: arcia-identity\nversion: 1.0.0\nkind: backend\ndescription: ArcIA permanent local and federated identity\n'
    name = 'arcia-identity-plugin-' + hashlib.sha256(source.encode()).hexdigest()[:16]
    docs.append({'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': name, 'namespace': ns},
                 'immutable': True, 'data': {'__init__.py': source, 'plugin.yaml': descriptor}})
    spec = deployment['spec']['template']['spec']
    container=spec['containers'][0]
    container['envFrom']=[e for e in container.get('envFrom',[]) if e.get('secretRef',{}).get('name')!='arcia-oidc-runtime']
    container['envFrom'].append({'secretRef': {'name': 'arcia-oidc-runtime', 'optional': True}})
    container['volumeMounts']=[v for v in container['volumeMounts'] if v['name']!='identity-plugin']
    container['volumeMounts'].append({'name': 'identity-plugin',
        'mountPath': '/opt/data/plugins/arcia-identity', 'readOnly': True})
    spec['volumes']=[v for v in spec['volumes'] if v['name']!='identity-plugin']
    spec['volumes'].append({'name': 'identity-plugin', 'configMap': {'name': name}})
    cm = next(d for d in docs if d['kind'] == 'ConfigMap' and d['metadata']['name'] == 'hermes-pilot-config')
    config = yaml.safe_load(cm['data']['config.yaml'])
    enabled=config.setdefault('plugins', {}).setdefault('enabled', [])
    if 'arcia-identity' not in enabled:enabled.append('arcia-identity')
    cm['data']['config.yaml'] = yaml.safe_dump(config, sort_keys=False)
    deployment['spec']['template']['metadata']['annotations']['arcia.io/identity-plugin-sha256'] = hashlib.sha256(source.encode()).hexdigest()


def runtime_updates(prepared, config, https_ip):
    updates=[]
    for original in prepared['runtimes']:
        docs=copy.deepcopy(original)
        augment_hermes(docs)
        cm=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config')
        digest=hashlib.sha256(cm['data']['config.yaml'].encode()).hexdigest()
        ns=cm['metadata']['namespace'];name='hermes-config-'+digest[:16]
        docs.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':name,'namespace':ns},'immutable':True,'data':dict(cm['data'])})
        deployment=next(d for d in docs if d['kind']=='Deployment')
        spec=deployment['spec']['template']['spec']
        next(v for v in spec['volumes'] if v['name']=='config')['configMap']['name']=name
        deployment['spec']['template']['metadata']['annotations']['arcia.io/config-sha256']=digest
        boundary=(ROOT/'services/multiuser/dashboard_boundary.py').read_text(encoding='utf-8')
        docs.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'dashboard-session-boundary','namespace':ns},'data':{'boundary.py':boundary}})
        deployment['spec']['template']['metadata']['annotations']['arcia.io/session-boundary-sha256']=hashlib.sha256(boundary.encode()).hexdigest()
        docs.append({'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'identity-https-egress','namespace':ns},
            'spec':{'podSelector':{'matchLabels':{'app':'hermes-pilot'}},'policyTypes':['Egress'],
                    'egress':[{'to':[{'ipBlock':{'cidr':ip+'/32'}} for ip in dict.fromkeys([https_ip]+[n['address'] for n in config['nodes']])],
                               'ports':[{'port':443,'protocol':'TCP'}]}]}})
        updates.extend(docs)
    return updates
