<p align="left">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.5.0-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <a href="../README.md"><img src="https://img.shields.io/badge/🧩_Services-Microservices-0C2762?style=flat-square" alt="Services"></a>
  <img src="https://img.shields.io/badge/Canal-Microsoft_Teams_Bot-5B5FC7?style=flat-square&logo=microsoftteams&logoColor=white" alt="Teams Bot">
</p>

# 💬 Service adaptateur bot Microsoft Teams — ArcIA

> **[🏠 Accueil ArcIA](../../README.md)** › **[🧩 Microservices](../README.md)** › **Teams Bot (`services/teams/`)**

Ce dossier contient l'adaptateur conversationnel permettant aux collaborateurs d'interagir avec **ArcIA** directement depuis **Microsoft Teams** (en message direct 1:1 ou en canal d'équipe via `@ArcIA`), construit avec le SDK Microsoft Bot Framework et `aiohttp`.

---

## 🔀 Fonctionnement et routage hybride (`app.py`)

Le serveur asynchrone **[app.py](app.py)** (port `:3978`, synchronisé dans le ConfigMap `teams-bot-code`) et son **[Dockerfile](Dockerfile)** assurent :

| Route / commande | Profil cible | Comportement |
|---|---|---|
| **Message standard** *(DM ou `@ArcIA`)* | **`simple/auto`** *(LiteLLM `:4000/v1`)* | Réponse rapide et synthétique via la passerelle d'inférence protégée par le bouclier DLP Presidio. |
| **`/agent <mission>`** *(ou `!agent <mission>`)* | **`agentic/auto`** *(Hermes `:8642/v1`)* | Délègue une mission multi-étapes outillée au moteur d'agents autonomes Hermes Agent. |
| **`POST /api/teams/messages`** | Webhook Azure Bot | Authentifie les jetons JWT signés par Azure Bot Service via `MICROSOFT_APP_ID` et `MICROSOFT_APP_PASSWORD`. |
| **`GET /healthz`** *(et `/health`)* | Sondes Kubernetes | Sonde HTTP 200 garantissant les mises à jour `RollingUpdate` sans perte de messages. |

---

## ☸️ Déploiement et package Teams

Le service est déployé via [`deploy/manifests/08-teams-bot.yaml`](../../deploy/manifests/08-teams-bot.yaml) et exposé par l'Ingress HTTPS sur `/api/teams/messages`.

### 🔗 Références associées
* 📘 [Guide d'intégration Microsoft Teams](../../docs/guides/integration-teams.md)
* 📦 [Manifeste officiel de l'application Teams (`assets/teams/manifest.json`)](../../assets/teams/manifest.json)
