#!/usr/bin/env python3
"""
Test de non-régression et qualification du bouclier DLP ArcIA (Presidio Sanitizer Durci).
Vérifie les 4 couches de confidentialité :
  - Couche 1 : Filtre déterministe pré-NLP (Secrets bruts fail-closed HTTP 422, Kubeconfig, Infra, CIDR, MAC, FQDN).
  - Couche 2 : NER Multi-lingue, PII françaises (FR_NIR, FR_SIRET) et Deny-Lists dynamiques d'instance.
  - Couche 3 : Pseudonymisation cohérente et réversible (Vault éphémère in-memory, buffer streaming).
  - Couche 4 : Verrouillage ZDR côté serveur LiteLLM Proxy / OpenRouter.
"""

import unittest
import sys
import os
import json

# Ajout du chemin des services pour importer le module app
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "presidio"))
try:
    from app import (
        sanitize, deanonymize, analyze, anonymize,
        SanitizeRequest, DeanonymizeRequest, AnalyzeRequest, AnonymizeRequest,
        DeanonymizingStreamBuffer, HTTPException,
        IP_PATTERN, SECRET_PATTERNS, EMAIL_PATTERN, PHONE_PATTERN
    )
    APP_AVAILABLE = True
except ImportError:
    APP_AVAILABLE = False


class TestArcIADLP(unittest.TestCase):

    def setUp(self):
        if not APP_AVAILABLE:
            self.skipTest("Module services/presidio/app.py introuvable")

    # =========================================================================
    # Tests Historiques & Base PII (Adaptés aux tokens typés v0.4)
    # =========================================================================

    def test_ip_address_redaction(self):
        """Vérifie que les adresses IP (v4) sont pseudonymisées avec jetons cohérents [IPV4_XX]."""
        prompt = "Connexion au serveur Postgres sur 192.168.1.45 et passerelle 10.0.0.1 requise."
        res = sanitize(SanitizeRequest(text=prompt, language="fr"))
        self.assertNotIn("192.168.1.45", res["sanitized_text"])
        self.assertNotIn("10.0.0.1", res["sanitized_text"])
        self.assertIn("[IPV4_", res["sanitized_text"])
        self.assertIn("IP_ADDRESS", res["entities_detected"])

    def test_secrets_redaction(self):
        """Vérifie le caviardage des mots de passe, tokens Bearer, clés OpenAI et GitHub."""
        secrets_tests = [
            ("mot de passe admin: password=SuperSecretP@ssw0rd! ici", "SuperSecretP@ssw0rd!"),
            ("export OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz0123456789", "sk-abcdefghijklmnopqrstuvwxyz0123456789"),
            ("curl -H 'Authorization: Bearer my-super-secret-bearer-token-123456'", "my-super-secret-bearer-token-123456"),
            ("git clone avec token ghp_123456789012345678901234567890123456", "ghp_123456789012345678901234567890123456")
        ]
        for prompt, secret_val in secrets_tests:
            res = sanitize(SanitizeRequest(text=prompt, language="fr"))
            self.assertNotIn(secret_val, res["sanitized_text"])
            self.assertIn("[SECRET_REMOVED]", res["sanitized_text"])
            self.assertIn("SECRET", res["entities_detected"])

    def test_email_and_iban_redaction(self):
        """Vérifie le caviardage des emails professionnels et des IBANs."""
        prompt = "Virement pour jean.dupont@entreprise.com sur le compte FR7630006000011234567890189."
        res = sanitize(SanitizeRequest(text=prompt, language="fr"))
        self.assertNotIn("jean.dupont@entreprise.com", res["sanitized_text"])
        self.assertNotIn("FR7630006000011234567890189", res["sanitized_text"])
        self.assertIn("[EMAIL_", res["sanitized_text"])
        self.assertIn("[IBAN_", res["sanitized_text"])

    def test_phone_number_redaction(self):
        """Vérifie le caviardage des numéros de téléphone."""
        prompt = "Contactez le support au 06 12 34 56 78 ou au +33145678910."
        res = sanitize(SanitizeRequest(text=prompt, language="fr"))
        self.assertNotIn("06 12 34 56 78", res["sanitized_text"])
        self.assertNotIn("+33145678910", res["sanitized_text"])
        self.assertIn("[PHONE_", res["sanitized_text"])

    def test_clean_text_unchanged(self):
        """Vérifie qu'un prompt sans donnée sensible reste intact."""
        clean_prompt = "Explique-moi les différences fondamentales entre Kubernetes K3s et EKS."
        res = sanitize(SanitizeRequest(text=clean_prompt, language="fr"))
        self.assertEqual(res["sanitized_text"], clean_prompt)
        self.assertEqual(len(res["entities_detected"]), 0)

    def test_company_and_location_preserved(self):
        """Vérifie que les noms d'organisations et lieux publics (ex: DINUM, Lyon) ne sont PAS caviardés."""
        prompt = "Donne-moi le SIRET de l'entité DINUM à Lyon ou à Paris."
        res = sanitize(SanitizeRequest(text=prompt, language="fr"))
        self.assertIn("DINUM", res["sanitized_text"])
        self.assertNotIn("[LOC_", res["sanitized_text"])
        self.assertNotIn("[ORG_", res["sanitized_text"])

    def test_urls_and_python_scripts_preserved(self):
        """Vérifie que les URLs et scripts Python (ex: public_apis.py) ne sont jamais caviardés en faux token."""
        prompt = "Exécute le script /opt/data/skills/public-apis/scripts/public_apis.py pour interroger https://recherche-entreprises.api.gouv.fr."
        res = sanitize(SanitizeRequest(text=prompt, language="fr"))
        self.assertIn("public_apis.py", res["sanitized_text"])
        self.assertIn("https://recherche-entreprises.api.gouv.fr", res["sanitized_text"])

    def test_presidio_mocked_url_entity_ignored(self):
        """Vérifie que si Presidio Analyzer détecte une entité URL (ex: apis.py car .py est TLD), elle est ignorée."""
        from unittest.mock import patch, MagicMock
        class FakeRecognizerResult:
            def __init__(self, entity_type, start, end, score=0.9):
                self.entity_type = entity_type
                self.start = start
                self.end = end
                self.score = score

        mock_analyzer = MagicMock()
        text = "python /opt/data/skills/public-apis/scripts/public_apis.py company"
        mock_analyzer.analyze.return_value = [
            FakeRecognizerResult(entity_type="URL", start=44, end=51)
        ]

        with patch("app.get_analyzer", return_value=mock_analyzer):
            res = sanitize(SanitizeRequest(text=text, language="fr"))
            self.assertIn("public_apis.py", res["sanitized_text"])
            self.assertNotIn("URL", res["entities_detected"])

    # =========================================================================
    # Couche 1 : Filtre Déterministe Pré-NLP & Fail-Closed 422
    # =========================================================================

    def test_couche1_pem_key_dump_rejected_fail_closed(self):
        """Vérifie le rejet immédiat (HTTP 422) d'une clé privée PEM brute."""
        raw_key = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA0Y1+abcdefghijklmnopqrstuvwxyz1234567890\n"
            "-----END RSA PRIVATE KEY-----"
        )
        with self.assertRaises(HTTPException) as ctx:
            sanitize(SanitizeRequest(text=f"Analyse cette clé:\n{raw_key}"))
        self.assertEqual(ctx.exception.status_code, 422)
        detail = ctx.exception.detail
        self.assertEqual(detail.get("error"), "FAIL_CLOSED_SECRET_REJECTED")
        self.assertEqual(detail.get("reason"), "PEM_PRIVATE_KEY_DETECTED")

    def test_couche1_kubeconfig_dump_rejected_fail_closed(self):
        """Vérifie le rejet immédiat (HTTP 422) d'une extraction brute de kubeconfig."""
        kubeconfig_payload = (
            "apiVersion: v1\n"
            "clusters:\n"
            "- cluster:\n"
            "    server: https://10.24.1.1:6443\n"
            "    certificate-authority-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCg==\n"
            "  name: k3s-cluster\n"
            "contexts:\n"
            "- context:\n"
            "    cluster: k3s-cluster\n"
            "    user: admin\n"
            "  name: default\n"
            "current-context: default\n"
        )
        with self.assertRaises(HTTPException) as ctx:
            sanitize(SanitizeRequest(text=f"Mon fichier ~/.kube/config :\n{kubeconfig_payload}"))
        self.assertEqual(ctx.exception.status_code, 422)
        detail = ctx.exception.detail
        self.assertEqual(detail.get("error"), "FAIL_CLOSED_SECRET_REJECTED")
        self.assertEqual(detail.get("reason"), "KUBECONFIG_DUMP_DETECTED")

    def test_couche1_infrastructure_detection(self):
        """Vérifie la détection et pseudonymisation d'éléments d'infra (CIDR, MAC, Hostnames internes, chemins)."""
        prompt = (
            "Vérifier le sous-réseau 10.240.0.0/16 sur l'équipement MAC 00:1A:2B:3C:4D:5E. "
            "Le nœud maître srv-k3s-master01.corp et la passerelle gw-core.internal accèdent à /etc/shadow."
        )
        res = sanitize(SanitizeRequest(text=prompt, language="fr"))
        sanitized = res["sanitized_text"]
        self.assertNotIn("10.240.0.0/16", sanitized)
        self.assertNotIn("00:1A:2B:3C:4D:5E", sanitized)
        self.assertNotIn("srv-k3s-master01.corp", sanitized)
        self.assertNotIn("gw-core.internal", sanitized)
        self.assertNotIn("/etc/shadow", sanitized)
        self.assertIn("[CIDR_01]", sanitized)
        self.assertIn("[MAC_01]", sanitized)
        self.assertIn("[HOST_01]", sanitized)
        self.assertIn("[HOST_02]", sanitized)
        self.assertIn("[PATH_01]", sanitized)

    # =========================================================================
    # Couche 2 : PII Françaises & Deny-Lists Dynamiques
    # =========================================================================

    def test_couche2_french_nir_and_siret(self):
        """Vérifie la détection du numéro de sécurité sociale (NIR) et SIRET français."""
        # NIR valide avec clé (1 85 12 75 108 123 95 -> 1851275108123 % 97 = 2 -> 97 - 2 = 95)
        prompt = "Dossier patient NIR 1 85 12 75 108 123 95 pour l'établissement SIRET 73282932000074."
        res = sanitize(SanitizeRequest(text=prompt, language="fr"))
        sanitized = res["sanitized_text"]
        self.assertNotIn("1 85 12 75 108 123 95", sanitized)
        self.assertNotIn("73282932000074", sanitized)
        self.assertIn("[NIR_01]", sanitized)
        self.assertIn("[SIRET_01]", sanitized)
        self.assertIn("FR_NIR", res["entities_detected"])
        self.assertIn("FR_SIRET", res["entities_detected"])

    def test_couche2_dynamic_instance_deny_list(self):
        """Vérifie le chargement et l'application dynamique des listes d'interdiction d'instance."""
        synthetic_deny_list = {
            "entities": {
                "CLIENT_PROJECT": ["ProjectZeus", "ProjetPegase"],
                "INTERNAL_HOSTNAME": ["vm-esxi-prod01"],
                "FORBIDDEN_TERMS": ["ConfidentielDefense"]
            }
        }
        os.environ["ARCIA_DENY_LIST"] = json.dumps(synthetic_deny_list)
        try:
            prompt = "Le livrable de ProjectZeus sur la machine vm-esxi-prod01 est classé ConfidentielDefense."
            res = sanitize(SanitizeRequest(text=prompt, language="fr"))
            sanitized = res["sanitized_text"]
            self.assertNotIn("ProjectZeus", sanitized)
            self.assertNotIn("vm-esxi-prod01", sanitized)
            self.assertNotIn("ConfidentielDefense", sanitized)
            self.assertIn("[PROJECT_01]", sanitized)
            self.assertIn("[HOST_01]", sanitized)
            self.assertIn("[DENIED_01]", sanitized)
        finally:
            os.environ.pop("ARCIA_DENY_LIST", None)

    # =========================================================================
    # Couche 3 : Pseudonymisation Cohérente & Réversible (Stateful Vault)
    # =========================================================================

    def test_couche3_consistent_pseudonymization_per_session(self):
        """Vérifie que la même valeur répétée reçoit exactement le même jeton."""
        session_id = "test-session-consistent-01"
        prompt = "L'hôte 10.24.12.5 contacte 10.24.12.6, puis 10.24.12.5 confirme le paquet."
        res = sanitize(SanitizeRequest(text=prompt, session_id=session_id))
        sanitized = res["sanitized_text"]
        self.assertIn("[IPV4_01]", sanitized)
        self.assertIn("[IPV4_02]", sanitized)
        # 10.24.12.5 doit apparaître deux fois sous le même jeton [IPV4_01]
        self.assertEqual(sanitized.count("[IPV4_01]"), 2)
        self.assertEqual(sanitized.count("[IPV4_02]"), 1)

    def test_couche3_reversible_roundtrip_deanonymization(self):
        """Vérifie la ré-hydratation intégrale aller-retour via le Vault éphémère."""
        session_id = "test-session-roundtrip-01"
        original_prompt = "Contactez support@domain.corp pour la VM 192.168.10.20."
        res_sanitize = sanitize(SanitizeRequest(text=original_prompt, session_id=session_id))
        sanitized = res_sanitize["sanitized_text"]

        # Simulation de la réponse LLM reprenant les jetons
        llm_response = f"Bien reçu. Le serveur {sanitized} a été redémarré avec succès."

        res_deanonymize = deanonymize(DeanonymizeRequest(text=llm_response, session_id=session_id))
        restored = res_deanonymize["text"]
        self.assertIn("support@domain.corp", restored)
        self.assertIn("192.168.10.20", restored)
        self.assertNotIn("[EMAIL_01]", restored)
        self.assertNotIn("[IPV4_01]", restored)

    def test_couche3_secrets_are_strictly_non_reversible(self):
        """Vérifie que les secrets caviardés [SECRET_REMOVED] ne sont jamais mémorisés dans le Vault."""
        session_id = "test-session-no-secret-vault"
        prompt = "Clé secrète sk-123456789012345678909876543210 sur ip 10.1.2.3"
        res = sanitize(SanitizeRequest(text=prompt, session_id=session_id))
        sanitized = res["sanitized_text"]
        self.assertIn("[SECRET_REMOVED]", sanitized)

        # La ré-hydratation ne doit pas ré-injecter la clé secrète
        restored = deanonymize(DeanonymizeRequest(text=sanitized, session_id=session_id))
        self.assertIn("[SECRET_REMOVED]", restored["text"])
        self.assertNotIn("sk-123456789012345678909876543210", restored["text"])

    def test_couche3_streaming_deanonymizer_buffer(self):
        """Vérifie la ré-hydratation fluide au fil de l'eau sur flux de chunks découpés."""
        session_id = "test-session-stream-buffer"
        prompt = "Machine 10.50.60.70"
        sanitize(SanitizeRequest(text=prompt, session_id=session_id))

        buffer = DeanonymizingStreamBuffer(session_id=session_id)
        # Simulation d'un flux découpant le jeton [IPV4_01] sur plusieurs chunks
        chunks = [
            "Statut du serveur [",
            "IPV4",
            "_01",
            "] : OK en ligne."
        ]
        output_chunks = []
        for c in chunks:
            out = buffer.process_chunk(c)
            if out:
                output_chunks.append(out)
        out_flush = buffer.flush()
        if out_flush:
            output_chunks.append(out_flush)

        full_output = "".join(output_chunks)
        self.assertEqual(full_output, "Statut du serveur 10.50.60.70 : OK en ligne.")

    # =========================================================================
    # Couche 4 : Verrouillage ZDR LiteLLM Proxy / OpenRouter
    # =========================================================================

    def test_couche4_litellm_manifest_zdr_enforcement(self):
        """Vérifie que tous les modèles OpenRouter dans 05-litellm.yaml verrouillent ZDR côté serveur."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        manifest_path = os.path.join(root, "deploy", "manifests", "05-litellm.yaml")
        with open(manifest_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('data_collection: "deny"', content)
        self.assertIn('zdr: true', content)
        self.assertIn('allow_fallbacks: false', content)
        # Vérifie que les 3 modèles canoniques sont configurés avec le bloc provider
        for model in ("simple/free", "simple/auto", "agentic/expert"):
            self.assertIn(f'model_name: "{model}"', content)

    def test_couche4_litellm_lab_zdr_enforcement(self):
        """Vérifie que la configuration LiteLLM Lab verrouille également ZDR côté serveur."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        lab_path = os.path.join(root, "deploy", "litellm-lab.yaml")
        with open(lab_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('data_collection: "deny"', content)
        self.assertIn('zdr: true', content)
        self.assertIn('allow_fallbacks: false', content)

    # =========================================================================
    # Compatibilité LiteLLM Guardrail & Plugin Hermes
    # =========================================================================

    def test_litellm_analyze_and_anonymize_contract(self):
        """Vérifie que /analyze et /anonymize respectent l'interface guardrail LiteLLM."""
        from unittest.mock import patch, MagicMock
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = []

        prompt = "Serveur 10.20.30.40 avec password=MySecretPassword123 et contact alice@example.com"
        with patch("app.get_analyzer", return_value=mock_analyzer):
            findings = analyze(AnalyzeRequest(text=prompt, language="fr"))
            entity_types = {f["entity_type"] for f in findings}
            self.assertIn("SECRET", entity_types)
            self.assertIn("IP_ADDRESS", entity_types)
            self.assertIn("EMAIL_ADDRESS", entity_types)

            anon = anonymize(AnonymizeRequest(text=prompt, analyzer_results=findings))
            self.assertNotIn("10.20.30.40", anon["text"])
            self.assertNotIn("MySecretPassword123", anon["text"])
            self.assertNotIn("alice@example.com", anon["text"])

    def test_hermes_governance_plugin_ccr_and_dlp(self):
        """Vérifie le fonctionnement du plugin Hermes (CCR, fail-closed et ré-hydratation)."""
        import tempfile
        from unittest.mock import patch
        hermes_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "hermes")
        if hermes_dir not in sys.path:
            sys.path.insert(0, hermes_dir)
        import plugin as hermes_plugin

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hermes_plugin, "get_ccr_cache_dir", return_value=tmpdir):
                large_items = [{"id": i, "label": f"Item-{i}", "detail": "x" * 120} for i in range(90)]
                large_json = json.dumps({"results": large_items})
                compressed = hermes_plugin.compress_large_json(large_json)
                parsed_comp = json.loads(compressed)
                self.assertIn("_arcia_ccr", parsed_comp)
                ccr_hash = parsed_comp["_arcia_ccr"]["hash"]
                self.assertEqual(len(ccr_hash), 12)

                restored_key = hermes_plugin.ccr_retrieve(ccr_hash, json_key="results")
                self.assertTrue(restored_key["found"])
                self.assertEqual(len(restored_key["value"]), 90)

                # Test fail-closed DLP : si Presidio est injoignable et PRESIDIO_FAIL_CLOSED=true -> RuntimeError
                with patch.object(hermes_plugin, "PRESIDIO_DLP_URL", "http://127.0.0.1:59999/sanitize"), \
                     patch.object(hermes_plugin, "PRESIDIO_FAIL_CLOSED", True):
                    with self.assertRaises(RuntimeError):
                        hermes_plugin.on_pre_llm_call([{"role": "user", "content": "Mon secret sk-12345678901234567890"}])


if __name__ == "__main__":
    unittest.main()
