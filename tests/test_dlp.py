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
        """Vérifie que les noms d'entreprises et lieux publics (ex: Arcitek, Paris) ne sont PAS caviardés."""
        prompt = "Donne-moi le SIRET de la société Arcitek à Boulogne-Billancourt ou à Paris."
        res = sanitize(SanitizeRequest(text=prompt, language="fr"))
        self.assertIn("Arcitek", res["sanitized_text"])
        self.assertNotIn("[ARCIA_LOCATION]", res["sanitized_text"])
        self.assertNotIn("[ARCIA_ORGANIZATION]", res["sanitized_text"])


if __name__ == "__main__":
    unittest.main()
