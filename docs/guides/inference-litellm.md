# LiteLLM Proxy — Passerelle d'Inférence d'Entreprise

LiteLLM sert de point de passage unique pour toutes les requêtes LLM émises par les composants de la plateforme ArcIA (Open-WebUI, Hermes Agent, Bot Teams).

---

## 1. Rôles et Avantages

1. **Abstraction Complète des Fournisseurs** :
   - Expose une API compatible OpenAI (`/v1/chat/completions`, `/v1/models`).
   - Route les demandes vers les meilleurs modèles d'OpenRouter (Anthropic Claude 3.5 Sonnet, DeepSeek Chat/Coder, OpenAI GPT-4o).
2. **Catalogue Épuré & Modèles Managés Souverains** :
   - Expose deux profils d'entreprise dans le catalogue utilisateur :
     - **`ArcIA-Agentic (auto)`** : Routage automatique dynamique du meilleur modèle disponible (OpenRouter / OmniRoute) avec bascule résiliente et caviardage DLP Presidio.
     - **`ArcIA-Agentic (expert)`** : Modèle de raisonnement frontière haute fidélité, dont le comportement ou moteur sous-jacent peut être orienté par consigne directement dans le prompt.
   - Les collaborateurs disposant de clés personnelles utilisent le canal **BYOK** d'Open-WebUI sans polluer le catalogue managé de l'entreprise.
3. **Maîtrise des Budgets & Observabilité** :
   - Centralisation des métriques d'utilisation des tokens par service et utilisateur.
   - Prévention des dépassements de coûts.

---

## 2. Déploiement Kubernetes

Le service est déployé via [deploy/manifests/05-litellm.yaml](../../deploy/manifests/05-litellm.yaml) :
- **Service interne** : `litellm-proxy.arcia.svc:4000`.
- **Secret injecté** : `OPENROUTER_API_KEY` depuis `enterprise-llm-secret`.
- **Healthcheck** : Vérifiable en continu sur `/health/readiness` (HTTP 200).

---

## 3. Configuration du Routage

Le ConfigMap `litellm-config` définit la matrice de modèles :

```yaml
model_list:
  # Modèle principal souverain ArcIA : sélection automatique intelligente du meilleur modèle disponible
  - model_name: "ArcIA-Agentic (auto)"
    litellm_params:
      model: openrouter/auto
      api_key: os.environ/OPENROUTER_API_KEY
      fallbacks: ["openrouter/anthropic/claude-3.5-sonnet", "openrouter/openai/gpt-4o"]

  # Modèle d'expertise avancée ArcIA : raisonnement poussé, pilotable par consigne de modèle dans le prompt
  - model_name: "ArcIA-Agentic (expert)"
    litellm_params:
      model: openrouter/anthropic/claude-3.5-sonnet
      api_key: os.environ/OPENROUTER_API_KEY
      fallbacks: ["openrouter/openai/gpt-4o", "openrouter/auto"]

router_settings:
  model_group_alias:
    "auto": "ArcIA-Agentic (auto)"
    "ArcIA-Agentic": "ArcIA-Agentic (auto)"
    "hermes-agent": "ArcIA-Agentic (auto)"
```

---

## 4. Où et Comment Configurer les Clés d'Inférence d'Entreprise

1. **Point d'entrée standard (`arcia.config.yaml`)** :
   Dans la section `llm_gateway`, renseigner votre clé :
   ```yaml
   llm_gateway:
     openrouter_api_key: "sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
     default_model: "openrouter/auto"
     local_vllm_endpoint: ""  # optionnel: "http://vllm-internal.corp.local:8000/v1"
   ```
2. **Alternative `.env` (`secrets/arcia.env`)** :
   ```env
   OPENROUTER_API_KEY="sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   ```
3. **Application automatique** :
   Lors de l'exécution de `./scripts/Deploy-ArcIA.ps1` ou `./scripts/Apply-Secrets.ps1`, la clé est injectée dans le secret Kubernetes chiffré `enterprise-llm-secret`. Elle n'apparaît jamais dans les logs ni sur les navigateurs.

---

## 5. Raccordement Direct de Fournisseurs Spécifiques (Azure OpenAI, AWS Bedrock, Anthropic)

Si l'organisation dispose de souscriptions directes auprès d'éditeurs Cloud sans passer par OpenRouter :
1. Dans `deploy/manifests/05-litellm.yaml`, déclarer le modèle dans `model_list` :
   - **Azure OpenAI** :
     ```yaml
     - model_name: gpt-4o
       litellm_params:
         model: azure/gpt-4o
         api_base: https://mon-endpoint.openai.azure.com/
         api_key: os.environ/AZURE_OPENAI_API_KEY
     ```
   - **Anthropic Direct** :
     ```yaml
     - model_name: claude-3.5-sonnet
       litellm_params:
         model: anthropic/claude-3-5-sonnet-20241022
         api_key: os.environ/ANTHROPIC_API_KEY
     ```
2. Injecter la variable correspondante dans le secret Kubernetes via `secrets/arcia.env` et `05-litellm.yaml`.
3. Presidio DLP continue d'intercepter tout prompt avant envoi pour caviarder PII et secrets.

---

Voir également :
- [Chaîne de Routage Complète & Cycle de Vie d'une Requête](chaine-de-routage.md)
- [Gouvernance & Confidentialité Presidio DLP](confidentialite-presidio.md)
- [Routeur Complémentaire OmniRoute](omniroute.md)
- [Quickstart & Configuration Pratique](../runbooks/quickstart.md)
