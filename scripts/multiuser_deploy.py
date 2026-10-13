"""Fixed two-identity qualification; no model-selected namespaces or PodSpecs."""
import hashlib
import json
from pathlib import Path
import kubernetes_apps
import hermes_tools

ROOT=Path(__file__).resolve().parents[1]
SECOND='arcia-hermes-qualification-b'
PREFIX='/qualification-b'

def payload(lock,config,pilot,second_pilot):
    # Native Hermes understands the trusted forwarded prefix for SPA, APIs,
    # cookies and WebSockets. Separate processes and PVCs are the boundary.
    documents=json.loads(json.dumps(kubernetes_apps.hermes(lock,config,second_pilot)).replace('arcia-hermes',SECOND))
    for doc in documents:
        if doc['kind']=='Namespace':doc['metadata']['name']=SECOND
    deployment=next(d for d in documents if d['kind']=='Deployment' and d['metadata']['name']=='hermes-pilot')
    for env in deployment['spec']['template']['spec']['containers'][0]['env']:
        if env['name']=='HERMES_DASHBOARD_PUBLIC_URL':env['value']+=PREFIX
    # The stable configuration and immutable mounted configuration must agree.
    import yaml
    stable=next(d for d in documents if d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config')
    settings=yaml.safe_load(stable['data']['config.yaml'])
    settings['dashboard']['public_url']+=PREFIX
    stable['data']['config.yaml']=yaml.safe_dump(settings,sort_keys=False)
    documents=[d for d in documents if not (d['kind']=='ConfigMap' and d.get('immutable'))]
    digest=hashlib.sha256(stable['data']['config.yaml'].encode()).hexdigest();name='hermes-config-'+digest[:16]
    documents.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':name,'namespace':SECOND},'immutable':True,'data':dict(stable['data'])})
    next(v for v in deployment['spec']['template']['spec']['volumes'] if v['name']=='config')['configMap']['name']=name
    deployment['spec']['template']['metadata']['annotations']['arcia.io/config-sha256']=digest
    tools=hermes_tools.payload()
    job=json.loads(json.dumps(next(d for d in tools['documents'] if d['kind']=='Job')).replace('arcia-hermes',SECOND))
    return {'documents':documents,'deployment':deployment,'job':job,'catalog_sha256':tools['catalog_sha256'],
            'ingress':kubernetes_apps.ingress(lock,config,pilot),
            'probe':(ROOT/'services/multiuser/probe.py').read_text(encoding='utf-8'),
            'tools_probe':tools['verify_source'],
            'knowledge_probe':(ROOT/'services/multiuser/knowledge_probe.py').read_text(encoding='utf-8')}
