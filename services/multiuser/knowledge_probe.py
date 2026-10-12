"""Shared enterprise corpus plus personal A/B, SQL RLS and download checks."""
import base64
import json
from pathlib import Path
import urllib.request
import urllib.error
import psycopg

tokens=json.loads(Path('/credentials/tokens.json').read_text())
def token(scope,role):return next(k for k,v in tokens.items() if v.get('scope')==scope and v.get('role')==role)
def request(path,scope,role='reader',value=None,key=None):
    headers={'Authorization':'Bearer '+(key or token(scope,role)),'Content-Type':'application/json'}
    req=urllib.request.Request('http://127.0.0.1:8090'+path,data=None if value is None else json.dumps(value).encode(),headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=240) as r:return r.status,r.read()
    except urllib.error.HTTPError as e:return e.code,e.read()
checks={};ids={}
for suffix,scope in [('A','qualification-a'),('B','qualification-b'),('COMMON','qualification-common')]:
    fixture={'product':'ArcIA Multiuser Synthetic','version':'1-'+suffix,'title':'Isolation fixture '+suffix,
        'source':'https://example.invalid/multiuser','suffix':'.md',
        'content_base64':base64.b64encode(('ARCIAMULTIUSER '+suffix+' synthetic qualification reference.').encode()).decode()}
    status,raw=request('/ingest',scope,'ingester',fixture);ids[suffix]=json.loads(raw).get('id')
    checks['ingest_'+suffix]=status==200 and bool(ids[suffix])
for who,scope in [('A','qualification-a'),('B','qualification-b')]:
    status,raw=request('/search',scope,value={'query':'ARCIAMULTIUSER','product':'ArcIA Multiuser Synthetic','limit':10})
    rows=json.loads(raw).get('results',[]);seen={r['document_id'] for r in rows}
    other='B' if who=='A' else 'A'
    checks[who+'_common_and_own_search']=status==200 and ids[who] in seen and ids['COMMON'] in seen
    checks[who+'_other_private_search_denied']=ids[other] not in seen
    checks[who+'_common_download']=request('/assets/'+ids['COMMON']+'/original.md',scope)[0]==200
    checks[who+'_other_private_download_denied']=request('/assets/'+ids[other]+'/original.md',scope)[0]==404
    checks[who+'_reader_write_denied']=request('/ingest',scope,value={})[0]==403
    checks[who+'_scope_spoof_denied']=request('/search',scope,value={'query':'ARCIAMULTIUSER','read_scopes':['qualification-common','qualification-'+other.lower()]})[0]==400
db=json.loads(Path('/credentials/db.json').read_text())
with psycopg.connect(**db) as connection:
    checks['sql_without_identity_empty']=connection.execute('SELECT count(*) FROM knowledge.documents').fetchone()[0]==0
    connection.execute("SELECT set_config('arcia.scope','qualification-a',true)")
    connection.execute("SELECT set_config('arcia.read_scopes','qualification-a|qualification-common',true)")
    seen={r[0] for r in connection.execute('SELECT id FROM knowledge.documents WHERE product=%s',('ArcIA Multiuser Synthetic',))}
    checks['sql_rls_common_and_own_only']=seen=={ids['A'],ids['COMMON']}
    try:
        with connection.transaction():connection.execute('INSERT INTO knowledge.documents(id,scope,product,version,title,source,sha256,suffix) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',('synthetic-cross-write','qualification-b','fixture','1','fixture','example.invalid','0'*64,'.md'))
        checks['sql_cross_scope_write_denied']=False
    except psycopg.errors.InsufficientPrivilege:checks['sql_cross_scope_write_denied']=True
checks['invalid_token_denied']=request('/search','qualification-a',value={'query':'ARCIAMULTIUSER'},key='synthetic-invalid-token')[0]==401
print(json.dumps({'checks':checks,'passed':all(checks.values())}))
