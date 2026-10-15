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
        self.assertEqual(cfg["kubernetes"]["namespace"], "arcia")
        self.assertEqual(cfg["network"]["public_fqdn"], "assistant.example.org")

    def test_parse_env_example(self):
        """Vérifie le parsing de arcia.env.example."""
        cfg = deploy.parse_yaml_or_env(self.env_example_path)
        self.assertIsInstance(cfg, dict)
        self.assertIn("kubernetes", cfg)
        self.assertIn("network", cfg)
        self.assertEqual(cfg["kubernetes"]["mode"], "local")
        self.assertEqual(cfg["kubernetes"]["namespace"], "arcia")
        self.assertEqual(cfg["network"]["public_fqdn"], "assistant.example.org")

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


if __name__ == "__main__":
    unittest.main()
