"""Régressions synthétiques des sauvegardes ; aucun accès à une instance réelle."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy
import wizard
from services.instance_backup import storage


class TestBackupConfiguration(unittest.TestCase):
    def test_saved_config_preserves_instance_repository_and_extra_fields(self):
        cfg = {"instance_backup": {"enabled": True, "repo_url": "https://github.com/example/synthetic-instance.git"},
               "llm_gateway": {"hosting_extension": {"enabled": True}},
               "custom_connector": {"scope": ["synthetic"]}}
        result = deploy.parse_simple_yaml(wizard.serialize_yaml_config(cfg))
        self.assertEqual(result.get("instance_backup"), cfg["instance_backup"])
        self.assertEqual(result["llm_gateway"].get("hosting_extension"), {"enabled": True})
        self.assertEqual(result.get("custom_connector"), {"scope": ["synthetic"]})

    def test_backup_info_reports_remote_failure(self):
        cfg = {"instance_backup": {"repo_url": "https://github.com/example/synthetic-instance.git"}}
        with patch.object(wizard, "load_config_data", return_value=(cfg, True)), \
                patch.object(wizard, "get_instance_backup_timeline", return_value={"success": False, "error": "synthetic offline", "timeline": []}), \
                patch.object(storage, "credentials", return_value={"token": "", "passphrase": ""}):
            result = wizard.get_instance_backup_info()
        self.assertTrue(result["configured"])
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "synthetic offline")

    def test_new_backup_never_silently_downgrades_aes(self):
        with patch.object(wizard, "HAS_CRYPTOGRAPHY", False):
            with self.assertRaises(RuntimeError):
                wizard.encrypt_instance_bundle({"synthetic": True}, "synthetic-password")


class TestEncryptedQueue(unittest.TestCase):
    def test_offline_queue_deduplicates_and_retries_every_change(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = {"instance_backup": {"repo_url": "https://github.com/example/synthetic.git"}, "value": 1}
            with patch.object(storage, "credentials", return_value={"token": "synthetic", "passphrase": "synthetic-pass"}), patch.object(storage, "push_snapshot", side_effect=RuntimeError("offline")):
                for _ in range(2):
                    result = storage.backup(directory, cfg, "value: 1", "SYNTHETIC=one", wizard.encrypt_instance_bundle)
                self.assertEqual(result["state"], "pending")
                queue = Path(directory) / "secrets" / "backup-pending"
                self.assertEqual(len(list(queue.glob("*.json"))), 1)
                cfg["value"] = 2
                storage.backup(directory, cfg, "value: 2", "SYNTHETIC=two", wizard.encrypt_instance_bundle)
                self.assertEqual(len(list(queue.glob("*.json"))), 2)
            bundles = []
            def push(repo, token, bundle, metadata, **kwargs):
                self.assertEqual(metadata["encryption"], "AES-256-GCM")
                bundles.append(wizard.decrypt_instance_bundle(bundle, "synthetic-pass"))
                return {"success": True, "commit": "a" * 40}
            with patch.object(storage, "credentials", return_value={"token": "synthetic", "passphrase": "synthetic-pass"}), patch.object(storage, "push_snapshot", side_effect=push) as mocked:
                result = storage.backup(directory, cfg, "value: 2", "SYNTHETIC=two", wizard.encrypt_instance_bundle)
                self.assertTrue(result["success"])
                self.assertEqual([p["config_yaml"] for p in bundles], ["value: 1", "value: 2"])
                self.assertFalse(list(queue.glob("*.json")))
                storage.backup(directory, cfg, "value: 2", "SYNTHETIC=two", wizard.encrypt_instance_bundle)
                self.assertEqual(mocked.call_count, 2)

    def test_locked_backup_is_explicit_and_has_no_plaintext_queue(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(storage, "credentials", return_value={"token": "", "passphrase": ""}):
            result = storage.backup(directory, {"instance_backup": {"repo_url": "https://github.com/example/synthetic.git"}}, "synthetic", "synthetic", wizard.encrypt_instance_bundle)
            self.assertEqual(result["state"], "locked")
            self.assertFalse((Path(directory) / "secrets" / "backup-pending").exists())

    def test_central_save_preserves_repo_unknown_env_and_triggers_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "arcia.config.yaml")
            secret = Path(directory) / "secrets"
            secret.mkdir()
            (secret / "arcia.env").write_text("EXTRA_SYNTHETIC=value\n", encoding="utf-8")
            Path(path).write_text('instance_git:\n  owner: "example"\n  repo_name: "synthetic"\ncustom_setting:\n  preserved: true\n', encoding="utf-8")
            with patch.object(wizard, "ROOT_DIR", directory), patch.object(wizard, "DEFAULT_CONFIG_PATH", path), patch.object(storage, "backup", return_value={"success": True}) as mocked, patch.object(storage, "credentials", return_value={"token": "", "passphrase": ""}):
                wizard.save_config_to_files({"llm_gateway": {"master_key": "synthetic-key"}}, path)
                self.assertEqual(mocked.call_count, 1)
                self.assertTrue(mocked.call_args.args[1]["custom_setting"]["preserved"])
                self.assertIn("EXTRA_SYNTHETIC=value", mocked.call_args.args[3])
                self.assertIn("LITELLM_MASTER_KEY=synthetic-key", mocked.call_args.args[3])
                self.assertEqual(mocked.call_args.args[1]["instance_git"]["repo_name"], "synthetic")
                # Restore also keeps unknown encrypted environment entries.
                wizard.save_config_to_files({}, path, restored_env="RESTORED_SYNTHETIC=yes\n")
                self.assertIn("RESTORED_SYNTHETIC=yes", mocked.call_args.args[3])


    def test_wrong_unlock_password_never_replaces_existing_backup_key(self):
        cfg = {"instance_backup": {"repo_url": "https://github.com/example/synthetic.git"}}
        bundle = wizard.encrypt_instance_bundle({"config_yaml": "synthetic: true"}, "synthetic-correct")
        with patch.object(storage, "credentials", return_value={"token": "synthetic", "passphrase": ""}), patch.object(storage, "read_latest_bundle", return_value=bundle), patch.object(storage, "unlock") as unlock, patch.object(storage, "backup") as backup:
            with self.assertRaises(ValueError):
                wizard.backup_current_instance(cfg, passphrase="synthetic-wrong")
            unlock.assert_not_called()
            backup.assert_not_called()


class TestIsolatedGit(unittest.TestCase):
    def test_push_uses_remote_branch_and_changes_only_two_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            seed = root / "seed"
            env = dict(os.environ, GIT_AUTHOR_NAME="Synthetic engineer", GIT_AUTHOR_EMAIL="synthetic@example.invalid", GIT_COMMITTER_NAME="Synthetic engineer", GIT_COMMITTER_EMAIL="synthetic@example.invalid")
            def git(*args, cwd=None):
                return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, check=True).stdout.decode().strip()
            git("init", "--bare", "--initial-branch=instance-config", str(remote))
            git("clone", str(remote), str(seed))
            (seed / "README.md").write_text("Keep this unrelated file", encoding="utf-8")
            git("add", "README.md", cwd=seed)
            git("commit", "-m", "Synthetic seed", cwd=seed)
            git("push", "origin", "HEAD", cwd=seed)
            git("config", "user.name", "Synthetic engineer", cwd=seed)
            git("config", "user.email", "synthetic@example.invalid", cwd=seed)
            clean_env = {k: v for k, v in os.environ.items() if k not in {"GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"}}
            with patch.dict(os.environ, clean_env, clear=True):
                result = storage.push_snapshot(str(remote), "", "encrypted synthetic", {"encryption": "AES-256-GCM"}, allow_local=True, source_root=seed)
            self.assertTrue(result["success"])
            self.assertEqual(result["branch"], "instance-config")
            self.assertEqual(set(git("--git-dir=" + str(remote), "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()), set(storage.ALLOWED_FILES))
            self.assertEqual(git("--git-dir=" + str(remote), "show", "HEAD:README.md"), "Keep this unrelated file")
            self.assertEqual(git("--git-dir=" + str(remote), "log", "-1", "--format=%ae"), "synthetic@example.invalid")

    def test_token_not_in_command_arguments(self):
        commands = []
        def execute(args, **kwargs):
            commands.append(args)
            self.assertNotIn("synthetic-pat-secret", " ".join(args))
            if "clone" in args:
                Path(args[-1]).mkdir()
            out = b"instance-config" if "symbolic-ref" in args else b"instance-secrets.enc\0instance.json\0" if "diff" in args else b"a" * 40
            return subprocess.CompletedProcess(args, 0, out, b"")
        with patch.object(storage, "assert_private"), patch.object(storage.subprocess, "run", side_effect=execute):
            storage.push_snapshot("https://github.com/example/synthetic.git", "synthetic-pat-secret", "ciphertext", {})
        self.assertFalse(any("--force" in command or "." in command[3:] for command in commands))

    def test_public_repo_is_rejected_before_git(self):
        with patch.object(storage, "assert_private", side_effect=ValueError("public")), patch.object(storage.subprocess, "run") as mocked:
            with self.assertRaises(ValueError):
                storage.push_snapshot("https://github.com/example/synthetic.git", "synthetic", "ciphertext", {})
            mocked.assert_not_called()


class TestBackupHttp(unittest.TestCase):
    def test_backup_endpoint_reuses_saved_repository_and_calls_current_signature(self):
        import threading
        import urllib.request
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "arcia.config.yaml")
            repo = "https://github.com/example/synthetic.git"
            cfg = {"instance_backup": {"repo_url": repo}}
            Path(path).write_text(wizard.serialize_yaml_config(cfg), encoding="utf-8")
            with patch.object(wizard, "ROOT_DIR", directory), patch.object(wizard, "DEFAULT_CONFIG_PATH", path), patch.object(storage, "credentials", return_value={"token": "synthetic-token", "passphrase": "synthetic-pass"}), patch.object(storage, "push_snapshot", return_value={"success": True, "commit": "a" * 40}) as pushed:
                server = wizard.HttpServerClass(("127.0.0.1", 0), wizard.WizardHTTPHandler)
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    request = urllib.request.Request("http://127.0.0.1:" + str(server.server_port) + "/api/instance/backup-now", data=b"{}", headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(request, timeout=10) as response:
                        result = json.load(response)
                    self.assertTrue(result["success"])
                    self.assertEqual(result["state"], "pushed")
                    self.assertEqual(pushed.call_args.args[0], repo)
                    self.assertEqual(pushed.call_args.args[1], "synthetic-token")
                finally:
                    server.shutdown()
                    server.server_close()
                    worker.join(timeout=2)

    def test_empty_template_does_not_override_declared_legacy_repo(self):
        cfg = {"instance_git": {"repo_url": "https://github.com/example/synthetic.git"}, "instance_backup": {"enabled": True, "repo_url": ""}}
        self.assertEqual(storage.normalize_settings(cfg)["repo_url"], cfg["instance_git"]["repo_url"])


if __name__ == "__main__":
    unittest.main()
