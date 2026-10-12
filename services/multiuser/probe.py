"""Inside each Hermes runtime: safe synthetic fixture only; no private output."""
import json
import os
from pathlib import Path
import socket
import sys
import hashlib
import urllib.request
import urllib.error

checks={}
try:socket.create_connection(('__OTHER_IP__',9119),timeout=3).close();checks['other_runtime_network_denied']=False
except OSError:checks['other_runtime_network_denied']=True
try:socket.create_connection(('1.1.1.1',443),timeout=3).close();checks['direct_cloud_network_denied']=False
except OSError:checks['direct_cloud_network_denied']=True
checks['provider_key_absent']='OPENROUTER_API_KEY' not in os.environ
checks['tools_present_readonly']=Path('/opt/arcia-tools/installed.json').is_file()
try:Path('/opt/arcia-tools/forbidden-qualification-write').write_text('synthetic');checks['tools_present_readonly']=False
except OSError:pass
checks['knowledge_readonly_token_present']=Path('/opt/arcia-knowledge/token').is_file()
checks['no_kubernetes_credentials']=not Path('/var/run/secrets/kubernetes.io/serviceaccount/token').exists()
marker=Path('/opt/data/.multiuser-qualification-marker')
marker.write_text('synthetic-local-state')
checks['own_workspace_write']=marker.read_text()=='synthetic-local-state'
marker.unlink()
who='__WHO__';other='b' if who=='a' else 'a'
fixture=Path('/opt/data/.multiuser-private-'+who+'.txt');fixture.write_text('synthetic-private-'+who)
checks['other_workspace_file_absent']=not Path('/opt/data/.multiuser-private-'+other+'.txt').exists()
sys.path.insert(0,'/opt/hermes')
from hermes_state import SessionDB
db=SessionDB(db_path=Path('/opt/data/state.db'))
sid='arcia-multiuser-qualification-'+who
if not db.get_session(sid):
    db.create_session(sid,'cli')
    db.set_session_title(sid,'ArcIA synthetic multiuser '+who)
    db.append_message(sid,'user','Synthetic private message '+who)
checks['own_state_session_created']=db.get_session(sid) is not None
checks['other_state_session_absent']=db.get_session('arcia-multiuser-qualification-'+other) is None
db.close()
req=urllib.request.Request('http://privacy.arcia-privacy.svc.cluster.local:8091/v1/sanitize',
    data=json.dumps({'messages':[{'role':'user','content':'alice@example.invalid'}]}).encode(),
    headers={'Authorization':'Bearer '+os.environ.get('OPENAI_API_KEY',''),'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=60) as r:filtered=r.read()
checks['own_cloud_filter_token_accepted']=r.status==200 and b'alice@example.invalid' not in filtered
req=urllib.request.Request('http://knowledge.arcia-knowledge.svc.cluster.local:8090/search',
    data=json.dumps({'query':'ARCIAMULTIUSER','product':'ArcIA Multiuser Synthetic','limit':10}).encode(),
    headers={'Authorization':'Bearer '+Path('/opt/arcia-knowledge/token').read_text().strip(),'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=180) as r:rows=json.loads(r.read()).get('results',[])
versions={row['version'] for row in rows}
checks['mounted_knowledge_token_common_and_own']={'1-'+who.upper(),'1-COMMON'}<=versions and '1-'+other.upper() not in versions
print(json.dumps({'checks':checks,'pseudonym_sha256':hashlib.sha256(filtered).hexdigest()}))
