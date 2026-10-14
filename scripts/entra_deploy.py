"""One auth-only Hermes canary; retain Keycloak until the human login recipe."""
import copy
import hashlib
import json
from pathlib import Path
from uuid import UUID
import yaml
import kubernetes_apps
import hermes_tools

ROOT=Path(__file__).resolve().parents[1]
NS='arcia-entra-test'
PREFIX='/entra-test'


def enrollment(value,operation):
    if value.get('operation_id')!=operation:raise ValueError('ENTRA_TEST_ENROLLMENT_SCOPE')
    fields={key:str(UUID(value[key])) for key in ('tenant_id','client_id','owner_object_id')}
    if any(UUID(v).int==0 for v in fields.values()):raise ValueError('ENTRA_TEST_GUID_REQUIRED')
    secret=value.get('client_secret')
    if not isinstance(secret,str) or not 8<=len(secret)<=8192:raise ValueError('ENTRA_TEST_SECRET_REQUIRED')
    return {**fields,'client_secret':secret}


def payload(lock,config,pilot,enrolled,operation):
    fields=enrollment(enrolled,operation)
    if pilot.get('username')!='admin':raise ValueError('ENTRA_TEST_SINGLE_LOCAL_ADMIN_REQUIRED')
    # Auth recipe has no inference, RAG or connection to another user's state.
    canary_lock=copy.deepcopy(lock)
    for feature in ('identity','privacy','knowledge'):canary_lock[feature]={'enabled':False}
    canary_lock['multiuser']={'enabled':True}
    documents=json.loads(json.dumps(kubernetes_apps.hermes(canary_lock,config,pilot)).replace('arcia-hermes',NS))
    for doc in documents:
        meta=doc['metadata']
        if doc['kind']=='Namespace':meta['name']=NS
        if 'namespace' in meta:meta['namespace']=NS
    deployment=next(d for d in documents if d['kind']=='Deployment' and d['metadata']['name']=='hermes-pilot')
    spec=deployment['spec']['template']['spec'];container=spec['containers'][0]
    # Cluster DNS can resolve the internal relay; Hermes cannot reach public IPs.
    spec.pop('dnsConfig',None);spec['dnsPolicy']='ClusterFirst'
    for env in container['env']:
        if env['name']=='HERMES_DASHBOARD_PUBLIC_URL':env['value']+=PREFIX
    container['envFrom'].append({'secretRef':{'name':'entra-test-oidc'}})
    container['env'] += [{'name':'HTTPS_PROXY','value':'http://entra-auth-egress:8088'},
                        {'name':'HTTP_PROXY','value':'http://entra-auth-egress:8088'},
                        {'name':'NO_PROXY','value':'localhost,127.0.0.1,.svc,.svc.cluster.local'}]
    source=(ROOT/'services/identity/entra_provider.py').read_text(encoding='utf-8')
    digest=hashlib.sha256(source.encode()).hexdigest();plugin='entra-native-'+digest[:16]
    documents.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':plugin,'namespace':NS},'immutable':True,
        'data':{'__init__.py':source,'plugin.yaml':'name: arcia-entra-test\nversion: 1.0.0\nkind: backend\ndescription: Native Entra OIDC owner-bound authentication canary\n'}})
    container['volumeMounts'].append({'name':'entra-plugin','mountPath':'/opt/data/plugins/arcia-entra-test','readOnly':True})
    spec['volumes'].append({'name':'entra-plugin','configMap':{'name':plugin}})
    stable=next(d for d in documents if d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config')
    settings=yaml.safe_load(stable['data']['config.yaml'])
    settings['dashboard']['public_url']+=PREFIX
    settings.setdefault('plugins',{})['enabled']=['arcia-entra-test']
    settings['platform']['authentication_canary_only']=True
    stable['data']['config.yaml']=yaml.safe_dump(settings,sort_keys=False)
    documents=[d for d in documents if not (d['kind']=='ConfigMap' and d['metadata']['name'].startswith('hermes-config-'))]
    config_sha=hashlib.sha256(stable['data']['config.yaml'].encode()).hexdigest();name='hermes-config-'+config_sha[:16]
    documents.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':name,'namespace':NS},'immutable':True,'data':dict(stable['data'])})
    next(v for v in spec['volumes'] if v['name']=='config')['configMap']['name']=name
    deployment['spec']['template']['metadata']['annotations'].update({'arcia.io/config-sha256':config_sha,'arcia.io/entra-plugin-sha256':digest})
    documents.append({'apiVersion':'v1','kind':'Secret','metadata':{'name':'entra-test-oidc','namespace':NS},'type':'Opaque','stringData':{
        'ARCIA_ENTRA_TENANT_ID':fields['tenant_id'],'ARCIA_ENTRA_CLIENT_ID':fields['client_id'],
        'ARCIA_ENTRA_OWNER_OBJECT_ID':fields['owner_object_id'],'ARCIA_ENTRA_CLIENT_SECRET':fields['client_secret']}})
    job=json.loads(json.dumps(next(d for d in hermes_tools.payload()['documents'] if d['kind']=='Job')).replace('arcia-hermes',NS))
    job['metadata']['namespace']=NS
    # Replace the runtime allowlist; public egress belongs only to installer/relay.
    documents=[d for d in documents if not (d['kind']=='NetworkPolicy' and d['metadata']['name']=='hermes-internal-docs-only')]
    dns={'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},'podSelector':{'matchLabels':{'k8s-app':'kube-dns'}}}],
         'ports':[{'port':53,'protocol':p} for p in ('TCP','UDP')]}
    documents.append({'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'hermes-auth-only','namespace':NS},'spec':{
        'podSelector':{'matchLabels':{'app':'hermes-pilot'}},'policyTypes':['Egress'],'egress':[dns,{
            'to':[{'podSelector':{'matchLabels':{'app':'entra-auth-egress'}}}],'ports':[{'port':8088,'protocol':'TCP'}]}]}})
    relay_source=(ROOT/'services/identity/entra_egress.py').read_text(encoding='utf-8')
    relay_sha=hashlib.sha256(relay_source.encode()).hexdigest();relay_code='entra-auth-egress-'+relay_sha[:16]
    documents.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':relay_code,'namespace':NS},'immutable':True,'data':{'relay.py':relay_source}})
    documents.append({'apiVersion':'v1','kind':'Service','metadata':{'name':'entra-auth-egress','namespace':NS},'spec':{
        'selector':{'app':'entra-auth-egress'},'ports':[{'port':8088,'targetPort':8088}]}})
    documents.append({'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':'entra-auth-egress','namespace':NS},'spec':{
        'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':{'app':'entra-auth-egress'}},
        'template':{'metadata':{'labels':{'app':'entra-auth-egress'},'annotations':{'arcia.io/code-sha256':relay_sha}},'spec':{
            'automountServiceAccountToken':False,'securityContext':copy.deepcopy(spec['securityContext']),
            'containers':[{'name':'relay','image':lock['components']['hermes']['image'],
                'command':['/opt/hermes/.venv/bin/python','/code/relay.py'],'securityContext':copy.deepcopy(container['securityContext']),
                'resources':{'requests':{'cpu':'25m','memory':'32Mi'},'limits':{'cpu':'250m','memory':'128Mi'}},
                'readinessProbe':{'tcpSocket':{'port':8088}},'volumeMounts':[{'name':'code','mountPath':'/code','readOnly':True}]}],
            'volumes':[{'name':'code','configMap':{'name':relay_code}}]}}}})
    documents.append({'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'entra-auth-egress','namespace':NS},'spec':{
        'podSelector':{'matchLabels':{'app':'entra-auth-egress'}},'policyTypes':['Ingress','Egress'],
        'ingress':[{'from':[{'podSelector':{'matchLabels':{'app':'hermes-pilot'}}}],'ports':[{'port':8088,'protocol':'TCP'}]}],
        'egress':[dns,{'to':[{'ipBlock':{'cidr':'0.0.0.0/0','except':['0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8',
            '169.254.0.0/16','172.16.0.0/12','192.168.0.0/16','224.0.0.0/4','240.0.0.0/4']}}],'ports':[{'port':443,'protocol':'TCP'}]}]}})
    quota=next(d for d in documents if d['kind']=='ResourceQuota')
    quota['spec']['hard']['pods']='4';quota['spec']['hard']['requests.memory']='7Gi';quota['spec']['hard']['limits.memory']='13Gi'
    return {'documents':documents,'deployment':deployment,'job':job,'prefix':PREFIX,'namespace':NS,'source_sha256':digest}


def ingress_route(resolver):
    return '''    location = /entra-test { return 302 /entra-test/; }
    location ^~ /entra-test/ {
      resolver '''+resolver+''' valid=10s ipv6=off;
      set $entra_test http://hermes-pilot.arcia-entra-test.svc.cluster.local:9119;
      rewrite ^/entra-test/(.*)$ /$1 break;
      proxy_pass $entra_test;
      proxy_http_version 1.1;
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-Proto https;
      proxy_set_header X-Forwarded-Prefix /entra-test;
      proxy_set_header X-Forwarded-For $remote_addr;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection $connection_upgrade;
      proxy_buffering off;
      proxy_read_timeout 600s;
    }
'''
