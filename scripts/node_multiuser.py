"""Owned qualification runtimes; private credentials only through protected stdin."""
import base64
import hashlib
import json
import secrets
import subprocess
import time

FIRST='arcia-hermes';SECOND='arcia-hermes-qualification-b'

def kube(*args,document=None,input_text=None,timeout=90):
    result=subprocess.run(['/usr/local/bin/k3s','kubectl',*args],capture_output=True,
        input=json.dumps(document).encode() if document is not None else (input_text.encode() if input_text is not None else None),timeout=timeout)
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout.decode()

def owned(kind,name,ns,operation,optional=False):
    args=['get',kind,name,'--ignore-not-found','-o','json']
    if ns:args+=['-n',ns]
    raw=kube(*args)
    if not raw and optional:return None
    value=json.loads(raw)
    if value['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:raise ValueError('MULTIUSER_FOREIGN_RESOURCE')
    return value

def apply(documents,operation):
    for doc in documents:
        owned(doc['kind'],doc['metadata']['name'],doc['metadata'].get('namespace'),operation,True)
        doc['metadata'].setdefault('annotations',{})['arcia.io/operation-id']=operation
    kube('apply','--server-side','--field-manager=arcia-foundation','-f','-',document={'apiVersion':'v1','kind':'List','items':documents})

def secret(name,ns,operation):
    value=owned('Secret',name,ns,operation)
    return {k:base64.b64decode(v).decode() for k,v in value['data'].items()}

def save_secret(name,ns,data,operation):
    apply([{'apiVersion':'v1','kind':'Secret','metadata':{'name':name,'namespace':ns},'type':'Opaque','stringData':data}],operation)

def pod(ns):
    pods=json.loads(kube('get','pods','-n',ns,'-l','app=hermes-pilot','-o','json'))['items']
    active=[p for p in pods if not p['metadata'].get('deletionTimestamp') and p['status']['phase']=='Running']
    if len(active)!=1:raise ValueError('SINGLE_HERMES_OWNER_REQUIRED')
    return active[0]

def install(values):
    operation=values['operation_id'];owned('Deployment','hermes-pilot',FIRST,operation)
    # Create owned resource skeleton before tokens; never mount A's RWOP volumes.
    apply([d for d in values['documents'] if d['kind']!='Deployment'],operation)
    credentials=secret('knowledge-credentials','arcia-knowledge',operation)
    tokens=json.loads(credentials['tokens.json'])
    for identity in tokens.values():
        if identity.get('scope') in ('qualification-a','qualification-b'):
            identity['read_scopes']=[identity['scope'],'qualification-common']
    if not any(v.get('scope')=='qualification-common' and v.get('role')=='ingester' for v in tokens.values()):
        tokens[secrets.token_urlsafe(36)]={'scope':'qualification-common','role':'ingester'}
    credentials['tokens.json']=json.dumps(tokens);save_secret('knowledge-credentials','arcia-knowledge',credentials,operation)
    reader=next(k for k,v in tokens.items() if v.get('scope')=='qualification-b' and v.get('role')=='reader')
    save_secret('knowledge-reader',SECOND,{'token':reader},operation)
    privacy=secret('privacy-policy','arcia-privacy',operation);policy=json.loads(privacy['policy.json'])
    token=next((k for k,v in policy['tokens'].items() if v['scope']=='qualification-b'),None)
    if token is None:
        token=secrets.token_urlsafe(36);policy['tokens'][token]={'scope':'qualification-b','classification':'synthetic','identifiers':['Dossier Synthetique']}
    privacy['policy.json']=json.dumps(policy);save_secret('privacy-policy','arcia-privacy',privacy,operation)
    save_secret('privacy-client',SECOND,{'token':token},operation)
    # Explicit allowlists on service side; no cross-runtime network connectivity.
    for ns,name in [('arcia-knowledge','knowledge-private-only'),('arcia-privacy','local-sanitizer-only'),('arcia-privacy','static-dns-only')]:
        doc=owned('NetworkPolicy',name,ns,operation)
        for rule in doc['spec']['ingress']:
            peer={'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':SECOND}},'podSelector':{'matchLabels':{'app':'hermes-pilot'}}}
            if peer not in rule['from']:rule['from'].append(peer)
        doc.pop('status',None);doc['metadata']={k:doc['metadata'][k] for k in ('name','namespace','annotations')};apply([doc],operation)
    records_doc=owned('ConfigMap','private-dns-records','arcia-privacy',operation)
    records=json.loads(records_doc['data']['records.json'])
    records['context7-docs.'+SECOND+'.svc.cluster.local']=owned('Service','context7-docs',SECOND,operation)['spec']['clusterIP']
    apply([{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'private-dns-records','namespace':'arcia-privacy'},'data':{'records.json':json.dumps(records)}}],operation)
    kube('rollout','restart','deployment/private-dns','deployment/privacy','-n','arcia-privacy')
    for name in ('private-dns','privacy'):kube('rollout','status','deployment/'+name,'-n','arcia-privacy','--timeout=600s',timeout=620)
    kube('rollout','restart','deployment/knowledge','-n','arcia-knowledge')
    kube('rollout','status','deployment/knowledge','-n','arcia-knowledge','--timeout=600s',timeout=620)
    previous=owned('Deployment','hermes-pilot',SECOND,operation,True)
    if previous and previous['spec']['template']['metadata']['annotations'].get('arcia.io/tools-sha256')!=values['catalog_sha256']:
        kube('scale','deployment/hermes-pilot','-n',SECOND,'--replicas=0')
        kube('wait','pod','-l','app=hermes-pilot','-n',SECOND,'--for=delete','--timeout=150s',timeout=160)
    if not previous or previous['spec']['template']['metadata']['annotations'].get('arcia.io/tools-sha256')!=values['catalog_sha256']:
        job=values['job'];old=owned('Job',job['metadata']['name'],SECOND,operation,True)
        if old and old.get('status',{}).get('failed'):kube('delete','job',job['metadata']['name'],'-n',SECOND,'--wait=true')
        apply([job],operation)
        kube('wait','job/'+job['metadata']['name'],'-n',SECOND,'--for=condition=Complete','--timeout=1200s',timeout=1220)
        kube('delete','job',job['metadata']['name'],'-n',SECOND,'--wait=true')
    dns=owned('Service','private-dns','arcia-privacy',operation)['spec']['clusterIP']
    spec=values['deployment']['spec']['template']['spec']
    spec.update(dnsPolicy='None',dnsConfig={'nameservers':[dns],'searches':[SECOND+'.svc.cluster.local','svc.cluster.local','cluster.local'],'options':[{'name':'ndots','value':'1'}]})
    apply([values['deployment'] if d['metadata']['name']=='hermes-pilot' else d for d in values['documents'] if d['kind']=='Deployment'],operation)
    kube('rollout','status','deployment/hermes-pilot','-n',SECOND,'--timeout=600s',timeout=620)
    # Preserve TLS from the protected main identity; B only has a local password.
    apply(values['ingress'],operation)
    kube('rollout','status','daemonset/pilot-https','-n','arcia-ingress','--timeout=180s',timeout=200)
    return {'passed':True,'isolated_runtime_count':2,'shared_state_db':False,'central_sso_qualified':False}

def verify(values):
    operation=values['operation_id'];checks={}
    owned('Deployment','knowledge','arcia-knowledge',operation)
    pods=json.loads(kube('get','pods','-n','arcia-knowledge','-l','app=knowledge','-o','json'))['items']
    kp=next(p for p in pods if not p['metadata'].get('deletionTimestamp') and p['status']['phase']=='Running')
    result=json.loads(kube('exec',kp['metadata']['name'],'-n','arcia-knowledge','--','/runtime/python/bin/python','-c',values['knowledge_probe'],timeout=600))
    checks.update(result['checks'])
    workloads={ns:owned('Deployment','hermes-pilot',ns,operation) for ns in (FIRST,SECOND)}
    claims=[];pseudonyms=[]
    for ns in (FIRST,SECOND):
        p=pod(ns);spec=p['spec'];checks[ns+'_single_owner']=workloads[ns]['spec']['replicas']==1 and workloads[ns]['spec']['strategy']['type']=='Recreate'
        checks[ns+'_no_service_account']=spec.get('automountServiceAccountToken') is False
        for v in spec['volumes']:
            if 'persistentVolumeClaim' in v:
                pvc=owned('PersistentVolumeClaim',v['persistentVolumeClaim']['claimName'],ns,operation)
                claims.append(pvc['spec']['volumeName']);checks[ns+'_'+v['name']+'_rwop']=pvc['spec']['accessModes']==['ReadWriteOncePod']
        who='a' if ns==FIRST else 'b'
        source=values['probe'].replace('__OTHER_IP__',pod(SECOND if ns==FIRST else FIRST)['status']['podIP']).replace('__WHO__',who)
        result=json.loads(kube('exec',p['metadata']['name'],'-n',ns,'--','/opt/hermes/.venv/bin/python','-c',source,timeout=120))
        checks.update({ns+'_'+k:v for k,v in result['checks'].items()})
        pseudonyms.append(result['pseudonym_sha256'])
        kube('rollout','restart','deployment/hermes-pilot','-n',ns)
        kube('rollout','status','deployment/hermes-pilot','-n',ns,'--timeout=600s',timeout=620)
        p=pod(ns)
        persistence="from pathlib import Path;import json;print(json.dumps({'persisted':Path('/opt/data/.multiuser-private-"+who+".txt').read_text()=='synthetic-private-"+who+"'}))"
        checks[ns+'_workspace_survives_restart']=json.loads(kube('exec',p['metadata']['name'],'-n',ns,'--','/opt/hermes/.venv/bin/python','-c',persistence))['persisted']
    checks['privacy_pseudonyms_separated_by_identity']=len(set(pseudonyms))==2
    checks['four_distinct_state_and_tools_volumes']=len(claims)==len(set(claims))==4
    return {'passed':all(checks.values()),'checks':checks,'synthetic_only':True,'central_sso_qualified':False}

if __name__=='__main__':print(json.dumps({'install_multiuser':install,'verify_multiuser':verify}[ARCIA_INPUT['action']](ARCIA_INPUT)))
