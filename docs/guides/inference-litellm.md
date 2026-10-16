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
- **Passerelle LiteLLM** : [05-litellm.yaml](../../deploy/manifests/05-litellm.yaml) (Service interne `litellm-proxy.arcia.svc:4000`, exposition Ingress `/v1` avec RateLimit).
- **Base Comptable PostgreSQL** : [05-litellm-db.yaml](../../deploy/manifests/05-litellm-db.yaml) (Service `litellm-db.arcia.svc:5432`, PVC 10Gi).
- **Secrets injectés** : `litellm-secret` (`master-key`, `salt-key`, `db-password`) et `enterprise-llm-secret` (`openrouter-key`).

---

## 3. Configuration du Routage v0.3

Le ConfigMap `litellm-config` ([05-litellm.yaml](../../deploy/manifests/05-litellm.yaml)) définit la matrice de modèles de l'instance (exemple d'illustration avec routage Cloud ZDR) :

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

## 4. Gestion des Clés Virtuelles et Budgets (Power Users N3)

L'administration des clés virtuelles nominatives pour les power users et clients locaux (IDE, Hermes CLI) s'effectue via le script dédié :

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
