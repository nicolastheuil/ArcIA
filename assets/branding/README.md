<p align="left">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.6.0-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <a href="../README.md"><img src="https://img.shields.io/badge/🎨_Assets-Design_System-0C2762?style=flat-square" alt="Assets"></a>
  <img src="https://img.shields.io/badge/Palette-%231659E4_•_%236BE7DD_•_%230C2762-6BE7DD?style=flat-square&logoColor=050712" alt="Palette">
</p>

# ✨ Identité visuelle et charte graphique — ArcIA

> **[🏠 Accueil ArcIA](../../README.md)** › **[🎨 Assets](../README.md)** › **Branding (`assets/branding/`)**

Ce dossier regroupe les vecteurs officiels SVG et la définition chromatique de la marque **ArcIA**.

---

## 🖼️ Fichiers vectoriels et palette

| Fichier | Format | Usage |
|---|---|---|
| **[banner-github-dark.svg](banner-github-dark.svg)** | SVG Vectoriel | Bannière principale grand format du dépôt GitHub et des portails d'accueil. |
| **[logo-arcia-dark.svg](logo-arcia-dark.svg)** | SVG Vectoriel | Logo complet optimisé pour les interfaces sombres (Setup Wizard, Open-WebUI Dark). |
| **[logo-arcia-light.svg](logo-arcia-light.svg)** | SVG Vectoriel | Logo complet optimisé pour les fonds clairs et documents imprimables. |
| **[logo-arcia-symbol.svg](logo-arcia-symbol.svg)** | SVG Vectoriel | Monogramme carré utilisé comme favicon et avatar d'agent. |
| **[icon-model-default.svg](icon-model-default.svg)** | SVG Vectoriel | Icône modèle classique par défaut : monogramme « aIA » sur squircle dark mode. |
| **[icon-model-local.svg](icon-model-local.svg)** | SVG Vectoriel | Icône modèle local souverain : monogramme « aIA » rehaussé d'un liseret doré marqué (Ollama / vLLM). |
| **[icon-model-zdr.svg](icon-model-zdr.svg)** | SVG Vectoriel | Icône modèle cloud sécurisé : monogramme « aIA » rehaussé d'un liseret argenté marqué (Zero Data Retention). |
| **[models-branding.json](models-branding.json)** | JSON | Référentiel dynamique du mappage des icônes de modèles poussé par le Wizard vers Open-WebUI. |
| **[palette.json](palette.json)** | JSON | Codes hexadécimaux officiels : Royal Blue (`#1659E4`), Cyan (`#6BE7DD`), Deep Navy (`#0C2762`), Coral (`#FA7B4E`), Gold (`#F1C557`). |

Les trois fichiers `icon-model-*.svg` sont les seules sources d’icônes de modèles. Les anciennes copies `model-arcia-*` ont été retirées car aucun parcours ne les utilisait. `models-branding.json` reste un patron vide pour le laboratoire ; le mapping réel Kubernetes est calculé en mémoire et monté dans un emplacement privé.
