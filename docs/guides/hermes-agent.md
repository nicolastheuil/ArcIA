# Hermes Agent — Moteur d'Agents & Orchestration ArcIA (v0.3)

> **Statut : Implémenté (v0.3)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

Hermes est le moteur d'exécution agentique d'entreprise d'ArcIA. Il permet d'exécuter des agents autonomes capables de planifier des tâches complexes, d'utiliser des outils (outils locaux, shell, git, navigateurs), de collaborer et de maintenir un état persistant.

---

## 1. Fonctionnalités Clés v0.3

- **Hermes Studio Dashboard (port 9119)** :
  - Interface visuelle de pilotage de missions en mode **Kanban**.
  - Visualisation des réflexions (CoT), appels d'outils et sous-agents.
  - Protégé par une barrière d'authentification native et ForwardAuth Entra ID.
- **Hermes Gateway & API Server (port 8642) — Backend Exclusif Open-WebUI** :
  - Expose une API standardisée compatible OpenAI (`/v1`).
  - **Zéro Bypass Open-WebUI** : Open-WebUI se connecte exclusivement sur cette passerelle. Chaque conversation web devient une session agentique autonome avec historique stocké dans `state.db`, mémoire et accès aux skills (outils de recherche web, appels d'APIs publiques).
  - Expose strictement les 3 modèles canoniques : `arcia/free`, `arcia/auto` (défaut), `arcia/expert`.
- **Mode Local Power User (N3) via `/v1`** :
  - Permet aux développeurs d'exécuter Hermes ou leur IDE localement sur leur machine tout en bénéficiant de l'inférence managée, du caviardage DLP et du budget d'entreprise via une clé virtuelle LiteLLM (PAT).
- **Persistance Dédiée (PVC 20Gi)** :
  - Monté sous `/opt/data`. Stocke `state.db` (SQLite WAL) et la mémoire de travail de l'agent.

---

## 2. Configuration & Déploiement

Le déploiement Kubernetes est géré par [deploy/manifests/06-hermes-agent.yaml](../../deploy/manifests/06-hermes-agent.yaml).

### Configuration Native (`~/.hermes/config.yaml`) :
Hermes Agent utilise son fichier de configuration officiel projeté via ConfigMap :

```yaml
model:
  provider: custom
  base_url: http://litellm-proxy.arcia.svc:4000/v1
  default: arcia/auto
  key_env: OPENAI_API_KEY
agent:
  auto_approve_safe_commands: true
  max_iterations: 30
platforms:
  api_server:
    direct_model_requests: true
    model_name: "arcia/auto"
    model_routes:
      arcia/free:
        model: "arcia/free"
      arcia/auto:
        model: "arcia/auto"
      arcia/expert:
        model: "arcia/expert"
```

---

<a id="power-users-spawn-kubernetes"></a>
## 3. Mode Power User (N3) : Pods Hermes Dédiés sur Kubernetes

Dans ArcIA v0.3, les Power Users ne déploient **aucun agent local sur leur PC**. Chaque Power User dispose d'une **instance Hermes complète et dédiée directement dans le cluster Kubernetes**, garantissant une étanchéité absolue de son environnement d'exécution, de son système de fichiers et de sa `SOUL.md`.

### 3.1 Architecture d'un Pod Power User Dédié
Chaque instance Power User est provisionnée à partir du gabarit [deploy/manifests/templates/hermes-poweruser.template.yaml](../../deploy/manifests/templates/hermes-poweruser.template.yaml) et comprend :
1. **Un PVC Isolé (`hermes-user-<slug>-pvc`)** : Volume persistant `ReadWriteOnce` (défaut 10Gi) montant `/opt/data`. Il contient exclusivement le `state.db` SQLite de l'utilisateur, sa mémoire de travail (`USER.md`, `MEMORY.md`) et ses fichiers créés.
2. **Une `SOUL.md` Personnalisée** : Injectée via ConfigMap et montée dans le profil. L'utilisateur peut calibrer la posture, le ton et les règles de son agent personnel sans impacter les autres.
3. **Un Deployment & Service Dédiés** : Exécutant `nousresearch/hermes-agent:latest`, avec accès à son propre **Studio Kanban** (`port 9119`) et sa **Gateway API** (`port 8642`).
4. **Un Ingress Traefik Sécurisé** : Exposé sur `https://<public_fqdn>/poweruser/<slug>/studio` protégé par authentification forte.
5. **Jeton d'Inférence Nominatif (PAT)** : Raccordé sur la passerelle centrale LiteLLM avec quota budgétaire mensuel contraint et filtrage DLP Presidio fail-closed.

### 3.2 Commandes d'Exploitation (`scripts/arcia_poweruser.py`)

Le script d'orchestration [scripts/arcia_poweruser.py](../../scripts/arcia_poweruser.py) (ou son wrapper PowerShell `scripts/Spawn-PowerUser.ps1`) permet de piloter l'ensemble du cycle de vie :

```bash
# 1. Spawner une nouvelle instance dédiée pour un collaborateur
python scripts/arcia_poweruser.py spawn claire.dubois@entreprise.com --team finance --job-title "Contrôleuse de Gestion" --manager "Marc Lefèvre"

# 2. Lister les instances Power Users actives dans le cluster
python scripts/arcia_poweruser.py list

# 3. Mettre en veille un pod inactif (scale=0 pour libérer la RAM tout en conservant le PVC)
python scripts/arcia_poweruser.py stop claire.dubois@entreprise.com

# 4. Réveiller une instance
python scripts/arcia_poweruser.py start claire.dubois@entreprise.com

# 5. Supprimer une instance (avec option de conservation du volume)
python scripts/arcia_poweruser.py destroy claire.dubois@entreprise.com --keep-pvc
```

### 3.3 Avantages Clés
1. **Zéro Empreinte PC** : Les collaborateurs n'ont aucun outil à installer localement ni configuration complexe d'IDE.
2. **Isolation de Sécurité Totale** : Étanchéité complète des processus et du disque ; l'agent peut exécuter du code (`bash`, shell, python) dans son conteneur sans aucun risque de fuite vers d'autres profils.
3. **Sobriété des Ressources** : La commande `stop` permet d'éteindre les pods hors des heures de travail (`replicas: 0`) pour restituer 100 % de la mémoire aux 3 nœuds du cluster VMware.
4. **DLP & Quotas Garantis** : 100 % des flux d'inférence sortants de l'agent passent par Presidio DLP et sont imputés au budget N3 de l'utilisateur.

> **Feuille de Route v0.4** : Les serveurs MCP distants dédiés (`arcia_knowledge` et `arcia_skills`) pour RAG multi-corpus font l'objet d'un lot d'évolution planifié pour la version v0.4. En v0.3, le RAG documentaire collaborateur est porté directement par Open-WebUI.

---

Voir également :
- [Chaîne de Routage & Cycle de Vie](chaine-de-routage.md)
- [Passerelle d'Inférence LiteLLM](inference-litellm.md)
- [État des Fonctionnalités v0.3](../etat-des-fonctionnalites.md)
- [Runbook Quickstart](../runbooks/quickstart.md)
