import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'services/skills'))
import bundle
import catalog
import server


def fixture(link=False, traversal=False):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        files = {'repo/skills/research/SKILL.md': b'---\nname: research\ndescription: Research documents\n---\n# Research\n',
                 'repo/skills/research/references/a.md': b'Local reference',
                 'repo/LICENSE': b'MIT Copyright synthetic author'}
        if traversal:
            files['repo/skills/../../outside.txt'] = b'no'
        for name, raw in files.items():
            member = tarfile.TarInfo(name);member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
        if link:
            member = tarfile.TarInfo('repo/skills/research/escape.md');member.type = tarfile.SYMTYPE;member.linkname = '/etc/passwd'
            archive.addfile(member)
    raw = stream.getvalue()
    source = {'id': 'synthetic', 'repository': 'https://github.com/example/catalog', 'revision': 'a'*40,
              'credit': 'Synthetic author', 'license': 'MIT', 'license_path': 'LICENSE',
              'roots': ['skills'], 'archive_sha256': hashlib.sha256(raw).hexdigest()}
    return source, raw


class SkillCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source, raw = fixture()
        self.index = bundle.assemble([source], {'synthetic': raw}, self.root)
        self.catalog = catalog.Catalog(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_discovery_returns_metadata_without_loading_instructions(self):
        result = self.catalog.search('recherche')
        self.assertEqual(result['total'], 1)
        self.assertFalse(result['instructions_loaded'])
        self.assertNotIn('content', result['matches'][0])

    def test_load_returns_credit_licence_and_reference(self):
        identifier = self.index['entries'][0]['id']
        self.assertIn('# Research', self.catalog.load(identifier)['content'])
        self.assertEqual(self.catalog.load(identifier, 'references/a.md')['content'], 'Local reference')
        self.assertEqual(self.catalog.load(identifier)['skill']['license'], 'MIT')
        self.assertIn('Hermes', str(self.catalog.load(identifier)['function_owners']))

    def test_unknown_id_and_unlisted_paths_cannot_read_private_files(self):
        for identifier, path in [('unknown:one', 'SKILL.md'), (self.index['entries'][0]['id'], '../../secret'),
                                 (self.index['entries'][0]['id'], '/etc/passwd'), (self.index['entries'][0]['id'], 'C:\\secret')]:
            with self.assertRaises(ValueError):
                self.catalog.load(identifier, path)

    def test_tampered_skill_is_not_loaded(self):
        target = self.root/'content/synthetic/skills/research/SKILL.md'
        target.write_text('tampered', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            self.catalog.load(self.index['entries'][0]['id'])

    def test_archive_rejects_symlinks_and_traversal(self):
        for kwargs in ({'link': True}, {'traversal': True}):
            source, raw = fixture(**kwargs)
            with self.assertRaises(ValueError):
                bundle.unpack(source, raw)

    def test_archive_hash_and_empty_source_are_refused(self):
        source, raw = fixture()
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            bundle.unpack(source, raw+b'changed')
        source['roots'] = ['empty']
        with self.assertRaisesRegex(ValueError, 'SOURCE_EMPTY'):
            bundle.assemble([source], {'synthetic': raw})

    def test_mcp_discovery_load_and_no_arbitrary_install_tool(self):
        self.assertEqual(len(server.dispatch({'method': 'tools/list'}, self.catalog)['tools']), 3)
        result = server.dispatch({'method': 'tools/call', 'params': {'name': 'catalog_search', 'arguments': {'query': 'research'}}}, self.catalog)
        identifier = json.loads(result['content'][0]['text'])['matches'][0]['id']
        loaded = server.dispatch({'method': 'tools/call', 'params': {'name': 'catalog_load', 'arguments': {'id': identifier}}}, self.catalog)
        self.assertIn('# Research', json.loads(loaded['content'][0]['text'])['content'])
        for name, args in [('install', {}), ('catalog_search', {'url': 'https://example.invalid'}), ('catalog_load', {})]:
            with self.assertRaises(ValueError):
                server.dispatch({'method': 'tools/call', 'params': {'name': name, 'arguments': args}}, self.catalog)

    def test_search_is_bounded_and_provider_scoped(self):
        self.assertEqual(self.catalog.search('research', 'other')['total'], 0)
        for limit in (0, 31, True):
            with self.assertRaises(ValueError):
                self.catalog.search('research', limit=limit)

    def test_rebuild_is_deterministic_and_locks_match(self):
        lock = json.loads((ROOT/'builder/skills.lock.json').read_text(encoding='utf-8'))
        index = json.loads((ROOT/'builder/skills-index.json').read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256(bundle.canonical(index)).hexdigest(), lock['index_sha256'])
        self.assertEqual(len(index['entries']), lock['skill_count'])
        self.assertEqual({s['id'] for s in index['sources']}, {'hermes', 'ecc', 'superpowers', 'vercel'})
        self.assertTrue(all(e['credit'] and e['license_url'] for e in index['entries']))


if __name__ == '__main__':
    unittest.main()
