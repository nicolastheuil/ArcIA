# Scripts d'Automatisation & Déploiement — ArcIA

Ce dossier regroupe l'ensemble des outils d'automatisation, assistants de configuration, moteurs de déploiement et utilitaires de validation pour la plateforme ArcIA.

## Vue d'Ensemble des Outils

### 1. Moteurs de Déploiement & Assistants

* **[deploy.py](deploy.py)** : Moteur de déploiement universel Python (multiplateforme). Valide la configuration `arcia.config.yaml`, vérifie les prérequis du cluster Kubernetes, génère les secrets et déploie les manifests ordonnés.
  ```bash
  python scripts/deploy.py --config arcia.config.yaml
  # Mode simulation :
  python scripts/deploy.py --config arcia.config.yaml --dry-run
  ```
* **[wizard.py](wizard.py)** : Assistant web interactif local (port 8765) guidant pas-à-pas la configuration d'ArcIA (génération de clés, sélection du dimensionnement VMware/K3s, secrets Entra ID et validation).
  ```bash
  python scripts/wizard.py
  ```
* **[deploy-arcia.sh](deploy-arcia.sh)** : Script d'orchestration Shell pour environnements Linux/macOS.
* **[Deploy-ArcIA.ps1](Deploy-ArcIA.ps1)** : Script d'orchestration PowerShell pour environnements Windows.
* **[Deploy-VMwareCluster.ps1](Deploy-VMwareCluster.ps1)** : Provisionnement automatisé des 3 machines virtuelles Debian sur VMware vSphere / ESXi.

### 2. Gestion des Secrets & État Protégé

* **[apply-secrets.sh](apply-secrets.sh)** / **[Apply-Secrets.ps1](Apply-Secrets.ps1)** : Injection sécurisée des secrets dans le cluster Kubernetes (OAuth2, Presidio, LiteLLM, Hermes, Open-WebUI) depuis le trousseau local.
* **[ProtectedState.ps1](ProtectedState.ps1)** : Gestion de l'état protégé et persistant des composants sans exposition de secrets bruts.

### 3. Outillage Agentique & Synchronisation

* **[arcia_graphify.py](arcia_graphify.py)** : Analyseur AST déterministe en Python pur produisant la cartographie de code et le rapport GraphRAG local (`skills/graphify/`).
  ```bash
  python scripts/arcia_graphify.py --src ./mon-code --output ./graph.json
  ```
* **[Sync-Skills.ps1](Sync-Skills.ps1)** : Script de synchronisation du catalogue de compétences d'entreprise vers le volume partagé `/var/data/arcia/shared-skills`.
* **[Invoke-K3s.ps1](Invoke-K3s.ps1)** : Wrapper d'exécution de commandes kubectl/k3s sécurisées avec gestion de session.

### 4. Validation & Qualité

* **[validate_docs.py](validate_docs.py)** : Validateur d'intégrité de la documentation. Vérifie que chaque lien Markdown interne et ancre HTML pointe vers un fichier réellement suivi dans Git.
  ```bash
  python scripts/validate_docs.py
  ```
* **[test-validation.sh](test-validation.sh)** : Script Shell exécutant la suite complète des tests de non-régression et de frontière de confidentialité.
