"""Canonical Hermes integration, read-only query token in a separate Secret."""
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def augment(docs,settings):
    settings.setdefault('mcp_servers',{})['arcia_knowledge']={
        'command':'/opt/hermes/.venv/bin/python','args':['/opt/arcia-knowledge/client.py'],
        'connect_timeout':30,'timeout':180}
    code=(ROOT/'services/knowledge/mcp_client.py').read_text(encoding='utf-8')
    docs.extend([
        {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'knowledge-client','namespace':'arcia-hermes'},'data':{'client.py':code}},
        {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'hermes-knowledge-only','namespace':'arcia-hermes'},
            'spec':{'podSelector':{'matchLabels':{'app':'hermes-pilot'}},'policyTypes':['Egress'],'egress':[
                {'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'arcia-knowledge'}},
                    'podSelector':{'matchLabels':{'app':'knowledge'}}}],'ports':[{'port':8090,'protocol':'TCP'}]}]}}
    ])
    deploy=next(d for d in docs if d['kind']=='Deployment' and d['metadata']['name']=='hermes-pilot')
    spec=deploy['spec']['template']['spec'];container=spec['containers'][0]
    container['volumeMounts'].extend([
        {'name':'knowledge-client','mountPath':'/opt/arcia-knowledge/client.py','subPath':'client.py','readOnly':True},
        {'name':'knowledge-token','mountPath':'/opt/arcia-knowledge/token','subPath':'token','readOnly':True}])
    spec['volumes'].extend([{'name':'knowledge-client','configMap':{'name':'knowledge-client'}},
        {'name':'knowledge-token','secret':{'secretName':'knowledge-reader','defaultMode':288}}])
    deploy['spec']['template']['metadata'].setdefault('annotations',{})['arcia.io/knowledge-client-sha256']=hashlib.sha256(code.encode()).hexdigest()
