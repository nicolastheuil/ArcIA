"""Runs only in the pinned Hermes installer Job, as UID 10000."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path('/opt/arcia-tools')
INPUT = Path('/input')


def run(*args):
    subprocess.run(args, check=True, timeout=700)


def main():
    os.umask(0o022)
    value = json.loads((INPUT/'catalog.json').read_text())
    ROOT.mkdir(exist_ok=True)
    (ROOT/'npm').mkdir(exist_ok=True)
    for name in ('package.json','package-lock.json'):
        shutil.copyfile(INPUT/name, ROOT/'npm'/name)
    run('/usr/local/bin/npm', 'ci', '--prefix', str(ROOT/'npm'),
        '--ignore-scripts', '--no-audit', '--no-fund')
    # This environment is independent of Hermes' own dependencies. Same pinned
    # image and absolute mount path in installer and runtime preserve the venv.
    if not (ROOT/'python/bin/python').exists():
        run(sys.executable, '-m', 'venv', '--copies', str(ROOT/'python'))
    # CSI fsGroup permission reconciliation may leave a partial interpreter
    # after an interrupted installation. Restore executable bits before reuse.
    (ROOT/'python/bin/python').chmod(0o755)
    for name in ('python3','python3.14'):
        candidate=ROOT/'python/bin'/name
        if candidate.exists() and not candidate.is_symlink():candidate.chmod(0o755)
    run(str(ROOT/'python/bin/python'), '-m', 'ensurepip', '--upgrade')
    run(str(ROOT/'python/bin/python'), '-m', 'pip', 'install', '--require-hashes',
        '--only-binary=:all:', '-r', str(INPUT/'requirements.lock.txt'))
    for relative, content in value['skills'].items():
        path = ROOT/'skills'/relative
        if not path.resolve().is_relative_to((ROOT/'skills').resolve()):
            raise ValueError('CATALOG_PATH_REFUSED')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')
    for relative, expected in value['skill_hashes'].items():
        if hashlib.sha256((ROOT/'skills'/relative).read_bytes()).hexdigest() != expected:
            raise ValueError('CATALOG_HASH_MISMATCH')
    (ROOT/'bin').mkdir(exist_ok=True)
    rtk = value['tools']['rtk']
    with urllib.request.urlopen(rtk['asset_url'], timeout=60) as response:
        archive = response.read(64*1024*1024+1)
    if len(archive)>64*1024*1024 or hashlib.sha256(archive).hexdigest()!=rtk['sha256']:
        raise ValueError('RTK_HASH_MISMATCH')
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        members = [m for m in tar.getmembers() if m.isfile() and Path(m.name).name=='rtk']
        if len(members)!=1 or members[0].size>128*1024*1024:
            raise ValueError('RTK_ARCHIVE_REFUSED')
        (ROOT/'bin/rtk').write_bytes(tar.extractfile(members[0]).read())
        (ROOT/'bin/rtk').chmod(0o755)
    wrappers = {'context7':('node','/opt/arcia-tools/npm/node_modules/@upstash/context7-mcp/dist/index.js'),
        'skills':('node','/opt/arcia-tools/npm/node_modules/skills/bin/cli.mjs')}
    for name, (command, entry) in wrappers.items():
        target=ROOT/'bin'/name
        target.write_text('#!/bin/sh\nexport DISABLE_TELEMETRY=1\nexec /usr/local/bin/'+command+' '+entry+' "$@"\n')
        target.chmod(0o755)
    for name in ('lintlang','headroom','certbot'):
        target=ROOT/'bin'/name
        if not target.exists(): target.symlink_to(ROOT/'python/bin'/name)
    shutil.copyfile(INPUT/'AGENTS.md', ROOT/'AGENTS.md')
    shutil.copyfile(INPUT/'role.md', ROOT/'role.md')
    (ROOT/'installed.json').write_text(json.dumps({'catalog_sha256':value['catalog_sha256'],
        'versions':{k:v.get('version',v.get('revision')) for k,v in value['tools'].items()}}))
    print('HERMES_PINNED_TOOLS_INSTALLED', flush=True)


if __name__=='__main__': main()
