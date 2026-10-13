"""Runs only in the controlled tools installer Job, with public artefact egress."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import urllib.request
from bundle import MAX_ARCHIVE, assemble, canonical


def install(root=Path('/opt/arcia-tools'), inputs=Path('/input')):
    lock = json.loads((inputs/'skills.lock.json').read_text(encoding='utf-8'))
    archives = {}
    for source in lock['sources']:
        expected = 'https://codeload.github.com/'+source['repository'].removeprefix('https://github.com/')+'/tar.gz/'+source['revision']
        if source['archive_url'] != expected or len(source['revision']) != 40:
            raise ValueError('SKILLS_SOURCE_NOT_PINNED')
        with urllib.request.urlopen(expected, timeout=120) as response:
            if response.url != expected:
                raise ValueError('SKILLS_ARCHIVE_REDIRECT_REFUSED')
            raw = response.read(MAX_ARCHIVE+1)
        if len(raw) > MAX_ARCHIVE or hashlib.sha256(raw).hexdigest() != source['archive_sha256']:
            raise ValueError('SKILLS_ARCHIVE_HASH_MISMATCH')
        archives[source['id']] = raw
    parent = root/'catalogs'
    parent.mkdir(exist_ok=True)
    name = lock['index_sha256']
    if len(name) != 64 or any(c not in '0123456789abcdef' for c in name):
        raise ValueError('SKILLS_INDEX_ID_INVALID')
    target = parent/name
    staging = parent/(name+'.staging')
    if staging.exists():
        if staging.is_symlink() or not staging.resolve().is_relative_to(parent.resolve()):
            raise ValueError('SKILLS_STAGING_SCOPE')
        shutil.rmtree(staging)
    staging.mkdir()
    index = assemble(lock['sources'], archives, staging)
    if hashlib.sha256(canonical(index)).hexdigest() != name or len(index['entries']) != lock['skill_count']:
        raise ValueError('SKILLS_INDEX_MISMATCH')
    if target.exists():
        if hashlib.sha256((target/'index.json').read_bytes()).hexdigest() != name:
            raise ValueError('SKILLS_EXISTING_INDEX_CONFLICT')
        # Rebuild the owned version to repair damaged content; runtime is stopped.
        shutil.rmtree(target)
    os.replace(staging, target)
    link = root/'catalog.next'
    if link.is_symlink():
        link.unlink()
    link.symlink_to(target, target_is_directory=True)
    os.replace(link, root/'catalog')
    service = root/'skills-service'
    service.mkdir(exist_ok=True)
    for name in ('catalog.py', 'server.py', 'headroom_file.py'):
        shutil.copyfile(inputs/('skills-'+name), service/name)
    plugin=root/'plugins/arcia-platform'
    plugin.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(inputs/'skills-plugin.py',plugin/'__init__.py')
    shutil.copyfile(inputs/'skills-result_compression.py',plugin/'result_compression.py')
    (plugin/'plugin.yaml').write_text('name: arcia-platform\nversion: "1.0.0"\ndescription: Local skill discovery and qualified read-only RTK integration\nauthor: ArcIA harness contributors\n',encoding='utf-8')
    return len(index['entries'])


if __name__ == '__main__':
    install()
