# Architecture ArcIA v0.5.2

> **Statut : Implémenté (v0.5.2)** · [Consulter le tableau de bord des fonctionnalités](etat-des-fonctionnalites.md)

ArcIA est la plateforme d'IA agentique d'entreprise conçue pour concilier autonomie des agents, gouvernance stricte des données et expérience utilisateur unifiée sur n'importe quel cluster Kubernetes (ou en mode Lab Docker).

---

## 1. Principes fondateurs v0.5.2

1. **Namespace Unifié (`arcia`)** : Déploiement centralisé dans un namespace unique simplifiant la découverte réseau (`*.arcia.svc`), le contrôle d'accès RBAC et les politiques de sécurité.
2. **Routage Hybride & Catalogue à 5 Profils Canoniques** :
   - **Flux Directs (`simple/free`, `simple/auto`)** : Acheminés directement d'Open-WebUI (et du bot Teams par défaut) vers **LiteLLM Proxy** (`:4000/v1`) pour offrir une réponse instantanée sans surcharge de boucle agentique sur les requêtes textuelles courantes.
   - **Flux Agentiques (`agentic/free`, `agentic/auto`, `agentic/expert`)** : Acheminés vers **Hermes Agent** (`:8642/v1`) pour exécuter des sessions autonomes complètes avec persistance SQLite (`state.db`), compétences partagées, analyse AST locale, recherche web et outils.
3. **Deux Profils Utilisateurs Clairs** :
   - **Utilisateurs Standards** : Accès à **Open-WebUI** sur l'ensemble des profils **Simple** (`simple/free`, `simple/auto`) et **Agentic** (`agentic/free`, `agentic/auto`, `agentic/expert`), ainsi qu'au bot **Microsoft Teams** (`simple/auto` et commande `/agent`).
   - **Power Users** : Accès complet à **Open-WebUI** (`simple/*` + `agentic/*`) **+ une instance Hermes en Pod dédié sur Kubernetes** (`.\scripts\Spawn-PowerUser.ps1`) disposant d'un PVC `10Gi` isolé, d'une `SOUL.md` propre et d'un Studio Kanban personnel (`/poweruser/<slug>/studio`).
4. **Double Barrière DLP Presidio Fail-Closed** :
   - **Barrière 1 (Amont dans Hermes)** : Le plugin `services/hermes/plugin.py` assainit les prompts et les sorties d'outils via `http://presidio-dlp.arcia.svc:8080/sanitize` avant toute sauvegarde SQLite et avant tout appel LLM.
   - **Barrière 2 (Aval dans LiteLLM)** : Le guardrail `pre_call` (`default_on: true`) filtre systématiquement 100 % des requêtes sortant vers les fournisseurs cloud via `/analyze` et `/anonymize`. En cas d'indisponibilité du module DLP, la requête est rejetée net.
5. **Sobriété Tokenmaxing Active (CCR + RTK + Graphify + Ponytail)** :
   - **CCR (Compress-Cache-Retrieve)** : Compression réversible des fichiers et résultats JSON volumineux (> 8 Ko) avec cache mémoire SHA-256 privé et restitution paginée (`arcia_compress_json_file`, `arcia_restore_tool_result`).
   - **RTK** : Réécriture et compaction bornée des commandes `git log`.
   - **Graphify & Ponytail** : Cartographie AST locale sans consommation de tokens et échelle de décision YAGNI.
6. **Packaging Microservices Sans Duplication** :
   - Le code source de référence vit exclusivement dans `services/presidio/app.py`, `services/teams/app.py` et `services/hermes/plugin.py` (accompagnés de leurs `Dockerfile` respectifs).
   - Le moteur `scripts/deploy.py` (`sync_service_configmaps`) synchronise dynamiquement ces fichiers dans les ConfigMaps Kubernetes (`presidio-code`, `teams-bot-code`, `hermes-governance-plugin`).
7. **Verrouillage Strict du Portail Open-WebUI & Zéro Fuite BYOK** :
   - Connexions directes navigateur-fournisseur désactivées (`ENABLE_DIRECT_CONNECTIONS=false`), auto-inscription publique fermée (`ENABLE_SIGNUP=false`), rôle par défaut `user` (`DEFAULT_USER_ROLE=user`), contrôle d'accès aux modèles activé (`BYPASS_MODEL_ACCESS_CONTROL=false`) et authentification obligatoire (`WEBUI_AUTH=true`).
8. **Isolation Réseau (NetworkPolicies) & RateLimiting** :
   - Politique `DenyAll` par défaut dans le namespace `arcia` n'autorisant que les flux légitimes (WebUI vers LiteLLM `:4000` et Hermes `:8642`, Teams Bot vers LiteLLM `:4000` et Hermes `:8642`, Hermes vers Presidio `:8080`, LiteLLM `:4000` et HTTPS `:443`, LiteLLM vers Presidio `:8080` et PostgreSQL `:5432`).
   - Route `/v1` protégée par middleware Traefik de limitation de débit (`RateLimit`).

---

## 2. Diagramme d'architecture globale

```mermaid
flowchart TD
    subgraph Utilisateurs ["👥 Profils Utilisateurs"]
        StdUser["Utilisateur Standard<br/>(Open-WebUI Simple + Agentic & Teams)"]
        PowerUser["Power User<br/>(Open-WebUI + Pod Hermes dédié K8s)"]
        HermesDesk["Hermes Studio Central<br/>(Kanban :9119 via SSO)"]
    end

    subgraph IngressLayer ["🌐 Ingress & Sécurité Périmétrique (assistant.example.org)"]
        Traefik["Ingress Controller<br/>(Cert-Manager TLS)"]
        ForwardAuth["ForwardAuth Middleware<br/>(OAuth2-Proxy / Entra ID)"]
        RateLimit["Middleware RateLimit (/v1)"]
    end

    subgraph ArcIANamespace ["☸️ Cluster Kubernetes — Namespace: arcia"]
        WebUI["Open-WebUI<br/>(Port 8080 / PVC 20Gi)<br/>• Catalogue 5 profils canoniques<br/>• Routage hybride LiteLLM + Hermes"]
        TeamsBot["Teams Bot Adapter<br/>(Port 3978)<br/>• simple/auto par défaut<br/>• /agent vers Hermes"]
        HermesCore["Hermes Agent Runtime<br/>Studio (9119) & Gateway (8642)<br/>(PVC 20Gi / Plugin DLP + CCR + RTK)"]
        HermesPU["Pods Hermes Power Users<br/>(/poweruser/slug/studio + PVC 10Gi)"]
        Presidio["Presidio DLP (Fail-Closed)<br/>(Port 8080 - Double Barrière Secrets, IP, PII)"]
        LiteLLM["LiteLLM Proxy<br/>(Port 4000 - 5 Profils, ZDR & Quotas)"]
        LiteLLMDB[("LiteLLM DB PostgreSQL<br/>(Port 5432 - Clés virtuelles & Budgets)")]
    end

    subgraph CloudLayer ["☁️ Services Externes Sécurisés"]
        OpenRouter["OpenRouter API<br/>(Free, Auto, DeepSeek V4.1 Flash - ZDR)"]
        EntraID["Microsoft Entra ID<br/>(SSO & MFA)"]
        AzureBot["Azure Bot Framework<br/>(DirectLine / Graph)"]
    end

    StdUser -->|HTTPS /| Traefik
    PowerUser -->|HTTPS /poweruser/slug/studio| Traefik
    HermesDesk -->|HTTPS /studio| Traefik
    StdUser -->|Webhook Teams| AzureBot
    AzureBot -->|HTTPS /api/teams/messages| Traefik

    Traefik --> ForwardAuth
    ForwardAuth -.->|Validation OIDC| EntraID
    ForwardAuth -->|Autorisé /studio| HermesCore
    ForwardAuth -->|Autorisé /poweruser/slug| HermesPU

    Traefik --> RateLimit
    RateLimit -->|Inférence /v1| LiteLLM

    Traefik -->|Accès Portail /| WebUI
    Traefik -->|Bypass Auth Webhook| TeamsBot

    WebUI -->|Chat Direct simple/* :4000| LiteLLM
    WebUI -->|Session Agentique agentic/* :8642| HermesCore
    TeamsBot -->|Chat Direct simple/auto :4000| LiteLLM
    TeamsBot -->|Mission /agent :8642| HermesCore

    HermesCore -->|Barrière 1 DLP /sanitize| Presidio
    HermesCore -->|Inférence LLM :4000| LiteLLM
    HermesCore -->|Outils Web HTTPS :443| CloudLayer
    HermesPU -->|Barrière 1 DLP /sanitize| Presidio
    HermesPU -->|Inférence LLM :4000| LiteLLM

    LiteLLM <--> LiteLLMDB
    LiteLLM -->|Barrière 2 DLP /analyze + /anonymize| Presidio
    LiteLLM -->|Inférence Cloud Sécurisée ZDR| OpenRouter
```

---

<a id="carte-du-dépôt"></a>
## 3. Cartographie des composants et ports (v0.5.2)

| Composant | Image Docker / Runtime | Port Interne | Exposition Ingress | Persistance | Rôle |
|---|---|---|---|---|---|
| **Open-WebUI** | `ghcr.io/open-webui/open-webui:v0.5.10` | `8080` | `/` (SSO O365 / Admin local) | PVC 20Gi (`open-webui-pvc`) | Interface web conversationnelle hybride connectée à LiteLLM (`:4000`) et Hermes (`:8642`) |
| **Hermes Studio** | `nousresearch/hermes-agent:v0.2.0` | `9119` | `/studio` (Protégé SSO) | PVC 20Gi (`hermes-user-pvc`) | Observabilité Kanban, sessions, multi-agents |
| **Hermes Gateway** | `nousresearch/hermes-agent:v0.2.0` | `8642` | `/gateway` (Protégé PAT) | Partagé PVC 20Gi (`state.db`) | Serveur API `/v1` (`agentic/*`) avec plugin DLP/CCR/RTK & WebSocket Desktop |
| **Pods Power Users** | `nousresearch/hermes-agent:v0.2.0` | `9119` / `8642` | `/poweruser/<slug>/studio` | PVC 10Gi (`hermes-user-<slug>-pvc`) | Instance Hermes dédiée par Power User (`.\scripts\Spawn-PowerUser.ps1`) |
| **Teams Bot Adapter** | `python:3.11-slim` + BotBuilder | `3978` | `/api/teams/messages` | Stateless | Passerelle Microsoft Teams (`simple/auto` par défaut, `/agent` vers Hermes `agentic/auto`) |
| **LiteLLM Proxy** | `ghcr.io/berriai/litellm:main-v1.72.6-stable` | `4000` | `/v1` (PAT + RateLimit) | Stateless | Passerelle LLM, catalogue profils, fallbacks, guardrail DLP, gestionnaire d'erreurs convivial et clés virtuelles |
| **LiteLLM DB** | `postgres:16-alpine` | `5432` | Interne cluster | PVC 10Gi (`litellm-db-pvc`) | Base relationnelle des clés virtuelles, des équipes et de la comptabilité |
| **Presidio DLP** | `python:3.11-slim` + spaCy fr/en | `8080` | Interne cluster | Stateless | Caviardage systématique fail-closed des secrets, IP et PII (`/sanitize`, `/analyze`, `/anonymize`) |
| **NetworkPolicy** | `networking.k8s.io/v1` | N/A | Interne cluster | N/A | Isolation réseau périmétrique et intra-cluster (Default DenyAll) |
| **OAuth2-Proxy** | `quay.io/oauth2-proxy/oauth2-proxy:v7.8.1` | `4180` | Middleware Traefik | Stateless | Validation SSO OIDC avec Entra ID (`/oauth2/auth`) |

---

## 4. Documentation par domaine

Pour approfondir chaque brique :
- [État des Fonctionnalités & Traçabilité](etat-des-fonctionnalites.md)
- [Moteur d'Agents Hermes, Studio & Power Users](guides/hermes-agent.md)
- [Chaîne de Routage IA & Cycle de Vie d'une Requête](guides/chaine-de-routage.md)
- [Passerelle d'Inférence d'Entreprise LiteLLM](guides/inference-litellm.md)
- [Gouvernance & Confidentialité Presidio DLP](guides/confidentialite-presidio.md)
- [Sobriété Tokenmaxing (CCR & RTK)](guides/tokenmaxing.md)
- [Portail Collaborateur Open-WebUI & SSO Entra ID](guides/portail-webui-entraid.md)
- [Intégration Microsoft Teams](guides/integration-teams.md)
- [Catalogue de Compétences Partagées (Skills)](guides/skills.md)
- [Outillage Agentique & Sobriété (Ponytail, Graphify, Public-APIs)](guides/outillage-builder.md)
- [Moteur de Déploiement Universel Kubernetes](guides/deploiement-universel.md)
- [Infrastructure Kubernetes & Exploitation](guides/infrastructure-k3s.md)
