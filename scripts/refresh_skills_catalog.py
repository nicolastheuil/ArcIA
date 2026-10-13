"""Engineer-only public source pinning and deterministic update report.

No runtime installs. Existing immutable revisions are reused unless --latest is
explicitly selected. --write records locks for subsequent CI and K3s bootstrap.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'services/skills'))
from bundle import MAX_ARCHIVE, assemble, canonical

DEFAULTS = [
    {'id': 'hermes', 'repository': 'https://github.com/NousResearch/hermes-agent', 'revision': '818c13be1dc4fd28987e1e881a9408224afd4535',
     'roots': ['skills', 'optional-skills'], 'credit': 'Nous Research and Hermes contributors', 'license': 'MIT; individual skills may override', 'license_path': 'LICENSE'},
    {'id': 'ecc', 'repository': 'https://github.com/affaan-m/ECC', 'revision': 'b92f181b3b748d1abbc2afd94af6aa7d8c8fca29',
     'roots': ['skills'], 'credit': 'Affaan Mustafa and ECC contributors', 'license': 'MIT; individual files may override', 'license_path': 'LICENSE'},
    {'id': 'superpowers', 'repository': 'https://github.com/obra/superpowers', 'revision': 'bb92a77741419a4ab5f06e711a283343f1ada0c3',
     'roots': ['skills'], 'credit': 'Jesse Vincent and Superpowers contributors', 'license': 'MIT', 'license_path': 'LICENSE'},
    {'id': 'vercel', 'repository': 'https://github.com/vercel-labs/skills', 'revision': '671e8c320810d36fed80fac5f1a2c1bf7e82d812',
     'roots': ['skills'], 'credit': 'Vercel Labs and skills contributors', 'license': 'MIT', 'license_path': 'LICENSE'},
]


def request(url, maximum=MAX_ARCHIVE):
    req = urllib.request.Request(url, headers={'User-Agent': 'ArcIA-catalog-build'})
    with urllib.request.urlopen(req, timeout=120) as response:
        raw = response.read(maximum+1)
    if len(raw) > maximum:
        raise ValueError('PUBLIC_SOURCE_TOO_LARGE')
    return raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--latest', action='store_true', help='Check default-branch revisions; never deploy')
    parser.add_argument('--write', action='store_true', help='Write candidate locks; subsequent tests and deployment required')
    args = parser.parse_args()
    path = ROOT/'builder/skills.lock.json'
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    sources = previous.get('sources', DEFAULTS)
    cache = ROOT/'artifacts/skills-archives'
    cache.mkdir(parents=True, exist_ok=True)
    def resolve(source):
        source = dict(source)
        repo = source['repository'].removeprefix('https://github.com/')
        if args.latest:
            info = json.loads(request('https://api.github.com/repos/'+repo+'/commits?per_page=1', 1024*1024))
            source['revision'] = info[0]['sha']
        url = 'https://codeload.github.com/'+repo+'/tar.gz/'+source['revision']
        file = cache/(source['id']+'-'+source['revision']+'.tar.gz')
        raw = file.read_bytes() if file.exists() else request(url)
        sha = hashlib.sha256(raw).hexdigest()
        if not args.latest and source.get('archive_sha256') not in (None, sha):
            raise ValueError('UPSTREAM_ARCHIVE_CHANGED')
        file.write_bytes(raw)
        source.update(archive_url=url, archive_sha256=sha)
        return source, raw
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        resolved = list(pool.map(resolve, sources))
    sources = [source for source, _ in resolved]
    index = assemble(sources, {source['id']: raw for source, raw in resolved})
    digest = hashlib.sha256(canonical(index)).hexdigest()
    lock = {'schema_version': 1, 'sources': sources, 'index_sha256': digest,
            'skill_count': len(index['entries']), 'runtime_network': False,
            'memory_owner': 'hermes', 'delegation_owner': 'hermes', 'auto_hooks': False}
    if args.write:
        path.write_text(json.dumps(lock, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        (ROOT/'builder/skills-index.json').write_bytes(canonical(index)+b'\n')
    print(json.dumps({'status': 'candidate_written' if args.write else 'checked',
                     'skills': len(index['entries']), 'sources': [{ 'id': s['id'], 'count': s['count'], 'revision': s['revision']} for s in index['sources']],
                     'changed': previous.get('index_sha256') != digest, 'deployed': False}))


if __name__ == '__main__':
    main()
