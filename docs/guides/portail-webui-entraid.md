# Portail Collaborateur Open-WebUI & SSO Microsoft Entra ID

Open-WebUI est l'interface utilisateur de référence pour l'ensemble des collaborateurs de votre organisation. Elle offre une expérience moderne et ergonomique pour dialoguer avec les agents et les modèles d'entreprise.

---

## 1. Caractéristiques Principales

- **Interface Conversationnelle Avancée** :
  - Support du Markdown riche, des artefacts de code, des tableaux et des rendus mathématiques LaTeX.
  - Gestion des historiques de discussion et organisation par dossiers.
- **Raccordement Double : LiteLLM & Hermes Agent Gateway** :
  - **LiteLLM Proxy** (`http://litellm-proxy.arcia.svc:4000/v1`) : fournit le modèle virtuel `auto` avec routage d'entreprise, bascule et caviardage DLP Presidio.
  - **Hermes Gateway** (`http://hermes-studio.arcia.svc:8642/v1`) : expose le moteur d'agents autonome avec exécution d'outils, skills et mémoire.
  - Clé d'API déclarée : `sk-arcia` (LiteLLM) et `admin` (Hermes).
- **Sous-agents & Exécution Multi-Agents** :
  - `ENABLE_SUBAGENTS=true` : active la délégation de tâches à des sous-agents spécialisés.
- **Désactivation d'Ollama Local Inaccessible** :
  - `ENABLE_OLLAMA_API=false` : supprime l'appel erroné vers `host.docker.internal:11434` sur K3s.
- **Authentification Unique (SSO) Microsoft Entra ID** :
  - Connexion fluide avec le compte d'entreprise Microsoft 365.
  - Fusion automatique des comptes par adresse email (`OAUTH_MERGE_ACCOUNTS_BY_EMAIL=true`).
- **Persistance Dédiée (PVC 20Gi)** :
  - Monté sous `/app/backend/data`.
  - Conserve la base de données interne des utilisateurs, favoris, réglages et conversations.

---

## 2. Déploiement Kubernetes & Ingress

- **Manifeste** : [deploy/manifests/07-open-webui.yaml](../../deploy/manifests/07-open-webui.yaml).
- **Service** : `open-webui.arcia.svc:8080`.
- **Exposition Ingress** : Racine du domaine public `https://assistant.example.org/` (ou votre domaine).
- **Sécurité Périmétrique** : Traefik ForwardAuth via `oauth2-proxy` pour valider les tokens Microsoft Entra ID.

---

### 3. Dépannage « Aucun modèle disponible »

Si le sélecteur affiche « Aucun modèle disponible » :
1. Dans Open-WebUI, aller dans **Paramètres > Admin > Connexions**.
2. Dans la section **API compatibles OpenAI**, vérifier la ligne `http://litellm-proxy.arcia.svc:4000/v1` :
   - Cliquer sur la **roue crantée (⚙️)**.
   - Saisir une clé d'API (ex: `sk-arcia` ou `dummy`). Open-WebUI refuse d'interroger `/models` si ce champ est vide.
   - Cliquer sur la validation/sauvegarde. Les modèles `auto` et `local-internal` apparaissent immédiatement.
3. Désactiver le commutateur **API Ollama** (`http://host.docker.internal:11434`) pour éviter les timeouts locaux.
4. Pour appliquer de manière définitive en mode Infrastructure-as-Code sans intervention manuelle, le manifeste injecte `ENABLE_PERSISTENT_CONFIG=false` et préconfigure les endpoints.

---

<a id="creation-app-entraid"></a>
## 4. Procédure Détaillée : Création de l'Application Microsoft Entra ID (SSO)

Cette étape facultative permet de verrouiller l'accès à Hermes Studio et Open-WebUI aux seuls comptes Microsoft 365 de votre entreprise.

### Étape 1 : Créer l'inscription d'application
1. Rendez-vous sur le [Portail Azure](https://portal.azure.com/) et connectez-vous avec un compte administrateur.
2. Recherchez et sélectionnez **Microsoft Entra ID** (anciennement Azure AD).
3. Dans le menu de gauche, cliquez sur **Inscriptions d'applications** (*App registrations*), puis sur **+ Nouvelle inscription** (*+ New registration*).
4. Renseignez les paramètres suivants :
   - **Nom** : `ArcIA-Enterprise-SSO` (ou le libellé souhaité).
   - **Types de comptes pris en charge** : *Comptes dans cet annuaire d'organisation uniquement (Mono-locataire / Single-Tenant)*.
   - **URI de redirection (facultatif)** : Sélectionnez la plateforme **Web** et entrez :
     `https://<VOTRE_FQDN_PUBLIC>/oauth2/callback`
     *(Exemple : `https://assistant.entreprise.com/oauth2/callback`)*
5. Cliquez sur **Inscrire** (*Register*).

### Étape 2 : Récupérer les identifiants Client & Tenant
Sur la page **Vue d'ensemble** (*Overview*) de votre application créée :
1. Copiez la valeur de l'**ID d'application (client)** -> Ce sera votre `client_id`.
2. Copiez la valeur de l'**ID de l'annuaire (locataire)** -> Ce sera votre `tenant_id`.

### Étape 3 : Générer le Secret Client (*Client Secret*)
1. Dans le menu de gauche de l'application, cliquez sur **Certificats & secrets** (*Certificates & secrets*).
2. Cliquez sur l'onglet **Secrets client** puis sur **+ Nouveau secret client** (*+ New client secret*).
3. Ajoutez une description (ex: `ArcIA SSO Secret`) et choisissez une durée de validité (ex: *180 jours* ou *24 mois*).
4. Cliquez sur **Ajouter**.
5. **ATTENTION :** Copiez immédiatement la valeur du champ **Valeur** (*Value*). Cette valeur ne sera plus jamais affichée par la suite -> Ce sera votre `client_secret`.

### Étape 4 : Permissions d'API
1. Dans le menu de gauche, cliquez sur **Autorisations d'API** (*API permissions*).
2. Vérifiez que la permission déléguée `Microsoft Graph > User.Read` est présente (attribuée par défaut).
3. Cliquez sur **Accorder le consentement de l'administrateur pour [Votre Organisation]** (*Grant admin consent*) pour valider l'accès sans invite individuelle.

### Étape 5 : Renseignement dans ArcIA
Renseignez ces 3 identifiants (`tenant_id`, `client_id`, `client_secret`) dans le **Wizard graphique ArcIA** (Écran 6) ou dans `arcia.config.yaml`.
Le `cookie_secret` (clé de 32 octets aléatoire) est généré automatiquement par le Wizard.

