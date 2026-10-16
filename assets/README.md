# Ressources Graphiques & Visuelles — ArcIA

Ce dossier regroupe l'ensemble des éléments graphiques, identités visuelles, icônes d'application et manifests de distribution pour la plateforme ArcIA.

## Structure du Dossier

```
assets/
├── branding/     # Identité de marque, logos SVG (light/dark) et palette de couleurs officielle
├── installer/    # Icônes (.ico) et images de l'assistant d'installation (wizard Inno Setup / web)
└── teams/        # Icônes officielle (color & outline) et manifest pour l'application Microsoft Teams
```

## Sous-Dossiers

### 1. [branding/](branding/)
Contient les fichiers vectoriels SVG officiels d'ArcIA et d'Arcitek :
* `logo-arcia-dark.svg` / `logo-arcia-light.svg` : Logos complets avec typographie pour thèmes sombre et clair.
* `logo-arcia-symbol.svg` : Symbole seul (icône carrée réutilisable en favicon ou avatar).
* `banner-github-dark.svg` : Bannière d'en-tête pour le README GitHub et les portails d'accueil.
* `palette.json` : Définition des codes couleurs officiels (couleurs primaires, accents cyan/vert, arrières-plans sombres).

### 2. [installer/](installer/)
Contient les ressources destinées aux assistants d'installation et installateurs Windows/Linux :
* `app.ico` : Icône de bureau multi-résolutions.
* `wizard-header.bmp` / `wizard-side.bmp` : Bandeaux graphiques pour l'installateur Inno Setup.
* `installer-sample.iss` : Modèle de script de compilation Inno Setup.

### 3. [teams/](teams/)
Contient le package d'intégration officiel pour Microsoft Teams :
* `manifest.json` : Manifeste d'application Teams définissant les capacités du bot conversationnel, les permissions d'interaction (DM et mentions de canal), et les liens de support.
* `color.png` (192x192) : Icône en couleur pleine pour le catalogue d'applications Teams.
* `outline.png` (32x32) : Icône filaire monochrome pour la barre latérale Teams.
