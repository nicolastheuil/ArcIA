# LiteLLM Proxy — passerelle d'inférence d'entreprise (v0.6.0)

> **Statut : Implémenté (v0.6.0)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

LiteLLM sert de point de passage unique vers les fournisseurs LLM pour tous les composants de la plateforme ArcIA (Open-WebUI en flux directs `Simple`, Hermes Agent pour les flux `Agentic`, Bot Teams, ainsi que les pods dédiés des Power Users).

---

## 1. Rôles et architecture v0.6.0

1. **Abstraction & Pivot Unique Sécurisé** :
   - Expose une API standardisée compatible OpenAI (`/v1/chat/completions`, `/v1/models`).
   - Applique la **Barrière 2 DLP Presidio** en interception pré-appel (`pre_call`, `default_on: true`) sur 100 % des requêtes.
   - Force la **Zéro Rétention de Données (ZDR)** (`extra_body: {provider: {zdr: true}}`) et l'harmonisation des paramètres (`drop_params: true`).
2. **Catalogue administré par instance** :
   - Les noms et les fournisseurs des modèles sont libres et déclarés dans le wizard.
   - Les modèles **Simple** relient directement Open-WebUI à LiteLLM.
   - Les modèles **Agentic** sont exécutés dans Hermes ; Hermes utilise ensuite LiteLLM pour ses inférences.
   - Le champ `category` choisit ce parcours, sans convention de préfixe.
3. **Persistance Relationnelle & Base Comptable (`litellm-db`)** :
   - Base de données PostgreSQL 16 dédiée ([05-litellm-db.yaml](../../deploy/manifests/05-litellm-db.yaml)).
   - Gestion des budgets d'équipes et des **clés virtuelles nominatives (PAT)** ([scripts/arcia_keys.py](../../scripts/arcia_keys.py)).
   - Suivi unifié des coûts et de la consommation par utilisateur (`X-OpenWebUI-User-Email`).

---

## 2. Déploiement Kubernetes et base comptable

Le service est déployé via :
- **Passerelle LiteLLM** : [05-litellm.yaml](../../deploy/manifests/05-litellm.yaml) (Service interne `litellm-proxy.arcia.svc:4000`, portail d'administration NodePort `30400`, API `/v1` avec RateLimit).
- **Base Comptable PostgreSQL** : [05-litellm-db.yaml](../../deploy/manifests/05-litellm-db.yaml) (Service `litellm-db.arcia.svc:5432`, PVC 10Gi).
- **Secrets injectés** : `litellm-secret` (`master-key`, `salt-key`, `db-password`, `openrouter-key`, `database-url`).
- **Gestion Dynamique GUI (`store_model_in_db`)** : Activée en base de données (`store_model_in_db: true`), permettant d'ajouter ou réassigner des modèles et des chaînes de fallback depuis l'interface web.

---

## 3. Configuration du routage v0.6.0

Le déploiement génère le ConfigMap `litellm-config` à partir du catalogue administré. Le manifeste [05-litellm.yaml](../../deploy/manifests/05-litellm.yaml) fournit le socle et le guardrail Presidio. Voici un exemple de structure avec des noms libres :

```yaml
model_list:
  # 1. Palier Simple Gratuit
  - model_name: "conversation-econome"
    litellm_params:
      model: openrouter/openrouter/free
      api_key: os.environ/OPENROUTER_API_KEY
      extra_body:
        provider:
          zdr: true

  # 2. Palier Simple Auto (Défaut)
  - model_name: "conversation"
    litellm_params:
      model: openrouter/auto
      api_key: os.environ/OPENROUTER_API_KEY
      extra_body:
        provider:
          zdr: true

  # 3. Modèle Expert DeepSeek V4.1 Flash (propulse mission-experte)
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
    - "conversation-econome": ["conversation"]
    - "conversation": ["openrouter/deepseek/deepseek-v4.1-flash"]
    - "openrouter/deepseek/deepseek-v4.1-flash": ["conversation"]
  model_group_alias:
    "arcia/free":
      model: "conversation-econome"
      hidden: true
    "arcia/auto":
      model: "conversation"
      hidden: true
    "arcia/expert":
      model: "openrouter/deepseek/deepseek-v4.1-flash"
      hidden: true
    "arcia/standard":
      model: "conversation"
      hidden: true
    "arcia/reasoning":
      model: "openrouter/deepseek/deepseek-v4.1-flash"
      hidden: true
    "auto":
      model: "conversation"
      hidden: true
    "hermes-agent":
      model: "conversation"
      hidden: true

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/DATABASE_URL
  store_model_in_db: true

litellm_settings:
  drop_params: true
```

---

## 4. Portail d'administration graphique LiteLLM UI

LiteLLM intègre nativement une interface web de gestion des modèles, des clés virtuelles et de la comptabilité adossée à PostgreSQL.

### Sécurité et périmètre d'exposition
* **Zéro exposition Internet** : L'interface d'administration LiteLLM n'est **JAMAIS** exposée sur le nom de domaine public ou sur l'Ingress Internet.
* **Accès réseau interne exclusif** : Le portail est accessible uniquement depuis le réseau d'administration interne ou VPN sur le NodePort `30400` :
  ```text
  http://<IP_NOEUD_K8S>:30400/ui/
  ```

### Authentification par clé maître (master key)
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

## Diagnostic du catalogue et de la session d'administration

Une erreur `token_not_found_in_db` dans l'onglet **Models** signifie que le jeton
présenté par le navigateur n'est pas reconnu par le proxy. Elle ne prouve pas que
`model_list` est vide. Les clés fournisseurs (OpenRouter, OpenAI, etc.), la clé
maître LiteLLM et les jetons de session ou clés virtuelles ont des rôles distincts.

1. Déconnectez la session LiteLLM, puis ouvrez `/ui/` dans une fenêtre privée et
   reconnectez-vous avec le compte administrateur et la clé maître **actuelle**
   du Secret `litellm-secret` (sauf mot de passe UI personnalisé). Utilisez un outil
   local protégé ou le presse-papiers ; ne collez aucune clé dans le chat.
2. Lancez le diagnostic en lecture seule depuis le dépôt utilisé par le wizard :

   ```powershell
   python scripts/diagnose_litellm.py --config arcia.config.yaml
   ```

   Le diagnostic compare le nombre de mappings locaux, la ConfigMap, le fichier
   monté dans le pod, la clé maître du Secret et celle du pod, puis interroge
   `/v1/models` et `/model/info` avec cette dernière. Il ne réalise aucune
   inférence, ne modifie aucune ressource et ne restitue que des compteurs,
   codes HTTP et comparaisons. `null` signifie qu'une vérification est indisponible.
   Il inspecte un pod du Deployment ; en cas de rollout en cours, contrôler aussi
   les autres répliques avant de conclure à une convergence complète.
3. Deux réponses HTTP 200 avec la clé du pod, associées à un 401 dans le navigateur,
   orientent vers le jeton du navigateur. Un champ `pod_master_matches_secret`
   faux signale une variable d'environnement périmée. Un champ
   `mounted_config_matches_configmap` faux signale une différence de fichier
   (contenu ou format) : le montage `subPath` ne se recharge pas à chaud.
4. Comparez `models_unique_count` et `admin_models_unique_count` aux compteurs
   d'entrées : plusieurs déploiements peuvent partager le même alias. Avec les
   modèles YAML et ceux persistés en base, quatre entrées ne signifient donc pas
   forcément quatre alias distincts. Le wizard reste la source déclarative ;
   n'effacez pas la base pour corriger une session invalide.
5. Avant toute réapplication, vérifiez le fichier d'instance et les mappings à
   conserver. Enregistrez ensuite le routage depuis le wizard corrigé. Il pousse
   le catalogue et les clés fournisseurs, préserve la clé maître, le sel et les
   identifiants PostgreSQL, puis vérifie le redémarrage et le rollout. Une
   sauvegarde locale sans application au cluster est explicitement signalée.

Le déploiement headless rend la ConfigMap dynamique **avant** le Deployment et
annote son PodTemplate avec les empreintes du catalogue et du Secret : une
réapplication déclenche le chargement des changements. La sauvegarde du wizard
conserve `master_key`, `salt_key`, `db_password` et tous les mappings explicites.
Les alias priment sur les noms d'affichage ; deux routes agentiques explicites
ne sont plus supprimées au profit d'alias implicites.

## 5. Gestion des clés virtuelles et budgets

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

## 6. Gestionnaire d'erreurs d'inférence et messages conviviaux

LiteLLM intègre un gestionnaire d'interception d'erreurs d'inférence ([services/litellm/error_handler.py](../../services/litellm/error_handler.py)) activé via le hook `async_post_call_failure_hook` dans `litellm_settings.callbacks`.

### 6.1 Objectifs et sécurité
1. **Zéro fuite de données sensibles** : Les identifiants de clés d'API, les URLs de workspaces privées et les traces internes de réessais ou de filtres de routage (`Filter by Data Policy`, `routing_funnel`) ne sont jamais exposés aux utilisateurs d'Open-WebUI ou de Microsoft Teams.
2. **Journalisation serveur exhaustive** : L'ingénieur plateforme et les administrateurs conservent la trace technique complète dans les journaux du pod (`kubectl logs -n arcia -l app=litellm-proxy` ou `docker logs arcia-litellm-lab`), avec masquage automatique des clés (`sk-[MASQUÉ]`).
3. **Pédagogie et orientation utilisateur** : Les erreurs techniques sont traduites en messages clairs en français structurés en Markdown, indiquant la cause réelle et l'action recommandée.

### 6.2 Matrice de correspondance des erreurs

| Cause technique sous-jacente | Statut HTTP | Message convivial affiché dans Open-WebUI / Teams |
| :--- | :---: | :--- |
| **Quota / Solde épuisé** (`Key limit exceeded`, `daily limit`) | 429 | ⚠️ **Quota d'inférence atteint** : La limite journalière d'utilisation ou le solde de crédits de la clé d'API fournisseur a été atteint. Veuillez contacter votre administrateur ArcIA ou patienter jusqu'à la réinitialisation du quota. |
| **Incompatibilité ZDR** (`Zero data retention`, modèle gratuit) | 400 | 🔒 **Politique de confidentialité (ZDR)** : Aucun modèle public gratuit ne garantit actuellement le Zéro Rétention de Données (ZDR) exigé par la gouvernance de sécurité ArcIA. Veuillez sélectionner le profil standard `conversation` ou un profil agentique qualifié. |
| **Blocage DLP Presidio** (`FAIL_CLOSED_SECRET_REJECTED`) | 422 | 🛡️ **Bouclier DLP ArcIA (Fail-Closed)** : Votre message a été bloqué par mesure de protection souveraine car il contient des secrets d'infrastructure sensibles (clé privée SSH/PEM, kubeconfig ou token). Aucune donnée n'a été transmise vers l'extérieur. |
| **Surcharge fournisseur** (`RateLimitError`, `429`) | 429 | ⏳ **Service momentanément surchargé** : Le fournisseur de modèles d'IA fait face à une forte affluence. Veuillez patienter quelques instants avant de relancer votre demande. |
| **Dépassement de contexte** (`ContextWindowExceededError`) | 400 | 📄 **Message trop volumineux** : Votre échange dépasse la capacité de contexte maximale acceptée par ce modèle. Veuillez raccourcir votre message ou démarrer une nouvelle conversation. |
| **Modèle indisponible** (`No deployments available`, `503`) | 503 | 🛠️ **Modèle temporairement indisponible** : Aucun point d'accès n'est actuellement opérationnel pour ce profil d'IA. Veuillez basculer sur un autre modèle du catalogue ou réessayer dans un instant. |
| **Authentification invalide** (`AuthenticationError`, clé révoquée) | 401 | 🔑 **Erreur d'authentification** : La clé d'API fournisseur configurée sur la passerelle est invalide ou a expiré. Veuillez contacter l'administrateur de la plateforme ArcIA. |
| **Délai dépassé** (`Timeout`) | 504 | ⏱️ **Délai de réponse dépassé** : Le modèle d'IA a mis trop de temps à répondre. Veuillez relancer votre message ou choisir un modèle plus réactif. |

---

Voir également :
- [Chaîne de routage complète et cycle de vie d'une requête](chaine-de-routage.md)
- [Gouvernance et confidentialité Presidio DLP](confidentialite-presidio.md)
- [État des fonctionnalités v0.6.0](../etat-des-fonctionnalites.md)
- [Quickstart et configuration pratique](../runbooks/quickstart.md)
