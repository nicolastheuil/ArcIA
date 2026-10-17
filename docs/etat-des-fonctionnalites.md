# ArcIA v0.4 — État Réel des Fonctionnalités & Traçabilité de l'Audit

Ce tableau de bord de référence reprend l'ensemble des 25 écarts relevés lors de l'audit technique v0.2 et consigne leur statut officiel dans la version **v0.4**.

La documentation d'ArcIA respecte désormais une stricte transparence entre l'existant prouvé par le code et les cibles futures.

---

## Tableau de Traçabilité des 25 Écarts de l'Audit v0.2

| # | Constat Audit v0.2 | Statut v0.4 | Correction / Implémentation effective dans le code |
|:---:|---|:---:|---|
| **1** | « Aucun prompt ne part vers un LLM sans caviardage » contredit par le BYOK direct | **Résolu (v0.4)** | `ENABLE_DIRECT_CONNECTIONS=false` dans Open-WebUI. 100 % des requêtes passent obligatoirement par Presidio DLP (double barrière Hermes + LiteLLM). |
| **2** | « DLP Presidio Active » mais Presidio non initialisé (échec `AnalyzerEngine()`) | **Résolu (v0.4)** | `NlpEngineProvider` configuré avec modèles spaCy `fr` et `en`. Endpoints `/sanitize`, `/analyze`, `/anonymize` et `/healthz` opérationnels. |
| **3** | Caviardage IPs / téléphones inopérant (`IP_PATTERN` non utilisé) | **Résolu (v0.4)** | `IP_PATTERN`, `PHONE_PATTERN`, `CREDIT_CARD_PATTERN`, `IBAN_PATTERN` et regex de secrets actifs et couverts par `tests/test_dlp.py`. |
| **4** | « Zéro Rétention de Données (ZDR) absolue » non forcée sur OpenRouter | **Résolu (v0.4)** | Option `extra_body: { provider: { zdr: true } }` injectée sur tous les déploiements dans `05-litellm.yaml` et `litellm-lab.yaml`. |
| **5** | « Quotas par équipe et budgets » sans base de données | **Résolu (v0.4)** | Déploiement d'un StatefulSet `litellm-db` PostgreSQL 16 (`05-litellm-db.yaml`), clés virtuelles nominatives et budgets gérés via `scripts/arcia_keys.py`. |
| **6** | « Clé BYOK chiffrée en local » persistée en clair dans `webui.db` | **Résolu (v0.4)** | Connexions directes client désactivées (`ENABLE_DIRECT_CONNECTIONS=false`). Les accès se font via les clés virtuelles gérées par la passerelle d'entreprise. |
| **7** | Nomenclature des modèles contradictoire entre fichiers | **Résolu (v0.4)** | Standardisation sur les 5 profils canoniques : `simple/free`, `simple/auto` (LiteLLM direct) et `agentic/free`, `agentic/auto`, `agentic/expert` (Hermes Agent). |
| **8** | « Forcer un modèle par `[Modèle: Claude]` dans le prompt » inexistant | **Abandonné (v0.4)** | Retiré de la documentation. Le choix du palier s'effectue explicitement via le sélecteur d'interface ou le paramètre `model`. |
| **9** | Modèle expert pointant sur `claude-3.5-sonnet` retiré d'OpenRouter | **Résolu (v0.4)** | Profil `agentic/expert` aligné sur `openrouter/deepseek/deepseek-v4.1-flash` avec repli automatique vers `simple/auto`. |
| **10**| Fallbacks déclarés hors `router_settings` avec cibles non déclarées | **Résolu (v0.4)** | Déclaration conforme sous `router_settings.fallbacks` avec replis mutuels entre modèles canoniques déclarés. |
| **11**| OmniRoute documenté en amont mais non raccordé | **Abandonné (v0.4)** | OmniRoute intégralement purgé du dépôt. LiteLLM Proxy assure l'ensemble du routage, des fallbacks et des budgets. |
| **12**| « Portail LAN OmniRoute :20129 » inexistant | **Abandonné (v0.4)** | Retiré avec OmniRoute. |
| **13**| Alias polluant `/v1/models` dans Open-WebUI | **Résolu (v0.4)** | Filtrage strict `MODEL_FILTER_LIST` dans Open-WebUI et alias de rétro-compatibilité masqués (`hidden: true`) dans `router_settings.model_group_alias`. |
| **14**| Diagrammes contradictoires sur `/sanitize` vs `/analyze` + `/anonymize` | **Résolu (v0.4)** | Double barrière documentée et active : Hermes appelle `/sanitize` en amont et LiteLLM appelle `/analyze` + `/anonymize` en aval (`pre_call`). |
| **15**| Variables `OPENAI_API_BASE` non lues par Hermes | **Résolu (v0.4)** | Configuration native projetée dans `~/.hermes/config.yaml` (`model.provider: custom`, `model.base_url: ...`). |
| **16**| `hermes serve` lançant un dashboard headless au lieu de la Gateway API | **Résolu (v0.4)** | Séparation propre : `hermes dashboard` sur port 9119 pour Studio, `hermes gateway` pour l'API et WebSocket (port 8642). |
| **17**| « Hermes Studio » confondu avec un projet tiers | **Clarifié (v0.4)** | Studio documenté comme le tableau de bord officiel `hermes dashboard`. |
| **18**| Plugin Tokenmaxing non chargeable (pas de `register(ctx)`) | **Résolu (v0.4)** | `services/hermes/plugin.py` implémente `register(ctx)` avec double barrière DLP fail-closed, compression réversible CCR (cache SHA-256 + `arcia_restore_tool_result`) et compaction RTK `git log`. |
| **19**| Mode power user local `/v1` + PAT et pods dédiés non harmonisés | **Résolu (v0.4)** | Double modalité N3 active : route `/v1` exposée avec RateLimit + PAT (`scripts/arcia_keys.py`) ET pods Hermes dédiés sur K8s (`scripts/arcia_poweruser.py`). |
| **20**| Serveurs MCP `arcia_knowledge` et ChromaDB 50Gi dédiés absents | **Cible (v0.5)** | RAG embarqué dans Open-WebUI en v0.4. Les connecteurs MCP dédiés sont planifiés pour la v0.5. |
| **21**| Synchronisation non contrôlée de skills externes en tâche de fond | **Résolu (v0.4)** | Suppression du CronJob automatique. Synchronisation contrôlée via `scripts/Sync-Skills.ps1` / `skills/sync-skills.sh` et compétences natives montées par ConfigMap. |
| **22**| Duplication du code Python entre `services/` et les ConfigMaps K8s | **Résolu (v0.4)** | Source unique dans `services/*/app.py` et `plugin.py`, synchronisée automatiquement en ConfigMaps par `scripts/deploy.py` (`sync_service_configmaps`). |
| **23**| Versions officielles annoncées mais images flottantes (`:main`, `:latest`) | **Résolu (v0.4)** | Versions épinglées avec tags stables (`berriai/litellm:main-v1.61.16`, `open-webui:v0.5.10`, `hermes-agent:v0.2.0`, `postgres:16-alpine`). |
| **24**| « Cluster K3s HA » annoncé alors que les pods sont en réplique 1 et RWO | **Clarifié (v0.4)** | Qualification HA identifiée comme cible d'infrastructure VMware. Le harness documente un déploiement mono-réplique résilient par état SQLite. |
| **25**| « Tests DLP » ne testant pas le comportement réel | **Résolu (v0.4)** | Suite de 87 tests unitaires (`tests/test_dlp.py`, `test_manifests.py`, `test_deploy.py`, `test_poweruser.py`, `test_privacy.py`, `test_wizard.py`, `test_public_apis.py`). |

---

## Niveaux d'Autonomie v0.4 (Power Users & Collaborateurs)

| Niveau | Profil | Canaux Autorisés | Modèles | Quota / Budget | Contrôle DLP |
|---|---|---|---|---|---|
| **N1** | Collaborateur | Open-WebUI, Microsoft Teams | `simple/free`, `simple/auto`, `agentic/free` | Budget d'équipe partagé | Double barrière DLP obligatoire |
| **N2** | Expert Métier | Open-WebUI (+ Outils & RAG), Teams (`/agent`) | `simple/*`, `agentic/free`, `agentic/auto` | Budget d'équipe avec alerte 80 % | Double barrière DLP obligatoire |
| **N3** | Power User / Dev | Pod Hermes dédié (`/poweruser/<slug>/studio`), IDE `/v1` | Les 5 profils (`simple/*`, `agentic/*` dont `agentic/expert`) | Budget individuel nominatif | Double barrière DLP obligatoire |

---

## Synthèse des Durcissements de Sécurité (v0.4)

| Domaine | Mesure Appliquée | Fichiers & Manifests | Bénéfice Sécurité |
|---|---|---|---|
| **Verrouillage Portail WebUI** | Inscription publique coupée (`ENABLE_SIGNUP=false`), rôle par défaut utilisateur standard (`DEFAULT_USER_ROLE=user`), contrôle des modèles activé (`BYPASS_MODEL_ACCESS_CONTROL=false`), auth locale manuelle ou SSO O365/Entra ID obligatoire. | `07-open-webui.yaml`, `docker-compose.lab.yml` | Aucun compte non autorisé ne peut consommer de modèles ou s'auto-enregistrer. |
| **Double Barrière DLP** | Barrière 1 amont dans Hermes (`plugin.py` → `/sanitize` fail-closed avant SQLite/LLM) + Barrière 2 aval dans LiteLLM (`pre_call` → `/analyze` + `/anonymize`). | `services/hermes/plugin.py`, `05-litellm.yaml`, `03-presidio.yaml` | Aucun secret ni PII n'est stocké en clair dans `state.db` ni transmis à un fournisseur cloud. |
| **Isolation Réseau K8s** | Politique `arcia-default-deny-all` Ingress/Egress, règles explicites pour Traefik, WebUI, Teams, Hermes, LiteLLM, Presidio, DB et DNS 53. | `09-network-policy.yaml`, `kustomization.yaml` | Étanche les flux internes ; empêche toute évasion ou contournement du bouclier DLP. |
| **Limitation de Débit (RateLimit)** | Middleware Traefik RateLimit dédié sur l'Ingress `/v1` d'inférence. | `04-ingress.yaml`, `scripts/deploy.py` | Protège contre le déni de service et la surconsommation de crédits API. |
| **Hermes Agent Runtime** | Exécution conjointe de Studio (:9119) et Gateway (:8642), désactivation des auto-approbations risquées (`agent.auto_approve_safe_commands: false`). | `06-hermes-agent.yaml` | Conformité au principe du moindre privilège pour les exécutions d'outils agentiques. |
| **Teams Bot & Sondes K8s** | Sonde de santé dédiée `/healthz`, routage hybride (`simple/auto` et `/agent` → Hermes `agentic/auto`), masquage des journaux et injection de `LITELLM_API_KEY`. | `services/teams/app.py`, `08-teams-bot.yaml` | Évite les crash loops Kubernetes et protège les données de conversation dans les logs. |
| **Secrets & Moteur Déploiement** | Injection déclarative via `stringData` sur stdin, synchronisation automatique des ConfigMaps microservices (`sync_service_configmaps`) et câblage SSO `/studio`. | `scripts/deploy.py` | Zéro fuite de secret dans la table des processus (`ps`) et zéro dérive entre `services/` et les pods K8s. |
| **Sécurisation du Wizard Web** | Séparation propre du backend (`scripts/wizard.py`) et de l'interface (`scripts/wizard_ui/index.html`), validation stricte de l'Origin/Host et chiffrement AES-256-GCM. | `scripts/wizard.py`, `scripts/wizard_ui/index.html` | Immunité contre les attaques DNS rebinding / CSRF et code maintenable. |
