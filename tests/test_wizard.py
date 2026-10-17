#!/usr/bin/env python3
"""
Unit tests for ArcIA Setup Wizard (scripts/wizard.py).
"""

import os
import sys
import unittest
import tempfile
import json
from unittest.mock import patch, MagicMock

# Ajouter scripts/ au sys.path
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "scripts"))

import wizard
import deploy

class TestArcIAWizard(unittest.TestCase):

    def setUp(self):
        self.root_dir = SCRIPT_DIR
        self.config_example_path = os.path.join(self.root_dir, "arcia.config.yaml.example")

    def test_generate_token_kinds(self):
        """Vérifie la génération de tokens cryptographiques pour chaque usage."""
        pat = wizard.generate_token("pat")
        self.assertTrue(pat.startswith("arcia-pat-"))
        self.assertGreater(len(pat), 20)

        cookie = wizard.generate_token("cookie")
        self.assertGreater(len(cookie), 30)

        admin = wizard.generate_token("admin")
        self.assertGreater(len(admin), 10)

        presidio = wizard.generate_token("presidio")
        self.assertTrue(presidio.startswith("arcia-master-"))

        # Vérifier l'entropie (deux appels ne produisent pas le même token)
        pat2 = wizard.generate_token("pat")
        self.assertNotEqual(pat, pat2)

    def test_default_config_structure(self):
        """Vérifie que la configuration par défaut contient toutes les sections nécessaires."""
        cfg = wizard.get_default_config_dict()
        required_sections = [
            "kubernetes", "network", "llm_gateway", "hermes",
            "presidio", "open_webui", "entra_id_sso", "teams_bot"
        ]
        for section in required_sections:
            self.assertIn(section, cfg, f"Section manquante : {section}")

        self.assertNotIn("omniroute", cfg)
        self.assertEqual(cfg["llm_gateway"]["default_model"], "simple/auto")

        # Vérifier que les composants internes sont activés par défaut
        self.assertTrue(cfg["presidio"]["enabled"])
        self.assertTrue(cfg["open_webui"]["enabled"])
        # Vérifier que les composants optionnels sont désactivés par défaut
        self.assertFalse(cfg["entra_id_sso"]["enabled"])
        self.assertFalse(cfg["teams_bot"]["enabled"])

    def test_ensure_config_defaults_cleans_placeholders(self):
        """Vérifie que ensure_config_defaults nettoie les placeholders d'exemple."""
        cfg = wizard.get_default_config_dict()
        cfg["network"]["public_fqdn"] = "assistant.example.org"
        cfg["network"]["acme_email"] = "admin@example.org"
        cfg["llm_gateway"]["openrouter_api_key"] = "sk-or-v1-xxxx123"

        cleaned = wizard.ensure_config_defaults(cfg)
        self.assertEqual(cleaned["network"]["public_fqdn"], "")
        self.assertEqual(cleaned["network"]["acme_email"], "")
        self.assertEqual(cleaned["llm_gateway"]["openrouter_api_key"], "")

    def test_serialize_and_parse_roundtrip(self):
        """Vérifie que la sérialisation YAML du Wizard est parfaitement ré-analysable par deploy.py."""
        cfg = wizard.get_default_config_dict()
        cfg["network"]["public_fqdn"] = "assistant.corp.internal"
        cfg["network"]["acme_email"] = "ops@corp.internal"
        cfg["llm_gateway"]["openrouter_api_key"] = "sk-or-v1-real-key-123456789"
        cfg["entra_id_sso"]["enabled"] = True
        cfg["entra_id_sso"]["tenant_id"] = "tenant-uuid-123"
        cfg["teams_bot"]["enabled"] = True
        cfg["teams_bot"]["app_id"] = "bot-appid-123"

        yaml_output = wizard.serialize_yaml_config(cfg)
        self.assertIn('public_fqdn: "assistant.corp.internal"', yaml_output)
        self.assertIn('tenant_id: "tenant-uuid-123"', yaml_output)
        self.assertIn('app_id: "bot-appid-123"', yaml_output)

        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".yaml", encoding="utf-8") as tmp:
            tmp_path = tmp.name
            tmp.write(yaml_output)

        try:
            parsed = deploy.parse_yaml_or_env(tmp_path)
            self.assertEqual(parsed["network"]["public_fqdn"], "assistant.corp.internal")
            self.assertEqual(parsed["llm_gateway"]["openrouter_api_key"], "sk-or-v1-real-key-123456789")
            self.assertTrue(parsed["entra_id_sso"]["enabled"])
            self.assertEqual(parsed["entra_id_sso"]["tenant_id"], "tenant-uuid-123")
            self.assertTrue(parsed["teams_bot"]["enabled"])
            self.assertEqual(parsed["teams_bot"]["app_id"], "bot-appid-123")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_html_page_contains_all_screens_and_guides(self):
        """Vérifie que la page HTML du Wizard contient les 10 écrans sans OmniRoute et les liens documentaires."""
        html = wizard.get_wizard_html_page()
        for i in range(1, 11):
            self.assertIn(f'id="step{i}"', html, f"Écran manquant : step{i}")

        # OmniRoute doit être retiré des écrans du Wizard
        self.assertNotIn("Routeur Multi-Fournisseurs OmniRoute", html)
        self.assertNotIn('id="step11"', html)

        # Vérifier la présence de l'import YAML
        self.assertIn("triggerYamlUpload()", html)
        self.assertIn('id="yamlFileInput"', html)
        self.assertIn('id="cardUploadYaml"', html)

        # Vérifier la présence des guides pas-à-pas et des liens GitHub
        self.assertIn("portail-webui-entraid.md#creation-app-entraid", html)
        self.assertIn("integration-teams.md#creation-azure-bot", html)
        self.assertIn("Presidio DLP", html)
        self.assertIn("Graphify", html)
        self.assertIn("Ponytail", html)
        self.assertIn("Public-APIs", html)
        self.assertIn("ArcIA-instance-", html)

    def test_find_available_port(self):
        """Vérifie que la détection d'un port disponible fonctionne."""
        port = wizard.find_available_port(8765)
        self.assertIsInstance(port, int)
        self.assertGreaterEqual(port, 8765)

    def test_encrypt_and_decrypt_instance_bundle_roundtrip(self):
        """Vérifie le cycle complet de chiffrement et déchiffrement des secrets d'instance."""
        secrets_payload = {
            "llm_gateway": {"openrouter_api_key": "sk-or-v1-secret-key-xyz987"},
            "entra_id_sso": {"client_secret": "my-ultra-secret-azure-client-key"},
            "teams_bot": {"app_password": "super-strong-teams-bot-password"},
            "open_webui": {"admin_password": "custom-admin-password-1234"},
        }
        passphrase = "Master-Enterprise-Passphrase-2026!"

        encrypted_bundle = wizard.encrypt_instance_bundle(secrets_payload, passphrase)
        self.assertIn("schema", encrypted_bundle)
        self.assertIn("algo", encrypted_bundle)
        self.assertIn("salt", encrypted_bundle)
        self.assertIn("nonce", encrypted_bundle)
        self.assertIn("ciphertext", encrypted_bundle)

        # Vérifier que les secrets bruts ne figurent nulle part en clair dans le bundle chiffré
        bundle_str = json.dumps(encrypted_bundle)
        self.assertNotIn("sk-or-v1-secret-key-xyz987", bundle_str)
        self.assertNotIn("my-ultra-secret-azure-client-key", bundle_str)
        self.assertNotIn("super-strong-teams-bot-password", bundle_str)

        # Déchiffrement avec la bonne passphrase
        decrypted_payload = wizard.decrypt_instance_bundle(encrypted_bundle, passphrase)
        self.assertEqual(decrypted_payload, secrets_payload)
        self.assertEqual(decrypted_payload["llm_gateway"]["openrouter_api_key"], "sk-or-v1-secret-key-xyz987")
        self.assertEqual(decrypted_payload["entra_id_sso"]["client_secret"], "my-ultra-secret-azure-client-key")

    def test_decrypt_instance_bundle_invalid_passphrase(self):
        """Vérifie que le déchiffrement avec un mot de passe erroné lève une exception ValueError."""
        secrets_payload = {"key": "secret-value"}
        passphrase = "Valid-Passphrase-123"
        encrypted_bundle = wizard.encrypt_instance_bundle(secrets_payload, passphrase)

        with self.assertRaises(ValueError):
            wizard.decrypt_instance_bundle(encrypted_bundle, "Wrong-Passphrase-999")

    def test_vmware_sizing_tiers(self):
        """Vérifie la définition des tranches de dimensionnement VMware vSphere."""
        tiers = wizard.VMWARE_SIZING_TIERS
        self.assertIn("20", tiers)
        self.assertIn("100", tiers)
        self.assertIn("500", tiers)
        self.assertIn("1000", tiers)

        # Vérifier que le profil 100 utilisateurs est HA et recommandé
        tier_100 = tiers["100"]
        self.assertTrue(tier_100["recommended"])
        self.assertEqual(tier_100["nodes"], 3)
        self.assertEqual(tier_100["total_vcpu"], 12)
        self.assertEqual(tier_100["total_ram_gb"], 48)
        self.assertEqual(tier_100["rag_storage_gb"], 200)
        self.assertEqual(tier_100["open_webui_pvc"], "200Gi")

        # Vérifier le profil Pilote 20 utilisateurs
        tier_20 = tiers["20"]
        self.assertEqual(tier_20["nodes"], 1)
        self.assertEqual(tier_20["total_vcpu"], 4)
        self.assertEqual(tier_20["rag_storage_gb"], 50)
        self.assertEqual(tier_20["open_webui_pvc"], "50Gi")

    def test_vmware_connection_validation_missing_host(self):
        """Vérifie que le testeur VMware rejette les requêtes sans hôte."""
        res = wizard.test_vmware_connection({})
        self.assertFalse(res["success"])
        self.assertIn("obligatoire", res["error"])

    def test_vmware_no_version_stipulation(self):
        """Vérifie qu'aucune version rigide de vCenter (ex: 7.0 / 8.0) n'est stipulée."""
        html = wizard.get_wizard_html_page()
        self.assertNotIn("7.0 / 8.0", html)
        self.assertNotIn("vCenter 7.0", html)
        self.assertNotIn("vCenter 8.0", html)

    def test_vmware_resource_overrides_and_dissociated_storage_in_html(self):
        """Vérifie la présence des champs d'override de ressources et de dissociation du compte stockage."""
        html = wizard.get_wizard_html_page()
        # Overrides matériels
        self.assertIn("vmware_custom_nodes", html)
        self.assertIn("vmware_custom_vcpu", html)
        self.assertIn("vmware_custom_ram", html)
        self.assertIn("vmware_custom_disk", html)
        self.assertIn("vmware_custom_rag", html)

        # Dissociation du compte de stockage
        self.assertIn("vmware_storage_separate", html)
        self.assertIn("vmware_storage_type", html)
        self.assertIn("vmware_storage_user", html)
        self.assertIn("vmware_storage_pass", html)
        self.assertIn("vmware_storage_endpoint", html)

        # Listes déroulantes de découverte dynamique
        self.assertIn("vmware_dc_select", html)
        self.assertIn("vmware_cluster_select", html)
        self.assertIn("vmware_ds_select", html)
        self.assertIn("vmware_pg_select", html)

    def test_discover_vsphere_resources_parsing(self):
        """Vérifie que discover_vsphere_resources extrait correctement les objets vSphere."""
        dummy_dc = {"value": [{"datacenter": "dc-1", "name": "Datacenter-Paris"}]}
        dummy_cluster = {"value": [{"cluster": "c-1", "name": "Cluster-Compute"}]}
        dummy_ds = {"value": [{"datastore": "ds-1", "name": "vsanDatastore", "free_space": 1073741824000, "capacity": 2147483648000}]}
        dummy_net = {"value": [{"network": "net-1", "name": "VM-Network-VLAN10"}]}

        def mock_urlopen(req, timeout=8, context=None):
            url = req.full_url
            mock_resp = MagicMock()
            mock_resp.status = 200
            if "datacenter" in url:
                mock_resp.read.return_value = json.dumps(dummy_dc).encode("utf-8")
            elif "cluster" in url:
                mock_resp.read.return_value = json.dumps(dummy_cluster).encode("utf-8")
            elif "resource-pool" in url:
                mock_resp.read.return_value = json.dumps({"value": []}).encode("utf-8")
            elif "datastore" in url:
                mock_resp.read.return_value = json.dumps(dummy_ds).encode("utf-8")
            elif "network" in url:
                mock_resp.read.return_value = json.dumps(dummy_net).encode("utf-8")
            else:
                mock_resp.read.return_value = b"{}"
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.__exit__.return_value = None
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = wizard.discover_vsphere_resources("vcenter.local", 443, "dummy-session-id", None)
            self.assertEqual(len(res["datacenters"]), 1)
            self.assertEqual(res["datacenters"][0]["name"], "Datacenter-Paris")
            self.assertEqual(len(res["clusters"]), 1)
            self.assertEqual(res["clusters"][0]["name"], "Cluster-Compute")
            self.assertEqual(len(res["datastores"]), 1)
            self.assertEqual(res["datastores"][0]["name"], "vsanDatastore")
            self.assertIn("1000.0 Go libres", res["datastores"][0]["label"])
            self.assertEqual(len(res["networks"]), 1)
            self.assertEqual(res["networks"][0]["name"], "VM-Network-VLAN10")

    def test_get_docker_status(self):
        """Vérifie la structure du statut Docker retourné par get_docker_status."""
        st = wizard.get_docker_status()
        self.assertIn("installed", st)
        self.assertIn("running", st)
        self.assertIn("message", st)

    def test_audit_kubernetes_environment_full_mock(self):
        """Vérifie que l'audit de qualification K8s évalue l'ensemble des 6 catégories requises."""
        class MockRunner:
            def run(self, cmd_args, stdin_input=None):
                cmd = " ".join(cmd_args)
                if "version" in cmd:
                    return 0, '{"serverVersion": {"major": "1", "minor": "31", "gitVersion": "v1.31.1"}}', ""
                elif "get nodes" in cmd:
                    return 0, json.dumps({
                        "items": [
                            {"status": {"conditions": [{"type": "Ready", "status": "True"}], "allocatable": {"cpu": "4", "memory": "16Gi"}}},
                            {"status": {"conditions": [{"type": "Ready", "status": "True"}], "allocatable": {"cpu": "4", "memory": "16Gi"}}},
                            {"status": {"conditions": [{"type": "Ready", "status": "True"}], "allocatable": {"cpu": "4", "memory": "16Gi"}}}
                        ]
                    }), ""
                elif "get ingressclass" in cmd:
                    return 0, '{"items": [{"metadata": {"name": "traefik"}}]}', ""
                elif "get crd" in cmd:
                    return 0, "certificates.cert-manager.io\nclusterissuers.cert-manager.io", ""
                elif "get storageclass" in cmd:
                    return 0, '{"items": [{"metadata": {"name": "arcia-vsphere", "annotations": {"storageclass.kubernetes.io/is-default-class": "true"}}}]}', ""
                elif "auth can-i" in cmd:
                    return 0, "yes", ""
                return 0, "", ""

        mock = MockRunner()
        res = wizard.audit_kubernetes_environment_full(mock)
        self.assertTrue(res["success"])
        self.assertTrue(res["all_valid"])
        self.assertEqual(len(res["checks"]), 6)
        check_ids = [c["id"] for c in res["checks"]]
        self.assertIn("api_server", check_ids)
        self.assertIn("nodes_capacity", check_ids)
        self.assertIn("ingress_controller", check_ids)
        self.assertIn("cert_manager", check_ids)
        self.assertIn("storage_class", check_ids)
        self.assertIn("rbac_admin", check_ids)

    def test_html_page_contains_infrastructure_targets(self):
        """Vérifie que la page HTML du Wizard contient les 3 cibles d'hébergement et le dimensionnement."""
        html = wizard.get_wizard_html_page()
        self.assertIn("target_card_vmware", html)
        self.assertIn("target_card_k8s", html)
        self.assertIn("target_card_docker", html)
        self.assertIn("panel_infra_vmware", html)
        self.assertIn("panel_infra_docker", html)
        self.assertIn("panel_infra_k8s", html)
        self.assertIn("tier_card_100", html)
        self.assertIn("testK8sQualificationFull", html)
        self.assertIn("k8s_ssh_key", html)
        self.assertIn("k8s_ssh_key_select", html)

    def test_detect_available_ssh_keys(self):
        """Vérifie que la détection des clés SSH renvoie une liste valide."""
        keys = wizard.detect_available_ssh_keys()
        self.assertIsInstance(keys, list)
        for k in keys:
            self.assertIn("path", k)
            self.assertIn("name", k)

    def test_serialize_and_default_config_includes_ssh_key(self):
        """Vérifie que la clé ssh_key est présente par défaut et correctement sérialisée."""
        cfg = wizard.get_default_config_dict()
        self.assertIn("ssh_key", cfg["kubernetes"]["remote_ssh"])
        cfg["kubernetes"]["remote_ssh"]["ssh_key"] = "C:\\Users\\test\\.ssh\\id_ed25519"
        yaml_text = wizard.serialize_yaml_config(cfg)
        self.assertIn('ssh_key: "C:\\Users\\test\\.ssh\\id_ed25519"', yaml_text)

    def test_audit_diagnoses_ssh_permission_denied(self):
        """Vérifie que l'audit K8s diagnostique précisément un échec d'authentification SSH."""
        class FailingSshRunner:
            mode = "remote-ssh"
            ssh_node = "192.168.1.50"
            ssh_user = "ubuntu"
            ssh_port = 22

            def run(self, cmd_args, stdin_input=None):
                return 255, "", "ubuntu@192.168.1.50: Permission denied (publickey)."

        res = wizard.audit_kubernetes_environment_full(FailingSshRunner())
        self.assertFalse(res["success"])
        api_check = [c for c in res["checks"] if c["id"] == "api_server"][0]
        self.assertEqual(api_check["status"], "error")
        self.assertIn("Permission refusée", api_check["message"])
        self.assertIn("clé privée SSH", api_check["recommendation"])

    def test_serialize_yaml_config_defensive_against_nulls_and_empty_values(self):
        """Vérifie que serialize_yaml_config ne plante pas avec des valeurs None, vides ou manquantes."""
        # Test 1: configuration vide
        out = wizard.serialize_yaml_config({})
        self.assertIn('ssh_port: 22', out)

        # Test 2: port SSH None et chaîne vide
        out2 = wizard.serialize_yaml_config({"kubernetes": {"remote_ssh": {"ssh_port": None}}})
        self.assertIn('ssh_port: 22', out2)

        out3 = wizard.serialize_yaml_config({"kubernetes": {"remote_ssh": {"ssh_port": ""}}})
        self.assertIn('ssh_port: 22', out3)

        # Test 3: sections à None
        out4 = wizard.serialize_yaml_config({
            "kubernetes": None,
            "network": None,
            "llm_gateway": None,
            "hermes": None,
            "presidio": None,
            "open_webui": None,
            "entra_id_sso": None,
            "teams_bot": None
        })
        self.assertIn('ssh_port: 22', out4)
        self.assertIn('mode: "local"', out4)

    def test_git_create_remote_repo_validation(self):
        """Vérifie la validation des paramètres d'entrée de git_create_remote_repo."""
        res_no_token = wizard.git_create_remote_repo("github", "", "test-repo", "owner")
        self.assertFalse(res_no_token["success"])
        self.assertIn("non renseigné", res_no_token["error"])

        res_no_repo = wizard.git_create_remote_repo("github", "ghp_dummy", "", "owner")
        self.assertFalse(res_no_repo["success"])
        self.assertIn("non renseigné", res_no_repo["error"])

    def test_upload_yaml_parsing(self):
        """Vérifie le parsing de YAML uploadé pour préremplir la configuration du wizard."""
        sample_yaml = """
kubernetes:
  mode: "remote-ssh"
  namespace: "arcia-custom"
  remote_ssh:
    node_ip: "192.168.1.100"
    ssh_user: "admin"
    ssh_port: 2222
network:
  public_fqdn: "ia.entreprise.com"
  tls_mode: "custom-secret"
llm_gateway:
  openrouter_api_key: "sk-or-v1-testkey"
  default_model: "arcia/expert"
"""
        import io
        from unittest.mock import MagicMock

        handler = wizard.WizardHTTPHandler.__new__(wizard.WizardHTTPHandler)
        handler.rfile = io.BytesIO(json.dumps({
            "yaml_content": sample_yaml,
            "filename": "arcia.config.yaml"
        }).encode("utf-8"))
        handler.headers = {"Content-Length": str(len(handler.rfile.getvalue())), "Host": "127.0.0.1:8765"}
        handler.path = "/api/config/upload-yaml"
        handler.send_json = MagicMock()
        handler.is_safe_origin = MagicMock(return_value=True)

        handler._handle_post_internal()
        handler.send_json.assert_called_once()
        status_code, data = handler.send_json.call_args[0]
        self.assertEqual(status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["config"]["network"]["public_fqdn"], "ia.entreprise.com")
        self.assertEqual(data["config"]["kubernetes"]["namespace"], "arcia-custom")
        self.assertEqual(data["config"]["kubernetes"]["remote_ssh"]["node_ip"], "192.168.1.100")
        self.assertEqual(data["config"]["kubernetes"]["remote_ssh"]["ssh_port"], 2222)
        self.assertEqual(data["config"]["llm_gateway"]["openrouter_api_key"], "sk-or-v1-testkey")

    def test_upload_yaml_empty_content_error(self):
        """Vérifie qu'un contenu YAML vide renvoie une erreur 400 explicite."""
        import io
        from unittest.mock import MagicMock

        handler = wizard.WizardHTTPHandler.__new__(wizard.WizardHTTPHandler)
        handler.rfile = io.BytesIO(json.dumps({
            "yaml_content": "   ",
            "filename": "empty.yaml"
        }).encode("utf-8"))
        handler.headers = {"Content-Length": str(len(handler.rfile.getvalue())), "Host": "127.0.0.1:8765"}
        handler.path = "/api/config/upload-yaml"
        handler.send_json = MagicMock()
        handler.is_safe_origin = MagicMock(return_value=True)

        handler._handle_post_internal()
        status_code, data = handler.send_json.call_args[0]
        self.assertEqual(status_code, 400)
        self.assertFalse(data["success"])

    def test_deployment_worker_initial_logs(self):
        """Vérifie que run_deployment_worker initialise immédiatement des logs informatifs."""
        with wizard.deployment_lock:
            wizard.deployment_state["logs"] = []
            wizard.deployment_state["status"] = "idle"

        # Simuler un dry-run avec un mock
        from unittest.mock import patch
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.stdout.readline.side_effect = ["[OK] Test deploy", ""]
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            wizard.run_deployment_worker(dry_run=True, infra_target="k8s_existing")

            with wizard.deployment_lock:
                logs = wizard.deployment_state["logs"]
                self.assertGreater(len(logs), 0)
                # Vérifie que les premiers logs contiennent l'initialisation et la cible
                self.assertTrue(any("Initialisation" in l for l in logs))
                self.assertTrue(any("k8s_existing" in l for l in logs))
                self.assertTrue(any("scripts/deploy.py" in l for l in logs))


if __name__ == "__main__":
    unittest.main()
