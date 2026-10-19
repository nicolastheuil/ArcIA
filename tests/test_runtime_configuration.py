"""Persistance des identités générées : fixtures synthétiques isolées."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy
from services.instance_backup.configuration import dump_mapping, persist_runtime_configuration


class TestRuntimeConfiguration(unittest.TestCase):
    def test_unknown_fields_and_generated_identity_roundtrip_without_yaml_dependency(self):
        cfg = {"llm_gateway": {"master_key": "sk-synthetic", "salt_key": "synthetic-salt", "db_password": "synthetic-password"},
               "custom": {"nested": [{"scope": ["synthetic"]}]},
               "instance_backup": {"passphrase": "must-not-export", "repo_url": "https://github.com/example/synthetic.git"}}
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {"yaml": None}):
            persist_runtime_configuration(directory, cfg)
            actual = deploy.parse_simple_yaml(Path(directory, "arcia.config.yaml").read_text(encoding="utf-8"))
        self.assertEqual(actual["custom"], cfg["custom"])
        self.assertEqual(actual["llm_gateway"], cfg["llm_gateway"])
        self.assertNotIn("passphrase", actual["instance_backup"])
        self.assertIn("passphrase", cfg["instance_backup"])

    def test_replace_failure_keeps_previous_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "arcia.config.yaml")
            path.write_text("previous: true\n")
            with patch("services.instance_backup.configuration.os.replace", side_effect=OSError()), self.assertRaises(RuntimeError):
                persist_runtime_configuration(directory, {"new": True})
            self.assertEqual(path.read_text(), "previous: true\n")
