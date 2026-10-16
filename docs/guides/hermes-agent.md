# Hermes Agent — Moteur d'Agents & Orchestration ArcIA

Hermes est le moteur d'exécution agentique d'entreprise d'ArcIA. Il permet d'exécuter des agents autonomes capables de planifier des tâches complexes, d'utiliser des outils (outils locaux, shell, git, navigateurs, MCP), de collaborer en essaim (multi-agents) et de maintenir un état persistant.

---

## 1. Fonctionnalités Clés

- **Hermes Studio Dashboard (port 9119)** :
  - Interface visuelle de pilotage de missions en mode **Kanban**.
  - Visualisation en direct des réflexions (CoT), appels d'outils et sous-agents.
  - Gestion des sessions et reprise d'historique.
  - Protégé par une barrière d'authentification native (Auth Gate).
- **Hermes Gateway & API Server (port 8642)** :
  - Serveur WebSocket & HTTP permettant de connecter le client lourd natif **Hermes Desktop**.
  - Permet le mode "Bot Screen" (prise de contrôle graphique de l'agent si requis).
  - Fournit une API d'exécution d'agents pour les intégrations tierces.
- **Plugin ArcIA Tokenmaxing** :
  - Compresse dynamiquement les sorties verbeuses (`git log`, commandes terminal, payloads JSON massifs).
  - Évite le débordement de contexte et divise la facture de tokens jusqu'à 60%.
- **Persistance Dédiée (PVC 20Gi)** :
  - Monté sous `/opt/data`.
  - Stocke `state.db` (SQLite WAL), la mémoire de travail et la configuration de l'agent sans risque de corruption.

---

## 2. Configuration & Déploiement

Le déploiement Kubernetes est géré par [deploy/manifests/06-hermes-agent.yaml](../../deploy/manifests/06-hermes-agent.yaml).

### Variables d'Environnement Clés :
- `API_SERVER_ENABLED=true` : Active la passerelle WebSocket/API sur le port 8642.
- `API_SERVER_KEY` : Clé secrète de la passerelle, injectée depuis le secret Kubernetes `hermes-gateway-secret`.
- `HERMES_DASHBOARD_BASIC_AUTH_USERNAME` / `PASSWORD` : Authentification requise pour l'exposition du Studio sur le port 9119.
- `OPENAI_API_BASE=http://litellm-proxy.arcia.svc:4000/v1` : Branchement transparent sur LiteLLM.
- `OPENAI_MODEL_NAME=auto` : Délégation au modèle virtuel intelligent d'ArcIA.

---

## 3. Connexion depuis l'application Hermes Desktop

Pour connecter un poste de travail avec Hermes Desktop :
1. Ouvrir **Hermes Desktop**.
2. Naviguer vers **Settings → Gateways → Add Gateway** :
   - **Name** : `ArcIA Enterprise Cluster`
   - **URL** : `https://assistant.example.org/gateway` (ou votre domaine d'instance)
   - **Auth Token** : Votre Personal Access Token (PAT) d'entreprise.
3. La liaison WebSocket chiffrée s'établit instantanément.

---

<a id="power-users-agent-local"></a>
## 4. Mode Power User : Agent Local & Ingestion Hybride

Pour les ingénieurs et *power users*, certains scénarios avancés nécessitent d'exécuter des actions directement depuis le poste de travail local plutôt que dans le conteneur Kubernetes central.

### 4.1 Pourquoi un mode local pour les Power Users ?

Le déploiement centralisé K3s isole l'exécution de l'agent dans un conteneur Linux headless. Ce cloisonnement empêche nativement certains cas d'usage poste client :

1. **Routage réseau & VPN client** :
   - Si un power user monte un VPN personnel ou temporaire sur son PC (ex. Cisco AnyConnect, FortiClient, WireGuard pour joindre un réseau client ou une DMZ isolée), le pod K3s central ne peut pas traverser cette interface réseau locale.
   - Les commandes terminal de l'agent central échoueront avec des erreurs de connectivité (*Network Unreachable*).
2. **Computer Use (Pilotage d'écran et d'OS)** :
   - Le conteneur Kubernetes n'a aucun accès au serveur d'affichage graphique de l'utilisateur (bureau Windows, macOS Quartz, Wayland/X11), ni aux clics de souris et saisies clavier du poste physique.
3. **Intégration directe à l'IDE local** :
   - Dans un IDE local (VS Code, Cursor, JetBrains), l'agent doit pouvoir inspecter, tester et modifier directement les fichiers de l'espace de travail local sans passer par des synchronisations distantes complexes.

### 4.2 Architecture du Mode Hybride

Le mode hybride combine l'autonomie d'exécution sur le poste de travail (accès direct au VPN, à l'IDE et à l'écran) avec la gouvernance centrale d'ArcIA (inférence souveraine, DLP Presidio, RAG et catalogue de compétences) :

```mermaid
flowchart TD
    subgraph PosteClient ["💻 Poste de Travail Power User"]
        IDE["IDE Local (VS Code / Cursor)"]
        LocalAgent["Agent Local (Hermes CLI / Runner)<br/>- Computer Use (Écran & Périphériques)<br/>- Workspace local sur disque"]
        ClientVPN["Tunnel VPN Client<br/>(Accès sous-réseaux protégés)"]
        RemoteServers["🖥️ Systèmes distants du VPN"]

        IDE <--> LocalAgent
        LocalAgent -->|Exécution shell & scripts| ClientVPN
        ClientVPN -->|Commandes réseau| RemoteServers
    end

    subgraph ArcIACentral ["☸️ Plateforme Centrale ArcIA (Cluster K3s)"]
        Ingress["Traefik Ingress<br/>(HTTPS /v1 et /mcp)"]
        Presidio["Presidio DLP<br/>(Caviardage PII & Secrets)"]
        LiteLLM["LiteLLM Proxy<br/>(Routage & Quotas d'Entreprise)"]
        MCPKnowledge["Serveur MCP arcia_knowledge<br/>(Portail RAG d'Entreprise)"]
        VectorDB[("ChromaDB & Corpus RAG<br/>(PVC 50Gi)")]
        MCPSkills["Catalogue de Skills<br/>(539 compétences miroir)"]
    end

    LocalAgent -->|1. Inférence LLM HTTPS + PAT| Ingress
    Ingress --> Presidio
    Presidio --> LiteLLM
    LiteLLM -->|Prompt assaini| CloudLLM["☁️ LLMs Souverains & Cloud"]

    LocalAgent -->|2. Requêtes documentaires (MCP)| MCPKnowledge
    MCPKnowledge --> VectorDB

    LocalAgent -.->|3. Synchronisation de compétences| MCPSkills
```

### 4.3 Raccordement de l'Agent Local aux Services d'Entreprise

Pour qu'un agent local conserve tous les atouts de la plateforme d'entreprise sans se limiter à un LLM brut, trois liaisons distinctes sont configurées :

#### 1. Inférence Souveraine & Caviardage DLP (Obligatoire)
L'agent local pointe son API OpenAI vers la passerelle ArcIA au lieu d'un fournisseur cloud direct :
```bash
# Variables d'environnement pour l'agent local (Hermes CLI, Cline, Continue.dev, etc.)
export OPENAI_API_BASE="https://assistant.example.org/v1"
export OPENAI_API_KEY="<VOTRE_PAT_ENTREPRISE>"
export OPENAI_MODEL_NAME="auto"
```
* **Bénéfice** : Tout prompt émis localement traverse systématiquement **Presidio DLP** sur le cluster central. Les secrets d'entreprise, tokens et données personnelles (PII) sont caviardés avant toute transmission vers un fournisseur de modèles externe. Les quotas et consommations sont agrégés sur le compte de l'organisation.

#### 2. Accès au RAG Documentaire d'Entreprise (Base de Connaissances)
`OPENAI_API_BASE` ne fournit que le moteur de complétion textuelle. Pour interroger les documents de l'entreprise (procédures, bases documentaires ChromaDB) :
* L'agent local déclare le connecteur distant [`arcia_knowledge`](connecteurs-mcp.md) dans son fichier de configuration MCP (`mcp_servers.json`) :
  ```json
  {
    "mcpServers": {
      "arcia_knowledge": {
        "url": "https://assistant.example.org/mcp/knowledge",
        "headers": {
          "Authorization": "Bearer <VOTRE_PAT_ENTREPRISE>"
        }
      }
    }
  }
  ```
* L'agent peut alors exécuter l'outil `search_knowledge` pour récupérer les extraits documentaires internes pertinents et les intégrer à son contexte de résolution.

#### 3. Catalogue de Skills d'Entreprise
Pour appliquer les méthodes standardisées de l'organisation ([skills.md](skills.md)) :
* **Option A (Recommandée - Synchronisation Git)** : Cloner ou synchroniser le répertoire `skills/` du dépôt ArcIA (ou du dépôt d'instance) vers le dossier local de l'agent (`~/.hermes/skills/`). L'agent dispose alors des méthodes canoniques (comme [Ponytail](../../skills/ponytail/README.md) pour la sobriété logicielle) directement en local.
* **Option B (MCP distant)** : Invoquer le serveur MCP `arcia_skills` pour rechercher (`catalog_search`) et charger (`catalog_load`) dynamiquement les compétences du miroir d'entreprise.

#### 4. GraphRAG de Code Local (Graphify)
Pour analyser le code source du projet sur le poste client sans saturer le contexte ni envoyer le code au cluster :
* Le développeur utilise la compétence native ArcIA [`Graphify`](../../skills/graphify/README.md).
* Le script `arcia_graphify.py` cartographie la structure AST localement sur la machine cliente, fournissant un **GraphRAG local déterministe à 0 token et 0 fuite de code**.

---

### 4.4 Matrice Comparative des Modes d'Exécution

| Fonctionnalité | Agent 100 % Central (Pod K3s) | Agent Hybride (Local + ArcIA) |
|---|:---:|:---:|
| **Passage par le VPN du poste client** | ❌ Impossible (réseau cluster isolé) | ✅ Natif (emprunte la table de routage locale) |
| **Computer Use (Pilotage de l'écran OS)** | ❌ Impossible (conteneur headless) | ✅ Natif (accès aux fenêtres et périphériques) |
| **Manipulation directe de l'IDE local** | ⚠️ Complexe (requiert montage SSH/DevContainer) | ✅ Natif (lecture/écriture directe sur disque) |
| **Missions longues asynchrones (Background)** | ✅ Idéal (persistant sur PVC `state.db`) | ⚠️ Dépendant de la mise en veille du poste |
| **Pilotage Kanban & Suivi d'équipe (Studio)**| ✅ Natif sur port 9119 | ⚠️ Sessions locales non centralisées |
| **Caviardage DLP Presidio & Quotas** | ✅ Automatique | ✅ Automatique via `OPENAI_API_BASE` |
| **RAG Documentaire d'Entreprise** | ✅ Natif dans le cluster | ✅ Via connecteur MCP `arcia_knowledge` |
| **Skills Partagées d'Entreprise** | ✅ Volume monté `/opt/shared-skills` | ✅ Via synchronisation Git ou MCP |

---

### 4.5 Bonnes Pratiques de Sécurité & Gouvernance

1. **VPN Personnels et Temporaires** : Conformément à la politique d'exploitation ArcIA, les accès VPN sur les postes clients doivent rester temporaires et circonscrits aux missions autorisées.
2. **Pas de Secrets en Dur** : Ne jamais stocker de jetons PAT ou d'identifiants d'accès dans les fichiers du projet ou l'historique de discussion. Utiliser des gestionnaires de trousseau d'accès locaux ou des variables d'environnement éphémères.
3. **Actions Externes à Risque** : Même exécutée depuis le poste client, toute action sur une infrastructure distante de production doit suivre le principe de validation explicite avant exécution destructive.

