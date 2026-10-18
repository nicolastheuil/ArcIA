<p align="left">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.5.1-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <a href="../README.md"><img src="https://img.shields.io/badge/🧩_Services-Microservices-0C2762?style=flat-square" alt="Services"></a>
  <img src="https://img.shields.io/badge/DLP_Shield-Microsoft_Presidio-FA7B4E?style=flat-square" alt="Presidio DLP">
</p>

# 🛡️ Service Presidio DLP sanitizer — ArcIA

> **[🏠 Accueil ArcIA](../../README.md)** › **[🧩 Microservices](../README.md)** › **Presidio DLP (`services/presidio/`)**

Ce dossier contient l'implémentation de référence du bouclier de détection et d'anonymisation de données sensibles **Presidio DLP**, propulsé par FastAPI, Microsoft Presidio et spaCy (`fr_core_news_sm` + `en_core_web_sm`).

---

## 🔌 Points de terminaison API exposés (`app.py`)

Le fichier **[app.py](app.py)** constitue la source unique du microservice (synchronisée à chaud dans le ConfigMap `presidio-code`) et [Dockerfile](Dockerfile) définit l'image autonome :

| Endpoint HTTP | Consommateur principal | Fonctionnement |
|---|---|---|
| `POST /sanitize`<br/>*(et `/v1/sanitize`)* | **Barrière 1 (Hermes Agent)** | Détecte et remplace les secrets techniques (`sk-...`, `ghp_...`, `AKIA...`, tokens Bearer, clés PEM), adresses IPv4 et PII (`fr`/`en` : emails, téléphones, IBAN, CB, personnes) par des balises neutres (`[SECRET_REMOVED]`, `[ARCIA_<TYPE>_n]`). |
| `POST /analyze` | **Barrière 2 (LiteLLM Proxy)** | Retourne la liste structurée des entités détectées (offsets, types, scores de confiance) pour le guardrail `pre_call`. |
| `POST /anonymize` | **Barrière 2 (LiteLLM Proxy)** | Anonymise le texte à partir des résultats d'analyse avant départ vers les fournisseurs LLM Cloud. |
| `GET /healthz`<br/>*(et `/health`)* | **Sondes Kubernetes** | Contrôle de disponibilité utilisé par les `readinessProbe` et `livenessProbe` lors des RollingUpdates Zero-Downtime. |

---

## 🔒 Architecture « double barrière » fail-closed

1. **Barrière 1 (Amont — Hermes Agent)** : [`services/hermes/plugin.py`](../hermes/plugin.py) invoque `POST /sanitize` en mode *fail-closed* avant toute persistance SQLite (`state.db`) et tout appel LLM.
2. **Barrière 2 (Aval — LiteLLM Proxy)** : [`deploy/manifests/05-litellm.yaml`](../../deploy/manifests/05-litellm.yaml) applique le guardrail `presidio` (`pre_call`, `default_on: true`) sur l'ensemble des flux directs (`simple/*`, Teams, `/v1`).

### 🔗 Références associées
* 🛡️ [Guide Confidentialité Presidio DLP](../../docs/guides/confidentialite-presidio.md)
* 📦 [Manifeste Kubernetes `03-presidio.yaml`](../../deploy/manifests/03-presidio.yaml)
