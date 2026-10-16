# Service Adaptateur Bot Microsoft Teams — ArcIA

Ce dossier contient l'adaptateur de bot conversationnel pour **Microsoft Teams**, développé avec le SDK Bot Framework de Microsoft et `aiohttp`.

## Contenu

* **[app.py](app.py)** : Serveur asynchrone écoutant sur le port 3978 (`/api/teams/messages`) :
  * Valide les requêtes entrantes signées par Azure Bot Framework via `MICROSOFT_APP_ID` et `MICROSOFT_APP_PASSWORD`.
  * Supporte les conversations privées (1:1 direct messages) et les mentions d'équipe (`@ArcIA`).
  * Achemine la demande utilisateur vers la passerelle d'inférence LiteLLM (`auto`), garantissant que le prompt bénéficie du caviardage DLP Presidio.
  * Restitue la réponse formatée en Markdown enrichi directement dans le client Teams.

## Déploiement & Configuration

Le service est déployé via [deploy/manifests/08-teams-bot.yaml](../../deploy/manifests/08-teams-bot.yaml) et exposé par l'Ingress Traefik sur `/api/teams/messages` sans passer par ForwardAuth (l'authentification étant vérifiée cryptographiquement par le protocole Bot Framework).

Pour plus de détails :
* [Guide d'Intégration Microsoft Teams](../../docs/guides/integration-teams.md)
* [Manifeste d'application Teams](../../assets/teams/manifest.json)
