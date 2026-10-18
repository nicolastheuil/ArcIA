"""Régressions du parcours wizard -> déploiement -> catalogue LiteLLM."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy
import wizard
import diagnose_litellm


class RecordingRunner:
    def __init__(self, failure=None):
        self.mode = "local"
        self.calls = []
        self.manifests = []
        self.failure = failure

    def run(self, args, stdin_input=None, timeout=None):
        self.calls.append((args, stdin_input))
        if self.failure and args[:len(self.failure)] == self.failure:
            return 1, "", "synthetic failure"
        if args[:3] == ["get", "secret", "litellm-secret"]:
            data = {k: base64.b64encode(v.encode()).decode() for k, v in {
                "master-key": "sk-synthetic-existing-master",
                "salt-key": "synthetic-salt", "db-password": "synthetic-password",
                "openrouter-key": "sk-or-synthetic-existing",
                "database-url": "postgresql://synthetic",
            }.items()}
            return 0, json.dumps({"data": data}), ""
        return 0, "", ""

    def apply_manifest(self, manifest):
        self.manifests.append(manifest)


class TestRoutingPipeline(unittest.TestCase):
    def test_wizard_roundtrip_preserves_gateway_credentials_and_four_models(self):
        cfg = {"llm_gateway": {
            "master_key": "sk-synthetic-master", "salt_key": "synthetic-salt",
            "db_password": "synthetic-db", "models_routing": [
                {"alias": f"simple/model-{i}", "target_model": "openrouter/auto"}
                for i in range(4)
            ]}}
        result = deploy.parse_simple_yaml(wizard.serialize_yaml_config(cfg))
        for field in ("master_key", "salt_key", "db_password", "models_routing"):
            self.assertEqual(result["llm_gateway"].get(field), cfg["llm_gateway"][field])

    def test_explicit_agentic_mappings_are_not_dropped(self):
        mappings = [
            {"alias": "simple/free", "target_model": "openrouter/openrouter/free"},
            {"alias": "simple/auto", "target_model": "openrouter/auto"},
            {"alias": "agentic/free", "target_model": "openrouter/openrouter/free"},
            {"alias": "agentic/auto", "target_model": "openrouter/auto"},
        ]
        config = deploy.build_litellm_config_data({"llm_gateway": {"models_routing": mappings}})
        self.assertEqual(config.count("model_name:"), 4)

    def test_deployment_reaches_dynamic_catalogue_and_preserves_identity(self):
        runner = RecordingRunner()
        cfg = {"kubernetes": {"namespace": "arcia"}, "network": {"tls_mode": "disabled"},
               "llm_gateway": {"models_routing": [
                   {"alias": "simple/synthetic", "target_model": "openrouter/auto"}
               ]}}
        with tempfile.TemporaryDirectory() as directory:
            # Read generic sources from the real harness; no instance file exists here.
            for name in ("services", "deploy", "assets", "skills"):
                import shutil
                shutil.copytree(ROOT / name, Path(directory) / name)
            with patch.object(deploy, "K8sRunner", return_value=runner), contextlib.redirect_stdout(io.StringIO()):
                deploy.deploy_arcia(cfg, directory)
        manifests = "\n".join(runner.manifests)
        self.assertIn('model_name: "simple/synthetic"', manifests)
        self.assertIn('master-key: "sk-synthetic-existing-master"', manifests)
        self.assertIn('salt-key: "synthetic-salt"', manifests)
        self.assertIn('db-password: "synthetic-password"', manifests)
        self.assertTrue(any(args[:2] == ["rollout", "status"] for args, _ in runner.calls))
        first_proxy_manifest = next(m for m in runner.manifests if "name: litellm-proxy" in m and "kind: Deployment" in m)
        self.assertIn('model_name: "simple/synthetic"', first_proxy_manifest)
        self.assertIn("checksum/litellm-config:", first_proxy_manifest)
        self.assertIn("checksum/litellm-secret:", first_proxy_manifest)

    def test_sync_refuses_to_claim_success_when_restart_fails(self):
        runner = RecordingRunner(failure=["rollout", "restart"])
        self.assertFalse(wizard.sync_litellm_configmap({}, runner, "arcia"))

    def test_sync_refuses_to_claim_success_when_rollout_fails(self):
        runner = RecordingRunner(failure=["rollout", "status"])
        self.assertFalse(wizard.sync_litellm_configmap({}, runner, "arcia"))

    def test_litellm_token_has_required_proxy_key_prefix(self):
        self.assertTrue(wizard.generate_token("litellm").startswith("sk-"))

    def test_diagnostic_executes_probe_without_exposing_credentials(self):
        cfg = {"llm_gateway": {"models_routing": [{"alias": "simple/test", "target_model": "openrouter/auto"}]}}
        config = deploy.build_litellm_config_data(cfg)

        class ProbeRunner(RecordingRunner):
            def run(self, args, stdin_input=None, timeout=None):
                if args[:2] == ["get", "configmap"]:
                    return 0, json.dumps({"data": {"config.yaml": config}}), ""
                if args[0] == "exec":
                    # Execute the actual transferred program with only HTTP replaced.
                    output = io.StringIO()
                    response = unittest.mock.MagicMock()
                    response.status = 200
                    response.read.return_value = b'{"data":[{"id":"simple/test","model_name":"simple/test"}]}'
                    response.__enter__.return_value = response
                    with patch.dict(os.environ, {"LITELLM_MASTER_KEY": "sk-synthetic-existing-master"}), \
                            patch("urllib.request.urlopen", return_value=response), \
                            patch.object(Path, "read_bytes", return_value=config.encode()), \
                            contextlib.redirect_stdout(output):
                        try:
                            exec(stdin_input, {})
                        except Exception:
                            return 1, "", "probe failed"
                    return 0, output.getvalue(), ""
                return super().run(args, stdin_input, timeout)

        result = diagnose_litellm.diagnose(cfg, ProbeRunner())
        self.assertTrue(result["pod_probe_ok"])
        self.assertTrue(result["pod_master_matches_secret"])
        self.assertEqual(result["models_http_status"], 200)
        self.assertEqual(result["admin_models_count"], 1)
        self.assertNotIn("sk-synthetic", json.dumps(result))

    def test_model_alias_takes_precedence_over_display_name(self):
        config = deploy.build_litellm_config_data({"llm_gateway": {"models_routing": [
            {"name": "Chat", "alias": "simple/chat", "target_model": "openrouter/auto"}
        ]}})
        self.assertIn('model_name: "simple/chat"', config)

    def test_provider_keys_are_updated_without_replacing_master_salt_or_db(self):
        runner = RecordingRunner()
        cfg = {"llm_gateway": {"openai_api_key": "sk-synthetic-openai"}}
        wizard.sync_litellm_configmap(cfg, runner, "arcia")
        updates = [json.loads(m) for m in runner.manifests if m.startswith('{')]
        secret = next((m for m in updates if m.get("kind") == "Secret"), {})
        self.assertEqual(secret.get("data", {}).get("openai-key"), base64.b64encode(b"sk-synthetic-openai").decode())
        self.assertEqual(secret.get("data", {}).get("master-key"), base64.b64encode(b"sk-synthetic-existing-master").decode())

    def test_routing_save_reports_local_only_when_cluster_unavailable(self):
        runner = RecordingRunner(failure=["get", "namespace"])
        with tempfile.TemporaryDirectory() as directory, patch.object(wizard, "ROOT_DIR", directory), \
                patch.object(wizard, "get_k8s_runner", return_value=runner):
            result = wizard.save_model_routing_config({"mappings": []}, str(Path(directory) / "config.yaml"))
        self.assertTrue(result["success"])
        self.assertFalse(result["cm_synced"])
        self.assertIn("non appliqué", result["message"])

    def test_catalog_projection_simple_and_agentic(self):
        cfg = {
            "llm_gateway": {
                "default_model": "custom-simple",
                "models_routing": [
                    {"alias": "custom-simple", "category": "simple", "target_model": "openrouter/auto"},
                    {"alias": "custom-agentic", "category": "agentic", "target_model": "openrouter/anthropic/claude-3.7-sonnet"}
                ]
            },
            "hermes": {
                "default_model": "custom-agentic"
            }
        }
        catalog = deploy.build_model_catalog(cfg)
        self.assertEqual(catalog["simple_models"], ["custom-simple"])
        self.assertEqual(catalog["agentic_models"], ["custom-agentic"])
        self.assertEqual(catalog["default_simple"], "custom-simple")
        self.assertEqual(catalog["default_agentic"], "custom-agentic")

        # Open-WebUI configs
        configs = json.loads(deploy.build_openwebui_api_configs(cfg))
        self.assertTrue(configs["0"]["enable"])
        self.assertEqual(configs["0"]["model_ids"], ["custom-simple"])
        self.assertTrue(configs["1"]["enable"])
        self.assertEqual(configs["1"]["model_ids"], ["custom-agentic"])

        # Hermes config
        hermes_cfg = deploy.build_hermes_config_data(cfg, namespace="arcia")
        self.assertIn("discover_models: false", hermes_cfg)
        self.assertIn("- custom-agentic", hermes_cfg)
        self.assertNotIn("- custom-simple", hermes_cfg)
        self.assertIn('model_name: "custom-agentic"', hermes_cfg)
        self.assertIn('custom-agentic:\n            model: "custom-agentic"', hermes_cfg)

    def test_empty_category_disables_connection(self):
        # Cas 1 : Aucun modèle agentique déclaré
        cfg_only_simple = {
            "llm_gateway": {
                "models_routing": [
                    {"alias": "simple/only", "category": "simple", "target_model": "openrouter/auto"}
                ]
            }
        }
        configs_simple = json.loads(deploy.build_openwebui_api_configs(cfg_only_simple))
        self.assertTrue(configs_simple["0"]["enable"])
        self.assertEqual(configs_simple["0"]["model_ids"], ["simple/only"])
        self.assertFalse(configs_simple["1"]["enable"])
        self.assertEqual(configs_simple["1"]["model_ids"], [])

        # Cas 2 : Aucun modèle simple déclaré
        cfg_only_agentic = {
            "llm_gateway": {
                "models_routing": [
                    {"alias": "agentic/only", "category": "agentic", "target_model": "openrouter/auto"}
                ]
            }
        }
        configs_agentic = json.loads(deploy.build_openwebui_api_configs(cfg_only_agentic))
        self.assertFalse(configs_agentic["0"]["enable"])
        self.assertEqual(configs_agentic["0"]["model_ids"], [])
        self.assertTrue(configs_agentic["1"]["enable"])
        self.assertEqual(configs_agentic["1"]["model_ids"], ["agentic/only"])

        # Cas 3 : Catalogue explicitement vide
        cfg_empty = {"llm_gateway": {"models_routing": []}}
        configs_empty = json.loads(deploy.build_openwebui_api_configs(cfg_empty))
        self.assertFalse(configs_empty["0"]["enable"])
        self.assertEqual(configs_empty["0"]["model_ids"], [])
        self.assertFalse(configs_empty["1"]["enable"])
        self.assertEqual(configs_empty["1"]["model_ids"], [])

    def test_explicit_catalog_does_not_inject_canonical_models(self):
        cfg = {
            "llm_gateway": {
                "models_routing": [
                    {"alias": "enterprise-chat", "category": "simple", "target_model": "openrouter/auto"}
                ]
            }
        }
        catalog = deploy.build_model_catalog(cfg)
        self.assertEqual(len(catalog["all_models"]), 1)
        self.assertEqual(catalog["all_models"][0]["id"], "enterprise-chat")

        configs = json.loads(deploy.build_openwebui_api_configs(cfg))
        self.assertNotIn("simple/auto", configs["0"]["model_ids"])
        self.assertNotIn("simple/free", configs["0"]["model_ids"])
        self.assertNotIn("agentic/auto", configs["1"]["model_ids"])

        branding = deploy.compute_models_branding_dict(cfg)
        self.assertIn("enterprise-chat", branding["models"])
        self.assertNotIn("local/model", branding["models"])

    def test_store_model_in_db_is_disabled(self):
        config = deploy.build_litellm_config_data({"llm_gateway": {"models_routing": []}})
        self.assertIn("store_model_in_db: false", config)

    def test_openwebui_manifest_server_side_restrictions(self):
        manifest_path = ROOT / "deploy" / "manifests" / "07-open-webui.yaml"
        content = manifest_path.read_text(encoding="utf-8")
        self.assertIn('name: ENABLE_DIRECT_CONNECTIONS\n          value: "false"', content)
        self.assertIn('name: ENABLE_COMMUNITY_SHARING\n          value: "false"', content)
        self.assertIn('name: BYPASS_MODEL_ACCESS_CONTROL\n          value: "false"', content)
        self.assertIn('name: DEFAULT_USER_ROLE\n          value: "user"', content)
        self.assertNotIn("MODEL_FILTER_LIST", content)
        self.assertNotIn("ENABLE_MODEL_FILTER", content)

    def test_three_component_sync_reports_per_component_status(self):
        runner = RecordingRunner()
        cfg = {
            "kubernetes": {"namespace": "arcia"},
            "llm_gateway": {
                "models_routing": [
                    {"alias": "simple/test", "category": "simple", "target_model": "openrouter/auto"},
                    {"alias": "agentic/test", "category": "agentic", "target_model": "openrouter/anthropic/claude-3.7-sonnet"}
                ]
            }
        }
        with tempfile.TemporaryDirectory() as directory, patch.object(wizard, "ROOT_DIR", directory), \
                patch.object(wizard, "get_k8s_runner", return_value=runner):
            res = wizard.save_model_routing_config({
                "mappings": cfg["llm_gateway"]["models_routing"],
                "default_model": "simple/test",
                "hermes_default_model": "agentic/test"
            }, str(Path(directory) / "config.yaml"))

        self.assertTrue(res["success"])
        self.assertTrue(res["litellm_synced"])
        self.assertTrue(res["hermes_synced"])
        self.assertTrue(res["openwebui_synced"])
        self.assertTrue(res["all_synced"])
        self.assertIn("Passerelle LiteLLM, moteur Hermes et portail Open-WebUI synchronisés", res["message"])

    def test_error_handler_differentiates_session_and_keys(self):
        sys.path.insert(0, str(ROOT / "services" / "litellm"))
        import error_handler

        # 1. Rejet de session administrative (token_not_found_in_db)
        code, msg = error_handler.format_user_friendly_error("token_not_found_in_db: Token sk-synthetic not found", 401)
        self.assertEqual(code, 401)
        self.assertIn("Session d'administration expirée ou invalide", msg)
        self.assertIn("déconnecter", msg)
        self.assertNotIn("sk-synthetic", msg)

        # 2. Clé virtuelle non autorisée
        code_v, msg_v = error_handler.format_user_friendly_error("user does not have access to model", 401)
        self.assertEqual(code_v, 401)
        self.assertIn("Jeton d'inférence non autorisé", msg_v)

        # 3. Clé fournisseur invalide
        code_p, msg_p = error_handler.format_user_friendly_error("AuthenticationError: invalid_api_key from OpenRouter", 401)
        self.assertEqual(code_p, 401)
        self.assertIn("Erreur d'authentification", msg_p)


if __name__ == "__main__":
    unittest.main()

