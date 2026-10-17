# Guides Techniques & Fonctionnels — ArcIA

Ce dossier regroupe les 15 guides thématiques détaillant chaque brique de l'architecture ArcIA v0.4.

## Index des Guides par Domaine

### 1. Architecture & Principes Généraux
* [plateforme-arcia.md](plateforme-arcia.md) : Vision globale d'ArcIA, articulation entre le harness générique et les dépôts d'instances privés.
* [securite.md](securite.md) : Périmètre de sécurité, gouvernance fail-closed Presidio DLP, proscription du BYOK non contrôlé et clés virtuelles PAT.
* [versions-officielles.md](versions-officielles.md) : Matrice des images Docker, versions logicielles et ports officiels déployés.

### 2. Moteur d'Agents & Outillage
* [hermes-agent.md](hermes-agent.md) : Moteur d'exécution Hermes Agent, Studio Kanban (port 9119), Gateway Desktop (port 8642) et double modalité Power Users (N3).
* [skills.md](skills.md) : Catalogue des compétences partagées, recherche locale et moteur de chargement.
* [tokenmaxing.md](tokenmaxing.md) : Compression réversible CCR (cache SHA-256), RTK et sobriété de contexte active en v0.4.
* [outillage-builder.md](outillage-builder.md) : Outils natifs de sobriété logicielle (Ponytail, analyseur Graphify AST et veille Public-APIs).
* [connecteurs-mcp.md](connecteurs-mcp.md) : Intégration du protocole Model Context Protocol (MCP) pour les outils et bases documentaires.

### 3. Inférence LLM, Routage & Confidentialité
* [chaine-de-routage.md](chaine-de-routage.md) : Routage hybride (`simple/*` & `agentic/*`), catalogue des 5 profils canoniques et cycle de vie d'une requête.
* [inference-litellm.md](inference-litellm.md) : Configuration du proxy LiteLLM, Zero Data Retention, guardrail Presidio et comptabilité PostgreSQL 16.
* [confidentialite-presidio.md](confidentialite-presidio.md) : Double barrière de caviardage DLP Presidio (Hermes amont + LiteLLM aval) en mode fail-closed.

### 4. Interfaces Collaborateurs & Canaux
* [portail-webui-entraid.md](portail-webui-entraid.md) : Portail conversationnel Open-WebUI, intégration SSO Microsoft Entra ID et RAG d'entreprise.
* [integration-teams.md](integration-teams.md) : Adaptateur bot interactif pour Microsoft Teams (`simple/auto` et commande `/agent`).

### 5. Infrastructure & Exploitation
* [deploiement-universel.md](deploiement-universel.md) : Moteur de déploiement universel `deploy.py`, synchronisation des ConfigMaps et fichier de configuration.
* [infrastructure-k3s.md](infrastructure-k3s.md) : Déploiement K3s sur 3 VM VMware, gestion du stockage CSI persistant et Ingress Traefik.
