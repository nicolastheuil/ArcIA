#!/usr/bin/env python3
"""
Unit tests for ArcIA Setup Wizard (scripts/wizard.py).
"""

import os
import sys
import unittest
import tempfile
import json

# Ajouter scripts/ au sys.path
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "scripts"))

import wizard
import deploy

class TestArcIAWizard(unittest.TestCase):

    def setUp(self):
        self.root_dir = SCRIPT_DIR
        self.config_example_path = os.path.join(self.root_dir, "arcia.config.yaml.example")

    def test_generate_token_kinds(self):
        """Vérifie la génération de tokens cryptographiques pour chaque usage."""
        pat = wizard.generate_token("pat")
        self.assertTrue(pat.startswith("arcia-pat-"))
        self.assertGreater(len(pat), 20)

        cookie = wizard.generate_token("cookie")
        self.assertGreater(len(cookie), 30)

        admin = wizard.generate_token("admin")
        self.assertGreater(len(admin), 10)

        presidio = wizard.generate_token("presidio")
        self.assertTrue(presidio.startswith("arcia-master-"))

        # Vérifier l'entropie (deux appels ne produisent pas le même token)
        pat2 = wizard.generate_token("pat")
        self.assertNotEqual(pat, pat2)

    def test_default_config_structure(self):
        """Vérifie que la configuration par défaut contient toutes les sections nécessaires."""
        cfg = wizard.get_default_config_dict()
        required_sections = [
            "kubernetes", "network", "llm_gateway", "hermes",
            "presidio", "open_webui", "entra_id_sso", "teams_bot", "omniroute"
        ]
        for section in required_sections:
            self.assertIn(section, cfg, f"Section manquante : {section}")

        # Vérifier que les composants internes sont activés par défaut
        self.assertTrue(cfg["presidio"]["enabled"])
        self.assertTrue(cfg["open_webui"]["enabled"])
        # Vérifier que les composants optionnels sont désactivés par défaut
        self.assertFalse(cfg["entra_id_sso"]["enabled"])
        self.assertFalse(cfg["teams_bot"]["enabled"])
        self.assertFalse(cfg["omniroute"]["enabled"])

    def test_ensure_config_defaults_cleans_placeholders(self):
        """Vérifie que ensure_config_defaults nettoie les placeholders d'exemple."""
        cfg = wizard.get_default_config_dict()
        cfg["network"]["public_fqdn"] = "assistant.example.org"
        cfg["network"]["acme_email"] = "admin@example.org"
        cfg["llm_gateway"]["openrouter_api_key"] = "sk-or-v1-xxxx123"

        cleaned = wizard.ensure_config_defaults(cfg)
        self.assertEqual(cleaned["network"]["public_fqdn"], "")
        self.assertEqual(cleaned["network"]["acme_email"], "")
        self.assertEqual(cleaned["llm_gateway"]["openrouter_api_key"], "")

    def test_serialize_and_parse_roundtrip(self):
        """Vérifie que la sérialisation YAML du Wizard est parfaitement ré-analysable par deploy.py."""
        cfg = wizard.get_default_config_dict()
        cfg["network"]["public_fqdn"] = "assistant.corp.internal"
        cfg["network"]["acme_email"] = "ops@corp.internal"
        cfg["llm_gateway"]["openrouter_api_key"] = "sk-or-v1-real-key-123456789"
        cfg["entra_id_sso"]["enabled"] = True
        cfg["entra_id_sso"]["tenant_id"] = "tenant-uuid-123"
        cfg["teams_bot"]["enabled"] = True
        cfg["teams_bot"]["app_id"] = "bot-appid-123"

        yaml_output = wizard.serialize_yaml_config(cfg)
        self.assertIn('public_fqdn: "assistant.corp.internal"', yaml_output)
        self.assertIn('tenant_id: "tenant-uuid-123"', yaml_output)
        self.assertIn('app_id: "bot-appid-123"', yaml_output)

        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".yaml", encoding="utf-8") as tmp:
            tmp_path = tmp.name
            tmp.write(yaml_output)

        try:
            parsed = deploy.parse_yaml_or_env(tmp_path)
            self.assertEqual(parsed["network"]["public_fqdn"], "assistant.corp.internal")
            self.assertEqual(parsed["llm_gateway"]["openrouter_api_key"], "sk-or-v1-real-key-123456789")
            self.assertTrue(parsed["entra_id_sso"]["enabled"])
            self.assertEqual(parsed["entra_id_sso"]["tenant_id"], "tenant-uuid-123")
            self.assertTrue(parsed["teams_bot"]["enabled"])
            self.assertEqual(parsed["teams_bot"]["app_id"], "bot-appid-123")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_html_page_contains_all_screens_and_guides(self):
        """Vérifie que la page HTML du Wizard contient les 11 écrans et les liens documentaires."""
        html = wizard.get_wizard_html_page()
        for i in range(1, 12):
            self.assertIn(f'id="step{i}"', html, f"Écran manquant : step{i}")

        # Vérifier la présence des guides pas-à-pas et des liens GitHub
        self.assertIn("portail-webui-entraid.md#creation-app-entraid", html)
        self.assertIn("integration-teams.md#creation-azure-bot", html)
        self.assertIn("Presidio DLP", html)
        self.assertIn("Graphify", html)
        self.assertIn("Ponytail", html)
        self.assertIn("Public-APIs", html)
        self.assertIn("ArcIA-instance-", html)

    def test_find_available_port(self):
        """Vérifie que la détection d'un port disponible fonctionne."""
        port = wizard.find_available_port(8765)
        self.assertIsInstance(port, int)
        self.assertGreaterEqual(port, 8765)

    def test_encrypt_and_decrypt_instance_bundle_roundtrip(self):
        """Vérifie le cycle complet de chiffrement et déchiffrement des secrets d'instance."""
        secrets_payload = {
            "llm_gateway": {"openrouter_api_key": "sk-or-v1-secret-key-xyz987"},
            "entra_id_sso": {"client_secret": "my-ultra-secret-azure-client-key"},
            "teams_bot": {"app_password": "super-strong-teams-bot-password"},
            "open_webui": {"admin_password": "custom-admin-password-1234"},
        }
        passphrase = "Master-Enterprise-Passphrase-2026!"

        encrypted_bundle = wizard.encrypt_instance_bundle(secrets_payload, passphrase)
        self.assertIn("schema", encrypted_bundle)
        self.assertIn("algo", encrypted_bundle)
        self.assertIn("salt", encrypted_bundle)
        self.assertIn("nonce", encrypted_bundle)
        self.assertIn("ciphertext", encrypted_bundle)

        # Vérifier que les secrets bruts ne figurent nulle part en clair dans le bundle chiffré
        bundle_str = json.dumps(encrypted_bundle)
        self.assertNotIn("sk-or-v1-secret-key-xyz987", bundle_str)
        self.assertNotIn("my-ultra-secret-azure-client-key", bundle_str)
        self.assertNotIn("super-strong-teams-bot-password", bundle_str)

        # Déchiffrement avec la bonne passphrase
        decrypted_payload = wizard.decrypt_instance_bundle(encrypted_bundle, passphrase)
        self.assertEqual(decrypted_payload, secrets_payload)
        self.assertEqual(decrypted_payload["llm_gateway"]["openrouter_api_key"], "sk-or-v1-secret-key-xyz987")
        self.assertEqual(decrypted_payload["entra_id_sso"]["client_secret"], "my-ultra-secret-azure-client-key")

    def test_decrypt_instance_bundle_invalid_passphrase(self):
        """Vérifie que le déchiffrement avec un mot de passe erroné lève une exception ValueError."""
        secrets_payload = {"key": "secret-value"}
        passphrase = "Valid-Passphrase-123"
        encrypted_bundle = wizard.encrypt_instance_bundle(secrets_payload, passphrase)

        with self.assertRaises(ValueError):
            wizard.decrypt_instance_bundle(encrypted_bundle, "Wrong-Passphrase-999")


if __name__ == "__main__":
    unittest.main()
