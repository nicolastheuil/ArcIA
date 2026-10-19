"""Portabilité et intégrité des configurations, uniquement avec des fixtures synthétiques."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch
from services.instance_backup import bundle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import wizard
import deploy
from services.instance_backup import storage


class TestPortableBundle(unittest.TestCase):
    def test_referenced_credentials_and_custom_settings_survive_relocation(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as destination:
            key = Path(source) / "synthetic.key"
            key.write_bytes(b"synthetic-only")
            cfg = {"kubernetes": {"mode": "remote-ssh", "remote_ssh": {"ssh_key": str(key)}},
                   "custom": {"config_file": "synthetic.key", "unknown": [1, 2]},
                   "microsoft365_integration": {"enabled": False, "config_file": "absent"}}
            assets, coverage = bundle.collect(source, cfg)
            self.assertTrue(coverage["complete"])
            self.assertEqual(coverage["referenced_files"], 2)
            restored, files = bundle.prepare_restore(cfg, assets)
            bundle.install_assets(destination, files)
            self.assertEqual(restored["custom"]["unknown"], [1, 2])
            self.assertEqual((Path(destination) / restored["kubernetes"]["remote_ssh"]["ssh_key"]).read_bytes(), b"synthetic-only")
            self.assertEqual(len(files), 1)
            self.assertEqual(cfg["kubernetes"]["remote_ssh"]["ssh_key"], str(key))

    def test_missing_active_reference_never_reports_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            assets, coverage = bundle.collect(directory, {"kubernetes": {"kubeconfig": "missing"}})
            self.assertFalse(coverage["complete"])
            self.assertEqual(coverage["missing_references"], ["kubernetes.kubeconfig"])
            with self.assertRaises(ValueError):
                bundle.prepare_restore({"kubernetes": {"kubeconfig": "missing"}}, assets)

    def test_unused_connection_mode_does_not_require_an_inactive_credential_file(self):
        with tempfile.TemporaryDirectory() as directory:
            for cfg in ({"kubernetes": {"mode": "remote-ssh", "kubeconfig": "unused-missing"}},
                        {"kubernetes": {"mode": "local", "remote_ssh": {"ssh_key": "unused-missing"}}}):
                assets, coverage = bundle.collect(directory, cfg)
                self.assertTrue(coverage["complete"])
                self.assertEqual(assets, [])
                restored, files = bundle.prepare_restore(cfg, assets)
                self.assertEqual(restored, cfg)
                self.assertEqual(files, {})

    def test_corruption_missing_and_unexpected_bindings_rejected_before_install(self):
        cfg = {"custom": {"config_file": "synthetic"}}
        for assets in ([], [{"binding": ["custom", "config_file"], "content": base64.b64encode(b"corrupt").decode(), "sha256": "0" * 64}],
                       [{"binding": ["network", "public_fqdn"], "content": "", "sha256": ""}]):
            with self.subTest(assets=assets), self.assertRaises(ValueError):
                bundle.prepare_restore(cfg, assets)

    def test_extra_file_and_size_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "synthetic.yaml").write_text("test: true")
            cfg = {"instance_backup": {"additional_files": ["synthetic.yaml"]}}
            assets, _ = bundle.collect(directory, cfg)
            restored, _ = bundle.prepare_restore(cfg, assets)
            self.assertTrue(restored["instance_backup"]["additional_files"][0].startswith("secrets/restored-assets/"))

    def test_archive_cannot_write_arbitrary_paths(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            bundle.install_assets(directory, {"scripts/wizard.py": b"forbidden"})

    def test_kubeconfig_embeds_external_certificates_even_without_pyyaml(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.joinpath("synthetic.crt").write_bytes(b"SYNTHETIC-CERTIFICATE")
            root.joinpath("synthetic.key").write_bytes(b"SYNTHETIC-PRIVATE-KEY")
            root.joinpath("kube.yaml").write_text('clusters:\n- cluster:\n    certificate-authority: synthetic.crt\n  name: synthetic\nusers:\n- name: synthetic\n  user:\n    client-key: synthetic.key\n', encoding="utf-8")
            with patch.dict(sys.modules, {"yaml": None}):
                assets, coverage = bundle.collect(directory, {"kubernetes": {"kubeconfig": "kube.yaml"}})
            self.assertTrue(coverage["complete"])
            portable = json.loads(base64.b64decode(assets[0]["content"]).decode())
            self.assertNotIn("certificate-authority", portable["clusters"][0]["cluster"])
            self.assertEqual(base64.b64decode(portable["users"][0]["user"]["client-key-data"]), b"SYNTHETIC-PRIVATE-KEY")

    def test_coffre_master_never_included_as_extra_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "instance-backup.dpapi").write_bytes(b"synthetic")
            with self.assertRaises(ValueError):
                bundle.collect(directory, {"instance_backup": {"additional_files": ["instance-backup.dpapi"]}})

    def test_inclusion_limits_reject_partial_success(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "synthetic.yaml").write_bytes(b"x" * 9)
            with patch.object(bundle, "MAX_FILE_BYTES", 8), self.assertRaises(ValueError):
                bundle.collect(directory, {"custom": {"config_file": "synthetic.yaml"}})


class TestCompleteBackupAndRestore(unittest.TestCase):
    def test_file_change_generates_new_encrypted_snapshot_and_restores_on_fresh_host(self):
        repo = "https://github.com/example/synthetic-instance.git"
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as destination:
            key = Path(source, "synthetic.key")
            key.write_text("synthetic: first")
            cfg = {"instance_backup": {"enabled": True, "repo_url": repo}, "infra_target": "k8s_existing",
                   "kubernetes": {"mode": "local", "kubeconfig": str(key)},
                   "custom_config": {"nested": {"enabled": True, "values": ["synthetic"]}}}
            path = str(Path(source, "arcia.config.yaml"))
            secret = Path(source, "secrets")
            secret.mkdir()
            secret.joinpath("arcia.env").write_text("EXTRA_SYNTHETIC=preserved\n")
            Path(source, "arcia.env").write_text("ROOT_SYNTHETIC=preserved\n")
            Path(path).write_text(wizard.serialize_yaml_config(cfg), encoding="utf-8")
            archives = []
            def pushed(repo, token, archive, metadata):
                self.assertNotIn("synthetic: first", archive)
                archives.append(archive)
                return {"success": True, "commit": "a" * 40}
            with patch.object(wizard, "ROOT_DIR", source), patch.object(wizard, "DEFAULT_CONFIG_PATH", path), \
                    patch.object(storage, "credentials", return_value={"token": "synthetic", "passphrase": "synthetic-pass"}), \
                    patch.object(storage, "push_snapshot", side_effect=pushed):
                self.assertTrue(wizard.backup_current_instance(cfg)["success"])
                key.write_text("synthetic: second")
                self.assertTrue(wizard.backup_current_instance(cfg)["success"])
                self.assertEqual(len(archives), 2)
            payload = wizard.decrypt_instance_bundle(archives[-1], "synthetic-pass")
            target = str(Path(destination, "arcia.config.yaml"))
            # La configuration plus récente doit disparaître pendant une reprise exacte.
            Path(target).write_text("stale_only: true\n", encoding="utf-8")
            with patch.object(wizard, "ROOT_DIR", destination), patch.object(wizard, "DEFAULT_CONFIG_PATH", target), \
                    patch.object(storage, "unlock"), patch.object(wizard, "backup_current_instance") as automatic:
                restored, result = wizard.restore_instance_payload(payload, repo, "synthetic", "synthetic-pass")
                automatic.assert_not_called()  # Ne pas écraser immédiatement le point historique choisi.
            self.assertTrue(result["portable"])
            self.assertNotIn("stale_only", deploy.parse_simple_yaml(Path(target).read_text(encoding="utf-8")))
            self.assertEqual(restored["custom_config"], cfg["custom_config"])
            self.assertEqual((Path(destination) / restored["kubernetes"]["kubeconfig"]).read_text(), "synthetic: second")
            self.assertEqual(Path(destination, "secrets", "arcia.env").read_text(), "EXTRA_SYNTHETIC=preserved\n")
            self.assertEqual(Path(destination, "arcia.env").read_text(), "ROOT_SYNTHETIC=preserved\n")
            self.assertEqual(len(list(Path(destination, "secrets").glob("pre-restore-*.enc"))), 1)

    def test_incomplete_backup_never_pushes(self):
        cfg = {"instance_backup": {"repo_url": "https://github.com/example/synthetic.git"}, "kubernetes": {"kubeconfig": "absent"}}
        with tempfile.TemporaryDirectory() as directory, patch.object(wizard, "ROOT_DIR", directory), \
                patch.object(storage, "credentials", return_value={"token": "synthetic", "passphrase": "synthetic-pass"}), \
                patch.object(storage, "push_snapshot") as pushed:
            result = wizard.backup_current_instance(cfg)
            self.assertEqual(result["state"], "incomplete")
            pushed.assert_not_called()
            self.assertFalse(Path(directory, "secrets", "backup-pending").exists())

    def test_corrupt_assets_leave_local_config_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "arcia.config.yaml")
            target.write_text("unchanged: true\n")
            payload = {"schema": "arcia-instance-v2", "config_yaml": "custom:\n  config_file: missing\n", "assets": [], "env_content": ""}
            with patch.object(wizard, "ROOT_DIR", directory), patch.object(wizard, "DEFAULT_CONFIG_PATH", str(target)), self.assertRaises(ValueError):
                wizard.restore_instance_payload(payload, "https://github.com/example/synthetic.git", "synthetic", "synthetic-pass")
            self.assertEqual(target.read_text(), "unchanged: true\n")

    def test_deploy_reuses_credentials_only_from_same_repository(self):
        repo = "https://github.com/example/synthetic.git"
        with patch.object(storage, "credentials", return_value={"token": "synthetic", "passphrase": "synthetic-pass"}) as credentials, \
                patch.object(storage, "unlock") as unlock, patch.object(storage, "read_latest_bundle") as latest:
            result = wizard.unlock_instance_repository({"instance_backup": {"repo_url": repo}}, {"repo_url": repo})
            self.assertEqual(result["repo_url"], repo)
            unlock.assert_called_once_with(wizard.ROOT_DIR, repo, "synthetic", "synthetic-pass")
            latest.assert_not_called()
            other = "https://github.com/example/other.git"
            wizard.unlock_instance_repository({"instance_backup": {"repo_url": repo, "git_token": "never-reuse"}}, {"repo_url": other})
            self.assertEqual(credentials.call_args.args[1], {"repo_url": other})

    def test_deleted_poweruser_is_not_resurrected_by_partial_config_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "arcia.config.yaml")
            path.write_text('powerusers:\n  enable_vpn: true\n  instances: {"synthetic": {"email": "synthetic@example.invalid"}}\n', encoding="utf-8")
            with patch.object(wizard, "ROOT_DIR", directory), patch.object(wizard, "DEFAULT_CONFIG_PATH", str(path)):
                wizard.save_config_to_files({"powerusers": {"instances": {}}}, str(path), trigger_backup=False)
            actual = deploy.parse_simple_yaml(path.read_text(encoding="utf-8"))
            self.assertEqual(actual["powerusers"]["instances"], {})
            self.assertTrue(actual["powerusers"]["enable_vpn"])

    def test_poweruser_creation_records_effective_credentials_only_after_cluster_success(self):
        from unittest.mock import Mock
        cfg = {"kubernetes": {"namespace": "synthetic"}, "network": {"public_fqdn": "synthetic.example.invalid"}}
        runner = Mock()
        runner.run.return_value = (0, "", "")
        with patch.object(wizard, "get_k8s_runner", return_value=runner), \
                patch.object(wizard, "save_config_to_files", return_value={"state": "locked"}) as saved, \
                patch("arcia_poweruser.render_manifest", return_value="synthetic manifest"):
            result = wizard.create_poweruser({"email": "synthetic@example.invalid", "pat": "sk-synthetic", "password": "synthetic-password"}, cfg=cfg)
            record = saved.call_args.args[0]["powerusers"]["instances"]["synthetic"]
            self.assertEqual(record["pat"], result["pat"])
            self.assertEqual(record["password"], result["password"])
            self.assertTrue(result["configuration_recorded"])
            runner.run.return_value = (1, "", "synthetic failure")
            saved.reset_mock()
            self.assertFalse(wizard.create_poweruser({"email": "synthetic@example.invalid"}, cfg=cfg)["success"])
            saved.assert_not_called()
