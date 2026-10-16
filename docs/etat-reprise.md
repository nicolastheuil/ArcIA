# État de reprise d’ArcIA — 15 octobre 2026 (v0.2 Transformation)

**Unique handoff courant.** L'ancien état v0.1 a été archivé sur la branche `archive/v0.1-legacy` et figé sous le tag `v0.1-legacy-archive`.
La cible d'exécution actuelle est le socle unifié et épuré **ArcIA v0.2**, déployé et vérifié sur le cluster K3s 3 nœuds (`node-01`, `node-02`, `node-03`).

---

## 1. Synthèse de la Transformation ArcIA v0.2

Conformément au plan initial de transformation v0.2 :
1. **Purge intégrale de la dette technique v0.1** :
   - Suppression des 43 anciens namespaces (`arcia-access`, `arcia-data`, `arcia-hermes`, `arcia-routing`, `arcia-user-p01..p32`, etc.).
   - Suppression des 116 scripts obsolètes, des briques OmniRoute, Keycloak, Kilo, CNPG non qualifiées.
   - Création du namespace unique et unifié : `arcia`.
   - Établissement de la StorageClass par défaut VMware CSI : `arcia-vsphere`.

2. **Fondations Ingress, TLS & Sécurité** :
   - Traefik déployé en DaemonSet sur les 3 nœuds avec liaison directe `hostPort` sur les ports **80** et **443**.
   - Restauration et injection du certificat Let's Encrypt production officiel (émis pour les domaines du tenant, ex: `assistant.example.org`) dans le secret Kubernetes `arcia-tls-cert`.
   - Ingress unifié (`arcia-public-ingress` et `arcia-studio-ingress`) opérationnel en HTTPS direct avec cadenas vert validé à travers le NAT du pare-feu d'entreprise.
   - Middleware Traefik ForwardAuth préparé pour `oauth2-proxy` et Microsoft Entra ID.

3. **Passerelle DLP & Confidentialité (Presidio)** :
   - Microservice Presidio DLP (`presidio-dlp:8080`) déployé dans le namespace `arcia`.
   - Règle de caviardage automatique : PII (emails, téléphones), mots de passe et clés d'API.
   - Validation en direct : `curl /sanitize` confirme le remplacement par `[ARCIA_EMAIL_1]` et détection d'entités sans altération de l'infrastructure.

4. **Passerelle d'Inférence LLM d'Entreprise (LiteLLM)** :
   - Service `litellm-proxy:4000` déployé et opérationnel.
   - Routage automatique vers OpenRouter (`anthropic/claude-3.5-sonnet`, `deepseek/deepseek-chat`, etc.) avec fallbacks résilients.
   - Readiness vérifiée via `/health/readiness` (HTTP 200).

5. **Catalogue de Compétences Partagées (Skills)** :
   - Répertoire partagé synchronisé `/var/data/arcia/shared-skills` présent et accessible en lecture/écriture sur les trois nœuds du cluster.
   - Catalogues intégrés : `anthropics/anthropic-quickstarts`, `vercel/ai-sdk`, `obra/superpowers`.
   - Script de synchronisation versionné : `skills/sync-skills.sh`.

6. **Moteur d'Agents Hermes v0.2 & Studio** :
   - Image runtime standard `docker.io/arcia/hermes-agent:v0.2` déployée sur PVC `hermes-user-pvc` (20Gi).
   - Double exposition réussie :
     - **Hermes Studio Dashboard (port 9119)** pour le pilotage visuel et Kanban multi-agents.
     - **Hermes Gateway API (port 8642)** en WebSocket/HTTP pour connecter Hermes Desktop et les backends distants.
   - Plugin de Tokenmaxing ArcIA (`arcia_tokenmaxing.py`) injecté pour la compression de contexte et l'économie de tokens.
   - Auth gate Hermes passée avec succès via authentification basique renforcée (`admin`).

7. **Portail Collaborateur Open-WebUI** :
   - Déploiement `open-webui:8080` avec persistance `open-webui-pvc` (20Gi).
   - Raccordement double : LiteLLM Proxy (`litellm-proxy.arcia.svc:4000/v1`) et Hermes Gateway (`hermes-studio.arcia.svc:8642/v1`).
   - Préconfiguration déclarative clean install : `OPENAI_API_KEYS`, `ENABLE_OLLAMA_API=false`, `ENABLE_SUBAGENTS=true`, `ENABLE_DIRECT_CONNECTIONS=true` (BYOK), `TASK_MODEL=auto`, `WEBUI_NAME=ArcIA` et `ENABLE_PERSISTENT_CONFIG=false`.
   - Modèles disponibles dès la première connexion : `auto`, `claude-3.5-sonnet`, `gpt-4o`, `deepseek-chat`, `hermes-agent`.
   - Santé validée via `/health` (HTTP 200).

8. **Adaptateur Microsoft Teams Bot** :
   - Service `teams-bot-adapter:3978` basé sur le SDK Bot Framework Python.
   - Routes `/api/teams/messages` et `/health` opérationnelles.
   - Prêt pour les conversations DM 1:1 et les mentions `@ArcIA` en canaux Teams.

9. **OmniRoute v3.8.51 & Outillage Agentique Avancé Qualifiés en Direct** :
   - **OmniRoute v3.8.51** : Déployé sur PVC 5Gi (`omniroute-data-pvc`), pod `1/1 Running` sans redémarrage, endpoints HTTP API (:20128) et Admin Dashboard (:20129) validés avec redirection 307 vers `/dashboard`.
   - **RTK v0.51.0 CLI** : Qualifié et opérationnel dans le runtime Hermes (`deployment/hermes-agent`) avec plugin de tokenmaxing ArcIA.
   - **Headroom AI v0.41.0** : Installé et qualifié dans l'environnement Python 3.14 d'Hermes pour l'optimisation de contexte.
   - **LintLang v0.8.2** : Installé et qualifié pour la validation et le linting sémantique des prompts.
   - **Skills CLI v1.7.2** : Installé et qualifié au chemin `/usr/local/bin/skills`.
   - **Catalogues de Compétences Partagés** : 313 skills ECC (`affaan-m/ECC`), 15 skills Superpowers (`obra/superpowers`), compétences Vercel AI SDK et Anthropics montés sur `/opt/shared-skills`.
   - **Context7** : Intégration remote MCP validée via le manifeste approuvé sous `/opt/hermes/optional-mcps/context7/manifest.yaml` avec isolation DLP Presidio.
   - Intégration CI/CD : Tests unitaires (`tests/`), validation des manifests, vérification de barrière de confidentialité (zéro fuite de données privées) exécutés et validés à 100% sur GitHub Actions.

10. **Évaluation et Intégration de Ponytail, Graphify et Public-APIs ([Guide outillage](guides/outillage-builder.md))** :
   - **Ponytail (v1.0)** : Intégré comme compétence partagée de sobriété logicielle (`skills/ponytail/SKILL.md`) appliquant la *Decision Ladder* (YAGNI, réutilisation, stdlib, code minimaliste) pour prévenir l'over-engineering d'Hermes.
   - **ArcIA Graphify (v0.2)** : Intégré comme extracteur AST local déterministe (`scripts/arcia_graphify.py`) et compétence associée (`skills/graphify/SKILL.md`), générant `graph.json` et `GRAPH_REPORT.md` (GraphRAG local, 0 token d'inférence, 0 fuite de code).
   - **Public-APIs** : Cadré formellement comme référentiel de veille et guide d'intégration sécurisée (`skills/public-apis/SKILL.md`) ; rejeté comme service ou daemon K3s afin de préserver l'hermétisme réseau d'ArcIA.
   - **Automatisation** : Scripts `skills/sync-skills.sh` et `scripts/Sync-Skills.ps1` mis à jour pour le provisionnement vers `/var/data/arcia/shared-skills/arcia/`.
   - **Validation** : 23 tests unitaires et contrôles de confidentialité validés avec succès (`tests/test_graphify.py`, `tests/test_skills.py`, `tests/test_privacy.py`, etc.).

11. **Assainissement Documentaire Intégral & Réalignement Déployé v0.2 (`scripts/validate_docs.py`)** :
   - **Suppression des 10 guides & runbooks v0.1 obsolètes** : Guides `connaissance-documentaire.md`, `identite-utilisateurs.md`, `multi-utilisateur.md`, `confidentialite-cloud.md`, `securisation-plateforme-donnees.md` et runbooks `bootstrap.md`, `certificats-dns.md`, `exploitation-qualification.md`, `preparer-deploiement.md`, `vcenter.md`.
   - **Purge intégrale et définitive de `docs/archives/` et `docs/adr/` (51 fichiers supprimés au total)** : Suppression de l'intégralité du répertoire `docs/archives/` et de l'ensemble des 21 fichiers `docs/adr/`. Toutes les décisions d'architecture et de gouvernance sont consolidées de manière vivante et unique dans `docs/architecture.md` et les guides dédiés.
   - **Réalignement intégral des documents directeurs (`AGENTS.md`)** : `docs/installation-k3s-codex.md`, `docs/plan-integration-hermes.md`, `docs/schemas-plateforme-hermes.md` (schémas Mermaid v0.2 Traefik, Open-WebUI, Hermes, LiteLLM, Presidio, Graphify), `docs/backlog.md` et `docs/organisation.md` entièrement épurés de tout concept v0.1 hérité.
   - **Réalignement des guides v0.2 actifs** : `versions-officielles.md`, `plateforme-arcia.md`, `securite.md`, `outillage-builder.md`, `skills.md`, `omniroute.md` et refonte complète de `quickstart.md` (déploiement 3 étapes, LiteLLM keys, Open-WebUI BYOK/OAuth, Hermes Studio/Gateway, Teams).
   - **Outillage d'intégrité automatique** : Script déterministe `scripts/validate_docs.py` vérifiant 100% des fichiers markdown et liens relatifs/ancres (0 erreur, arborescence documentaire strictement active).
   - **Périmètre GitHub** : Le dépôt GitHub est 100% épuré et ne comporte plus aucun composant, trace ou document qui ne soit déployé et qualifié sur le harness v0.2.

---

## 2. État Courant des Composants

| Composant | Pod / Service | Port | Statut Réel | Rôle |
|---|---|---|---|---|
| **Presidio DLP** | `presidio-dlp` | 8080 | **1/1 Running** | Caviardage des secrets et PII avant envoi cloud |
| **LiteLLM Proxy** | `litellm-proxy` | 4000 | **1/1 Running** | Routage LLM d'entreprise unifié avec cache et métriques |
| **Hermes Agent** | `hermes-agent` | 9119 / 8642 | **1/1 Running** | Moteur agentique autonome, Studio Kanban et Gateway Desktop |
| **Open-WebUI** | `open-webui` | 8080 | **1/1 Running** | Interface web chat pour l'ensemble des collaborateurs |
| **Teams Bot** | `teams-bot-adapter` | 3978 | **1/1 Running** | Passerelle Microsoft Teams (DM et canaux) |
| **Cert-Manager** | `cert-manager` | - | **3/3 Running** | Gestionnaire ACME / Let's Encrypt automatique |
| **OAuth2-Proxy** | `oauth2-proxy` | 4180 | **1/1 Running** | Authentification SSO Microsoft Entra ID (OIDC v2.0 opérationnel) |
| **OmniRoute** | `omniroute` | 20128 / 20129 | **1/1 Running** | Routeur multi-fournisseurs & portail LAN v3.8.51 (Opérationnel) |
| **RTK CLI** | `rtk` (in hermes) | CLI | **v0.51.0 Qualifié** | CLI Tokenmaxing et observation de contexte LLM |
| **Headroom AI** | `headroom-ai` (in hermes) | Lib | **v0.41.0 Qualifié** | Optimisation et compression de contextes dynamiques |
| **LintLang** | `lintlang` (in hermes) | CLI | **v0.8.2 Qualifié** | Linter sémantique et hygiène de prompt |
| **Skills CLI** | `skills` (in hermes) | CLI | **v1.7.2 Qualifié** | Découverte et installation de compétences modulaires |
| **Shared Skills** | `/opt/shared-skills` | Volume | **313 ECC + 15 Superpowers + Vercel + ArcIA** | Catalogues de compétences partagées multi-agents |
| **Context7 MCP** | `context7` (manifest) | MCP | **Approuvé & Sécurisé** | Documentation à jour via passerelle DLP |
| **Ponytail** | `skills/ponytail` | Skill | **v1.0 Codé & Intégré** | Sobriété logicielle, échelle de décision YAGNI et anti-bloat |
| **ArcIA Graphify** | `scripts/arcia_graphify.py` | Tool/Skill | **v0.2 Codé & Vérifié (3/3)** | Cartographie AST locale déterministe et GraphRAG (0 token) |
| **Public-APIs** | `skills/public-apis` | Référentiel | **Cadré (Veille)** | Guide de qualification et sécurisation Presidio/NetworkPolicy |
| **Doc Validator** | `scripts/validate_docs.py` | CLI | **Vérifié (72 docs / 222 liens)** | Contrôle d'intégrité automatique des liens et ancres |


---

## 3. Matrice de Validation Exécutée (`scripts/test-validation.sh`)

La recette automatique a été exécutée avec succès sur le cluster K3s :

```
[1/6] Vérification des Pods Kubernetes : OK (7/7 pods opérationnels, oauth2-proxy inclus)
[2/6] Test Presidio DLP Sanitization : SUCCESS (PII caviardé en [ARCIA_EMAIL_1])
[3/6] Test LiteLLM Proxy Health & Models : HTTP 200 (/health/readiness & /v1/models expose 6 modèles)
[4/6] Test Hermes Agent Studio (9119) & Gateway (8642) : HTTP 302 (Auth Gate active)
[5/6] Test Teams Bot Adapter Health : {"status": "ok", "service": "teams-bot-adapter", "version": "0.2.0"}
[6/6] Test Open-WebUI Portal Health & OIDC : HTTP 200 (/health) & HTTP 302 (/oauth/oidc/login vers login.microsoftonline.com)
```

---

## 4. Activation des Secrets et Raccordement SSO / Modèles (16 octobre 2026)

Les secrets de production ont été restaurés depuis le coffre DPAPI local (`ArcIA-Harness\integrations.dpapi`) et l'état persistant du cluster, puis appliqués via `./scripts/Apply-Secrets.ps1` :

1. **Clé API OpenRouter & Catalogue LiteLLM (`05-litellm.yaml`)** :
   - Ajout explicite de `args: ["--config", "/app/config.yaml", "--port", "4000"]` sur `litellm-proxy` et mise au format v2 du guardrail Presidio (`/analyze` + `/anonymize`).
   - Exposition vérifiée sur `/v1/models` : `auto`, `claude-3.5-sonnet`, `gpt-4o`, `deepseek-chat`, `hermes-agent`, `local-internal`.

2. **SSO Microsoft Entra ID (`02-oauth2-proxy.yaml` & `07-open-webui.yaml`)** :
   - Correction de `OPENID_PROVIDER_URL` dans `07-open-webui.yaml` vers `https://login.microsoftonline.com/$(ENTRA_TENANT_ID)/v2.0/.well-known/openid-configuration` (au lieu du `tenant-id` brut qui provoquait une erreur HTTP 500 `Internal Server Error`).
   - Passage d'`oauth2-proxy` en `--provider=oidc` avec `--oidc-issuer-url` explicite et `cookie-secret` AES 32 octets (`1/1 Running`).
   - Activation de `BYPASS_MODEL_ACCESS_CONTROL=true` et synchronisation de la table `config` de `webui.db` pour rendre tous les modèles visibles immédiatement par les comptes utilisateurs (`user` et `admin`).

---

---

## 5. Commandes d'Exploitation Rapides

- **Lancer le Setup Wizard Graphique (Installation & Reconfiguration)** :
  ```powershell
  # Windows PowerShell
  .\wizard.ps1

  # Linux / macOS
  ./wizard.sh
  ```
- **Vérifier l'état du cluster** :
  ```powershell
  .\scripts\Invoke-K3s.ps1 "get pods -n arcia -o wide"
  ```
- **Réappliquer les secrets après mise à jour** :
  ```powershell
  .\scripts\Apply-Secrets.ps1
  ```
- **Relancer la suite de tests de validation** :
  ```powershell
  Get-Content .\scripts\test-validation.sh -Raw | .\scripts\Invoke-K3s.ps1 -RawShell "bash -s"
  ```
- **Consulter les logs d'Hermes** :
  ```powershell
  .\scripts\Invoke-K3s.ps1 "logs -l app=hermes-agent -n arcia --tail=50"
  ```

---

## 6. Assistant Graphique Interactif (Setup Wizard), Dépôts d'Instance Privés & Restauration (16 octobre 2026)

Conformément à l'exigence de fluidification intégrale du parcours d'installation et de stricte séparation socle/instance :
1. **Wizard Graphique Autonome (`scripts/wizard.py`, `./wizard.sh`, `.\wizard.ps1`)** :
   - Parcours complet écran-par-écran (11 étapes) :
     - *Étape 1* : Choix du mode (**Nouvelle Instance** ou **Restaurer une Instance existante**).
     - *Étape 2* : **Dépôt Git d'Instance Privé** (GitHub ou GitLab, test live de PAT, création automatique de `ArcIA-instance-XXXX`, mot de passe maître de chiffrement AES-256-GCM / PBKDF2).
     - *Étape 3* : Cluster K8s (test interactif de connectivité `kubectl` ou SSH K3s).
     - *Étape 4* : Réseau & TLS FQDN (`assistant.votre-entreprise.com`).
     - *Étape 5* : Passerelle LLM Cloud & Local (OpenRouter, LiteLLM).
     - *Étape 6* : Hermes Studio & Desktop (génération automatique des PAT et mots de passe).
     - *Étape 7* : SSO Microsoft Entra ID (optionnel, avec guide pas-à-pas intégré).
     - *Étape 8* : Bot Microsoft Teams (optionnel, avec guide pas-à-pas intégré).
     - *Étape 9* : OmniRoute (optionnel).
     - *Étape 10* : Déploiement live avec streaming de logs + synchronisation chiffrée vers le Git d'instance privé.
     - *Étape 11* : Récapitulatif 100% opérationnel avec URLs, identifiants et lien d'accès au dépôt d'instance privé.
   - Serveur Web local autonome (Python standard library uniquement, 0 dépendance pip/npm requise).
   - Mode restauration : téléchargement automatique de `instance-secrets.enc`, déchiffrement via le mot de passe maître, pré-remplissage de toute la configuration et déploiement 1-clic.
2. **Auto-Configuration Intégrale des Éléments Internes & Compétences** :
   - Presidio DLP, Open-WebUI, Hermes Studio/Gateway, LiteLLM et synchronisation automatique de 100% des compétences natives (*Ponytail*, *Graphify*, *Public-APIs*) déployés d'office sans aucune manipulation utilisateur.
3. **État du Cluster Kubernetes** :
   - Cluster entièrement remis à blanc : namespace `arcia` détruit, 24 Persistent Volumes orphelins VMware CSI purgés, état prêt pour une installation fraîche 100% propre via le Wizard.
4. **Vérification Complète** :
   - 31 tests unitaires validés avec succès (`tests/test_wizard.py`, `tests/test_privacy.py`, `tests/test_deploy.py`, etc.).
   - Validation documentaire stricte à 100% (`scripts/validate_docs.py`).

---

## 7. Nettoyage et Épure du Socle (16 octobre 2026)

Conformément à l'exigence de clarté, lisibilité et stricte application de la règle *« Une information, une référence »* :
1. **Suppression du Blueprint Initial** :
   - Suppression définitive de `PLAN_DE_MISE_EN_OEUVRE_ARCIA_v0.2.md` à la racine du dépôt.
   - Les manifestes, scripts d'automatisation, guides d'architecture et runbooks d'exploitation sont consolidés dans leurs répertoires respectifs (`deploy/manifests/`, `scripts/`, `docs/`).
2. **Validation Globale** :
   - 32 fichiers documentaires et 159 liens relatifs vérifiés sans anomalie (`scripts/validate_docs.py`).
   - 31 tests unitaires exécutés et validés avec succès (`python -m unittest discover tests`).



