#!/usr/bin/env python3
"""
Unit tests for ArcIA Graphify AST / Knowledge Graph extractor.
"""

import os
import sys
import unittest
import tempfile
import json

# Ajout du dossier scripts au path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(root_dir, "scripts"))

import arcia_graphify

class TestArcIAGraphify(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        # Création d'un mini-projet de test
        self.py_file = os.path.join(self.test_dir.name, "sample.py")
        with open(self.py_file, "w", encoding="utf-8") as f:
            f.write(
                "import os\n"
                "from sys import version\n\n"
                "class DataProcessor:\n"
                "    def process(self):\n"
                "        return os.path.exists('.')\n\n"
                "def main_func():\n"
                "    dp = DataProcessor()\n"
                "    return dp.process()\n"
            )

        self.md_file = os.path.join(self.test_dir.name, "doc.md")
        with open(self.md_file, "w", encoding="utf-8") as f:
            f.write(
                "# Sample Documentation\n\n"
                "Consulter [le code](sample.py) pour les détails.\n"
            )

    def tearDown(self):
        self.test_dir.cleanup()

    def test_build_knowledge_graph(self):
        graph = arcia_graphify.build_knowledge_graph(self.test_dir.name)
        self.assertIn("metadata", graph)
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)
        self.assertGreater(graph["metadata"]["total_nodes"], 0)
        self.assertGreater(graph["metadata"]["total_edges"], 0)

        node_types = {n.get("type") for n in graph["nodes"]}
        self.assertIn("module", node_types)
        self.assertIn("class", node_types)
        self.assertIn("function", node_types)
        self.assertIn("external_import", node_types)

    def test_markdown_report_generation(self):
        graph = arcia_graphify.build_knowledge_graph(self.test_dir.name)
        report = arcia_graphify.generate_markdown_report(graph)
        self.assertIn("Rapport Graphify", report)
        self.assertIn("Nœuds Centraux", report)
        self.assertIn("Dépendances Externes", report)

    def test_graph_json_export(self):
        output_json = os.path.join(self.test_dir.name, "graph.json")
        output_report = os.path.join(self.test_dir.name, "GRAPH_REPORT.md")

        graph = arcia_graphify.build_knowledge_graph(self.test_dir.name)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(graph, f)
        with open(output_report, "w", encoding="utf-8") as f:
            f.write(arcia_graphify.generate_markdown_report(graph))

        self.assertTrue(os.path.isfile(output_json))
        self.assertTrue(os.path.isfile(output_report))

        with open(output_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["metadata"]["total_nodes"], graph["metadata"]["total_nodes"])


if __name__ == "__main__":
    unittest.main()
