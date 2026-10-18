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
        # Les fixtures ne doivent jamais découvrir un cluster privé du poste.
        ssh = patch("deploy.find_harness_ssh", return_value=(None, None))
        ssh.start()
        self.addCleanup(ssh.stop)
        # Les tests généraux ne doivent jamais sauvegarder l'instance privée du poste.
        backup = patch("wizard.backup_current_instance", return_value={"success": True, "state": "synthetic"})
        backup.start()
        self.addCleanup(backup.stop)

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

        # Vérifier que le profil 100 utilisateurs s'intitule PME et n'affiche plus de recommandation
        tier_100 = tiers["100"]
        self.assertEqual(tier_100["title"], "PME")
        self.assertEqual(tier_100["users_label"], "21 à 100 utilisateurs")
        self.assertFalse(tier_100["recommended"])
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
        parsed = deploy.parse_simple_yaml(yaml_text)
        self.assertEqual(parsed["kubernetes"]["remote_ssh"]["ssh_key"], cfg["kubernetes"]["remote_ssh"]["ssh_key"])

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

        with patch("wizard.save_config_to_files"):
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

    def test_homepage_presentation_and_update_center_in_html(self):
        """Vérifie la page d'accueil épurée (3 options dédiées), le chargement YAML contextuel et le tableau sans retour à la ligne."""
        html = wizard.get_wizard_html_page()
        self.assertIn('id="homepagePresentationHero"', html)
        self.assertIn('id="cardNewInstance"', html)
        self.assertIn('id="cardUpdateInstance"', html)
        self.assertIn('id="cardRestoreInstance"', html)
        self.assertIn('id="updateSection"', html)
        self.assertIn('id="restoreSection"', html)
        self.assertIn('id="updateComponentsBody"', html)
        self.assertIn('id="updateProgressBar"', html)
        self.assertIn("checkOnlineUpdates", html)
        self.assertIn("triggerInstanceUpdate", html)
        self.assertIn("returnToHome", html)
        self.assertIn("col-nowrap", html)
        self.assertIn("white-space: nowrap", html)

    def test_check_components_updates_offline_and_manifest_extraction(self):
        """Vérifie l'extraction des versions depuis les manifestes et le tri séquentiel Zero-Downtime."""
        res = wizard.check_components_updates(check_online=False)
        self.assertTrue(res["success"])
        self.assertEqual(len(res["components"]), 7)
        orders = [c["order"] for c in res["components"]]
        self.assertEqual(orders, sorted(orders))
        comp_ids = [c["id"] for c in res["components"]]
        self.assertIn("open-webui", comp_ids)
        self.assertIn("hermes-agent", comp_ids)
        self.assertIn("litellm-proxy", comp_ids)
        self.assertIn("presidio-dlp", comp_ids)
        self.assertIn("oauth2-proxy", comp_ids)

    def test_run_update_worker_dry_run_sequence(self):
        """Vérifie que la séquence de mise à jour Zero-Downtime (Dry-Run) parcourt les 6 phases jusqu'à 100%."""
        wizard.run_update_worker(
            selected_components=["arcia-core", "presidio-dlp", "litellm-proxy", "hermes-agent", "open-webui"],
            bump_image_tags=False,
            dry_run=True,
        )
        with wizard.update_lock:
            self.assertEqual(wizard.update_state["status"], "success")
            self.assertEqual(wizard.update_state["progress_pct"], 100)
            self.assertEqual(len(wizard.update_state["phases"]), 6)
            for phase in wizard.update_state["phases"]:
                self.assertEqual(phase["status"], "done")


    def test_microservices_image_bump_protection(self):
        """Vérifie que les microservices internes ne sont pas marqués comme bumpables et ne sont pas altérés."""
        res = wizard.check_components_updates(check_online=False)
        components_map = {c["id"]: c for c in res["components"]}
        self.assertFalse(components_map["presidio-dlp"]["is_bumpable_image"])
        self.assertFalse(components_map["teams-bot"]["is_bumpable_image"])
        self.assertFalse(components_map["arcia-core"]["is_bumpable_image"])
        self.assertTrue(components_map["litellm-proxy"]["is_bumpable_image"])
        self.assertTrue(components_map["open-webui"]["is_bumpable_image"])

        # Vérifier que update_manifest_image_tag protège formellement les manifests python:3.11-slim
        self.assertIsNone(wizard.update_manifest_image_tag("deploy/manifests/03-presidio.yaml", "2.2.364"))
        self.assertIsNone(wizard.update_manifest_image_tag("deploy/manifests/08-teams-bot.yaml", "4.17.1"))

    def test_repair_corrupted_manifest_images(self):
        """Vérifie que repair_corrupted_manifest_images restaure python:3.11-slim si un tag upstream a été injecté."""
        presidio_path = os.path.join(self.root_dir, "deploy", "manifests", "03-presidio.yaml")
        with open(presidio_path, "r", encoding="utf-8") as f:
            original_content = f.read()

        try:
            # Simuler une corruption par un ancien wizard
            corrupted = original_content.replace("python:3.11-slim", "python:2.2.364")
            with open(presidio_path, "w", encoding="utf-8") as f:
                f.write(corrupted)

            repaired = wizard.repair_corrupted_manifest_images()
            self.assertIn("deploy/manifests/03-presidio.yaml", repaired)

            with open(presidio_path, "r", encoding="utf-8") as f:
                restored = f.read()
            self.assertIn("image: python:3.11-slim", restored)
            self.assertNotIn("python:2.2.364", restored)
        finally:
            with open(presidio_path, "w", encoding="utf-8") as f:
                f.write(original_content)


    def test_scan_production_versions_mocked(self):
        """Vérifie que scan_production_versions extrait fidèlement les versions et images déployées sur K8s."""
        mock_k8s_output = json.dumps({
            "items": [
                {
                    "metadata": {"name": "litellm-proxy"},
                    "spec": {"template": {"spec": {"containers": [{"image": "ghcr.io/berriai/litellm:main-v1.106.0"}]}}},
                    "status": {"replicas": 1, "readyReplicas": 1}
                },
                {
                    "metadata": {"name": "open-webui"},
                    "spec": {"template": {"spec": {"containers": [{"image": "ghcr.io/open-webui/open-webui:v0.12.3"}]}}},
                    "status": {"replicas": 1, "readyReplicas": 1}
                },
                {
                    "metadata": {"name": "oauth2-proxy"},
                    "spec": {"template": {"spec": {"containers": [{"image": "quay.io/oauth2-proxy/oauth2-proxy:v7.15.5"}]}}},
                    "status": {"replicas": 1, "readyReplicas": 1}
                }
            ]
        })

        with patch("deploy.K8sRunner.run") as mock_run:
            mock_run.return_value = (0, mock_k8s_output, "")
            dummy_cfg = {
                "kubernetes": {
                    "mode": "local",
                    "namespace": "arcia"
                }
            }
            prod_versions = wizard.scan_production_versions(dummy_cfg)

            self.assertIn("litellm-proxy", prod_versions)
            self.assertEqual(prod_versions["litellm-proxy"]["version"], "v1.106.0")
            self.assertTrue(prod_versions["litellm-proxy"]["ready"])

            self.assertIn("open-webui", prod_versions)
            self.assertEqual(prod_versions["open-webui"]["version"], "v0.12.3")

            self.assertIn("oauth2-proxy", prod_versions)
            self.assertEqual(prod_versions["oauth2-proxy"]["version"], "v7.15.5")

    def test_check_components_updates_with_prod_scan(self):
        """Vérifie que check_components_updates intègre les versions détectées en production et marque is_prod_live."""
        mock_prod = {
            "litellm-proxy": {
                "version": "v1.106.0",
                "image": "ghcr.io/berriai/litellm:v1.106.0",
                "ready": True,
                "replicas": 1,
                "source": "Cluster K8s (arcia)"
            }
        }
        with patch("wizard.scan_production_versions", return_value=mock_prod):
            res = wizard.check_components_updates(check_online=False, force_prod_scan=True)
            self.assertTrue(res["prod_scanned"])
            litellm_comp = next(c for c in res["components"] if c["id"] == "litellm-proxy")
            self.assertEqual(litellm_comp["current_version"], "v1.106.0")
            self.assertTrue(litellm_comp["is_prod_live"])
            self.assertEqual(litellm_comp["source"], "Cluster K8s (arcia)")

    def test_upload_yaml_returns_live_updates(self):
        """Vérifie que le point d'entrée upload-yaml retourne à la fois la config et le scan de production."""
        sample_yaml = "kubernetes:\n  mode: 'local'\n  namespace: 'arcia'\n"
        import io

        handler = wizard.WizardHTTPHandler.__new__(wizard.WizardHTTPHandler)
        handler.rfile = io.BytesIO(json.dumps({
            "yaml_content": sample_yaml,
            "filename": "arcia.config.yaml"
        }).encode("utf-8"))
        handler.headers = {"Content-Length": str(len(handler.rfile.getvalue())), "Host": "127.0.0.1:8765"}
        handler.path = "/api/config/upload-yaml"
        handler.send_json = MagicMock()
        handler.is_safe_origin = MagicMock(return_value=True)

        with patch("wizard.save_config_to_files"), patch("wizard.check_components_updates") as mock_check:
            mock_check.return_value = {"success": True, "components": [{"id": "arcia-core"}], "updates_available_count": 0}
            handler._handle_post_internal()
            handler.send_json.assert_called_once()
            code, data = handler.send_json.call_args[0]
            self.assertEqual(code, 200)
            self.assertTrue(data["success"])
            self.assertIn("updates", data)
            self.assertEqual(data["updates"]["components"][0]["id"], "arcia-core")

    def test_powerusers_and_models_routing_html(self):
        """Vérifie la présence des sections Power Users et Routage Modèles dans le HTML du Wizard."""
        html = wizard.get_wizard_html_page()
        # Header navigation tabs
        self.assertIn('id="mainHeaderNav"', html)
        self.assertIn('id="navTabPowerUsers"', html)
        self.assertIn('id="navTabModels"', html)
        self.assertIn("switchMainTab", html)

        # Home cards
        self.assertIn('id="cardPowerUsers"', html)
        self.assertIn('id="cardModelsRouting"', html)

        # Sections
        self.assertIn('id="powerUsersSection"', html)
        self.assertIn('id="modelsRoutingSection"', html)

        # Tables
        self.assertIn('id="powerUsersTable"', html)
        self.assertIn('id="modelsRoutingTable"', html)

        # Modals
        self.assertIn('id="modalCreatePowerUser"', html)
        self.assertIn('id="modalResizePvc"', html)
        self.assertIn('id="modalDeletePowerUser"', html)
        self.assertIn('id="modalEditProviderKey"', html)

        # Direction 1 elements (Bento grid, central YAML, compact provider pills, ZDR switch)
        self.assertIn('id="centralYamlTrigger"', html)
        self.assertIn('id="centralYamlFilename"', html)
        self.assertIn('class="bento-summary-grid"', html)
        self.assertIn('class="providers-strip"', html)
        self.assertIn('class="zdr-switch"', html)
        self.assertIn("Sauvegarde et restauration", html)

        # Key JS functions
        self.assertIn("fetchPowerUsers", html)
        self.assertIn("renderPowerUsersTable", html)
        self.assertIn("openResizePvcModal", html)
        self.assertIn("fetchModelRouting", html)
        self.assertIn("renderProvidersGrid", html)
        self.assertIn("openEditProviderModal", html)
        self.assertIn("onZdrToggled", html)
        self.assertIn("saveModelRouting", html)
        self.assertIn("applyModelPreset", html)

    def test_list_powerusers_mocked(self):
        """Vérifie que list_powerusers extrait les Power Users, l'état de leurs pods et le volume PVC."""
        mock_deps_json = json.dumps({
            "items": [
                {
                    "metadata": {
                        "name": "hermes-poweruser-alice",
                        "labels": {
                            "app.kubernetes.io/name": "hermes-poweruser",
                            "app.kubernetes.io/instance": "alice",
                            "arcia.io/role": "poweruser",
                            "arcia.io/user-slug": "alice",
                            "arcia.io/user-name": "Alice Martin",
                            "arcia.io/user-email": "alice@example.com",
                            "arcia.io/user-team": "DevOps"
                        }
                    },
                    "spec": {"replicas": 1},
                    "status": {"replicas": 1, "readyReplicas": 1}
                },
                {
                    "metadata": {
                        "name": "hermes-poweruser-bob",
                        "labels": {
                            "app.kubernetes.io/name": "hermes-poweruser",
                            "app.kubernetes.io/instance": "bob",
                            "arcia.io/role": "poweruser",
                            "arcia.io/user-slug": "bob",
                            "arcia.io/user-name": "Bob Dupont",
                            "arcia.io/user-email": "bob@example.com",
                            "arcia.io/user-team": "Finance"
                        }
                    },
                    "spec": {"replicas": 0},
                    "status": {"replicas": 0}
                }
            ]
        })

        mock_pvcs_json = json.dumps({
            "items": [
                {
                    "metadata": {"name": "hermes-user-alice-pvc"},
                    "spec": {"resources": {"requests": {"storage": "10Gi"}}},
                    "status": {"phase": "Bound", "capacity": {"storage": "10Gi"}}
                },
                {
                    "metadata": {"name": "hermes-user-bob-pvc"},
                    "spec": {"resources": {"requests": {"storage": "20Gi"}}},
                    "status": {"phase": "Bound", "capacity": {"storage": "20Gi"}}
                }
            ]
        })

        mock_pods_json = json.dumps({
            "items": [
                {
                    "metadata": {
                        "name": "hermes-poweruser-alice-7f89d",
                        "labels": {"arcia.io/user-slug": "alice"}
                    },
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [{"name": "hermes-agent", "ready": True, "state": {"running": {}}}]
                    }
                }
            ]
        })

        def mock_k8s_run(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "get deployment" in cmd_str:
                return (0, mock_deps_json, "")
            elif "get pvc" in cmd_str:
                return (0, mock_pvcs_json, "")
            elif "get pod" in cmd_str:
                return (0, mock_pods_json, "")
            elif "exec" in cmd_str:
                return (0, "Filesystem Size Used Avail Use% Mounted\n/dev/sdb 10G 1.5G 8.5G 15% /opt/data\n", "")
            return (0, "", "")

        with patch("deploy.K8sRunner.run", side_effect=mock_k8s_run):
            res = wizard.list_powerusers()
            self.assertEqual(res["status"], "ok")
            users = res["powerusers"]
            self.assertEqual(len(users), 2)

            alice = next(u for u in users if u["slug"] == "alice")
            self.assertEqual(alice["name"], "Alice Martin")
            self.assertEqual(alice["pod_status"], "Running")
            self.assertEqual(alice["pvc_capacity"], "10Gi")
            self.assertEqual(alice["pvc_used_human"], "1.5G")
            self.assertEqual(alice["pvc_percent"], 15.0)

            bob = next(u for u in users if u["slug"] == "bob")
            self.assertEqual(bob["name"], "Bob Dupont")
            self.assertEqual(bob["pod_status"], "Sleeping")
            self.assertEqual(bob["pvc_capacity"], "20Gi")

            stats = res["stats"]
            self.assertEqual(stats["total"], 2)
            self.assertEqual(stats["running"], 1)
            self.assertEqual(stats["sleeping"], 1)
            self.assertEqual(stats["total_storage_gi"], 30)

    def test_poweruser_operations_create_scale_resize_delete(self):
        """Vérifie les opérations unitaires sur un Power User (création, veille, agrandissement PVC, suppression)."""
        calls = []
        def mock_run(cmd, **kwargs):
            calls.append(" ".join(cmd))
            return (0, "", "")

        with patch("deploy.K8sRunner.run", side_effect=mock_run):
            # 1. Création
            res_create = wizard.create_poweruser({
                "name": "Camille Leroy",
                "slug": "camille-leroy",
                "email": "camille@example.com",
                "team": "Data Science",
                "pvc_size": "20Gi"
            })
            self.assertTrue(res_create["success"])
            self.assertTrue(any("apply" in c for c in calls))

            # 2. Mise en veille / réveil (scale)
            calls.clear()
            res_scale = wizard.scale_poweruser("camille-leroy", replicas=0)
            self.assertTrue(res_scale["success"])
            self.assertEqual(res_scale["replicas"], 0)
            self.assertTrue(any("scale deployment/hermes-poweruser-camille-leroy --replicas=0" in c for c in calls))

            # 3. Agrandissement PVC
            calls.clear()
            res_resize = wizard.resize_poweruser_pvc("camille-leroy", new_size="40Gi")
            self.assertTrue(res_resize["success"])
            self.assertEqual(res_resize["new_size"], "40Gi")
            self.assertTrue(any("patch pvc hermes-user-camille-leroy-pvc" in c for c in calls))

            # Test rejet taille invalide
            res_invalid = wizard.resize_poweruser_pvc("camille-leroy", new_size="invalid-size")
            self.assertFalse(res_invalid["success"])

            # 4. Suppression
            calls.clear()
            res_del = wizard.delete_poweruser("camille-leroy", keep_pvc=False)
            self.assertTrue(res_del["success"])
            self.assertTrue(any("delete deployment hermes-poweruser-camille-leroy" in c for c in calls))
            self.assertTrue(any("delete pvc hermes-user-camille-leroy-pvc" in c for c in calls))

    def test_model_routing_config_and_test_provider(self):
        """Vérifie la configuration du routage de modèles, les mappings canoniques et le testeur de clé."""
        cfg = wizard.get_default_config_dict()
        cfg["llm_gateway"]["openrouter_api_key"] = "sk-or-v1-dummykey123456"
        cfg["llm_gateway"]["default_model"] = "simple/auto"

        routing = wizard.get_model_routing_config(cfg)
        self.assertEqual(routing["status"], "ok")
        self.assertEqual(routing["default_model"], "simple/auto")

        # Fournisseurs
        providers = {p["id"]: p for p in routing["providers"]}
        self.assertIn("openrouter", providers)
        self.assertTrue(providers["openrouter"]["configured"])
        self.assertIn("openai", providers)
        self.assertFalse(providers["openai"]["configured"])
        self.assertNotIn("local_vllm", providers)

        # Vérification qu'un serveur local vLLM/Ollama personnalisé s'intègre via custom_providers
        cfg["llm_gateway"]["custom_providers"] = [
            {"id": "custom-vllm", "name": "Mon vLLM Local", "endpoint": "http://192.168.1.50:8000/v1"}
        ]
        routing_custom = wizard.get_model_routing_config(cfg)
        provs_custom = {p["id"]: p for p in routing_custom["providers"]}
        self.assertIn("custom-vllm", provs_custom)
        self.assertTrue(provs_custom["custom-vllm"]["is_custom"])

        # Mappings canoniques
        aliases = [m["alias"] for m in routing["mappings"]]
        self.assertIn("simple/auto", aliases)
        self.assertIn("simple/free", aliases)
        self.assertIn("agentic/auto", aliases)
        self.assertIn("agentic/free", aliases)
        self.assertIn("agentic/expert", aliases)

        # Enregistrement
        mb_path = os.path.join(wizard.ROOT_DIR, "assets", "branding", "models-branding.json")
        orig_mb = None
        if os.path.isfile(mb_path):
            with open(mb_path, "r", encoding="utf-8") as f:
                orig_mb = f.read()

        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".yaml", encoding="utf-8") as tmp:
            tmp_path = tmp.name

        try:
            mock_runner = MagicMock()
            mock_runner.run.return_value = (0, "", "")
            with patch("wizard.DEFAULT_CONFIG_PATH", tmp_path), \
                 patch("wizard.get_k8s_runner", return_value=mock_runner), \
                 patch("wizard.sync_litellm_configmap") as mock_sync:
                mock_sync.return_value = {"success": True}
                save_data = {
                    "providers": {
                        "openrouter_api_key": "sk-or-v1-savedkey",
                        "openai_api_key": "sk-proj-realopenai123456789"
                    },
                    "custom_providers": [
                        {"id": "vllm-local", "name": "vLLM", "endpoint": "http://192.168.1.100:8000/v1"}
                    ],
                    "default_model": "agentic/auto",
                    "mappings": routing["mappings"]
                }
                res_save = wizard.save_model_routing_config(save_data, cfg_path=tmp_path)
                self.assertTrue(res_save["success"])
                mock_sync.assert_called_once()

                # Recharger et vérifier
                loaded = wizard.get_model_routing_config()
                p_loaded = {p["id"]: p for p in loaded["providers"]}
                self.assertTrue(p_loaded["openrouter"]["configured"])
                self.assertTrue(p_loaded["openai"]["configured"])
                self.assertIn("vllm-local", p_loaded)
                self.assertEqual(p_loaded["vllm-local"]["endpoint"], "http://192.168.1.100:8000/v1")
                self.assertEqual(loaded["default_model"], "agentic/auto")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            if orig_mb is not None:
                with open(mb_path, "w", encoding="utf-8") as f:
                    f.write(orig_mb)

        # Test connectivité
        res_test_empty = wizard.test_provider_connectivity("openrouter", "")
        self.assertFalse(res_test_empty["valid"])

        res_test_vllm = wizard.test_provider_connectivity("custom-test", "", endpoint="invalid-url")
        self.assertFalse(res_test_vllm["valid"])

    def test_powerusers_and_models_http_endpoints(self):
        """Vérifie les routes HTTP GET et POST dédiées aux Power Users et au Routage Modèles."""
        import io

        # 1. GET /api/powerusers/list
        h_get_pu = wizard.WizardHTTPHandler.__new__(wizard.WizardHTTPHandler)
        h_get_pu.path = "/api/powerusers/list"
        h_get_pu.send_json = MagicMock()
        h_get_pu.is_safe_origin = MagicMock(return_value=True)
        with patch("wizard.list_powerusers", return_value={"status": "ok", "powerusers": []}):
            h_get_pu.do_GET()
            h_get_pu.send_json.assert_called_once()
            code, data = h_get_pu.send_json.call_args[0]
            self.assertEqual(code, 200)
            self.assertEqual(data["status"], "ok")

        # 2. GET /api/models/routing
        h_get_mod = wizard.WizardHTTPHandler.__new__(wizard.WizardHTTPHandler)
        h_get_mod.path = "/api/models/routing"
        h_get_mod.send_json = MagicMock()
        h_get_mod.is_safe_origin = MagicMock(return_value=True)
        with patch("wizard.get_model_routing_config", return_value={"status": "ok", "providers": []}):
            h_get_mod.do_GET()
            h_get_mod.send_json.assert_called_once()
            code, data = h_get_mod.send_json.call_args[0]
            self.assertEqual(code, 200)
            self.assertEqual(data["status"], "ok")

        # 3. POST /api/powerusers/create
        h_post_pu = wizard.WizardHTTPHandler.__new__(wizard.WizardHTTPHandler)
        pu_data = {"name": "Test User", "slug": "test-user", "email": "test@example.com"}
        h_post_pu.rfile = io.BytesIO(json.dumps(pu_data).encode("utf-8"))
        h_post_pu.headers = {"Content-Length": str(len(h_post_pu.rfile.getvalue())), "Host": "127.0.0.1:8765"}
        h_post_pu.path = "/api/powerusers/create"
        h_post_pu.send_json = MagicMock()
        h_post_pu.is_safe_origin = MagicMock(return_value=True)
        with patch("wizard.create_poweruser", return_value={"success": True, "slug": "test-user"}):
            h_post_pu._handle_post_internal()
            h_post_pu.send_json.assert_called_once()
            code, data = h_post_pu.send_json.call_args[0]
            self.assertEqual(code, 200)
            self.assertTrue(data["success"])

        # 4. POST /api/powerusers/delete avec delete_pvc
        h_post_del = wizard.WizardHTTPHandler.__new__(wizard.WizardHTTPHandler)
        del_data = {"slug": "test-user", "delete_pvc": True}
        h_post_del.rfile = io.BytesIO(json.dumps(del_data).encode("utf-8"))
        h_post_del.headers = {"Content-Length": str(len(h_post_del.rfile.getvalue())), "Host": "127.0.0.1:8765"}
        h_post_del.path = "/api/powerusers/delete"
        h_post_del.send_json = MagicMock()
        h_post_del.is_safe_origin = MagicMock(return_value=True)
        with patch("wizard.delete_poweruser", return_value={"success": True, "slug": "test-user"}) as mock_del:
            h_post_del._handle_post_internal()
            mock_del.assert_called_once_with("test-user", keep_pvc=False)
            h_post_del.send_json.assert_called_once()
            code, data = h_post_del.send_json.call_args[0]
            self.assertEqual(code, 200)
            self.assertTrue(data["success"])

        # 5. POST /api/models/test-provider
        h_post_test = wizard.WizardHTTPHandler.__new__(wizard.WizardHTTPHandler)
        test_data = {"provider": "openrouter", "api_key": "sk-or-v1-xyz"}
        h_post_test.rfile = io.BytesIO(json.dumps(test_data).encode("utf-8"))
        h_post_test.headers = {"Content-Length": str(len(h_post_test.rfile.getvalue())), "Host": "127.0.0.1:8765"}
        h_post_test.path = "/api/models/test-provider"
        h_post_test.send_json = MagicMock()
        h_post_test.is_safe_origin = MagicMock(return_value=True)
        with patch("wizard.test_provider_connectivity", return_value={"status": "ok", "valid": True}):
            h_post_test._handle_post_internal()
            h_post_test.send_json.assert_called_once()
            code, data = h_post_test.send_json.call_args[0]
            self.assertEqual(code, 200)
            self.assertTrue(data["valid"])

    def test_sync_litellm_configmap_with_per_model_zdr(self):
        """Vérifie que la synchronisation du ConfigMap LiteLLM applique l'option ZDR individuellement par modèle."""
        cfg = wizard.get_default_config_dict()
        cfg["llm_gateway"]["models_routing"] = [
            {
                "alias": "simple/auto",
                "real_model": "openrouter/anthropic/claude-3.5-haiku",
                "target_model": "openrouter/anthropic/claude-3.5-haiku",
                "provider": "openrouter",
                "zdr": True,
                "fallback": "openrouter/openai/gpt-4o-mini"
            },
            {
                "alias": "simple/free",
                "real_model": "openrouter/meta-llama/llama-3.3-70b-instruct:free",
                "target_model": "openrouter/meta-llama/llama-3.3-70b-instruct:free",
                "provider": "openrouter",
                "zdr": False,
                "fallback": ""
            }
        ]
        mock_runner = MagicMock()
        mock_runner.run.return_value = (0, "", "")

        res = wizard.sync_litellm_configmap(cfg, mock_runner, "arcia")
        self.assertTrue(res)
        self.assertEqual(mock_runner.run.call_count, 3)
        call_args = mock_runner.run.call_args_list[0][0][0]
        self.assertEqual(call_args, ["apply", "-f", "-"])

        restart_args = mock_runner.run.call_args_list[1][0][0]
        self.assertEqual(restart_args[:3], ["rollout", "restart", "deployment/litellm-proxy"])

        patch_json = json.loads(mock_runner.run.call_args_list[0].kwargs["stdin_input"])
        config_yaml = patch_json["data"]["config.yaml"]

        self.assertIn('model_name: "simple/auto"', config_yaml)
        self.assertIn("zdr: true", config_yaml)

        self.assertIn('model_name: "simple/free"', config_yaml)
        self.assertIn("zdr: false", config_yaml)

    def test_homepage_dual_default_models_and_gauges_in_html(self):
        """Vérifie la présence des 2 modèles par défaut et des jauges de charge sur le dashboard d'accueil."""
        html = wizard.get_wizard_html_page()
        self.assertIn('id="dashDefaultModelSimple"', html)
        self.assertIn('id="dashDefaultModelAgentic"', html)
        self.assertIn('class="resource-gauges-grid"', html)
        self.assertIn('id="gaugeCpuValue"', html)
        self.assertIn('id="gaugeRamValue"', html)
        self.assertIn('id="gaugeStorageValue"', html)
        self.assertIn("setGaugeValue", html)

    def test_check_instance_connectivity_returns_metrics_and_webui_url(self):
        """Vérifie que check_instance_connectivity renvoie l'URL WebUI, les modèles par défaut et les métriques de charge."""
        cfg = {
            "infra_target": "docker_lab",
            "network": {"public_fqdn": "arcia.example.com"},
            "llm_gateway": {"default_model": "simple/auto"},
            "hermes": {"default_model": "agentic/auto"}
        }
        res = wizard.check_instance_connectivity(cfg)
        self.assertIn("webui_url", res)
        self.assertEqual(res["webui_url"], "http://localhost:3000")
        self.assertIn("metrics", res)
        self.assertIn("cpu", res["metrics"])
        self.assertIn("ram", res["metrics"])
        self.assertIn("storage", res["metrics"])
        self.assertEqual(res["default_model_simple"], "simple/auto")
        self.assertEqual(res["default_model_agentic"], "agentic/auto")

    def test_update_center_single_component_update_and_has_update_in_html(self):
        """Vérifie la mise à jour unitaire par composant et la fonction triggerSingleComponentUpdate dans le HTML."""
        html = wizard.get_wizard_html_page()
        self.assertIn("triggerSingleComponentUpdate", html)
        self.assertIn("<th>Action</th>", html)
        self.assertIn("Mettre à jour", html)

    def test_unified_model_routing_block_in_html(self):
        """Vérifie la présence du bloc unifié de routage des modèles montable dans l'installation et en post-déploiement."""
        html = wizard.get_wizard_html_page()
        self.assertIn('id="modelRoutingUnifiedBlock"', html)
        self.assertIn('id="installModelRoutingMount"', html)
        self.assertIn('id="postDeployModelRoutingMount"', html)
        self.assertIn("mountModelRoutingBlock", html)


    def test_loading_screen_and_light_sidebar_in_html(self):
        """Vérifie la présence de l'écran de chargement initial et de la sidebar claire à gauche dans le HTML."""
        html = wizard.get_wizard_html_page()
        # Écran de chargement et étapes
        self.assertIn('id="appLoadingScreen"', html)
        self.assertIn('id="stepLoadConfig"', html)
        self.assertIn('id="stepConnectCluster"', html)
        self.assertIn('id="stepDiscoverComponents"', html)
        self.assertIn('id="stepScanVersions"', html)
        self.assertIn('id="stepInitReady"', html)
        self.assertIn("runInitialLoadingSequence", html)

        # Bandeau latéral clair à gauche
        self.assertIn('class="app-shell"', html)
        self.assertIn('class="app-sidebar"', html)
        self.assertIn('class="app-main-area"', html)
        self.assertIn('class="app-sidebar-nav"', html)
        self.assertIn('class="sidebar-brand-wrap"', html)
        self.assertIn('class="sidebar-yaml-badge"', html)
        self.assertIn('class="sidebar-footer"', html)

    def test_load_arcia_official_versions_from_json(self):
        """Vérifie le chargement du référentiel des versions officielles ArcIA depuis deploy/versions.json."""
        versions = wizard.load_arcia_official_versions(check_online=False)
        self.assertIsInstance(versions, dict)
        self.assertIn("arcia_version", versions)
        self.assertIn("components", versions)
        comps = versions["components"]
        self.assertIn("presidio-dlp", comps)
        self.assertIn("litellm-proxy", comps)
        self.assertIn("hermes-agent", comps)
        self.assertIn("open-webui", comps)

    def test_scale_cluster_resources_scale_out_and_up(self):
        """Vérifie le dimensionnement horizontal (scale-out) et vertical (scale-up)."""
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".yaml", encoding="utf-8") as tmp:
            tmp.write(wizard.serialize_yaml_config(wizard.get_default_config_dict()))
            tmp_path = tmp.name

        try:
            # Test scale-out
            res_out = wizard.scale_cluster_resources({
                "scale_type": "out",
                "nodes": 5
            }, cfg_path=tmp_path)
            self.assertTrue(res_out.get("success"))
            self.assertEqual(res_out["sizing"]["nodes"], 5)

            # Test scale-up
            res_up = wizard.scale_cluster_resources({
                "scale_type": "up",
                "vcpu_per_node": 8,
                "ram_per_node_gb": 32,
                "disk_per_node_gb": 300,
                "rag_storage": "500Gi"
            }, cfg_path=tmp_path)
            self.assertTrue(res_up.get("success"))
            self.assertEqual(res_up["sizing"]["vcpu_per_node"], 8)
            self.assertEqual(res_up["sizing"]["ram_per_node_gb"], 32)
            self.assertEqual(res_up["sizing"]["disk_per_node_gb"], 300)
            self.assertEqual(res_up["sizing"]["rag_storage"], "500Gi")

            # Test palier
            res_tier = wizard.scale_cluster_resources({
                "scale_type": "full",
                "tier": "100"
            }, cfg_path=tmp_path)
            self.assertTrue(res_tier.get("success"))
            self.assertEqual(res_tier["sizing"]["nodes"], 3)
            self.assertEqual(res_tier["sizing"]["vcpu_per_node"], 4)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_scaling_scale_out_scale_up_in_html(self):
        """Vérifie la présence des volets scale-out et scale-up dans le HTML du wizard."""
        html = wizard.get_wizard_html_page()
        self.assertIn("Scale-out (dimensionnement horizontal)", html)
        self.assertIn("Scale-up (dimensionnement vertical)", html)
        self.assertIn("applyClusterScaling('out')", html)
        self.assertIn("applyClusterScaling('up')", html)
        self.assertIn("applyClusterScaling('full')", html)
        self.assertIn("loadClusterSizing", html)

    def test_get_provider_models_catalog(self):
        """Vérifie la récupération dynamique ou de secours des modèles par fournisseur."""
        models_or = wizard.get_provider_models_catalog("openrouter")
        self.assertIsInstance(models_or, list)
        self.assertGreater(len(models_or), 0)
        self.assertTrue(any("openrouter/" in m["id"] for m in models_or))

        models_oa = wizard.get_provider_models_catalog("openai")
        self.assertIsInstance(models_oa, list)
        self.assertTrue(any("openai/" in m["id"] for m in models_oa))

    def test_sidebar_nowrap_and_pme_tier_in_html(self):
        """Vérifie l'absence de retour à la ligne sur les boutons du menu et l'intitulé PME sans recommandation."""
        html = wizard.get_wizard_html_page()
        # Non-retour à la ligne dans la sidebar
        self.assertIn("white-space: nowrap;", html)
        self.assertIn("Dimensionnement cluster", html)

        # Palier PME avec nombre d'utilisateurs et sans badge Recommandé
        self.assertIn("PME", html)
        self.assertIn("21 à 100", html)
        self.assertNotIn("PME / Direction métier", html)

    def test_generate_ssh_key_pair(self):
        """Vérifie la fonction de génération de clés SSH Ed25519/RSA."""
        res = wizard.generate_ssh_key_pair("test-arcia-key")
        self.assertIsInstance(res, dict)
        if res.get("success"):
            self.assertTrue(os.path.isfile(res["key_path"]))
            self.assertIn("public_key", res)
            self.assertIn("private_key", res)
            # Nettoyage
            try:
                os.remove(res["key_path"])
                if os.path.isfile(res["key_path"] + ".pub"):
                    os.remove(res["key_path"] + ".pub")
            except Exception:
                pass
        else:
            self.assertIn("error", res)

    def test_vmware_network_and_ssh_in_html(self):
        """Vérifie la présence des champs réseau VMware et authentification VM dans l'interface."""
        html = wizard.get_wizard_html_page()
        # Configuration réseau
        self.assertIn("vmware_ip_mode", html)
        self.assertIn("vmware_node_ips", html)
        self.assertIn("vmware_gateway", html)
        self.assertIn("vmware_netmask", html)
        self.assertIn("vmware_dns", html)
        self.assertIn("vmware_ntp", html)
        self.assertIn("vmware_domain", html)
        # Authentification VMs
        self.assertIn("vmware_vm_user", html)
        self.assertIn("vmware_vm_password", html)
        self.assertIn("vmware_root_password", html)
        self.assertIn("vmware_ssh_key_mode", html)
        self.assertIn("generateVmwareSshKey", html)
        self.assertIn("downloadPrivateKeyFile", html)

    def test_deploy_credentials_recap_in_html(self):
        """Vérifie la présence de la carte récapitulative des identifiants et des fonctions de téléchargement."""
        html = wizard.get_wizard_html_page()
        self.assertIn("deployCredentialsRecapCard", html)
        self.assertIn("credentialsRecapContent", html)
        self.assertIn("renderDeploymentCredentials", html)
        self.assertIn("copyAllCredentialsToClipboard", html)
        self.assertIn("downloadCredentialsSummaryFile", html)
        self.assertIn("generateCredentialsText", html)
        self.assertIn("arcia-credentials.txt", html)

    def test_detect_fallback_loops(self):
        """Vérifie la détection rigoureuse des cycles et boucles infinies de repli."""
        no_loop = [{"alias": "simple/auto", "fallback": "simple/free"}, {"alias": "simple/free", "fallback": ""}]
        self.assertIsNone(wizard.detect_fallback_loops(no_loop))

        direct_loop = [{"alias": "A", "fallback": "B"}, {"alias": "B", "fallback": "A"}]
        self.assertEqual(wizard.detect_fallback_loops(direct_loop), "A -> B -> A")

        transitive_loop = [{"alias": "A", "fallback": "B"}, {"alias": "B", "fallback": "C"}, {"alias": "C", "fallback": "A"}]
        self.assertEqual(wizard.detect_fallback_loops(transitive_loop), "A -> B -> C -> A")

    def test_vmware_config_serialization_and_reload(self):
        """Vérifie que la configuration VMware est fidèlement sérialisée et rechargée pour le scale-up/scale-out."""
        cfg = wizard.get_default_config_dict()
        cfg["vmware"] = {
            "host": "vcenter.arcia.internal",
            "port": 443,
            "username": "administrator@vsphere.local",
            "insecure_tls": False,
            "datacenter": "Datacenter-ArcIA",
            "cluster": "Cluster-Production",
            "datastore": "datastore-purestorage-nvme",
            "portgroup": "DVS-VLAN-150",
            "tier": "250",
            "network": {
                "mode": "static",
                "node_ips": "10.10.150.11,10.10.150.12,10.10.150.13",
                "netmask": "255.255.255.0",
                "gateway": "10.10.150.1",
                "dns": "10.10.150.254",
                "ntp": "10.10.150.253",
                "domain": "arcia.internal"
            },
            "auth": {
                "vm_user": "debian",
                "ssh_key_mode": "generate",
                "ssh_public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGeneratedTestKey"
            },
            "resources_override": {
                "nodes": 3,
                "vcpu_per_node": 8,
                "ram_per_node_gb": 32,
                "disk_per_node_gb": 300
            }
        }
        yaml_str = wizard.serialize_yaml_config(cfg)
        self.assertIn("vcenter.arcia.internal", yaml_str)
        self.assertIn("10.10.150.1", yaml_str)
        self.assertIn("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGeneratedTestKey", yaml_str)

        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".yaml", encoding="utf-8") as tmp:
            tmp.write(yaml_str)
            tmp_path = tmp.name

        try:
            reloaded, exists = wizard.load_config_data(tmp_path)
            self.assertTrue(exists)
            self.assertEqual(reloaded.get("vmware", {}).get("host"), "vcenter.arcia.internal")
            self.assertEqual(reloaded.get("vmware", {}).get("network", {}).get("gateway"), "10.10.150.1")
            self.assertEqual(reloaded.get("vmware", {}).get("resources_override", {}).get("vcpu_per_node"), 8)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_vmware_ssh_key_generation_native(self):
        """Vérifie la génération autonome d'une paire de clés SSH Ed25519 OpenSSH."""
        with tempfile.TemporaryDirectory() as directory, patch("wizard.os.path.expanduser", return_value=directory):
            res = wizard.generate_ssh_key_pair("test_ed25519_unit")
        self.assertTrue(res.get("success"), res.get("error"))
        self.assertTrue(res.get("public_key", "").startswith("ssh-ed25519 "))
        self.assertIn("BEGIN OPENSSH PRIVATE KEY", res.get("private_key", ""))

    def test_toggle_password_visibility_in_html(self):
        """Vérifie que la fonction togglePasswordVisibility est définie dans le script JS."""
        html = wizard.get_wizard_html_page()
        self.assertIn("function togglePasswordVisibility(fieldId)", html)

    def test_model_routing_includes_icon_metadata(self):
        """Vérifie que get_model_routing_config enrichit chaque modèle avec les icônes ArcIA."""
        cfg = {
            "llm_gateway": {
                "models_routing": [
                    {"name": "local-vllm", "provider": "vllm", "target_model": "vllm/qwen", "zdr": False},
                    {"name": "cloud-haiku", "provider": "openrouter", "target_model": "openrouter/anthropic/claude-3.5-haiku", "zdr": True},
                    {"name": "plain-gpt", "provider": "openai", "target_model": "openai/gpt-4o", "zdr": False}
                ]
            }
        }
        res = wizard.get_model_routing_config(cfg)
        mappings = res.get("mappings", [])
        self.assertEqual(len(mappings), 3)

        local_m = next(m for m in mappings if m["name"] == "local-vllm")
        self.assertEqual(local_m["icon_type"], "local")
        self.assertEqual(local_m["icon"], "/static/icon-model-local.svg")

        cloud_m = next(m for m in mappings if m["name"] == "cloud-haiku")
        self.assertEqual(cloud_m["icon_type"], "zdr")
        self.assertEqual(cloud_m["icon"], "/static/icon-model-zdr.svg")

        plain_m = next(m for m in mappings if m["name"] == "plain-gpt")
        self.assertEqual(plain_m["icon_type"], "default")
        self.assertEqual(plain_m["icon"], "/static/icon-model-default.svg")

    def test_save_model_routing_keeps_instance_mapping_out_of_public_assets(self):
        """Une sauvegarde privée ne doit pas publier les identifiants dans les assets du harness."""
        mb_path = os.path.join(wizard.ROOT_DIR, "assets", "branding", "models-branding.json")
        orig_mb = None
        if os.path.isfile(mb_path):
            with open(mb_path, "r", encoding="utf-8") as f:
                orig_mb = f.read()

        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".yaml", encoding="utf-8") as tmp:
            tmp.write("llm_gateway:\n  default_model: simple/auto\n")
            tmp_path = tmp.name

        try:
            payload = {
                "default_model": "simple/auto",
                "mappings": [
                    {"name": "simple/auto", "alias": "simple/auto", "provider": "openrouter", "target_model": "openrouter/auto", "zdr": True},
                    {"name": "local/model", "alias": "local/model", "provider": "ollama", "target_model": "ollama/llama3", "zdr": False}
                ]
            }
            with patch("wizard.get_k8s_runner") as get_runner:
                get_runner.return_value.run.return_value = (1, "", "synthetic offline")
                res = wizard.save_model_routing_config(payload, cfg_path=tmp_path)
            self.assertTrue(res.get("success"))
            self.assertTrue(os.path.isfile(mb_path))
            with open(mb_path, "r", encoding="utf-8") as f:
                branding = json.load(f)
            self.assertEqual(json.dumps(branding, sort_keys=True), json.dumps(json.loads(orig_mb), sort_keys=True))
            projection = deploy.compute_models_branding_dict(cfg=deploy.parse_yaml_or_env(tmp_path))
            self.assertEqual(set(projection["models"]), {"simple/auto", "local/model"})
            self.assertEqual(projection["models"]["simple/auto"]["type"], "zdr")
            self.assertEqual(projection["models"]["local/model"]["type"], "local")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            if orig_mb is not None:
                with open(mb_path, "w", encoding="utf-8") as f:
                    f.write(orig_mb)


    def test_step_containers_are_siblings_and_not_nested(self):
        """Vérifie que les 4 conteneurs d'étapes (stepContainer1..4) sont des frères directs dans installSection."""
        from html.parser import HTMLParser
        VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

        class StepHierarchyValidator(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []
                self.step_ancestors = {}

            def handle_starttag(self, tag, attrs):
                if tag in VOID_TAGS:
                    return
                attrs_dict = dict(attrs)
                el_id = attrs_dict.get("id", "")
                if el_id and el_id.startswith("stepContainer"):
                    self.step_ancestors[el_id] = [p[1] for p in self.stack if p[1]]
                self.stack.append((tag, el_id))

            def handle_endtag(self, tag):
                if tag in VOID_TAGS:
                    return
                if self.stack:
                    self.stack.pop()

        html = wizard.get_wizard_html_page()
        validator = StepHierarchyValidator()
        validator.feed(html)

        for step_num in range(1, 5):
            s_id = f"stepContainer{step_num}"
            self.assertIn(s_id, validator.step_ancestors, f"{s_id} doit être présent dans le DOM")
            ancestors = validator.step_ancestors[s_id]
            self.assertIn("installSection", ancestors, f"{s_id} doit être dans installSection")
            for other_num in range(1, 5):
                if other_num != step_num:
                    self.assertNotIn(f"stepContainer{other_num}", ancestors, f"{s_id} ne doit pas être imbriqué dans stepContainer{other_num}")

    def test_instance_menus_conditional_visibility(self):
        """Vérifie que les menus de configuration d'instance sont masqués par défaut et conditionnés."""
        html = wizard.get_wizard_html_page()
        self.assertIn("updateNavigationVisibility", html)
        self.assertIn('id="navTabModels" class="nav-btn hidden"', html)
        self.assertIn('id="navTabPowerUsers" class="nav-btn hidden"', html)
        self.assertIn('id="navTabIntegrations" class="nav-btn hidden"', html)
        self.assertIn('id="navTabScaling" class="nav-btn hidden"', html)
        self.assertIn('id="navTabUpdates" class="nav-btn hidden"', html)
        self.assertIn('id="btnSidebarNewInstance" class="btn secondary compact hidden"', html)
        # Accueil et Sauvegarde & reprise ne doivent pas être masqués
        self.assertIn('id="navTabHome" class="nav-btn active"', html)
        self.assertIn('id="navTabRestore" class="nav-btn"', html)

    def test_strip_ansi_codes_and_preservation(self):
        """Vérifie le nettoyage des codes ANSI standards et orphelins tout en préservant les balises de log."""
        raw_text_1 = "\x1b[1m\x1b[96m=================================================================\x1b[0m"
        self.assertEqual(wizard.strip_ansi_codes(raw_text_1), "=================================================================")

        raw_text_2 = " [1m [96m[1/7] [0m  [1mVérification de la connectivité au cluster Kubernetes [0m"
        cleaned_2 = wizard.strip_ansi_codes(raw_text_2).strip()
        self.assertEqual(cleaned_2, "[1/7]   Vérification de la connectivité au cluster Kubernetes")

        raw_text_3 = " [92m[OK] [0m Cluster connecté avec succès."
        self.assertEqual(wizard.strip_ansi_codes(raw_text_3).strip(), "[OK]  Cluster connecté avec succès.")

        raw_text_4 = " [93m[WARN] [0m Le déploiement met du temps à démarrer."
        self.assertEqual(wizard.strip_ansi_codes(raw_text_4).strip(), "[WARN]  Le déploiement met du temps à démarrer.")

    def test_cancel_active_deployment_idle_and_running(self):
        """Vérifie l'annulation d'un déploiement : refus si inactif, et interruption propre si en cours."""
        with wizard.deployment_lock:
            wizard.deployment_state["status"] = "idle"
            wizard.active_deployment_proc = None

        res_idle = wizard.cancel_active_deployment()
        self.assertFalse(res_idle["success"])
        self.assertIn("Aucun déploiement", res_idle["error"])

        mock_proc = MagicMock()
        mock_proc.terminate = MagicMock()
        mock_proc.wait = MagicMock()
        with wizard.deployment_lock:
            wizard.deployment_state["status"] = "running"
            wizard.deployment_state["logs"] = ["[INFO] Initialisation..."]
            wizard.active_deployment_proc = mock_proc

        res_running = wizard.cancel_active_deployment()
        self.assertTrue(res_running["success"])
        mock_proc.terminate.assert_called_once()
        with wizard.deployment_lock:
            self.assertEqual(wizard.deployment_state["status"], "canceled")
            self.assertIsNone(wizard.active_deployment_proc)
            self.assertTrue(any("interrompu" in log for log in wizard.deployment_state["logs"]))

    def test_run_deployment_worker_k8s_existing_vm_cfg_scope(self):
        """Vérifie que run_deployment_worker lie vm_cfg et construit le récapitulatif sans crash sous k8s_existing."""
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "[INFO] Lecture du fichier de configuration : arcia.config.yaml\n",
            "[OK] Validation de la configuration\n",
            ""
        ]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0

        with patch("subprocess.Popen", return_value=mock_proc):
            wizard.run_deployment_worker(dry_run=True, infra_target="k8s_existing")

        with wizard.deployment_lock:
            self.assertEqual(wizard.deployment_state["status"], "success")
            self.assertIn("summary", wizard.deployment_state)
            summary = wizard.deployment_state["summary"]
            self.assertIn("webui_url", summary)
            self.assertIn("hermes_admin_pass", summary)

    def test_wizard_ui_full_page_deployment_and_credentials_view(self):
        """Vérifie la présence du mode déploiement plein écran, du bouton d'annulation et du résumé des accès."""
        html = wizard.get_wizard_html_page()
        self.assertIn(".app-shell.deploy-mode aside.app-sidebar", html)
        self.assertIn(".app-shell.deploy-mode .app-main-area", html)
        self.assertIn('id="btnCancelDeploy"', html)
        self.assertIn("cancelDeployment", html)
        self.assertIn('id="deployLogsDetails"', html)
        self.assertIn('id="credentialsRecapContent"', html)
        self.assertIn("credentials-grid", html)
        self.assertIn("Liseret doré", html)
        self.assertIn("Liseret argenté", html)

    def test_get_integrations_status_mocked(self):
        """Vérifie la détection d'état de connexion de Entra ID et Teams Bot."""
        cfg = {
            "entra_id_sso": {
                "enabled": True,
                "tenant_id": "azure-tenant-123",
                "client_id": "azure-client-456"
            },
            "teams_bot": {
                "enabled": True,
                "app_id": "teams-app-789",
                "app_password": "secret-password"
            },
            "kubernetes": {"namespace": "arcia"}
        }

        mock_deployments = json.dumps({
            "items": [
                {
                    "metadata": {"name": "oauth2-proxy"},
                    "status": {"readyReplicas": 2}
                },
                {
                    "metadata": {"name": "teams-bot-adapter"},
                    "status": {"readyReplicas": 1}
                }
            ]
        })

        runner_mock = MagicMock()
        runner_mock.run.return_value = (0, mock_deployments, "")

        with patch("wizard.get_k8s_runner", return_value=runner_mock):
            res = wizard.get_integrations_status(cfg)

        self.assertTrue(res["success"])
        self.assertTrue(res["sso"]["enabled"])
        self.assertEqual(res["sso"]["status"], "connected")
        self.assertEqual(res["sso"]["ready_replicas"], 2)
        self.assertEqual(res["sso"]["tenant_id"], "azure-tenant-123")

        self.assertTrue(res["teams"]["enabled"])
        self.assertEqual(res["teams"]["status"], "connected")
        self.assertEqual(res["teams"]["ready_replicas"], 1)
        self.assertEqual(res["teams"]["app_id"], "teams-app-789")

    def test_get_instance_backup_timeline_mocked(self):
        """Vérifie l'analyse de l'historique Git et la construction de la frise chronologique."""
        mock_log = (
            "a1b2c3d4e5f6g7h8|2026-10-18 20:30:00 +0200|chore(instance): sauvegarde chiffrée\n"
            "b2c3d4e5f6g7h8i9|2026-10-18 19:15:00 +0200|chore(instance): déploiement initial\n"
        )

        with patch("subprocess.run") as mock_run:
            # premier appel clone ok, second log ok
            mock_proc_clone = MagicMock(returncode=0)
            mock_proc_log = MagicMock(returncode=0, stdout=mock_log)
            mock_run.side_effect = [mock_proc_clone, mock_proc_log]

            res = wizard.get_instance_backup_timeline("https://github.com/myorg/arcia-backup.git", "pat123")

        self.assertTrue(res["success"])
        self.assertEqual(len(res["timeline"]), 2)
        self.assertEqual(res["timeline"][0]["short_hash"], "a1b2c3d")
        self.assertEqual(res["timeline"][0]["datetime"], "2026-10-18 20:30:00 +0200")
        self.assertEqual(res["last_backup"], "2026-10-18 20:30:00 +0200")

    def test_wizard_ui_integrations_and_backup_timeline_elements(self):
        """Vérifie la présence des bandeaux de statut en direct, de la timeline et des champs ACME dans l'UI."""
        html = wizard.get_wizard_html_page()
        # Éléments SSO et Teams
        self.assertIn('id="post_entra_status_banner"', html)
        self.assertIn('id="post_entra_status_dot"', html)
        self.assertIn('id="post_teams_status_banner"', html)
        self.assertIn("fetchIntegrationsStatus", html)

        # Éléments Sauvegarde et Reprise
        self.assertIn('id="backup_current_repo_badge"', html)
        self.assertIn('id="backup_current_repo_text"', html)
        self.assertIn('id="backupTimelineTableBody"', html)
        self.assertIn("fetchBackupInfo", html)
        self.assertIn("backupCurrentInstanceNow", html)
        self.assertIn("restorePointInTime", html)

        # Champs DNS ACME
        self.assertIn('id="network_acme_dns_txt"', html)
        self.assertIn('id="network_acme_account_key"', html)


if __name__ == "__main__":
    unittest.main()




