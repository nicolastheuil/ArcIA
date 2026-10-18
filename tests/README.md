<p align="left">
  <a href="../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.5.2-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <img src="https://img.shields.io/badge/Tests-141_Unit_&_Integration_Checks-10B981?style=flat-square" alt="141 Tests">
  <img src="https://img.shields.io/badge/Docs_Validator-100%25_Links_Checked-6BE7DD?style=flat-square&logoColor=050712" alt="Docs Validated">
</p>

# 🧪 Suite de tests automatisés et qualification — ArcIA

> **[🏠 Accueil ArcIA](../README.md)** › **Tests (`tests/`)**

Ce dossier regroupe l'ensemble des tests unitaires, tests d'intégration et contrôles de sécurité de la plateforme **ArcIA v0.5.2**.

---

## ⚡ Exécution rapide

```bash
# 1. Exécuter les 141 tests unitaires et d'intégration :
python -m unittest discover -s tests -v

# 2. Vérifier l'intégrité de 100 % des liens et ancres documentaires :
python scripts/validate_docs.py
```

---

## 🗂️ Cartographie des suites de tests

| Fichier de test | Périmètre contrôlé |
|---|---|
| **[test_wizard.py](test_wizard.py)** | Centre de pilotage [`scripts/wizard.py`](../scripts/wizard.py) : page d'accueil, **3 parcours dédiés** (Installation, Mise à jour, Restauration), chargement YAML contextuel, **vérificateur en direct des versions amont**, **séquence Zero-Downtime RollingUpdate**, tableau sans retour à la ligne, chiffrement `AES-256-GCM`, audit K8s et dimensionnement VMware. *(Détail : [Runbook Quickstart](../docs/runbooks/quickstart.md))* |
| **[test_deploy.py](test_deploy.py)** | Orchestrateur [`scripts/deploy.py`](../scripts/deploy.py) : validation de `arcia.config.yaml`, synchronisation des ConfigMaps (`sync_service_configmaps`) et simulation `--dry-run`. |
| **[test_poweruser.py](test_poweruser.py)** | Provisionnement des Pods Hermes dédiés Power Users ([`scripts/arcia_poweruser.py`](../scripts/arcia_poweruser.py)) et gestion des clés virtuelles PAT ([`scripts/arcia_keys.py`](../scripts/arcia_keys.py)) pour les profils `standard` et `poweruser`. |
| **[test_manifests.py](test_manifests.py)** | Conformité YAML, attribution au namespace `arcia`, cohérence des ports et sondes de santé sur tous les manifestes de [`deploy/manifests/`](../deploy/manifests/README.md). |
| **[test_dlp.py](test_dlp.py)** & **[test_privacy.py](test_privacy.py)** | Bouclier DLP Microsoft Presidio ([`services/presidio/app.py`](../services/presidio/app.py)) et plugin de gouvernance Hermes ([`services/hermes/plugin.py`](../services/hermes/plugin.py)) : détection des secrets (`sk-...`, `ghp_...`, `AKIA...`), adresses IP, PII (`fr`/`en`) et CCR. |
| **[test_teams_app.py](test_teams_app.py)** | Adaptateur Bot Microsoft Teams ([`services/teams/app.py`](../services/teams/app.py)) et validité du package [`assets/teams/manifest.json`](../assets/teams/manifest.json). |
| **[test_skills.py](test_skills.py)** | Conformité structurelle du catalogue [`skills/`](../skills/README.md) et absence d'exécutables non autorisés. |
| **[test_graphify.py](test_graphify.py)** | Analyseur AST déterministe [`scripts/arcia_graphify.py`](../scripts/arcia_graphify.py) et génération du rapport GraphRAG local. |
| **[test_public_apis.py](test_public_apis.py)** | Passerelle Open Data [`skills/public-apis/scripts/public_apis.py`](../skills/public-apis/scripts/public_apis.py) : SIREN/SIRET, calcul de clé TVA intracommunautaire et cache local. |

---

## 🔄 Intégration continue (GitHub Actions)

Cette suite est exécutée automatiquement à chaque commit et Pull Request via le pipeline CI documenté dans [`.github/WORKFLOWS.md`](../.github/WORKFLOWS.md).
