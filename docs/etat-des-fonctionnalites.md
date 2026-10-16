# ArcIA v0.3 — État Réel des Fonctionnalités & Traçabilité de l'Audit

Ce tableau de bord de référence reprend l'ensemble des 25 écarts relevés lors de l'audit technique v0.2 (Annexe A du rapport d'audit) et consigne leur statut officiel dans la version **v0.3**.

La documentation d'ArcIA respecte désormais une stricte transparence entre l'existant prouvé par le code et les cibles futures.

---

## Tableau de Traçabilité des 25 Écarts de l'Audit v0.2

| # | Constat Audit v0.2 | Statut v0.3 | Correction / Implémentation effective dans le code |
|:---:|---|:---:|---|
| **1** | « Aucun prompt ne part vers un LLM sans caviardage » contredit par le BYOK direct | **Résolu (v0.3)** | `ENABLE_DIRECT_CONNECTIONS=false` dans Open-WebUI. 100 % des requêtes passent obligatoirement par LiteLLM et Presidio DLP. |
| **2** | « DLP Presidio Active » mais Presidio non initialisé (échec `AnalyzerEngine()`) | **Résolu (v0.3)** | `NlpEngineProvider` configuré avec modèles spaCy `fr` et `en`. Endpoints `/analyze` et `/anonymize` opérationnels. |
| **3** | Caviardage IPs / téléphones inopérant (`IP_PATTERN` non utilisé) | **Résolu (v0.3)** | `IP_PATTERN`, `PHONE_PATTERN`, `CREDIT_CARD_PATTERN`, `IBAN_PATTERN` et regex de secrets actifs et couverts par `tests/test_dlp.py`. |
| **4** | « Zéro Rétention de Données (ZDR) absolue » non forcée sur OpenRouter | **Résolu (v0.3)** | Option `extra_body: { provider: { zdr: true } }` injectée sur tous les déploiements dans `05-litellm.yaml` et `litellm-lab.yaml`. |
| **5** | « Quotas par équipe et budgets » sans base de données | **Résolu (v0.3)** | Déploiement d'un StatefulSet `litellm-db` PostgreSQL 16 (`05-litellm-db.yaml`), clés virtuelles nominatives et budgets gérés via `scripts/arcia_keys.py`. |
| **6** | « Clé BYOK chiffrée en local » persistée en clair dans `webui.db` | **Résolu (v0.3)** | Connexions directes client désactivées (`ENABLE_DIRECT_CONNECTIONS=false`). Les accès se font via les clés virtuelles gérées par la passerelle d'entreprise. |
| **7** | « ArcIA évalue la complexité en temps réel » = `openrouter/auto` opaque | **Résolu (v0.3)** | Remplacement du routeur opaque par 3 paliers fixes explicites : `arcia/standard`, `arcia/expert`, `arcia/reasoning`. |
| **8** | « Forcer un modèle par `[Modèle: Claude]` dans le prompt » inexistant | **Abandonné (v0.3)** | Retiré de la documentation. Le choix du palier s'effectue explicitement via le sélecteur d'interface ou le paramètre `model`. |
| **9** | Modèle expert pointant sur `claude-3.5-sonnet` retiré d'OpenRouter | **Résolu (v0.3)** | Palier `arcia/expert` mis à jour vers `anthropic/claude-3.7-sonnet` (avec repli vers `arcia/standard`). |
| **10**| Fallbacks déclarés hors `router_settings` avec cibles non déclarées | **Résolu (v0.3)** | Déclaration conforme sous `router_settings.fallbacks` avec replis mutuels entre modèles canoniques déclarés. |
| **11**| OmniRoute documenté en amont mais non raccordé | **Abandonné (v0.3)** | OmniRoute retiré des manifests actifs. LiteLLM Proxy assure l'ensemble du routage, des fallbacks et des budgets. |
| **12**| « Portail LAN OmniRoute :20129 » inexistant | **Abandonné (v0.3)** | Retiré avec OmniRoute. |
| **13**| Alias polluant `/v1/models` dans Open-WebUI | **Résolu (v0.3)** | Alias unifiés dans `router_settings.model_group_alias` redirigeant vers `arcia/standard` et `arcia/expert`. |
| **14**| Diagrammes montrant `POST /sanitize` au lieu de `/analyze` + `/anonymize` | **Résolu (v0.3)** | Diagrammes et codebase réalignés : LiteLLM consomme `/analyze` et `/anonymize`. |
| **15**| Variables `OPENAI_API_BASE` non lues par Hermes | **Résolu (v0.3)** | Configuration native projetée dans `~/.hermes/config.yaml` (`model.provider: custom`, `model.base_url: ...`). |
| **16**| `hermes serve` lançant un dashboard headless au lieu de la Gateway API | **Résolu (v0.3)** | Séparation propre : `hermes dashboard` sur port 9119 pour Studio, `hermes gateway` pour l'API WebSocket (port 8642). |
| **17**| « Hermes Studio » confondu avec un projet tiers | **Clarifié (v0.3)** | Studio documenté comme le tableau de bord officiel `hermes dashboard`. |
| **18**| Plugin Tokenmaxing non chargeable (pas de `register(ctx)`) et binaire RTK manquant | **Abandonné (v0.3)** | Plugin maison retiré des manifests. La compression RTK native sera intégrée en v0.4 après benchmark mesuré. |
| **19**| Mode power user local `/v1` + PAT non exposé dans l'Ingress | **Résolu (v0.3)** | Route `/v1` exposée sur Traefik Ingress (`04-ingress.yaml`) protégée par RateLimit et clés virtuelles LiteLLM nominatives (PAT). |
| **20**| Serveurs MCP `arcia_knowledge` et ChromaDB 50Gi dédiés absents | **Cible (v0.4)** | RAG embarqué dans Open-WebUI en v0.3. Les connecteurs MCP dédiés sont planifiés pour la v0.4. |
| **21**| « 539 skills miroir » synchronisés sans signature depuis GitHub | **Résolu (v0.3)** | CronJob externe suspendu (`suspend: true`). Seules les compétences d'entreprise validées et versionnées sont montées. |
| **22**| `services/presidio/README.md` décrivant des endpoints faux | **Résolu (v0.3)** | Documentation et code synchronisés : `/healthz`, `/anonymize`, `/analyze`, `/sanitize`. |
| **23**| Versions officielles annoncées mais images flottantes (`:main`, `:latest`) | **Résolu (v0.3)** | Versions épinglées avec tags stables (`berriai/litellm:main-v1.61.16`, `postgres:16-alpine`, etc.). |
| **24**| « Cluster K3s HA » annoncé alors que les pods sont en réplique 1 et RWO | **Clarifié (v0.3)** | Qualification HA identifiée comme cible d'infrastructure VMware. Le harness documente un déploiement mono-réplique résilient. |
| **25**| « 41 tests dont DLP » alors qu'aucun test ne testait le comportement DLP | **Résolu (v0.3)** | Ajout de `tests/test_dlp.py` validant activement le caviardage de phrases de référence, secrets et adresses IP. |

---

## Niveaux d'Autonomie v0.3 (Power Users & Collaborateurs)

| Niveau | Profil | Canaux Autorisés | Modèles | Quota / Budget | Contrôle DLP |
|---|---|---|---|---|---|
| **N1** | Collaborateur | Open-WebUI, Microsoft Teams | `arcia/standard` | Budget d'équipe partagé | Caviardage universel obligatoire |
| **N2** | Expert Métier | Open-WebUI (+ Outils & RAG) | `arcia/standard`, `arcia/expert` | Budget d'équipe avec alerte | Caviardage universel obligatoire |
| **N3** | Power User / Dev | IDE, Hermes local, `/v1` | Tous les paliers (`standard`, `expert`, `reasoning`) | Budget individuel nominatif | Caviardage universel obligatoire (via `/v1`) |

---

## Synthèse des Durcissements de Sécurité (v0.3)

| Domaine | Mesure Appliquée | Fichiers & Manifests | Bénéfice Sécurité |
|---|---|---|---|
| **Verrouillage Portail WebUI** | Inscription publique coupée (`ENABLE_SIGNUP=false`), rôle par défaut utilisateur standard (`DEFAULT_USER_ROLE=user`), contrôle des modèles activé (`BYPASS_MODEL_ACCESS_CONTROL=false`), auth locale manuelle ou SSO O365/Entra ID obligatoire. | `07-open-webui.yaml`, `docker-compose.lab.yml` | Aucun compte non autorisé ne peut consommer de modèles ou s'auto-enregistrer. |
| **Isolation Réseau K8s** | Politique `arcia-default-deny-all` Ingress/Egress, règles explicites pour Traefik, LiteLLM, Presidio, DB et DNS 53. | `09-network-policy.yaml`, `kustomization.yaml` | Étanche les flux internes ; empêche toute évasion ou contournement du bouclier DLP. |
| **Limitation de Débit (RateLimit)** | Middleware Traefik RateLimit dédié sur l'Ingress `/v1` d'inférence. | `04-ingress.yaml`, `scripts/deploy.py` | Protège contre le déni de service et la surconsommation de crédits API. |
| **Hermes Agent Runtime** | Exécution conjointe de Studio (:9119) et Gateway (:8642), désactivation des auto-approbations risquées (`agent.auto_approve_safe_commands: false`). | `06-hermes-agent.yaml` | Conformité au principe du moindre privilège pour les exécutions d'outils agentiques. |
| **Teams Bot & Sondes K8s** | Sonde de santé dédiée `/healthz` (évite les erreurs 405 sur `/api/teams/messages`), masquage des journaux et injection de `LITELLM_API_KEY`. | `services/teams/app.py`, `08-teams-bot.yaml` | Évite les crash loops Kubernetes et protège les données de conversation dans les logs. |
| **Secrets & Moteur Déploiement** | Injection déclarative via `stringData` sur stdin (élimine `--from-literal`), génération automatique de secrets cryptographiques forts, et masquage dans le résumé. | `scripts/deploy.py` | Zéro fuite de secret dans la table des processus (`ps`) ou l'historique shell. |
| **Sécurisation du Wizard Web** | Validation stricte de l'Origin/Host (rejet des requêtes hors localhost/127.0.0.1) et headers de protection X-Content-Type-Options / X-Frame-Options. | `scripts/wizard.py` | Immunité contre les attaques DNS rebinding et CSRF depuis un navigateur tiers. |

