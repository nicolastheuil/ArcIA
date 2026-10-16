# Versions et compatibilités — ArcIA v0.3

Ce document consigne les versions officielles et images de conteneurs retenues et déployées dans le socle **ArcIA v0.3**.

---

## Composants Déployés sur le Harness

| Composant | Image / Runtime | Version | Port / Protocole | Rôle dans l'Architecture |
|---|---|---|---|---|
| **Traefik Ingress** | Chart Helm officiel K3s | Traefik v3.x | 80, 443 (HTTP/HTTPS) | Contrôleur d'Ingress périmétrique, terminaison TLS Let's Encrypt, routage `/v1` |
| **Cert-Manager** | `quay.io/jetstack/cert-manager-controller` | v1.16.1 | Interne K3s | Gestionnaire automatique de certificats ACME Let's Encrypt (HTTP-01) |
| **OAuth2-Proxy** | `quay.io/oauth2-proxy/oauth2-proxy:v7.6.0` | v7.6.0 | 4180 (HTTP) | Middleware ForwardAuth Traefik pour l'authentification SSO Microsoft Entra ID |
| **Open-WebUI** | `ghcr.io/open-webui/open-webui:main` | v0.5+ | 8080 (HTTP) | Portail conversationnel web grand public, SSO OIDC, Direct Connections désactivées |
| **Hermes Agent** | `docker.io/arcia/hermes-agent:v0.3` | v0.3 | 9119 (Studio), 8642 (Gateway) | Moteur d'agents autonomes, configuration native `~/.hermes/config.yaml` |
| **LiteLLM Proxy** | `ghcr.io/berriai/litellm:main-latest` | v1.50+ | 4000 (HTTP) | Passerelle d'inférence d'entreprise, 3 tiers canoniques, ZDR forcé, hook Presidio |
| **LiteLLM Database** | `postgres:16-alpine` | 16.x | 5432 (TCP) | Base relationnelle PostgreSQL pour le suivi comptable, virtual keys (PAT) et budgets |
| **Presidio DLP** | `python:3.11-slim` + FastAPI | 2.2.354 | 8080 (HTTP) | Caviardage et anonymisation pré-inférence (PII, secrets, clés d'API) en mode fail-closed |
| **Teams Bot Adapter** | `python:3.11-slim` + BotBuilder | v4 SDK | 3978 (HTTP) | Adaptateur Webhook Microsoft Teams (DM 1:1 et mentions de canaux) |
| **OmniRoute** | *Retiré en v0.3* | — | — | Remplacé par LiteLLM Proxy unifié (simplification opérationnelle) |
| **K3s** | Binaire officiel lightweight Kubernetes | v1.31+ | 6443 (API) | Socle d'orchestration Kubernetes haute disponibilité |
| **Debian** | Image officielle generic cloud | Debian 13 (Trixie) | OS hôte VM | Système d'exploitation des nœuds du cluster |

---

## Verrouillage et Reproductibilité

1. **Images et Registres Officiels** : Toutes les images proviennent des registres de référence (`ghcr.io`, `quay.io`, `docker.io`).
2. **Déploiement Déterministe** : Les manifests sont appliqués dans l'ordre strict de dépendance par `scripts/deploy.py` ou via Kustomize (`deploy/overlays/prod` et `deploy/overlays/lab`).
3. **Absence de Dépendances Mortes** : Les anciens composants v0.1 (Keycloak local, CNPG PostgreSQL pgvector, NGINX standalone) et v0.2 (OmniRoute standalone, tokenmaxing configmap tiers) ont été retirés du harness d'exploitation.

