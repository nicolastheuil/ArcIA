"""Réapplication des versions sans migration implicite des données PostgreSQL."""
import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy
import wizard
import sync_versions
import yaml


class Runner:
    def __init__(self, statefulset=None, pvc=None, error=False):
        self.statefulset, self.pvc, self.error = statefulset, pvc, error

    def run(self, args, **kwargs):
        if self.error:
            return 1, "", "private diagnostic must not escape"
        obj = self.statefulset if args[1] == "statefulset" else self.pvc
        return 0, json.dumps(obj) if obj else "", ""


def database(image):
    return {"spec": {"template": {"spec": {"containers": [
        {"name": "postgres", "image": image}]}}}}


class TestDatabaseUpgrade(unittest.TestCase):
    def test_empty_installation_is_allowed(self):
        deploy.assert_database_upgrade_safe(Runner(), "synthetic", "postgres:18.6-alpine")

    def test_same_major_is_allowed(self):
        deploy.assert_database_upgrade_safe(Runner(database("postgres:18.5-alpine"), {}),
                                            "synthetic", "postgres:18.6-alpine")

    def test_major_change_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "migration"):
            deploy.assert_database_upgrade_safe(Runner(database("postgres:16-alpine")),
                                                "synthetic", "postgres:18.6-alpine")

    def test_orphan_volume_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "volume"):
            deploy.assert_database_upgrade_safe(Runner(pvc={"metadata": {"name": "litellm-db-pvc"}}),
                                                "synthetic", "postgres:18.6-alpine")

    def test_unversioned_existing_image_is_rejected(self):
        with self.assertRaises(ValueError):
            deploy.assert_database_upgrade_safe(Runner(database("postgres@sha256:unknown")),
                                                "synthetic", "postgres:18.6-alpine")

    def test_read_failure_is_closed_without_private_diagnostic(self):
        with self.assertRaises(ValueError) as raised:
            deploy.assert_database_upgrade_safe(Runner(error=True), "synthetic", "postgres:18.6-alpine")
        self.assertNotIn("private diagnostic", str(raised.exception))


class TestReleaseLock(unittest.TestCase):
    def test_presidio_fail_closed_is_explicit_in_every_gateway_config(self):
        current = yaml.safe_load(deploy.build_litellm_config_data({}))
        manifest = next(yaml.safe_load_all((ROOT / "deploy/manifests/05-litellm.yaml").read_text(encoding="utf-8")))
        configs = [current, yaml.safe_load(manifest["data"]["config.yaml"]),
                   yaml.safe_load((ROOT / "deploy/litellm-lab.yaml").read_text(encoding="utf-8"))]
        for config in configs:
            params = config["guardrails"][0]["litellm_params"]
            self.assertEqual(params.get("pii_entities_config", {}).get("EMAIL_ADDRESS"), "MASK")

    def test_version_sync_does_not_relabel_historical_attestations(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.md"
            original = "> **Statut en v0.6.0 : Implémenté et Actif.**\n"
            path.write_text(original, encoding="utf-8")
            sync_versions.sync_file_versions(path, "v0.7.0", apply_changes=True)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_managed_images_are_digest_pinned_and_present_in_manifests(self):
        registry = json.loads((ROOT / "deploy/versions.json").read_text(encoding="utf-8"))
        for component in registry["components"].values():
            if "manifest" not in component:
                continue
            with self.subTest(component=component):
                self.assertRegex(component["image"], r"@sha256:[0-9a-f]{64}$")
                self.assertIn(component["image"], (ROOT / component["manifest"]).read_text(encoding="utf-8"))

    def test_wizard_cannot_remove_a_locked_digest_for_an_unapproved_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "deploy/manifests").mkdir(parents=True)
            path = root / "deploy/manifests/05-litellm.yaml"
            original = "image: ghcr.io/berriai/litellm:v1.0.0@sha256:" + "a" * 64 + "\n"
            path.write_text(original, encoding="utf-8")
            (root / "deploy/versions.json").write_text(json.dumps({"components": {"litellm-proxy": {
                "manifest": "deploy/manifests/05-litellm.yaml", "version": "v1.0.0", "image": original[7:].strip()}}}), encoding="utf-8")
            with patch.object(wizard, "ROOT_DIR", directory):
                self.assertIsNone(wizard.update_manifest_image_tag("deploy/manifests/05-litellm.yaml", "v9.9.9"))
            self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
