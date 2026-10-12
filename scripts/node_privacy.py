"""Fixed engineer operation on the owned K3s cluster; protected I/O only."""
import base64
import hashlib
import json
import secrets
import subprocess
import time

NS='arcia-privacy'
def kube(*args,document=None,timeout=90):
    result=subprocess.run(['/usr/local/bin/k3s','kubectl',*args],input=json.dumps(document).encode() if document is not None else None,
        capture_output=True,timeout=timeout)
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout.decode()

def owned(kind,name,namespace,operation,optional=False):
    args=['get',kind,name,'-o','json']
    if namespace:args.extend(['-n',namespace])
    if optional:args.append('--ignore-not-found')
    raw=kube(*args)
    if not raw:return None
    result=json.loads(raw)
    if result['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:raise ValueError('FOREIGN_PRIVACY_RESOURCE')
    return result

def apply(documents,operation):
    for doc in documents:
        meta=doc['metadata'];owned(doc['kind'],meta['name'],meta.get('namespace'),operation,True)
        meta.setdefault('annotations',{})['arcia.io/operation-id']=operation
    kube('apply','--server-side','--field-manager=arcia-foundation','-f','-',document={'apiVersion':'v1','kind':'List','items':documents})

def inspect(values):
    owned('Namespace',NS,None,values['operation_id'])
    deployments=json.loads(kube('get','deployments','-n',NS,'-o','json'))['items']
    config=owned('ConfigMap','hermes-pilot-config','arcia-hermes',values['operation_id'])['data']['config.yaml']
    return {'deployments':[{'name':d['metadata']['name'],'ready':d.get('status',{}).get('readyReplicas',0)==1} for d in deployments],
            'configmap_gateway_present':'http://privacy.arcia-privacy.svc.cluster.local:8091/v1' in config,
            'configmap_free_model_present':'openrouter/free' in config,
            'cloud_enabled':True,'paid_enabled':False,'business_iam_enabled':False}

def verify(values):
    operation=values['operation_id'];owned('deployment','privacy',NS,operation)
    owned('deployment','hermes-pilot','arcia-hermes',operation)
    pods=json.loads(kube('get','pods','-n','arcia-hermes','-l','app=hermes-pilot','-o','json'))['items']
    running=[p for p in pods if p['status']['phase']=='Running' and not p['metadata'].get('deletionTimestamp')]
    if len(running)!=1:raise ValueError('SINGLE_HERMES_OWNER_REQUIRED')
    result=json.loads(kube('exec',running[0]['metadata']['name'],'-n','arcia-hermes','--',
        '/opt/arcia-tools/python/bin/python','-c',values['probe'],timeout=500))
    if result.get('cloud_completion_verified'):
        # Durable sanitized evidence: no prompt, response, identifiers or provider key.
        proof={'cloud_completion_verified':True,'paid_enabled':False,'synthetic_only':True,
               'verified_at_unix':int(time.time()),'privacy_code_sha256':values['digest']}
        apply([{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'privacy-qualification-proof','namespace':NS},
            'data':{'proof.json':json.dumps(proof)}}],operation)
    proof=owned('ConfigMap','privacy-qualification-proof',NS,operation,True)
    result['previous_cloud_completion_verified']=bool(proof)
    return result

def install(values):
    op=values['operation_id'];owned('deployment','hermes-pilot','arcia-hermes',op)
    namespace=owned('Namespace',NS,None,op,True)
    previous=owned('deployment','privacy',NS,op,True) if namespace else None
    if previous:
        old=owned('ConfigMap','privacy-code',NS,op)['data']
        new=next(d['data'] for d in values['documents'] if d['kind']=='ConfigMap')
        if any(old[k]!=new[k] for k in ('models.lock.json','requirements.lock.txt')):raise ValueError('CONTROLLED_PRIVACY_RUNTIME_UPGRADE_REQUIRED')
    if not values.get('api_key'):raise ValueError('PROTECTED_OPENROUTER_KEY_REQUIRED')
    apply(values['documents'],op)
    policy_secret=owned('Secret','privacy-policy',NS,op,True)
    if policy_secret:policy=json.loads(base64.b64decode(policy_secret['data']['policy.json']))
    else:
        policy={'cloud_enabled':True,'paid_enabled':False,'hmac_key':secrets.token_hex(32),'attestation_key':secrets.token_hex(32),
                'tokens':{secrets.token_urlsafe(36):{'scope':'qualification-a','classification':'synthetic',
                    'identifiers':['Fictif Conseil','Dossier Synthetique']}}}
    for identity in policy['tokens'].values():
        if identity.get('classification')=='synthetic':
            identity['identifiers']=[s.replace('Client Synthetique','Dossier Synthetique') for s in identity.get('identifiers',[])]
    token=next(k for k,v in policy['tokens'].items() if v['scope']=='qualification-a' and v['classification']=='synthetic')
    apply([{'apiVersion':'v1','kind':'Secret','metadata':{'name':'privacy-policy','namespace':NS},'type':'Opaque',
                'stringData':{'policy.json':json.dumps(policy)}},
           {'apiVersion':'v1','kind':'Secret','metadata':{'name':'cloud-provider','namespace':NS},'type':'Opaque',
                'stringData':{'egress.json':json.dumps({'api_key':values['api_key'],'attestation_key':policy['attestation_key']})}},
           {'apiVersion':'v1','kind':'Secret','metadata':{'name':'privacy-client','namespace':'arcia-hermes'},'type':'Opaque',
                'stringData':{'token':token}}],op)
    records={}
    for name,ns in [('privacy',NS),('cloud-egress',NS),('knowledge','arcia-knowledge'),('context7-docs','arcia-hermes')]:
        svc=kube('get','service',name,'-n',ns,'--ignore-not-found','-o','json')
        if svc:
            data=json.loads(svc)
            if data['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=op:raise ValueError('FOREIGN_DNS_SERVICE')
            records[name+'.'+ns+'.svc.cluster.local']=data['spec']['clusterIP']
    records['kubernetes.default.svc.cluster.local']=json.loads(kube('get','service','kubernetes','-n','default','-o','json'))['spec']['clusterIP']
    apply([{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'private-dns-records','namespace':NS},'data':{'records.json':json.dumps(records)}}],op)
    values['dns_deployment']['spec']['template']['metadata']['annotations']['arcia.io/records-sha256']=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()
    if not previous:
        # Resume only our failed installer; never evict an active RWOP owner.
        name=values['job']['metadata']['name'];old=owned('Job',name,NS,op,True)
        if old and any(c['type']=='Failed' and c['status']=='True' for c in old.get('status',{}).get('conditions',[])):
            kube('delete','job',name,'-n',NS,'--wait=true','--timeout=90s',timeout=100)
        apply([values['job']],op);deadline=time.monotonic()+2100
        while time.monotonic()<deadline:
            state=json.loads(kube('get','job',name,'-n',NS,'-o','json')).get('status',{})
            if any(c['type']=='Failed' and c['status']=='True' for c in state.get('conditions',[])):
                raise RuntimeError('PRIVACY_INSTALL_FAILED\n'+kube('logs','job/'+name,'-n',NS,'--tail=35'))
            if state.get('succeeded')==1:break
            time.sleep(3)
        else:raise ValueError('PRIVACY_INSTALL_TIMEOUT')
        kube('delete','job',name,'-n',NS,'--wait=true','--timeout=90s',timeout=100)
    apply([values[k] for k in ('dns_deployment','egress_deployment','deployment')],op)
    for name in ('private-dns','cloud-egress','privacy'):
        try:kube('rollout','status','deployment/'+name,'-n',NS,'--timeout=600s',timeout=620)
        except Exception as exc:raise RuntimeError('PRIVACY_START_FAILED\n'+kube('logs','deployment/'+name,'-n',NS,'--tail=30')) from exc
    apply([values['hermes_policy']],op)
    dns_ip=owned('Service','private-dns',NS,op)['spec']['clusterIP']
    kube('patch','deployment','hermes-pilot','-n','arcia-hermes','--field-manager=arcia-foundation','--type=merge','-p',json.dumps({
        'spec':{'template':{'spec':{'dnsPolicy':'None','dnsConfig':{'nameservers':[dns_ip],
            'searches':['arcia-hermes.svc.cluster.local','svc.cluster.local','cluster.local'],'options':[{'name':'ndots','value':'1'}]}}}}}))
    kube('rollout','status','deployment/hermes-pilot','-n','arcia-hermes','--timeout=600s',timeout=620)
    return {'passed':True,'presidio_deployed':True,'cloud_gateway_enabled':True,'paid_enabled':False,'cloud_completion_verified':False}

if __name__=='__main__':print(json.dumps({'install_privacy':install,'verify_privacy':verify,'inspect_privacy':inspect}[ARCIA_INPUT['action']](ARCIA_INPUT)))
