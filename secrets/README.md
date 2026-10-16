# Gestion des Secrets & Variables d'Environnement — ArcIA

Ce dossier contient les modèles de configuration des secrets d'entreprise pour la plateforme ArcIA.

> [!CAUTION]
> **Règle absolue de sécurité ArcIA** : Aucun secret en clair, mot de passe, jeton API, certificat privé ou fichier `.env` réel ne doit jamais être commité dans ce dépôt Git. Seuls les fichiers de modèles (`*.template`) sont versionnés.

## Contenu

* **[arcia.env.template](arcia.env.template)** : Fichier modèle recensant l'intégralité des variables d'environnement secrètes nécessaires au fonctionnement d'ArcIA.

## Variables Clés Requises

1. **Inférence & Fournisseurs Cloud** :
   * `LITELLM_MASTER_KEY` : Clé d'administration pour la passerelle LiteLLM.
   * `OPENROUTER_API_KEY` : Clé d'accès à l'agrégateur de modèles souverains et cloud.
2. **Authentification SSO Microsoft Entra ID** :
   * `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` : Identifiants de l'App Registration Azure AD.
   * `OAUTH2_PROXY_COOKIE_SECRET` : Clé de chiffrement des cookies de session SSO.
3. **Moteur d'Agents Hermes** :
   * `HERMES_API_SERVER_KEY` : Jeton Personal Access Token (PAT) d'entreprise pour la Gateway (:8642) et Hermes Desktop.
   * `HERMES_ADMIN_PASSWORD` : Mot de passe du compte administrateur Hermes Studio (:9119).
4. **Intégration Microsoft Teams** :
   * `TEAMS_APP_ID` / `TEAMS_APP_PASSWORD` : Identifiants du bot Azure Bot Framework.

## Cycle d'Application des Secrets

1. Copier le modèle hors Git (ou laisser l'assistant `wizard.py` le générer) :
   ```bash
   cp secrets/arcia.env.template secrets/arcia.env
   ```
2. Compléter les valeurs réelles dans `secrets/arcia.env` (protégé par `.gitignore`).
3. Appliquer les secrets dans le cluster Kubernetes :
   ```bash
   # Linux / macOS :
   ./scripts/apply-secrets.sh
   # Windows PowerShell :
   ./scripts/Apply-Secrets.ps1
   ```
4. Les scripts injectent automatiquement les objets Kubernetes `Secret` dans le namespace `arcia`.
