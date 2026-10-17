# Architecture ArcIA v0.4

> **Statut : Implémenté (v0.4)** · [Consulter le tableau de bord des fonctionnalités](etat-des-fonctionnalites.md)

ArcIA est la plateforme d'IA agentique souveraine d'entreprise conçue pour concilier autonomie des agents, gouvernance stricte des données et expérience utilisateur unifiée.

---

## 1. Principes Fondateurs v0.4

1. **Namespace Unifié (`arcia`)** : Déploiement centralisé dans un namespace unique simplifiant la découverte réseau (`*.arcia.svc`), le contrôle d'accès RBAC et les politiques de sécurité.
2. **Routage Hybride & Catalogue à 5 Profils Canoniques** :
   - **Flux Directs (`simple/free`, `simple/auto`)** : Acheminés directement d'Open-WebUI (et du bot Teams par défaut) vers **LiteLLM Proxy** (`:4000/v1`) pour offrir une réponse instantanée sans surcharge de boucle agentique sur les requêtes textuelles courantes.
   - **Flux Agentiques (`agentic/free`, `agentic/auto`, `agentic/expert`)** : Acheminés vers **Hermes Agent** (`:8642/v1`) pour exécuter des sessions autonomes complètes avec persistance SQLite (`state.db`), compétences partagées, analyse AST locale, recherche web et outils.
3. **Niveaux d'Autonomie Explicites (N1, N2, N3)** :
   - **N1 — Collaborateur** : Accès Open-WebUI et Microsoft Teams sur les profils `simple/free`, `simple/auto` et `agentic/free`.
   - **N2 — Expert Métier** : Accès étendu aux sessions autonomes `agentic/auto`, au RAG documentaire et à la commande `/agent` dans Teams.
   - **N3 — Power User (Double Modalité)** :
     1. **Pods Hermes Dédiés sur Kubernetes** (`scripts/arcia_poweruser.py`) : Instance personnelle isolée avec PVC `10Gi`, `SOUL.md` propre et Studio Kanban sur `/poweruser/<slug>/studio`.
     2. **Accès API Direct `/v1`** (`scripts/arcia_keys.py`) : Clé virtuelle nominative (PAT) pour connecter les IDEs locaux (VS Code, Cursor) ou outils CLI directement sur LiteLLM avec plafond budgétaire mensuel.
4. **Double Barrière DLP Presidio Fail-Closed** :
   - **Barrière 1 (Amont dans Hermes)** : Le plugin `services/hermes/plugin.py` assainit les prompts et les sorties d'outils via `http://presidio-dlp.arcia.svc:8080/sanitize` avant toute sauvegarde SQLite et avant tout appel LLM.
   - **Barrière 2 (Aval dans LiteLLM)** : Le guardrail `pre_call` (`default_on: true`) filtre systématiquement 100 % des requêtes sortant vers les fournisseurs cloud via `/analyze` et `/anonymize`. En cas d'indisponibilité du module DLP, la requête est rejetée net.
5. **Sobriété Tokenmaxing v0.4 Active (CCR + RTK + Graphify + Ponytail)** :
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
   - Route publique `/v1` protégée par middleware Traefik de limitation de débit (`RateLimit`).

---

## 2. Diagramme d'Architecture Globale

```mermaid
flowchart TD
    subgraph Utilisateurs ["👥 Utilisateurs & Entrées (Niveaux N1, N2, N3)"]
        Browser["Navigateur Web<br/>(Collaborateur N1 / Expert N2)"]
        TeamsClient["Microsoft Teams<br/>(Canaux & DM N1/N2)"]
        PowerUser["Power User N3<br/>(Pod dédié K8s ou IDE via /v1)"]
        HermesDesk["Hermes Studio Central<br/>(Kanban :9119 via SSO)"]
    end

    subgraph IngressLayer ["🌐 Ingress & Sécurité Périmétrique (assistant.example.org)"]
        Traefik["Traefik Ingress Controller<br/>(Cert-Manager TLS)"]
        ForwardAuth["ForwardAuth Middleware<br/>(OAuth2-Proxy / Entra ID)"]
        RateLimit["Middleware RateLimit (/v1)"]
    end

    subgraph ArcIANamespace ["☸️ Cluster K3s — Namespace: arcia"]
        WebUI["Open-WebUI<br/>(Port 8080 / PVC 20Gi)<br/>• Catalogue 5 profils canoniques<br/>• Routage hybride LiteLLM + Hermes"]
        TeamsBot["Teams Bot Adapter<br/>(Port 3978)<br/>• simple/auto par défaut<br/>• /agent vers Hermes"]
        HermesCore["Hermes Agent Runtime<br/>Studio (9119) & Gateway (8642)<br/>(PVC 20Gi / Plugin DLP + CCR + RTK)"]
        Presidio["Presidio DLP (Fail-Closed)<br/>(Port 8080 - Double Barrière Secrets, IP, PII)"]
        LiteLLM["LiteLLM Proxy<br/>(Port 4000 - 5 Profils, ZDR & Quotas)"]
        LiteLLMDB[("LiteLLM DB PostgreSQL<br/>(Port 5432 - Clés virtuelles & Budgets)")]
    end

    subgraph CloudLayer ["☁️ Services Externes Sécurisés"]
        OpenRouter["OpenRouter API<br/>(Free, Auto, DeepSeek V4.1 Flash - ZDR)"]
        EntraID["Microsoft Entra ID<br/>(SSO & MFA)"]
        AzureBot["Azure Bot Framework<br/>(DirectLine / Graph)"]
    end

    Browser -->|HTTPS /| Traefik
    PowerUser -->|HTTPS /v1 + PAT| Traefik
    HermesDesk -->|HTTPS /studio| Traefik
    TeamsClient -->|Webhook Teams| AzureBot
    AzureBot -->|HTTPS /api/teams/messages| Traefik

    Traefik --> ForwardAuth
    ForwardAuth -.->|Validation OIDC| EntraID
    ForwardAuth -->|Autorisé /studio| HermesCore

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

    LiteLLM <--> LiteLLMDB
    LiteLLM -->|Barrière 2 DLP /analyze + /anonymize| Presidio
    LiteLLM -->|Inférence Cloud Sécurisée ZDR| OpenRouter
```

---

<a id="carte-du-dépôt"></a>
## 3. Cartographie des Composants & Ports (v0.4)

| Composant | Image Docker / Runtime | Port Interne | Exposition Ingress | Persistance | Rôle |
|---|---|---|---|---|---|
| **Open-WebUI** | `ghcr.io/open-webui/open-webui:v0.5.10` | `8080` | `/` (SSO O365 / Admin local) | PVC 20Gi (`open-webui-pvc`) | Interface web conversationnelle hybride connectée à LiteLLM (`:4000`) et Hermes (`:8642`) |
| **Hermes Studio** | `nousresearch/hermes-agent:v0.2.0` | `9119` | `/studio` (Protégé SSO) | PVC 20Gi (`hermes-user-pvc`) | Observabilité Kanban, sessions, multi-agents |
| **Hermes Gateway** | `nousresearch/hermes-agent:v0.2.0` | `8642` | `/gateway` (Protégé PAT) | Partagé PVC 20Gi (`state.db`) | Serveur API `/v1` (`agentic/*`) avec plugin DLP/CCR/RTK & WebSocket Desktop |
| **Teams Bot Adapter** | `python:3.11-slim` + BotBuilder | `3978` | `/api/teams/messages` | Stateless | Passerelle Microsoft Teams (`simple/auto` par défaut, `/agent` vers Hermes `agentic/auto`) |
| **LiteLLM Proxy** | `ghcr.io/berriai/litellm:main-v1.61.16` | `4000` | `/v1` (Public PAT + RateLimit) | Stateless | Passerelle LLM, catalogue 5 profils, fallbacks, guardrail DLP et clés virtuelles |
| **LiteLLM DB** | `postgres:16-alpine` | `5432` | Interne cluster | PVC 10Gi (`litellm-db-pvc`) | Base relationnelle des clés virtuelles, des équipes et de la comptabilité |
| **Presidio DLP** | `python:3.11-slim` + spaCy fr/en | `8080` | Interne cluster | Stateless | Caviardage systématique fail-closed des secrets, IP et PII (`/sanitize`, `/analyze`, `/anonymize`) |
| **NetworkPolicy** | `networking.k8s.io/v1` | N/A | Interne cluster | N/A | Isolation réseau périmétrique et intra-cluster (Default DenyAll) |
| **OAuth2-Proxy** | `quay.io/oauth2-proxy/oauth2-proxy:v7.6.0` | `4180` | Middleware Traefik | Stateless | Validation SSO OIDC avec Entra ID (`/oauth2/auth`) |

---

## 4. Documentation par Domaine

Pour approfondir chaque brique :
- [État des Fonctionnalités & Traçabilité Audit](etat-des-fonctionnalites.md)
- [Moteur d'Agents Hermes, Studio & Power Users](guides/hermes-agent.md)
- [Chaîne de Routage IA & Cycle de Vie d'une Requête](guides/chaine-de-routage.md)
- [Passerelle d'Inférence d'Entreprise LiteLLM](guides/inference-litellm.md)
- [Gouvernance & Confidentialité Presidio DLP](guides/confidentialite-presidio.md)
- [Sobriété Tokenmaxing v0.4 (CCR & RTK)](guides/tokenmaxing.md)
- [Portail Collaborateur Open-WebUI & SSO Entra ID](guides/portail-webui-entraid.md)
- [Intégration Microsoft Teams](guides/integration-teams.md)
- [Catalogue de Compétences Partagées (Skills)](guides/skills.md)
- [Outillage Agentique & Sobriété (Ponytail, Graphify, Public-APIs)](guides/outillage-builder.md)
- [Moteur de Déploiement Universel Kubernetes](guides/deploiement-universel.md)
- [Infrastructure K3s & Exploitation](guides/infrastructure-k3s.md)
