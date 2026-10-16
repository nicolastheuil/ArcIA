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


if __name__ == "__main__":
    unittest.main()
