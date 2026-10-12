"""Synthetic end-to-end checks run inside the isolated knowledge Pod."""
import base64
import hashlib
import json
from pathlib import Path
import socket
import urllib.request
import urllib.error
import psycopg
import pymupdf
import time
import sys
sys.path.insert(0,'/code')
from core import maxsim

tokens=json.loads(Path('/credentials/tokens.json').read_text())
def token(scope,role):return next(k for k,v in tokens.items() if v=={'scope':scope,'role':role})
reader=token('qualification-a','reader');writer=token('qualification-a','ingester');other=token('qualification-b','reader')
def request(path,value=None,key=reader):
    data=None if value is None else json.dumps(value).encode()
    req=urllib.request.Request('http://127.0.0.1:8090'+path,data=data,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=300) as response:return response.status,response.read()
    except urllib.error.HTTPError as exc:return exc.code,exc.read()
def document(content,suffix='.md',version='1',**extra):
    return {'product':'ArcIA Synthetic Appliance','version':version,'title':'Snapshot recovery API guide',
        'source':'https://example.invalid/synthetic/reference','suffix':suffix,'content_base64':base64.b64encode(content).decode(),**extra}

checks={}
checks['maxsim_cosine_known_vectors']=abs(maxsim([[1,0],[0,1]],[[2,0],[0,3]])-1)<1e-6 and maxsim([[1,0]],[[-1,0]])==-1
pdf=pymupdf.open();page=pdf.new_page()
page.insert_text((40,40),'Synthetic vendor guide: backupPolicy API creates a daily backup.')
page.draw_rect(pymupdf.Rect(50,100,200,150));page.insert_text((60,125),'Hermes -> Knowledge API')
status,raw=request('/ingest',document(pdf.tobytes(),'.pdf'),writer)
checks['pdf_text_and_diagram_preserved']=status==200 and 'page-1.png' in json.loads(raw).get('assets',[])
empty=pymupdf.open();empty.new_page()
checks['unreadable_pdf_not_published']=request('/ingest',document(empty.tobytes(),'.pdf'),writer)[0]==400
long_guide=('Snapshot restore parameters and recovery procedure. '*160+' Final parameter retentionDays preserves restoreSnapshot history.').encode()
status,raw=request('/ingest',document(long_guide,version='token-windows-v1'),writer)
checks['long_guide_ingested']=status==200
status,raw=request('/search',{'query':'retentionDays','version':'token-windows-v1'})
checks['late_windows_preserve_tail']=status==200 and any('retentionDays' in row['body'] for row in json.loads(raw).get('results',[]))
api=json.dumps({'openapi':'3.1.0','info':{'title':'Synthetic Storage API','version':'1'},'paths':{
    '/snapshots/{id}/restore':{'post':{'operationId':'restoreSnapshot','summary':'Restore a storage snapshot / restaurer un instantané',
        'parameters':[{'name':'id','in':'path','required':True,'schema':{'type':'string'}}],
        'responses':{'202':{'description':'Restore scheduled'}}}}}}).encode()
status,raw=request('/ingest',document(api,'.json'),writer);result=json.loads(raw)
checks['openapi_ingested']=status==200 and bool(result.get('id'));identifier=result.get('id','')
status,raw=request('/ingest',document(api,'.json'),writer)
checks['idempotent_ingestion']=status==200 and json.loads(raw).get('deduplicated',False)
guide=b'Synthetic guide version 2: snapshot restore is removed. Use cloneSnapshot instead.'
checks['second_version_ingested']=request('/ingest',document(guide,version='2'),writer)[0]==200
diagram=b'flowchart LR\n  H[Hermes] --> K[Knowledge API]\n  K --> P[PostgreSQL]\n'
status,raw=request('/ingest',document(diagram,'.mmd',parent_id=identifier,reconstruction=True),writer)
derivative=json.loads(raw)
checks['editable_derivative_ingested']=status==200 and request('/assets/'+derivative.get('id','')+'/editable.mmd')[0]==200
started=time.monotonic()
status,raw=request('/search',{'query':'Comment restaurer un instantane via restoreSnapshot ?','version':'1'})
latency=round(time.monotonic()-started,3)
rows=json.loads(raw).get('results',[])
checks['multivector_search_cited']=status==200 and bool(rows) and any('restoreSnapshot' in r['body'] and r['locator'].startswith('operation:POST:') for r in rows)
checks['version_filter_enforced']=bool(rows) and all(row['version']=='1' for row in rows)
checks['source_hash_citation']=bool(rows) and all(len(row['sha256'])==64 and row['source'].startswith('https://example.invalid/') for row in rows)
checks['cross_scope_search_denied']=json.loads(request('/search',{'query':'restoreSnapshot'},other)[1]).get('results')==[]
checks['cross_scope_asset_denied']=request('/assets/'+identifier+'/original.json',key=other)[0]==404
checks['reader_cannot_ingest']=request('/ingest',document(b'synthetic text'),reader)[0]==403
checks['anonymous_denied']=request('/search',{'query':'snapshot'},'invalid')[0]==401
checks['model_cannot_set_scope']=request('/search',{'query':'snapshot','scope':'qualification-b'})[0]==400
checks['external_schema_ref_denied']=request('/ingest',document(b'{"$ref":"http://169.254.169.254/metadata"}','.json'),writer)[0]==400
checks['active_svg_denied']=request('/ingest',document(b'<svg><script>alert(1)</script></svg>','.svg'),writer)[0]==400
status,raw=request('/assets/'+identifier+'/original.json')
checks['original_roundtrip']=status==200 and hashlib.sha256(raw).hexdigest()==hashlib.sha256(api).hexdigest()
db=json.loads(Path('/credentials/db.json').read_text())
with psycopg.connect(**db) as connection:
    row=connection.execute('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
    checks['database_role_no_superuser_or_bypass']=row==(False,False)
    checks['database_no_scope_returns_no_rows']=connection.execute('SELECT count(*) FROM knowledge.documents').fetchone()[0]==0
    checks['database_not_table_owner']=connection.execute("SELECT count(*) FROM pg_tables WHERE schemaname='knowledge' AND tableowner=current_user").fetchone()[0]==0
try:
    socket.create_connection(('1.1.1.1',443),timeout=3).close();checks['runtime_public_egress_denied']=False
except OSError:checks['runtime_public_egress_denied']=True
try:
    Path('/runtime/illegal-write').write_text('synthetic');checks['models_readonly']=False
except OSError:checks['models_readonly']=True
print(json.dumps({'checks':checks,'passed':all(checks.values()),'fixture_only':True,'synthetic_search_seconds':latency}))
