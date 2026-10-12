"""Private qualification API: local inference, server-bound scopes, no fetching."""
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
import urllib.parse

import numpy as np
import psycopg
from psycopg.rows import dict_row
from sentence_transformers import SentenceTransformer, MultiVectorEncoder
from core import extract,maxsim,reciprocal_rank,validate_metadata,MAX_BYTES,MAX_CHUNKS,Part

DATA=Path('/data')
TOKENS=json.loads(Path('/credentials/tokens.json').read_text())
DB=json.loads(Path('/credentials/db.json').read_text())
MODELS=json.loads(Path('/code/models.lock.json').read_text())
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
import torch
torch.set_num_threads(2)
DENSE=SentenceTransformer('/runtime/models/dense',device='cpu',local_files_only=True,trust_remote_code=False)
DENSE.max_seq_length=512
LATE=MultiVectorEncoder('/runtime/models/late',device='cpu',local_files_only=True,trust_remote_code=False)
LATE.max_seq_length=256
READY=True

def connect(scope,read_scopes=None):
    connection=psycopg.connect(**DB,row_factory=dict_row,connect_timeout=5)
    connection.execute("SELECT set_config('arcia.scope',%s,true)",(scope,))
    connection.execute("SELECT set_config('arcia.read_scopes',%s,true)",('|'.join(read_scopes or [scope]),))
    connection.execute("SET LOCAL statement_timeout='15s'")
    connection.execute("SET LOCAL hnsw.iterative_scan='strict_order'")
    return connection

def vector(value):return '['+','.join(format(float(x),'.8g') for x in value)+']'

def encoding(text,query=False):
    dense=DENSE.encode(('query: ' if query else 'passage: ')+text,normalize_embeddings=True,show_progress_bar=False)
    late=LATE.encode_query(text) if query else LATE.encode_document(text)
    late=np.asarray(late,dtype=np.float32)
    if late.ndim==3:late=late[0]
    late=late[:64 if query else 256]
    if dense.shape!=(384,) or late.ndim!=2 or late.shape[1]!=128 or not len(late):
        raise ValueError('MODEL_DIMENSION_MISMATCH')
    return dense,late

def ingest(scope,value):
    metadata=validate_metadata(value)
    data=base64.b64decode(value['content_base64'],validate=True)
    suffix=value.get('suffix','').lower()
    parts,assets=extract(data,suffix)
    token_parts=[]
    for part in parts:
        ids=LATE.tokenizer.encode(part.text,add_special_tokens=False)
        for start in range(0,len(ids),180):
            segment=LATE.tokenizer.decode(ids[start:start+220],skip_special_tokens=True)
            token_parts.append(Part(part.locator+f':tokens:{start}',part.kind,segment))
            if start+220>=len(ids):break
    if not token_parts or len(token_parts)>MAX_CHUNKS:raise ValueError('TOKEN_CHUNK_BUDGET')
    parts=token_parts
    digest=hashlib.sha256(data).hexdigest()
    identifier=hashlib.sha256((scope+'\0'+metadata['product']+'\0'+metadata['version']+'\0'+digest).encode()).hexdigest()
    parent=value.get('parent_id');reconstruction=bool(value.get('reconstruction',False))
    if reconstruction and not parent:raise ValueError('RECONSTRUCTION_PARENT_REQUIRED')
    with connect(scope) as db:
        old=db.execute('SELECT id FROM knowledge.documents WHERE id=%s',(identifier,)).fetchone()
        if old:return {'id':identifier,'deduplicated':True}
        if parent and not db.execute('SELECT id FROM knowledge.documents WHERE id=%s',(parent,)).fetchone():
            raise ValueError('AUTHORIZED_PARENT_REQUIRED')
        folder=DATA/identifier;folder.mkdir(mode=0o700,exist_ok=True)
        (folder/('original'+suffix)).write_bytes(data)
        for name,content in assets.items():(folder/name).write_bytes(content)
        manifest={'id':identifier,**metadata,'sha256':digest,'suffix':suffix,'parent_id':parent,
            'reconstruction':reconstruction,'models':{k:v['revision'] for k,v in MODELS.items()},'assets':{
                name:hashlib.sha256(content).hexdigest() for name,content in assets.items()}}
        (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False))
        db.execute('INSERT INTO knowledge.documents(id,scope,product,version,title,source,sha256,suffix,parent_id,reconstruction) '
            'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(identifier,scope,metadata['product'],metadata['version'],
                metadata['title'],metadata['source'],digest,suffix,parent,reconstruction))
        title=DENSE.encode('passage: '+metadata['product']+' '+metadata['version']+' '+metadata['title'],
            normalize_embeddings=True,show_progress_bar=False)
        for part in parts:
            dense,tokens=encoding(part.text)
            db.execute('INSERT INTO knowledge.chunks(document_id,scope,locator,kind,body,title_vector,body_vector,tokens,token_count) '
                'VALUES(%s,%s,%s,%s,%s,%s::vector,%s::vector,%s,%s)',
                (identifier,scope,part.locator,part.kind,part.text,vector(title),vector(dense),tokens.astype('<f2').tobytes(),len(tokens)))
    return {'id':identifier,'chunks':len(parts),'assets':list(assets),'sha256':digest}

def search(scope,value,read_scopes=None):
    query=value.get('query')
    if not isinstance(query,str) or not 1<=len(query)<=2000:raise ValueError('QUERY_SIZE')
    product=value.get('product');version=value.get('version')
    if any(v is not None and (not isinstance(v,str) or len(v)>300) for v in (product,version)):
        raise ValueError('FILTER_SIZE')
    limit=value.get('limit',5)
    if type(limit)!=int or not 1<=limit<=10:raise ValueError('RESULT_LIMIT')
    dense,tokens=encoding(query,True)
    with connect(scope,read_scopes) as db:
        base='SELECT c.id FROM knowledge.chunks c JOIN knowledge.documents d ON d.id=c.document_id '
        where='WHERE (%s::text IS NULL OR d.product=%s) AND (%s::text IS NULL OR d.version=%s) '
        filters=(product,product,version,version)
        lexical=db.execute(base+where+"AND terms @@ websearch_to_tsquery('simple',%s) ORDER BY "
            "ts_rank_cd(terms,websearch_to_tsquery('simple',%s)) DESC,c.id LIMIT 60",filters+(query,query)).fetchall()
        rankings=[[r['id'] for r in lexical]]
        for field in ('body_vector','title_vector'):
            rows=db.execute(base+where+f'ORDER BY {field} <=> %s::vector LIMIT 60',filters+(vector(dense),)).fetchall()
            rankings.append([r['id'] for r in rows])
        candidates=reciprocal_rank(rankings,30)
        rows=db.execute('SELECT c.*,d.product,d.version,d.title,d.source,d.sha256,d.reconstruction '
            'FROM knowledge.chunks c JOIN knowledge.documents d ON d.id=c.document_id WHERE c.id=ANY(%s)',(candidates,)).fetchall()
        for row in rows:
            matrix=np.frombuffer(row.pop('tokens'),dtype='<f2').reshape(row['token_count'],128)
            row['score']=maxsim(tokens,matrix)
            row.pop('title_vector');row.pop('body_vector');row.pop('terms');row.pop('scope')
        rows.sort(key=lambda row:(-row['score'],row['id']))
        return {'results':rows[:limit],'candidate_count':len(rows),'method':'fts+dense+title/rrf/mlateon-maxsim',
            'untrusted_document_content':True}

class Handler(BaseHTTPRequestHandler):
    server_version='ArcIA-Knowledge'
    def log_message(self,*args):pass
    def reply(self,status,value):
        raw=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)))
        self.end_headers();self.wfile.write(raw)
    def identity(self):
        supplied=self.headers.get('Authorization','').removeprefix('Bearer ')
        # Read the projected policy on every request; a revoked identity must not
        # survive indefinitely in a process cache. Malformed policy fails closed.
        try:tokens=json.loads(Path('/credentials/tokens.json').read_text())
        except (OSError,ValueError):return None
        for token,identity in tokens.items():
            if hmac.compare_digest(supplied,token):return identity
        return None
    def do_GET(self):
        if self.path=='/health':return self.reply(200,{'ready':READY})
        identity=self.identity()
        if not identity:return self.reply(401,{'error':'AUTH_REQUIRED'})
        if not self.path.startswith('/assets/'):return self.reply(404,{'error':'NOT_FOUND'})
        pieces=urllib.parse.urlsplit(self.path).path.split('/')
        if len(pieces)!=4:return self.reply(404,{'error':'NOT_FOUND'})
        _,_,identifier,name=pieces
        if len(identifier)!=64 or any(c not in '0123456789abcdef' for c in identifier):
            return self.reply(404,{'error':'NOT_FOUND'})
        with connect(identity['scope'],identity.get('read_scopes')) as db:
            doc=db.execute('SELECT suffix FROM knowledge.documents WHERE id=%s',(identifier,)).fetchone()
        if not doc:return self.reply(404,{'error':'NOT_FOUND'})
        folder=DATA/identifier
        manifest=json.loads((folder/'manifest.json').read_text())
        allowed={'original'+doc['suffix'],'manifest.json'}|set(manifest['assets'])
        if name not in allowed:return self.reply(404,{'error':'NOT_FOUND'})
        raw=(folder/name).read_bytes()
        # Downloads only: never execute or inline untrusted SVG/HTML.
        self.send_response(200);self.send_header('Content-Type','application/octet-stream')
        self.send_header('Content-Disposition','attachment; filename="'+name+'"')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        identity=self.identity()
        if not identity:return self.reply(401,{'error':'AUTH_REQUIRED'})
        if self.path not in ('/search','/ingest'):return self.reply(404,{'error':'NOT_FOUND'})
        if self.path=='/ingest' and identity['role']!='ingester':return self.reply(403,{'error':'INGEST_ROLE_REQUIRED'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 1<=size<=MAX_BYTES*2:raise ValueError('REQUEST_SIZE')
            value=json.loads(self.rfile.read(size))
            if not isinstance(value,dict):raise ValueError('OBJECT_REQUIRED')
            if any(k in value for k in ('scope','read_scopes','principal','user_id','role')):raise ValueError('SCOPE_BOUND_TO_SERVER_IDENTITY')
            result=search(identity['scope'],value,identity.get('read_scopes')) if self.path=='/search' else ingest(identity['scope'],value)
            return self.reply(200,result)
        except (ValueError,KeyError):return self.reply(400,{'error':'INVALID_DOCUMENT_OR_REQUEST'})
        except Exception:return self.reply(503,{'error':'KNOWLEDGE_OPERATION_FAILED'})

if __name__=='__main__':
    DATA.mkdir(exist_ok=True)
    # A single request at a time bounds CPU/model memory and prevents concurrent
    # writers. Separate workers/leases are required before concurrent ingestion.
    HTTPServer(('0.0.0.0',8090),Handler).serve_forever()
