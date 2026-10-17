# Intégration Microsoft Teams — Bot ArcIA (v0.4)

L'adaptateur Microsoft Teams permet d'amener les capacités d'ArcIA directement dans le flux de travail quotidien des équipes sous Microsoft 365 (messages privés 1:1, mentions d'équipe et canaux partagés).

---

## 1. Vue d'Ensemble & Règle d'Or

> [!IMPORTANT]
> **Règle d'or de l'ordre des opérations :**
> Vous **devez obligatoirement créer le Bot auprès de Microsoft (Étape 1)** AVANT d'importer le package d'application dans Teams (Étape 3).
> Si vous tentez d'importer le package `.zip` avec un identifiant de bot non encore enregistré, les serveurs de Microsoft vérifient le registre central Bot Framework et renvoient immédiatement l'erreur bloquante :
> *« Bot non valide : Veuillez vérifier que le bot est enregistré et que le canal Teams est activé. »*

### Les 5 étapes de bout en bout

```mermaid
flowchart LR
    E1["1. Créer le Bot<br/>(dev.teams ou Azure)"] --> E2["2. Noter Bot ID & Secret"]
    E2 --> E3["3. Générer le ZIP Teams<br/>(avec votre Bot ID)"]
    E3 --> E4["4. Importer dans dev.teams<br/>(100% validé par MS)"]
    E4 --> E5["5. Configurer ArcIA & Tester"]
```

---

## 2. Architecture Technique & Routage Hybride

L'adaptateur est implémenté en Python asynchrone (`aiohttp` + `botbuilder-core`) dans [services/teams/app.py](../../services/teams/app.py) et synchronisé automatiquement dans le ConfigMap `teams-bot-code` par `scripts/deploy.py` :

- **Mode Chat Rapide (par défaut)** : Tout message standard envoyé au bot est acheminé vers **LiteLLM Proxy** (`:4000/v1`) sur le profil **`simple/auto`** (avec caviardage DLP Presidio).
- **Mode Mission Agentique (`/agent`)** : Tout message préfixé par `/agent <mission>` ou `!agent <mission>` est délégué au runtime **Hermes Agent** (`:8642/v1`) sur le profil **`agentic/auto`** pour exécuter une tâche autonome outillée.

```mermaid
sequenceDiagram
    participant User as Collaborateur Teams
    participant MS as Azure Bot Service
    participant Ingress as Ingress Traefik (assistant.example.org)
    participant Adapter as Teams Bot Adapter (:3978)
    participant LiteLLM as LiteLLM Proxy (:4000)
    participant Hermes as Hermes Agent (:8642)

    User->>MS: Envoi du message (DM ou @ArcIA)
    MS->>Ingress: POST /api/teams/messages (Webhook)
    Ingress->>Adapter: Transmission sécurisée (Authorization header)
    Adapter->>Adapter: Nettoyage mention & vérification JWT
    alt Commande /agent <mission>
        Adapter->>Hermes: POST /v1/chat/completions (model: agentic/auto)
        Hermes-->>Adapter: Résultat de la mission autonome
    else Message standard
        Adapter->>LiteLLM: POST /v1/chat/completions (model: simple/auto)
        LiteLLM-->>Adapter: Réponse d'inférence directe
    end
    Adapter->>MS: Send Activity (Markdown)
    MS-->>User: Affichage dans Microsoft Teams
```

- **Manifeste Kubernetes** : [deploy/manifests/08-teams-bot.yaml](../../deploy/manifests/08-teams-bot.yaml).
- **Service interne** : `teams-bot-adapter.arcia.svc:3978` (sonde de santé `GET /healthz`).
- **Webhook public** : `https://<VOTRE_FQDN_PUBLIC>/api/teams/messages`.

---

<a id="creation-azure-bot"></a>
## 3. Étape 1 : Enregistrer le Bot auprès de Microsoft

Deux parcours équivalents sont disponibles pour créer l'identité du bot :

### Parcours A : Via le Portail Développeur Teams *(Gratuit, sans abonnement Azure — Recommandé)*

Ce parcours ne nécessite aucun abonnement Azure facturé.

1. Rendez-vous sur le **[Portail Développeur Microsoft Teams](https://dev.teams.microsoft.com/)** et connectez-vous avec votre compte professionnel Microsoft 365.
2. Dans le menu de gauche, cliquez sur **Tools** (Outils) > **Bot management** (Gestion des bots).
3. Cliquez sur le bouton **+ New Bot** :
   - **Name** : `ArcIA Assistant`
   - Cliquez sur **Add**.
4. Dans la page de configuration de votre nouveau bot :
   - Sous **Bot ID** : Notez précieusement cette valeur GUID (ex: `a1b2c3d4-xxxx-xxxx-xxxx-xxxxxxxxxxxx`). C'est votre `TEAMS_BOT_APP_ID`.
   - Cliquez sur l'onglet **Client secrets** > **Add a client secret** :
     - Notez immédiatement la **valeur du secret généré**. C'est votre `TEAMS_BOT_APP_PASSWORD`.
   - Sous **Bot endpoint address** (Adresse du point de terminaison) :
     ```text
     https://<VOTRE_FQDN_PUBLIC>/api/teams/messages
     ```
     *(Exemple : `https://assistant.example.org/api/teams/messages`)*
   - Cliquez sur **Save**.
5. *Note* : Le canal Microsoft Teams est activé automatiquement dans ce mode.

---

### Parcours B : Via le Portail Azure *(Si vous disposez d'un abonnement Azure)*

1. Rendez-vous sur le **[Portail Azure](https://portal.azure.com/)**.
2. Recherchez **Azure Bot** et cliquez sur **Créer**.
   - **Bot handle** : `arcia-assistant` (doit être unique globalement).
   - **Pricing tier** : `Standard` (ou `F0 Gratuit`).
   - **Type of App** : `Single Tenant` (ou `Multi Tenant`).
   - **Creation type** : `Create new Microsoft App ID`.
3. Une fois créé, allez dans la ressource Azure Bot :
   - Menu **Configuration** :
     - Renseignez le **Messaging endpoint** : `https://<VOTRE_FQDN_PUBLIC>/api/teams/messages`.
     - Copiez le **Microsoft App ID** (`TEAMS_BOT_APP_ID`).
     - Cliquez sur **Manage Password** à côté de l'App ID pour générer et copier le secret client (`TEAMS_BOT_APP_PASSWORD`).
   - Menu **Canaux (*Channels*)** :
     - Cliquez sur **Microsoft Teams**, acceptez les conditions et cliquez sur **Apply**.
     - Vérifiez que le statut affiche **En cours d'exécution (*Running*)**.

---

## 4. Étape 2 : Générer le Package d'Application Teams avec votre Bot ID

Maintenant que le bot existe dans le registre Microsoft, vous pouvez générer le package d'application `.zip` qui associe le bot aux logos, commandes et métadonnées d'ArcIA.

Exécutez la commande suivante depuis la racine du dépôt :

```powershell
# En PowerShell (Windows) :
.\scripts\Package-TeamsApp.ps1 -BotId "VOTRE-BOT-ID-GUID"

# En Python (Linux / macOS / Windows) :
python scripts/package_teams_app.py --bot-id "VOTRE-BOT-ID-GUID"
```

Le script réalise automatiquement :
- L'injection de votre `BotId` réel dans le fichier `manifest.json`.
- La validation des spécifications Teams **v1.25** (`supportsChannelFeatures: tier1`).
- La validation des résolutions d'icônes (`color.png` 192x192 px et `outline.png` 32x32 px).
- L'empaquetage dans l'archive : `assets/teams/arcia-teams-app.zip`.

---

## 5. Étape 3 : Importer le Package dans dev.teams

1. Rendez-vous sur **[Portail Développeur Microsoft Teams > Apps](https://dev.teams.microsoft.com/apps)**.
2. Cliquez sur **Importer une application** (*Import app*).
3. Sélectionnez le fichier généré : `assets/teams/arcia-teams-app.zip`.
4. **Résultat :** Comme le bot est déjà enregistré chez Microsoft, l'importation est **validée instantanément à 100% sans aucune erreur**.
5. Votre application **ArcIA** s'ouvre dans le portail avec tous ses réglages configurés (discussions 1:1, canaux, logos, commandes `aide` et `statut`).

---

## 6. Étape 4 : Configurer ArcIA avec les Secrets

Pour que l'adaptateur ArcIA puisse authentifier les messages envoyés par Microsoft Teams :

### Option A : Via `arcia.config.yaml`
```yaml
teams_bot:
  enabled: true
  app_id: "VOTRE-BOT-ID-GUID"
  app_password: "VOTRE-CLIENT-SECRET"
```

### Option B : Via variables d'environnement (`.env` ou secrets Kubernetes)
```bash
TEAMS_BOT_APP_ID="VOTRE-BOT-ID-GUID"
TEAMS_BOT_APP_PASSWORD="VOTRE-CLIENT-SECRET"
```

Appliquez les secrets sur votre cluster K3s :
```powershell
.\scripts\Apply-Secrets.ps1
```

---

## 7. Étape 5 : Tester et Déployer dans Teams

1. **Test immédiat individuel (*Preview*)** :
   - Dans le Portail Développeur Teams, cliquez sur le bouton **Preview in Teams** (en haut à droite).
   - Teams s'ouvre : cliquez sur **Ajouter** (*Add*).
   - Envoyez un message direct au bot : `Bonjour ArcIA, comment peux-tu m'aider ?` (routé vers `simple/auto`).
   - Envoyez une mission agentique : `/agent Recherche le SIRET de la DINUM et synthétise ses informations` (routé vers Hermes `agentic/auto`).
2. **Test en canal d'équipe** :
   - Ajoutez le bot dans une équipe de test.
   - Mentionnez-le : `@ArcIA résume-moi la situation`.
3. **Publication permanente au catalogue d'entreprise** :
   - Téléversez `assets/teams/arcia-teams-app.zip` dans le **[Centre d'administration Microsoft Teams](https://admin.teams.microsoft.com/)** (**Applications Teams > Gérer les applications > + Charger une nouvelle application**) pour le rendre disponible à toute l'organisation.

---

## 8. Dépannage & Erreurs Courantes

| Symptôme | Cause | Solution |
| :--- | :--- | :--- |
| **« Bot non valide : Veuillez vérifier que le bot est enregistré et que le canal Teams est activé »** | Vous avez tenté d'importer le ZIP avant de créer le bot, ou avec un Bot ID inexistant. | Suivez l'**Étape 1** pour créer le bot dans *Bot management*, puis régénérez le ZIP avec votre vrai Bot ID (Étape 2). |
| **Le bot ne répond pas dans Teams** | L'adaptateur ne reçoit pas les messages ou rejette l'authentification. | 1. Vérifiez que l'URL du Webhook (`https://<FQDN>/api/teams/messages`) est accessible publiquement avec un certificat TLS valide.<br/>2. Vérifiez que `TEAMS_BOT_APP_ID` et `TEAMS_BOT_APP_PASSWORD` correspondent exactement au bot. |
| **Erreur HTTP 401 sur le webhook** | Le mot de passe client (`TEAMS_BOT_APP_PASSWORD`) est expiré ou incorrect. | Régénérez un secret client dans *Bot management > Client secrets* et mettez à jour ArcIA. |
