<p align="left">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.5.0-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <a href="../README.md"><img src="https://img.shields.io/badge/🎨_Assets-Design_System-0C2762?style=flat-square" alt="Assets"></a>
  <img src="https://img.shields.io/badge/Teams_App-Manifest_v1.25-5B5FC7?style=flat-square&logo=microsoftteams&logoColor=white" alt="Teams Manifest">
</p>

# 💬 Package d'application Microsoft Teams — ArcIA

> **[🏠 Accueil ArcIA](../../README.md)** › **[🎨 Assets](../README.md)** › **Microsoft Teams (`assets/teams/`)**

Ce dossier regroupe le manifeste, les icônes réglementaires et les archives `.zip` prêtes à l'emploi pour déployer le bot **ArcIA** dans **Microsoft Teams**.

---

## 📦 Fichiers du package

| Fichier | Dimensions / Format | Rôle |
|---|---|---|
| **`arcia-teams-ui.zip`** | Archive ZIP | **Import immédiat sans pré-enregistrement** dans `dev.teams.microsoft.com` (association du Bot ID a posteriori en 1 clic). |
| **`arcia-teams-app.zip`** | Archive ZIP | **Package complet avec Bot déclaré** (généré par `.\scripts\Package-TeamsApp.ps1`). |
| **[manifest.json](manifest.json)** | JSON (Schéma v1.25) | Manifeste officiel déclarant les portées (`personal`, `team`, `groupChat`) et commandes (`/agent`). |
| **[color.png](color.png)** | PNG `192x192` px | Icône couleur officielle pour le catalogue d'applications Microsoft Teams. |
| **[outline.png](outline.png)** | PNG `32x32` px | Icône monochrome transparente pour la barre latérale Teams. |

---

## 🚀 Procédure d'importation dans Microsoft Teams

### Option A : import direct dans le portail développeur (sans bot pré-créé)
1. Ouvrez le **[Portail Développeur Microsoft Teams](https://dev.teams.microsoft.com/apps)** et cliquez sur **Importer une application**.
2. Sélectionnez `assets/teams/arcia-teams-ui.zip`.
3. Dans **App features › Bot**, liez ou créez votre bot Azure en 1 clic.

### Option B : empaquetage automatisé avec votre `BotId`
```powershell
.\scripts\Package-TeamsApp.ps1 -BotId "VOTRE-APP-ID-GUID"
```
Puis importez `assets/teams/arcia-teams-app.zip` dans votre catalogue d'entreprise.
