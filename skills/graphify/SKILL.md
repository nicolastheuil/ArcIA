# Skill : Graphify (Cartographie Structurelle de Code & GraphRAG Local)

## Présentation

**Graphify** est un système de cartographie structurelle de codebase par arbre syntaxique (AST) et graphe de relations.
Il permet à l'agent Hermes d'explorer rapidement l'architecture d'un projet, ses dépendances, ses classes et ses fonctions maîtresses sans saturer sa fenêtre de contexte avec des dizaines de lectures de fichiers bruts ou des `grep` aveugles.

> [!IMPORTANT]
> **Souveraineté & Zéro Fuite de Données**
> - L'analyse AST est **100% locale et déterministe** via `scripts/arcia_graphify.py`.
> - **Zéro appel LLM externe** pour la cartographie du code : aucun fragment de code ne sort du périmètre.
> - Coût en tokens : 0 token d'inférence pour la construction du graphe.

---

## Déclenchement & Utilisation

Lorsque Hermes doit comprendre l'architecture d'un dépôt ou localiser les composants centraux :

1. **Exécuter l'analyseur de structure locale** :
   ```bash
   python scripts/arcia_graphify.py --root . --output-json graph.json --output-report GRAPH_REPORT.md
   ```

2. **Consulter en priorité le rapport condensé `GRAPH_REPORT.md`** :
   - Observer les **Nœuds Centraux (God nodes)** qui concentrent le plus grand nombre de dépendances ou d'appels.
   - Identifier les dépendances externes (`import`) utilisées par le projet.

3. **Interroger les arêtes et chemins critiques dans `graph.json`** :
   - Cibler directement le fichier et la fonction à éditer sans avoir besoin de relire l'intégralité du code source.

---

## Directives d'Intégrité ArcIA

- Ne jamais inclure dans le graphe des répertoires contenant des secrets (`secrets/`, `.personal/`, `.env`).
- Les fichiers générés (`graph.json`, `GRAPH_REPORT.md`) sont des artefacts de travail locaux et ne doivent pas être exposés sur des endpoints publics non authentifiés.
