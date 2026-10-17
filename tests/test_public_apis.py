#!/usr/bin/env python3
"""
Unit tests for ArcIA Public APIs Gateway (skills/public-apis/scripts/public_apis.py).
"""

import os
import sys
import json
import unittest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PA_DIR = os.path.join(SCRIPT_DIR, "skills", "public-apis", "scripts")
sys.path.insert(0, PA_DIR)

import public_apis

class TestPublicApis(unittest.TestCase):

    def test_french_tva_computation(self):
        """Vérifie l'exactitude mathématique du calcul de la TVA intracommunautaire française."""
        # Formule : (12 + 3 * (siren % 97)) % 97
        # Exemple 1 : SIREN 130025265 -> (12 + 3 * (130025265 % 97)) % 97 = 07 -> FR07130025265
        tva = public_apis.compute_french_tva("130025265")
        self.assertEqual(tva, "FR07130025265")

        # Exemple 2 : SIREN avec espaces ou ponctuation
        tva_spaced = public_apis.compute_french_tva("130 025 265")
        self.assertEqual(tva_spaced, "FR07130025265")

        # Exemple 3 : SIREN invalide
        tva_inv = public_apis.compute_french_tva("12345")
        self.assertTrue("N/A" in tva_inv)

    def test_catalog_structure(self):
        """Vérifie que catalog.json existe et contient les définitions d'APIs requises."""
        catalog_path = os.path.join(SCRIPT_DIR, "skills", "public-apis", "catalog.json")
        self.assertTrue(os.path.isfile(catalog_path), f"Fichier {catalog_path} introuvable")
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("apis", data)
        api_ids = [a["id"] for a in data["apis"]]
        self.assertIn("recherche-entreprises", api_ids)
        self.assertIn("base-adresse-nationale", api_ids)
        self.assertIn("open-meteo-france", api_ids)

        for api in data["apis"]:
            self.assertFalse(api["auth_required"])
            self.assertTrue(api["base_url"].startswith("https://"))

    def test_format_company_markdown(self):
        """Vérifie la mise en forme Markdown synthétique d'une entreprise."""
        fake_company = {
            "nom_complet": "EXEMPLE SA",
            "siren": "123456782",
            "etat_administratif": "A",
            "activite_principale": "62.02A",
            "date_creation": "2020-01-01",
            "siege": {
                "siret": "12345678200010",
                "adresse": "10 RUE DE LA PAIX 75001 PARIS"
            },
            "dirigeants": [
                {
                    "nom": "DUPONT",
                    "prenoms": "JEAN",
                    "qualite": "Président",
                    "type_dirigeant": "personne physique"
                }
            ]
        }
        md = public_apis.format_company_markdown(fake_company)
        self.assertIn("EXEMPLE SA", md)
        self.assertIn("123456782", md)
        self.assertIn("12345678200010", md)
        self.assertIn("🟢 Actif", md)
        self.assertIn("JEAN DUPONT (Président)", md)

    def test_format_address_markdown(self):
        """Vérifie la mise en forme Markdown synthétique d'une adresse."""
        fake_addr = {
            "properties": {
                "label": "10 Rue de la Paix 75001 Paris",
                "postcode": "75001",
                "city": "Paris",
                "context": "75, Paris, Île-de-France",
                "score": 0.95
            },
            "geometry": {
                "coordinates": [2.3312, 48.8698]
            }
        }
        md = public_apis.format_address_markdown(fake_addr)
        self.assertIn("10 Rue de la Paix 75001 Paris", md)
        self.assertIn("75001 Paris", md)
        self.assertIn("95%", md)

    def test_cache_mechanism(self):
        """Vérifie le fonctionnement de la mise en cache sur disque avec TTL."""
        test_key = "http://test-cache-key-for-unit-tests"
        test_data = {"test_val": 42, "status": "ok"}
        public_apis.write_cache(test_key, test_data)

        cached = public_apis.read_cache(test_key, max_age=60)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.get("test_val"), 42)

        # Vérifier expiration si max_age = 0
        expired = public_apis.read_cache(test_key, max_age=0)
        self.assertIsNone(expired)

if __name__ == "__main__":
    unittest.main()
