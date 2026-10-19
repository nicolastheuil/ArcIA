<p align="left">
  <a href="../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.7.0-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <img src="https://img.shields.io/badge/Design_System-ArcIA_Brand_Kit-6BE7DD?style=flat-square&logoColor=050712" alt="Brand Kit">
</p>

# 🎨 Ressources graphiques, identité visuelle et packages — ArcIA

> **[🏠 Accueil ArcIA](../README.md)** › **Assets (`assets/`)**

Ce dossier centralise la charte graphique officielle d'**ArcIA**, les ressources de l'installateur et les packages d'application pour **Microsoft Teams**.

---

## 📂 Structure des ressources

```text
assets/
├── branding/     # Identité visuelle vectorielle (SVG dark/light, bannière GitHub) et palette.json
├── installer/    # Icônes (.ico), bandeaux graphiques et script Inno Setup
└── teams/        # Icônes officielles (192x192 / 32x32), manifest.json et archives .zip Teams
```

| Sous-dossier | Contenu principal | Rôle |
|---|---|---|
| 🎨 **[branding/](branding/README.md)** | `banner-github-dark.svg`, `logo-arcia-dark.svg`, `logo-arcia-light.svg`, `logo-arcia-symbol.svg`, `icon-model-*.svg`, `palette.json` | Identité visuelle officielle injectée dans Open-WebUI (`arcia-webui-branding`), le Setup Wizard et la documentation. |
| 💿 **[installer/](installer/README.md)** | `app.ico`, `wizard-header.bmp`, `wizard-side.bmp`, `installer-sample.iss` | Ressources visuelles et script de packaging pour les exécutables d'installation Windows. |
| 💬 **[teams/](teams/README.md)** | `manifest.json`, `color.png`, `outline.png`, `arcia-teams-ui.zip`, `arcia-teams-app.zip` | Package officiel de l'application ArcIA pour le Portail Développeur Microsoft Teams. |
