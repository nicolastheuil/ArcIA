# Hermes Agent — moteur d'agents, Studio et pods dédiés Power Users (v0.5.0)

> **Statut : Implémenté (v0.5.0)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

Hermes est le moteur d'exécution agentique d'entreprise d'ArcIA. Il permet d'exécuter des agents autonomes capables de planifier des tâches complexes, d'utiliser des outils (outils locaux, shell, git, recherche web, APIs publiques), de compresser leur contexte (CCR/RTK) et de maintenir un état persistant.

---

## 1. Fonctionnalités clés v0.5.0

- **Hermes Studio Dashboard (port 9119)** :
  - Interface visuelle de pilotage de missions en mode **Kanban**.
  - Visualisation des réflexions (Chain of Thought), appels d'outils et sous-agents.
  - Protégé par authentification native et middleware Traefik ForwardAuth Entra ID (`/studio`).
- **Hermes Gateway & API Server (port 8642) — Moteur des Profils `agentic/*`** :
  - Expose une API standardisée compatible OpenAI (`/v1`).
  - Prend en charge les sessions agentiques d'Open-WebUI (`agentic/free`, `agentic/auto`, `agentic/expert`) ainsi que les missions déléguées depuis Microsoft Teams via la commande `/agent <mission>`.
  - Chaque conversation agentique dispose d'un historique persistant dans `state.db`, de compétences partagées (`/opt/shared-skills`) et du plugin de gouvernance [services/hermes/plugin.py](../../services/hermes/plugin.py) (Barrière 1 DLP Presidio + compression réversible CCR + RTK).
  - Gestion des erreurs conviviales Power Users : `format_hermes_error` intercepte les rejets de sécurité Presidio (`ArcIAPresidioBlockedException` Fail-Closed) et les erreurs amont pour les restituer sous forme d'alertes Markdown explicites (`[!CAUTION]`, `[!WARNING]`) dans Hermes Studio et le CLI.
- **Pods Hermes Dédiés pour Power Users** :
  - En plus de l'accès complet à Open-WebUI (`simple/*` + `agentic/*`), chaque Power User dispose d'un pod Hermes personnel et isolé sur Kubernetes (`/poweruser/<slug>/studio`) via [scripts/Spawn-PowerUser.ps1](../../scripts/Spawn-PowerUser.ps1).
- **Persistance Dédiée (PVC 20Gi)** :
  - Monté sous `/opt/data`. Stocke `state.db` (SQLite WAL) et l'espace de travail de l'agent.

---

## 2. Configuration et déploiement

Le déploiement Kubernetes est géré par [deploy/manifests/06-hermes-agent.yaml](../../deploy/manifests/06-hermes-agent.yaml). Le plugin [services/hermes/plugin.py](../../services/hermes/plugin.py) est injecté dans le ConfigMap `hermes-governance-plugin` par `scripts/deploy.py`.

### Configuration native (`~/.hermes/config.yaml`) :
```yaml
model:
  provider: custom
  base_url: http://litellm-proxy.arcia.svc:4000/v1
  default: simple/auto
  key_env: OPENAI_API_KEY
agent:
  auto_approve_safe_commands: false
  max_iterations: 30
platforms:
  api_server:
    direct_model_requests: true
    model_name: "agentic/auto"
    model_routes:
      agentic/free:
        model: "simple/free"
      agentic/auto:
        model: "simple/auto"
      agentic/expert:
        model: "openrouter/deepseek/deepseek-v4.1-flash"
      simple/free:
        model: "simple/free"
      simple/auto:
        model: "simple/auto"
```

---

<a id="power-users-spawn-kubernetes"></a>
## 3. Mode Power User : pods Hermes dédiés sur Kubernetes

ArcIA distingue deux profils d'utilisateurs :
- **Utilisateurs Standards** : Accèdent aux modèles `simple/*` et `agentic/*` depuis Open-WebUI et Microsoft Teams.
- **Power Users** : Accèdent à Open-WebUI (`simple/*` + `agentic/*`) **et disposent en plus d'une instance Hermes complète et dédiée directement dans le cluster Kubernetes**, garantissant une étanchéité absolue de leur environnement d'exécution, de leur système de fichiers et de leur `SOUL.md`.

### 3.1 Architecture d'un pod Power User dédié
Provisionnée à partir du gabarit [deploy/manifests/templates/hermes-poweruser.template.yaml](../../deploy/manifests/templates/hermes-poweruser.template.yaml), chaque instance comprend :
1. **Un PVC Isolé (`hermes-user-<slug>-pvc`)** : Volume persistant `ReadWriteOnce` (`10Gi` par défaut) montant `/opt/data`. Il contient exclusivement le `state.db` SQLite de l'utilisateur, sa mémoire de travail et ses fichiers.
2. **Une `SOUL.md` Personnalisée** : Injectée via ConfigMap et montée dans le profil pour adapter la posture et les règles métier de l'agent.
3. **Un Deployment & Service Dédiés** : Exécutant `nousresearch/hermes-agent:v0.2.0` avec le plugin DLP + CCR + RTK actif, son propre **Studio Kanban** (`port 9119`) et sa **Gateway API** (`port 8642`).
4. **Un Ingress Traefik Sécurisé** : Exposé sur `https://<public_fqdn>/poweruser/<slug>/studio` protégé par authentification SSO Entra ID.
5. **Un Jeton d'Inférence Nominatif (PAT)** : Raccordé sur la passerelle centrale LiteLLM avec quota budgétaire mensuel contraint.

### 3.2 Commandes d'exploitation (`Spawn-PowerUser.ps1`)
Le script [scripts/Spawn-PowerUser.ps1](../../scripts/Spawn-PowerUser.ps1) (adossé à [scripts/arcia_poweruser.py](../../scripts/arcia_poweruser.py)) pilote l'ensemble du cycle de vie :

```powershell
# 1. Spawner une nouvelle instance dédiée pour un Power User
.\scripts\Spawn-PowerUser.ps1 claire.dubois@example.org -Team finance -JobTitle "Contrôleuse de Gestion" -Manager "Marc Lefèvre"

# 2. Lister les instances Power Users actives dans le cluster
.\scripts\Spawn-PowerUser.ps1 -Action list

# 3. Mettre en veille un pod inactif (scale=0 pour libérer la RAM tout en conservant le PVC)
.\scripts\Spawn-PowerUser.ps1 claire.dubois@example.org -Action stop

# 4. Réveiller une instance
.\scripts\Spawn-PowerUser.ps1 claire.dubois@example.org -Action start

# 5. Supprimer une instance (avec option de conservation du volume)
.\scripts\Spawn-PowerUser.ps1 claire.dubois@example.org -Action destroy -KeepPvc
```

---

Voir également :
- [Chaîne de Routage & Cycle de Vie](chaine-de-routage.md)
- [Sobriété Tokenmaxing v0.5.0 (CCR & RTK)](tokenmaxing.md)
- [Passerelle d'Inférence LiteLLM](inference-litellm.md)
- [État des fonctionnalités v0.5.0](../etat-des-fonctionnalites.md)
