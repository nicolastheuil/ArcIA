# Portail collaborateur Open-WebUI et SSO Microsoft Entra ID (v0.7.0)

> **Statut : Implémenté (v0.6.0)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

Open-WebUI est l'interface utilisateur de référence pour l'ensemble des collaborateurs de votre organisation (Utilisateurs Standards et Power Users). Elle offre une expérience moderne et ergonomique pour dialoguer avec les modèles directs (`Simple`) et les agents autonomes (`Agentic`), sous une gouvernance d'accès strictement verrouillée.

---

## 1. Caractéristiques principales et verrouillage d'accès v0.7.0

- **Accès Verrouillé & Zéro Auto-Inscription Publique** :
  - `WEBUI_AUTH=true` : Authentification obligatoire pour tout accès à l'interface.
  - `ENABLE_SIGNUP=false` : **Auto-inscription publique totalement interdite.** N'importe quel internaute arrivant sur le portail ne peut pas créer de compte.
  - **Modes d'accès autorisés exclusivement** :
    1. **Authentification SSO Microsoft 365 / Entra ID** (`ENABLE_OAUTH_SIGNUP=true`) pour les collaborateurs du tenant d'entreprise.
    2. **Comptes locaux créés manuellement par l'administrateur** via le panneau de gestion des utilisateurs.
  - `DEFAULT_USER_ROLE=user` : Rôle par défaut fixé en utilisateur standard (`user`). Les modèles Simple et Agentic restent soumis aux droits natifs du compte ; les tâches Agentic exigent aussi une association administrée à un espace Hermes privé.
  - `BYPASS_MODEL_ACCESS_CONTROL=false` : Contrôle d'accès aux modèles activé.
  - `OAUTH_MERGE_ACCOUNTS_BY_EMAIL=true` : Fusion transparente et automatique des comptes SSO Microsoft Entra ID avec les comptes existants partageant la même adresse email vérifiée au sein du tenant d'organisation.

- **Double Raccordement Hybride (LiteLLM Direct + Hermes Agent)** :
  - `OPENAI_API_BASE_URLS="http://litellm-proxy.arcia.svc:4000/v1;http://127.0.0.1:8080/api/v1/arcia/hermes/v1"` :
    - Les modèles **Simple** sont routés directement vers **LiteLLM Proxy** (`:4000/v1`) pour offrir une réponse instantanée sur les conversations rapides.
    - Les modèles **Agentic** sont routés vers **le routeur privé du backend**, puis le pod Hermes associé au compte (`:8643`) pour exécuter des sessions autonomes outillées avec persistance SQLite (`state.db`), compétences partagées, compression CCR et recherche web.
  - **Catalogue déclaré dans le wizard, restreint par connexion avec `OPENAI_API_CONFIGS`** : seuls les modèles Simple déclarés sont exposés sur la connexion LiteLLM et les modèles Agentic sur la connexion Hermes. Une catégorie vide désactive sa connexion. Les noms sont libres, sans nombre fixe de modèles ni préfixe imposé.
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
- **Modèle par défaut** : celui déclaré dans `llm_gateway.default_model`.

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
- [État des fonctionnalités v0.7.0](../etat-des-fonctionnalites.md)


## Sessions privées et téléchargement des fichiers

Les sessions agentiques d’un utilisateur standard utilisent son pod et son PVC privés. Celles d’un Power User utilisent directement son pod existant et sa personnalisation Studio. Sans association administrée, le portail renvoie HTTP 403, sans repli partagé. Les liens de fichiers exigent la session du propriétaire ; copier un lien ou partager un chat n’en transfère pas les droits.

Voir le [fonctionnement, le provisionnement et la recette des espaces privés](espaces-utilisateurs-webui.md). Les fichiers du runtime central historique ne sont pas automatiquement attribués aux comptes.

## Icônes et configuration conservée

Les icônes normales, ZDR et locales viennent des déclarations de l’administrateur et de la classification commune dans `services/open_webui/branding.py`. L’alias ne décide pas de l’hébergement. Le mapping est monté dans `/etc/arcia/models-branding.json` et reste privé ; la route d’avatar applique le filtrage natif des modèles accessibles avant de renvoyer une ressource statique autorisée. Elle conserve le comportement officiel comme repli et ne crée aucune fiche ni alias de modèle.

**Enregistrer le routage** publie aussi les icônes sur une instance existante ; la même action reprend un échec partiel. Une installation neuve applique ces ressources automatiquement. La clé de session est conservée sur le PVC. Le rechargement respecte `Recreate`, avec interruption possible ; un contrôle HTTP des SVG ne prouve pas leur rendu dans une session authentifiée. Les détails de sauvegarde relèvent du [runbook de reprise](../runbooks/sauvegarde-reconstruction.md).
