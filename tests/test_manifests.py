#!/usr/bin/env python3
"""
Manifest validation test: checks all deploy/manifests/*.yaml files.
"""

import os
import unittest
import glob

class TestKubernetesManifests(unittest.TestCase):

    def setUp(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.manifests_dir = os.path.join(root_dir, "deploy", "manifests")

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


if __name__ == "__main__":
    unittest.main()
