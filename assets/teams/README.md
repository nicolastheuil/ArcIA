# Package d'Application Microsoft Teams — ArcIA

Ce dossier regroupe le manifeste et les icônes nécessaires à la publication et au déploiement du bot ArcIA dans Microsoft Teams.

## Fichiers Disponibles

* `manifest.json` : Manifeste officiel de l'application Teams (version du schéma Bot Framework, scopes d'autorisation personnels et de groupe, commandes slash et métadonnées d'entreprise).
* `color.png` : Icône carrée couleur 192x192 px requise par le catalogue d'applications Teams.
* `outline.png` : Icône transparente monochrome 32x32 px pour la barre latérale gauche de Teams.

## Déploiement dans le Portail Développeur Teams

Pour déployer le bot dans votre tenant Microsoft 365 :
1. Compresser les 3 fichiers (`manifest.json`, `color.png`, `outline.png`) dans une archive `arcia-teams.zip`.
2. Ouvrir le **Portail Développeur Microsoft Teams** (ou le Centre d'administration Microsoft Teams).
3. Sélectionner **Importer une application** et choisir l'archive zip.
4. Distribuer l'application aux utilisateurs de votre organisation.
