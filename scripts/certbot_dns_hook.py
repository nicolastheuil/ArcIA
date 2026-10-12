"""Certbot DNS-01 hook: public TXT records only; keys remain in protected storage."""
import json
import os
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request


def published(record):
    name=urllib.parse.quote(record['name'])
    for endpoint in ('https://dns.google/resolve?name='+name+'&type=TXT',
                     'https://cloudflare-dns.com/dns-query?name='+name+'&type=TXT'):
        try:
            req=urllib.request.Request(endpoint,headers={'Accept':'application/dns-json'})
            with urllib.request.urlopen(req,timeout=5) as response: data=json.load(response)
            if any(record['value']==''.join(re.findall(r'"([^"]*)"',answer.get('data','')))
                   for answer in data.get('Answer',[]) if answer.get('type')==16): return True
        except Exception: pass
    return False


def main():
    root=Path(os.environ['ARCIA_ACME_ROOT'])
    request=json.loads((root/'request.json').read_text())
    domain=os.environ['CERTBOT_DOMAIN'];value=os.environ['CERTBOT_VALIDATION']
    if domain not in request['domains'] or not re.fullmatch(r'[A-Za-z0-9_-]{43}',value):
        raise ValueError('ACME_CHALLENGE_SCOPE')
    record={'name':'_acme-challenge.'+domain,'type':'TXT','value':value}
    path=root/'challenges'/(domain+'.json')
    temporary=path.with_suffix('.part')
    temporary.write_text(json.dumps(record));temporary.chmod(0o600);temporary.replace(path)
    # Certbot calls hooks sequentially; publish both challenges before waiting.
    if int(os.environ.get('CERTBOT_REMAINING_CHALLENGES','0'))!=0: return
    deadline=time.monotonic()+1800
    while time.monotonic()<deadline:
        records=[json.loads(p.read_text()) for p in (root/'challenges').glob('*.json')]
        if records and all(published(r) for r in records):
            # Leave a short extra propagation window before ACME's independent check.
            time.sleep(15);return
        time.sleep(10)
    raise ValueError('ACME_DNS_PUBLICATION_TIMEOUT')


if __name__=='__main__':
    os.umask(0o077)
    main()
