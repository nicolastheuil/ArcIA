"""Bounded, reversible views of large read-only JSON tool results."""
from collections import OrderedDict
import json
import re
import secrets
import string
import threading
import time

MIN_BYTES=8192
MAX_BYTES=512*1024


class Originals:
    def __init__(self,clock=time.monotonic,ttl=300,max_bytes=4*1024*1024,max_items=32):
        self.clock=clock;self.ttl=ttl;self.max_bytes=max_bytes;self.max_items=max_items
        self.items=OrderedDict();self.lock=threading.Lock()

    def prune(self):
        now=self.clock()
        for key in list(self.items):
            if self.items[key][0]<=now:self.items.pop(key)
        while self.items and (len(self.items)>self.max_items or sum(len(v[1].encode()) for v in self.items.values())>self.max_bytes):
            self.items.popitem(last=False)

    def put(self,text):
        if len(text.encode())>min(MAX_BYTES,self.max_bytes):raise ValueError('ORIGINAL_TOO_LARGE')
        reference='ref_'+''.join(secrets.choice(string.ascii_lowercase) for _ in range(24))
        with self.lock:
            self.prune();self.items[reference]=(self.clock()+self.ttl,text);self.prune()
        return reference

    def get(self,reference,offset=0):
        if not isinstance(reference,str) or type(offset) is not int or offset<0:raise ValueError('ORIGINAL_REQUEST_INVALID')
        with self.lock:
            self.prune()
            if reference not in self.items:raise ValueError('ORIGINAL_EXPIRED_OR_UNKNOWN')
            text=self.items[reference][1]
        return {'content':text[offset:offset+48000],'next_offset':offset+48000 if len(text)>offset+48000 else None}


def structured_content(result):
    parsed=json.loads(result)
    if isinstance(parsed,dict):
        if parsed.get('isError') is True or parsed.get('success') is False or parsed.get('error'):
            raise ValueError('ERROR_RESULT_UNCHANGED')
        content=parsed.get('content',parsed.get('output',parsed))
        if isinstance(content,list) and len(content)==1 and isinstance(content[0],dict) and content[0].get('type')=='text':
            content=content[0].get('text')
    else:content=parsed
    if isinstance(content,str):
        lines=content.splitlines()
        if lines and all(re.match(r'^\d+\|',line) for line in lines):
            content='\n'.join(line.split('|',1)[1] for line in lines)
        content=json.loads(content)
    if not isinstance(content,(dict,list)):raise ValueError('STRUCTURED_JSON_REQUIRED')
    return json.dumps(content,ensure_ascii=False)


def transform(tool_name,result,eligible,compress,originals):
    if tool_name not in eligible or any(part in tool_name.casefold() for part in ('knowledge','catalog','skill','memory','session','auth','secret','credential','asset','restore')):
        return None
    if not isinstance(result,str) or not MIN_BYTES<=len(result.encode())<=MAX_BYTES:return None
    try:
        content=structured_content(result)
        if len(content.encode())<MIN_BYTES:return None
        reduced=compress(content)
        if not isinstance(reduced,str) or len(reduced.encode())>=.9*len(content.encode()):return None
        envelope={'arcia_compressed_overview':True,'source_tool':tool_name,
                  'original_reference':'ref_'+'a'*24,'original_bytes':len(result.encode()),
                  'preview':reduced,'notice':'Lossy overview. Use arcia_restore_tool_result for exact counts, quotations or omitted facts. Original is private to this runtime and expires after 5 minutes; after expiry repeat the original read. Normal privacy filtering still applies.'}
        # Count the complete model-facing envelope, not just the compressed body.
        if len(json.dumps(envelope,ensure_ascii=False).encode())>=.9*len(result.encode()):return None
        envelope['original_reference']=originals.put(result)
        return json.dumps(envelope,ensure_ascii=False)
    except Exception:return None
