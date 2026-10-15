#!/usr/bin/env python3
"""
Unit tests for ArcIA built-in skills (ponytail, graphify, public-apis).
"""

import os
import unittest

class TestArcIASkills(unittest.TestCase):

    def setUp(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.skills_dir = os.path.join(root_dir, "skills")

    def test_skills_directory_exists(self):
        self.assertTrue(os.path.isdir(self.skills_dir))

    def test_builtin_skills_exist(self):
        expected_skills = ["ponytail", "graphify", "public-apis"]
        for skill in expected_skills:
            skill_path = os.path.join(self.skills_dir, skill, "SKILL.md")
            self.assertTrue(os.path.isfile(skill_path), f"Fichier SKILL.md manquant pour {skill}")
            with open(skill_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertGreater(len(content), 100, f"Contenu trop court pour {skill}")

    def test_ponytail_contains_decision_ladder(self):
        skill_path = os.path.join(self.skills_dir, "ponytail", "SKILL.md")
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Decision Ladder", content)
        self.assertIn("YAGNI", content)

    def test_graphify_contains_local_ast_rule(self):
        skill_path = os.path.join(self.skills_dir, "graphify", "SKILL.md")
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("arcia_graphify.py", content)
        self.assertIn("AST", content)

    def test_public_apis_contains_governance_rules(self):
        skill_path = os.path.join(self.skills_dir, "public-apis", "SKILL.md")
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Presidio DLP", content)
        self.assertIn("NetworkPolicy", content)


if __name__ == "__main__":
    unittest.main()
