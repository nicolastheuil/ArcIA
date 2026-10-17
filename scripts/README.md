# Scripts d'Automatisation & Déploiement — ArcIA

Ce dossier regroupe l'ensemble des outils d'automatisation, assistants de configuration, moteurs de déploiement et utilitaires de validation pour la plateforme ArcIA.

## Vue d'Ensemble des Outils

### 1. Moteurs de Déploiement & Assistants

* **[deploy.py](deploy.py)** : Moteur de déploiement universel Python (multiplateforme). Valide la configuration `arcia.config.yaml`, vérifie les prérequis du cluster Kubernetes, génère les secrets en mémoire, synchronise les ConfigMaps des microservices (`sync_service_configmaps`) et des skills natives, et déploie les manifests ordonnés.
  ```bash
  python scripts/deploy.py --config arcia.config.yaml
  # Mode simulation :
  python scripts/deploy.py --config arcia.config.yaml --dry-run
  ```
* **[wizard.py](wizard.py)** & **[wizard_ui/index.html](wizard_ui/index.html)** : Assistant web interactif local (port 8765) guidant pas-à-pas la configuration d'ArcIA (chiffrement AES-256-GCM de dépôt d'instance, sélection des 5 profils canoniques, secrets Entra ID/Teams et audit K8s).
  ```bash
  python scripts/wizard.py
  ```
* **[deploy-arcia.sh](deploy-arcia.sh)** : Script d'orchestration Shell pour environnements Linux/macOS.
* **[Deploy-ArcIA.ps1](Deploy-ArcIA.ps1)** : Script d'orchestration PowerShell pour environnements Windows.

### 2. Gouvernance Power Users (N3) & Clés Virtuelles

* **[arcia_poweruser.py](arcia_poweruser.py)** / **[Spawn-PowerUser.ps1](Spawn-PowerUser.ps1)** : Orchestrateur du cycle de vie des pods Hermes dédiés sur Kubernetes pour les Power Users N3 (`spawn`, `list`, `stop`, `start`, `destroy`) avec PVC `10Gi` isolé et `SOUL.md` personnalisée.
  ```bash
  python scripts/arcia_poweruser.py spawn dev@example.org --team engineering
  ```
* **[arcia_keys.py](arcia_keys.py)** : Gestionnaire CLI des clés virtuelles nominatives (PAT) et des budgets mensuels sur LiteLLM Proxy (`/v1`).
  ```bash
  python scripts/arcia_keys.py create --user dev@example.org --tier N3 --budget 25
  ```

### 3. Gestion des Secrets & État Protégé

* **[apply-secrets.sh](apply-secrets.sh)** / **[Apply-Secrets.ps1](Apply-Secrets.ps1)** : Injection sécurisée des secrets dans le cluster Kubernetes (`arcia-env-secret`, `litellm-secret`, `hermes-gateway-secret`, `presidio-secret`, `webui-secret`) depuis le trousseau local.
* **[ProtectedState.ps1](ProtectedState.ps1)** : Gestion de l'état protégé DPAPI et persistant des composants sans exposition de secrets bruts.

### 4. Outillage Agentique & Synchronisation

* **[arcia_graphify.py](arcia_graphify.py)** : Analyseur AST déterministe en Python pur produisant la cartographie de code et le rapport GraphRAG local (`skills/graphify/`).
  ```bash
  python scripts/arcia_graphify.py ./mon-code --json ./graph.json --report ./GRAPH_REPORT.md
  ```
* **[Sync-Skills.ps1](Sync-Skills.ps1)** : Script de synchronisation du catalogue de compétences d'entreprise vers le volume partagé `/var/data/arcia/shared-skills`.
* **[package_teams_app.py](package_teams_app.py)** / **[Package-TeamsApp.ps1](Package-TeamsApp.ps1)** : Empaquetage et validation de l'archive Microsoft Teams (`arcia-teams-app.zip`) pour importation directe dans le Portail Développeur Teams.
  ```bash
  python scripts/package_teams_app.py --bot-id "<BOT_APP_ID>"
  ```
* **[Invoke-K3s.ps1](Invoke-K3s.ps1)** : Wrapper d'exécution de commandes kubectl/k3s sécurisées à distance.

### 5. Validation & Qualité

* **[validate_docs.py](validate_docs.py)** : Validateur d'intégrité de la documentation. Vérifie que chaque lien Markdown interne et ancre HTML pointe vers un fichier réellement suivi dans Git.
  ```bash
  python scripts/validate_docs.py
  ```
* **[test-validation.sh](test-validation.sh)** : Script Shell exécutant la suite complète des tests unitaires et la recette bout-en-bout sur le cluster K3s.
