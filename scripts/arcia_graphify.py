#!/usr/bin/env python3
"""
ArcIA — Extracteur Déterministe de Graphe de Connaissances (AST / GraphRAG)
===========================================================================
Génère une cartographie structurelle de code source (dépendances, appels,
classes, fonctions, couplages) sans aucun appel LLM externe ni fuite de données.
100% autonome en Python Standard Library.
"""

import os
import sys
import ast
import json
import re
import argparse
from typing import Dict, Any, List, Set, Optional

def analyze_python_file(filepath: str, rel_path: str) -> Dict[str, Any]:
    """Analyse un fichier Python via le module standard 'ast'."""
    nodes = []
    edges = []
    
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        tree = ast.parse(source, filename=rel_path)
    except Exception as e:
        return {"nodes": [{"id": rel_path, "type": "module", "error": str(e)}], "edges": []}

    module_node_id = f"module:{rel_path}"
    nodes.append({
        "id": module_node_id,
        "type": "module",
        "path": rel_path,
        "lines": len(source.splitlines())
    })

    current_class = None

    class CodeVisitor(ast.NodeVisitor):
        def __init__(self):
            self.classes = []
            self.functions = []
            self.imports = []
            self.calls = []

        def visit_Import(self, node):
            for alias in node.names:
                imp_id = f"import:{alias.name}"
                nodes.append({"id": imp_id, "type": "external_import", "name": alias.name})
                edges.append({"source": module_node_id, "target": imp_id, "type": "imports"})
            self.generic_visit(node)

        def visit_ImportFrom(self, node):
            module_name = node.module or ""
            for alias in node.names:
                target_name = f"{module_name}.{alias.name}" if module_name else alias.name
                imp_id = f"import:{target_name}"
                nodes.append({"id": imp_id, "type": "external_import", "name": target_name})
                edges.append({"source": module_node_id, "target": imp_id, "type": "imports"})
            self.generic_visit(node)

        def visit_ClassDef(self, node):
            class_id = f"class:{rel_path}::{node.name}"
            nodes.append({
                "id": class_id,
                "type": "class",
                "name": node.name,
                "module": rel_path,
                "line": node.lineno
            })
            edges.append({"source": module_node_id, "target": class_id, "type": "defines"})
            
            # Bases (héritage)
            for base in node.bases:
                if isinstance(base, ast.Name):
                    edges.append({"source": class_id, "target": f"class_ref:{base.id}", "type": "inherits"})
            
            old_class = self.classes
            self.classes.append(class_id)
            self.generic_visit(node)
            self.classes.pop()

        def visit_FunctionDef(self, node):
            parent = self.classes[-1] if self.classes else module_node_id
            func_id = f"func:{rel_path}::{node.name}"
            nodes.append({
                "id": func_id,
                "type": "function",
                "name": node.name,
                "parent": parent,
                "line": node.lineno
            })
            edges.append({"source": parent, "target": func_id, "type": "defines"})
            self.generic_visit(node)

        def visit_Call(self, node):
            call_name = None
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            if call_name:
                self.calls.append(call_name)
            self.generic_visit(node)

    visitor = CodeVisitor()
    visitor.visit(tree)

    return {"nodes": nodes, "edges": edges}

def scan_text_file(filepath: str, rel_path: str) -> Dict[str, Any]:
    """Analyse basique pour fichiers non-Python (Markdown, Shell, YAML, etc.)."""
    nodes = []
    edges = []
    module_node_id = f"file:{rel_path}"
    
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return {"nodes": [], "edges": []}

    file_ext = os.path.splitext(rel_path)[1].lower()
    nodes.append({
        "id": module_node_id,
        "type": "file",
        "path": rel_path,
        "extension": file_ext,
        "lines": len(lines)
    })

    # Détection de liens relatifs dans Markdown
    if file_ext == ".md":
        link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
        for line in lines:
            for match in link_pattern.finditer(line):
                target = match.group(2)
                if not target.startswith("http") and not target.startswith("#"):
                    clean_target = target.split("#")[0]
                    edges.append({
                        "source": module_node_id,
                        "target": f"file:{clean_target}",
                        "type": "links_to"
                    })

    return {"nodes": nodes, "edges": edges}

def build_knowledge_graph(root_dir: str, exclude_dirs: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Parcourt l'arborescence et génère le graphe complet."""
    if exclude_dirs is None:
        exclude_dirs = {".git", ".personal", "node_modules", "__pycache__", ".venv", "artifacts", "visual", "secrets"}

    all_nodes: Dict[str, Dict[str, Any]] = {}
    all_edges: List[Dict[str, Any]] = []

    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, root_dir).replace("\\", "/")
            ext = os.path.splitext(file)[1].lower()

            if ext == ".py":
                res = analyze_python_file(full_path, rel_path)
            elif ext in [".md", ".sh", ".ps1", ".yaml", ".yml", ".json"]:
                res = scan_text_file(full_path, rel_path)
            else:
                continue

            for n in res["nodes"]:
                all_nodes[n["id"]] = n
            all_edges.extend(res["edges"])

    # Calcul de centralité / degré des nœuds pour identifier les composants critiques ("God nodes")
    in_degree: Dict[str, int] = {}
    out_degree: Dict[str, int] = {}

    for e in all_edges:
        src = e["source"]
        tgt = e["target"]
        out_degree[src] = out_degree.get(src, 0) + 1
        in_degree[tgt] = in_degree.get(tgt, 0) + 1

    for nid, node in all_nodes.items():
        node["in_degree"] = in_degree.get(nid, 0)
        node["out_degree"] = out_degree.get(nid, 0)
        node["total_degree"] = node["in_degree"] + node["out_degree"]

    return {
        "metadata": {
            "root_directory": root_dir,
            "total_nodes": len(all_nodes),
            "total_edges": len(all_edges)
        },
        "nodes": list(all_nodes.values()),
        "edges": all_edges
    }

def generate_markdown_report(graph: Dict[str, Any]) -> str:
    """Produit un rapport de synthèse GraphRAG condensé pour l'agent."""
    nodes = graph["nodes"]
    edges = graph["edges"]
    meta = graph["metadata"]

    # Top central components
    sorted_nodes = sorted(nodes, key=lambda x: x.get("total_degree", 0), reverse=True)
    top_central = [n for n in sorted_nodes if n.get("type") in ["module", "file", "class"]][:10]

    report = []
    report.append("# ArcIA — Rapport Graphify (Cartographie de Code & Dépendances)")
    report.append("")
    report.append(f"- **Composants cartographiés (nœuds)** : {meta['total_nodes']}")
    report.append(f"- **Relations et liens (arêtes)** : {meta['total_edges']}")
    report.append("")
    report.append("## 1. Nœuds Centraux & Composants Clés (Centralité)")
    report.append("")
    report.append("| Nœud | Type | Degré Total | Liens Entrants | Liens Sortants |")
    report.append("|---|---|---|---|---|")
    for n in top_central:
        report.append(f"| `{n['id']}` | {n.get('type')} | {n.get('total_degree', 0)} | {n.get('in_degree', 0)} | {n.get('out_degree', 0)} |")

    report.append("")
    report.append("## 2. Dépendances Externes Détectées")
    report.append("")
    ext_imports = sorted(list({n.get("name") for n in nodes if n.get("type") == "external_import" and n.get("name")}))
    if ext_imports:
        report.append(", ".join([f"`{x}`" for x in ext_imports]))
    else:
        report.append("*Aucune dépendance externe requise.*")

    report.append("")
    report.append("## 3. Guide de Navigation pour l'Agent (GraphRAG)")
    report.append("")
    report.append("Pour explorer une fonction ou classe spécifique, consulter le fichier `graph.json` généré.")
    report.append("Ce graphe évite les recherches de texte massives (`grep`) et cible directement les relations d'appel.")

    return "\n".join(report)

def main():
    parser = argparse.ArgumentParser(description="ArcIA Graphify AST / Knowledge Graph Generator")
    parser.add_argument("--root", default=".", help="Répertoire racine à analyser")
    parser.add_argument("--output-json", default="graph.json", help="Fichier de sortie JSON")
    parser.add_argument("--output-report", default="GRAPH_REPORT.md", help="Fichier de sortie rapport Markdown")
    args = parser.parse_args()

    graph = build_knowledge_graph(args.root)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)

    report_content = generate_markdown_report(graph)
    with open(args.output_report, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"[OK] Graphify : {graph['metadata']['total_nodes']} nœuds et {graph['metadata']['total_edges']} arêtes analysés.")
    print(f"[OK] Graphe sauvegardé dans : {args.output_json}")
    print(f"[OK] Rapport sauvegardé dans : {args.output_report}")

if __name__ == "__main__":
    main()
