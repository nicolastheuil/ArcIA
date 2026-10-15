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
