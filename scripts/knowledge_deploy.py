"""Engineer render for local, private document retrieval qualification."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
NS='arcia-knowledge'

def payload():
    code={p.name:p.read_text(encoding='utf-8') for p in (ROOT/'services/knowledge').iterdir()
        if p.name in ('core.py','server.py','install.py','schema.sql','models.lock.json','requirements.lock.txt')}
    digest=hashlib.sha256(json.dumps(code,sort_keys=True).encode()).hexdigest()
    image=json.loads((ROOT/'versions.lock.yaml').read_text(encoding='utf-8'))['components']['hermes']['image']
    security={'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}}
    context={'runAsNonRoot':True,'runAsUser':10000,'runAsGroup':10000,'fsGroup':10000,'seccompProfile':{'type':'RuntimeDefault'}}
    def resource(kind,name,spec):
        api={'NetworkPolicy':'networking.k8s.io/v1','Deployment':'apps/v1','Job':'batch/v1'}.get(kind,'v1')
        return {'apiVersion':api,'kind':kind,'metadata':{'name':name,'namespace':NS},'spec':spec}
    dns={'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},
        'podSelector':{'matchLabels':{'k8s-app':'kube-dns'}}}],'ports':[{'port':53,'protocol':'UDP'},{'port':53,'protocol':'TCP'}]}
    public={'to':[{'ipBlock':{'cidr':'0.0.0.0/0','except':['0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8',
        '169.254.0.0/16','172.16.0.0/12','192.168.0.0/16','224.0.0.0/4','240.0.0.0/4']}}],'ports':[{'port':443,'protocol':'TCP'}]}
    def pod(installer):
        return {'automountServiceAccountToken':False,'restartPolicy':'Never' if installer else 'Always','securityContext':context,
            'containers':[{'name':'knowledge','image':image,'securityContext':security,
                'command':['/opt/hermes/.venv/bin/python','/code/install.py'] if installer else ['/runtime/python/bin/python','/code/server.py'],
                'env':[{'name':'HOME','value':'/tmp'},{'name':'PYTHONDONTWRITEBYTECODE','value':'1'},
                    {'name':'HF_HUB_DISABLE_TELEMETRY','value':'1'},{'name':'PIP_NO_CACHE_DIR','value':'1'}],
                'resources':{'requests':{'cpu':'500m','memory':'1Gi'},'limits':{'cpu':'2000m','memory':'4Gi' if installer else '8Gi'}},
                **({} if installer else {'startupProbe':{'httpGet':{'path':'/health','port':8090},'failureThreshold':120,'periodSeconds':5},
                    'readinessProbe':{'httpGet':{'path':'/health','port':8090},'periodSeconds':10}}),
                'volumeMounts':[{'name':'runtime','mountPath':'/runtime','readOnly':not installer},
                    {'name':'code','mountPath':'/code','readOnly':True},{'name':'tmp','mountPath':'/tmp'}]+([] if installer else [
                        {'name':'data','mountPath':'/data'},{'name':'credentials','mountPath':'/credentials','readOnly':True}])}],
            'volumes':[{'name':'runtime','persistentVolumeClaim':{'claimName':'knowledge-runtime','readOnly':not installer}},
                {'name':'code','configMap':{'name':'knowledge-code'}},{'name':'tmp','emptyDir':{'sizeLimit':'4Gi'}}]+([] if installer else [
                    {'name':'data','persistentVolumeClaim':{'claimName':'knowledge-data'}},
                    {'name':'credentials','secret':{'secretName':'knowledge-credentials','defaultMode':288}}])}
    docs=[{'apiVersion':'v1','kind':'Namespace','metadata':{'name':NS,'labels':{'pod-security.kubernetes.io/enforce':'restricted'}}},
        {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'knowledge-code','namespace':NS},'data':code},
        resource('ResourceQuota','qualification-bounds',{'hard':{'pods':'2','requests.cpu':'4','requests.memory':'8Gi',
            'limits.cpu':'6','limits.memory':'16Gi','persistentvolumeclaims':'2','requests.storage':'30Gi'}}),
        resource('NetworkPolicy','deny-all',{'podSelector':{},'policyTypes':['Ingress','Egress']}),
        resource('NetworkPolicy','installer-public-only',{'podSelector':{'matchLabels':{'app':'knowledge-installer'}},
            'policyTypes':['Egress'],'egress':[dns,public]}),
        resource('NetworkPolicy','knowledge-private-only',{'podSelector':{'matchLabels':{'app':'knowledge'}},'policyTypes':['Ingress','Egress'],
            'ingress':[{'from':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'arcia-hermes'}},
                'podSelector':{'matchLabels':{'app':'hermes-pilot'}}}],'ports':[{'port':8090,'protocol':'TCP'}]}],
            'egress':[dns,{'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'arcia-data'}},
                'podSelector':{'matchLabels':{'cnpg.io/cluster':'arcia-postgres'}}}],'ports':[{'port':5432,'protocol':'TCP'}]}]}),
        resource('Service','knowledge',{'selector':{'app':'knowledge'},'ports':[{'port':8090,'targetPort':8090}]})]
    for name,size in [('knowledge-runtime','10Gi'),('knowledge-data','20Gi')]:
        docs.append(resource('PersistentVolumeClaim',name,{'storageClassName':'arcia-vsphere','accessModes':['ReadWriteOncePod'],
            'resources':{'requests':{'storage':size}}}))
    job=resource('Job','knowledge-install-'+digest[:12],{'backoffLimit':0,'activeDeadlineSeconds':2400,
        'template':{'metadata':{'labels':{'app':'knowledge-installer'}},'spec':pod(True)}})
    deployment=resource('Deployment','knowledge',{'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':{'app':'knowledge'}},
        'template':{'metadata':{'labels':{'app':'knowledge'},'annotations':{'arcia.io/code-sha256':digest}},'spec':pod(False)}})
    postgres_policy={'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'knowledge-postgres','namespace':'arcia-data'},
        'spec':{'podSelector':{'matchLabels':{'cnpg.io/cluster':'arcia-postgres'}},'policyTypes':['Ingress'],
            'ingress':[{'from':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':NS}},
                'podSelector':{'matchLabels':{'app':'knowledge'}}}],'ports':[{'port':5432,'protocol':'TCP'}]}]}}
    return {'documents':docs,'job':job,'deployment':deployment,'postgres_policy':postgres_policy,
        'schema':code['schema.sql'],'digest':digest,'probe':(ROOT/'services/knowledge/probe.py').read_text(encoding='utf-8')}
