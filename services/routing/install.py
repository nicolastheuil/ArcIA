"""Install only the NPM artifact already fixed in the builder lock."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request
import shutil
import subprocess

ROOT=Path('/opt/arcia-routing')


def install():
    # Initial installation/repair never rewrites an existing provider database.
    # Any persistent database requires a separately qualified migration.
    if any(Path('/existing-data').glob('*.sqlite*')):
        raise ValueError('EXISTING_ROUTER_DATABASE_MIGRATION_REQUIRED')
    lock=json.loads(Path('/input/runtime.json').read_text())
    with urllib.request.urlopen(lock['url'],timeout=120) as response:
        archive=response.read(160*1024*1024+1)
    if len(archive)>160*1024*1024 or 'sha512-'+base64.b64encode(hashlib.sha512(archive).digest()).decode()!=lock['integrity']:
        raise ValueError('OMNIROUTE_ARTIFACT_HASH_REFUSED')
    ROOT.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
        tar.extractall(ROOT,filter='data')
    package=json.loads((ROOT/'package/package.json').read_text())
    if package['version']!=lock['version']:raise ValueError('OMNIROUTE_VERSION_REFUSED')
    # The upstream NPM artifact is the standalone application without its
    # dependency tree. Install the already pinned tree; never run postinstall.
    npm=ROOT/'npm';npm.mkdir(exist_ok=True)
    for name in ('package.json','package-lock.json'):shutil.copyfile(Path('/input')/name,npm/name)
    subprocess.run(['/usr/local/bin/npm','ci','--prefix',str(npm),'--ignore-scripts','--no-audit','--no-fund'],
                   check=True,timeout=1000)
    modules=ROOT/'package/dist/node_modules'
    if not modules.exists():modules.symlink_to(npm/'node_modules',target_is_directory=True)
    (ROOT/'package/dist/.build/next/cache').mkdir(parents=True,exist_ok=True)
    subprocess.run(['/usr/local/bin/node','-e',"require('next');require('better-sqlite3')(':memory:').close()"],
                   cwd=npm,check=True,timeout=30)
    (ROOT/'installed.json').write_text(json.dumps({'version':package['version'],'integrity':lock['integrity']}))
    print('OMNIROUTE_PINNED_RUNTIME_INSTALLED')


if __name__=='__main__':install()
