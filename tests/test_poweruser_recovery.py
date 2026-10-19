"""Qualification synthétique de l'état désiré, sans accès aux instances privées."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.instance_backup import powerusers


def fixture(email="synthetic.user@example.org", **changes):
    record = dict(email=email, team="synthetic", job_title="Qualification",
                  manager="Synthetic admin", storage_size="25Gi",
                  custom_soul="# Synthetic soul\nUse synthetic fixtures only.",
                  vpn=False, pat="sk-synthetic-recovery", password="synthetic-password",
                  replicas=1)
    record.update(changes)
    return record


class TestPoweruserDesiredState(unittest.TestCase):
    def test_register_update_remove_preserve_unrelated_configuration(self):
        cfg = {"powerusers": {"enable_vpn": True}, "network": {"public_fqdn": "synthetic.example.org"}}
        record = fixture()
        slug = powerusers.register_poweruser(cfg, record)
        record["pat"] = "modified-outside"
        self.assertEqual(slug, "synthetic-user")
        self.assertEqual(cfg["powerusers"]["instances"][slug]["pat"], "sk-synthetic-recovery")
        self.assertTrue(powerusers.update_poweruser(cfg, slug, replicas=0, storage_size="50Gi"))
        restored = json.loads(json.dumps(cfg))
        self.assertEqual(restored["powerusers"]["instances"][slug]["replicas"], 0)
        self.assertEqual(restored["powerusers"]["instances"][slug]["storage_size"], "50Gi")
        self.assertTrue(powerusers.remove_poweruser(cfg, slug))
        self.assertTrue(cfg["powerusers"]["enable_vpn"])
        self.assertEqual(cfg["network"]["public_fqdn"], "synthetic.example.org")
        self.assertEqual(cfg["powerusers"]["instances"], {})

    def test_legacy_cluster_only_user_is_not_invented(self):
        cfg = {}
        self.assertFalse(powerusers.update_poweruser(cfg, "legacy", replicas=0))
        self.assertFalse(powerusers.remove_poweruser(cfg, "legacy"))
        runner = Mock()
        self.assertEqual(powerusers.reconcile_powerusers(cfg, runner), 0)
        runner.run.assert_not_called()
        self.assertEqual(cfg, {})

    def test_slug_collision_and_identity_replacement_are_rejected(self):
        cfg = {}
        slug = powerusers.register_poweruser(cfg, fixture())
        before = copy.deepcopy(cfg)
        with self.assertRaises(ValueError):
            powerusers.register_poweruser(cfg, fixture("synthetic.user@other.example.org"))
        with self.assertRaises(ValueError):
            powerusers.update_poweruser(cfg, slug, email="synthetic.user@other.example.org")
        self.assertEqual(cfg, before)

    def test_invalid_records_never_mutate_cfg_or_generate_credentials(self):
        for change in ({"pat": ""}, {"password": None}, {"replicas": 2}, {"replicas": True},
                       {"storage_size": "0Gi"}, {"storage_size": "10Gi\nkind: Secret"},
                       {"vpn": "true"}, {"custom_soul": {}}, {"email": "@@@example.org"},
                       {"unknown": "value"}):
            with self.subTest(fields=list(change)):
                cfg = {}
                with self.assertRaises(ValueError):
                    powerusers.register_poweruser(cfg, fixture(**change))
                self.assertEqual(cfg, {})

    def test_all_records_validated_before_kubernetes_changes(self):
        cfg = {}
        powerusers.register_poweruser(cfg, fixture())
        cfg["powerusers"]["instances"]["other"] = fixture("other@example.org", pat="")
        runner = Mock()
        with self.assertRaises(ValueError):
            powerusers.reconcile_powerusers(cfg, runner)
        runner.run.assert_not_called()

    def test_shared_pat_is_rejected_before_any_mutation(self):
        cfg = {}
        powerusers.register_poweruser(cfg, fixture())
        before = copy.deepcopy(cfg)
        with self.assertRaises(ValueError):
            powerusers.register_poweruser(cfg, fixture("other@example.org"))
        self.assertEqual(cfg, before)
        cfg["powerusers"]["instances"]["other"] = fixture("other@example.org")
        runner = Mock()
        with self.assertRaises(ValueError):
            powerusers.reconcile_powerusers(cfg, runner)
        runner.run.assert_not_called()


class TestPoweruserReconciliation(unittest.TestCase):
    def setUp(self):
        # Une lecture de la configuration du poste est un échec, jamais une fixture.
        guard = patch("scripts.arcia_poweruser.load_arcia_config", side_effect=AssertionError("private config forbidden"))
        guard.start()
        self.addCleanup(guard.stop)
        self.cfg = {"network": {"public_fqdn": "recovery.example.org"},
                    "kubernetes": {"namespace": "synthetic-recovery"}}
        self.runner = Mock()
        self.runner.run.return_value = (0, "", "")

    def test_rebuild_preserves_credentials_personality_storage_vpn_and_suspension(self):
        record = fixture(vpn=True, replicas=0, password='synthetic "quoted" password\\suffix')
        powerusers.register_poweruser(self.cfg, record)
        with patch("scripts.arcia_poweruser.generate_litellm_pat", side_effect=AssertionError("no new PAT")), \
             patch("scripts.arcia_poweruser.secrets.token_urlsafe", side_effect=AssertionError("no new password")):
            self.assertEqual(powerusers.reconcile_powerusers(self.cfg, self.runner), 1)
        apply_call, pat_call = self.runner.run.call_args_list
        self.assertEqual(apply_call.args[0], ["apply", "-f", "-"])
        manifest = apply_call.kwargs["stdin_input"]
        self.assertIn("namespace: synthetic-recovery", manifest)
        self.assertIn("host: recovery.example.org", manifest)
        self.assertIn("  replicas: 0\n", manifest)
        self.assertNotIn("  replicas: 1\n", manifest)
        self.assertIn("storage: 25Gi", manifest)
        self.assertIn("Use synthetic fixtures only.", manifest)
        self.assertIn("NET_ADMIN", manifest)
        self.assertIn('litellm-pat: "sk-synthetic-recovery"', manifest)
        self.assertIn(json.dumps(record["password"]), manifest)
        self.assertIn("hermes-user-synthetic-user-pvc", manifest)
        self.assertNotIn(record["pat"], " ".join(pat_call.args[0]))
        self.assertIn(record["pat"], pat_call.kwargs["stdin_input"])
        self.assertIn("deployment/litellm-proxy", pat_call.args[0])

    def test_dry_run_renders_without_cluster_calls(self):
        powerusers.register_poweruser(self.cfg, fixture())
        self.assertEqual(powerusers.reconcile_powerusers(self.cfg, self.runner, dry_run=True), 1)
        self.runner.run.assert_not_called()

    def test_bound_existing_poweruser_is_not_reapplied_but_missing_one_is_rebuilt(self):
        powerusers.register_poweruser(self.cfg, fixture())
        self.cfg["hermes_workspaces"] = {"users": [{"webui_user_id": "alice", "poweruser_slug": "synthetic-user"}]}
        existing = json.dumps({"metadata": {"name": "hermes-poweruser-synthetic-user"}})
        self.runner.run.side_effect = [(0, existing, ""), (0, "", "")]
        powerusers.reconcile_powerusers(self.cfg, self.runner)
        self.assertFalse(any(call.args[0][0] == "apply" for call in self.runner.run.call_args_list))
        self.runner.reset_mock()
        self.runner.run.side_effect = [(0, "", ""), (0, "", ""), (0, "", "")]
        powerusers.reconcile_powerusers(self.cfg, self.runner)
        self.assertEqual(sum(call.args[0][0] == "apply" for call in self.runner.run.call_args_list), 1)

    def test_apply_or_pat_failures_stop_recovery_without_raw_output(self):
        powerusers.register_poweruser(self.cfg, fixture())
        raw = "synthetic-password sk-synthetic-recovery"
        for responses in ([(1, raw, raw)], [(0, "", ""), (1, raw, raw)]):
            with self.subTest(stage=len(responses)):
                self.runner.run.side_effect = responses
                with self.assertRaises(RuntimeError) as error:
                    powerusers.reconcile_powerusers(self.cfg, self.runner)
                self.assertNotIn(raw, str(error.exception))
                self.assertNotIn("synthetic-password", str(error.exception))
        self.runner.run.side_effect = RuntimeError(raw)
        with self.assertRaises(RuntimeError) as error:
            powerusers.reconcile_powerusers(self.cfg, self.runner)
        self.assertNotIn(raw, str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)

    def test_scope_fields_are_validated_before_render(self):
        powerusers.register_poweruser(self.cfg, fixture())
        self.cfg["kubernetes"]["namespace"] = "arcia; injected"
        with self.assertRaises(ValueError):
            powerusers.reconcile_powerusers(self.cfg, self.runner)
        self.runner.run.assert_not_called()


class TestPoweruserPatRecovery(unittest.TestCase):
    def execute_registration(self, responses, record=None):
        record = record or fixture()
        opener = Mock(side_effect=[io.BytesIO(json.dumps(response).encode()) for response in responses])
        script = "import json\n" + powerusers._pat_registration_code("synthetic-user", record)
        with patch.dict("os.environ", {"LITELLM_MASTER_KEY": "sk-synthetic-master"}), \
             patch("urllib.request.urlopen", opener), patch("sys.stderr", new_callable=io.StringIO) as stderr:
            try:
                exec(compile(script, "<synthetic-pat-recovery>", "exec"), {})
            except SystemExit as error:
                return opener, error.code, stderr.getvalue()
        return opener, 0, stderr.getvalue()

    def key_info(self, **changes):
        key = dict(token=hashlib.sha256(fixture()["pat"].encode()).hexdigest(),
                   user_id=fixture()["email"], key_alias="pat-synthetic-user")
        key.update(changes)
        return {"keys": [key]}

    def test_existing_pat_is_idempotent_without_rotation(self):
        opener, rc, stderr = self.execute_registration([self.key_info()])
        self.assertEqual((rc, stderr), (0, ""))
        self.assertEqual(opener.call_count, 1)
        self.assertIsNone(opener.call_args.args[0].data)
        self.assertNotIn(fixture()["pat"], opener.call_args.args[0].full_url)

    def test_empty_gateway_registers_exact_restored_pat_then_verifies(self):
        opener, rc, _ = self.execute_registration([{"keys": []}, {"key": fixture()["pat"]}, self.key_info()])
        self.assertEqual(rc, 0)
        payload = json.loads(opener.call_args_list[1].args[0].data)
        self.assertEqual(payload["key"], fixture()["pat"])
        self.assertEqual(payload["user_id"], fixture()["email"])
        self.assertEqual(opener.call_count, 3)

    def test_unverified_registration_or_wrong_owner_fails_closed(self):
        for responses in ([{"keys": []}, {}, {"keys": []}],
                          [self.key_info(user_id="other@example.org")], [{"unexpected": []}]):
            with self.subTest(responses=len(responses)):
                _, rc, stderr = self.execute_registration(responses)
                self.assertEqual(rc, 1)
                self.assertEqual(stderr, "ARCIA_POWERUSER_PAT_FAILED\n")

    def test_special_characters_cannot_inject_python(self):
        record = fixture(pat="synthetic'; raise RuntimeError('injected') #")
        opener, rc, _ = self.execute_registration([{"keys": []}, {}, {"keys": []}], record=record)
        self.assertEqual(rc, 1)
        payload = json.loads(opener.call_args_list[1].args[0].data)
        self.assertEqual(payload["key"], record["pat"])


if __name__ == "__main__":
    unittest.main()
