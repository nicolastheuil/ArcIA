<p align="left">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.5.2-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <a href="../README.md"><img src="https://img.shields.io/badge/🧠_Skills-Catalogue_Natif-0C2762?style=flat-square" alt="Skills"></a>
  <img src="https://img.shields.io/badge/GraphRAG-AST_Déterministe_(0_Token)-6BE7DD?style=flat-square&logoColor=050712" alt="GraphRAG AST">
</p>

# 🕸️ Graphify — cartographie AST et GraphRAG local déterministe

> **[🏠 Accueil ArcIA](../../README.md)** › **[🧠 Compétences](../README.md)** › **Graphify (`skills/graphify/`)**

Ce dossier abrite la compétence native **Graphify**, le moteur d'exploration et de cartographie structurelle de bases de code d'**ArcIA**.

---

## 🎯 Pourquoi Graphify ?

Lorsqu'un agent autonome comme Hermes intervient sur un dépôt de 10 000 à 100 000+ lignes de code :
* **Éviter la saturation de contexte** : Lire les fichiers un par un consomme des dizaines de milliers de tokens et dégrade la précision de l'agent.
* **Prévenir les effets de bord** : Identifier immédiatement les carrefours d'architecture (*God nodes*) et les dépendances croisées avant toute modification.
* **Garantir l'étanchéité souveraine** : Contrairement aux solutions d'indexation vectorielle Cloud, Graphify tourne **100 % en local sur CPU** (0 token consommé, 0 octet de code transmis à l'extérieur).

---

## ⚙️ Fonctionnement et pipeline AST

Le moteur repose sur le script Python standard [`scripts/arcia_graphify.py`](../../scripts/arcia_graphify.py) :

```mermaid
flowchart LR
    Code["Code Source (.py, .js, .ts, ...)"] ==> AST["Parseur AST & Regex Local"]
    AST ==> Graph["Graphe Relationnel & Centralité"]
    Graph ==> Report["GRAPH_REPORT.md (Synthèse Compacte)"]
    Graph ==> JSON["graph.json (Arêtes & Appels)"]
    Report ==> Hermes["Hermes Agent (Ciblage Chirurgical)"]

    style Code fill:#0C2762,stroke:#1659E4,stroke-width:2px,color:#F8FAFC
    style AST fill:#0F172A,stroke:#6BE7DD,stroke-width:2px,color:#F8FAFC
    style Graph fill:#0C2762,stroke:#6BE7DD,stroke-width:2px,color:#F8FAFC
    style Report fill:#0F172A,stroke:#10B981,stroke-width:2px,color:#F8FAFC
    style Hermes fill:#1E1B4B,stroke:#FA7B4E,stroke-width:2px,color:#F8FAFC
```

### 🚀 Commande d'exécution
```bash
python scripts/arcia_graphify.py --root . --output-json graph.json --output-report GRAPH_REPORT.md
```

---

## 📖 Fichiers associés
* 📄 **[SKILL.md](SKILL.md)** : Fiche de directives opérationnelles injectée dans Hermes Agent.
* 🐍 **[scripts/arcia_graphify.py](../../scripts/arcia_graphify.py)** : Analyseur AST déterministe (bibliothèque standard Python 3).
