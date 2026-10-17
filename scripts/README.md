<p align="left">
  <a href="../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.4-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <img src="https://img.shields.io/badge/Automation-PowerShell_&_Python_3.11-6BE7DD?style=flat-square&logoColor=050712" alt="Automation">
  <img src="https://img.shields.io/badge/Updates-Zero--Downtime_Engine-FA7B4E?style=flat-square" alt="Zero-Downtime Engine">
</p>

# ⚙️ Scripts d'Automatisation, Wizard & Outillage — ArcIA

> **[🏠 Accueil ArcIA](../README.md)** › **Scripts & Outillage (`scripts/`)**

Ce dossier regroupe les moteurs d'installation, le centre de mise à jour Zero-Downtime, les gestionnaires de Pods Power Users et les outils de validation de la plateforme **ArcIA**.

---

## 🚀 1. Setup Wizard, Mise à Jour Zero-Downtime & Déploiement

| Outil | Point d'Entrée Recommandé | Rôle & Fonctionnalités |
|---|---|---|
| **Setup & Update Wizard** | **[`.\wizard.ps1`](../wizard.ps1)** / **[`./wizard.sh`](../wizard.sh)**<br/>*(Moteur : [wizard.py](wizard.py) + [wizard_ui/index.html](wizard_ui/index.html))* | Centre de pilotage graphique : présentation de l'architecture, installation guidée, **vérification en ligne des nouvelles versions (`Open-WebUI`, `Hermes`, `LiteLLM`, `Presidio`, `OAuth2`)**, séquence de **mise à jour intelligente Zero-Downtime (`RollingUpdate`)** et restauration Git chiffrée (`AES-256-GCM`). |
| **Déploiement Headless** | **[Deploy-ArcIA.ps1](Deploy-ArcIA.ps1)** / **[deploy-arcia.sh](deploy-arcia.sh)**<br/>*(Moteur : [deploy.py](deploy.py))* | Orchestrateur CLI universel : valide `arcia.config.yaml`, qualifie le cluster Kubernetes, génère les secrets en mémoire, synchronise à chaud les ConfigMaps (`sync_service_configmaps`) et les skills natives, puis applique les manifestes. |

```powershell
# Lancer le Wizard graphique (Installation, Mise à jour Zero-Downtime ou Restauration) :
.\wizard.ps1

# Lancer un déploiement headless (ou une simulation -DryRun) :
.\scripts\Deploy-ArcIA.ps1
.\scripts\Deploy-ArcIA.ps1 -DryRun
```

---

## 👥 2. Gestion des Power Users & Clés Virtuelles

| Outil | Fichiers | Rôle & Commandes Types |
|---|---|---|
| **Pods Dédiés Power Users** | **[Spawn-PowerUser.ps1](Spawn-PowerUser.ps1)**<br/>*(Moteur : [arcia_poweruser.py](arcia_poweruser.py))* | Provisionne et pilote le cycle de vie (`spawn`, `list`, `stop`, `start`, `destroy`) des Pods Hermes dédiés par Power User avec PVC `10Gi` isolé et `SOUL.md` personnalisée. |
| **Clés Virtuelles LiteLLM** | **[arcia_keys.py](arcia_keys.py)** | Crée, liste et révoque les clés virtuelles nominatives (PAT) et les budgets mensuels sur LiteLLM Proxy (`/v1`) pour les profils `standard` et `poweruser`. |

```powershell
# Provisionner un Pod Hermes dédié pour un Power User :
.\scripts\Spawn-PowerUser.ps1 prenom.nom@example.org -Team engineering
.\scripts\Spawn-PowerUser.ps1 -Action list

# Générer une clé virtuelle PAT avec budget mensuel :
python scripts/arcia_keys.py create --user prenom.nom@example.org --profile poweruser --budget 50
```

---

## 🔐 3. Gestion des Secrets & État Protégé

* **[Apply-Secrets.ps1](Apply-Secrets.ps1)** / **[apply-secrets.sh](apply-secrets.sh)** : Injection sécurisée des secrets dans le cluster Kubernetes (`arcia-env-secret`, `litellm-secret`, `hermes-gateway-secret`, `presidio-secret`, `webui-secret`) depuis le trousseau local sans écriture en clair dans Git.
* **[ProtectedState.ps1](ProtectedState.ps1)** : Chiffrement local DPAPI et gestion de l'état protégé de l'instance.

---

## 🧠 4. Outillage Cognitif, GraphRAG & Empaquetage Teams

* **[arcia_graphify.py](arcia_graphify.py)** : Analyseur AST déterministe en Python pur générant la cartographie structurelle et le rapport GraphRAG local (`skills/graphify/`) sans consommer aucun token LLM.
  ```bash
  python scripts/arcia_graphify.py ./mon-code --json ./graph.json --report ./GRAPH_REPORT.md
  ```
* **[Sync-Skills.ps1](Sync-Skills.ps1)** : Synchronise à chaud le catalogue `skills/` vers le volume partagé `/var/data/arcia/shared-skills`.
* **[Package-TeamsApp.ps1](Package-TeamsApp.ps1)** / **[package_teams_app.py](package_teams_app.py)** : Génère et valide l'archive officielle `arcia-teams-app.zip` pour le Portail Développeur Microsoft Teams.
* **[Invoke-K3s.ps1](Invoke-K3s.ps1)** : Exécuteur de commandes `kubectl` sécurisées sur le cluster cible.

---

## ✅ 5. Validation Documentaire & Recette

* **[validate_docs.py](validate_docs.py)** : Vérifie que 100 % des liens Markdown internes et ancres HTML pointent vers des cibles valides suivies dans Git.
* **[test-validation.sh](test-validation.sh)** : Exécute la suite de tests unitaires et les vérifications de conformité.
