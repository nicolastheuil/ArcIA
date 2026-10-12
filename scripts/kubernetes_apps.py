"""Pinned qualification applications. No real client data or cloud credentials."""
import base64
import hashlib
import ipaddress
import json
import re
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]


def namespace(name, privileged=False):
    return {'apiVersion':'v1','kind':'Namespace','metadata':{'name':name,
        'labels':{'pod-security.kubernetes.io/enforce':'privileged' if privileged else 'restricted'}}}


def deny_all(name):
    return {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'deny-all','namespace':name},
        'spec':{'podSelector':{},'policyTypes':['Ingress','Egress']}}


def quota(name, hard):
    return {'apiVersion':'v1','kind':'ResourceQuota','metadata':{'name':'qualification-bounds','namespace':name},'spec':{'hard':hard}}


def operator(lock):
    content=(ROOT/'deploy/vendor/cnpg/operator.yaml').read_bytes()
    if hashlib.sha256(content).hexdigest()!=lock['cnpg_source']['rendered_sha256']:
        raise ValueError('CNPG_SOURCE_HASH_MISMATCH')
    documents=list(yaml.safe_load_all(content))
    for doc in documents:
        if doc['kind']=='Namespace': doc['metadata']['labels']={'pod-security.kubernetes.io/enforce':'restricted'}
        if doc['kind']=='Deployment':
            doc['spec']['replicas']=2
            doc['spec']['template']['spec']['affinity']={'podAntiAffinity':{'requiredDuringSchedulingIgnoredDuringExecution':[
                {'labelSelector':{'matchLabels':doc['spec']['selector']['matchLabels']},'topologyKey':'kubernetes.io/hostname'}]}}
            doc['spec']['template']['spec']['containers'][0]['resources']={'requests':{'cpu':'100m','memory':'256Mi'},'limits':{'cpu':'1000m','memory':'512Mi'}}
    return documents


def postgres(lock, config):
    ns='arcia-data'
    docs=[namespace(ns),deny_all(ns),quota(ns,{'pods':'10','requests.cpu':'8','requests.memory':'16Gi',
        'limits.cpu':'16','limits.memory':'32Gi','persistentvolumeclaims':'5','requests.storage':'100Gi'})]
    api_ips=[str(ipaddress.ip_network(config['network']['service_cidr']).network_address+1)]+[n['address'] for n in config['nodes']]
    docs.append({'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'postgres-control-and-replication','namespace':ns},
        'spec':{'podSelector':{},'policyTypes':['Ingress','Egress'],
            'ingress':[{'from':[{'podSelector':{}}],'ports':[{'port':5432,'protocol':'TCP'}]},
                {'from':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'cnpg-system'}}}],'ports':[{'port':8000,'protocol':'TCP'}]}],
            'egress':[{'to':[{'podSelector':{}}],'ports':[{'port':5432,'protocol':'TCP'}]},
                {'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},'podSelector':{'matchLabels':{'k8s-app':'kube-dns'}}}],
                    'ports':[{'port':53,'protocol':'UDP'},{'port':53,'protocol':'TCP'}]},
                {'to':[{'ipBlock':{'cidr':ip+'/32'}} for ip in api_ips],
                    'ports':[{'port':443,'protocol':'TCP'},{'port':6443,'protocol':'TCP'}]}]}})
    # CNPG parses the PostgreSQL major from the tag; the digest still fixes bytes.
    image=lock['components']['postgres_pgvector']['image']
    if not re.fullmatch(r'ghcr.io/cloudnative-pg/postgresql:18\.[A-Za-z0-9._-]+@sha256:[a-f0-9]{64}',image):
        raise ValueError('POSTGRES_VERSION_TAG_AND_DIGEST_REQUIRED')
    docs.append({'apiVersion':'postgresql.cnpg.io/v1','kind':'Cluster','metadata':{'name':'arcia-postgres','namespace':ns},
        'spec':{'instances':3,'imageName':image,
            'enableSuperuserAccess':False,'storage':{'size':'20Gi','storageClass':'arcia-vsphere'},
            'affinity':{'enablePodAntiAffinity':True,'podAntiAffinityType':'required','topologyKey':'kubernetes.io/hostname'},
            'resources':{'requests':{'cpu':'500m','memory':'1Gi'},'limits':{'cpu':'2000m','memory':'4Gi'}},
            'postgresql':{'synchronous':{'method':'any','number':1,'dataDurability':'required'}},
            'bootstrap':{'initdb':{'database':'arcia','owner':'arcia','postInitApplicationSQL':['CREATE EXTENSION IF NOT EXISTS vector;']}},
            'monitoring':{'enablePodMonitor':False}}})
    return docs


def password_hash(pilot):
    salt=base64.b64decode(pilot['password_salt'])
    derived=hashlib.scrypt(pilot['password'].encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
    return 'scrypt$16384$8$1$'+base64.b64encode(salt).decode()+'$'+base64.b64encode(derived).decode()


def hermes(lock, config, pilot):
    ns='arcia-hermes'
    host=config['network']['public_hostname']
    settings={'model':{'default':'qualification-disabled','provider':'custom','base_url':'http://127.0.0.1:9/v1'},
        'terminal':{'backend':'local'},'security':{'allow_lazy_installs':False},
        'dashboard':{'public_url':'https://'+host,'trusted_proxies':[str(ipaddress.ip_network(config['network']['pod_cidr']))]},
        'platform':{'qualification_only':True,'cloud_calls_enabled':False}}
    docs=[namespace(ns),deny_all(ns),quota(ns,{'pods':'3','requests.cpu':'3','requests.memory':'6Gi',
        'limits.cpu':'6','limits.memory':'12Gi','persistentvolumeclaims':'2','requests.storage':'20Gi'}),
        {'apiVersion':'v1','kind':'Secret','metadata':{'name':'hermes-pilot-auth','namespace':ns},'type':'Opaque',
            'stringData':{'HERMES_DASHBOARD_BASIC_AUTH_USERNAME':pilot['username'],
                'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH':password_hash(pilot),
                'HERMES_DASHBOARD_BASIC_AUTH_SECRET':pilot['session_secret']}},
        {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'hermes-pilot-config','namespace':ns},
            'data':{'config.yaml':yaml.safe_dump(settings,sort_keys=False)}},
        {'apiVersion':'v1','kind':'PersistentVolumeClaim','metadata':{'name':'hermes-pilot-state','namespace':ns},
            'spec':{'storageClassName':'arcia-vsphere','accessModes':['ReadWriteOncePod'],
                'resources':{'requests':{'storage':'10Gi'}}}},
        {'apiVersion':'v1','kind':'Service','metadata':{'name':'hermes-pilot','namespace':ns},
            'spec':{'selector':{'app':'hermes-pilot'},'ports':[{'port':9119,'targetPort':9119}]}},
        {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'ingress-from-private-proxy','namespace':ns},
            'spec':{'podSelector':{'matchLabels':{'app':'hermes-pilot'}},'policyTypes':['Ingress'],
                'ingress':[{'from':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'arcia-ingress'}},
                    'podSelector':{'matchLabels':{'app':'pilot-https'}}}],
                    'ports':[{'port':9119,'protocol':'TCP'}]}]}},
        {'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':'hermes-pilot','namespace':ns},
            'spec':{'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':{'app':'hermes-pilot'}},
                'template':{'metadata':{'labels':{'app':'hermes-pilot'},'annotations':{
                    'arcia.io/config-sha256':hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()}},'spec':{
                    'automountServiceAccountToken':False,'terminationGracePeriodSeconds':45,
                    'securityContext':{'runAsNonRoot':True,'runAsUser':10000,'runAsGroup':10000,'fsGroup':10000,
                        'seccompProfile':{'type':'RuntimeDefault'}},
                    'containers':[{'name':'hermes','image':lock['components']['hermes']['image'],
                        'workingDir':'/opt/data',
                        'command':['/opt/hermes/.venv/bin/python','-c',
                            "import os;os.makedirs('/tmp/hermes-runtime',mode=0o700,exist_ok=True);os.execv('/opt/hermes/.venv/bin/hermes',['hermes','dashboard','--host','0.0.0.0','--port','9119','--no-open'])"],
                        'env':[{'name':'HOME','value':'/opt/data'},{'name':'HERMES_HOME','value':'/opt/data'},
                            {'name':'HERMES_DASHBOARD_PUBLIC_URL','value':'https://'+host},
                            {'name':'DISABLE_TELEMETRY','value':'1'},{'name':'PYTHONDONTWRITEBYTECODE','value':'1'}],
                        'envFrom':[{'secretRef':{'name':'hermes-pilot-auth'}}],
                        'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},
                        'ports':[{'containerPort':9119}],
                        'resources':{'requests':{'cpu':'500m','memory':'1Gi'},'limits':{'cpu':'2000m','memory':'4Gi'}},
                        'startupProbe':{'tcpSocket':{'port':9119},'failureThreshold':60,'periodSeconds':5},
                        'readinessProbe':{'tcpSocket':{'port':9119},'periodSeconds':5},
                        'volumeMounts':[{'name':'state','mountPath':'/opt/data'},
                            {'name':'config','mountPath':'/opt/data/config.yaml','subPath':'config.yaml','readOnly':True},
                            {'name':'tmp','mountPath':'/tmp'}]}],
                    'volumes':[{'name':'state','persistentVolumeClaim':{'claimName':'hermes-pilot-state'}},
                        {'name':'config','configMap':{'name':'hermes-pilot-config'}},{'name':'tmp','emptyDir':{'sizeLimit':'512Mi'}}]}}}}]
    if lock.get('hermes_tools',{}).get('enabled'):
        import hermes_tools
        hermes_tools.augment(docs)
    if lock.get('knowledge',{}).get('enabled'):
        import knowledge_client
        cm=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config')
        settings=yaml.safe_load(cm['data']['config.yaml'])
        knowledge_client.augment(docs,settings)
        cm['data']['config.yaml']=yaml.safe_dump(settings,sort_keys=False)
        deployment=next(d for d in docs if d['kind']=='Deployment' and d['metadata']['name']=='hermes-pilot')
        deployment['spec']['template']['metadata']['annotations']['arcia.io/config-sha256']=hashlib.sha256(cm['data']['config.yaml'].encode()).hexdigest()
    if lock.get('privacy',{}).get('enabled'):
        import privacy_deploy
        privacy_deploy.augment(docs)
    if lock.get('multiuser',{}).get('enabled'):
        boundary=(ROOT/'services/multiuser/dashboard_boundary.py').read_text(encoding='utf-8')
        docs.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'dashboard-session-boundary','namespace':ns},'data':{'boundary.py':boundary}})
        deployment=next(d for d in docs if d['kind']=='Deployment' and d['metadata']['name']=='hermes-pilot')
        spec=deployment['spec']['template']['spec'];container=spec['containers'][0]
        container['command']=['/opt/hermes/.venv/bin/python','/opt/arcia-dashboard/boundary.py']
        container['volumeMounts'].append({'name':'dashboard-boundary','mountPath':'/opt/arcia-dashboard','readOnly':True})
        spec['volumes'].append({'name':'dashboard-boundary','configMap':{'name':'dashboard-session-boundary'}})
        deployment['spec']['template']['metadata']['annotations']['arcia.io/session-boundary-sha256']=hashlib.sha256(boundary.encode()).hexdigest()
    # A content-addressed immutable mount avoids kubelet caching an older value
    # during a rollout. The stable ConfigMap remains the administrative interface.
    cm=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config')
    digest=hashlib.sha256(cm['data']['config.yaml'].encode()).hexdigest()
    name='hermes-config-'+digest[:16]
    docs.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':name,'namespace':ns},'immutable':True,'data':dict(cm['data'])})
    deployment=next(d for d in docs if d['kind']=='Deployment' and d['metadata']['name']=='hermes-pilot')
    next(v for v in deployment['spec']['template']['spec']['volumes'] if v['name']=='config')['configMap']['name']=name
    return docs


def ingress(lock, config, pilot):
    ns='arcia-ingress';host=config['network']['public_hostname']
    # A narrow hostPort exception exposes only the private HTTPS listener on each node.
    nginx='''pid /tmp/nginx.pid;
error_log /dev/stderr warn;
events { worker_connections 1024; }
http {
  access_log off;
  error_log /dev/stderr warn;
  client_body_temp_path /tmp/client;
  proxy_temp_path /tmp/proxy;
  fastcgi_temp_path /tmp/fastcgi;
  uwsgi_temp_path /tmp/uwsgi;
  scgi_temp_path /tmp/scgi;
  map $http_upgrade $connection_upgrade { default upgrade; '' close; }
  server { listen 8443 ssl default_server; ssl_reject_handshake on; }
  server {
    listen 8443 ssl;
    server_name '''+host+''';
    ssl_certificate /tls/tls.crt;
    ssl_certificate_key /tls/tls.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 20m;
    location / {
      proxy_pass http://hermes-pilot.arcia-hermes.svc.cluster.local:9119;
      proxy_http_version 1.1;
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-Proto https;
      proxy_set_header X-Forwarded-For $remote_addr;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection $connection_upgrade;
      proxy_buffering off;
      proxy_read_timeout 600s;
    }
  }
}
'''
    if lock.get('multiuser',{}).get('enabled'):
        # Runtime DNS resolution permits a fresh bootstrap before B exists.
        resolver=str(ipaddress.ip_network(config['network']['service_cidr']).network_address+10)
        route='''    location = /qualification-b { return 302 /qualification-b/; }
    location ^~ /qualification-b/ {
      resolver '''+resolver+''' valid=10s ipv6=off;
      set $qualification_b http://hermes-pilot.arcia-hermes-qualification-b.svc.cluster.local:9119;
      rewrite ^/qualification-b/(.*)$ /$1 break;
      proxy_pass $qualification_b;
      proxy_http_version 1.1;
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-Proto https;
      proxy_set_header X-Forwarded-Prefix /qualification-b;
      proxy_set_header X-Forwarded-For $remote_addr;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection $connection_upgrade;
      proxy_buffering off;
      proxy_read_timeout 600s;
    }
'''
        nginx=nginx.replace('    location / {',route+'    location / {')
        # Never trust a caller-supplied prefix or identity on the main route.
        nginx=nginx.replace('    location / {','    location / {\n      proxy_set_header X-Forwarded-Prefix "";')
    return [namespace(ns,True),deny_all(ns),quota(ns,{'pods':'6','requests.cpu':'1','requests.memory':'1Gi',
        'limits.cpu':'3','limits.memory':'2Gi','persistentvolumeclaims':'0'}),
        {'apiVersion':'v1','kind':'Secret','metadata':{'name':'pilot-tls','namespace':ns},'type':'kubernetes.io/tls',
            'stringData':{'tls.crt':pilot['tls_certificate'],'tls.key':pilot['tls_private_key']}},
        {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'pilot-nginx','namespace':ns},'data':{'nginx.conf':nginx}},
        {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'https-and-hermes-only','namespace':ns},
            'spec':{'podSelector':{},'policyTypes':['Ingress','Egress'],
                'ingress':[{'ports':[{'port':8443,'protocol':'TCP'}]}],
                'egress':[{'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'arcia-hermes'}},
                    'podSelector':{'matchLabels':{'app':'hermes-pilot'}}}],'ports':[{'port':9119,'protocol':'TCP'}]},
                    *([{'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'arcia-hermes-qualification-b'}},
                        'podSelector':{'matchLabels':{'app':'hermes-pilot'}}}],'ports':[{'port':9119,'protocol':'TCP'}]}] if lock.get('multiuser',{}).get('enabled') else []),
                    {'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},
                        'podSelector':{'matchLabels':{'k8s-app':'kube-dns'}}}],
                        'ports':[{'port':53,'protocol':'UDP'},{'port':53,'protocol':'TCP'}]}]}},
        {'apiVersion':'apps/v1','kind':'DaemonSet','metadata':{'name':'pilot-https','namespace':ns},
            'spec':{'selector':{'matchLabels':{'app':'pilot-https'}},'template':{
                'metadata':{'labels':{'app':'pilot-https'},'annotations':{
                    'arcia.io/config-sha256':hashlib.sha256(nginx.encode()).hexdigest(),
                    'arcia.io/tls-sha256':hashlib.sha256(pilot['tls_certificate'].encode()).hexdigest()}},'spec':{
                    'automountServiceAccountToken':False,'securityContext':{'runAsNonRoot':True,'runAsUser':101,
                        'runAsGroup':101,'fsGroup':101,'seccompProfile':{'type':'RuntimeDefault'}},
                    'containers':[{'name':'nginx','image':lock['components']['ingress']['image'],
                        'command':['nginx'],'args':['-g','daemon off;','-c','/etc/nginx/nginx.conf'],
                        'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},
                        'ports':[{'containerPort':8443,'hostPort':443}],
                        'readinessProbe':{'tcpSocket':{'port':8443},'periodSeconds':5},
                        'resources':{'requests':{'cpu':'50m','memory':'64Mi'},'limits':{'cpu':'500m','memory':'256Mi'}},
                        'volumeMounts':[{'name':'config','mountPath':'/etc/nginx/nginx.conf','subPath':'nginx.conf','readOnly':True},
                            {'name':'tls','mountPath':'/tls','readOnly':True},{'name':'tmp','mountPath':'/tmp'}]}],
                    'volumes':[{'name':'config','configMap':{'name':'pilot-nginx'}},
                        {'name':'tls','secret':{'secretName':'pilot-tls','defaultMode':288}},
                        {'name':'tmp','emptyDir':{'sizeLimit':'128Mi'}}]}}}}]
