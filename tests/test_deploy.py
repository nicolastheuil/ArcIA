#!/usr/bin/env python3
"""
Unit tests for ArcIA deployment engine and configuration parser.
"""

import os
import sys
import unittest
import json
import base64
from unittest.mock import MagicMock

# Ajouter scripts/ au sys.path
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "scripts"))

import deploy

class TestArcIADeploy(unittest.TestCase):

    def setUp(self):
        self.root_dir = SCRIPT_DIR
        self.config_example_path = os.path.join(self.root_dir, "arcia.config.yaml.example")
        self.env_example_path = os.path.join(self.root_dir, "arcia.env.example")

    def test_yaml_example_exists(self):
        """Vérifie que arcia.config.yaml.example existe."""
        self.assertTrue(os.path.isfile(self.config_example_path))

    def test_env_example_exists(self):
        """Vérifie que arcia.env.example existe."""
        self.assertTrue(os.path.isfile(self.env_example_path))

    def test_parse_yaml_example(self):
        """Vérifie le parsing de arcia.config.yaml.example."""
        cfg = deploy.parse_yaml_or_env(self.config_example_path)
        self.assertIsInstance(cfg, dict)
        self.assertIn("kubernetes", cfg)
        self.assertIn("network", cfg)
        self.assertIn("llm_gateway", cfg)
        self.assertIn("hermes", cfg)
        self.assertNotIn("omniroute", cfg)
        self.assertEqual(cfg["kubernetes"]["namespace"], "arcia")
        self.assertEqual(cfg["network"]["public_fqdn"], "assistant.example.org")
        self.assertEqual(cfg["llm_gateway"]["default_model"], "simple/auto")

    def test_parse_env_example(self):
        """Vérifie le parsing de arcia.env.example."""
        cfg = deploy.parse_yaml_or_env(self.env_example_path)
        self.assertIsInstance(cfg, dict)
        self.assertIn("kubernetes", cfg)
        self.assertIn("network", cfg)
        self.assertNotIn("omniroute", cfg)
        self.assertEqual(cfg["kubernetes"]["mode"], "local")
        self.assertEqual(cfg["kubernetes"]["namespace"], "arcia")
        self.assertEqual(cfg["network"]["public_fqdn"], "assistant.example.org")
        self.assertEqual(cfg["llm_gateway"]["default_model"], "simple/auto")

    def test_validation_success_with_valid_keys(self):
        """Vérifie que la validation réussit avec des clés valides."""
        cfg = deploy.parse_yaml_or_env(self.config_example_path)
        cfg["llm_gateway"]["openrouter_api_key"] = "sk-or-v1-valid-test-key-1234567890"
        cfg["network"]["public_fqdn"] = "assistant.corp.internal"
        # Ne doit lever aucune exception
        try:
            deploy.validate_config(cfg)
        except SystemExit:
            self.fail("validate_config a échoué avec une configuration valide !")

    def test_validation_fails_on_missing_fqdn(self):
        """Vérifie que l'absence de FQDN public provoque une erreur."""
        cfg = deploy.parse_yaml_or_env(self.config_example_path)
        cfg["network"]["public_fqdn"] = ""
        cfg["llm_gateway"]["openrouter_api_key"] = "sk-or-v1-valid-key"
        with self.assertRaises(SystemExit):
            deploy.validate_config(cfg)

    def test_validation_fails_on_placeholder_key(self):
        """Vérifie que la clé placeholder openrouter est détectée et rejetée."""
        cfg = deploy.parse_yaml_or_env(self.config_example_path)
        # La clé par défaut commence par sk-or-v1-xxxx
        with self.assertRaises(SystemExit):
            deploy.validate_config(cfg)

    def test_validation_allows_empty_openrouter_key(self):
        """Vérifie que la validation autorise une clé openrouter vide pour déploiement générique sans souscription."""
        cfg = deploy.parse_yaml_or_env(self.config_example_path)
        cfg["llm_gateway"]["openrouter_api_key"] = ""
        cfg["network"]["public_fqdn"] = "assistant.corp.internal"
        try:
            deploy.validate_config(cfg)
        except SystemExit:
            self.fail("validate_config a échoué avec openrouter_api_key='' !")

    def test_validation_fails_on_sso_missing_fields(self):
        """Vérifie que si SSO Entra ID est activé, tous les champs sont requis."""
        cfg = deploy.parse_yaml_or_env(self.config_example_path)
        cfg["llm_gateway"]["openrouter_api_key"] = "sk-or-v1-valid-key"
        cfg["entra_id_sso"]["enabled"] = True
        cfg["entra_id_sso"]["tenant_id"] = ""
        with self.assertRaises(SystemExit):
            deploy.validate_config(cfg)

    def test_validation_fails_on_teams_missing_fields(self):
        """Vérifie que si Teams Bot est activé, app_id et app_password sont requis."""
        cfg = deploy.parse_yaml_or_env(self.config_example_path)
        cfg["llm_gateway"]["openrouter_api_key"] = "sk-or-v1-valid-key"
        cfg["teams_bot"]["enabled"] = True
        cfg["teams_bot"]["app_id"] = ""
        with self.assertRaises(SystemExit):
            deploy.validate_config(cfg)

    def test_k8s_runner_ssh_key_handling(self):
        """Vérifie l'initialisation et le support de ssh_key dans K8sRunner."""
        runner = deploy.K8sRunner(
            mode="remote-ssh",
            ssh_node="192.168.1.100",
            ssh_user="ubuntu",
            ssh_port=2222,
            ssh_key="~/.ssh/test_nonexistent_key_123"
        )
        self.assertEqual(runner.ssh_key, "~/.ssh/test_nonexistent_key_123")
        self.assertEqual(runner.ssh_user, "ubuntu")
        self.assertEqual(runner.ssh_port, 2222)
        # Tester qu'une clé introuvable renvoie le code d'erreur 255 avec message clair
        rc, out, err = runner.run(["get", "nodes"])
        self.assertEqual(rc, 255)
        self.assertIn("Clé SSH introuvable", err)

    def test_validation_fails_on_invalid_ssh_key(self):
        """Vérifie que validate_config rejette une clé SSH introuvable sur le disque."""
        cfg = deploy.parse_yaml_or_env(self.config_example_path)
        cfg["llm_gateway"]["openrouter_api_key"] = "sk-or-v1-valid-key"
        cfg["network"]["public_fqdn"] = "assistant.corp.internal"
        cfg["kubernetes"]["mode"] = "remote-ssh"
        cfg["kubernetes"]["remote_ssh"] = {
            "node_ip": "192.168.1.50",
            "ssh_user": "ubuntu",
            "ssh_port": 22,
            "ssh_key": "/path/to/definitely_nonexistent_key.pem"
        }
        with self.assertRaises(SystemExit):
            deploy.validate_config(cfg)

    def test_parse_env_ssh_key(self):
        """Vérifie que parse_env_format extrait correctement ARCIA_K3S_SSH_KEY."""
        env_content = """ARCIA_K8S_MODE="remote-ssh"
ARCIA_K3S_NODE="192.168.1.50"
ARCIA_K3S_USER="ubuntu"
ARCIA_K3S_PORT="22"
ARCIA_K3S_SSH_KEY="~/.ssh/custom_key"
"""
        parsed = deploy.parse_env_format(env_content)
        self.assertEqual(parsed["kubernetes"]["remote_ssh"]["ssh_key"], "~/.ssh/custom_key")
        self.assertEqual(parsed["kubernetes"]["remote_ssh"]["ssh_user"], "ubuntu")

    def test_sync_service_configmaps_includes_litellm_error_handler(self):
        """Vérifie que sync_service_configmaps intègre litellm-error-handler."""
        class DummyRunner:
            def __init__(self):
                self.applied = []
            def apply_manifest(self, manifest_yaml):
                self.applied.append(manifest_yaml)

        runner = DummyRunner()
        checksums = deploy.sync_service_configmaps(runner, "arcia", self.root_dir)
        self.assertIn("litellm-error-handler", checksums)
        self.assertIn("presidio-code", checksums)
        self.assertIn("teams-bot-code", checksums)
        self.assertIn("hermes-governance-plugin", checksums)
        applied_names = "\n".join(runner.applied)
        self.assertIn("name: litellm-error-handler", applied_names)
        self.assertIn("error_handler.py: |", applied_names)

    def test_sync_webui_branding_includes_model_icons(self):
        """Vérifie que sync_webui_branding intègre les icônes de modèles SVG et models-branding.json."""
        class DummyRunner:
            def __init__(self):
                self.applied = []
            def apply_manifest(self, manifest_yaml):
                self.applied.append(manifest_yaml)

        runner = DummyRunner()
        mb_path = os.path.join(self.root_dir, "assets", "branding", "models-branding.json")
        orig_mb = None
        if os.path.isfile(mb_path):
            with open(mb_path, "r", encoding="utf-8") as f:
                orig_mb = f.read()

        try:
            deploy.sync_webui_branding(runner, "arcia", self.root_dir)
            applied = "\n".join(runner.applied)
            self.assertIn("name: arcia-webui-branding", applied)
            self.assertIn("icon-model-default.svg: |", applied)
            self.assertIn("icon-model-local.svg: |", applied)
            self.assertIn("icon-model-zdr.svg: |", applied)
            self.assertIn("models-branding.json: |", applied)
        finally:
            if orig_mb is not None:
                with open(mb_path, "w", encoding="utf-8") as f:
                    f.write(orig_mb)

    def test_compute_models_branding_dict(self):
        """Vérifie le calcul dynamique du dictionnaire d'icônes de modèles."""
        cfg = {
            "llm_gateway": {
                "models_routing": [
                    {"name": "local-llama", "provider": "ollama", "target_model": "ollama/llama3", "zdr": False},
                    {"name": "cloud-claude", "provider": "openrouter", "target_model": "openrouter/anthropic/claude-3.5-haiku", "zdr": True},
                    {"name": "custom-std", "provider": "openai", "target_model": "openai/gpt-4o", "zdr": False}
                ]
            }
        }
        res = deploy.compute_models_branding_dict(cfg=cfg, root_dir=self.root_dir)
        models = res.get("models", {})
        self.assertEqual(models["local-llama"]["type"], "local")
        self.assertEqual(models["local-llama"]["icon"], "/static/icon-model-local.svg")
        self.assertEqual(models["cloud-claude"]["type"], "zdr")
        self.assertEqual(models["cloud-claude"]["icon"], "/static/icon-model-zdr.svg")
        self.assertEqual(models["custom-std"]["type"], "default")
        self.assertEqual(models["custom-std"]["icon"], "/static/icon-model-default.svg")

    def test_build_litellm_config_data(self):
        """Vérifie la génération dynamique de la configuration YAML de LiteLLM avec profils et modèles."""
        cfg = {
            "llm_gateway": {
                "default_model": "simple/auto",
                "models_routing": [
                    {
                        "alias": "simple/claude",
                        "target_model": "openrouter/anthropic/claude-3.5-haiku",
                        "category": "simple",
                        "zdr": True
                    },
                    {
                        "alias": "agentic/coding",
                        "target_model": "openrouter/deepseek/deepseek-chat",
                        "category": "agentic",
                        "zdr": False
                    }
                ]
            },
            "hermes": {
                "default_model": "agentic/coding"
            }
        }
        res_yaml = deploy.build_litellm_config_data(cfg)
        self.assertIsInstance(res_yaml, str)

        # Vérifier salt_key dans general_settings
        self.assertIn("salt_key: os.environ/LITELLM_SALT_KEY", res_yaml)
        self.assertIn("store_model_in_db: false", res_yaml)

        # Vérifier que les modèles et alias canoniques sont présents
        self.assertIn('model_name: "simple/claude"', res_yaml)
        self.assertIn('model_name: "agentic/coding"', res_yaml)
        self.assertIn('"agentic/auto":', res_yaml)
        self.assertIn("presidio-dlp.arcia.svc", res_yaml)

    def test_make_secret_manifest_tls(self):
        """Vérifie la génération d'un secret Kubernetes de type TLS avec blocs littéraux."""
        data = {
            "tls.crt": "-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----\n",
            "tls.key": "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n"
        }
        manifest = deploy.make_secret_manifest("arcia-tls-cert", "arcia", data, secret_type="kubernetes.io/tls")
        self.assertIn("type: kubernetes.io/tls", manifest)
        self.assertIn("tls.crt: |", manifest)
        self.assertIn("tls.key: |", manifest)

    def test_get_existing_cluster_secret_hyphenated_keys(self):
        """Vérifie l'extraction sécurisée de clés avec tirets depuis le secret cluster JSON."""
        fake_secret_json = json.dumps({
            "data": {
                "master-key": base64.b64encode(b"sk-secret-12345").decode("utf-8"),
                "salt-key": base64.b64encode(b"salt-abcdef").decode("utf-8"),
                "db-password": base64.b64encode(b"pg-pass-987").decode("utf-8")
            }
        })
        runner = MagicMock()
        runner.run.return_value = (0, fake_secret_json, "")

        key = deploy.get_existing_cluster_secret(runner, "arcia", "litellm-secret", "master-key")
        self.assertEqual(key, "sk-secret-12345")

        salt = deploy.get_existing_cluster_secret(runner, "arcia", "litellm-secret", "salt-key")
        self.assertEqual(salt, "salt-abcdef")

if __name__ == "__main__":
    unittest.main()
