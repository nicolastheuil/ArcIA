# Portail Collaborateur Open-WebUI & SSO Microsoft Entra ID (v0.3)

> **Statut : Implémenté (v0.3)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

Open-WebUI est l'interface utilisateur de référence pour l'ensemble des collaborateurs de votre organisation. Elle offre une expérience moderne et ergonomique pour dialoguer avec les agents et les modèles d'entreprise.

---

## 1. Caractéristiques Principales v0.3

- **Interface Conversationnelle Avancée** :
  - Support du Markdown riche, des artefacts de code, des tableaux et des rendus mathématiques LaTeX.
  - Gestion des historiques de discussion et organisation par dossiers.
- **Raccordement Exclusif sur LiteLLM Proxy** :
  - `http://litellm-proxy.arcia.svc:4000/v1` : fournit les 3 paliers d'entreprise (`arcia/standard`, `arcia/expert`, `arcia/reasoning`) avec bascule et caviardage DLP Presidio fail-closed.
- **Suppression des Connexions Directes (Sécurité & Gouvernance)** :
  - `ENABLE_DIRECT_CONNECTIONS=false` : empêche le navigateur d'émettre des requêtes directes vers des tiers non gouvernés et protège les secrets personnels de toute persistance en clair.
- **Propagation de l'Identité Utilisateur** :
  - `ENABLE_FORWARD_USER_INFO_HEADERS=true` : transmet l'adresse email de la session collaborateur (`X-OpenWebUI-User-Email`) à LiteLLM pour imputer la consommation budgétaire à l'équipe.
- **Sous-agents & Exécution Multi-Agents** :
  - `ENABLE_SUBAGENTS=true` : active la délégation de tâches à des sous-agents spécialisés.
- **Authentification Unique (SSO) Microsoft Entra ID** :
  - Connexion fluide avec le compte d'entreprise Microsoft 365.
  - Fusion automatique des comptes par adresse email (`OAUTH_MERGE_ACCOUNTS_BY_EMAIL=true`).
- **Persistance Dédiée (PVC 20Gi)** :
  - Monté sous `/app/backend/data`.
  - Conserve la base de données interne des profils, favoris, réglages et conversations.

---

## 2. Déploiement Kubernetes & Ingress

- **Manifeste** : [deploy/manifests/07-open-webui.yaml](../../deploy/manifests/07-open-webui.yaml).
- **Service** : `open-webui.arcia.svc:8080`.
- **Exposition Ingress** : Racine du domaine public `https://assistant.example.org/`.
- **Modèle par Défaut** : `arcia/standard`.

---

<a id="creation-app-entraid"></a>
## 3. Procédure Détaillée : Création de l'Application Microsoft Entra ID (SSO)

Cette étape permet d'authentifier les collaborateurs avec leurs identifiants Microsoft 365 professionnels.

### Étape 1 : Créer l'inscription d'application
1. Rendez-vous sur le [Portail Azure](https://portal.azure.com/) et connectez-vous avec un compte administrateur.
2. Recherchez et sélectionnez **Microsoft Entra ID** (anciennement Azure AD).
3. Dans le menu de gauche, cliquez sur **Inscriptions d'applications** (*App registrations*), puis sur **+ Nouvelle inscription** (*+ New registration*).
4. Renseignez les paramètres suivants :
   - **Nom** : `ArcIA Enterprise Assistant`
   - **Types de comptes pris en charge** : *Comptes dans cet annuaire organisationnel uniquement (Locataire unique)*
   - **URI de redirection** : Sélectionner *Web* et saisir `https://<public_fqdn>/oauth/oidc/callback`
5. Récupérer le `Tenant ID`, le `Client ID` et générer un `Client Secret`.
6. Reporter ces informations dans la section `entra_id_sso` de votre `arcia.config.yaml`.

---

Voir également :
- [Chaîne de Routage & Cycle de Vie](chaine-de-routage.md)
- [Passerelle d'Inférence LiteLLM](inference-litellm.md)
- [Gouvernance Presidio DLP](confidentialite-presidio.md)
- [État des fonctionnalités v0.3](../etat-des-fonctionnalites.md)
