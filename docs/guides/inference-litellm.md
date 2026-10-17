# LiteLLM Proxy — Passerelle d'Inférence d'Entreprise (v0.4)

> **Statut : Implémenté (v0.4)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

LiteLLM sert de point de passage unique vers les fournisseurs LLM pour tous les composants de la plateforme ArcIA (Open-WebUI en flux directs `simple/*`, Hermes Agent pour les flux `agentic/*`, Bot Teams, ainsi que les pods dédiés des Power Users).

---

## 1. Rôles et Architecture v0.4

1. **Abstraction & Pivot Unique Sécurisé** :
   - Expose une API standardisée compatible OpenAI (`/v1/chat/completions`, `/v1/models`).
   - Applique la **Barrière 2 DLP Presidio** en interception pré-appel (`pre_call`, `default_on: true`) sur 100 % des requêtes.
   - Force la **Zéro Rétention de Données (ZDR)** (`extra_body: {provider: {zdr: true}}`) et l'harmonisation des paramètres (`drop_params: true`).
2. **Catalogue Unifié des Profils Canoniques** :
   - **`simple/free`** : Découverte et qualification sans coût via OpenRouter Free (`openrouter/openrouter/free`).
   - **`simple/auto`** *(Défaut)* : Routage automatique intelligent équilibrant performance et coût (`openrouter/auto`).
   - **`openrouter/deepseek/deepseek-v4.1-flash`** : Moteur haute performance propulsant le profil **`agentic/expert`** exposé par Hermes Agent.
   - **`openrouter/*`** : Route générique avec ZDR forcé permettant la sélection dynamique de modèles par les profils autorisés.
   > **Note d'agnosticisme & Souscriptions :** ArcIA est un harness d'entreprise agnostique. Ces profils constituent un contrat d'interface virtuel que chaque instance mappe vers ses fournisseurs souscrits (OpenRouter, Azure OpenAI, AWS Bedrock, Mistral AI) ou ses serveurs GPU on-premise (`local_vllm_endpoint`).
3. **Persistance Relationnelle & Base Comptable (`litellm-db`)** :
   - Base de données PostgreSQL 16 dédiée ([05-litellm-db.yaml](../../deploy/manifests/05-litellm-db.yaml)).
   - Gestion des budgets d'équipes et des **clés virtuelles nominatives (PAT)** ([scripts/arcia_keys.py](../../scripts/arcia_keys.py)).
   - Suivi unifié des coûts et de la consommation par utilisateur (`X-OpenWebUI-User-Email`).

---

## 2. Déploiement Kubernetes & Base Comptable

Le service est déployé via :
- **Passerelle LiteLLM** : [05-litellm.yaml](../../deploy/manifests/05-litellm.yaml) (Service interne `litellm-proxy.arcia.svc:4000`, portail d'administration NodePort `30400`, API `/v1` avec RateLimit).
- **Base Comptable PostgreSQL** : [05-litellm-db.yaml](../../deploy/manifests/05-litellm-db.yaml) (Service `litellm-db.arcia.svc:5432`, PVC 10Gi).
- **Secrets injectés** : `litellm-secret` (`master-key`, `salt-key`, `db-password`, `openrouter-key`, `database-url`).
- **Gestion Dynamique GUI (`store_model_in_db`)** : Activée en base de données (`store_model_in_db: true`), permettant d'ajouter ou réassigner des modèles et des chaînes de fallback depuis l'interface web.

---

## 3. Configuration du Routage v0.4

Le ConfigMap `litellm-config` ([05-litellm.yaml](../../deploy/manifests/05-litellm.yaml)) définit la matrice de modèles et le guardrail Presidio :

```yaml
model_list:
  # 1. Palier Simple Gratuit
  - model_name: "simple/free"
    litellm_params:
      model: openrouter/openrouter/free
      api_key: os.environ/OPENROUTER_API_KEY
      extra_body:
        provider:
          zdr: true

  # 2. Palier Simple Auto (Défaut)
  - model_name: "simple/auto"
    litellm_params:
      model: openrouter/auto
      api_key: os.environ/OPENROUTER_API_KEY
      extra_body:
        provider:
          zdr: true

  # 3. Modèle Expert DeepSeek V4.1 Flash (propulse agentic/expert)
  - model_name: "openrouter/deepseek/deepseek-v4.1-flash"
    litellm_params:
      model: openrouter/deepseek/deepseek-v4.1-flash
      api_key: os.environ/OPENROUTER_API_KEY
      extra_body:
        provider:
          zdr: true

  # 4. Modèles dynamiques OpenRouter
  - model_name: "openrouter/*"
    litellm_params:
      model: "openrouter/*"
      api_key: os.environ/OPENROUTER_API_KEY
      extra_body:
        provider:
          zdr: true

guardrails:
  - guardrail_name: "arcia-presidio-dlp"
    litellm_params:
      guardrail: presidio
      mode: "pre_call"
      presidio_analyzer_api_base: "http://presidio-dlp.arcia.svc:8080"
      presidio_anonymizer_api_base: "http://presidio-dlp.arcia.svc:8080"
      default_on: true

router_settings:
  fallbacks:
    - "simple/free": ["simple/auto"]
    - "simple/auto": ["openrouter/deepseek/deepseek-v4.1-flash"]
    - "openrouter/deepseek/deepseek-v4.1-flash": ["simple/auto"]
  model_group_alias:
    "arcia/free":
      model: "simple/free"
      hidden: true
    "arcia/auto":
      model: "simple/auto"
      hidden: true
    "arcia/expert":
      model: "openrouter/deepseek/deepseek-v4.1-flash"
      hidden: true
    "arcia/standard":
      model: "simple/auto"
      hidden: true
    "arcia/reasoning":
      model: "openrouter/deepseek/deepseek-v4.1-flash"
      hidden: true
    "auto":
      model: "simple/auto"
      hidden: true
    "hermes-agent":
      model: "simple/auto"
      hidden: true

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/DATABASE_URL
  store_model_in_db: true

litellm_settings:
  drop_params: true
```

---

## 4. Portail d'Administration Graphique LiteLLM UI

LiteLLM intègre nativement une interface web de gestion des modèles, des clés virtuelles et de la comptabilité adossée à PostgreSQL.

### Sécurité & Périmètre d'Exposition
* **Zéro exposition Internet** : L'interface d'administration LiteLLM n'est **JAMAIS** exposée sur le nom de domaine public ou sur l'Ingress Internet.
* **Accès réseau interne exclusif** : Le portail est accessible uniquement depuis le réseau d'administration interne ou VPN sur le NodePort `30400` :
  ```text
  http://<IP_NOEUD_K8S>:30400/ui/
  ```

### Authentification par Master Key
La connexion requiert la **Master Key** cryptographique générée au déploiement (`sk-arcia-...`), stockée dans le Secret Kubernetes `litellm-secret`.

* **Copie directe dans le presse-papiers (PowerShell)** :
  ```powershell
  [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String((.\scripts\Invoke-K3s.ps1 "get secret litellm-secret -n arcia -o jsonpath={.data.master-key}" -Node "<IP_NOEUD>"))).Trim() | Set-Clipboard
  ```
* **Lecture console (Bash)** :
  ```bash
  kubectl get secret litellm-secret -n arcia -o jsonpath="{.data.master-key}" | base64 -d
  ```

---

## 5. Gestion des Clés Virtuelles et Budgets

L'administration des clés virtuelles nominatives s'effectue via le portail UI (onglet **Virtual Keys**) ou via le script [scripts/arcia_keys.py](../../scripts/arcia_keys.py) :

```bash
# Créer une clé nominative avec budget mensuel contraint
python scripts/arcia_keys.py create --user jean.dupont@example.org --profile poweruser --budget 50 --duration 30d

# Lister les clés et leur consommation
python scripts/arcia_keys.py list

# Révoquer une clé
python scripts/arcia_keys.py revoke --key sk-xxxx
```

---

Voir également :
- [Chaîne de Routage Complète & Cycle de Vie d'une Requête](chaine-de-routage.md)
- [Gouvernance & Confidentialité Presidio DLP](confidentialite-presidio.md)
- [État des fonctionnalités v0.4](../etat-des-fonctionnalites.md)
- [Quickstart & Configuration Pratique](../runbooks/quickstart.md)
