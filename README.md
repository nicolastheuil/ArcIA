<p align="center">
  <img src="assets/branding/banner-github-dark.svg" alt="ArcIA Enterprise Agentic AI Platform" width="100%">
</p>

<p align="center">
  <a href="docs/architecture.md"><img src="https://img.shields.io/badge/ArcIA-v0.4-1659E4.svg?style=flat-square&logo=cube&logoColor=white" alt="ArcIA Version"></a>
  <a href="docs/guides/deploiement-universel.md"><img src="https://img.shields.io/badge/Kubernetes-Any%20Cluster-326CE5.svg?style=flat-square&logo=kubernetes&logoColor=white" alt="Kubernetes"></a>
  <a href="docs/guides/portail-webui-entraid.md"><img src="https://img.shields.io/badge/Portail-Open--WebUI-10B981.svg?style=flat-square&logo=chat&logoColor=white" alt="Open-WebUI"></a>
  <a href="docs/guides/hermes-agent.md"><img src="https://img.shields.io/badge/Agent%20Runtime-Hermes%20Agent-1659E4.svg?style=flat-square&logo=openai&logoColor=white" alt="Hermes Agent"></a>
  <a href="docs/guides/inference-litellm.md"><img src="https://img.shields.io/badge/Gateway-LiteLLM-0EA5E9.svg?style=flat-square&logo=serverless&logoColor=white" alt="LiteLLM Gateway"></a>
  <a href="docs/guides/confidentialite-presidio.md"><img src="https://img.shields.io/badge/DLP-Microsoft%20Presidio-6BE7DD.svg?style=flat-square&logo=shield&logoColor=050712" alt="Presidio DLP"></a>
  <a href="docs/guides/integration-teams.md"><img src="https://img.shields.io/badge/Teams-Bot%20Framework-5B5FC7.svg?style=flat-square&logo=microsoftteams&logoColor=white" alt="Microsoft Teams"></a>
</p>

<h3 align="center">Plateforme d'IA Agentique d'Entreprise</h3>

<p align="center">
  <b>Open-WebUI (Simple + Agentic) • Hermes Agent • Double Barrière DLP Presidio • LiteLLM Gateway • Tokenmaxing CCR</b>
</p>

<p align="center">
  <a href="#-démarrage-rapide"><b>🚀 Démarrage Rapide</b></a> •
  <a href="#-architecture-globale"><b>🏛️ Architecture</b></a> •
  <a href="#-fonctionnalités-clés"><b>🌟 Fonctionnalités</b></a> •
  <a href="#-profils-utilisateurs"><b>👥 Profils Utilisateurs</b></a> •
  <a href="docs/README.md"><b>📖 Documentation</b></a>
</p>

---

**ArcIA** est un socle d'IA agentique d'entreprise déployable sur **n'importe quel cluster Kubernetes** (K3s, EKS, AKS, GKE, kubeadm) ou en local via Docker Compose. Il fédère un portail conversationnel moderne, un moteur d'agents autonomes, un bouclier DLP et une passerelle d'inférence unifiée :

* **Pour les Utilisateurs Standards** : accès au portail **Open-WebUI** avec SSO Microsoft Entra ID sur l'ensemble des profils **Simple** (`simple/free`, `simple/auto`) et **Agentic** (`agentic/free`, `agentic/auto`, `agentic/expert`), ainsi qu'au bot **Microsoft Teams** (`simple/auto` par défaut, `/agent` pour déléguer une mission à Hermes).
* **Pour les Power Users** : accès complet à **Open-WebUI** (`simple/*` + `agentic/*`) **+ une instance Hermes Agent en Pod dédié sur Kubernetes** (`/poweruser/<slug>/studio` avec volume persistant `10Gi` isolé et `SOUL.md` personnalisée).
* **Pour la DSI & le RSSI** : une **double barrière DLP** (**Microsoft Presidio**) en mode *fail-closed* (en amont dans Hermes avant persistance SQLite et en aval dans LiteLLM avant sortie cloud), et une passerelle d'inférence centralisée (**LiteLLM**) avec base comptable PostgreSQL (`litellm-db`) et Zéro Rétention de Données (`zdr: true`).

---

## 🌟 Fonctionnalités Clés

Chaque brique majeure d'ArcIA fait l'objet d'un guide technique dédié :

### 💬 1. Interfaces Collaborateurs & Routage Hybride
* **Portail Web d'Entreprise (Open-WebUI)** : Interface conversationnelle avec gestion documentaire RAG (ChromaDB), authentification SSO Microsoft Entra ID (OIDC / OAuth2-Proxy) et double raccordement d'infrastructure :
  * **Flux Directs (`simple/*`)** : connectés à LiteLLM (`:4000/v1`) pour les échanges rapides sans latence de boucle agentique.
  * **Flux Agentiques (`agentic/*`)** : connectés à Hermes Agent (`:8642/v1`) pour les missions complexes nécessitant outils, code, skills et mémoire persistante.
  * *Gouvernance* : connexions directes navigateur désactivées (`ENABLE_DIRECT_CONNECTIONS=false`), garantissant le passage de 100 % des flux par le bouclier DLP et la passerelle d'entreprise.  
  👉 *Détail complet :* [Guide Portail Open-WebUI & Entra ID](docs/guides/portail-webui-entraid.md)
* **Intégration Microsoft Teams Native** : Bot applicatif Bot Framework permettant d'interagir avec ArcIA en conversation privée (DM 1:1) ou par mention `@ArcIA` dans les canaux d'équipe (`simple/auto` en réponse rapide, ou commande `/agent <mission>` routée vers `agentic/auto`).  
  👉 *Détail complet :* [Guide Intégration Microsoft Teams](docs/guides/integration-teams.md)

### 🤖 2. Moteur d'Agents Autonomes Hermes & Pods Dédiés Power Users
* **Hermes Studio (Kanban port 9119)** : Tableau de bord visuel protégé par SSO Entra ID pour suivre en direct les réflexions (Chain of Thought), les appels d'outils et la planification multi-étapes.
* **Hermes Gateway (API & WebSocket port 8642)** : Serveur API compatible OpenAI pour les sessions agentiques Open-WebUI, le bot Teams et le client lourd **Hermes Desktop**.
* **Pods Hermes Dédiés pour Power Users** (`.\scripts\Spawn-PowerUser.ps1`) : Chaque Power User dispose de son propre pod Hermes sur Kubernetes avec un PVC isolé de `10Gi`, sa propre `SOUL.md` et son Studio Kanban personnel (`/poweruser/<slug>/studio`).  
  👉 *Détail complet :* [Guide Hermes Agent & Mode Power User](docs/guides/hermes-agent.md)

### ⚡ 3. Passerelle d'Inférence & Catalogue des 5 Profils Canoniques
* **Catalogue Unifié** :
  * `simple/free` : Chat direct instantané sans coût (`openrouter/openrouter/free`).
  * `simple/auto` *(Défaut)* : Chat direct polyvalent et rapide avec routage intelligent (`openrouter/auto`).
  * `agentic/free` : Session autonome Hermes outillée sur palier gratuit (`openrouter/openrouter/free`).
  * `agentic/auto` : Session autonome Hermes avec outils, recherche et skills (`openrouter/auto`).
  * `agentic/expert` : Session autonome Hermes haute performance pour l'architecture et le code complexe (`openrouter/deepseek/deepseek-v4.1-flash`).
* **LiteLLM Proxy (port 4000) & Base Comptable (`litellm-db`)** : Équilibrage de charge, chaînes de fallback automatiques, quotas par équipe et suivi unifié des coûts.  
  👉 *Détail complet :* [Guide Inférence LiteLLM](docs/guides/inference-litellm.md) · [Guide Chaîne de Routage](docs/guides/chaine-de-routage.md)

### 🛡️ 4. Gouvernance, Double Barrière DLP & Sécurité
* **Double Barrière Presidio DLP (port 8080)** :
  * **Barrière 1 (Amont — Hermes Agent)** : Le plugin de gouvernance (`services/hermes/plugin.py`) caviarde les prompts et résultats d'outils via `/sanitize` *avant* écriture dans `state.db` et *avant* appel LLM.
  * **Barrière 2 (Aval — LiteLLM Proxy)** : Guardrail systématique en interception pré-inférence (`pre_call`, `default_on: true`) via `/analyze` et `/anonymize` pour tous les flux directs (`simple/*`, Teams, `/v1`).
* **Mode Fail-Closed & ZDR** : En cas d'indisponibilité du module DLP, la requête est bloquée net. La Zéro Rétention de Données (`zdr: true`) est forcée sur OpenRouter.  
  👉 *Détail complet :* [Guide Confidentialité Presidio DLP](docs/guides/confidentialite-presidio.md) · [Politique de Sécurité](docs/guides/securite.md)

### 🗜️ 5. Sobriété Tokenmaxing & Outillage
* **CCR (Compress-Cache-Retrieve)** : Compression réversible des fichiers et sorties JSON volumineuses (> 8 Ko) avec cache mémoire SHA-256 privé et restitution paginée à la demande (`arcia_compress_json_file`, `arcia_restore_tool_result`).
* **RTK (Rust Token Killer)** : Réécriture et compaction bornée des commandes `git log` verbeuses.
* **Graphify (GraphRAG Local Déterministe)** : Cartographie structurelle AST de bases de code en local (0 token consommé, 0 fuite de code vers le cloud).
* **Sobriété Ponytail** : Échelle de décision YAGNI évitant l'over-engineering agentique.  
  👉 *Détail complet :* [Guide Tokenmaxing](docs/guides/tokenmaxing.md) · [Guide Outillage Builder](docs/guides/outillage-builder.md) · [Guide Skills](docs/guides/skills.md)

---

## 🏛️ Architecture Globale

Tous les services sont déployés dans le namespace Kubernetes unifié `arcia`, sécurisés par Ingress et Cert-Manager TLS :

```mermaid
flowchart TD
    subgraph Clients ["👥 Utilisateurs"]
        StdUser["Utilisateur Standard<br/>(Open-WebUI Simple + Agentic & Teams)"]
        PowerUser["Power User<br/>(Open-WebUI + Pod Hermes dédié K8s)"]
        HermesDesk["Hermes Studio<br/>(Kanban :9119 via SSO)"]
    end

    subgraph IngressLayer ["🌐 Périmètre d'Ingress HTTPS (assistant.example.org)"]
        Traefik["Ingress Controller<br/>(Cert-Manager TLS)"]
        ForwardAuth["ForwardAuth Middleware<br/>(OAuth2-Proxy / Microsoft Entra ID)"]
        RateLimit["Middleware RateLimit (/v1)"]
    end

    subgraph ArcIANamespace ["☸️ Cluster Kubernetes — Namespace : arcia"]
        WebUI["Open-WebUI (:8080)<br/>Portail Hybride simple/* & agentic/*"]
        TeamsBot["Teams Bot Adapter (:3978)<br/>simple/auto & /agent -> Hermes"]
        HermesAgent["Hermes Agent (:9119 & :8642)<br/>Plugin DLP + CCR + RTK (PVC 20Gi)"]
        HermesPU["Pods Hermes Power Users<br/>(/poweruser/slug/studio + PVC 10Gi)"]
        PresidioDLP["Presidio DLP (:8080)<br/>Double Barrière Fail-Closed"]
        LiteLLM["LiteLLM Proxy (:4000)<br/>5 Profils Canoniques, ZDR & Quotas"]
        LiteLLMDB[("LiteLLM DB PostgreSQL (:5432)<br/>Clés Virtuelles, Teams & Budgets")]
    end

    subgraph CloudLayer ["☁️ Services Cloud Sécurisés"]
        OpenRouter["OpenRouter API<br/>(ZDR forcé : Free, Auto, DeepSeek V4.1 Flash)"]
        EntraID["Microsoft Entra ID<br/>(SSO & MFA d'Entreprise)"]
        AzureBot["Azure Bot Service<br/>(Passerelle Microsoft 365)"]
    end

    StdUser -->|HTTPS /| Traefik
    PowerUser -->|HTTPS /poweruser/slug/studio| Traefik
    HermesDesk -->|HTTPS /studio| Traefik
    StdUser -->|Activité Teams| AzureBot
    AzureBot -->|POST /api/teams/messages| Traefik

    Traefik --> ForwardAuth
    ForwardAuth -.->|Validation OIDC| EntraID
    ForwardAuth -->|Accès Autorisé /studio| HermesAgent
    ForwardAuth -->|Accès Autorisé /poweruser/slug| HermesPU

    Traefik --> RateLimit
    RateLimit -->|Appels API /v1| LiteLLM

    Traefik -->|Accès Portail /| WebUI
    Traefik -->|Bypass Webhook Signé| TeamsBot

    WebUI -->|Chat Direct simple/* :4000| LiteLLM
    WebUI -->|Session Agentique agentic/* :8642| HermesAgent
    TeamsBot -->|Chat simple/auto :4000| LiteLLM
    TeamsBot -->|Commande /agent :8642| HermesAgent

    HermesAgent -->|Barrière 1 DLP /sanitize| PresidioDLP
    HermesAgent -->|Inférence Agentique :4000| LiteLLM
    HermesPU -->|Barrière 1 DLP /sanitize| PresidioDLP
    HermesPU -->|Inférence Agentique :4000| LiteLLM

    LiteLLM <--> LiteLLMDB
    LiteLLM -->|Barrière 2 DLP /analyze + /anonymize| PresidioDLP
    LiteLLM -->|Appel Modèle Sécurisé ZDR| OpenRouter
```

👉 *Spécification d'architecture détaillée :* [docs/architecture.md](docs/architecture.md)

---

## 👥 Profils Utilisateurs

| Profil | Environnements & Canaux | Modèles Disponibles | Isolation & Persistance | Gouvernance & DLP |
|---|---|---|---|---|
| **Utilisateur Standard** | **Open-WebUI** (`/`) + **Microsoft Teams** | `simple/free`, `simple/auto`, `agentic/free`, `agentic/auto`, `agentic/expert` | Sessions Open-WebUI & Hermes partagé | SSO Entra ID + Double barrière DLP |
| **Power User** | **Open-WebUI** (`/`) + **Pod Hermes dédié** (`/poweruser/<slug>/studio`) | `simple/free`, `simple/auto`, `agentic/free`, `agentic/auto`, `agentic/expert` | Pod K8s isolé + PVC dédié `10Gi` + `SOUL.md` propre | SSO Entra ID + Budget dédié + Double barrière DLP |

👉 *Documentation détaillée :* [Guide Chaîne de Routage](docs/guides/chaine-de-routage.md) · [Guide Hermes Agent & Power Users](docs/guides/hermes-agent.md)

---

## 🚀 Démarrage Rapide

ArcIA se déploie sur n'importe quel cluster Kubernetes (EKS, AKS, GKE, K3s, kubeadm) ou en mode laboratoire Docker local via l'assistant interactif.

### 1. Cloner le dépôt
```bash
git clone https://github.com/votre-org/ArcIA.git
cd ArcIA
```

### 2. Lancer l'installeur interactif (Setup Wizard)
```powershell
# Sous Windows (PowerShell) :
.\wizard.ps1
```
```bash
# Sous Linux / macOS :
./wizard.sh
```

*(Pour un déploiement headless sans interface graphique :)*
```powershell
# Sous Windows (PowerShell) :
.\scripts\Deploy-ArcIA.ps1

# Sous Linux / macOS :
./scripts/deploy-arcia.sh
```

### 3. Déployer un Pod dédié pour un Power User
```powershell
.\scripts\Spawn-PowerUser.ps1 prenom.nom@example.org -Team engineering
```

👉 *Guides d'installation complets :* [Runbook Quickstart](docs/runbooks/quickstart.md) · [Guide de Déploiement Universel](docs/guides/deploiement-universel.md)

---

## 🛠️ Commandes d'Exploitation Essentielles

```powershell
# Vérifier l'état de tous les Pods, Services et StatefulSets
.\scripts\Invoke-K3s.ps1 "get pods,services,ingress,statefulset -n arcia -o wide"

# Lister ou gérer les pods dédiés des Power Users
.\scripts\Spawn-PowerUser.ps1 -Action list

# Exécuter la suite complète de tests unitaires et la validation documentaire
python -m unittest discover -s tests -v
python scripts/validate_docs.py
```

---

## 📄 Licence & Crédits

Développé pour la plateforme d'entreprise **ArcIA**.  
* Moteur d'agents basé sur [Hermes Agent](https://github.com/NousResearch/Hermes-Agent) (NousResearch).  
* Caviardage DLP propulsé par [Microsoft Presidio](https://github.com/microsoft/presidio).  
* Passerelle d'inférence propulsée par [LiteLLM](https://github.com/BerriAI/litellm).  
* Portail collaborateur propulsé par [Open-WebUI](https://github.com/open-webui/open-webui).
