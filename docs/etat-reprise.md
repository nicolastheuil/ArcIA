# État de reprise d’ArcIA — 16 octobre 2026 (v0.2)

**Unique handoff courant.**
La cible d'exécution actuelle est le socle unifié et épuré **ArcIA v0.2**, déployé et vérifié sur le cluster K3s 3 nœuds VMware vSphere (`node-01`, `node-02`, `node-03`) ainsi qu'en mode local Docker Lab.

---

## 1. Statut Global du Socle v0.2

1. **Namespace Unifié (`arcia`)** :
   - Namespace unique pour tous les services applicatifs.
   - StorageClass par défaut VMware vSphere CSI : `arcia-vsphere` (ext4 bloc, Retain, RWOP).

2. **Ingress, TLS & Sécurité Périmétrique** :
   - Traefik déployé en DaemonSet avec ports `80` et `443` exposés.
   - Certificats Let's Encrypt production gérés par Cert-Manager (`letsencrypt-prod`).
   - Authentification SSO Microsoft Entra ID via OAuth2-Proxy (`oauth2-proxy:4180`) et intégration OIDC native Open-WebUI.

3. **Passerelle DLP & Confidentialité (Presidio)** :
   - Service `presidio-dlp:8080` opérationnel dans le namespace `arcia`.
   - Caviardage automatique systématique des secrets, mots de passe et PII (`[ARCIA_EMAIL_1]`, etc.) avant tout appel vers un modèle cloud externe.

4. **Passerelle d'Inférence d'Entreprise (LiteLLM)** :
   - Service `litellm-proxy:4000` opérationnel avec modèle virtuel `auto` et fallbacks résilients.
   - Guardrail `pre_call` Presidio DLP actif.

5. **Interfaces Utilisateurs** :
   - **Open-WebUI (port 8080)** : Portail web conversationnel grand public avec persistance PVC 20Gi (`open-webui-pvc`), raccordé à LiteLLM et Hermes Gateway, thème dark officiel ArcIA injecté.
   - **Hermes Studio & Gateway (ports 9119 & 8642)** : Studio Kanban multi-agents et Gateway WebSocket/HTTP pour Hermes Desktop, persistance PVC 20Gi (`hermes-user-pvc`).
   - **Teams Bot Adapter (port 3978)** : Bot Framework Microsoft Teams opérationnel pour conversations privées et mentions de canaux `@ArcIA`.

---

## 2. Matrice des Composants Déployés & Qualifiés

| Composant | Pod / Service | Port | Statut Réel | Rôle |
|---|---|---|---|---|
| **Presidio DLP** | `presidio-dlp` | 8080 | **1/1 Running** | Caviardage des secrets et PII avant envoi cloud |
| **LiteLLM Proxy** | `litellm-proxy` | 4000 | **1/1 Running** | Routage LLM d'entreprise unifié avec cache et métriques |
| **Hermes Agent** | `hermes-agent` | 9119 / 8642 | **1/1 Running** | Moteur agentique autonome, Studio Kanban et Gateway Desktop |
| **Open-WebUI** | `open-webui` | 8080 | **1/1 Running** | Interface web chat pour l'ensemble des collaborateurs |
| **Teams Bot** | `teams-bot-adapter` | 3978 | **1/1 Running** | Passerelle Microsoft Teams (DM et canaux) |
| **Cert-Manager** | `cert-manager` | - | **3/3 Running** | Gestionnaire ACME / Let's Encrypt automatique |
| **OAuth2-Proxy** | `oauth2-proxy` | 4180 | **1/1 Running** | Authentification SSO Microsoft Entra ID (OIDC v2.0) |
| **OmniRoute (Optionnel)** | `omniroute` | 20128 / 20129 | **1/1 Running** | Routeur multi-fournisseurs & portail LAN v3.8.51 |
| **RTK CLI** | `rtk` (in hermes) | CLI | **v0.51.0 Qualifié** | CLI Tokenmaxing et observation de contexte LLM |
| **Headroom AI** | `headroom-ai` (in hermes) | Lib | **v0.41.0 Qualifié** | Optimisation et compression de contextes dynamiques |
| **LintLang** | `lintlang` (in hermes) | CLI | **v0.8.2 Qualifié** | Linter sémantique et hygiène de prompt |
| **Skills CLI** | `skills` (in hermes) | CLI | **v1.7.2 Qualifié** | Découverte et installation de compétences modulaires |
| **Shared Skills** | `/opt/shared-skills` | Volume | **ECC + Superpowers + ArcIA** | Montage multi-nœuds partagé de compétences souveraines |
| **Ponytail** | `skills/ponytail` | Skill | **v1.0 Intégré** | Sobriété logicielle, échelle de décision YAGNI |
| **ArcIA Graphify** | `scripts/arcia_graphify.py` | Tool/Skill | **v0.2 Vérifié** | Cartographie AST locale déterministe (0 token) |
| **Public-APIs** | `skills/public-apis` | Skill | **Opérationnel** | Passerelle sécurisée d'APIs publiques souveraines |

---

## 3. Déploiement & Setup Wizard

La plateforme dispose de deux parcours d'installation reproductibles :
1. **Setup Wizard Graphique (`wizard.sh` / `wizard.ps1` / `scripts/wizard.py`)** :
   - Assistant Web local autonome (0 dépendance externe requise).
   - Prise en charge de 3 cibles : Nouveau cluster K3s sur VMware (dimensionnement interactif avec volume RAG/ChromaDB), Connexion Kubernetes existant (audit en 6 volets), ou Mode Lab Docker local.
   - Gestion des dépôts d'instance privés chiffrés en **AES-256-GCM** (dérivation PBKDF2).
   - Mode restauration 1-clic depuis le dépôt Git privé d'instance.

2. **Moteur Déclaratif CLI (`scripts/deploy.py` / `scripts/Deploy-ArcIA.ps1`)** :
   - Configuration universelle centralisée dans `arcia.config.yaml`.
   - Injection automatique des secrets et application ordonnée des manifestes dans `deploy/manifests/`.

---

## 4. Recette Opérationnelle Exécutée (`scripts/test-validation.sh`)

La recette automatique a été exécutée avec succès sur le cluster K3s (6/6 tests réussis) :
- `[1/6]` Vérification des Pods Kubernetes : OK (7/7 pods opérationnels, oauth2-proxy inclus)
- `[2/6]` Test Presidio DLP Sanitization : SUCCESS (PII caviardé en `[ARCIA_EMAIL_1]`)
- `[3/6]` Test LiteLLM Proxy Health & Models : HTTP 200 (`/health/readiness` & `/v1/models` exposent les modèles)
- `[4/6]` Test Hermes Agent Studio (9119) & Gateway (8642) : HTTP 302 (Auth Gate active et passée)
- `[5/6]` Test Teams Bot Adapter Health : `{"status": "ok", "service": "teams-bot-adapter", "version": "0.2.0"}`
- `[6/6]` Test Open-WebUI Portal Health & OIDC : HTTP 200 (`/health`)

---

## 5. Commandes d'Exploitation Rapides

```powershell
# 1. Lancer le Setup Wizard Graphique
.\wizard.ps1

# 2. Vérifier l'état des Pods
.\scripts\Invoke-K3s.ps1 "get pods -n arcia -o wide"

# 3. Réappliquer les secrets
.\scripts\Apply-Secrets.ps1

# 4. Lancer la suite de validation automatique
Get-Content .\scripts\test-validation.sh -Raw | .\scripts\Invoke-K3s.ps1 -RawShell "bash -s"

# 5. Consulter les logs d'Hermes
.\scripts\Invoke-K3s.ps1 "logs -l app=hermes-agent -n arcia --tail=50 -f"
```

---

## 6. Prochaines Actions

1. Déploiement d'une nouvelle instance en production via `.\wizard.ps1` sur l'infrastructure VMware cible.
2. Configuration des secrets d'entreprise dans le dépôt Git d'instance privé dédié.
3. Activation des options d'entreprise spécifiques (SSO Entra ID, Bot Teams) selon la politique de l'organisation.

---

## 7. Direction Artistique ArcIA & Qualification d'OmniRoute v3.8.51 (16 octobre 2026)

1. **Intégration de la Direction Artistique ArcIA dans Open-WebUI** :
   - **Typographie Officielle** : Injection des polices `Montserrat` (titres, logos, boutons) et `Inter` (corps) via Google Fonts.
   - **Palette Graphique Officielle** :
     - Fond Deep Dark : `#050712`.
     - Surface Sidebar Squircle : `#0A0F1D` avec bordure `#1E293B`.
     - Cartes secondaires : `#131B2E`.
     - Boutons d'action et submit : Dégradé signature ArcIA `linear-gradient(135deg, #1659E4 0%, #5AD8CE 100%)` avec effet glow `#6BE7DD`.
     - Focus ring et sélecteurs : Cyan officiel `#6BE7DD`.
   - **Logos Vectoriels Officiels** :
     - Monogramme officiel squircle "aIA" (`assets/branding/logo-arcia-symbol.svg`) injecté directement en data URI SVG dans `CUSTOM_CSS` pour remplacer les logos et favicons de la sidebar, du header et du splash screen.
     - Injection automatique via le ConfigMap Kubernetes `arcia-webui-branding` (`sync_webui_branding` dans `scripts/deploy.py`) et volume mounts `/app/build/static/favicon.svg` et `/app/build/static/logo.svg`.
   - **Bannière d'Accueil** : Titre `⚡ ArcIA — Enterprise Agentic Platform`, sous-titre `Plateforme IA Agentique Souveraine d'Entreprise • Hermes Agent & LiteLLM`.

2. **Rôle et Qualification d'OmniRoute v3.8.51** :
   - **Positionnement Architectural** : LiteLLM Proxy (`:4000`) reste la passerelle LLM centrale par défaut car elle assure le caviardage DLP Presidio. OmniRoute v3.8.51 (`:20128`) est le routeur IA optionnel dédié à l'administration LAN, aux combos de modèles (`auto/smart`, `auto/coding`, `auto/cheap`) et à l'agrégation d'abonnements/pools de clés.
   - **Activation** : Proposé à l'étape 9 du Wizard (`scripts/wizard.py`) ou via `omniroute.enabled: true` dans `arcia.config.yaml`.
   - **Qualification Cluster Réelle** : Déployé et testé sur le cluster K3s (`09-omniroute.yaml`) :
     - Volume persistant VMware CSI 5Gi `omniroute-data-pvc` alloué et Bound.
     - Pod `omniroute` `1/1 Running`.
     - Endpoint API (`:20128/v1`) fonctionnel (réponse HTTP 401 sur requête non authentifiée).
     - Dashboard Web d'Administration LAN (`:20128/dashboard` et `:20128/`) fonctionnel et servi par le runtime Next.js d'OmniRoute.

