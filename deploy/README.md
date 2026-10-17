<p align="left">
  <a href="../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.4-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <img src="https://img.shields.io/badge/IaC-Kubernetes_&_Docker_Lab-326CE5?style=flat-square&logo=kubernetes&logoColor=white" alt="IaC Kubernetes">
  <img src="https://img.shields.io/badge/Rollout-Zero--Downtime-10B981?style=flat-square" alt="Zero-Downtime">
</p>

# ☸️ Déploiement & Infrastructure-as-Code — ArcIA

> **[🏠 Accueil ArcIA](../README.md)** › **Déploiement (`deploy/`)**

Ce répertoire rassemble les définitions *Infrastructure-as-Code (IaC)* et les manifestes déclaratifs permettant de déployer ou de mettre à jour la plateforme **ArcIA** sur **n'importe quel cluster Kubernetes** (K3s, EKS, AKS, GKE, kubeadm) ou en environnement de laboratoire Docker Compose.

---

## 📂 Structure du Dossier

```text
deploy/
├── manifests/          # Manifestes Kubernetes officiels numérotés (00 à 09) + template Power User
├── litellm-lab.yaml    # Configuration LiteLLM autonome pour le mode Docker Compose Lab
└── README.md           # Ce guide d'orientation
```

---

## 🚀 Cibles & Modes d'Exécution

| Mode | Cible | Commande de Lancement | Description |
|---|---|---|---|
| **1. Assistant Graphique & Updates** | Tout cluster Kubernetes ou Docker Lab | `.\wizard.ps1` / `./wizard.sh` | Interface web complète en **3 parcours dédiés** (Installation guidée, **mise à jour Zero-Downtime RollingUpdate**, Restauration chiffrée) avec chargement YAML contextuel. |
| **2. Déploiement Kubernetes Headless** | Tout cluster Kubernetes (namespace `arcia`) | `.\scripts\Deploy-ArcIA.ps1` / `./scripts/deploy-arcia.sh` | Applique séquentiellement les manifestes de [`deploy/manifests/`](manifests/README.md) et synchronise les ConfigMaps à chaud. |
| **3. Mode Laboratoire Local** | Poste développeur (Docker Desktop / Engine) | `docker compose -f docker-compose.lab.yml up -d` | Lance rapidement la pile locale avec `litellm-lab.yaml` pour qualifier les modèles et les skills hors cluster. |

---

## 🔗 Documentation Associée

* 📘 [ Catalogue des Manifestes Kubernetes (`deploy/manifests/README.md`)](manifests/README.md)
* 🌐 [Guide du Déploiement Universel (`docs/guides/deploiement-universel.md`)](../docs/guides/deploiement-universel.md)
* 🏛️ [Architecture Technique (`docs/architecture.md`)](../docs/architecture.md)
* 🛠️ [Runbook Quickstart (`docs/runbooks/quickstart.md`)](../docs/runbooks/quickstart.md)
