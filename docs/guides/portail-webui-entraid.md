# Portail collaborateur Open-WebUI et SSO Microsoft Entra ID (v0.5.2)

> **Statut : Implémenté (v0.5.2)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

Open-WebUI est l'interface utilisateur de référence pour l'ensemble des collaborateurs de votre organisation (Utilisateurs Standards et Power Users). Elle offre une expérience moderne et ergonomique pour dialoguer avec les modèles directs (`simple/*`) et les agents autonomes (`agentic/*`), sous une gouvernance d'accès strictement verrouillée.

---

## 1. Caractéristiques principales et verrouillage d'accès v0.5.2

- **Accès Verrouillé & Zéro Auto-Inscription Publique** :
  - `WEBUI_AUTH=true` : Authentification obligatoire pour tout accès à l'interface.
  - `ENABLE_SIGNUP=false` : **Auto-inscription publique totalement interdite.** N'importe quel internaute arrivant sur le portail ne peut pas créer de compte.
  - **Modes d'accès autorisés exclusivement** :
    1. **Authentification SSO Microsoft 365 / Entra ID** (`ENABLE_OAUTH_SIGNUP=true`) pour les collaborateurs du tenant d'entreprise.
    2. **Comptes locaux créés manuellement par l'administrateur** via le panneau de gestion des utilisateurs.
  - `DEFAULT_USER_ROLE=user` : Rôle par défaut fixé en utilisateur standard (`user`). Tout collaborateur authentifié via Microsoft 365 / Entra ID ou compte local créé par l'admin accède directement aux profils `simple/*` et `agentic/*`.
  - `BYPASS_MODEL_ACCESS_CONTROL=false` : Contrôle d'accès aux modèles activé.
  - `OAUTH_MERGE_ACCOUNTS_BY_EMAIL=true` : Fusion transparente et automatique des comptes SSO Microsoft Entra ID avec les comptes existants partageant la même adresse email vérifiée au sein du tenant d'organisation.

- **Double Raccordement Hybride (LiteLLM Direct + Hermes Agent)** :
  - `OPENAI_API_BASE_URLS="http://litellm-proxy.arcia.svc:4000/v1;http://hermes-studio.arcia.svc:8642/v1"` :
    - Les profils **`simple/*`** sont routés directement vers **LiteLLM Proxy** (`:4000/v1`) pour offrir une réponse instantanée sur les conversations rapides.
    - Les profils **`agentic/*`** sont routés vers **Hermes Agent** (`:8642/v1`) pour exécuter des sessions autonomes outillées avec persistance SQLite (`state.db`), compétences partagées, compression CCR et recherche web.
  - **Catalogue filtré aux 5 profils canoniques (`ENABLE_MODEL_FILTER=true`)** :
    1. **`simple/free`** : Chat direct gratuit sans boucle agentique (`openrouter/openrouter/free`).
    2. **`simple/auto`** *(Défaut)* : Chat direct polyvalent et réactif (`openrouter/auto`).
    3. **`agentic/free`** : Session autonome Hermes outillée sur palier gratuit (`openrouter/openrouter/free`).
    4. **`agentic/auto`** : Session autonome Hermes complète avec outils et skills (`openrouter/auto`).
    5. **`agentic/expert`** : Session autonome Hermes haute performance pour l'architecture et le code complexe (`openrouter/deepseek/deepseek-v4.1-flash`).
- **Suppression des Connexions Directes (Sécurité & Gouvernance)** :
  - `ENABLE_DIRECT_CONNECTIONS=false` : empêche le navigateur d'émettre des requêtes directes vers des tiers non gouvernés et protège les secrets personnels de toute persistance en clair.
- **Propagation de l'Identité Utilisateur** :
  - `ENABLE_FORWARD_USER_INFO_HEADERS=true` : transmet l'adresse email de la session collaborateur (`X-OpenWebUI-User-Email`) pour imputer la consommation budgétaire à l'équipe.
- **Sous-agents & Exécution Multi-Agents** :
  - `ENABLE_SUBAGENTS=true` : active la délégation de tâches à des sous-agents spécialisés.
- **Persistance Dédiée (PVC 20Gi)** :
  - Monté sous `/app/backend/data`.
  - Conserve la base de données interne des profils, favoris, réglages, conversations ainsi que la clé de chiffrement des sessions (`WEBUI_SECRET_KEY_FILE: /app/backend/data/.webui_secret_key`).

---

## 2. Déploiement Kubernetes et Ingress

- **Manifeste** : [deploy/manifests/07-open-webui.yaml](../../deploy/manifests/07-open-webui.yaml).
- **Service** : `open-webui.arcia.svc:8080`.
- **Exposition Ingress** : Racine du domaine public `https://assistant.example.org/`.
- **Modèle par Défaut** : `simple/auto`.

---

<a id="creation-app-entraid"></a>
## 3. Procédure détaillée : création de l'application Microsoft Entra ID (SSO)

Cette étape permet d'authentifier les collaborateurs avec leurs identifiants Microsoft 365 professionnels.

### Étape 1 : créer l'inscription d'application
1. Rendez-vous sur le [Portail Azure](https://portal.azure.com/) et connectez-vous avec un compte administrateur.
2. Recherchez et sélectionnez **Microsoft Entra ID** (anciennement Azure AD).
3. Dans le menu de gauche, cliquez sur **Inscriptions d'applications** (*App registrations*), puis sur **+ Nouvelle inscription** (*+ New registration*).
4. Renseignez les paramètres suivants :
   - **Nom** : `ArcIA Enterprise Assistant`
   - **Types de comptes pris en charge** : *Comptes dans cet annuaire organisationnel uniquement (Locataire unique)*
   - **URI de redirection** : Sélectionner *Web* et saisir `https://<public_fqdn>/oauth/oidc/callback` (ainsi que `https://<public_fqdn>/oauth2/callback` pour OAuth2-Proxy sur `/studio`).
5. Récupérer le `Tenant ID`, le `Client ID` et générer un `Client Secret`.
6. Reporter ces informations dans la section `entra_id_sso` de votre `arcia.config.yaml`.

---

Voir également :
- [Chaîne de routage et cycle de vie](chaine-de-routage.md)
- [Passerelle d'inférence LiteLLM](inference-litellm.md)
- [Gouvernance Presidio DLP](confidentialite-presidio.md)
- [État des fonctionnalités v0.5.2](../etat-des-fonctionnalites.md)
