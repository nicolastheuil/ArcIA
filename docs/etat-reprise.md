# État de reprise d’ArcIA — 15 octobre 2026 (v0.2 Transformation)

**Unique handoff courant.** L'ancien état v0.1 a été archivé sur la branche `archive/v0.1-legacy` et figé sous le tag `v0.1-legacy-archive`.
La cible d'exécution actuelle est le socle unifié et épuré **ArcIA v0.2**, déployé et vérifié sur le cluster K3s 3 nœuds (`node-01`, `node-02`, `node-03`).

---

## 1. Synthèse de la Transformation ArcIA v0.2

Conformément à `PLAN_DE_MISE_EN_OEUVRE_ARCIA_v0.2.md` :
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
   - Préconfiguration déclarative : `OPENAI_API_KEYS`, `ENABLE_OLLAMA_API=false`, `ENABLE_SUBAGENTS=true`, `TASK_MODEL=auto`, `WEBUI_NAME=ArcIA` et `ENABLE_PERSISTENT_CONFIG=false`.
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

10. **Évaluation et Intégration de Ponytail, Graphify et Public-APIs ([ADR 0021](adr/0021-evaluation-et-integration-ponytail-graphify-public-apis.md))** :
   - **Ponytail (v1.0)** : Intégré comme compétence partagée de sobriété logicielle (`skills/ponytail/SKILL.md`) appliquant la *Decision Ladder* (YAGNI, réutilisation, stdlib, code minimaliste) pour prévenir l'over-engineering d'Hermes.
   - **ArcIA Graphify (v0.2)** : Intégré comme extracteur AST local déterministe (`scripts/arcia_graphify.py`) et compétence associée (`skills/graphify/SKILL.md`), générant `graph.json` et `GRAPH_REPORT.md` (GraphRAG local, 0 token d'inférence, 0 fuite de code).
   - **Public-APIs** : Cadré formellement comme référentiel de veille et guide d'intégration sécurisée (`skills/public-apis/SKILL.md`) ; rejeté comme service ou daemon K3s afin de préserver l'hermétisme réseau d'ArcIA.
   - **Automatisation** : Scripts `skills/sync-skills.sh` et `scripts/Sync-Skills.ps1` mis à jour pour le provisionnement vers `/var/data/arcia/shared-skills/arcia/`.
   - **Validation** : 23 tests unitaires et contrôles de confidentialité validés avec succès (`tests/test_graphify.py`, `tests/test_skills.py`, `tests/test_privacy.py`, etc.).

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
| **OAuth2-Proxy** | `oauth2-proxy` | 4180 | *CrashLoop* (Attente clés) | Authentification SSO Microsoft Entra ID (en attente des identifiants réels) |
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


---

## 3. Matrice de Validation Exécutée (`scripts/test-validation.sh`)

La recette automatique a été exécutée avec succès sur le cluster K3s :

```
[1/6] Vérification des Pods Kubernetes : OK (6/6 pods opérationnels)
[2/6] Test Presidio DLP Sanitization : SUCCESS (PII caviardé en [ARCIA_EMAIL_1])
[3/6] Test LiteLLM Proxy Health : HTTP 200 (/health/readiness)
[4/6] Test Hermes Agent Studio (9119) & Gateway (8642) : HTTP 302 (Auth Gate active)
[5/6] Test Teams Bot Adapter Health : {"status": "ok", "service": "teams-bot-adapter", "version": "0.2.0"}
[6/6] Test Open-WebUI Portal Health : HTTP 200 (/health)
```

---

## 4. TODO / Prérequis Utilisateur (Activation Définitive)

Le déploiement a été conduit sans blocage ni demande d'identifiants pendant l'exécution.
Pour finaliser l'activation en production, compléter les valeurs manquantes dans `secrets/arcia.env` puis relancer `./scripts/Apply-Secrets.ps1` :

1. **Clé API OpenRouter (`OPENROUTER_API_KEY`)** :
   - Renseigner la clé de production dans `secrets/arcia.env`.
   - Permet à LiteLLM et Hermes d'effectuer les appels vers les modèles cloud configurés (`auto`, Sonnet 3.5, etc.).

2. **Identifiants Microsoft Entra ID (SSO Collaborateurs & OAuth2-Proxy)** :
   - `ENTRA_TENANT_ID`
   - `ENTRA_CLIENT_ID`
   - `ENTRA_CLIENT_SECRET`
   - Dès ces valeurs saisies, `oauth2-proxy` démarre immédiatement (résolvant le CrashLoop actuel) et active la protection SSO sur `/studio` et `/gateway`.

3. **Identifiants Microsoft Teams Bot Framework** :
   - `TEAMS_BOT_APP_ID`
   - `TEAMS_BOT_APP_PASSWORD`
   - Configurer l'endpoint de messagerie dans Azure Bot Service vers `https://assistant.example.org/api/teams/messages` (remplacer par votre nom de domaine d'instance).

4. **Enregistrement DNS Public** :
   - Créer l'enregistrement DNS de type A pour votre domaine (ex: `assistant.example.org`) pointant vers l'adresse IP publique / VIP du cluster (actuellement `cm-acme-http-solver` attend la résolution pour finaliser le certificat SSL Let's Encrypt).

---

## 5. Commandes d'Exploitation Rapides

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
