"""Pinned Presidio boundary, isolated free-only cloud relay and private DNS."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
NS='arcia-privacy'

def payload():
    names=('core.py','server.py','install.py','private_dns.py','wire.py','egress.py','models.lock.json','requirements.lock.txt')
    code={name:(ROOT/'services/privacy'/name).read_text(encoding='utf-8') for name in names}
    digest=hashlib.sha256(json.dumps(code,sort_keys=True).encode()).hexdigest()
    image=json.loads((ROOT/'versions.lock.yaml').read_text(encoding='utf-8'))['components']['hermes']['image']
    context={'runAsNonRoot':True,'runAsUser':10000,'runAsGroup':10000,'fsGroup':10000,'seccompProfile':{'type':'RuntimeDefault'}}
    security={'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}}
    def resource(kind,name,spec):
        api={'NetworkPolicy':'networking.k8s.io/v1','Deployment':'apps/v1','Job':'batch/v1'}.get(kind,'v1')
        return {'apiVersion':api,'kind':kind,'metadata':{'name':name,'namespace':NS},'spec':spec}
    def pod(installer):
        return {'automountServiceAccountToken':False,'restartPolicy':'Never' if installer else 'Always','securityContext':context,
            'containers':[{'name':'privacy','image':image,'securityContext':security,
                'command':['/opt/hermes/.venv/bin/python','/code/install.py'] if installer else ['/runtime/python/bin/python','/code/server.py'],
                'env':[{'name':'HOME','value':'/tmp'},{'name':'PYTHONDONTWRITEBYTECODE','value':'1'},{'name':'PIP_NO_CACHE_DIR','value':'1'},
                    {'name':'OMP_NUM_THREADS','value':'2'},{'name':'OPENBLAS_NUM_THREADS','value':'2'}],
                'resources':{'requests':{'cpu':'250m','memory':'512Mi'},'limits':{'cpu':'2000m','memory':'3Gi'}},
                **({} if installer else {'startupProbe':{'httpGet':{'path':'/health','port':8091},'failureThreshold':90,'periodSeconds':5},
                    'readinessProbe':{'httpGet':{'path':'/health','port':8091}}}),
                'volumeMounts':[{'name':'runtime','mountPath':'/runtime','readOnly':not installer},
                    {'name':'code','mountPath':'/code','readOnly':True},{'name':'tmp','mountPath':'/tmp'}]+([] if installer else [
                        {'name':'credentials','mountPath':'/credentials','readOnly':True}])}],
            'volumes':[{'name':'runtime','persistentVolumeClaim':{'claimName':'privacy-runtime','readOnly':not installer}},
                {'name':'code','configMap':{'name':'privacy-code'}},{'name':'tmp','emptyDir':{'sizeLimit':'2Gi'}}]+([] if installer else [
                    {'name':'credentials','secret':{'secretName':'privacy-policy','defaultMode':288}}])}
    dns={'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},'podSelector':{'matchLabels':{'k8s-app':'kube-dns'}}}],
        'ports':[{'port':53,'protocol':'UDP'},{'port':53,'protocol':'TCP'}]}
    public={'to':[{'ipBlock':{'cidr':'0.0.0.0/0','except':['0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8',
        '169.254.0.0/16','172.16.0.0/12','192.168.0.0/16','224.0.0.0/4','240.0.0.0/4']}}],'ports':[{'port':443,'protocol':'TCP'}]}
    hermes={'from':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'arcia-hermes'}},'podSelector':{'matchLabels':{'app':'hermes-pilot'}}}]}
    documents=[{'apiVersion':'v1','kind':'Namespace','metadata':{'name':NS,'labels':{'pod-security.kubernetes.io/enforce':'restricted'}}},
        {'apiVersion':'v1','kind':'Service','metadata':{'name':'context7-docs','namespace':'arcia-hermes'},'spec':{'selector':{'app':'context7-docs'},'ports':[{'port':8080,'targetPort':8080}]}},
        {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'privacy-code','namespace':NS},'data':code},
        resource('ResourceQuota','qualification-bounds',{'hard':{'pods':'4','requests.cpu':'3','requests.memory':'4Gi','limits.cpu':'5','limits.memory':'7Gi',
            'persistentvolumeclaims':'1','requests.storage':'5Gi'}}),
        resource('PersistentVolumeClaim','privacy-runtime',{'storageClassName':'arcia-vsphere','accessModes':['ReadWriteOncePod'],'resources':{'requests':{'storage':'5Gi'}}}),
        resource('NetworkPolicy','deny-all',{'podSelector':{},'policyTypes':['Ingress','Egress']}),
        resource('NetworkPolicy','installer-only-public',{'podSelector':{'matchLabels':{'app':'privacy-installer'}},'policyTypes':['Egress'],'egress':[dns,public]}),
        resource('NetworkPolicy','local-sanitizer-only',{'podSelector':{'matchLabels':{'app':'privacy'}},'policyTypes':['Ingress','Egress'],
            'ingress':[{**hermes,'ports':[{'port':8091,'protocol':'TCP'}]}],'egress':[dns,{
                'to':[{'podSelector':{'matchLabels':{'app':'cloud-egress'}}}],'ports':[{'port':8092,'protocol':'TCP'}]}]}),
        resource('NetworkPolicy','attested-cloud-only',{'podSelector':{'matchLabels':{'app':'cloud-egress'}},'policyTypes':['Ingress','Egress'],
            'ingress':[{'from':[{'podSelector':{'matchLabels':{'app':'privacy'}}}],'ports':[{'port':8092,'protocol':'TCP'}]}],'egress':[dns,public]}),
        resource('NetworkPolicy','static-dns-only',{'podSelector':{'matchLabels':{'app':'private-dns'}},'policyTypes':['Ingress','Egress'],
            'ingress':[{**hermes,'ports':[{'port':5353,'protocol':'UDP'},{'port':5353,'protocol':'TCP'}]}],'egress':[]}),
        resource('Service','privacy',{'selector':{'app':'privacy'},'ports':[{'port':8091,'targetPort':8091}]}),
        resource('Service','cloud-egress',{'selector':{'app':'cloud-egress'},'ports':[{'port':8092,'targetPort':8092}]}),
        resource('Service','private-dns',{'selector':{'app':'private-dns'},'ports':[{'name':'udp','protocol':'UDP','port':53,'targetPort':5353},
            {'name':'tcp','protocol':'TCP','port':53,'targetPort':5353}]})]
    job=resource('Job','privacy-install-'+digest[:12],{'backoffLimit':0,'activeDeadlineSeconds':1800,
        'template':{'metadata':{'labels':{'app':'privacy-installer'}},'spec':pod(True)}})
    deployment=resource('Deployment','privacy',{'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':{'app':'privacy'}},
        'template':{'metadata':{'labels':{'app':'privacy'},'annotations':{'arcia.io/code-sha256':digest}},'spec':pod(False)}})
    dns_deployment=resource('Deployment','private-dns',{'replicas':1,'selector':{'matchLabels':{'app':'private-dns'}},
        'template':{'metadata':{'labels':{'app':'private-dns'},'annotations':{'arcia.io/code-sha256':digest}},'spec':{
            'automountServiceAccountToken':False,'securityContext':context,'containers':[{'name':'dns','image':image,'securityContext':security,
                'command':['/opt/hermes/.venv/bin/python','/code/private_dns.py'],
                'env':[{'name':'PYTHONDONTWRITEBYTECODE','value':'1'}],
                'resources':{'requests':{'cpu':'50m','memory':'64Mi'},'limits':{'cpu':'250m','memory':'128Mi'}},
                'readinessProbe':{'tcpSocket':{'port':5353}},
                'volumeMounts':[{'name':'code','mountPath':'/code','readOnly':True},{'name':'dns','mountPath':'/dns','readOnly':True}]}],
            'volumes':[{'name':'code','configMap':{'name':'privacy-code'}},{'name':'dns','configMap':{'name':'private-dns-records'}}]}}})
    egress=resource('Deployment','cloud-egress',{'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':{'app':'cloud-egress'}},
        'template':{'metadata':{'labels':{'app':'cloud-egress'},'annotations':{'arcia.io/code-sha256':digest}},'spec':{
            'automountServiceAccountToken':False,'securityContext':context,'containers':[{'name':'egress','image':image,'securityContext':security,
                'command':['/opt/hermes/.venv/bin/python','/code/egress.py'],'env':[{'name':'PYTHONDONTWRITEBYTECODE','value':'1'}],
                'resources':{'requests':{'cpu':'50m','memory':'64Mi'},'limits':{'cpu':'250m','memory':'128Mi'}},
                'readinessProbe':{'httpGet':{'path':'/health','port':8092}},'volumeMounts':[
                    {'name':'code','mountPath':'/code','readOnly':True},{'name':'credentials','mountPath':'/credentials','readOnly':True}]}],
            'volumes':[{'name':'code','configMap':{'name':'privacy-code'}},{'name':'credentials','secret':{'secretName':'cloud-provider','defaultMode':288}}]}}})
    return {'documents':documents,'job':job,'deployment':deployment,'dns_deployment':dns_deployment,'egress_deployment':egress,'digest':digest,
            'probe':(ROOT/'services/privacy/probe.py').read_text(encoding='utf-8')}


def augment(docs):
    """Canonical Hermes binding. Private DNS address resolved by the engineer worker."""
    import yaml
    cm=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config')
    settings=yaml.safe_load(cm['data']['config.yaml'])
    settings['model']={'default':'openrouter/free','provider':'custom','base_url':'http://privacy.arcia-privacy.svc.cluster.local:8091/v1'}
    settings['auxiliary']={k:{'provider':'main','model':'openrouter/free','base_url':'http://privacy.arcia-privacy.svc.cluster.local:8091/v1'} for k in ('compression','vision')}
    settings['platform'].update(cloud_calls_enabled=True,cloud_classification='synthetic',paid_llm_enabled=False)
    cm['data']['config.yaml']=yaml.safe_dump(settings,sort_keys=False)
    deployment=next(d for d in docs if d['kind']=='Deployment' and d['metadata']['name']=='hermes-pilot')
    spec=deployment['spec']['template']['spec'];container=spec['containers'][0]
    container['env'].extend([{'name':'OPENAI_API_KEY','valueFrom':{'secretKeyRef':{'name':'privacy-client','key':'token'}}},
        {'name':'OPENAI_BASE_URL','value':'http://privacy.arcia-privacy.svc.cluster.local:8091/v1'}])
    deployment['spec']['template']['metadata']['annotations']['arcia.io/privacy-boundary']='required'
    deployment['spec']['template']['metadata']['annotations']['arcia.io/config-sha256']=hashlib.sha256(cm['data']['config.yaml'].encode()).hexdigest()


def hermes_policy():
    return {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'hermes-internal-docs-only','namespace':'arcia-hermes'},'spec':{
        'podSelector':{'matchLabels':{'app':'hermes-pilot'}},'policyTypes':['Egress'],'egress':[
            {'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':NS}},'podSelector':{'matchLabels':{'app':'private-dns'}}}],
                'ports':[{'port':5353,'protocol':'TCP'},{'port':5353,'protocol':'UDP'}]},
            {'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':NS}},'podSelector':{'matchLabels':{'app':'privacy'}}}],
                'ports':[{'port':8091,'protocol':'TCP'}]},
            {'to':[{'podSelector':{'matchLabels':{'app':'context7-docs'}}}],'ports':[{'port':8080,'protocol':'TCP'}]}]}}
