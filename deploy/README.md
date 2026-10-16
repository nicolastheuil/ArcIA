# Déploiement & Manifests Kubernetes — ArcIA

Ce dossier contient l'ensemble des définitions d'infrastructure-as-code (IaC) et manifests Kubernetes pour déployer la plateforme ArcIA sur un cluster K3s (VMware / Debian) ou tester en environnement de laboratoire.

## Structure du Dossier

```
deploy/
├── manifests/          # Manifests Kubernetes officiels numérotés pour le cluster K3s (namespace 'arcia')
├── litellm-lab.yaml    # Configuration LiteLLM autonome pour les tests en environnement de laboratoire
└── README.md           # Ce guide d'orientation
```

## Modes de Déploiement

1. **Déploiement Kubernetes de Production (Cible principale)** :
   * S'applique via le script universel `scripts/deploy.py` ou le script bash `scripts/deploy-arcia.sh`.
   * Utilise les manifests ordonnés dans [deploy/manifests/](manifests/README.md).
   * Cible : cluster 3 nœuds K3s sur VMware avec stockage partagé CSI (vSphere CNS ou local-path) dans le namespace unifié `arcia`.
2. **Mode Laboratoire Local (Docker Compose)** :
   * Permet de tester rapidement l'inférence et les outils sur un poste de travail avec [docker-compose.lab.yml](../docker-compose.lab.yml).
   * Utilise `litellm-lab.yaml` pour préconfigurer le routage des modèles sans cluster Kubernetes.

## Documentation Associée

* [Guide du Déploiement Universel](../docs/guides/deploiement-universel.md)
* [Architecture ArcIA](../docs/architecture.md)
* [Runbook Quickstart](../docs/runbooks/quickstart.md)
