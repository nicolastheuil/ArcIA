# ArcIA — Plateforme IA Agentique Souveraine d'Entreprise

[![ArcIA Version](https://img.shields.io/badge/ArcIA-v0.2-blue.svg)](docs/architecture.md)
[![Cluster Status](https://img.shields.io/badge/Cluster-K3s%20Debian%20HA-success.svg)](docs/guides/infrastructure-k3s.md)
[![DLP Engine](https://img.shields.io/badge/DLP-Presidio%20Active-green.svg)](docs/guides/confidentialite-presidio.md)
[![Agent Runtime](https://img.shields.io/badge/Engine-Hermes%20v0.2-purple.svg)](docs/guides/hermes-agent.md)
[![Teams Integration](https://img.shields.io/badge/Teams-Bot%20Framework-blue.svg)](docs/guides/integration-teams.md)

**ArcIA** est la plateforme d'intelligence artificielle agentique d'entreprise conçue pour réconcilier **l'autonomie d'agents d'élite**, la **gouvernance stricte des données** et une **expérience utilisateur unifiée**.

Elle offre aux collaborateurs une interface de chat web moderne et un bot Microsoft Teams, tout en mettant à disposition des ingénieurs et power users le moteur agentique **Hermes**, un tableau de bord Kanban multi-agents et une passerelle sécurisée pour l'application **Hermes Desktop**.

---

## 🗺️ Navigation Rapide vers la Documentation

| Domaine / Fonctionnalité | Rôle & Description | Documentation Spécifique |
|---|---|---|
| 🚀 **Déploiement Universel** | Guide complet pour déployer ArcIA sur n'importe quel cluster Kubernetes | 📖 [docs/guides/deploiement-universel.md](docs/guides/deploiement-universel.md) |
| 🏗️ **Architecture Globale** | Vue d'ensemble du cluster unifié, flux de requêtes et isolation | 📖 [docs/architecture.md](docs/architecture.md) |
| 🤖 **Moteur d'Agents Hermes** | Hermes Studio (Kanban 9119), Gateway Desktop (8642) et Tokenmaxing | 📖 [docs/guides/hermes-agent.md](docs/guides/hermes-agent.md) |
| 🛡️ **Confidentialité & DLP** | Caviardage automatique des secrets, mots de passe et PII (Presidio) | 📖 [docs/guides/confidentialite-presidio.md](docs/guides/confidentialite-presidio.md) |
| ⚡ **Passerelle d'Inférence** | LiteLLM Proxy, modèle virtuel intelligent `auto`, fallbacks et quotas | 📖 [docs/guides/inference-litellm.md](docs/guides/inference-litellm.md) |
| 💻 **Portail Collaborateur** | Open-WebUI chat d'entreprise et SSO Microsoft Entra ID | 📖 [docs/guides/portail-webui-entraid.md](docs/guides/portail-webui-entraid.md) |
| 💬 **Intégration Teams** | Adaptateur Bot Framework, conversations privées et mentions en canaux | 📖 [docs/guides/integration-teams.md](docs/guides/integration-teams.md) |
| 🔀 **Routeur OmniRoute** | Routeur multi-fournisseurs avec dashboard d'administration LAN v3.8.51 | 📖 [docs/guides/omniroute.md](docs/guides/omniroute.md) |
| 🗜️ **Tokenmaxing & Optimisation** | RTK CLI, Headroom AI et LintLang pour la réduction de contexte et l'hygiène de prompt | 📖 [docs/guides/tokenmaxing.md](docs/guides/tokenmaxing.md) |
| 📚 **Catalogues de Skills** | Montage partagé multi-agents : ECC (313 skills), Superpowers (15), Vercel & Anthropics | 📖 [docs/guides/skills.md](docs/guides/skills.md) |
| 🧰 **Outillage Agentique & MCP** | Skills CLI, LintLang, Context7 MCP, outillage interne et gestion des dépendances | 📖 [docs/guides/outillage-builder.md](docs/guides/outillage-builder.md) |
| ☸️ **Infrastructure & K3s** | Cluster 3 nœuds VMware, StorageClass CSI et certificats Let's Encrypt | 📖 [docs/guides/infrastructure-k3s.md](docs/guides/infrastructure-k3s.md) |
| 🛠️ **Runbook d'Exploitation** | Commandes d'administration, consultation des logs et maintenance | 📖 [docs/runbooks/exploitation.md](docs/runbooks/exploitation.md) |
| 📋 **Suivi & Handoff** | Journal d'exécution, état de qualification et prochaines étapes | 📖 [docs/etat-reprise.md](docs/etat-reprise.md) |

---

## 🚀 Déploiement Rapide en 5 Minutes (Cluster Kubernetes Quelconque)

ArcIA est **100% reproductible et automatisé**. N'importe quel cluster Kubernetes (K3s, EKS, AKS, GKE, KinD, Minikube...) peut héberger votre instance à partir d'un **seul et unique fichier de configuration**.

### 1. Cloner le dépôt
```bash
git clone https://github.com/nicolastheuil/ArcIA.git
cd ArcIA
```

### 2. Lancer l'Assistant Graphique Interactif (Setup Wizard)

Pour configurer et déployer votre instance en toute simplicité écran par écran, lancez simplement l'assistant graphique :

```bash
# Sous Linux / macOS :
./wizard.sh

# Sous Windows (PowerShell) :
.\wizard.ps1

# Ou directement avec Python :
python scripts/wizard.py
```

Le Wizard démarre un serveur local autonome et ouvre automatiquement votre navigateur Web :
- **Écran par écran** : Saisie guidée de la connexion Kubernetes, du nom de domaine FQDN et de votre clé LLM.
- **Auto-configuration interne intégrale** : Presidio DLP, Open-WebUI, Hermes Studio & Gateway, LiteLLM Proxy et synchronisation automatique de toutes les compétences (Ponytail, Graphify, Public-APIs) sans aucune manipulation.
- **Modules optionnels ré-exécutables** : Activez ou complétez à tout moment le SSO Microsoft Entra ID ou le bot Teams avec guides pas-à-pas intégrés et liens directs vers la documentation.
- **Récapitulatif immédiat 100% opérationnel** : Affichage et copie directe de toutes les URLs d'accès, jetons et identifiants administrateur.

---

### Alternative en ligne de commande (Sans interface graphique)

Si vous préférez une configuration manuelle sans interface :
1. Copiez [arcia.config.yaml.example](arcia.config.yaml.example) vers `arcia.config.yaml` :
   ```bash
   cp arcia.config.yaml.example arcia.config.yaml
   ```
2. Renseignez votre FQDN et votre clé OpenRouter.
3. Exécutez le déploiement :
   ```bash
   ./scripts/deploy-arcia.sh   # Linux / macOS
   .\scripts\Deploy-ArcIA.ps1  # Windows PowerShell
   ```

👉 Pour le détail complet, consultez le **[Guide de Déploiement Universel](docs/guides/deploiement-universel.md)** et le **[Quickstart](docs/runbooks/quickstart.md)**.

---

## 🏛️ Architecture Technique v0.2

```mermaid
flowchart TD
    subgraph Clients ["👥 Points d'Entrée Utilisateurs"]
        WebUser["Navigateur Web<br/>(Collaborateur)"]
        TeamsUser["Microsoft Teams<br/>(DM & Canaux @ArcIA)"]
        HermesDesk["Hermes Desktop<br/>(Power User / Dev)"]
    end

    subgraph Ingress ["🌐 Périmètre d'Ingress HTTPS (assistant.example.org)"]
        Traefik["Traefik Controller + Cert-Manager TLS"]
        AuthMiddleware["ForwardAuth Middleware (oauth2-proxy)"]
    end

    subgraph CoreCluster ["☸️ Cluster K3s — Namespace: arcia"]
        WebUI["Open-WebUI<br/>(:8080 - Portail Chat)"]
        TeamsBot["Teams Bot Adapter<br/>(:3978 - Bot Framework)"]
        HermesAgent["Hermes Agent v0.2<br/>Studio (:9119) & Gateway (:8642)"]
        SkillsShare[("Catalogue Shared Skills<br/>/var/data/arcia/shared-skills")]
        Presidio["Presidio DLP<br/>(:8080 - Caviardage Secrets & PII)"]
        LiteLLM["LiteLLM Proxy<br/>(:4000 - Modèle Virtuel 'auto')"]
    end

    subgraph External ["☁️ Services Cloud & Partenaires"]
        OpenRouter["OpenRouter API<br/>(Claude 3.5 Sonnet, DeepSeek)"]
        EntraID["Microsoft Entra ID / M365"]
        AzureBotSvc["Azure Bot Service"]
    end

    WebUser -->|HTTPS /| Traefik
    HermesDesk -->|HTTPS /gateway /studio| Traefik
    TeamsUser -->|Activité Teams| AzureBotSvc
    AzureBotSvc -->|POST /api/teams/messages| Traefik

    Traefik --> AuthMiddleware
    AuthMiddleware -.->|Vérification OIDC| EntraID
    AuthMiddleware -->|Accès Autorisé /| WebUI
    AuthMiddleware -->|Accès Autorisé /studio| HermesAgent
    Traefik -->|Bypass Auth Webhook| TeamsBot

    WebUI -->|Prompt| LiteLLM
    TeamsBot -->|Prompt| LiteLLM
    HermesAgent -->|Inférence| LiteLLM
    SkillsShare -.->|Montage RO| HermesAgent

    LiteLLM -->|Filtrage Pré-Vol| Presidio
    LiteLLM -->|Prompt Caviardé| OpenRouter
```

---

## 📦 Organisation du Répertoire

```
arcia/
├── deploy/                     # Manifestes Kubernetes de production
│   └── manifests/
│       ├── 01-cert-manager-issuer.yaml  # ClusterIssuer Let's Encrypt automatique
│       ├── 02-oauth2-proxy.yaml         # Middleware SSO ForwardAuth Microsoft Entra ID
│       ├── 03-presidio.yaml             # Microservice Presidio DLP
│       ├── 04-ingress.yaml              # Routes d'Ingress Traefik (public & studio)
│       ├── 05-litellm.yaml              # Passerelle d'inférence LiteLLM
│       ├── 06-hermes-agent.yaml         # Moteur Hermes Core, Studio et Gateway
│       ├── 07-open-webui.yaml           # Portail Web collaborateur
│       ├── 08-teams-bot.yaml            # Adaptateur Microsoft Teams Bot
│       └── 09-omniroute.yaml            # Routeur d'inférence multi-fournisseurs et portail LAN OmniRoute
├── services/                   # Code source des microservices applicatifs
│   ├── hermes/                 # Dockerfile custom et plugin ArcIA Tokenmaxing
│   ├── presidio/               # Service FastAPI d'anonymisation PII & secrets
│   └── teams/                  # Adaptateur asynchrone Teams Bot Framework
├── skills/                     # Compétences et outillage méthodologique
│   ├── ponytail/               # Sobriété logicielle, YAGNI & Decision Ladder (ADR 0021)
│   ├── graphify/               # Cartographie structurelle AST & GraphRAG local (ADR 0021)
│   ├── public-apis/            # Référentiel de veille & gouvernance APIs ouvertes (ADR 0021)
│   └── sync-skills.sh          # Synchronisation des compétences partagées
├── scripts/                    # Outillage d'exploitation et d'automatisation
│   ├── arcia_graphify.py       # Cartographie AST & GraphRAG locale déterministe (0 token, 0 fuite)
│   ├── Sync-Skills.ps1         # Synchronisation des compétences (PowerShell)
│   ├── deploy.py               # Moteur universel de déploiement Kubernetes (Python)
│   ├── Deploy-ArcIA.ps1        # Script de déploiement en une commande (PowerShell)
│   ├── deploy-arcia.sh         # Script de déploiement en une commande (Bash / Linux)
│   ├── Invoke-K3s.ps1          # Wrapper d'exécution distant sur cluster K3s SSH
│   ├── Apply-Secrets.ps1       # Injection directe des secrets Kubernetes (PowerShell)
│   ├── apply-secrets.sh        # Injection directe des secrets Kubernetes (Bash)
│   └── test-validation.sh      # Suite de validation automatisée (6/6 tests)
├── arcia.config.yaml.example   # Gabarit officiel unique de configuration (recommandé)
├── arcia.env.example           # Alternative .env plate pour la configuration
├── secrets/                    # Gestion des variables d'environnement et secrets
│   ├── arcia.env.template      # Gabarit officiel de secrets
│   └── arcia.env               # Fichier de secrets réels (strictement ignoré par Git)
└── docs/                       # Documentation exhaustive du projet
    ├── architecture.md         # Spécification détaillée de l'architecture
    ├── etat-reprise.md         # Journal d'exploitation et handoff unique
    ├── guides/                 # Guides techniques par composant
    └── runbooks/               # Procédures opérationnelles et d'urgence
```

---

## 🚀 Commandes d'Exploitation Essentielles

Toutes les actions d'administration s'exécutent depuis le contrôleur local :

```powershell
# 1. Vérifier l'état de tous les composants sur le cluster K3s
.\scripts\Invoke-K3s.ps1 "get pods -n arcia -o wide"

# 2. Lancer la suite de recette automatique (6/6 tests)
Get-Content .\scripts\test-validation.sh -Raw | .\scripts\Invoke-K3s.ps1 -RawShell "bash -s"

# 3. Mettre à jour et injecter les secrets Kubernetes
.\scripts\Apply-Secrets.ps1

# 4. Consulter les journaux en direct d'un composant
.\scripts\Invoke-K3s.ps1 "logs -l app=hermes-agent -n arcia --tail=50 -f"
.\scripts\Invoke-K3s.ps1 "logs -l app=litellm-proxy -n arcia --tail=50 -f"
.\scripts\Invoke-K3s.ps1 "logs -l app=teams-bot-adapter -n arcia --tail=50 -f"
```

Pour la liste complète des procédures, consultez le [Runbook d'Exploitation](docs/runbooks/exploitation.md).

---

## 🔒 Sécurité, Confidentialité & Secrets

- **Zero Secret in Git** : Le fichier `secrets/arcia.env` est strictement exclu du versionnement par `.gitignore`. Seul le gabarit `secrets/arcia.env.template` est suivi.
- **Principe du Moindre Privilège** : Les conteneurs tournent avec des utilisateurs dédiés sans privilège cluster-admin.
- **Isolation du Stockage** : Un seul écrivain actif par base `state.db` Hermes sur volume dédié VMware CSI.
- **Protection DLP Active** : Caviardage systématique avant tout départ de prompt vers le cloud public.

---

## 📄 Licence & Mentions Légales

Développé pour la plateforme d'entreprise souveraine ArcIA.
Moteur d'agents basé sur [Hermes Agent](https://github.com/NousResearch/Hermes-Agent) (NousResearch).
DLP propulsé par [Microsoft Presidio](https://github.com/microsoft/presidio).
Passerelle d'inférence propulsée par [LiteLLM](https://github.com/BerriAI/litellm).
Portail collaborateur propulsé par [Open-WebUI](https://github.com/open-webui/open-webui).
