#!/usr/bin/env python3
"""
Unit tests for ArcIA deployment engine and configuration parser.
"""

import os
import sys
import unittest

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
        self.assertIn("omniroute", cfg)
        self.assertEqual(cfg["kubernetes"]["namespace"], "arcia")
        self.assertEqual(cfg["network"]["public_fqdn"], "assistant.example.org")
        self.assertFalse(cfg["omniroute"]["enabled"])

    def test_parse_env_example(self):
        """Vérifie le parsing de arcia.env.example."""
        cfg = deploy.parse_yaml_or_env(self.env_example_path)
        self.assertIsInstance(cfg, dict)
        self.assertIn("kubernetes", cfg)
        self.assertIn("network", cfg)
        self.assertIn("omniroute", cfg)
        self.assertEqual(cfg["kubernetes"]["mode"], "local")
        self.assertEqual(cfg["kubernetes"]["namespace"], "arcia")
        self.assertEqual(cfg["network"]["public_fqdn"], "assistant.example.org")
        self.assertFalse(cfg["omniroute"]["enabled"])

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

if __name__ == "__main__":
    unittest.main()
