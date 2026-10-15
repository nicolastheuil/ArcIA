# ADR 0021 — Évaluation et intégration de Ponytail, Graphify et Public-APIs dans le harness

Date : 15 octobre 2026. Statut : Décidé et intégré dans ArcIA v0.2.

---

## 1. Contexte & Problématique

L'écosystème d'ingénierie agentique propose divers outils pour optimiser le travail des agents LLM :
- **Ponytail** (`DietrichGebert/ponytail`) : framework promouvant l'archétype du « lazy senior developer » pour restreindre l'over-engineering et le code inutile.
- **Graphify** (`graphifyy`) : générateur de graphe de connaissances (AST / GraphRAG) cartographiant les relations de code.
- **Public-APIs** (`public-apis/public-apis`) : répertoire communautaire d'APIs publiques gratuites.

L'objectif de cet ADR est d'évaluer la pertinence de chacun de ces trois composants au regard des principes directeurs d'ArcIA (souveraineté des données, hermétisme réseau, absence d'over-engineering, tokenmaxing, isolation multi-tenant et standard library) et de consigner les modalités d'intégration dans le harness.

---

## 2. Analyse de Pertinence par Composant

### 2.1 Ponytail
- **Nature** : Ensemble de directives comportementales structurées autour d'une échelle de décision stricte (*The Decision Ladder* / YAGNI).
- **Pertinence pour ArcIA** : **Très Élevée**.
  - Les agents d'entreprise ont une propension avérée à sur-architecturer, inventer des dépendances inutiles ou introduire des bibliothèques externes pour des fonctions triviales.
  - Ponytail renforce la doctrine de **Tokenmaxing** et la sobriété logicielle en forçant l'agent à exploiter la bibliothèque standard et les primitives déjà présentes avant d'ajouter le moindre fichier ou package.
  - **Décision** : **RETENU**. Intégré au catalogue de compétences partagées (`skills/ponytail/SKILL.md`) et déployé vers `/var/data/arcia/shared-skills/arcia/ponytail` pour consultation par Hermes.
  - **Garde-fous** : La recherche de sobriété ne dispense en aucun cas des validations aux frontières de confiance, de la couverture de tests et de l'anonymisation DLP.

### 2.2 Graphify
- **Nature** : Extraction de graphe de connaissances de codebase combinant analyse syntaxique AST et structuration relationnelle.
- **Pertinence pour ArcIA** : **Élevée (sous condition d'exécution déterministe locale)**.
  - La recherche aveugle (`grep`) ou la lecture séquentielle de multiples fichiers sature la fenêtre de contexte d'Hermes et entraîne des coûts d'inférence élevés.
  - La cartographie structurelle permet à l'agent de naviguer directement dans les dépendances, classes et fonctions clés (« God nodes »).
  - **Décision** : **RETENU**. Intégré sous la forme d'un analyseur AST autonome en Python Standard Library (`scripts/arcia_graphify.py`), sans dépendance externe lourde ni fuite de données. Il produit un artefact exploitable `graph.json` et un rapport synthétique `GRAPH_REPORT.md` (GraphRAG local).
  - **Garde-fous** : Zéro appel LLM externe pour la cartographie structurelle ; interdiction stricte d'analyser des répertoires sensibles (`secrets/`, `.personal/`).

### 2.3 Public-APIs
- **Nature** : Répertoire de plusieurs centaines de liens et documentations vers des APIs publiques externes.
- **Pertinence pour ArcIA** :
  - **En tant que service d'infrastructure / Daemon K3s** : **NULLE (REJET TOTAL)**. `public-apis` n'est ni un binaire ni une API ; déployer un conteneur dédié serait une absurdité architecturale.
  - **En tant qu'accès réseau libre** : **PROSCRIT**. Le plan d'intégration d'ArcIA (§10 et §20) stipule qu'Hermes ne possède aucun Internet général ni DNS libre.
  - **En tant que référentiel de veille & catalogue de schémas d'outils souverains** : **Pertinence de Veille Validée**.
  - **Décision** : **RETENU COMME CADRE DE VEILLE & MÉTHODOLOGIE DE SÉCURISATION**. Intégré via `skills/public-apis/SKILL.md` pour encadrer la qualification, la compatibilité OpenAPI, le passage obligatoire par Presidio DLP et le cloisonnement par `NetworkPolicy` pour toute API tierce requise par une instance.

---

## 3. Matrice Récapitulative des Décisions

| Composant | Rôle Identifié | Statut ArcIA | Modalité d'Intégration au Harness |
|---|---|---|---|
| **Ponytail** | Sobriété logicielle, YAGNI, anti-bloat | **Adopté** | Compétence partagée `skills/ponytail/SKILL.md` + sync-skills |
| **Graphify** | Cartographie AST & GraphRAG local | **Adopté** | Outil déterministe `scripts/arcia_graphify.py` + `skills/graphify/SKILL.md` |
| **Public-APIs** | Veille et sécurisation d'APIs tierces | **Cadré (Veille)** | Règle de gouvernance et guide `skills/public-apis/SKILL.md` |

---

## 4. Conséquences

1. **Outillage Hermes enrichi** : Hermes dispose désormais de méthodes explicites pour limiter son empreinte de code (Ponytail) et naviguer dans les grands projets (Graphify).
2. **Respect des frontières de sécurité** : Aucun service réseau supplémentaire n'est ouvert ; aucun port n'est exposé ; la consommation de tokens et la surface d'attaque restent minimales.
3. **Automatisation & Reproductibilité** : Le script de synchronisation (`skills/sync-skills.sh` et `scripts/Sync-Skills.ps1`) assure le provisionnement automatique sur le cluster K3s dans `/var/data/arcia/shared-skills`.
