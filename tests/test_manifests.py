#!/usr/bin/env python3
"""
Manifest validation test: checks all deploy/manifests/*.yaml files,
including behavioral consistency, model tiers, and security constraints for v0.3.
"""

import os
import unittest
import glob

class TestKubernetesManifests(unittest.TestCase):

    def setUp(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.manifests_dir = os.path.join(root_dir, "deploy", "manifests")

    def test_manifests_directory_exists(self):
        self.assertTrue(os.path.isdir(self.manifests_dir))

    def test_all_manifests_are_non_empty(self):
        yaml_files = glob.glob(os.path.join(self.manifests_dir, "*.yaml"))
        self.assertGreaterEqual(len(yaml_files), 7, "Au moins 7 manifestes Kubernetes attendus.")
        for yf in yaml_files:
            with open(yf, "r", encoding="utf-8") as f:
                content = f.read().strip()
            self.assertGreater(len(content), 20, f"Le fichier {yf} est anormalement court ou vide.")

    def test_manifests_contain_apiversion_and_kind(self):
        yaml_files = glob.glob(os.path.join(self.manifests_dir, "*.yaml"))
        for yf in yaml_files:
            with open(yf, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("apiVersion:", content, f"apiVersion manquant dans {yf}")
            self.assertIn("kind:", content, f"kind manquant dans {yf}")
            self.assertIn("metadata:", content, f"metadata manquant dans {yf}")

    def test_litellm_v03_configuration(self):
        """Vérifie la présence des 3 paliers v0.3, des fallbacks valides et de la sécurité."""
        litellm_path = os.path.join(self.manifests_dir, "05-litellm.yaml")
        with open(litellm_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("arcia/standard", content)
        self.assertIn("arcia/expert", content)
        self.assertIn("arcia/reasoning", content)
        # Modèle déprécié retiré
        self.assertNotIn("openrouter/anthropic/claude-3.5-sonnet\n", content)
        # Fallbacks bien placés dans router_settings
        self.assertIn("router_settings:\n      fallbacks:", content)
        # Variable d'insécurité supprimée
        self.assertNotIn("LITELLM_DANGEROUSLY_PERMIT_WEAK_OR_UNSET_MASTER_KEY", content)
        self.assertIn("LITELLM_MASTER_KEY", content)
        self.assertIn("DATABASE_URL", content)

    def test_open_webui_v03_security(self):
        """Vérifie que les connexions directes contournant le DLP sont désactivées."""
        webui_path = os.path.join(self.manifests_dir, "07-open-webui.yaml")
        with open(webui_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('name: ENABLE_DIRECT_CONNECTIONS\n          value: "false"', content)
        self.assertIn('name: ENABLE_FORWARD_USER_INFO_HEADERS\n          value: "true"', content)
        self.assertIn('name: DEFAULT_MODELS\n          value: "arcia/standard"', content)

    def test_hermes_native_config(self):
        """Vérifie que Hermes utilise ~/.hermes/config.yaml et non les variables OPENAI_API_BASE obsolètes."""
        hermes_path = os.path.join(self.manifests_dir, "06-hermes-agent.yaml")
        with open(hermes_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("provider: custom", content)
        self.assertIn("base_url: http://litellm-proxy.arcia.svc:4000/v1", content)
        self.assertNotIn("OPENAI_API_BASE", content)
        self.assertNotIn("OPENAI_MODEL_NAME", content)
        self.assertNotIn("arcia_tokenmaxing.py", content)

    def test_litellm_db_manifest_present(self):
        """Vérifie que la base comptable LiteLLM PostgreSQL est déclarée."""
        db_path = os.path.join(self.manifests_dir, "05-litellm-db.yaml")
        self.assertTrue(os.path.isfile(db_path))
        with open(db_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("kind: StatefulSet", content)
        self.assertIn("name: litellm-db", content)


if __name__ == "__main__":
    unittest.main()
