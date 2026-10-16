# Outillage d’ArcIA : Moteur Hermes & Compétences Intégrées

> **Statut : Implémenté (v0.3)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

Ce guide décrit l'outillage intégré, les extensions et les compétences agentiques déployées dans l'instance Hermes d'**ArcIA v0.3**.

---

## 1. Outils et Modules Déployés

| Outil / Compétence | Type | Emplacement | Rôle dans l'Architecture |
|---|---|---|---|
| **ArcIA Graphify** | Script d'analyse AST local | [scripts/arcia_graphify.py](../../scripts/arcia_graphify.py) | Cartographie structurelle de codebase, graphes de dépendances déterministes (0 token, 0 fuite) |
| **Ponytail** | Skill de sobriété logicielle | [skills/ponytail/SKILL.md](../../skills/ponytail/SKILL.md) | Échelle de décision YAGNI, prévention du sur-développement et de l'over-engineering |
| **Public-APIs** | Skill de gouvernance d'APIs | [skills/public-apis/SKILL.md](../../skills/public-apis/SKILL.md) | Référentiel de veille et règles de sécurisation des intégrations d'APIs externes |
| **Gestion des Clés PAT** | CLI de gestion | [scripts/arcia_keys.py](../../scripts/arcia_keys.py) | Émission de clés virtuelles LiteLLM et quotas pour power users N3 |

---

## 2. Tokenmaxing et Sobriété de Contexte

Le plugin natif ArcIA ([services/hermes/plugin.py](../../services/hermes/plugin.py)) intercepte et optimise automatiquement les flux d'entrée d'Hermes :
1. **Réécriture `git log`** : Simplifie les sorties verbeuses vers un format concis sans impacter les paramètres métier.
2. **Compression JSON Headroom (`arcia_compress_json_file`)** : Les fichiers JSON volumineux du workspace sont réduits de plus de 40% avant présentation au modèle, tout en conservant l'original paginable via `arcia_restore_tool_result`.
3. **Économie de Tokens & Respect DLP** : Les tokens économisés réduisent l'empreinte carbone et la facture API, tout en restant strictement contrôlés par Presidio DLP avant sortie cloud.

---

## 3. Analyse Déterministe de Codebase (ArcIA Graphify)

Pour comprendre l'architecture d'un projet sans consommer des millions de tokens en RAG naïf :
- L'analyseur AST Python ([scripts/arcia_graphify.py](../../scripts/arcia_graphify.py)) extrait classes, méthodes, fonctions, imports et dépendances de manière purement algorithmique.
- Produit un graphe orienté exportable en JSON ou en diagramme Mermaid.
- Zéro appel réseau, zéro token consommé, conformité totale avec le secret des affaires.

---

## 4. Synchronisation des Compétences

La mise à jour du catalogue de compétences s'effectue via les scripts dédiés :
- Sous Windows PowerShell :
  ```powershell
  .\scripts\Sync-Skills.ps1
  ```
- Sous Linux / Bash :
  ```bash
  bash skills/sync-skills.sh
  ```

Voir également : [Guide des Skills](skills.md) · [Mesures Tokenmaxing](tokenmaxing.md) · [Moteur d'Agents Hermes](hermes-agent.md).
