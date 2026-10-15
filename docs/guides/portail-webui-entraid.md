# Portail Collaborateur Open-WebUI & SSO Microsoft Entra ID

Open-WebUI est l'interface utilisateur de référence pour l'ensemble des collaborateurs de votre organisation. Elle offre une expérience moderne et ergonomique pour dialoguer avec les agents et les modèles d'entreprise.

---

## 1. Caractéristiques Principales

- **Interface Conversationnelle Avancée** :
  - Support du Markdown riche, des artefacts de code, des tableaux et des rendus mathématiques LaTeX.
  - Gestion des historiques de discussion et organisation par dossiers.
- **Raccordement Natif à LiteLLM** :
  - Open-WebUI pointe sur `http://litellm-proxy.arcia.svc:4000/v1`.
  - Le modèle par défaut est préconfiguré sur `auto`.
- **Authentification Unique (SSO) Microsoft Entra ID** :
  - Connexion fluide avec le compte d'entreprise Microsoft 365.
  - Fusion automatique des comptes par adresse email (`OAUTH_MERGE_ACCOUNTS_BY_EMAIL=true`).
- **Persistance Dédiée (PVC 20Gi)** :
  - Monté sous `/app/backend/data`.
  - Conserve la base de données interne des utilisateurs, favoris, réglages et conversations.

---

## 2. Déploiement Kubernetes & Ingress

- **Manifeste** : [deploy/manifests/07-open-webui.yaml](../../deploy/manifests/07-open-webui.yaml).
- **Service** : `open-webui.arcia.svc:8080`.
- **Exposition Ingress** : Racine du domaine public `https://assistant.example.org/` (ou votre domaine).
- **Sécurité Périmétrique** : Traefik ForwardAuth via `oauth2-proxy` pour valider les tokens Microsoft Entra ID.
