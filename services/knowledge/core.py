"""Bounded structural ingestion and late interaction; documents are untrusted."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

MAX_BYTES=32*1024*1024
MAX_CHUNKS=2000

@dataclass
class Part:
    locator: str
    kind: str
    text: str

def chunk(text, size=1800, overlap=200):
    text=text.strip()
    for start in range(0,len(text),size-overlap):
        yield text[start:start+size]
        if start+size>=len(text):break

def local_refs(value):
    """No remote reference resolution or implicit schema/network execution."""
    if isinstance(value,dict):
        if '$ref' in value and not str(value['$ref']).startswith('#/'):
            raise ValueError('EXTERNAL_SCHEMA_REFERENCE_REFUSED')
        for child in value.values():local_refs(child)
    elif isinstance(value,list):
        for child in value:local_refs(child)

def extract(data, suffix):
    if len(data)>MAX_BYTES:raise ValueError('SOURCE_TOO_LARGE')
    parts=[];assets={}
    if suffix=='.pdf':
        import pymupdf
        with pymupdf.open(stream=data,filetype='pdf') as doc:
            if doc.needs_pass or len(doc)>1000:raise ValueError('PDF_ENCRYPTED_OR_TOO_LONG')
            for number,page in enumerate(doc,1):
                text=page.get_text(sort=True).strip()
                if len(text)<20:raise ValueError('OCR_REQUIRED_BEFORE_PUBLICATION')
                for index,body in enumerate(chunk(text)):
                    parts.append(Part(f'page:{number}:text:{index}','passage',body))
                for index,table in enumerate(page.find_tables().tables):
                    rows=table.extract()
                    parts.append(Part(f'page:{number}:table:{index}','table',json.dumps(rows,ensure_ascii=False)))
                # Original page retains layout, arrows and legends, without a
                # generated description being mistaken for the authoritative image.
                if page.get_images() or page.get_drawings():
                    name=f'page-{number}.png'
                    image=page.get_pixmap(matrix=pymupdf.Matrix(1,1)).tobytes('png')
                    if sum(map(len,assets.values()))+len(image)>64*1024*1024:
                        raise ValueError('PAGE_ASSETS_BUDGET_EXCEEDED')
                    assets[name]=image
                    parts.append(Part(f'page:{number}:image','diagram',f'Schéma page {number}. '+text[:1200]))
    elif suffix in ('.json','.yaml','.yml'):
        if suffix=='.json':value=json.loads(data)
        else:
            import yaml
            value=yaml.safe_load(data)
        local_refs(value)
        if not isinstance(value,dict):raise ValueError('STRUCTURED_DOCUMENT_REQUIRED')
        if 'openapi' in value or 'swagger' in value:
            if len(value.get('paths',{}))>5000:raise ValueError('API_TOO_LARGE')
            shared={k:value[k] for k in ('info','security','components','definitions') if k in value}
            for path,methods in value.get('paths',{}).items():
                for method,operation in methods.items():
                    if method.lower() not in ('get','post','put','patch','delete','head','options','trace'):continue
                    title=method.upper()+' '+path+' '+operation.get('operationId','')
                    body=title+'\n'+json.dumps({'operation':operation,'path_parameters':methods.get('parameters',[]),
                        'shared':shared},ensure_ascii=False)
                    # Long schemas remain complete in the archived original;
                    # every operation has its own searchable, bounded sections.
                    for index,text in enumerate(chunk(body)):
                        parts.append(Part(f'operation:{method.upper()}:{path}:{index}','api',text))
        else:
            for index,text in enumerate(chunk(json.dumps(value,ensure_ascii=False))):
                parts.append(Part(f'schema:{index}','schema',text))
    elif suffix in ('.svg','.drawio','.mmd','.mermaid'):
        text=data.decode('utf-8')
        if suffix in ('.svg','.drawio'):
            if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise ValueError('XML_ENTITIES_REFUSED')
            root=ET.fromstring(text)
            if any(node.tag.split('}')[-1].lower() in ('script','foreignobject') for node in root.iter()):
                raise ValueError('ACTIVE_DIAGRAM_REFUSED')
            for node in root.iter():
                for key,value in node.attrib.items():
                    if key.split('}')[-1].lower().startswith('on') or (key.split('}')[-1]=='href' and not value.startswith('#')):
                        raise ValueError('ACTIVE_DIAGRAM_REFUSED')
        parts=[Part('diagram:source','diagram',text[:12000])]
        assets['editable'+suffix]=data
    elif suffix in ('.md','.txt'):
        parts=[Part(f'section:{i}','passage',text) for i,text in enumerate(chunk(data.decode('utf-8')))]
    else:raise ValueError('SOURCE_TYPE_REFUSED')
    if not parts or len(parts)>MAX_CHUNKS:raise ValueError('SOURCE_EMPTY_OR_TOO_MANY_CHUNKS')
    return parts,assets

def maxsim(query,document):
    import numpy as np
    q=np.asarray(query,dtype=np.float32);d=np.asarray(document,dtype=np.float32)
    if q.ndim!=2 or d.ndim!=2 or q.shape[1]!=d.shape[1] or not len(q) or not len(d):
        raise ValueError('INVALID_TOKEN_VECTORS')
    if len(q)>64 or len(d)>256 or not np.isfinite(q).all() or not np.isfinite(d).all():
        raise ValueError('TOKEN_VECTOR_BUDGET_OR_FINITE_CHECK')
    q=q/np.maximum(np.linalg.norm(q,axis=1,keepdims=True),1e-12)
    d=d/np.maximum(np.linalg.norm(d,axis=1,keepdims=True),1e-12)
    return float((q@d.T).max(axis=1).sum()/len(q))

def reciprocal_rank(rankings,limit=30):
    scores={}
    for ranking in rankings:
        for rank,identifier in enumerate(dict.fromkeys(ranking),1):
            scores[identifier]=scores.get(identifier,0)+1/(60+rank)
    return sorted(scores,key=lambda key:(-scores[key],key))[:limit]

def validate_metadata(value):
    required=('product','version','title','source')
    if any(not isinstance(value.get(key),str) or not 1<=len(value[key])<=300 for key in required):
        raise ValueError('DOCUMENT_METADATA_REQUIRED')
    # Identifier filters are data, never SQL identifiers or filesystem paths.
    return {key:value[key] for key in required}
