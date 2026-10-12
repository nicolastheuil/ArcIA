"""Bounded authenticated internal envelope. No provider credential in Hermes."""
import hashlib
import hmac
import json
import secrets
import time

def encode(body,key):
    value={'timestamp':int(time.time()),'nonce':secrets.token_hex(24),'body':body}
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    return raw,hmac.new(key,raw,hashlib.sha256).hexdigest()

def decode(raw,signature,key,seen):
    if not hmac.compare_digest(signature,hmac.new(key,raw,hashlib.sha256).hexdigest()):raise ValueError('BAD_ATTESTATION')
    value=json.loads(raw);now=time.time()
    if set(value)!={'timestamp','nonce','body'} or abs(now-value['timestamp'])>60:raise ValueError('EXPIRED_ATTESTATION')
    for n,t in list(seen.items()):
        if now-t>120:seen.pop(n,None)
    nonce=value['nonce']
    if not isinstance(nonce,str) or len(nonce)!=48 or nonce in seen:raise ValueError('REPLAY_REFUSED')
    if len(seen)>10000:raise ValueError('ATTESTATION_CAPACITY')
    seen[nonce]=now
    return value['body']
