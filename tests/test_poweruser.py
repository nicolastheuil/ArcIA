#!/usr/bin/env python3
"""
Unit tests for ArcIA Power User Kubernetes Spawner (scripts/arcia_poweruser.py).
Validates slug conversion, template rendering, isolation, and manifest structure.
"""

import os
import unittest
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))

from arcia_poweruser import email_to_slug, render_manifest, TEMPLATE_PATH


class TestPowerUserSpawner(unittest.TestCase):

    def test_email_to_slug_basic(self):
        self.assertEqual(email_to_slug("claire.dubois@entreprise.com"), "claire-dubois")
        self.assertEqual(email_to_slug("nicolas.theuil@arcitek.fr"), "nicolas-theuil")
        self.assertEqual(email_to_slug("jean-pierre.martin@domaine.org"), "jean-pierre-martin")

    def test_email_to_slug_special_characters(self):
        slug = email_to_slug("user+test_01.dev@company.com")
        self.assertTrue(slug.isalnum() or "-" in slug)
        self.assertNotIn("+", slug)
        self.assertNotIn("_", slug)

    def test_template_file_exists(self):
        self.assertTrue(os.path.isfile(TEMPLATE_PATH), f"Template non trouvé sur {TEMPLATE_PATH}")

    def test_render_manifest_contains_required_resources(self):
        rendered = render_manifest(
            user_email="claire.dubois@entreprise.com",
            team="finance",
            job_title="Contrôleuse de Gestion",
            manager="Marc Lefèvre",
            storage_size="15Gi",
            public_fqdn="assistant.acme.corp",
            namespace="arcia"
        )

        # 1. Vérification des ressources Kubernetes
        self.assertIn("kind: PersistentVolumeClaim", rendered)
        self.assertIn("name: hermes-user-claire-dubois-pvc", rendered)
        self.assertIn("storage: 15Gi", rendered)

        self.assertIn("kind: ConfigMap", rendered)
        self.assertIn("name: hermes-user-claire-dubois-config", rendered)
        self.assertIn("SOUL.md:", rendered)
        self.assertIn("USER.md:", rendered)
        self.assertIn("Contrôleuse de Gestion", rendered)
        self.assertIn("Marc Lefèvre", rendered)

        self.assertIn("kind: Secret", rendered)
        self.assertIn("name: hermes-user-claire-dubois-secret", rendered)

        self.assertIn("kind: Deployment", rendered)
        self.assertIn("name: hermes-poweruser-claire-dubois", rendered)
        self.assertIn("image: nousresearch/hermes-agent:latest", rendered)
        self.assertIn("HERMES_HOME", rendered)
        self.assertIn("http://litellm-proxy.arcia.svc:4000/v1", rendered)

        self.assertIn("kind: Service", rendered)
        self.assertIn("name: hermes-poweruser-claire-dubois", rendered)

        self.assertIn("kind: Ingress", rendered)
        self.assertIn("name: hermes-poweruser-claire-dubois-ingress", rendered)
        self.assertIn("/poweruser/claire-dubois/studio", rendered)
        self.assertIn("host: assistant.acme.corp", rendered)

    def test_custom_soul_injection(self):
        custom_soul = """# Custom Soul
Tu es l'agent dédié au trading algorithmique haute fréquence.
Ne fais aucune concession sur la latence.
"""
        rendered = render_manifest(
            user_email="trader.one@hedgefund.com",
            custom_soul=custom_soul
        )
        self.assertIn("trading algorithmique haute fréquence", rendered)
        self.assertIn("Ne fais aucune concession sur la latence", rendered)

    def test_render_manifest_vpn_disabled_by_default(self):
        rendered = render_manifest(
            user_email="standard.user@company.com",
            enable_vpn=False
        )
        self.assertNotIn("NET_ADMIN", rendered)
        self.assertNotIn("dev-net-tun", rendered)

    def test_render_manifest_vpn_enabled(self):
        rendered = render_manifest(
            user_email="network.admin@company.com",
            enable_vpn=True
        )
        self.assertIn("NET_ADMIN", rendered)
        self.assertIn("dev-net-tun", rendered)
        self.assertIn("openconnect", rendered)

    def test_render_manifest_contains_agentic_models_catalog(self):
        rendered = render_manifest(user_email="dev.lead@company.com")
        self.assertIn("ArcIA Agentic", rendered)
        self.assertIn("discover_models: false", rendered)
        self.assertIn("agentic/auto", rendered)
        self.assertIn("agentic/free", rendered)
        self.assertIn("agentic/deepseek-v4.1-flash", rendered)

    def test_render_manifest_init_container_config_sync(self):
        rendered = render_manifest(user_email="dev.lead@company.com")
        self.assertIn("hermes_yaml", rendered)
        self.assertIn("init-user-state", rendered)
        self.assertIn("providers", rendered)


if __name__ == "__main__":
    unittest.main()

