# Microservices Applicatifs & Composants Dédiés — ArcIA

Ce dossier regroupe les codebases et définitions de conteneurs pour les microservices personnalisés développés spécifiquement pour la plateforme ArcIA.

## Structure des Services

```
services/
├── hermes/     # Plugin Tokenmaxing ArcIA et personnalisations pour le moteur Hermes Agent
├── presidio/   # Passerelle FastAPI Presidio DLP (détection et caviardage de PII, tokens et secrets)
├── teams/      # Adaptateur bot interactif Microsoft Teams (BotBuilder SDK)
└── README.md   # Ce guide d'orientation
```

## Présentation des Microservices

| Service | Répertoire | Runtime / Stack | Rôle dans l'Architecture |
|---|---|---|---|
| **Hermes Agent Runtime** | [hermes/](hermes/README.md) | Python 3.11 + Hermes CLI v0.2 | Moteur d'agents, Studio Kanban (port 9119), Gateway Desktop (port 8642) et plugin Tokenmaxing. |
| **Presidio DLP Sanitizer** | [presidio/](presidio/README.md) | FastAPI / Python 3.11 + Presidio | Caviardage souverain des données confidentielles avant sortie vers les modèles d'inférence externes. |
| **Microsoft Teams Bot** | [teams/](teams/README.md) | Python 3.11 + BotBuilder aiohttp | Passerelle de discussion interactive dans Microsoft Teams (conversations 1:1 et mentions de canal). |

## Cycle de Vie & Déploiement

Ces services sont conteneurisés et déployés dans le cluster K3s via les manifests de [deploy/manifests/](../deploy/manifests/README.md).
Pour les tests locaux hors Kubernetes, consulter [docker-compose.lab.yml](../docker-compose.lab.yml).
