"""Routage et icônes : une action, pour une instance existante ou nouvelle."""
import contextlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy
import wizard


class RecordingRunner:
    mode = "local"

    def __init__(self):
        self.manifests = []

    def run(self, args, **kwargs):
        return 0, "", ""

    def apply_manifest(self, manifest):
        self.manifests.append(manifest)


def synthetic_config():
    return {"kubernetes": {"namespace": "synthetic"}, "network": {"tls_mode": "disabled"},
            "llm_gateway": {"default_model": "synthetic-chat", "models_routing": [
                {"alias": "synthetic-chat", "provider": "synthetic-provider", "target_model": "openrouter/auto", "zdr": True}
            ], "custom_providers": [{"id": "synthetic-provider", "hosting": "local", "endpoint": "https://synthetic.invalid/v1"}]}}


class TestModelIconWorkflow(unittest.TestCase):
    def save_routing(self, appearance_ok):
        cfg = synthetic_config()
        runner = RecordingRunner()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(wizard, "load_config_data", return_value=(cfg, True)))
            stack.enter_context(patch.object(wizard, "save_config_to_files"))
            stack.enter_context(patch.object(wizard, "get_k8s_runner", return_value=runner))
            for name in ("sync_litellm_configmap", "sync_hermes_configmap", "sync_openwebui_models_config"):
                stack.enter_context(patch.object(wizard, name, return_value=True))
            stack.enter_context(patch.object(wizard, "sync_all_powerusers_wizard", return_value={"success": True}))
            activate = stack.enter_context(patch.object(deploy, "activate_webui_branding", return_value={
                "assets_applied": True, "runtime_loaded": appearance_ok, "assets_served": appearance_ok,
                "error": None if appearance_ok else "synthetic rollout failure"}))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            result = wizard.save_model_routing_config({"mappings": cfg["llm_gateway"]["models_routing"],
                                                       "custom_providers": cfg["llm_gateway"]["custom_providers"]})
        return result, activate

    def test_existing_instance_saves_routing_and_applies_declared_icons_together(self):
        result, activate = self.save_routing(True)
        activate.assert_called_once()
        mapping = activate.call_args.args[2]["mapping"]
        self.assertEqual(mapping["models"]["synthetic-chat"]["type"], "local")
        self.assertTrue(result["branding_synced"])
        self.assertTrue(result["all_synced"])

    def test_failed_icons_are_reported_as_partial_routing_application(self):
        result, _ = self.save_routing(False)
        self.assertTrue(result["success"])  # La configuration locale est conservée.
        self.assertFalse(result["all_synced"])
        self.assertIn("icônes", result["message"])
        self.assertIn("branding", result["details"])

    def test_new_instance_manifest_enables_icons_from_the_installation_config(self):
        runner = RecordingRunner()
        # Un déploiement peut persister ses secrets : sa racine doit être isolée.
        with tempfile.TemporaryDirectory() as directory:
            for name in ("services", "deploy", "assets", "skills"):
                shutil.copytree(ROOT / name, Path(directory) / name)
            with patch.object(deploy, "K8sRunner", return_value=runner), \
                    patch.object(deploy, "get_existing_cluster_secret", return_value=None), \
                    patch.object(deploy, "sync_native_skills"), \
                    patch.object(deploy.subprocess, "run") as external, \
                    contextlib.redirect_stdout(io.StringIO()):
                deploy.deploy_arcia(synthetic_config(), directory)
            effective = deploy.parse_simple_yaml(Path(directory, "arcia.config.yaml").read_text(encoding="utf-8"))
            self.assertTrue(effective["llm_gateway"]["master_key"])
            self.assertTrue(effective["llm_gateway"]["salt_key"])
            self.assertTrue(effective["llm_gateway"]["db_password"])
            self.assertTrue(effective["hermes"]["api_token"])
            self.assertTrue(effective["presidio"]["master_key"])
        external.assert_not_called()
        branding = next(m for m in runner.manifests if "name: arcia-webui-branding\n" in m)
        projection = json.loads(deploy.parse_simple_yaml(branding)["data"]["models-branding.json"])
        self.assertEqual(projection["models"]["synthetic-chat"]["type"], "local")
        webui = next(m for m in runner.manifests if "kind: Deployment" in m and "name: open-webui\n" in m)
        self.assertIn('/opt/arcia-webui/start.py', webui)
        self.assertIn('mountPath: /etc/arcia', webui)
        self.assertNotIn('checksum/arcia-webui-branding: "default"', webui)

    @unittest.skipUnless(shutil.which("node"), "Node requis pour exécuter le parcours JavaScript synthétique")
    def test_shared_form_uses_one_save_action_and_preserves_installation_appearance(self):
        html = (ROOT / "scripts/wizard_ui/index.html").read_text(encoding="utf-8")
        functions = []
        for name in ("collectConfigFromUI", "saveModelRouting"):
            match = re.search(r"    (?:async )?function " + name + r"\([^\n]*\) \{.*?(?=\n    (?:async )?function )", html, re.S)
            self.assertIsNotNone(match, name)
            functions.append(match.group())
        script = """
const state = {models: [{alias: 'synthetic-chat', provider: 'synthetic-provider', hosting: 'local', testedOk: true}],
               customProviders: [{id: 'synthetic-provider', hosting: 'local'}]};
const document = {getElementById: () => ({value: 'synthetic', checked: false})};
const calls = [];
const api = async (path, payload) => {calls.push({path, payload}); return {success:true};};
const showToast = () => {};
const fetchInitialConfig = () => {};
""" + "\n".join(functions) + """
(async () => {
  await saveModelRouting();
  const cfg = collectConfigFromUI();
  console.log(JSON.stringify({calls, installModels: cfg.llm_gateway.models_routing,
                             installProviders: cfg.llm_gateway.custom_providers}));
})().catch(error => {console.error(error); process.exit(1);});
"""
        proc = subprocess.run([shutil.which("node"), "-"], input=script, text=True, capture_output=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual([call["path"] for call in result["calls"]], ["models/routing"])
        self.assertEqual(result.get("installProviders"), result["calls"][0]["payload"]["custom_providers"])
        self.assertEqual(result["installModels"], result["calls"][0]["payload"]["mappings"])

    def test_routing_panel_has_only_the_combined_save_action(self):
        html = (ROOT / "scripts/wizard_ui/index.html").read_text(encoding="utf-8")
        self.assertFalse('onclick="syncModelAppearance()"' in html)
        self.assertEqual(html.count('onclick="saveModelRouting()"'), 1)


if __name__ == "__main__":
    unittest.main()
