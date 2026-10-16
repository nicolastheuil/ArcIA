# Guides Techniques & Fonctionnels — ArcIA

Ce dossier regroupe les 16 guides thématiques détaillant chaque brique de l'architecture ArcIA v0.3.

## Index des Guides par Domaine

### 1. Architecture & Principes Généraux
* [plateforme-arcia.md](plateforme-arcia.md) : Vision globale d'ArcIA, articulation entre le harness générique et les dépôts d'instances privés.
* [securite.md](securite.md) : Périmètre de sécurité, gouvernance fail-closed Presidio DLP, proscription du BYOK non contrôlé et clés virtuelles PAT.
* [versions-officielles.md](versions-officielles.md) : Matrice des images Docker, versions logicielles et ports officiels déployés.

### 2. Moteur d'Agents & Outillage
* [hermes-agent.md](hermes-agent.md) : Moteur d'exécution Hermes Agent, Studio Kanban (port 9119), Gateway Desktop (port 8642) et mode hybride Power Users.
* [skills.md](skills.md) : Catalogue des 539 compétences miroir, recherche locale et moteur de chargement.
* [tokenmaxing.md](tokenmaxing.md) : Compression contextuelle native et outillage standard (abandon du plugin ConfigMap en v0.3).
* [outillage-builder.md](outillage-builder.md) : Outils natifs de sobriété logicielle (Ponytail, analyseur Graphify AST et veille Public-APIs).
* [connecteurs-mcp.md](connecteurs-mcp.md) : Intégration du protocole Model Context Protocol (MCP) pour les outils et bases documentaires.

### 3. Inférence LLM, Routage & Confidentialité
* [chaine-de-routage.md](chaine-de-routage.md) : Cycle de vie d'une requête d'inférence, de l'utilisateur jusqu'au modèle cloud avec observabilité.
* [inference-litellm.md](inference-litellm.md) : Configuration du proxy LiteLLM, 3 tiers canoniques (`standard`/`expert`/`reasoning`), Zero Data Retention, PostgreSQL 16.
* [confidentialite-presidio.md](confidentialite-presidio.md) : Passerelle de caviardage DLP Presidio (anonymisation PII, tokens et secrets d'entreprise) en mode fail-closed.
* [omniroute.md](omniroute.md) : Documentation d'OmniRoute (retiré en v0.3 au profit de LiteLLM Proxy unifié).

### 4. Interfaces Collaborateurs & Canaux
* [portail-webui-entraid.md](portail-webui-entraid.md) : Portail conversationnel Open-WebUI, intégration SSO Microsoft Entra ID et RAG d'entreprise.
* [integration-teams.md](integration-teams.md) : Adaptateur bot interactif pour Microsoft Teams (messages privés et mentions de canal).

### 5. Infrastructure & Exploitation
* [deploiement-universel.md](deploiement-universel.md) : Moteur de déploiement universel `deploy.py`, validation des prérequis et fichier de configuration.
* [infrastructure-k3s.md](infrastructure-k3s.md) : Déploiement K3s sur 3 VM VMware, gestion du stockage CSI persistant et Ingress Traefik.

