"""Relire les déclarations YAML sans réintroduire un catalogue par défaut."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy
import wizard


class TestRoutingYamlReload(unittest.TestCase):
    def test_block_models_with_indentless_sequences_and_sibling_keys(self):
        source = '''llm_gateway:
  models_routing:
  - alias: synthetic-chat
    target_model: openrouter/auto
    zdr: false
    description: Description repliée
      sur deux lignes
    options:
      stops:
      - stop-one
      - stop-two
  - alias: synthetic-agent
    category: agentic
    target_model: openrouter/auto
  default_model: synthetic-chat
hermes:
  default_model: synthetic-agent
'''
        cfg = deploy.parse_simple_yaml(source)
        rows = cfg["llm_gateway"]["models_routing"]
        self.assertIsInstance(rows, list)
        self.assertEqual([r["alias"] for r in rows], ["synthetic-chat", "synthetic-agent"])
        self.assertFalse(rows[0]["zdr"])
        self.assertEqual(rows[0]["description"], "Description repliée sur deux lignes")
        self.assertEqual(rows[0]["options"]["stops"], ["stop-one", "stop-two"])
        self.assertEqual(cfg["llm_gateway"]["default_model"], "synthetic-chat")
        self.assertEqual(cfg["hermes"]["default_model"], "synthetic-agent")

    def test_indented_list_and_literal_text_keep_quotes_hashes_and_urls(self):
        cfg = deploy.parse_simple_yaml('''llm_gateway:
  models_routing:
    - alias: "synthetic # chat" # commentaire
      target_model: "openrouter/auto"
      description: |
        ligne # conservée
        seconde ligne
  endpoints:
    - https://synthetic.invalid/v1
  extra: {"enabled": true}
''')
        self.assertEqual(cfg["llm_gateway"]["models_routing"][0]["alias"], "synthetic # chat")
        self.assertIn("ligne # conservée", cfg["llm_gateway"]["models_routing"][0]["description"])
        self.assertEqual(cfg["llm_gateway"]["endpoints"], ["https://synthetic.invalid/v1"])
        self.assertEqual(cfg["llm_gateway"]["extra"], {"enabled": True})

    def test_routing_reload_without_pyyaml_keeps_the_two_saved_models(self):
        source = '''llm_gateway:
  openrouter_api_key: sk-synthetic-valid
  models_routing:
  - alias: synthetic-chat
    target_model: openrouter/auto
  - alias: synthetic-agent
    target_model: openrouter/auto
hermes:
  api_token: synthetic-token
'''
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text(source, encoding="utf-8")
            with patch.dict(sys.modules, {"yaml": None}), \
                    patch.object(wizard, "ROOT_DIR", directory), \
                    patch.object(wizard, "get_default_config_dict", return_value={
                        "network": {"public_fqdn": "", "acme_email": ""},
                        "entra_id_sso": {"cookie_secret": "synthetic-cookie"},
                        "presidio": {"master_key": "synthetic-master"}, "hermes": {}, "llm_gateway": {}}), \
                    patch.object(wizard, "resolve_env_secrets_into_config", side_effect=lambda cfg: cfg), \
                    patch.object(wizard, "get_k8s_runner") as cluster:
                for _ in range(3):
                    cfg, exists = wizard.load_config_data(str(config))
                    self.assertTrue(exists)
                    result = wizard.get_model_routing_config(cfg, include_defaults=False)
                    self.assertEqual([r["alias"] for r in result["mappings"]], ["synthetic-chat", "synthetic-agent"])
                cluster.assert_not_called()
            self.assertEqual(config.read_text(encoding="utf-8"), source)

    def test_explicit_empty_models_never_restore_legacy_defaults(self):
        cfg = {"llm_gateway": {"openrouter_api_key": "sk-synthetic-valid", "models_routing": []}}
        result = wizard.get_model_routing_config(cfg)
        self.assertEqual(len(result["mappings"]), 0)

    def test_existing_instance_without_models_does_not_receive_defaults(self):
        cfg = {"llm_gateway": {"openrouter_api_key": "sk-synthetic-valid"}}
        result = wizard.get_model_routing_config(cfg, include_defaults=False)
        self.assertEqual(len(result["mappings"]), 0)

    def test_invalid_existing_yaml_does_not_load_a_default_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text("invalid YAML without a mapping", encoding="utf-8")
            with patch.dict(sys.modules, {"yaml": None}):
                with self.assertRaisesRegex(ValueError, "configuration"):
                    wizard.load_config_data(str(config))


if __name__ == "__main__":
    unittest.main()
