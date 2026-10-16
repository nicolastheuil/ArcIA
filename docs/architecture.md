# Architecture ArcIA v0.3

> **Statut : Implémenté (v0.3)** · [Consulter le tableau de bord des fonctionnalités](etat-des-fonctionnalites.md)

ArcIA est la plateforme d'IA agentique souveraine d'entreprise conçue pour concilier autonomie des agents, gouvernance stricte des données et expérience utilisateur unifiée.

---

## 1. Principes Fondateurs v0.3

1. **Namespace Unifié (`arcia`)** : Déploiement centralisé dans un namespace unique simplifiant la découverte réseau (`*.arcia.svc`), le contrôle d'accès RBAC et les politiques de sécurité.
2. **Niveaux d'Autonomie Explicites (N1, N2, N3)** :
   - **N1 — Collaborateur & N2 — Expert (Open-WebUI)** : Open-WebUI est strictement le frontal conversationnel. Tous les chats sont acheminés exclusivement vers **Hermes Agent** (`:8642`). Les collaborateurs disposent des 3 paliers génériques (`arcia/free`, `arcia/auto` par défaut, `arcia/expert` avec sélection dynamique par `/model`), exécutés avec toute la puissance outillée (skills, AST, web, bash, RAG).
   - **N3 — Power User** : Instances Hermes complètes et dédiées spawnées à la demande sur Kubernetes (aucun agent local sur PC), avec PVC 10Gi, `SOUL.md` personnalisée, Studio Kanban individuel et jeton nominatif LiteLLM (PAT).
3. **Bouclier DLP Presidio Fail-Closed** : Aucun prompt ne sort vers un modèle cloud externe sans caviardage strict des adresses IP, secrets techniques, téléphones, IBAN et PII. En cas d'indisponibilité du module DLP, la requête est rejetée net.
4. **Passerelle d'Inférence Unique & Base Comptable (`litellm-db`)** :
   - Catalogue virtuel d'entreprise strict à 3 paliers : `arcia/free` (gratuit/qualification), `arcia/auto` (défaut intelligent), `arcia/expert` (raisonnement approfondi).
   - Zéro Rétention de Données (ZDR) et `drop_params: true` pour harmonisation universelle des paramètres.
   - Persistance PostgreSQL des clés virtuelles, budgets et équipes.
5. **Intégration Microsoft Teams Native** : Bot applicatif certifié Bot Framework connecté sur la passerelle pour les conversations 1:1 et canaux d'équipe.
6. **Suppression des Fuites BYOK & Zéro Bypass Hermes** : Les connexions directes navigateur-fournisseur sont désactivées (`ENABLE_DIRECT_CONNECTIONS=false`). Open-WebUI n'a aucune permission réseau directe vers LiteLLM.
7. **Verrouillage Strict du Portail Open-WebUI** : Inscription publique désactivée (`ENABLE_SIGNUP=false`), rôle par défaut fixé en utilisateur standard (`DEFAULT_USER_ROLE=user`), contrôle des modèles activé (`BYPASS_MODEL_ACCESS_CONTROL=false`), et authentification obligatoire (`WEBUI_AUTH=true`). Seuls les utilisateurs authentifiés via Microsoft 365 / Entra ID SSO ou des comptes administrateurs créés manuellement peuvent accéder au portail.
8. **Isolation Réseau & Bouclier Inter-Pods (NetworkPolicies)** : Politique `DenyAll` par défaut limitant strictement les communications intra-namespace aux flux autorisés (WebUI vers Hermes :8642 uniquement, Hermes vers LiteLLM :4000 et egress HTTPS :443, LiteLLM vers Presidio et PostgreSQL).
9. **Protection Ingress & Limitation de Débit** : Séparation de la route `/v1` d'inférence protégée par un middleware Traefik de RateLimiting pour éviter tout déni de service ou surconsommation budgétaire.

---

## 2. Diagramme d'Architecture Globale

```mermaid
flowchart TD
    subgraph Utilisateurs ["👥 Utilisateurs & Entrées (Niveaux N1, N2, N3)"]
        Browser["Navigateur Web<br/>(Collaborateur N1 / Expert N2)"]
        TeamsClient["Microsoft Teams<br/>(Canaux & DM N1)"]
        PowerUser["Power User N3<br/>(Pod Hermes dédié K8s + PVC 10Gi)"]
        HermesDesk["Hermes Studio Central<br/>(Kanban :9119 via SSO)"]
    end

    subgraph IngressLayer ["🌐 Ingress & Sécurité Périmétrique (assistant.example.org)"]
        Traefik["Traefik Ingress Controller<br/>(Cert-Manager TLS)"]
        ForwardAuth["ForwardAuth Middleware<br/>(OAuth2-Proxy / Entra ID)"]
        RateLimit["Middleware RateLimit (/v1)"]
    end

    subgraph ArcIANamespace ["☸️ Cluster K3s — Namespace: arcia"]
        WebUI["Open-WebUI<br/>(Port 8080 / PVC 50Gi)<br/>• Catalogue 3 modèles filtré<br/>• Connexion exclusive Hermes"]
        TeamsBot["Teams Bot Adapter<br/>(Port 3978)"]
        HermesCore["Hermes Agent Runtime<br/>Studio (9119) & Gateway (8642)<br/>(PVC 20Gi / SQLite state.db)"]
        Presidio["Presidio DLP (Fail-Closed)<br/>(Port 8080 - Caviardage Secrets, IP, PII)"]
        LiteLLM["LiteLLM Proxy<br/>(Port 4000 - Inférence, Quotas & DropParams)"]
        LiteLLMDB[("LiteLLM DB PostgreSQL<br/>(Port 5432 - Clés virtuelles & Budgets)")]
    end

    subgraph CloudLayer ["☁️ Services Externes Sécurisés"]
        OpenRouter["OpenRouter API<br/>(Free, Auto, Expert / Wildcard)"]
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

    WebUI -->|Sessions & Prompts Agentiques :8642 (Zéro Bypass)| HermesCore
    TeamsBot -->|Requête Inférence| LiteLLM
    HermesCore -->|Inférence LLM :4000| LiteLLM
    HermesCore -->|Outils Web HTTPS :443 (API Gouv, Search...)| CloudLayer

    LiteLLM <--> LiteLLMDB
    LiteLLM -->|Filtrage Pré-Inférence Fail-Closed| Presidio
    Presidio -->|Prompt Caviardé| LiteLLM
    LiteLLM -->|Inférence Cloud Sécurisée| OpenRouter
```

---

<a id="carte-du-dépôt"></a>
## 3. Cartographie des Composants & Ports (v0.3)

| Composant | Image Docker / Runtime | Port Interne | Exposition Ingress | Persistance | Rôle |
|---|---|---|---|---|---|
| **Open-WebUI** | `ghcr.io/open-webui/open-webui:main` | `8080` | `/` (SSO O365 / Admin local) | PVC 50Gi (`open-webui-pvc`) | Interface web conversationnelle connectée exclusivement à Hermes Agent (:8642) |
| **Hermes Studio** | `nousresearch/hermes-agent:latest` | `9119` | `/studio` (Protégé SSO) | PVC 20Gi (`hermes-user-pvc`) | Observabilité Kanban, sessions, multi-agents |
| **Hermes Gateway** | `nousresearch/hermes-agent:latest` | `8642` | `/gateway` (Protégé PAT) | Partagé PVC 20Gi (`state.db`) | Passerelle API :8642 /v1 (Backend exclusif Open-WebUI) & WebSocket Desktop |
| **Teams Bot Adapter** | `python:3.11-slim` + BotBuilder | `3978` | `/api/teams/messages` | Stateless | Passerelle interactive Microsoft Teams connectée sur `arcia/auto` |
| **LiteLLM Proxy** | `ghcr.io/berriai/litellm:main-v1.61.16` | `4000` | `/v1` (Public PAT + RateLimit) | Stateless | Passerelle LLM, routage 3 paliers, fallbacks et gestion des clés virtuelles |
| **LiteLLM DB** | `postgres:16-alpine` | `5432` | Interne cluster | PVC 10Gi (`litellm-db-pvc`) | Base relationnelle des clés virtuelles, des équipes et de la comptabilité |
| **Presidio DLP** | `python:3.11-slim` + spaCy fr/en | `8080` | Interne cluster | Stateless | Caviardage systématique fail-closed des secrets, IP et PII |
| **NetworkPolicy** | `networking.k8s.io/v1` | N/A | Interne cluster | N/A | Isolation réseau périmétrique et intra-cluster (Default DenyAll) |
| **OAuth2-Proxy** | `quay.io/oauth2-proxy/oauth2-proxy:v7.6.0` | `4180` | Middleware Traefik | Stateless | Validation SSO OIDC avec Entra ID (`/oauth2/auth`) |

> **Composants retirés en v0.3** :
> * **OmniRoute** : Retiré au profit du raccordement unifié LiteLLM.
> * **Plugin Tokenmaxing maison** : Retiré au profit de l'outillage standard.

---

## 4. Documentation par Domaine

Pour approfondir chaque brique :
- [État des Fonctionnalités & Traçabilité Audit](etat-des-fonctionnalites.md)
- [Moteur d'Agents Hermes & Studio](guides/hermes-agent.md)
- [Chaîne de Routage IA & Cycle de Vie d'une Requête](guides/chaine-de-routage.md)
- [Passerelle d'Inférence d'Entreprise LiteLLM](guides/inference-litellm.md)
- [Gouvernance & Confidentialité Presidio DLP](guides/confidentialite-presidio.md)
- [Portail Collaborateur Open-WebUI & SSO Entra ID](guides/portail-webui-entraid.md)
- [Intégration Microsoft Teams](guides/integration-teams.md)
- [Catalogue de Compétences Partagées (Skills)](guides/skills.md)
- [Outillage Agentique & Sobriété (Ponytail, Graphify, Public-APIs)](guides/outillage-builder.md)
- [Moteur de Déploiement Universel Kubernetes](guides/deploiement-universel.md)
- [Infrastructure K3s & Exploitation](guides/infrastructure-k3s.md)
