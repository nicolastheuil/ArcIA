# LiteLLM Proxy — Passerelle d'Inférence d'Entreprise (v0.3)

> **Statut : Implémenté (v0.3)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

LiteLLM sert de point de passage unique pour toutes les requêtes LLM émises par les composants de la plateforme ArcIA (Open-WebUI, Hermes Agent, Bot Teams, ainsi que les postes des power users via `/v1`).

---

## 1. Rôles et Architecture v0.3

1. **Abstraction & Pivot Unique Sécurisé** :
   - Expose une API standardisée compatible OpenAI (`/v1/chat/completions`, `/v1/models`).
   - Route les demandes vers les moteurs configurés par l'organisation (fournisseurs Cloud avec ZDR forcée ou backends locaux souverains).
2. **Catalogue Épuré à 3 Paliers Canoniques** :
   - **`arcia/free`** : Découverte et qualification sans coût via OpenRouter Free (`openrouter/openrouter/free`).
   - **`arcia/auto`** *(Défaut)* : Routage automatique intelligent équilibrant performance et coût (`openrouter/auto`).
   - **`arcia/expert`** : Modèle de pointe pour l'expertise métier, l'architecture logicielle et les requêtes dynamiques (`openrouter/*`).
   > **Note d'agnosticisme & Souscriptions :** ArcIA est un harness d'entreprise agnostique. Sans souscription API ni moteur d'inférence local configuré sur l'instance, aucun modèle n'est actif. Les 3 paliers ci-dessus constituent un contrat d'interface virtuel que chaque instance mappe vers ses propres fournisseurs (Azure OpenAI, AWS Bedrock, Mistral AI, OpenRouter) ou ses propres serveurs GPU on-premise (vLLM, Ollama).
3. **Persistance Relationnelle & Base Comptable (`litellm-db`)** :
   - Base de données PostgreSQL 16 dédiée ([05-litellm-db.yaml](../../deploy/manifests/05-litellm-db.yaml)).
   - Gestion des budgets d'équipes et des **clés virtuelles nominatives (PAT)** pour les power users N3.
   - Suivi unifié des coûts et de la consommation par utilisateur (`X-OpenWebUI-User-Email`).

---

## 2. Déploiement Kubernetes & Base Comptable

Le service est déployé via :
- **Passerelle LiteLLM** : [05-litellm.yaml](../../deploy/manifests/05-litellm.yaml) (Service interne `litellm-proxy.arcia.svc:4000`, portail d'administration NodePort `30400` sur la VIP du cluster, API power users via Ingress `/v1` avec RateLimit).
- **Base Comptable PostgreSQL** : [05-litellm-db.yaml](../../deploy/manifests/05-litellm-db.yaml) (Service `litellm-db.arcia.svc:5432`, PVC 10Gi).
- **Secrets injectés** : `litellm-secret` (`master-key`, `salt-key`, `db-password`) et `enterprise-llm-secret` (`openrouter-key`).
- **Gestion Dynamique GUI (`store_model_in_db`)** : Activée en base de données (`STORE_MODEL_IN_DB: "True"`), permettant d'ajouter, modifier ou réassigner les modèles réels et les chaînes de fallback directement depuis l'interface web sans éditer de fichier YAML ni redémarrer les pods.

---

## 3. Configuration du Routage v0.3

Le ConfigMap `litellm-config` ([05-litellm.yaml](../../deploy/manifests/05-litellm.yaml)) définit la matrice initiale de modèles de l'instance :

```yaml
model_list:
  # 1. Palier Gratuit : Découverte et qualification sans coût
  - model_name: "arcia/free"
    litellm_params:
      model: openrouter/openrouter/free
      api_key: os.environ/OPENROUTER_API_KEY

  # 2. Palier Auto (Défaut) : Routage automatique intelligent
  - model_name: "arcia/auto"
    litellm_params:
      model: openrouter/auto
      api_key: os.environ/OPENROUTER_API_KEY

  # 3. Palier Expert : Choix dynamique de modèle ou auto
  - model_name: "arcia/expert"
    litellm_params:
      model: openrouter/auto
      api_key: os.environ/OPENROUTER_API_KEY

  # 4. Modèles dynamiques OpenRouter (pour sélection libre par l'expert dans le prompt)
  - model_name: "openrouter/*"
    litellm_params:
      model: "openrouter/*"
      api_key: os.environ/OPENROUTER_API_KEY

router_settings:
  fallbacks:
    - "arcia/free": ["arcia/auto"]
    - "arcia/auto": ["arcia/expert"]
    - "arcia/expert": ["arcia/auto"]
  model_group_alias:
    "arcia/standard":
      model: "arcia/auto"
      hidden: true
    "arcia/reasoning":
      model: "arcia/expert"
      hidden: true
    "auto":
      model: "arcia/auto"
      hidden: true
    "hermes-agent":
      model: "arcia/auto"
      hidden: true

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/DATABASE_URL
  store_model_in_db: true

litellm_settings:
  drop_params: true
```

---

## 4. Portail d'Administration Graphique LiteLLM UI (VIP K3s)

LiteLLM intègre nativement une interface web de gestion des modèles, des clés virtuelles et de la comptabilité adossée à PostgreSQL.

### Sécurité & Périmètre d'Exposition
* **Zéro exposition Internet** : L'interface d'administration LiteLLM n'est **JAMAIS** exposée sur le nom de domaine public ou sur l'Ingress Internet. Les requêtes publiques vers `/ui` sont rejetées (HTTP 404).
* **Accès LAN / VIP K3s exclusif** : Le portail est accessible uniquement depuis le réseau d'administration interne ou VPN via la VIP du cluster sur le NodePort `30400` :
  ```text
  http://<IP_VIP_K3S>:30400/ui/
  ```

### Authentification par Master Key
La connexion requiert la **Master Key** cryptographique générée au déploiement (`sk-arcia-...`), stockée dans le Secret Kubernetes `litellm-secret`.

* **Copie directe dans le presse-papiers (PowerShell)** :
  ```powershell
  [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String((.\scripts\Invoke-K3s.ps1 "get secret litellm-secret -n arcia -o jsonpath={.data.master-key}" -Node "<IP_NOEUD>"))).Trim() | Set-Clipboard
  ```
* **Lecture console (Bash SSH)** :
  ```bash
  sudo k3s kubectl get secret litellm-secret -n arcia -o jsonpath="{.data.master-key}" | base64 -d
  ```

### Configuration Dynamique des Modèles et Chaînes de Fallback
Grâce à `store_model_in_db: true`, les modèles peuvent être réassignés en direct dans la base de données sans modifier de fichier YAML ni redémarrer de Pod :

1. Accédez à **Models + Endpoints** > **+ Add Model**.
2. Renseignez l'alias d'entreprise dans **Model Name** (ex: `arcia/auto` ou `arcia/vision`).
3. Spécifiez le modèle amont dans **LiteLLM Model Name** (ex: `openrouter/auto`, `azure/gpt-4o`, ou endpoint souverain local `openai/vllm-model`).
4. Forcez le Zéro Data Retention dans **Extra Body** (si fournisseur cloud) :
   ```json
   {
     "provider": {
       "zdr": true
     }
   }
   ```
5. Définissez la chaîne de repli dans **Fallback Models** (ex: `["arcia/auto"]`).
6. Cliquez sur **Save** : le modèle porte le badge *Database* et devient immédiatement actif pour LiteLLM, Hermes Agent et Teams.
7. **Exposition dans Open-WebUI (Zéro Bypass Hermes)** : Rappelez-vous qu'Open-WebUI ne dialogue jamais en direct avec LiteLLM. Pour rendre ce nouveau modèle disponible dans la liste déroulante des utilisateurs Open-WebUI, ajoutez son alias dans `platforms.api_server.model_routes` de Hermes Agent ([06-hermes-agent.yaml](../../deploy/manifests/06-hermes-agent.yaml)) et rechargez l'agent. Voir la [Chaîne de Routage](chaine-de-routage.md#5-comment-modifier-ou-ajouter-des-modèles-sans-contourner-hermes).

---

## 5. Gestion des Clés Virtuelles et Budgets (Power Users N3)

L'administration des clés virtuelles nominatives pour les power users et clients locaux (IDE, Hermes CLI) s'effectue via le portail UI (onglet **Virtual Keys**) ou via le script en ligne de commande :

```bash
# Créer une clé nominative avec budget mensuel contraint
python scripts/arcia_keys.py create-user jean.dupont@entreprise.com --level N3 --team engineering

# Lister les clés et leur consommation
python scripts/arcia_keys.py list

# Révoquer une clé
python scripts/arcia_keys.py revoke sk-xxxx
```

---

Voir également :
- [Chaîne de Routage Complète & Cycle de Vie d'une Requête](chaine-de-routage.md)
- [Gouvernance & Confidentialité Presidio DLP](confidentialite-presidio.md)
- [État des fonctionnalités v0.3](../etat-des-fonctionnalites.md)
- [Quickstart & Configuration Pratique](../runbooks/quickstart.md)

