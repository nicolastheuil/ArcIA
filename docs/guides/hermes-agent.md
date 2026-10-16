# Hermes Agent — Moteur d'Agents & Orchestration ArcIA (v0.3)

> **Statut : Implémenté (v0.3)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

Hermes est le moteur d'exécution agentique d'entreprise d'ArcIA. Il permet d'exécuter des agents autonomes capables de planifier des tâches complexes, d'utiliser des outils (outils locaux, shell, git, navigateurs), de collaborer et de maintenir un état persistant.

---

## 1. Fonctionnalités Clés v0.3

- **Hermes Studio Dashboard (port 9119)** :
  - Interface visuelle de pilotage de missions en mode **Kanban**.
  - Visualisation des réflexions (CoT), appels d'outils et sous-agents.
  - Protégé par une barrière d'authentification native et ForwardAuth Entra ID.
- **Hermes Gateway & API Server (port 8642)** :
  - Serveur WebSocket & HTTP permettant de connecter le client lourd natif **Hermes Desktop**.
- **Mode Local Power User (N3) via `/v1`** :
  - Permet aux développeurs d'exécuter Hermes ou leur IDE localement sur leur machine tout en bénéficiant de l'inférence managée, du caviardage DLP et du budget d'entreprise via une clé virtuelle LiteLLM (PAT).
- **Persistance Dédiée (PVC 20Gi)** :
  - Monté sous `/opt/data`. Stocke `state.db` (SQLite WAL) et la mémoire de travail de l'agent.

---

## 2. Configuration & Déploiement

Le déploiement Kubernetes est géré par [deploy/manifests/06-hermes-agent.yaml](../../deploy/manifests/06-hermes-agent.yaml).

### Configuration Native (`~/.hermes/config.yaml`) :
Contrairement aux variables génériques OpenAI, Hermes Agent utilise son fichier de configuration officiel projeté via ConfigMap :

```yaml
model:
  provider: custom
  base_url: http://litellm-proxy.arcia.svc:4000/v1
  default: arcia/standard
agent:
  auto_approve_safe_commands: true
  max_iterations: 30
```

---

<a id="power-users-agent-local"></a>
## 3. Mode Power User (N3) : Inférence Locale via `/v1` & PAT

Pour les ingénieurs et power users, certains scénarios avancés (accès VPN client temporaire, intégration directe dans l'IDE VS Code / Cursor, Computer Use) nécessitent d'exécuter les agents en local.

### 3.1 Raccordement Local à la Passerelle ArcIA

L'agent local ou l'IDE est configuré pour utiliser la passerelle d'entreprise exposée sur l'Ingress :

```bash
# Variables d'environnement pour Hermes local ou client compatible OpenAI
export OPENAI_BASE_URL="https://assistant.example.org/v1"
export OPENAI_API_KEY="<VOTRE_PAT_LITELLM_NOMINATIF>"
export OPENAI_MODEL_NAME="arcia/standard"  # ou arcia/expert, arcia/reasoning
```

### 3.2 Émission du Jeton Personnel (PAT)

L'émission et la gestion des clés virtuelles nominatives avec budget mensuel contraint s'effectuent via :
```bash
python scripts/arcia_keys.py create-user prenom.nom@entreprise.com --level N3 --team engineering
```

### 3.3 Avantages du Mode Power User v0.3
1. **DLP Systématique** : Tout prompt émis localement traverse le bouclier **Presidio DLP** sur le cluster central. Secrets et PII sont caviardés avant toute inférence cloud.
2. **Plafond Budgétaire Garanti** : Le dépassement du budget individuel bloque automatiquement les requêtes avec une erreur explicite.
3. **Zéro Rétention de Données (ZDR)** : Préservation absolue de la propriété intellectuelle.

> **Feuille de Route v0.4** : Les serveurs MCP distants dédiés (`arcia_knowledge` et `arcia_skills`) pour RAG multi-corpus font l'objet d'un lot d'évolution planifié pour la version v0.4. En v0.3, le RAG documentaire collaborateur est porté directement par Open-WebUI.

---

Voir également :
- [Chaîne de Routage & Cycle de Vie](chaine-de-routage.md)
- [Passerelle d'Inférence LiteLLM](inference-litellm.md)
- [État des Fonctionnalités v0.3](../etat-des-fonctionnalites.md)
- [Runbook Quickstart](../runbooks/quickstart.md)
