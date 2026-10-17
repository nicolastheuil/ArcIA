# Microservices Applicatifs & Composants Dédiés — ArcIA

Ce dossier regroupe les codebases et définitions de conteneurs pour les microservices personnalisés développés spécifiquement pour la plateforme ArcIA.

## Architecture Zéro Duplication (v0.4)

Chaque microservice possède **une seule source de vérité** dans ce dossier (`app.py` / `plugin.py` et `Dockerfile`).
Lors du déploiement Kubernetes, le moteur [scripts/deploy.py](../scripts/deploy.py) (`sync_service_configmaps`) synchronise automatiquement ces fichiers dans les ConfigMaps Kubernetes (`presidio-code`, `teams-bot-code`, `hermes-governance-plugin`) montés par les déploiements de [deploy/manifests/](../deploy/manifests/README.md).

## Structure des Services

```
services/
├── hermes/     # Plugin de gouvernance DLP, CCR et RTK (plugin.py + Dockerfile) pour Hermes Agent
├── presidio/   # Passerelle FastAPI Presidio DLP (app.py + Dockerfile)
├── teams/      # Adaptateur bot interactif Microsoft Teams (app.py + Dockerfile)
└── README.md   # Ce guide d'orientation
```

## Présentation des Microservices

| Service | Répertoire | Runtime / Stack | Rôle dans l'Architecture |
|---|---|---|---|
| **Hermes Governance & CCR Plugin** | [hermes/](hermes/README.md) | Python 3.11 + Hermes Agent v0.2.0 | Barrière 1 DLP fail-closed (`/sanitize`), compression réversible CCR (cache SHA-256 + `arcia_restore_tool_result`) et compaction RTK `git log`. |
| **Presidio DLP Sanitizer** | [presidio/](presidio/README.md) | FastAPI / Python 3.11 + spaCy fr/en | Caviardage souverain des secrets, adresses IP et PII (`/sanitize`, `/analyze`, `/anonymize`, `/healthz`). |
| **Microsoft Teams Bot** | [teams/](teams/README.md) | Python 3.11 + BotBuilder aiohttp | Passerelle interactive Microsoft Teams (`simple/auto` par défaut et commande `/agent` vers Hermes `agentic/auto`). |

## Cycle de Vie & Déploiement

Ces services sont déployés dans le cluster K3s via [scripts/deploy.py](../scripts/deploy.py) et les manifests de [deploy/manifests/](../deploy/manifests/README.md).
Pour les tests locaux hors Kubernetes, consulter [docker-compose.lab.yml](../docker-compose.lab.yml).
