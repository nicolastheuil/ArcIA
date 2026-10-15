#!/usr/bin/env python3
"""
Privacy Gate test: ensures no private IPs, tenant names or domains are tracked in git.
"""

import os
import unittest
import subprocess

class TestPrivacyBoundary(unittest.TestCase):

    def test_no_private_tenant_references_in_git(self):
        """Scanne tous les fichiers suivis par git pour s'assurer qu'aucun identifiant privé n'est présent."""
        pattern = "arc" + "itek"
        cmd = ["git", "grep", "-i", pattern, "--", ":(exclude)tests/test_privacy.py"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, f"Fuite de données privées détectée :\n{proc.stdout}")

    def test_no_private_wan_ip_in_git(self):
        """Vérifie l'absence de l'IP WAN de production."""
        pattern = "82.210" + ".11.39"
        cmd = ["git", "grep", pattern, "--", ":(exclude)tests/test_privacy.py"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, f"Fuite de l'IP WAN détectée :\n{proc.stdout}")

    def test_no_private_lan_cluster_ips_in_git(self):
        """Vérifie l'absence des IPs privées du cluster 172.31.210.x."""
        pattern = "172.31." + "210."
        cmd = ["git", "grep", "-E", pattern, "--", ":(exclude)tests/test_privacy.py"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, f"Fuite d'IPs de cluster détectée :\n{proc.stdout}")


if __name__ == "__main__":
    unittest.main()
