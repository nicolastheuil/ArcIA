<p align="left">
  <a href="../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.4-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <img src="https://img.shields.io/badge/Microservices-Python_3.11-6BE7DD?style=flat-square&logo=python&logoColor=050712" alt="Python 3.11">
  <img src="https://img.shields.io/badge/Sync-Zero_Duplication_ConfigMaps-10B981?style=flat-square" alt="Zero Duplication">
</p>

# 🧩 Microservices Applicatifs & Plugins — ArcIA

> **[🏠 Accueil ArcIA](../README.md)** › **Microservices (`services/`)**

Ce dossier regroupe le code source de référence et les `Dockerfile` des microservices et plugins développés sur mesure pour la plateforme **ArcIA v0.4**.

---

## 🔄 Architecture « Zéro Duplication » & Hot-Sync

> [!TIP]
> Chaque microservice possède **une seule source de vérité** dans ce dossier (`app.py` / `plugin.py`).
> Lors d'un déploiement ou d'une mise à jour Zero-Downtime via `.\wizard.ps1` ou `.\scripts\Deploy-ArcIA.ps1`, la fonction `sync_service_configmaps` ([`scripts/deploy.py`](../scripts/deploy.py)) injecte automatiquement ces fichiers dans les ConfigMaps Kubernetes (`presidio-code`, `teams-bot-code`, `hermes-governance-plugin`, `litellm-error-handler`) montés par les Pods de [`deploy/manifests/`](../deploy/manifests/README.md).

---

## 🗂️ Cartographie des Microservices

```text
services/
├── hermes/     # Plugin de gouvernance DLP amont, compression CCR et compaction RTK (plugin.py)
├── litellm/    # Gestionnaire d'erreurs d'inférence user-friendly et hooks proxy (error_handler.py)
├── presidio/   # Microservice FastAPI d'anonymisation PII & secrets (app.py)
├── teams/      # Adaptateur Bot Framework Microsoft Teams (app.py)
└── README.md   # Ce guide d'orientation
```

| Microservice | Dossier | Stack Technique | Rôle dans la Chaîne ArcIA |
|---|---|---|---|
| 🤖 **Hermes Governance & CCR Plugin** | **[hermes/](hermes/README.md)** | Python 3.11 · Hermes Agent Hook | **Barrière 1 DLP** *fail-closed* (`/sanitize` avant SQLite `state.db`), compression réversible **CCR** (cache SHA-256) et compaction **RTK** `git log`. |
| 🛡️ **LiteLLM Error Handler** | **[litellm/](litellm/README.md)** | Python 3.11 · LiteLLM `CustomLogger` | **Gestionnaire d'erreurs convivial** interceptant les exceptions de passerelle (quota, ZDR, timeout) pour renvoyer des messages en français sans fuite de secrets. |
| 🛡️ **Presidio DLP Sanitizer** | **[presidio/](presidio/README.md)** | FastAPI · spaCy `fr`/`en` · Presidio | **Bouclier DLP souverain** détectant et anonymisant secrets, clés API, IP et données personnelles (`/sanitize`, `/analyze`, `/anonymize`, `/healthz`). |
| 💬 **Microsoft Teams Bot Adapter** | **[teams/](teams/README.md)** | Python 3.11 · `aiohttp` · BotBuilder | **Passerelle collaborative Microsoft 365** routant les messages Teams vers `simple/auto` par défaut et la commande `/agent` vers Hermes (`agentic/auto`). |

---

## 🧪 Tests & Qualification Locale

L'ensemble de ces microservices est couvert par la suite de tests unitaires du dépôt (`tests/test_dlp.py`, `tests/test_privacy.py`, `tests/test_teams_app.py`) exécutable via :

```bash
python -m unittest discover -s tests -v
```
