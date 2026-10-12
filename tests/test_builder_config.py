"""Synthetic protection tests for the narrow Codex configuration update."""
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from register_builder_mcp import register


class BuilderConfigTests(unittest.TestCase):
    def test_preserves_other_settings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.toml'
            path.write_text('model = "synthetic-model"\n[mcp_servers.other]\nurl = "https://example.invalid/mcp"\n',encoding='utf-8')
            value={'config_path':str(path),'node':'C:\\synthetic path\\node.exe','entry':'C:\\synthetic path\\index.js'}
            register(value)
            first=path.read_bytes()
            config=tomllib.loads(first.decode())
            self.assertEqual(config['model'],'synthetic-model')
            self.assertEqual(config['mcp_servers']['other']['url'],'https://example.invalid/mcp')
            self.assertEqual(config['mcp_servers']['arcia_context7']['args'],[value['entry']])
            register(value)
            self.assertEqual(first,path.read_bytes())

    def test_conflicting_table_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.toml'
            original=b'[mcp_servers.arcia_context7]\ncommand = "foreign-command"\n'
            path.write_bytes(original)
            with self.assertRaises(ValueError):
                register({'config_path':str(path),'node':'node','entry':'pinned.js'})
            self.assertEqual(original,path.read_bytes())

    def test_invalid_existing_config_stays_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.toml'
            original=b'[[ broken config'
            path.write_bytes(original)
            with self.assertRaises(tomllib.TOMLDecodeError):
                register({'config_path':str(path),'node':'node','entry':'pinned.js'})
            self.assertEqual(original,path.read_bytes())


if __name__=='__main__':
    unittest.main()
