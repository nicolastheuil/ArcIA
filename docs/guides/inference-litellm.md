# LiteLLM Proxy — Passerelle d'Inférence d'Entreprise (v0.3)

> **Statut : Implémenté (v0.3)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

LiteLLM sert de point de passage unique pour toutes les requêtes LLM émises par les composants de la plateforme ArcIA (Open-WebUI, Hermes Agent, Bot Teams, ainsi que les postes des power users via `/v1`).

---

## 1. Rôles et Architecture v0.3

1. **Abstraction & Pivot Unique Sécurisé** :
   - Expose une API standardisée compatible OpenAI (`/v1/chat/completions`, `/v1/models`).
   - Route les demandes vers les moteurs configurés par l'organisation (fournisseurs Cloud avec ZDR forcée ou backends locaux souverains).
2. **Catalogue Épuré à 3 Paliers Canoniques** :
   - **`arcia/standard`** *(Défaut)* : Modèle polyvalent, rapide et économique pour tous collaborateurs (N1, N2, N3).
   - **`arcia/expert`** : Modèle agentique de pointe pour l'expertise métier, l'architecture logicielle et le code complexe.
   - **`arcia/reasoning`** : Modèle de réflexion profonde pour l'analyse critique, la planification et la logique formelle.
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

Le ConfigMap `litellm-config` ([05-litellm.yaml](../../deploy/manifests/05-litellm.yaml)) définit la matrice initiale de modèles de l'instance (exemple d'illustration avec routage Cloud ZDR) :

```yaml
model_list:
  - model_name: "arcia/standard"
    litellm_params:
      model: openrouter/anthropic/claude-3-5-haiku
      api_key: os.environ/OPENROUTER_API_KEY
      extra_body:
        provider:
          zdr: true

  - model_name: "arcia/expert"
    litellm_params:
      model: openrouter/anthropic/claude-3.7-sonnet
      api_key: os.environ/OPENROUTER_API_KEY
      extra_body:
        provider:
          zdr: true

  - model_name: "arcia/reasoning"
    litellm_params:
      model: openrouter/deepseek/deepseek-r1
      api_key: os.environ/OPENROUTER_API_KEY
      extra_body:
        provider:
          zdr: true

router_settings:
  fallbacks:
    - "arcia/standard": ["arcia/expert"]
    - "arcia/expert": ["arcia/standard"]
    - "arcia/reasoning": ["arcia/expert"]
  model_group_alias:
    "ArcIA-Agentic (auto)": "arcia/standard"
    "ArcIA-Agentic (expert)": "arcia/expert"
    "auto": "arcia/standard"
    "hermes-agent": "arcia/standard"
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
2. Renseignez l'alias d'entreprise dans **Model Name** (ex: `arcia/standard`).
3. Spécifiez le modèle amont dans **LiteLLM Model Name** (ex: `openrouter/auto`, `azure/gpt-4o`, ou endpoint souverain local `openai/vllm-model`).
4. Forcez le Zéro Data Retention dans **Extra Body** :
   ```json
   {
     "provider": {
       "zdr": true
     }
   }
   ```
5. Définissez la chaîne de repli dans **Fallback Models** (ex: `["arcia/expert"]`).
6. Cliquez sur **Save** : le modèle porte le badge *Database* et devient immédiatement actif pour Open-WebUI, Hermes Agent et Teams.

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

