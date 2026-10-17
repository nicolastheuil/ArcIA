#!/usr/bin/env python3
"""
Privacy Gate test: ensures no private IPs, tenant names or domains are tracked in git.
Patterns can be configured via the ARCIA_PRIVACY_PATTERNS environment variable.
By default, verifies synthetic boundaries and absence of private RFC-1918 / test-net identifiers.
"""

import os
import unittest
import subprocess

class TestPrivacyBoundary(unittest.TestCase):

    def _check_pattern_not_in_git(self, pattern: str, case_sensitive: bool = True):
        cmd = ["git", "grep"]
        if not case_sensitive:
            cmd.append("-i")
        cmd.extend([pattern, "--", ":(exclude)tests/test_privacy.py", ":(exclude)assets/*"])
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, f"Fuite de motif privé détectée pour '{pattern}' :\n{proc.stdout}")

    def test_dynamic_privacy_patterns_from_env(self):
        """Vérifie tous les motifs privés injectés via la variable ARCIA_PRIVACY_PATTERNS."""
        env_patterns = os.environ.get("ARCIA_PRIVACY_PATTERNS", "").strip()
        if env_patterns:
            for p in env_patterns.split(","):
                pattern = p.strip()
                if pattern:
                    self._check_pattern_not_in_git(pattern)

    def test_synthetic_boundary_checks(self):
        """Vérifie l'absence de motifs sensibles synthétiques et d'identifiants privés d'instance."""
        synthetic_forbidden = [
            "SECRET_PRIVATE_API_KEY_NEVER_COMMIT",
            "198.51.100.254",
            "internal.private.corp.example",
            "arcitek",
            "OpenAI.Codex",
            "789315306",
            "yves kermen"
        ]
        for pattern in synthetic_forbidden:
            self._check_pattern_not_in_git(pattern, case_sensitive=False)


if __name__ == "__main__":
    unittest.main()
