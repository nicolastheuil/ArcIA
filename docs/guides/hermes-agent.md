# Hermes Agent — Moteur d'Agents, Studio & Mode Power User (v0.4)

> **Statut : Implémenté (v0.4)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

Hermes est le moteur d'exécution agentique d'entreprise d'ArcIA. Il permet d'exécuter des agents autonomes capables de planifier des tâches complexes, d'utiliser des outils (outils locaux, shell, git, recherche web, APIs publiques), de compresser leur contexte (CCR/RTK) et de maintenir un état persistant.

---

## 1. Fonctionnalités Clés v0.4

- **Hermes Studio Dashboard (port 9119)** :
  - Interface visuelle de pilotage de missions en mode **Kanban**.
  - Visualisation des réflexions (Chain of Thought), appels d'outils et sous-agents.
  - Protégé par authentification native et middleware Traefik ForwardAuth Entra ID (`/studio`).
- **Hermes Gateway & API Server (port 8642) — Moteur des Profils `agentic/*`** :
  - Expose une API standardisée compatible OpenAI (`/v1`).
  - Prend en charge les sessions agentiques d'Open-WebUI (`agentic/free`, `agentic/auto`, `agentic/expert`) ainsi que les missions déléguées depuis Microsoft Teams via la commande `/agent <mission>`.
  - Chaque conversation agentique dispose d'un historique persistant dans `state.db`, de compétences partagées (`/opt/shared-skills`) et du plugin de gouvernance [services/hermes/plugin.py](../../services/hermes/plugin.py) (Barrière 1 DLP Presidio + compression réversible CCR + RTK).
- **Double Modalité Power User (N3)** :
  1. **Pod Hermes Dédié sur Kubernetes** (`/poweruser/<slug>/studio`) via [scripts/arcia_poweruser.py](../../scripts/arcia_poweruser.py).
  2. **Accès API Direct via `/v1`** pour les IDEs locaux (VS Code, Cursor) et outils CLI via une clé virtuelle LiteLLM nominative (PAT) générée par [scripts/arcia_keys.py](../../scripts/arcia_keys.py).
- **Persistance Dédiée (PVC 20Gi)** :
  - Monté sous `/opt/data`. Stocke `state.db` (SQLite WAL) et l'espace de travail de l'agent.

---

## 2. Configuration & Déploiement

Le déploiement Kubernetes est géré par [deploy/manifests/06-hermes-agent.yaml](../../deploy/manifests/06-hermes-agent.yaml). Le plugin [services/hermes/plugin.py](../../services/hermes/plugin.py) est injecté dans le ConfigMap `hermes-governance-plugin` par `scripts/deploy.py`.

### Configuration Native (`~/.hermes/config.yaml`) :
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
## 3. Mode Power User (N3) : Double Modalité (Pods K8s Dédiés & API `/v1`)

ArcIA v0.4 offre aux Power Users (ingénieurs IA, développeurs, experts métier N3) deux modalités complémentaires et gouvernées :

### 3.1 Modalité A : Pods Hermes Dédiés sur Kubernetes
Chaque Power User peut disposer d'une **instance Hermes complète et dédiée directement dans le cluster Kubernetes**, garantissant une étanchéité absolue de son environnement d'exécution, de son système de fichiers et de sa `SOUL.md`.

Provisionnée à partir du gabarit [deploy/manifests/templates/hermes-poweruser.template.yaml](../../deploy/manifests/templates/hermes-poweruser.template.yaml), chaque instance comprend :
1. **Un PVC Isolé (`hermes-user-<slug>-pvc`)** : Volume persistant `ReadWriteOnce` (10Gi) montant `/opt/data`. Il contient exclusivement le `state.db` SQLite de l'utilisateur, sa mémoire de travail et ses fichiers.
2. **Une `SOUL.md` Personnalisée** : Injectée via ConfigMap et montée dans le profil pour adapter la posture et les règles métier de l'agent.
3. **Un Deployment & Service Dédiés** : Exécutant `nousresearch/hermes-agent:v0.2.0` avec le plugin DLP + CCR + RTK actif, son propre **Studio Kanban** (`port 9119`) et sa **Gateway API** (`port 8642`).
4. **Un Ingress Traefik Sécurisé** : Exposé sur `https://<public_fqdn>/poweruser/<slug>/studio` protégé par authentification SSO Entra ID.
5. **Un Jeton d'Inférence Nominatif (PAT)** : Raccordé sur la passerelle centrale LiteLLM avec quota budgétaire mensuel contraint.

#### Commandes d'Exploitation (`scripts/arcia_poweruser.py`)
Le script d'orchestration [scripts/arcia_poweruser.py](../../scripts/arcia_poweruser.py) (ou son wrapper PowerShell [scripts/Spawn-PowerUser.ps1](../../scripts/Spawn-PowerUser.ps1)) pilote le cycle de vie :

```bash
# 1. Spawner une nouvelle instance dédiée pour un collaborateur
python scripts/arcia_poweruser.py spawn claire.dubois@example.org --team finance --job-title "Contrôleuse de Gestion" --manager "Marc Lefèvre"

# 2. Lister les instances Power Users actives dans le cluster
python scripts/arcia_poweruser.py list

# 3. Mettre en veille un pod inactif (scale=0 pour libérer la RAM tout en conservant le PVC)
python scripts/arcia_poweruser.py stop claire.dubois@example.org

# 4. Réveiller une instance
python scripts/arcia_poweruser.py start claire.dubois@example.org

# 5. Supprimer une instance (avec option de conservation du volume)
python scripts/arcia_poweruser.py destroy claire.dubois@example.org --keep-pvc
```

### 3.2 Modalité B : Accès API Direct `/v1` par Clé Virtuelle (PAT)
Pour les développeurs souhaitant connecter leur IDE local (VS Code, Cursor, Continue) ou un client CLI :
1. L'administrateur émet une clé virtuelle nominative via [scripts/arcia_keys.py](../../scripts/arcia_keys.py) :
   ```bash
   python scripts/arcia_keys.py create --user dev-lead@example.org --tier N3 --budget 25 --duration 30
   ```
2. L'utilisateur configure son client sur `https://<public_fqdn>/v1` avec sa clé `sk-arcia-...` et accède aux 5 profils canoniques sous protection RateLimit, Presidio DLP et plafond budgétaire PostgreSQL.

---

Voir également :
- [Chaîne de Routage & Cycle de Vie](chaine-de-routage.md)
- [Sobriété Tokenmaxing v0.4 (CCR & RTK)](tokenmaxing.md)
- [Passerelle d'Inférence LiteLLM](inference-litellm.md)
- [État des Fonctionnalités v0.4](../etat-des-fonctionnalites.md)
