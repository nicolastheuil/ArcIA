# Versions et compatibilités — ArcIA v0.5.2

Ce document consigne les versions officielles et images de conteneurs retenues et déployées dans le socle **ArcIA v0.5.2**.

---

## Composants déployés sur le harness

| Composant | Image / Runtime | Version | Port / Protocole | Rôle dans l'Architecture |
|---|---|---|---|---|
| **Traefik Ingress** | Chart Helm officiel K3s | Traefik v3.x | 80, 443 (HTTP/HTTPS) | Contrôleur d'Ingress périmétrique, terminaison TLS Let's Encrypt, routage `/v1` |
| **Cert-Manager** | `quay.io/jetstack/cert-manager-controller` | v1.16.1 | Interne K3s | Gestionnaire automatique de certificats ACME Let's Encrypt (HTTP-01) |
| **OAuth2-Proxy** | `quay.io/oauth2-proxy/oauth2-proxy:v7.8.1` | v7.8.1 | 4180 (HTTP) | Middleware ForwardAuth Traefik pour l'authentification SSO Microsoft Entra ID |
| **Open-WebUI** | `ghcr.io/open-webui/open-webui:v0.5.10` | v0.5.10 | 8080 (HTTP) | Portail conversationnel hybride (`simple/*` & `agentic/*`), SSO OIDC, Direct Connections désactivées |
| **Hermes Agent** | `nousresearch/hermes-agent:v0.2.0` | v0.2.0 | 9119 (Studio), 8642 (Gateway) | Moteur d'agents autonomes, plugin DLP + CCR + RTK (`services/hermes/plugin.py`) |
| **LiteLLM Proxy** | `ghcr.io/berriai/litellm:main-v1.72.6-stable` | v1.72.6-stable | 4000 (HTTP) | Passerelle d'inférence d'entreprise, 5 profils canoniques, ZDR forcé, guardrail Presidio |
| **LiteLLM Database** | `postgres:16-alpine` | 16-alpine | 5432 (TCP) | Base relationnelle PostgreSQL pour le suivi comptable, virtual keys (PAT) et budgets |
| **Presidio DLP** | `python:3.11-slim` + FastAPI + spaCy | 2.2.355 | 8080 (HTTP) | Double barrière de caviardage pré-inférence (PII, IP, secrets) en mode fail-closed |
| **Teams Bot Adapter** | `python:3.11-slim` + BotBuilder | v4.16.0 | 3978 (HTTP) | Adaptateur Webhook Microsoft Teams (`simple/auto` par défaut, `/agent` vers Hermes) |
| **K3s** | Binaire officiel lightweight Kubernetes | v1.31+ | 6443 (API) | Socle d'orchestration Kubernetes haute disponibilité |
| **Debian** | Image officielle generic cloud | Debian 13 (Trixie) | OS hôte VM | Système d'exploitation des nœuds du cluster |

---

## Verrouillage et reproductibilité

1. **Images et Registres Officiels** : Toutes les images proviennent des registres de référence (`ghcr.io`, `quay.io`, `docker.io`) avec tags épinglés.
2. **Déploiement Déterministe** : Les manifests sont appliqués dans l'ordre strict de dépendance par [scripts/deploy.py](../../scripts/deploy.py) ou via Kustomize (`kubectl apply -k deploy/manifests/`).
3. **Zéro Duplication Microservices** : Le code source des services (`services/presidio/app.py`, `services/teams/app.py`, `services/hermes/plugin.py`) est synchronisé automatiquement en ConfigMaps par `scripts/deploy.py`.
