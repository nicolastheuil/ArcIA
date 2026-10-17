# Service Adaptateur Bot Microsoft Teams — ArcIA

Ce dossier contient l'adaptateur de bot conversationnel pour **Microsoft Teams**, développé avec le SDK Bot Framework de Microsoft et `aiohttp`.

## Contenu

* **[app.py](app.py)** : Serveur asynchrone écoutant sur le port 3978 (synchronisé dans le ConfigMap `teams-bot-code` par `scripts/deploy.py`) :
  * `POST /api/teams/messages` : Valide les requêtes entrantes signées par Azure Bot Framework via `MICROSOFT_APP_ID` et `MICROSOFT_APP_PASSWORD`.
  * Supporte les conversations privées (1:1 direct messages) et les mentions d'équipe (`@ArcIA`).
  * **Routage Hybride** :
    * Les messages standards sont acheminés vers la passerelle d'inférence LiteLLM sur le profil **`simple/auto`**.
    * Les messages préfixés par `/agent <mission>` (ou `!agent <mission>`) sont délégués au runtime Hermes Agent (`:8642/v1`) sur le profil **`agentic/auto`**.
  * `GET /healthz` (et alias `GET /health`) : Sonde de disponibilité HTTP 200 pour Kubernetes.
* **[Dockerfile](Dockerfile)** : Image Docker autonome Python 3.11 avec `botbuilder-core`, `aiohttp` et `httpx`.

## Déploiement & Configuration

Le service est déployé via [deploy/manifests/08-teams-bot.yaml](../../deploy/manifests/08-teams-bot.yaml) et exposé par l'Ingress Traefik sur `/api/teams/messages`.

Pour plus de détails :
* [Guide d'Intégration Microsoft Teams](../../docs/guides/integration-teams.md)
* [Manifeste d'application Teams](../../assets/teams/manifest.json)
