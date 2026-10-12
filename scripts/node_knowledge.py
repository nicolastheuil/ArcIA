"""Fixed privileged engineer operation. Private outputs captured by DPAPI wrapper."""
import base64
import hashlib
import json
import secrets
import subprocess
import time

NS='arcia-knowledge'
def kube(*args,document=None,input_text=None,timeout=90):
    result=subprocess.run(['/usr/local/bin/k3s','kubectl',*args],capture_output=True,
        input=json.dumps(document).encode() if document is not None else (input_text.encode() if input_text is not None else None),timeout=timeout)
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout.decode()

def apply(documents,operation):
    for doc in documents:
        doc['metadata'].setdefault('annotations',{})['arcia.io/operation-id']=operation
        args=['get',doc['kind'],doc['metadata']['name'],'--ignore-not-found','-o','json']
        if doc['kind']!='Namespace':args.extend(['-n',doc['metadata']['namespace']])
        old=kube(*args)
        if old and json.loads(old)['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:
            raise ValueError('FOREIGN_KNOWLEDGE_RESOURCE')
    kube('apply','--server-side','--field-manager=arcia-foundation','-f','-',document={'apiVersion':'v1','kind':'List','items':documents})

def pod():
    pods=json.loads(kube('get','pods','-n',NS,'-l','app=knowledge','-o','json'))['items']
    ready=[p for p in pods if p['status']['phase']=='Running' and not p['metadata'].get('deletionTimestamp')]
    if len(ready)!=1:raise ValueError('SINGLE_KNOWLEDGE_OWNER_REQUIRED')
    return ready[0]['metadata']['name']

def verify(values):
    deployment=json.loads(kube('get','deployment','knowledge','-n',NS,'-o','json'))
    if deployment['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=values['operation_id']:
        raise ValueError('KNOWLEDGE_OWNERSHIP_REQUIRED')
    return json.loads(kube('exec',pod(),'-n',NS,'--','/runtime/python/bin/python','-c',values['probe'],timeout=600))

def inspect(values):
    ns=json.loads(kube('get','namespace',NS,'-o','json'))
    if ns['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=values['operation_id']:
        raise ValueError('KNOWLEDGE_OWNERSHIP_REQUIRED')
    jobs=json.loads(kube('get','jobs','-n',NS,'-o','json'))['items']
    pods=json.loads(kube('get','pods','-n',NS,'-o','json'))['items']
    return {'jobs':[{'active':j.get('status',{}).get('active',0),'succeeded':j.get('status',{}).get('succeeded',0),
        'failed':j.get('status',{}).get('failed',0)} for j in jobs],
        'pods':[{'phase':p['status']['phase'],'ready':any(c['type']=='Ready' and c['status']=='True' for c in p.get('status',{}).get('conditions',[]))} for p in pods]}

def connect_hermes(values):
    operation=values['operation_id']
    deployment=json.loads(kube('get','deployment','hermes-pilot','-n','arcia-hermes','-o','json'))
    if deployment['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:
        raise ValueError('HERMES_OWNERSHIP_REQUIRED')
    secret=json.loads(kube('get','secret','knowledge-credentials','-n',NS,'-o','json'))
    if secret['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:
        raise ValueError('KNOWLEDGE_CREDENTIAL_OWNERSHIP')
    tokens=json.loads(base64.b64decode(secret['data']['tokens.json']))
    token=next(k for k,v in tokens.items() if v=={'scope':'qualification-a','role':'reader'})
    apply([{'apiVersion':'v1','kind':'Secret','metadata':{'name':'knowledge-reader','namespace':'arcia-hermes'},
        'type':'Opaque','stringData':{'token':token}}],operation)
    return {'passed':True,'read_only_hermes_token_provisioned':True,'business_iam_enabled':False}

def install(values):
    operation=values['operation_id']
    current=kube('get','namespace',NS,'--ignore-not-found','-o','json')
    if current and json.loads(current)['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:
        raise ValueError('FOREIGN_KNOWLEDGE_NAMESPACE')
    # Verify ownership of the designated CNPG cluster before creating anything.
    cluster=json.loads(kube('get','cluster.postgresql.cnpg.io','arcia-postgres','-n','arcia-data','-o','json'))
    if cluster['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:
        raise ValueError('POSTGRES_OWNERSHIP_REQUIRED')
    old=kube('get','deployment','knowledge','-n',NS,'--ignore-not-found','-o','json') if current else ''
    if old:
        previous=json.loads(old)
        if previous['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:
            raise ValueError('FOREIGN_KNOWLEDGE_DEPLOYMENT')
        previous_code=json.loads(kube('get','configmap','knowledge-code','-n',NS,'-o','json'))['data']
        incoming=next(d for d in values['documents'] if d['kind']=='ConfigMap')['data']
        if any(previous_code[k]!=incoming[k] for k in ('models.lock.json','requirements.lock.txt')):
            raise ValueError('KNOWLEDGE_MODEL_OR_DEPENDENCY_UPGRADE_REQUIRES_CONTROLLED_UNMOUNT')
    apply(values['documents'],operation)
    existing=kube('get','secret','knowledge-credentials','-n',NS,'--ignore-not-found','-o','json')
    if existing:
        secret=json.loads(existing)
        if secret['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:raise ValueError('FOREIGN_KNOWLEDGE_CREDENTIALS')
        password=json.loads(base64.b64decode(secret['data']['db.json']))['password']
    else:
        password=secrets.token_urlsafe(36)
        tokens={secrets.token_urlsafe(36):{'scope':scope,'role':role} for scope in ('qualification-a','qualification-b') for role in ('reader','ingester')}
        secret={'apiVersion':'v1','kind':'Secret','metadata':{'name':'knowledge-credentials','namespace':NS},'type':'Opaque',
            'stringData':{'db.json':json.dumps({'host':'arcia-postgres-rw.arcia-data.svc.cluster.local','dbname':'arcia',
                'user':'arcia_knowledge','password':password,'sslmode':'require'}),'tokens.json':json.dumps(tokens)}}
        apply([secret],operation)
    primary=cluster['status']['currentPrimary']
    sql="""DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='arcia_knowledge') THEN
 CREATE ROLE arcia_knowledge LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; END IF; END $$;
ALTER ROLE arcia_knowledge PASSWORD '"""+password.replace("'","''")+"';\n"+values['schema']
    kube('exec','-i',primary,'-n','arcia-data','-c','postgres','--','psql','-U','postgres','-d','arcia','-v','ON_ERROR_STOP=1',input_text=sql)
    apply([values['postgres_policy']],operation)
    if old:
        apply([values['deployment']],operation)
        kube('rollout','status','deployment/knowledge','-n',NS,'--timeout=600s',timeout=620)
        return verify(values)
    apply([values['job']],operation)
    name=values['job']['metadata']['name'];deadline=time.monotonic()+2400
    while time.monotonic()<deadline:
        state=json.loads(kube('get','job',name,'-n',NS,'-o','json')).get('status',{})
        if any(c['type']=='Failed' and c['status']=='True' for c in state.get('conditions',[])):
            raise RuntimeError('KNOWLEDGE_INSTALL_FAILED\n'+kube('logs','job/'+name,'-n',NS,'--tail=45'))
        if state.get('succeeded')==1:break
        time.sleep(3)
    else:raise ValueError('KNOWLEDGE_INSTALL_TIMEOUT')
    kube('delete','job',name,'-n',NS,'--wait=true','--timeout=90s',timeout=100)
    apply([values['deployment']],operation)
    try:kube('rollout','status','deployment/knowledge','-n',NS,'--timeout=600s',timeout=620)
    except Exception as exc:
        raise RuntimeError('KNOWLEDGE_START_FAILED\n'+kube('logs','deployment/knowledge','-n',NS,'--tail=40')) from exc
    return verify(values)

if __name__=='__main__':
    print(json.dumps({'install_knowledge':install,'verify_knowledge':verify,'inspect_knowledge':inspect,'connect_knowledge':connect_hermes}[ARCIA_INPUT['action']](ARCIA_INPUT)))
