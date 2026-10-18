<p align="left">
  <a href="../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.5.0-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <img src="https://img.shields.io/badge/Secrets-AES--256--GCM_&_K8s_Secrets-FA7B4E?style=flat-square" alt="Secrets">
  <img src="https://img.shields.io/badge/Git_Safety-Zero_Plaintext-10B981?style=flat-square" alt="Zero Plaintext">
</p>

# 🔐 Gestion des secrets et variables d'environnement — ArcIA

> **[🏠 Accueil ArcIA](../README.md)** › **Secrets (`secrets/`)**

Ce dossier contient le modèle de configuration des secrets d'entreprise pour la plateforme **ArcIA**.

> [!CAUTION]
> **Règle absolue de sécurité ArcIA** : Aucun secret en clair, mot de passe, jeton API, certificat privé ou fichier `.env` réel ne doit jamais être commité dans le socle public. Seuls les fichiers modèles (`*.template`) sont versionnés ici ; les secrets d'une instance sont chiffrés (`AES-256-GCM`) dans son dépôt d'instance privé.

---

## 📋 Modèle et variables requises (`arcia.env.template`)

Le fichier **[arcia.env.template](arcia.env.template)** recense l'ensemble des variables secrètes injectées dans les objets `Secret` Kubernetes :

| Domaine | Variables principales | Usage |
|---|---|---|
| **1. Passerelle LLM** | `LITELLM_MASTER_KEY`, `OPENROUTER_API_KEY` | Clé maître LiteLLM Proxy (`:4000`) et accès aux modèles Cloud (`zdr: true`). |
| **2. SSO Entra ID** | `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OAUTH2_PROXY_COOKIE_SECRET` | Authentification OpenID Connect via `oauth2-proxy` (`:4180`). |
| **3. Hermes Agent** | `HERMES_API_SERVER_KEY`, `HERMES_ADMIN_PASSWORD` | Jeton PAT de la Gateway (`:8642`) et mot de passe admin de Hermes Studio (`:9119`). |
| **4. Microsoft Teams** | `TEAMS_APP_ID`, `TEAMS_APP_PASSWORD` | Authentification des webhooks signés par Azure Bot Service (`:3978`). |

---

## ⚡ Cycle d'injection dans Kubernetes

1. **Via le Setup Wizard (Recommandé)** :
   ```powershell
   .\wizard.ps1
   ```
   *(Génère automatiquement les jetons cryptographiques et chiffre le bundle d'instance).*
2. **Manuellement en CLI** :
   ```bash
   cp secrets/arcia.env.template secrets/arcia.env
   ```
   Puis appliquez les secrets sur le cluster :
   ```powershell
   # Windows PowerShell :
   .\scripts\Apply-Secrets.ps1
   ```
   ```bash
   # Linux / macOS :
   ./scripts/apply-secrets.sh
   ```
