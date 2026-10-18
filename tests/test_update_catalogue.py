"""Le centre de mise à jour conserve le catalogue d'instance et les volumes RWO."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy
import wizard


class UpdateRunner:
    mode = "remote-ssh"
    ssh_node = "synthetic"
    known_hosts = None
    ident_key = None

    def __init__(self):
        self.manifests = []
        self.commands = []

    def apply_manifest(self, manifest):
        self.manifests.extend(d for d in yaml.safe_load_all(manifest) if d)

    def run(self, args, stdin_input=None, timeout=None):
        self.commands.append((args, stdin_input))
        if args[0] == "exec":
            return 0, 'ARCIA_BRANDING_RESULT={"runtime_loaded":true,"assets_served":true}\n', ""
        return 0, "", ""


class TestUpdateCatalogue(unittest.TestCase):
    def run_update(self, mappings):
        cfg = {"kubernetes": {"namespace": "synthetic"},
               "llm_gateway": {"models_routing": mappings, "default_model": "synthetic-chat"},
               "hermes": {"default_model": "synthetic-agent"}}
        runner = UpdateRunner()
        with patch.object(wizard, "load_config_data", return_value=(cfg, True)), \
                patch.object(deploy, "K8sRunner", return_value=runner), \
                patch.object(deploy, "sync_native_skills"), \
                patch.object(wizard, "repair_corrupted_manifest_images", return_value=[]), \
                contextlib.redirect_stdout(io.StringIO()):
            wizard.run_update_worker(["litellm-proxy", "hermes-agent", "open-webui"])
        self.assertEqual(wizard.update_state["status"], "success", wizard.update_state["logs"][-1:])
        return runner

    def test_update_preserves_only_declared_models_and_branding_revision(self):
        runner = self.run_update([
            {"alias": "synthetic-chat", "category": "simple", "target_model": "openrouter/auto"},
            {"alias": "synthetic-agent", "category": "agentic", "target_model": "openrouter/auto"},
        ])
        configs = {m["metadata"]["name"]: m for m in runner.manifests if m["kind"] == "ConfigMap"}
        litellm = yaml.safe_load(configs["litellm-config"]["data"]["config.yaml"])
        self.assertEqual([m["model_name"] for m in litellm["model_list"]], ["synthetic-chat", "synthetic-agent"])
        hermes = yaml.safe_load(configs["hermes-config"]["data"]["config.yaml"])
        self.assertEqual(hermes["providers"]["custom"]["models"], ["synthetic-agent"])
        webui = next(m for m in runner.manifests if m["kind"] == "Deployment" and m["metadata"]["name"] == "open-webui")
        env = {e["name"]: e.get("value") for e in webui["spec"]["template"]["spec"]["containers"][0]["env"]}
        self.assertEqual(json.loads(env["OPENAI_API_CONFIGS"]), {
            "0": {"enable": True, "model_ids": ["synthetic-chat"]},
            "1": {"enable": True, "model_ids": ["synthetic-agent"]},
        })
        self.assertNotEqual(webui["spec"]["template"]["metadata"]["annotations"]["checksum/arcia-webui-branding"], "default")

    def test_update_never_enables_concurrent_openwebui_writers(self):
        runner = self.run_update([])
        for args, body in runner.commands:
            if args[:3] == ["patch", "deployment", "open-webui"] and "-p" in args:
                strategy = json.loads(args[args.index("-p") + 1]).get("spec", {}).get("strategy", {})
                self.assertNotEqual(strategy.get("type"), "RollingUpdate")
        webui = next(m for m in runner.manifests if m["kind"] == "Deployment" and m["metadata"]["name"] == "open-webui")
        self.assertEqual(webui["spec"]["strategy"], {"type": "Recreate"})


if __name__ == "__main__":
    unittest.main()
