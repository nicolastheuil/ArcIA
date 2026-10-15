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
  - model_name: auto
    litellm_params:
      model: openrouter/anthropic/claude-3.5-sonnet
      api_key: os.environ/OPENROUTER_API_KEY
  - model_name: deepseek-chat
    litellm_params:
      model: openrouter/deepseek/deepseek-chat
      api_key: os.environ/OPENROUTER_API_KEY
router_settings:
  routing_strategy: usage-based-routing
  fallbacks:
    - auto: ["deepseek-chat"]
```
