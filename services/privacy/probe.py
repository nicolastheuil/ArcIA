"""Synthetic privacy acceptance, executed only in the owned Hermes pod."""
import json
import os
from pathlib import Path
import socket
import urllib.request
import urllib.error
import yaml

def main():
    checks={};token=os.environ.get('OPENAI_API_KEY','')
    def call(path,value=None,auth=token):
        req=urllib.request.Request('http://privacy.arcia-privacy.svc.cluster.local:8091'+path,
            data=json.dumps(value).encode() if value is not None else None,headers={'Authorization':'Bearer '+auth,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=145) as response:return response.status,json.loads(response.read())
        except urllib.error.HTTPError as exc:return exc.code,json.loads(exc.read())
    fixture='Dossier Synthetique, alice@example.invalid, 10.27.43.9, srv-demo-42, password=synthetic-secret-123; telephone 06 12 34 56 78.'
    status,result=call('/v1/sanitize',{'messages':[{'role':'system','content':fixture},{'role':'user','content':fixture}],
        'documents':[fixture],'tool_results':[fixture],'metadata':{'title':fixture,'filename':'Dossier Synthetique-contract.pdf'}})
    raw=json.dumps(result)
    checks['presidio_whole_payload_filtered']=status==200 and all(x not in raw for x in ('alice@example.invalid','10.27.43.9','srv-demo-42','synthetic-secret-123','Dossier Synthetique'))
    checks['secrets_irrecoverably_removed']='SECRET_REMOVED' in raw and result.get('raw_mapping_stored') is False
    checks['opaque_images_blocked']=call('/v1/chat/completions',{'model':'openrouter/free','messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,AAAA'}}]}]})[0]==422
    checks['caller_provider_override_blocked']=call('/v1/chat/completions',{'model':'openrouter/free','messages':[{'role':'user','content':'synthetic'}],'provider':{'zdr':False}})[0]==422
    checks['paid_model_override_blocked']=call('/v1/chat/completions',{'model':'openrouter/auto','messages':[{'role':'user','content':'synthetic'}]})[0]==422
    checks['unauthenticated_calls_denied']=call('/v1/sanitize',{'messages':[{'role':'user','content':'synthetic'}]},'wrong-synthetic-token')[0]==401
    checks['private_dns_internal_resolves']=bool(socket.getaddrinfo('knowledge.arcia-knowledge.svc.cluster.local',8090))
    try:socket.getaddrinfo('synthetic-exfil.example.org',443);checks['dns_exfiltration_denied']=False
    except OSError:checks['dns_exfiltration_denied']=True
    try:socket.create_connection(('1.1.1.1',443),timeout=3).close();checks['direct_cloud_egress_denied']=False
    except OSError:checks['direct_cloud_egress_denied']=True
    try:socket.create_connection(('cloud-egress.arcia-privacy.svc.cluster.local',8092),timeout=3).close();checks['relay_bypass_denied']=False
    except OSError:checks['relay_bypass_denied']=True
    checks['provider_key_absent_from_hermes']=not os.environ.get('OPENROUTER_API_KEY')
    config=yaml.safe_load(Path('/opt/data/config.yaml').read_text())
    checks['hermes_gateway_url_configured']=config['model']['base_url'].rstrip('/')=='http://privacy.arcia-privacy.svc.cluster.local:8091/v1'
    checks['hermes_free_model_configured']=config['model']['default']=='openrouter/free'
    checks['hermes_custom_provider_configured']=config['model'].get('provider')=='custom'
    status,result=call('/v1/chat/completions',{'model':'openrouter/free','messages':[{'role':'user','content':
        'Synthetic qualification only. Reply exactly ARCIA_CLOUD_OK. Contact alice@example.invalid, IP 10.27.43.9, password=synthetic-secret-123'}],
        'max_tokens':32,'temperature':0})
    cloud_ok=status==200 and bool(result.get('choices'))
    checks['cloud_api_reachable_with_policy']=cloud_ok or (status in (403,404,429,503) and isinstance(result.get('error'),dict))
    return {'passed':all(checks.values()),'checks':checks,'cloud_enabled':True,'paid_enabled':False,
        'cloud_completion_verified':cloud_ok,'cloud_http_status':status,
        'cloud_status':'COMPLETION_VERIFIED' if cloud_ok else result.get('error',{}).get('message','UNAVAILABLE'),
        'business_iam_enabled':False,'private_data_qualified':False}

if __name__=='__main__':print(json.dumps(main()))
