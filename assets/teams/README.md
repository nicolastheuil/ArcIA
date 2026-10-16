# Package d'Application Microsoft Teams — ArcIA

Ce dossier regroupe le manifeste, les icônes et les archives `.zip` prêtes à l'emploi nécessaires à l'importation et au déploiement du bot ArcIA dans Microsoft Teams.

## Fichiers Disponibles

* `arcia-teams-ui.zip` : **Archive prête à être importée sans pré-enregistrement** dans [dev.teams.microsoft.com](https://dev.teams.microsoft.com/apps). Ne déclenche aucun appel de validation Bot Framework au moment de l'import, et permet d'associer le bot ensuite via l'interface.
* `arcia-teams-app.zip` : **Archive complète avec bot déclaré**. Nécessite que le Bot ID soit déjà enregistré chez Microsoft (Azure Bot ou Teams Developer Portal) et que le canal Teams soit actif.
* `manifest.json` : Manifeste officiel de l'application Teams (schéma v1.25, `supportsChannelFeatures: tier1`, permissions, descriptions et commandes d'assistance).
* `color.png` : Icône carrée couleur 192x192 px requise par le catalogue d'applications Teams.
* `outline.png` : Icône transparente monochrome 32x32 px pour la barre latérale gauche de Teams.

## Importation dans dev.teams

### Méthode 1 : Import direct (Recommandée si le bot n'est pas encore créé dans Azure)
1. Rendez-vous sur le **[Portail Développeur Microsoft Teams](https://dev.teams.microsoft.com/apps)**.
2. Cliquez sur **Importer une application** (*Import app*).
3. Sélectionnez le fichier `assets/teams/arcia-teams-ui.zip`.
4. L'application est importée instantanément avec tous ses logos et métadonnées.
5. Dans l'onglet **App features** > **Bot**, cliquez pour lier votre bot ou en créer un nouveau en 1 clic.

### Méthode 2 : Import avec Bot ID pré-enregistré
1. Enregistrez votre bot dans *Tools > Bot management* (ou sur le portail Azure).
2. Vérifiez que le canal **Microsoft Teams** est bien activé (statut *Running*).
3. Injectez votre `BotId` :
   ```powershell
   .\scripts\Package-TeamsApp.ps1 -BotId "VOTRE-APP-ID-GUID"
   ```
4. Importez `assets/teams/arcia-teams-app.zip` dans le portail développeur.
