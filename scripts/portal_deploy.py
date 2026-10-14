"""Render fixed, dormant personal slots; the portal may bind and scale only these."""
import base64
import copy
import hashlib
import ipaddress
import json
import re
from pathlib import Path
import yaml
import kubernetes_apps
import hermes_tools
import identity_deploy

ROOT=Path(__file__).resolve().parents[1]
NS='arcia-access'


def payload(lock,config,pilot,operation,dns_ip,https_ip):
    count=config.get('identity',{}).get('personal_slots',lock.get('identity',{}).get('personal_slots',8))
    if not isinstance(count,int) or not 1<=count<=32:raise ValueError('PERSONAL_RUNTIME_CAPACITY_INVALID')
    image=lock['components']['hermes']['image'];slots=[];documents=[]
    tools=hermes_tools.payload();job=next(d for d in tools['documents'] if d['kind']=='Job')
    dummy={'username':'disabled','password':'unused-synthetic-render-fixture','password_salt':base64.b64encode(b'synthetic-salt16').decode(),'session_secret':'unused'}
    for index in range(1,count+1):
        slot='p'+str(index).zfill(2);ns='arcia-user-'+slot;prefix='/u/'+slot
        docs=json.loads(json.dumps(kubernetes_apps.hermes(lock,config,dummy)).replace('arcia-hermes',ns))
        docs=[d for d in docs if not(d['kind']=='Secret' or (d['kind']=='ConfigMap' and d.get('immutable') and d['metadata']['name'].startswith('hermes-config-')))]
        next(d for d in docs if d['kind']=='Namespace')['metadata']['labels']['arcia.io/personal-pool']='true'
        settings_doc=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config')
        settings=yaml.safe_load(settings_doc['data']['config.yaml'])
        settings['dashboard']['public_url']+=prefix
        settings['platform']['personal_workspace']=True
        settings_doc['data']['config.yaml']=yaml.safe_dump(settings,sort_keys=False)
        digest=hashlib.sha256(settings_doc['data']['config.yaml'].encode()).hexdigest();name='hermes-config-'+digest[:16]
        docs.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':name,'namespace':ns},'immutable':True,'data':dict(settings_doc['data'])})
        for doc in docs:
            if doc['kind']=='Deployment':doc['spec']['replicas']=0
        deployment=next(d for d in docs if d['kind']=='Deployment' and d['metadata']['name']=='hermes-pilot')
        deployment['spec']['template']['metadata']['annotations']['arcia.io/config-sha256']=digest
        spec=deployment['spec']['template']['spec'];container=spec['containers'][0]
        container['envFrom']=[{'secretRef':{'name':'arcia-oidc-runtime'}}]
        for env in container['env']:
            if env['name']=='HERMES_DASHBOARD_PUBLIC_URL':env['value']+=prefix
        next(v for v in spec['volumes'] if v['name']=='config')['configMap']['name']=name
        spec.update(dnsPolicy='None',dnsConfig={'nameservers':[dns_ip],'searches':[ns+'.svc.cluster.local','svc.cluster.local','cluster.local'],
            'options':[{'name':'ndots','value':'1'}]})
        install=json.loads(json.dumps(job).replace('arcia-hermes',ns));install['spec']['suspend']=True
        docs.append(install)
        slots.append({'id':slot,'namespace':ns,'prefix':prefix,'job':install['metadata']['name']})
        docs.extend([
            {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'slot-binding','namespace':ns},'data':{'binding.json':'{}'}},
            {'apiVersion':'v1','kind':'Secret','metadata':{'name':'arcia-oidc-runtime','namespace':ns},'type':'Opaque',
                'stringData':{'ARCIA_IDENTITY_ISSUER':'https://'+config['network']['public_hostname']+'/identity/realms/arcia',
                    'ARCIA_IDENTITY_CLIENT_ID':'arcia-'+slot,'ARCIA_IDENTITY_OWNER_SUBJECT':''}},
            identity_deploy.runtime_policy(config, https_ip, ns),
            {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'personal-readiness','namespace':ns},
                'spec':{'podSelector':{'matchLabels':{'app':'hermes-pilot'}},'policyTypes':['Ingress'],
                    'ingress':[{'from':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':NS}},
                        'podSelector':{'matchLabels':{'app':'arcia-portal'}}}],'ports':[{'port':9119,'protocol':'TCP'}]}]}},
            {'apiVersion':'rbac.authorization.k8s.io/v1','kind':'Role','metadata':{'name':'personal-slot-controller','namespace':ns},
                'rules':[{'apiGroups':[''],'resources':['configmaps'],'resourceNames':['slot-binding'],'verbs':['get','update']},
                    {'apiGroups':[''],'resources':['secrets'],'resourceNames':['arcia-oidc-runtime'],'verbs':['get','patch']},
                    {'apiGroups':['batch'],'resources':['jobs'],'resourceNames':[install['metadata']['name']],'verbs':['get','patch']},
                    {'apiGroups':['apps'],'resources':['deployments/scale'],'resourceNames':['hermes-pilot','context7-docs'],'verbs':['get','patch']}]},
            {'apiVersion':'rbac.authorization.k8s.io/v1','kind':'RoleBinding','metadata':{'name':'personal-slot-controller','namespace':ns},
                'roleRef':{'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'personal-slot-controller'},
                'subjects':[{'kind':'ServiceAccount','name':'arcia-portal','namespace':NS}]}])
        documents.extend(docs)
    source=portal_source()
    digest=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()
    portal_config={'hostname':config['network']['public_hostname'],'operation_id':operation,'slots':slots,
        'identity_internal':'http://keycloak.arcia-identity.svc.cluster.local:8080/identity/realms/arcia',
        'personal_key_configuration_enabled':True}
    api_ip=str(ipaddress.ip_network(config['network']['service_cidr']).network_address+1)
    dns={'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},'podSelector':{'matchLabels':{'k8s-app':'kube-dns'}}}],
        'ports':[{'port':53,'protocol':protocol} for protocol in ('UDP','TCP')]}
    namespace_peer=lambda namespace,app:{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':namespace}},'podSelector':{'matchLabels':{'app':app}}}
    pod={'automountServiceAccountToken':True,'serviceAccountName':'arcia-portal',
        'securityContext':{'runAsNonRoot':True,'runAsUser':10000,'runAsGroup':10000,'fsGroup':10000,'seccompProfile':{'type':'RuntimeDefault'}},
        'containers':[{'name':'portal','image':image,'command':['/opt/hermes/.venv/bin/python','/code/portal.py'],
            'env':[{'name':'PYTHONDONTWRITEBYTECODE','value':'1'},{'name':'DISABLE_TELEMETRY','value':'1'}],
            'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},
            'ports':[{'containerPort':8080}],
            'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'500m','memory':'512Mi'}},
            'readinessProbe':{'httpGet':{'path':'/portal/health','port':8080},'periodSeconds':5},
            'volumeMounts':[{'name':'code','mountPath':'/code','readOnly':True},{'name':'config','mountPath':'/config','readOnly':True},
                {'name':'credentials','mountPath':'/credentials','readOnly':True},{'name':'tmp','mountPath':'/tmp'}]}],
        'volumes':[{'name':'code','configMap':{'name':'portal-code-'+digest[:16]}},{'name':'config','configMap':{'name':'portal-config'}},
            {'name':'credentials','secret':{'secretName':'portal-hmac','defaultMode':288}},{'name':'tmp','emptyDir':{'sizeLimit':'64Mi'}}]}
    documents.extend([kubernetes_apps.namespace(NS),kubernetes_apps.deny_all(NS),
        kubernetes_apps.quota(NS,{'pods':'2','requests.cpu':'1','requests.memory':'1Gi','limits.cpu':'2','limits.memory':'2Gi','persistentvolumeclaims':'0'}),
        {'apiVersion':'v1','kind':'ServiceAccount','metadata':{'name':'arcia-portal','namespace':NS}},
        {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'portal-code-'+digest[:16],'namespace':NS},'immutable':True,'data':source},
        {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'portal-config','namespace':NS},'data':{'portal.json':json.dumps(portal_config,sort_keys=True)}},
        {'apiVersion':'v1','kind':'Service','metadata':{'name':'arcia-portal','namespace':NS},'spec':{'selector':{'app':'arcia-portal'},'ports':[{'port':8080,'targetPort':8080}]}},
        {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'portal-controlled-only','namespace':NS},
            'spec':{'podSelector':{'matchLabels':{'app':'arcia-portal'}},'policyTypes':['Ingress','Egress'],
                'ingress':[{'from':[namespace_peer('arcia-ingress','pilot-https')],'ports':[{'port':8080,'protocol':'TCP'}]}],
                'egress':[dns,{'to':[namespace_peer('arcia-identity','keycloak')],'ports':[{'port':8080,'protocol':'TCP'}]},
                    {'to':[{'namespaceSelector':{'matchLabels':{'arcia.io/personal-pool':'true'}},'podSelector':{'matchLabels':{'app':'hermes-pilot'}}}],
                        'ports':[{'port':9119,'protocol':'TCP'}]},
                    {'to':[{'ipBlock':{'cidr':api_ip+'/32'}}],'ports':[{'port':443,'protocol':'TCP'}]},
                    {'to':[{'ipBlock':{'cidr':n['address']+'/32'}} for n in config['nodes']],'ports':[{'port':6443,'protocol':'TCP'}]}]}},
        {'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':'arcia-portal','namespace':NS},'spec':{'replicas':1,
            'strategy':{'type':'Recreate'},'selector':{'matchLabels':{'app':'arcia-portal'}},
            'template':{'metadata':{'labels':{'app':'arcia-portal'},'annotations':{'arcia.io/source-sha256':digest,
                'arcia.io/config-sha256':hashlib.sha256(json.dumps(portal_config,sort_keys=True).encode()).hexdigest()}},'spec':pod}}}])
    documents.extend(key_resources(slots))
    mount_key_encryption(pod)
    return {'documents':documents,'slots':slots,'ingress':kubernetes_apps.ingress(lock,config,pilot),
        'realm_source':(ROOT/'services/identity/realm.py').read_text(encoding='utf-8')}


def portal_source():
    result={name:(ROOT/'services/identity'/name).read_text(encoding='utf-8')
            for name in ('portal.py','slots.py','keys_page.py')}
    result['user_keys.py']=(ROOT/'services/routing/user_keys.py').read_text(encoding='utf-8')
    return result


def mount_key_encryption(pod):
    pod['volumes'].append({'name':'key-encryption','secret':{'secretName':'portal-key-encryption','defaultMode':288}})
    pod['containers'][0]['volumeMounts'].append({'name':'key-encryption','mountPath':'/key-encryption','readOnly':True})


def key_resources(slots):
    documents=[]
    for slot in slots:
        ns=slot['namespace']
        if ns!='arcia-user-'+slot['id'] or not re.fullmatch(r'p(?:0[1-9]|[12][0-9]|3[0-2])',slot['id']):
            raise ValueError('KEY_CONFIG_FIXED_SLOT_REQUIRED')
        documents.extend([
            {'apiVersion':'v1','kind':'Secret','metadata':{'name':'personal-provider-keys','namespace':ns},'type':'Opaque','data':{}},
            {'apiVersion':'rbac.authorization.k8s.io/v1','kind':'Role','metadata':{'name':'personal-key-controller','namespace':ns},
             'rules':[{'apiGroups':[''],'resources':['secrets'],'resourceNames':['personal-provider-keys'],'verbs':['get','patch']}]},
            {'apiVersion':'rbac.authorization.k8s.io/v1','kind':'RoleBinding','metadata':{'name':'personal-key-controller','namespace':ns},
             'roleRef':{'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'personal-key-controller'},
             'subjects':[{'kind':'ServiceAccount','name':'arcia-portal','namespace':NS}]}])
    return documents


def key_payload(lock,settings):
    """Update only the existing portal; no runtime, ingress or route modification."""
    source=portal_source();digest=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()
    settings={**settings,'personal_key_configuration_enabled':True}
    return {'documents':key_resources(settings['slots'])+[
        {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'portal-code-'+digest[:16],'namespace':NS},'immutable':True,'data':source},
        {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'portal-config','namespace':NS},'data':{'portal.json':json.dumps(settings,sort_keys=True)}}],
        'code_name':'portal-code-'+digest[:16],'source_sha256':digest,
        'config_sha256':hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest(),
        'expected_image':lock['components']['hermes']['image']}
