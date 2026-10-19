<p align="left">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.6.0-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
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
| `POST /sanitize` et `POST /sanitize_batch` | **Barrière 1 (Hermes Agent)** | Refuse les clés privées, kubeconfigs, CIDR, MAC et FQDN internes ; supprime irréversiblement les secrets en ligne ; pseudonymise les IPv4 et PII avec une portée privée. |
| `POST /analyze` | **Barrière 2 (LiteLLM Proxy)** | Retourne la liste structurée des entités détectées (offsets, types, scores de confiance) pour le guardrail `pre_call`. |
| `POST /anonymize` | **Barrière 2 (LiteLLM Proxy)** | Anonymise le texte à partir des résultats d'analyse avant départ vers les fournisseurs LLM Cloud. |
| `POST /deanonymize` | **Restitution au propriétaire** | Réhydrate uniquement la portée privée encore valide, sans recherche dans les autres portées. |
| `GET /healthz` | **Sondes Kubernetes** | Vérifie la disponibilité réelle de l’analyseur NLP ; un échec renvoie HTTP 503. |

---

## 🔒 Architecture « double barrière » fail-closed

1. **Barrière 1 (amont — Hermes Agent)** : Le bootstrap natif impose [`runtime_guard.py`](../hermes/runtime_guard.py), qui utilise [`plugin.py`](../hermes/plugin.py) pour appeler `/sanitize` ou `/sanitize_batch` avant la persistance SQLite et les appels LLM. Le chargement ne dépend pas des replis d’extensions.
2. **Barrière 2 (aval — LiteLLM Proxy)** : [`05-litellm.yaml`](../../deploy/manifests/05-litellm.yaml) applique le guardrail `presidio` (`pre_call`, `default_on: true`) aux inférences Simple et Agentic. `/analyze` et `/anonymize` refusent aussi les secrets d’infrastructure.

### 🔗 Références associées
* 🛡️ [Guide Confidentialité Presidio DLP](../../docs/guides/confidentialite-presidio.md)
* 📦 [Manifeste Kubernetes `03-presidio.yaml`](../../deploy/manifests/03-presidio.yaml)
