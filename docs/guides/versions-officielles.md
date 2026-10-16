# Versions et compatibilités — ArcIA v0.2

Ce document consigne les versions officielles et images de conteneurs retenues et déployées dans le socle **ArcIA v0.2**.

---

## Composants Déployés sur le Harness

| Composant | Image / Runtime | Version | Port / Protocole | Rôle dans l'Architecture |
|---|---|---|---|---|
| **Traefik Ingress** | Chart Helm officiel K3s | Traefik v3.x | 80, 443 (HTTP/HTTPS) | Contrôleur d'Ingress périmétrique, terminaison TLS Let's Encrypt |
| **Cert-Manager** | `quay.io/jetstack/cert-manager-controller` | v1.16.1 | Interne K3s | Gestionnaire automatique de certificats ACME Let's Encrypt (HTTP-01) |
| **OAuth2-Proxy** | `quay.io/oauth2-proxy/oauth2-proxy:v7.6.0` | v7.6.0 | 4180 (HTTP) | Middleware ForwardAuth Traefik pour l'authentification SSO Microsoft Entra ID |
| **Open-WebUI** | `ghcr.io/open-webui/open-webui:main` | v0.5+ | 8080 (HTTP) | Portail conversationnel web grand public, SSO OIDC, Direct Connections BYOK |
| **Hermes Agent** | `docker.io/arcia/hermes-agent:v0.2` | v0.2 | 9119 (Studio), 8642 (Gateway) | Moteur d'agents autonomes, Kanban Studio, Gateway WebSocket Hermes Desktop |
| **LiteLLM Proxy** | `ghcr.io/berriai/litellm:main-latest` | v1.50+ | 4000 (HTTP) | Passerelle d'inférence d'entreprise, load balancing, fallbacks, hook Presidio |
| **Presidio DLP** | `python:3.11-slim` + FastAPI | 2.2.354 | 8080 (HTTP) | Caviardage et anonymisation pré-inférence (PII, secrets, clés d'API) |
| **Teams Bot Adapter** | `python:3.11-slim` + BotBuilder | v4 SDK | 3978 (HTTP) | Adaptateur Webhook Microsoft Teams (DM 1:1 et mentions de canaux) |
| **OmniRoute** | `node:22-alpine` + OmniRoute | 3.8.51 | 20128 (API), 20129 (Admin) | Routeur multi-fournisseurs et portail d'administration LAN |
| **K3s** | Binaire officiel lightweight Kubernetes | v1.31+ | 6443 (API) | Socle d'orchestration Kubernetes haute disponibilité |
| **Debian** | Image officielle generic cloud | Debian 13 (Trixie) | OS hôte VM | Système d'exploitation des nœuds du cluster |

---

## Verrouillage et Reproductibilité

1. **Images et Registres Officiels** : Toutes les images proviennent des registres de référence (`ghcr.io`, `quay.io`, `docker.io`).
2. **Déploiement Déterministe** : Les manifests sont appliqués dans l'ordre strict de dépendance par `scripts/deploy.py` et validés par `scripts/test-validation.sh`.
3. **Absence de Dépendances Mortes** : Les anciens composants v0.1 (Keycloak local, CNPG PostgreSQL pgvector, NGINX standalone, scripts de qualification manuelle) ont été purgés du harness d'exploitation.
