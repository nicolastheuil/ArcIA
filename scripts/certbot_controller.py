"""User-scoped Linux Certbot controller. Private collect output must be captured."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid


def main(payload):
    os.umask(0o077)
    operation=str(uuid.UUID(payload['operation_id']))
    root=Path.home()/'.local/share/arcia-acme'/operation
    root.mkdir(parents=True,mode=0o700,exist_ok=True)
    if root.is_symlink() or root.stat().st_mode & 0o077: raise ValueError('PROTECTED_ACME_ROOT_REQUIRED')
    request_path=root/'request.json'
    if payload['action']=='checkpoint':
        files={}
        for path in [request_path,*sorted((root/'config/accounts').rglob('*.json')),
                     *sorted((root/'challenges').glob('*.json'))]:
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or path.stat().st_size>256*1024:
                raise ValueError('ACME_CHECKPOINT_FILE_SCOPE')
            files[str(path.relative_to(root))]=path.read_text()
        return {'private':{'operation_id':operation,'files':files,'dns_validation':'deferred_by_user'}}
    if payload['action']=='suspend':
        (root/'suspended.flag').write_text('user-deferred-dns-validation\n')
        stopped=0
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit() or int(entry.name)==os.getpid(): continue
            try:
                args=(entry/'cmdline').read_bytes().split(b'\0')
                if not any(str(root).encode() in arg for arg in args): continue
                # Only the scoped Certbot process or its exact hook invocation.
                if not any(arg.endswith(b'/arcia-certbot/bin/certbot') or
                    str(root/'dns_hook.py').encode() in arg for arg in args): continue
                os.kill(int(entry.name),signal.SIGTERM);stopped+=1
            except (FileNotFoundError,ProcessLookupError,PermissionError): pass
        return {'status':'deferred','code':'ACME_DNS_VALIDATION_DEFERRED','stopped_processes':stopped}
    if payload['action']=='collect':
        request=json.loads(request_path.read_text())
        live=root/'config/live/arcia-pilot'
        return {'private':{'operation_id':operation,'domains':request['domains'],
            'certificate':(live/'fullchain.pem').read_text(),'private_key':(live/'privkey.pem').read_text()}}
    domains=payload['domains']
    if len(domains)!=2 or len(set(domains))!=2 or not all(
        re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,250}\.[a-z]{2,}',d) for d in domains):
        raise ValueError('TWO_EXPLICIT_ACME_DOMAINS_REQUIRED')
    request={'operation_id':operation,'domains':domains,'email':payload['email']}
    if request_path.exists() and json.loads(request_path.read_text())!=request:
        raise ValueError('ACME_REQUEST_SCOPE_CONFLICT')
    request_path.write_text(json.dumps(request));request_path.chmod(0o600)
    (root/'suspended.flag').unlink(missing_ok=True)
    for name in ('config','work','logs','challenges'):
        (root/name).mkdir(mode=0o700,exist_ok=True)
    # Never announce a previous order's records as the current challenge.
    for path in (root/'challenges').glob('*.json'):
        history=root/'challenge-history';history.mkdir(mode=0o700,exist_ok=True)
        path.rename(history/(str(time.time_ns())+'-'+path.name))
    hook=root/'dns_hook.py';hook.write_text(payload['hook_source']);hook.chmod(0o700)
    python=Path.home()/'.local/share/arcia-certbot/bin/python'
    certbot=python.parent/'certbot'
    if subprocess.run([str(certbot),'--version'],capture_output=True,check=True).stdout.strip()!=b'certbot 5.8.0':
        raise ValueError('PINNED_CERTBOT_REQUIRED')
    command=[str(certbot),'certonly','--manual','--preferred-challenges','dns','--non-interactive',
        '--agree-tos','--email',payload['email'],'--cert-name','arcia-pilot',
        '--config-dir',str(root/'config'),'--work-dir',str(root/'work'),'--logs-dir',str(root/'logs'),
        '--manual-auth-hook',str(python)+' '+str(hook)]
    for domain in domains: command+=['-d',domain]
    environment=dict(os.environ,ARCIA_ACME_ROOT=str(root))
    with (root/'certbot-process.log').open('ab') as log:
        process=subprocess.Popen(command,stdout=log,stderr=log,env=environment)
        announced=set()
        try:
            while process.poll() is None:
                for path in (root/'challenges').glob('*.json'):
                    record=json.loads(path.read_text())
                    if (record['name'],record['value']) not in announced:
                        announced.add((record['name'],record['value']))
                        print(json.dumps({'status':'waiting_dns','code':'ACME_DNS_TXT_REQUIRED','record':record}),flush=True)
                time.sleep(1)
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill();process.wait()
        if (root/'suspended.flag').exists():
            return {'status':'deferred','code':'ACME_DNS_VALIDATION_DEFERRED'}
        return {'status':'issued' if process.returncode==0 else 'blocked',
            'code':'ACME_CERTIFICATE_ISSUED' if process.returncode==0 else 'ACME_CERTIFICATE_FAILED'}


if __name__=='__main__':
    try: result=main(json.load(sys.stdin))
    except Exception: result={'status':'blocked','code':'PROTECTED_ACME_OPERATION_FAILED'}
    print(json.dumps(result),flush=True)
    sys.exit(2 if result.get('status')=='blocked' else 0)
