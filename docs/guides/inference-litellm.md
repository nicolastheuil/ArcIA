# LiteLLM Proxy — Passerelle d'Inférence d'Entreprise

LiteLLM sert de point de passage unique pour toutes les requêtes LLM émises par les composants de la plateforme ArcIA (Open-WebUI, Hermes Agent, Bot Teams).

---

## 1. Rôles et Avantages

1. **Abstraction Complète des Fournisseurs** :
   - Expose une API compatible OpenAI (`/v1/chat/completions`, `/v1/models`).
   - Route les demandes vers les meilleurs modèles d'OpenRouter (Anthropic Claude 3.5 Sonnet, DeepSeek Chat/Coder, OpenAI GPT-4o).
2. **Modèle Virtuel `auto`** :
   - Les clients appellent simplement `model: "auto"`.
   - LiteLLM résout automatiquement vers le modèle d'entreprise par défaut tout en gérant le failover transparent si le fournisseur primaire subit une coupure ou un rate-limit.
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
  # Modèle 'auto' d'entreprise avec bascule résiliente
  - model_name: auto
    litellm_params:
      model: openrouter/auto
      api_key: os.environ/OPENROUTER_API_KEY
      fallbacks: ["openrouter/anthropic/claude-3.5-sonnet", "openrouter/openai/gpt-4o"]

  # Modèles Cloud individuels exposés aux collaborateurs
  - model_name: claude-3.5-sonnet
    litellm_params:
      model: openrouter/anthropic/claude-3.5-sonnet
      api_key: os.environ/OPENROUTER_API_KEY

  - model_name: gpt-4o
    litellm_params:
      model: openrouter/openai/gpt-4o
      api_key: os.environ/OPENROUTER_API_KEY

  - model_name: deepseek-chat
    litellm_params:
      model: openrouter/deepseek/deepseek-chat
      api_key: os.environ/OPENROUTER_API_KEY
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
