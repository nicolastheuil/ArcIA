# Portail Collaborateur Open-WebUI & SSO Microsoft Entra ID

Open-WebUI est l'interface utilisateur de référence pour l'ensemble des collaborateurs de votre organisation. Elle offre une expérience moderne et ergonomique pour dialoguer avec les agents et les modèles d'entreprise.

---

## 1. Caractéristiques Principales

- **Interface Conversationnelle Avancée** :
  - Support du Markdown riche, des artefacts de code, des tableaux et des rendus mathématiques LaTeX.
  - Gestion des historiques de discussion et organisation par dossiers.
- **Raccordement Double : LiteLLM & Hermes Agent Gateway** :
  - **LiteLLM Proxy** (`http://litellm-proxy.arcia.svc:4000/v1`) : fournit le modèle virtuel `auto` avec routage d'entreprise, bascule et caviardage DLP Presidio.
  - **Hermes Gateway** (`http://hermes-studio.arcia.svc:8642/v1`) : expose le moteur d'agents autonome avec exécution d'outils, skills et mémoire.
  - Clé d'API déclarée : `sk-arcia` (LiteLLM) et `admin` (Hermes).
- **Sous-agents & Exécution Multi-Agents** :
  - `ENABLE_SUBAGENTS=true` : active la délégation de tâches à des sous-agents spécialisés.
- **Désactivation d'Ollama Local Inaccessible** :
  - `ENABLE_OLLAMA_API=false` : supprime l'appel erroné vers `host.docker.internal:11434` sur K3s.
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

---

## 3. Dépannage « Aucun modèle disponible »

Si le sélecteur affiche « Aucun modèle disponible » :
1. Dans Open-WebUI, aller dans **Paramètres > Admin > Connexions**.
2. Dans la section **API compatibles OpenAI**, vérifier la ligne `http://litellm-proxy.arcia.svc:4000/v1` :
   - Cliquer sur la **roue crantée (⚙️)**.
   - Saisir une clé d'API (ex: `sk-arcia` ou `dummy`). Open-WebUI refuse d'interroger `/models` si ce champ est vide.
   - Cliquer sur la validation/sauvegarde. Les modèles `auto` et `local-internal` apparaissent immédiatement.
3. Désactiver le commutateur **API Ollama** (`http://host.docker.internal:11434`) pour éviter les timeouts locaux.
4. Pour appliquer de manière définitive en mode Infrastructure-as-Code sans intervention manuelle, le manifeste injecte `ENABLE_PERSISTENT_CONFIG=false` et préconfigure les endpoints.
