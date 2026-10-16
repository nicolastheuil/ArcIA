# OmniRoute : routage complémentaire (Historique & Retrait v0.3)

> **Statut : Abandonné en v0.3 au profit de LiteLLM Proxy** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

Dans **ArcIA v0.3**, **[LiteLLM Proxy](inference-litellm.md)** (`litellm-proxy:4000`) est l'unique **passerelle LLM centrale**, assurant le raccordement au cloud, le guardrail fail-closed Presidio DLP, la gestion des quotas par équipe et les clés virtuelles nominatives pour l'ensemble des clients (Open-WebUI, Hermes Agent, Teams Bot, endpoint `/v1`).

## Décision d'Architecture v0.3

Lors de l'audit technique d'ArcIA, il a été constaté qu'OmniRoute introduisait une duplication inutile de fonctions de routage, une dépendance réseau instable à l'amorçage (`npm install` au runtime) et n'était pas raccordé à la passerelle LiteLLM. Conformément au principe Ponytail de sobriété architecturale du projet :

1. **OmniRoute a été retiré des manifests actifs** ([deploy/manifests/](../../deploy/manifests/README.md)).
2. **LiteLLM prend en charge l'ensemble des besoins** :
   - Équilibrage de charge et politiques de fallback natives (`router_settings.fallbacks`).
   - Catalogue standardisé à 3 paliers (`arcia/standard`, `arcia/expert`, `arcia/reasoning`).
   - Forçage de la Zéro Rétention de Données (ZDR).
   - Budgets mensuels nominatifs et suivi comptable via PostgreSQL.

## Rétro-compatibilité

Pour les environnements de transition conservant temporairement `omniroute.enabled: false` dans leur `arcia.config.yaml`, le moteur de déploiement universel ignore silencieusement la directive sans lever d'erreur bloquante.
