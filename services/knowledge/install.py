"""Cluster Job only: hashed wheels and pinned safetensors, no remote code."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT=Path('/runtime')
def run(*args):subprocess.run(args,check=True,timeout=1500)
def main():
    os.umask(0o022)
    run(sys.executable,'-m','venv','--copies',str(ROOT/'python'))
    run(str(ROOT/'python/bin/python'),'-m','pip','install','--require-hashes','--only-binary=:all:',
        '--extra-index-url','https://download.pytorch.org/whl/cpu','-r','/code/requirements.lock.txt')
    models=json.loads(Path('/code/models.lock.json').read_text())
    for name,model in models.items():
        for relative,expected in model['files'].items():
            path=ROOT/'models'/name/relative
            if not path.resolve().is_relative_to((ROOT/'models'/name).resolve()):raise ValueError('MODEL_PATH')
            path.parent.mkdir(parents=True,exist_ok=True)
            if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==expected['sha256']:continue
            temporary=path.with_name(path.name+'.partial');digest=hashlib.sha256();size=0
            url='https://huggingface.co/'+model['repository']+'/resolve/'+model['revision']+'/'+relative
            with urllib.request.urlopen(url,timeout=120) as response,temporary.open('wb') as target:
                while block:=response.read(1024*1024):
                    size+=len(block)
                    if size>expected['size']:raise ValueError('MODEL_SIZE')
                    target.write(block);digest.update(block)
            if size!=expected['size'] or digest.hexdigest()!=expected['sha256']:raise ValueError('MODEL_HASH')
            temporary.replace(path)
    (ROOT/'ready.json').write_text(json.dumps({'models':{k:v['revision'] for k,v in models.items()}}))
    print('KNOWLEDGE_RUNTIME_INSTALLED')
if __name__=='__main__':main()
