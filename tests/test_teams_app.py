#!/usr/bin/env python3
"""
Unit tests for the ArcIA Microsoft Teams application package and builder.
"""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.package_teams_app import (
    build_teams_package,
    get_png_dimensions,
    validate_manifest,
)


class TestTeamsAppPackage(unittest.TestCase):
    def setUp(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.assets_dir = self.project_root / "assets" / "teams"
        self.manifest_path = self.assets_dir / "manifest.json"
        self.color_png = self.assets_dir / "color.png"
        self.outline_png = self.assets_dir / "outline.png"
        self.zip_path = self.assets_dir / "arcia-teams-app.zip"
        if not self.zip_path.is_file():
            build_teams_package(
                manifest_path=self.manifest_path,
                icons_dir=self.assets_dir,
                output_zip=self.zip_path,
            )

    def test_official_manifest_structure_and_validity(self):
        """Vérifie que le manifest.json officiel d'ArcIA est valide selon les specs Microsoft Teams v1.25+."""
        self.assertTrue(self.manifest_path.is_file(), "manifest.json doit exister")
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        errors = validate_manifest(manifest)
        self.assertEqual(errors, [], f"Le manifeste officiel contient des erreurs : {errors}")
        self.assertEqual(manifest.get("manifestVersion"), "1.25")
        self.assertEqual(manifest.get("supportsChannelFeatures"), "tier1")
        self.assertEqual(manifest.get("name", {}).get("short"), "ArcIA")
        self.assertTrue(len(manifest.get("bots", [])) > 0, "Le bot doit être déclaré")
        self.assertIn("personal", manifest["bots"][0]["scopes"])
        self.assertIn("team", manifest["bots"][0]["scopes"])

    def test_official_icons_dimensions(self):
        """Vérifie que les icônes officielles respectent strictement les résolutions Teams."""
        self.assertTrue(self.color_png.is_file(), "color.png doit exister")
        self.assertTrue(self.outline_png.is_file(), "outline.png doit exister")

        c_w, c_h = get_png_dimensions(self.color_png)
        self.assertEqual((c_w, c_h), (192, 192), "color.png doit être de dimensions 192x192")

        o_w, o_h = get_png_dimensions(self.outline_png)
        self.assertEqual((o_w, o_h), (32, 32), "outline.png doit être de dimensions 32x32")

    def test_official_zip_archive_structure(self):
        """Vérifie que l'archive arcia-teams-app.zip contient les bons fichiers directement à la racine."""
        self.assertTrue(self.zip_path.is_file(), "L'archive arcia-teams-app.zip doit être générée")
        with zipfile.ZipFile(self.zip_path, "r") as zf:
            names = set(zf.namelist())
            expected = {"manifest.json", "color.png", "outline.png"}
            self.assertEqual(names, expected, "L'archive doit contenir exactement les 3 fichiers à la racine")

            manifest_content = json.loads(zf.read("manifest.json").decode("utf-8"))
            self.assertIn("id", manifest_content)
            self.assertEqual(manifest_content.get("manifestVersion"), "1.25")
            self.assertEqual(manifest_content.get("supportsChannelFeatures"), "tier1")
            self.assertIn("bots", manifest_content)

    def test_build_teams_package_with_custom_bot_id_and_domain(self):
        """Vérifie la personnalisation dynamique du package (botId, fqdn, nom)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_zip = Path(tmpdir) / "custom-app.zip"
            custom_bot_id = "11111111-2222-3333-4444-555555555555"
            custom_domain = "assistant.mycompany.org"

            build_teams_package(
                manifest_path=self.manifest_path,
                icons_dir=self.assets_dir,
                output_zip=tmp_zip,
                bot_id=custom_bot_id,
                short_name="ArcIA-Prod",
                domain=custom_domain,
            )

            self.assertTrue(tmp_zip.is_file())
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                data = json.loads(zf.read("manifest.json").decode("utf-8"))
                self.assertEqual(data["bots"][0]["botId"], custom_bot_id)
                self.assertEqual(data["name"]["short"], "ArcIA-Prod")
                self.assertEqual(data.get("supportsChannelFeatures"), "tier1")
                self.assertIn(custom_domain, data.get("validDomains", []))

    def test_build_teams_package_no_bot_mode(self):
        """Vérifie que le mode no_bot retire bien la section bots pour l'import direct sans validation préalable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_zip = Path(tmpdir) / "no-bot-app.zip"
            build_teams_package(
                manifest_path=self.manifest_path,
                icons_dir=self.assets_dir,
                output_zip=tmp_zip,
                no_bot=True,
            )
            self.assertTrue(tmp_zip.is_file())
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                data = json.loads(zf.read("manifest.json").decode("utf-8"))
                self.assertNotIn("bots", data)
                self.assertEqual(data.get("manifestVersion"), "1.25")
                self.assertEqual(data.get("supportsChannelFeatures"), "tier1")

    def test_validate_manifest_detects_errors(self):
        """Vérifie que les erreurs de manifeste sont correctement interceptées."""
        # Manifeste vide
        errors = validate_manifest({})
        self.assertTrue(any("Clé obligatoire manquante" in e for e in errors))

        # GUID invalide
        invalid_guid_manifest = {
            "manifestVersion": "1.25",
            "version": "1.0.0",
            "id": "not-a-guid",
            "developer": {"name": "Test", "websiteUrl": "https://x", "privacyUrl": "https://x", "termsOfUseUrl": "https://x"},
            "name": {"short": "Test", "full": "Test App"},
            "description": {"short": "Desc", "full": "Desc full"},
            "icons": {"color": "color.png", "outline": "outline.png"},
            "accentColor": "#123456",
            "supportsChannelFeatures": "tier1",
        }
        errors = validate_manifest(invalid_guid_manifest)
        self.assertTrue(any("GUID valide" in e for e in errors))

        # supportsChannelFeatures invalide
        invalid_tier = dict(invalid_guid_manifest, id="11111111-2222-3333-4444-555555555555", supportsChannelFeatures="tier2")
        errors = validate_manifest(invalid_tier)
        self.assertTrue(any("tier1" in e for e in errors))

        # supportedChannelTypes interdit en v1.25
        deprecated_types = dict(invalid_guid_manifest, id="11111111-2222-3333-4444-555555555555", supportedChannelTypes=["sharedChannels"])
        errors = validate_manifest(deprecated_types)
        self.assertTrue(any("supportedChannelTypes" in e for e in errors))

    def test_build_teams_package_default_id_with_domain(self):
        """Vérifie que build_teams_package génère un GUID déterministe avec le domaine sans lever de NameError sur fqdn."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_zip = Path(tmpdir) / "domain-app.zip"
            # Manifeste sans ID prédéfini
            tmp_manifest = Path(tmpdir) / "manifest.json"
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["id"] = "00000000-0000-0000-0000-000000000000"
            with open(tmp_manifest, "w", encoding="utf-8") as f:
                json.dump(data, f)

            build_teams_package(
                manifest_path=tmp_manifest,
                icons_dir=self.assets_dir,
                output_zip=tmp_zip,
                domain="assistant.example.org",
                bot_id="11111111-2222-3333-4444-555555555555",
            )
            self.assertTrue(tmp_zip.is_file())
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                result_manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                self.assertNotEqual(result_manifest["id"], "00000000-0000-0000-0000-000000000000")
                self.assertIn("assistant.example.org", result_manifest.get("validDomains", []))

    def test_teams_app_text_cleaning_and_sanitization(self):
        """Vérifie le nettoyage du texte Teams (HTML, XML <at>, espaces) et des emails utilisateurs."""
        import sys
        from unittest.mock import MagicMock
        for mod in ['aiohttp', 'botbuilder', 'botbuilder.core', 'botbuilder.schema', 'botframework', 'botframework.connector', 'botframework.connector.auth']:
            if mod not in sys.modules:
                sys.modules[mod] = MagicMock()

        from services.teams.app import clean_user_text, sanitize_user_email

        # 1. Nettoyage XML Teams
        raw1 = "<p><at>ArcIA</at> /hermes analyse les logs</p>"
        self.assertEqual(clean_user_text(raw1), "/hermes analyse les logs")

        raw2 = '<at id="28:8afbf35c-fe46-4918-aafe-b2a8c85f7adc">ArcIA</at> aide'
        self.assertEqual(clean_user_text(raw2), "aide")

        raw3 = "  @ArcIA   bonjour   "
        self.assertEqual(clean_user_text(raw3), "bonjour")

        # 2. Normalisation des emails pour l'en-tête HTTP
        self.assertEqual(sanitize_user_email("Nicolas THEUIL"), "nicolas.theuil@teams.local")
        self.assertEqual(sanitize_user_email("Clément Élodie"), "clement.elodie@teams.local")
        self.assertEqual(sanitize_user_email("Matthieu et Raphaël"), "matthieu.et.raphael@teams.local")
        self.assertEqual(sanitize_user_email(""), "collaborateur@teams.local")

    def test_teams_manifest_and_network_policy_alignment(self):
        """Vérifie que les manifestes 08-teams-bot.yaml et 09-network-policy.yaml sont cohérents pour Teams Bot."""
        manifest_path = self.project_root / "deploy" / "manifests" / "08-teams-bot.yaml"
        with open(manifest_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("checksum/teams-bot-code", content)
        self.assertIn("MICROSOFT_APP_TENANT_ID", content)
        self.assertIn("TEAMS_SYSTEM_PROMPT", content)
        self.assertIn("initialDelaySeconds: 30", content)

        netpol_path = self.project_root / "deploy" / "manifests" / "09-network-policy.yaml"
        with open(netpol_path, "r", encoding="utf-8") as f:
            netpol_content = f.read()

        self.assertIn("teams-bot-adapter", netpol_content)
        # Vérifie que hermes autorise teams-bot-adapter et que teams-bot-adapter peut contacter hermes-agent (8642)
        self.assertIn("port: 8642", netpol_content)


if __name__ == "__main__":
    unittest.main()
