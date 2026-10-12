"""Render pinned tools for the Hermes instance in K3s; no local installer."""
import hashlib
import json
import yaml
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
NS='arcia-hermes'


def settings():
    return {'mcp_servers':{'arcia_context7':{'command':'/opt/arcia-tools/bin/context7','args':[],
        'connect_timeout':30,'timeout':60,'env':{'DISABLE_TELEMETRY':'1',
            'CONTEXT7_API_URL':'http://context7-docs.arcia-hermes.svc.cluster.local:8080/api'}}},
        'skills':{'external_dirs':['/opt/arcia-tools/skills'],'project_discovery':False}}


def augment(docs):
    """Canonical render, including tools, survives TLS rotation and reapplication."""
    value=payload()
    cm=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config')
    configured=yaml.safe_load(cm['data']['config.yaml']);configured.update(settings())
    cm['data']['config.yaml']=yaml.safe_dump(configured,sort_keys=False)
    deployment=next(d for d in docs if d['kind']=='Deployment')
    template=deployment['spec']['template'];spec=template['spec'];container=spec['containers'][0]
    template['metadata']['annotations'].update({'arcia.io/tools-sha256':value['catalog_sha256'],
        'arcia.io/config-sha256':hashlib.sha256(cm['data']['config.yaml'].encode()).hexdigest()})
    container['volumeMounts'].append({'name':'tools','mountPath':'/opt/arcia-tools','readOnly':True})
    container['env'].extend([{'name':'PATH','value':'/opt/arcia-tools/bin:/opt/arcia-tools/python/bin:/opt/hermes/.venv/bin:/usr/local/bin:/usr/bin:/bin'},
        {'name':'RTK_TELEMETRY_DISABLED','value':'1'}])
    spec['volumes'].append({'name':'tools','persistentVolumeClaim':{'claimName':'hermes-tools','readOnly':True}})
    docs.extend(d for d in value['documents'] if d['kind']!='Job')


def payload():
    tools=json.loads((ROOT/'builder/tools.lock.json').read_text(encoding='utf-8'))['tools']
    catalog=json.loads((ROOT/'builder/catalog.lock.json').read_text(encoding='utf-8'))
    skills={};hashes={}
    for relative, expected in catalog['files'].items():
        source=ROOT/relative
        if source.is_symlink() or not source.resolve().is_relative_to((ROOT/'deploy/hermes/skills').resolve()):
            raise ValueError('HERMES_CATALOG_SCOPE')
        raw=source.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected: raise ValueError('HERMES_SKILL_HASH_MISMATCH')
        key=str(source.relative_to(ROOT/'deploy/hermes/skills')).replace('\\','/')
        skills[key]=raw.decode();hashes[key]=expected
    data={'package.json':(ROOT/'builder/npm/package.json').read_text(encoding='utf-8'),
        'package-lock.json':(ROOT/'builder/npm/package-lock.json').read_text(encoding='utf-8'),
        'requirements.lock.txt':(ROOT/'builder/requirements-tools.lock.txt').read_text(encoding='utf-8'),
        'installer.py':(ROOT/'scripts/install_hermes_tools.py').read_text(encoding='utf-8'),
        'AGENTS.md':(ROOT/'AGENTS.md').read_text(encoding='utf-8'),'role.md':(ROOT/'builder/role.md').read_text(encoding='utf-8')}
    digest=hashlib.sha256(json.dumps({'data':data,'skills':skills,'tools':tools},sort_keys=True).encode()).hexdigest()
    data['catalog.json']=json.dumps({'skills':skills,'skill_hashes':hashes,'tools':tools,'catalog_sha256':digest})
    lock=json.loads((ROOT/'versions.lock.yaml').read_text(encoding='utf-8'))
    return {'catalog_sha256':digest,'documents':documents(lock,data,digest),'config_append':yaml.safe_dump(settings(),sort_keys=False),
        'expected_skills':list(catalog['sources']),'verify_source':(ROOT/'scripts/probe_hermes_tools.py').read_text(encoding='utf-8')}


def documents(lock,data,digest):
    image=lock['components']['hermes']['image']
    security={'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}}
    context={'runAsNonRoot':True,'runAsUser':10000,'runAsGroup':10000,'fsGroup':10000,'seccompProfile':{'type':'RuntimeDefault'}}
    def resource(kind,name,spec):
        return {'apiVersion':'networking.k8s.io/v1' if kind=='NetworkPolicy' else ('apps/v1' if kind=='Deployment' else ('batch/v1' if kind=='Job' else 'v1')),
            'kind':kind,'metadata':{'name':name,'namespace':NS},'spec':spec}
    dns={'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},'podSelector':{'matchLabels':{'k8s-app':'kube-dns'}}}],
        'ports':[{'port':53,'protocol':'UDP'},{'port':53,'protocol':'TCP'}]}
    public={'to':[{'ipBlock':{'cidr':'0.0.0.0/0','except':['0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8','169.254.0.0/16','172.16.0.0/12','192.168.0.0/16','224.0.0.0/4','240.0.0.0/4']}}],
        'ports':[{'port':443,'protocol':'TCP'}]}
    cm={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'hermes-tools-input','namespace':NS},'data':data}
    proxy_cm={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'context7-relay-code','namespace':NS},
        'data':{'relay.py':(ROOT/'scripts/context7_egress.py').read_text(encoding='utf-8')}}
    job=resource('Job','hermes-tools-install-'+digest[:12],{'backoffLimit':0,'activeDeadlineSeconds':1200,
        'template':{'metadata':{'labels':{'app':'hermes-tools-installer'}},'spec':{
            'automountServiceAccountToken':False,'restartPolicy':'Never','securityContext':context,
            'containers':[{'name':'install','image':image,'command':['/opt/hermes/.venv/bin/python','/input/installer.py'],
                'env':[{'name':'HOME','value':'/tmp'},{'name':'DISABLE_TELEMETRY','value':'1'},
                    {'name':'NPM_CONFIG_CACHE','value':'/tmp/npm-cache'},{'name':'PIP_CACHE_DIR','value':'/tmp/pip-cache'}],
                'securityContext':security,'resources':{'requests':{'cpu':'500m','memory':'512Mi'},'limits':{'cpu':'2000m','memory':'2Gi'}},
                'volumeMounts':[{'name':'tools','mountPath':'/opt/arcia-tools'},{'name':'input','mountPath':'/input','readOnly':True},{'name':'tmp','mountPath':'/tmp'}]}],
            'volumes':[{'name':'tools','persistentVolumeClaim':{'claimName':'hermes-tools'}},
                {'name':'input','configMap':{'name':'hermes-tools-input'}},{'name':'tmp','emptyDir':{'sizeLimit':'4Gi'}}]}}})
    relay=resource('Deployment','context7-docs',{'replicas':1,'selector':{'matchLabels':{'app':'context7-docs'}},
        'template':{'metadata':{'labels':{'app':'context7-docs'},'annotations':{'arcia.io/code-sha256':hashlib.sha256(proxy_cm['data']['relay.py'].encode()).hexdigest()}},
            'spec':{'automountServiceAccountToken':False,'securityContext':context,
                'containers':[{'name':'relay','image':image,'command':['/opt/hermes/.venv/bin/python','/code/relay.py'],
                    'env':[{'name':'PYTHONDONTWRITEBYTECODE','value':'1'}], 'securityContext':security,
                    'resources':{'requests':{'cpu':'50m','memory':'64Mi'},'limits':{'cpu':'500m','memory':'256Mi'}},
                    'readinessProbe':{'httpGet':{'path':'/health','port':8080}},
                    'volumeMounts':[{'name':'code','mountPath':'/code','readOnly':True}]}],
                'volumes':[{'name':'code','configMap':{'name':'context7-relay-code'}}]}}})
    return [resource('PersistentVolumeClaim','hermes-tools',{'storageClassName':'arcia-vsphere','accessModes':['ReadWriteOncePod'],
        'resources':{'requests':{'storage':'10Gi'}}}),cm,proxy_cm,
        resource('Service','context7-docs',{'selector':{'app':'context7-docs'},'ports':[{'port':8080,'targetPort':8080}]}),
        resource('NetworkPolicy','hermes-tools-install-egress',{'podSelector':{'matchLabels':{'app':'hermes-tools-installer'}},'policyTypes':['Egress'],'egress':[dns,public]}),
        resource('NetworkPolicy','context7-docs-only',{'podSelector':{'matchLabels':{'app':'context7-docs'}},'policyTypes':['Ingress','Egress'],
            'ingress':[{'from':[{'podSelector':{'matchLabels':{'app':'hermes-pilot'}}}],'ports':[{'port':8080,'protocol':'TCP'}]}],'egress':[dns,public]}),
        resource('NetworkPolicy','hermes-internal-docs-only',{'podSelector':{'matchLabels':{'app':'hermes-pilot'}},'policyTypes':['Egress'],
            'egress':[dns,{'to':[{'podSelector':{'matchLabels':{'app':'context7-docs'}}}],'ports':[{'port':8080,'protocol':'TCP'}]}]}),relay,job]
