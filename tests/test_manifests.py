#!/usr/bin/env python3
"""
Manifest validation test: checks all deploy/manifests/*.yaml files,
including behavioral consistency, model tiers, and security constraints for v0.7.0
"""

import os
import unittest
import glob

class TestKubernetesManifests(unittest.TestCase):

    def setUp(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.manifests_dir = os.path.join(root_dir, "deploy", "manifests")

    def test_every_hermes_runtime_anchors_dlp_in_the_native_python_environment(self):
        for relative in ("06-hermes-agent.yaml", "templates/hermes-poweruser.template.yaml", "templates/hermes-files.template.yaml"):
            with open(os.path.join(self.manifests_dir, relative), encoding="utf-8") as source:
                manifest = source.read()
            with self.subTest(runtime=relative):
                self.assertIn("/opt/arcia-governance/bootstrap.py", manifest)
                self.assertIn("ARCIA_GOVERNANCE_REQUIRED", manifest)
                self.assertIn("/opt/hermes/.venv/lib/python3.14/site-packages/arcia_governance.pth", manifest)
                self.assertIn("subPath: arcia_governance.pth", manifest)
                self.assertIn("hermes-runtime-guard", manifest)

    def test_manifests_directory_exists(self):
        self.assertTrue(os.path.isdir(self.manifests_dir))

    def test_all_manifests_are_non_empty(self):
        yaml_files = glob.glob(os.path.join(self.manifests_dir, "*.yaml"))
        self.assertGreaterEqual(len(yaml_files), 7, "Au moins 7 manifestes Kubernetes attendus.")
        for yf in yaml_files:
            with open(yf, "r", encoding="utf-8") as f:
                content = f.read().strip()
            self.assertGreater(len(content), 20, f"Le fichier {yf} est anormalement court ou vide.")

    def test_manifests_contain_apiversion_and_kind(self):
        yaml_files = glob.glob(os.path.join(self.manifests_dir, "*.yaml"))
        for yf in yaml_files:
            with open(yf, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("apiVersion:", content, f"apiVersion manquant dans {yf}")
            self.assertIn("kind:", content, f"kind manquant dans {yf}")
            self.assertIn("metadata:", content, f"metadata manquant dans {yf}")

    def test_litellm_v03_configuration(self):
        """Vérifie la présence des 5 profils canoniques v0.7.0, des fallbacks valides, du guardrail Presidio et de la sécurité."""
        litellm_path = os.path.join(self.manifests_dir, "05-litellm.yaml")
        with open(litellm_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("simple/free", content)
        self.assertIn("simple/auto", content)
        self.assertIn("agentic/free", content)
        self.assertIn("agentic/auto", content)
        self.assertIn("agentic/expert", content)
        # Modèles dépréciés ou anciens alias retirés
        self.assertNotIn("openrouter/anthropic/claude-3.5-sonnet\n", content)
        self.assertNotIn("arcia/standard", content)
        self.assertNotIn("arcia/reasoning", content)
        # Fallbacks bien placés dans router_settings
        self.assertIn("router_settings:\n      fallbacks:", content)
        # Guardrail Presidio actif
        self.assertIn("guardrail: presidio", content)
        self.assertIn("default_on: true", content)
        # Variable d'insécurité supprimée
        self.assertNotIn("LITELLM_DANGEROUSLY_PERMIT_WEAK_OR_UNSET_MASTER_KEY", content)
        self.assertIn("LITELLM_MASTER_KEY", content)
        self.assertIn("DATABASE_URL", content)
        self.assertIn("store_model_in_db: true", content)
        self.assertIn("STORE_MODEL_IN_DB", content)
        self.assertIn("type: NodePort", content)
        self.assertIn("nodePort: 30400", content)
        self.assertIn("callbacks: error_handler.proxy_handler_instance", content)
        self.assertIn("litellm-error-handler", content)

    def test_open_webui_v03_security(self):
        """Vérifie le verrouillage strict d'Open-WebUI (pas d'inscription publique, rôle user standard, contrôle d'accès)."""
        webui_path = os.path.join(self.manifests_dir, "07-open-webui.yaml")
        with open(webui_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('name: ENABLE_DIRECT_CONNECTIONS\n          value: "false"', content)
        self.assertIn('name: ENABLE_FORWARD_USER_INFO_HEADERS\n          value: "true"', content)
        self.assertIn('name: DEFAULT_MODELS\n          value: "simple/auto"', content)
        self.assertIn('name: ENABLE_SIGNUP\n          value: "false"', content)
        self.assertIn('name: DEFAULT_USER_ROLE\n          value: "user"', content)
        self.assertIn('name: BYPASS_MODEL_ACCESS_CONTROL\n          value: "false"', content)
        self.assertIn('name: OAUTH_MERGE_ACCOUNTS_BY_EMAIL\n          value: "true"', content)
        self.assertIn('name: litellm-secret\n              key: master-key', content)
        self.assertIn('name: OPENAI_API_BASE_URLS\n          value: "http://litellm-proxy.arcia.svc:4000/v1;http://127.0.0.1:8080/api/v1/arcia/hermes/v1"', content)
        self.assertNotIn("hermes-gateway-secret", content, "Le portail ne doit plus recevoir la clé du runtime central partagé")
        self.assertIn('name: OPENAI_API_CONFIGS', content)
        self.assertIn('"0":{"enable":true', content)
        self.assertIn('"1":{"enable":true', content)
        self.assertIn('name: ENABLE_COMMUNITY_SHARING\n          value: "false"', content)

    def test_ingress_v1_rate_limited(self):
        """Vérifie que l'Ingress /v1 est séparé et protégé par le middleware RateLimit et que LiteLLM UI n'est pas exposé sur l'Ingress public."""
        ingress_path = os.path.join(self.manifests_dir, "04-ingress.yaml")
        with open(ingress_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("name: arcia-v1-ingress", content)
        self.assertIn("arcia-litellm-ratelimit@kubernetescrd", content)
        self.assertIn("name: litellm-ratelimit", content)
        # L'interface graphique LiteLLM ne doit PAS être exposée sur Internet
        self.assertNotIn("arcia-litellm-ui-ingress", content)
        self.assertNotIn("path: /ui", content)

    def test_teams_bot_health_probes(self):
        """Vérifie que les sondes de Teams Bot ciblent /healthz et que le code est monté via ConfigMap teams-bot-code."""
        teams_path = os.path.join(self.manifests_dir, "08-teams-bot.yaml")
        with open(teams_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("path: /healthz", content)
        self.assertNotIn("path: /api/teams/messages\n            port: 3978", content)
        self.assertIn("LITELLM_API_KEY", content)
        self.assertIn("name: teams-bot-code", content)
        self.assertIn('value: "simple/auto"', content)

    def test_hermes_native_config(self):
        """Vérifie que Hermes utilise ~/.hermes/config.yaml, démarre la gateway, expose model_routes et active le plugin de gouvernance DLP/CCR."""
        hermes_path = os.path.join(self.manifests_dir, "06-hermes-agent.yaml")
        with open(hermes_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("provider: custom", content)
        self.assertIn("base_url: http://litellm-proxy.arcia.svc:4000/v1", content)
        self.assertIn("mode: smart", content)
        self.assertIn("unattended_mode: approve", content)
        self.assertIn("external_dirs:", content)
        self.assertIn("hermes gateway &", content)
        self.assertIn("OPENAI_API_KEY", content)
        self.assertIn("path: /api/health", content)
        self.assertIn("direct_model_requests: true", content)
        self.assertIn("model_routes:", content)
        self.assertIn("agentic/auto:", content)
        self.assertIn("agentic/free:", content)
        self.assertIn("agentic/expert:", content)
        self.assertIn("PRESIDIO_DLP_URL", content)
        self.assertIn("PRESIDIO_FAIL_CLOSED", content)
        self.assertIn("hermes-governance-plugin", content)
        self.assertNotIn("OPENAI_API_BASE", content)
        self.assertNotIn("OPENAI_MODEL_NAME", content)
        self.assertNotIn("arcia_tokenmaxing.py", content)

    def test_litellm_db_manifest_present(self):
        """Vérifie que la base comptable LiteLLM PostgreSQL et drop_params sont déclarés."""
        db_path = os.path.join(self.manifests_dir, "05-litellm-db.yaml")
        self.assertTrue(os.path.isfile(db_path))
        with open(db_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("kind: StatefulSet", content)
        self.assertIn("name: litellm-db", content)

        litellm_path = os.path.join(self.manifests_dir, "05-litellm.yaml")
        with open(litellm_path, "r", encoding="utf-8") as f:
            litellm_content = f.read()
        self.assertIn("drop_params: true", litellm_content)

    def test_network_policy_manifest_present(self):
        """Vérifie que les politiques d'isolation réseau NetworkPolicy sont déclarées."""
        netpol_path = os.path.join(self.manifests_dir, "09-network-policy.yaml")
        self.assertTrue(os.path.isfile(netpol_path))
        with open(netpol_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("name: arcia-default-deny-all", content)
        self.assertIn("name: arcia-litellm-policy", content)
        self.assertIn("name: arcia-presidio-policy", content)
        self.assertIn("name: arcia-hermes-policy", content)
        self.assertIn("name: arcia-open-webui-policy", content)


if __name__ == "__main__":
    unittest.main()
