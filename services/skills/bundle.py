"""Deterministic catalogue from pinned public archives; never execute upstream code."""
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path, PurePosixPath
import yaml

MAX_ARCHIVE = 160*1024*1024
MAX_FILE = 2*1024*1024
MAX_CONTENT = 96*1024*1024
TEXT_SUFFIXES = {'.md', '.txt', '.py', '.sh', '.js', '.mjs', '.ts', '.tsx', '.json', '.yaml', '.yml', '.toml', '.csv', '.html', '.css', '.svg', '.xml', '.sql', '.rst'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def unpack(source, raw):
    if len(raw) > MAX_ARCHIVE or hashlib.sha256(raw).hexdigest() != source['archive_sha256']:
        raise ValueError('SKILLS_ARCHIVE_HASH_MISMATCH')
    files = {}
    size = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        members = archive.getmembers()
        if len(members) > 100000:
            raise ValueError('SKILLS_ARCHIVE_TOO_MANY_FILES')
        for member in members:
            parts = PurePosixPath(member.name).parts
            if len(parts) < 2:
                continue
            relative = '/'.join(parts[1:])
            selected = any(relative == root or relative.startswith(root+'/') for root in source['roots'])
            licence = relative in ('LICENSE', 'LICENSE.md', 'LICENSE.txt', 'COPYING')
            if not selected and not licence:
                continue
            if member.name.startswith('/') or any(p in ('..', '.') for p in parts) or '\\' in relative or ':' in relative:
                raise ValueError('SKILLS_ARCHIVE_PATH_REFUSED')
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError('SKILLS_ARCHIVE_LINK_REFUSED')
            if member.size > MAX_FILE:
                if relative.endswith('/SKILL.md'):
                    raise ValueError('SKILLS_INSTRUCTION_TOO_LARGE')
                continue
            if not licence and PurePosixPath(relative).suffix.lower() not in TEXT_SUFFIXES and 'license' not in relative.casefold():
                continue
            content = archive.extractfile(member).read(MAX_FILE+1)
            try:
                text = content.decode('utf-8')
            except UnicodeDecodeError:
                continue
            if '\x00' in text:
                continue
            size += len(content)
            if size > MAX_CONTENT or relative in files:
                raise ValueError('SKILLS_ARCHIVE_CONTENT_REFUSED')
            files[relative] = content
    return files


def metadata(content):
    text = content.decode('utf-8-sig')
    fm = {}
    if text.startswith('---\n'):
        end = text.find('\n---', 4)
        if 0 < end < 65536:
            try:
                fm = yaml.safe_load(text[4:end]) or {}
            except yaml.YAMLError:
                fm = {}
    return fm if isinstance(fm, dict) else {}


def entry(source, path, files):
    fm = metadata(files[path+'/SKILL.md'])
    subset = {k[len(path)+1:]: hashlib.sha256(v).hexdigest() for k, v in files.items() if k.startswith(path+'/')}
    name = str(fm.get('name') or path.rsplit('/', 1)[-1])[:150]
    description = re.sub(r'\s+', ' ', str(fm.get('description') or name))[:600]
    licence_files = [k for k in subset if 'license' in PurePosixPath(k).name.casefold()]
    declared = fm.get('license')
    licence = str(declared)[:200] if declared else ('See skill licence' if licence_files else source['license'])
    licence_path = path+'/'+licence_files[0] if licence_files else source['license_path']
    return {'id': source['id']+':'+path, 'provider': source['id'], 'name': name, 'description': description,
            'path': path, 'revision': source['revision'], 'source_url': source['repository']+'/tree/'+source['revision']+'/'+path,
            'credit': source['credit'], 'license': licence,
            'license_url': source['repository']+'/blob/'+source['revision']+'/'+licence_path,
            'files': dict(sorted(subset.items())), 'qualification': 'catalogued_not_individually_qualified'}


def assemble(sources, archives, destination=None):
    entries, summaries = [], []
    for source in sources:
        files = unpack(source, archives[source['id']])
        paths = sorted(k[:-len('/SKILL.md')] for k in files if k.endswith('/SKILL.md'))
        if not paths:
            raise ValueError('SKILLS_SOURCE_EMPTY')
        items = [entry(source, path, files) for path in paths]
        entries.extend(items)
        summaries.append({k: source[k] for k in ('id', 'repository', 'revision', 'credit', 'license', 'license_path')} | {'count': len(items)})
        if destination:
            base = Path(destination)/'content'/source['id']
            for relative, content in files.items():
                target = base.joinpath(*PurePosixPath(relative).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
    index = {'schema_version': 1, 'sources': summaries, 'entries': sorted(entries, key=lambda e: e['id'])}
    if destination:
        Path(destination, 'index.json').write_bytes(canonical(index))
    return index
