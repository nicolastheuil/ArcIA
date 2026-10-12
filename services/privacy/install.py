"""K3s Job: install hash-pinned Presidio and local spaCy models."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

def main():
    os.umask(0o022)
    root=Path('/runtime');python=root/'python/bin/python'
    subprocess.run([sys.executable,'-m','venv','--copies',str(root/'python')],check=True,timeout=120)
    subprocess.run([str(python),'-m','pip','install','--require-hashes','--only-binary=:all:','-r','/code/requirements.lock.txt'],check=True,timeout=1500)
    models=json.loads(Path('/code/models.lock.json').read_text())
    for name,model in models.items():
        path=root/(name+'-'+model['version']+'-py3-none-any.whl');digest=hashlib.sha256();size=0
        with urllib.request.urlopen(model['url'],timeout=90) as response,path.open('wb') as out:
            while block:=response.read(1048576):
                size+=len(block)
                if size>model['size']:raise ValueError('MODEL_SIZE')
                out.write(block);digest.update(block)
        if size!=model['size'] or digest.hexdigest()!=model['sha256']:raise ValueError('MODEL_HASH')
        subprocess.run([str(python),'-m','pip','install','--no-deps','--no-index',str(path)],check=True,timeout=120)
    (root/'ready.json').write_text(json.dumps({'presidio':'2.2.364','models':{k:v['version'] for k,v in models.items()}}))
    print('PRESIDIO_LOCAL_RUNTIME_INSTALLED')

if __name__=='__main__':main()
