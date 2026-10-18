<p align="left">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.5.1-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <a href="../README.md"><img src="https://img.shields.io/badge/🧩_Services-Microservices-0C2762?style=flat-square" alt="Services"></a>
  <img src="https://img.shields.io/badge/LiteLLM-Error_Handler-6BE7DD?style=flat-square&logoColor=050712" alt="Error Handler">
</p>

# 🛡️ Gestionnaire d'erreurs d'inférence convivial — LiteLLM Proxy

> **[🏠 Accueil ArcIA](../../README.md)** › **[🧩 Microservices](../README.md)** › **LiteLLM Error Handler (`services/litellm/`)**

Ce dossier contient le gestionnaire d'interception d'erreurs pour la passerelle **LiteLLM Proxy**, conçu pour assainir et traduire en français pédagogique les erreurs techniques des fournisseurs de modèles (OpenRouter, DeepSeek, etc.) à destination d'Open-WebUI, du bot Microsoft Teams et d'Hermes Agent.

---

## 📦 Composants du dossier

| Fichier | Rôle & Responsabilités |
|---|---|
| **[error_handler.py](error_handler.py)** | Module Python dérivant de `CustomLogger` et implémentant le hook `async_post_call_failure_hook`. |

---

## 🎯 Problème résolu

Par défaut, lorsqu'un appel à un fournisseur d'IA échoue (quota épuisé, politique de confidentialité ZDR non satisfaite, dépassement de contexte ou indisponibilité), LiteLLM renvoie l'intégralité de sa pile d'exceptions Python brute contenant :
* L'identifiant de la clé d'API (fuite de sécurité).
* Les détails internes du funnel de routage (`Filter by Data Policy`, `routing_funnel`).
* Les traces de réessais et listes de cooldown.

Le gestionnaire `error_handler.py` résout ce problème à la source :
1. **Journalisation complète côté serveur** : La trace technique reste intégralement visible dans `kubectl logs` ou `docker logs` pour l'ingénieur plateforme.
2. **Restitution assainie** : Le client (Open-WebUI ou Hermes) reçoit une `HTTPException` claire, structurée en Markdown, sans fuite d'informations sensibles.

---

## ☸️ Synchronisation et déploiement

* **Mode Lab Docker** : Monté dans `docker-compose.lab.yml` sous `/app/error_handler.py` et référencé dans `deploy/litellm-lab.yaml` via `litellm_settings.callbacks: ["error_handler.error_handler"]`.
* **Kubernetes (Production)** : Synchronisé automatiquement par [`scripts/deploy.py`](../../scripts/deploy.py) (`sync_service_configmaps`) dans le ConfigMap `litellm-error-handler` et monté dans le Pod [`deploy/manifests/05-litellm.yaml`](../../deploy/manifests/05-litellm.yaml).
