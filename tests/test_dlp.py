#!/usr/bin/env python3
"""
Test de non-régression et qualification du bouclier DLP ArcIA (Presidio Sanitizer).
Vérifie le caviardage effectif des adresses IP, secrets, emails, IBAN, cartes et téléphones.
"""

import unittest
import sys
import os

# Ajout du chemin des services pour importer le module app
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "presidio"))
try:
    from app import sanitize, SanitizeRequest, IP_PATTERN, SECRET_PATTERNS, EMAIL_PATTERN, PHONE_PATTERN
    APP_AVAILABLE = True
except ImportError:
    APP_AVAILABLE = False


class TestArcIADLP(unittest.TestCase):

    def setUp(self):
        if not APP_AVAILABLE:
            self.skipTest("Module services/presidio/app.py introuvable")

    def test_ip_address_redaction(self):
        """Vérifie que les adresses IP (v4) sont obligatoirement caviardées (Constat D1 résolu)."""
        prompt = "Connexion au serveur Postgres sur 192.168.1.45 et passerelle 10.0.0.1 requise."
        res = sanitize(SanitizeRequest(text=prompt, language="fr"))
        self.assertNotIn("192.168.1.45", res["sanitized_text"])
        self.assertNotIn("10.0.0.1", res["sanitized_text"])
        self.assertIn("[ARCIA_IP_ADDRESS_", res["sanitized_text"])
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
        self.assertIn("[ARCIA_EMAIL_", res["sanitized_text"])
        self.assertIn("[ARCIA_IBAN_", res["sanitized_text"])

    def test_phone_number_redaction(self):
        """Vérifie le caviardage des numéros de téléphone."""
        prompt = "Contactez le support au 06 12 34 56 78 ou au +33145678910."
        res = sanitize(SanitizeRequest(text=prompt, language="fr"))
        self.assertNotIn("06 12 34 56 78", res["sanitized_text"])
        self.assertNotIn("+33145678910", res["sanitized_text"])
        self.assertIn("[ARCIA_PHONE_", res["sanitized_text"])

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
        self.assertNotIn("[ARCIA_LOCATION]", res["sanitized_text"])
        self.assertNotIn("[ARCIA_ORGANIZATION]", res["sanitized_text"])

    def test_urls_and_python_scripts_preserved(self):
        """Vérifie que les URLs et scripts Python (ex: public_apis.py) ne sont jamais caviardés en [ARCIA_URL]."""
        prompt = "Exécute le script /opt/data/skills/public-apis/scripts/public_apis.py pour interroger https://recherche-entreprises.api.gouv.fr."
        res = sanitize(SanitizeRequest(text=prompt, language="fr"))
        self.assertIn("public_apis.py", res["sanitized_text"])
        self.assertIn("https://recherche-entreprises.api.gouv.fr", res["sanitized_text"])
        self.assertNotIn("[ARCIA_URL]", res["sanitized_text"])

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
        # apis.py starts at index 44 and ends at 51
        mock_analyzer.analyze.return_value = [
            FakeRecognizerResult(entity_type="URL", start=44, end=51)
        ]

        with patch("app.get_analyzer", return_value=mock_analyzer):
            res = sanitize(SanitizeRequest(text=text, language="fr"))
            self.assertNotIn("[ARCIA_URL]", res["sanitized_text"])
            self.assertIn("public_apis.py", res["sanitized_text"])
            self.assertNotIn("URL", res["entities_detected"])

    def test_litellm_analyze_and_anonymize_contract(self):
        """Vérifie que /analyze détecte les secrets et IP (même avec analyzer NLP actif) et que /anonymize caviarde le texte."""
        from unittest.mock import patch, MagicMock
        from app import analyze, anonymize, AnalyzeRequest, AnonymizeRequest
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

            # Double-barrière idempotente : repasser le texte déjà caviardé ne le corrompt pas
            second_pass = anonymize(AnonymizeRequest(text=anon["text"]))
            self.assertEqual(second_pass["text"], anon["text"])

    def test_hermes_governance_plugin_ccr_and_dlp(self):
        """Vérifie le fonctionnement du plugin Hermes (CCR réversible, préservation JSON, RTK, et DLP fail-closed)."""
        import tempfile
        import json
        from unittest.mock import patch
        hermes_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "hermes")
        if hermes_dir not in sys.path:
            sys.path.insert(0, hermes_dir)
        import plugin as hermes_plugin

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(hermes_plugin, "get_ccr_cache_dir", return_value=tmpdir):
                # 1. Test CCR sur une grosse payload JSON (> 8192 bytes)
                large_items = [{"id": i, "label": f"Item-{i}", "detail": "x" * 120} for i in range(90)]
                large_json = json.dumps({"results": large_items})
                compressed = hermes_plugin.compress_large_json(large_json)
                # Le résultat doit rester du JSON valide pour ne pas casser json.loads() des skills
                parsed_comp = json.loads(compressed)
                self.assertIn("_arcia_ccr", parsed_comp)
                ccr_hash = parsed_comp["_arcia_ccr"]["hash"]
                self.assertEqual(len(ccr_hash), 12)

                # Récupération intégrale via ccr_retrieve (avec --key results)
                restored_key = hermes_plugin.ccr_retrieve(ccr_hash, json_key="results")
                self.assertTrue(restored_key["found"])
                self.assertEqual(len(restored_key["value"]), 90)

                # 2. Test fail-closed DLP : si Presidio est injoignable et PRESIDIO_FAIL_CLOSED=true -> RuntimeError
                with patch.object(hermes_plugin, "PRESIDIO_DLP_URL", "http://127.0.0.1:59999/sanitize"), \
                     patch.object(hermes_plugin, "PRESIDIO_FAIL_CLOSED", True):
                    with self.assertRaises(RuntimeError):
                        hermes_plugin.on_pre_llm_call([{"role": "user", "content": "Mon secret sk-12345678901234567890"}])


if __name__ == "__main__":
    unittest.main()

