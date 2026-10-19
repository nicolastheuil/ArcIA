# ArcIA v0.5.2 — État réel des fonctionnalités et traçabilité

Ce tableau de bord de référence reprend l'ensemble des 25 écarts relevés lors de l'audit technique initial et consigne leur statut officiel dans la version **v0.5.2**.

La documentation d'ArcIA respecte une stricte transparence entre l'existant prouvé par le code et les cibles futures.

---

## Tableau de traçabilité technique

| # | Constat Initial | Statut v0.4 | Implémentation effective dans le code |
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
| **19**| Mode Power User et pods dédiés non harmonisés | **Résolu (v0.4)** | Simplification en 2 profils (Utilisateurs Standards & Power Users) avec pods Hermes dédiés sur K8s (`.\scripts\Spawn-PowerUser.ps1`) et accès `/v1` (`scripts/arcia_keys.py`). |
| **20**| Serveurs MCP `arcia_knowledge` et ChromaDB 50Gi dédiés absents | **Cible (v0.5.2)** | RAG embarqué dans Open-WebUI. Les connecteurs MCP dédiés sont gérés nativement dans le Setup Wizard et le catalogue de compétences. |
| **21**| Synchronisation non contrôlée de skills externes en tâche de fond | **Résolu (v0.4)** | Suppression du CronJob automatique. Synchronisation contrôlée via `scripts/Sync-Skills.ps1` / `skills/sync-skills.sh` et compétences natives montées par ConfigMap. |
| **22**| Duplication du code Python entre `services/` et les ConfigMaps K8s | **Résolu (v0.4)** | Source unique dans `services/*/app.py` et `plugin.py`, synchronisée automatiquement en ConfigMaps par `scripts/deploy.py` (`sync_service_configmaps`). |
| **23**| Versions officielles annoncées mais images flottantes (`:main`, `:latest`) | **Résolu (v0.4)** | Versions épinglées avec tags stables (`berriai/litellm:main-v1.72.6-stable`, `open-webui:v0.5.10`, `hermes-agent:v0.2.0`, `postgres:16-alpine`). |
| **24**| « Cluster K3s HA » annoncé alors que les pods sont en réplique 1 et RWO | **Clarifié (v0.4)** | Déploiement compatible avec n'importe quel cluster Kubernetes, avec un propriétaire unique par état SQLite (`state.db`). |
| **25**| « Tests DLP » ne testant pas le comportement réel | **Résolu (v0.4)** | Suite complète de 141 tests unitaires (`tests/test_dlp.py`, `test_manifests.py`, `test_deploy.py`, `test_poweruser.py`, `test_privacy.py`, `test_wizard.py`, `test_public_apis.py`, `test_error_handler.py`). |
| **26**| Traces d'erreurs Python brutes et fuites d'identifiants exposées dans Open-WebUI et Hermes | **Résolu (v0.4)** | Gestionnaires d'erreurs dédiés : `services/litellm/error_handler.py` (hook `async_post_call_failure_hook` avec masquage de clés et messages conviviaux en français) et `services/hermes/plugin.py` (`format_hermes_error` pour les Power Users). |

---

## Profils utilisateurs v0.5.2

Le parcours wizard → fichier d'instance → ConfigMap → pod LiteLLM dispose de
tests de régression synthétiques dans `tests/test_routing_pipeline.py` :
conservation des identifiants, des mappings explicites et des alias, déploiement
jusqu'au catalogue dynamique, contrôle des échecs de restart/rollout et diagnostic
sans restitution des clés. Ces tests ne constituent pas une recette sur cluster
neuf. Le [guide LiteLLM](guides/inference-litellm.md#diagnostic-du-catalogue-et-de-la-session-dadministration)
distingue un catalogue inaccessible par session invalide d'un catalogue absent.

| Profil | Environnements & canaux | Modèles configurés à l'installation | Isolation & persistance | Contrôle DLP |
|---|---|---|---|---|
| **Utilisateur standard** | Open-WebUI (`/`) + Microsoft Teams | Alias configurés par l'admin (`simple/*`, `agentic/*`) | Sessions Open-WebUI & Hermes partagé | Double barrière DLP obligatoire |
| **Power user** | Open-WebUI (`/`) + Pod Hermes dédié (`/poweruser/<slug>/studio`) | Alias configurés par l'admin (`simple/*`, `agentic/*`) | Pod K8s isolé + PVC 10Gi + `SOUL.md` propre | Double barrière DLP obligatoire |

---

## Synthèse des durcissements de sécurité (v0.5.2)

| Domaine | Mesure appliquée | Fichiers et manifests | Bénéfice de sécurité |
|---|---|---|---|
| **Verrouillage Portail WebUI** | Inscription publique coupée (`ENABLE_SIGNUP=false`), rôle par défaut utilisateur standard (`DEFAULT_USER_ROLE=user`), contrôle des modèles activé (`BYPASS_MODEL_ACCESS_CONTROL=false`), auth locale manuelle ou SSO O365/Entra ID obligatoire. | `07-open-webui.yaml`, `docker-compose.lab.yml` | Aucun compte non autorisé ne peut consommer de modèles ou s'auto-enregistrer. |
| **Double Barrière DLP** | Barrière 1 amont dans Hermes (`plugin.py` → `/sanitize` fail-closed avant SQLite/LLM) + Barrière 2 aval dans LiteLLM (`pre_call` → `/analyze` + `/anonymize`). | `services/hermes/plugin.py`, `05-litellm.yaml`, `03-presidio.yaml` | Aucun secret ni PII n'est stocké en clair dans `state.db` ni transmis à un fournisseur cloud. |
| **Isolation Réseau K8s** | Politique `arcia-default-deny-all` Ingress/Egress, règles explicites pour Traefik, WebUI, Teams, Hermes, LiteLLM, Presidio, DB et DNS 53. | `09-network-policy.yaml`, `kustomization.yaml` | Étanche les flux internes ; empêche toute évasion ou contournement du bouclier DLP. |
| **Limitation de Débit (RateLimit)** | Middleware Traefik RateLimit dédié sur l'Ingress `/v1` d'inférence. | `04-ingress.yaml`, `scripts/deploy.py` | Protège contre le déni de service et la surconsommation de crédits API. |
| **Hermes Agent Runtime** | Exécution conjointe de Studio (:9119) et Gateway (:8642), désactivation des auto-approbations risquées (`agent.auto_approve_safe_commands: false`). | `06-hermes-agent.yaml` | Conformité au principe du moindre privilège pour les exécutions d'outils agentiques. |
| **Teams Bot & Sondes K8s** | Sonde de santé dédiée `/healthz`, routage hybride (`simple/auto` et `/agent` → Hermes `agentic/auto`), masquage des journaux et injection de `LITELLM_API_KEY`. | `services/teams/app.py`, `08-teams-bot.yaml` | Évite les crash loops Kubernetes et protège les données de conversation dans les logs. |
| **Secrets & Moteur Déploiement** | Injection déclarative via `stringData` sur stdin, synchronisation automatique des ConfigMaps microservices (`sync_service_configmaps`) et câblage SSO `/studio`. | `scripts/deploy.py` | Zéro fuite de secret dans la table des processus (`ps`) et zéro dérive entre `services/` et les pods K8s. |
| **Sécurisation du Wizard Web** | Séparation propre du backend (`scripts/wizard.py`) et de l'interface (`scripts/wizard_ui/index.html`), validation stricte de l'Origin/Host et chiffrement AES-256-GCM. | `scripts/wizard.py`, `scripts/wizard_ui/index.html` | Immunité contre les attaques DNS rebinding / CSRF et code maintenable. |


## Correctif des icônes et des sauvegardes du wizard

| Fonction | Implémentation | Limite de validation |
|---|---|---|
| Icônes normal/ZDR/local | Résolution commune, projection sur la route native avec filtrage d'accès, mapping privé et vérification HTTP des SVG | Recette navigateur authentifiée distincte ; laboratoire Docker historique sans adaptateur |
| Sauvegarde/reprise d'instance | Étape dédiée, YAML complet, environnements et fichiers référencés portables, déclarations Power Users, AES-256-GCM, coffre protégé, file chiffrée et push limité à deux fichiers | Validation synthétique ; coffre à déverrouiller ; surveillance pendant la session ; extensions maison et bases/PVC sous responsabilité des admins ; reconstruction sur cluster neuf non exécutée |

Voir le [correctif détaillé](brief-icones-modeles-wizard.md). Ces changements n'attestent pas une reconstruction sur cluster neuf.
