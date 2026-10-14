# Connecteurs MCP dans ArcIA

MCP est l’interface entre le moteur d’agents et un serveur d’outils. Le serveur peut être un processus installé dans K3s parlant sur stdin/stdout, ou un service HTTP autorisé. Il ne reçoit aucun privilège du seul fait d’être déclaré dans Hermes. [Configuration officielle Hermes](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md).

## Ce qui existe

`arcia_knowledge` expose recherche et téléchargement autorisé en lecture seule. `arcia_context7` expose son catalogue, mais ses requêtes externes sont refusées jusqu’à qualification d’un adaptateur de confidentialité. Aucun MCP HubSpot ou SharePoint n’est activé. La configuration Hermes est rendue par le harness et montée depuis une ConfigMap immuable adressée par son hash ; une modification manuelle du dashboard ne constitue pas une configuration persistante de la plateforme.

## Exemple HubSpot

HubSpot fournit un serveur MCP distant à `https://mcp.hubspot.com`. Il nécessite une application d’authentification, OAuth/PKCE et les scopes correspondant aux objets autorisés. Ce n’est pas son MCP de développement CLI, qui a une autre fonction. [Guide officiel HubSpot](https://developers.hubspot.com/docs/apps/developer-platform/build-apps/integrate-with-the-remote-hubspot-mcp-server).

Dans ArcIA, le choix du compte, des utilisateurs, des objets et des éventuelles écritures appartient au dépôt d’instance. Commencer en lecture seule ; qualifier les scopes, le renouvellement, la révocation et les refus croisés. Une action sensible requiert le service d’autorisation, indépendamment du comportement du modèle.

## Exemple SharePoint

Pour la mise en œuvre tenant, les permissions exactes, grants et tests de
refus, suivre l'[annexe Intégration Microsoft365](../annexes/integration-microsoft365.md).

Une intégration documentaire doit sélectionner sites, bibliothèques et fichiers, récupérer leurs versions et conserver les droits applicables. Un adaptateur MCP privé peut proposer `search_documents` et `download_document` en s’appuyant sur Microsoft Graph avec les permissions vérifiées. Le mode délégué représente l’utilisateur ; un accès applicatif à des sites sélectionnés n’imite pas automatiquement les droits individuels. [Permissions Graph sélectionnées](https://learn.microsoft.com/en-us/graph/permissions-selected-overview).

Ce guide ne suppose pas qu’un MCP « SharePoint » universel soit présent. Choisir et auditer un serveur existant ou développer l’adaptateur dans le dépôt d’instance. Le MCP de développement SharePoint Embedded n’est pas, par son seul nom, une connexion documentaire à tous les sites de l’organisation.

## Gabarit de configuration, inactif

```yaml
# Exemple de contrat, pas une configuration prête à appliquer.
mcp_servers:
  documents_prives:
    url: http://documents-mcp.instance.svc.cluster.local:8080/mcp
    tools:
      include: [search_documents, download_document]
```

L’adresse est synthétique. Authentification, transport, allowlist et filtres exacts doivent être qualifiés sur le serveur choisi et la version Hermes fixée. Les tokens restent dans le stockage protégé de l’instance ; ne pas inscrire leur valeur dans YAML ou Git. Un connecteur stdio est installé à version/hash fixés dans le cluster, jamais téléchargé librement par un agent à chaque démarrage.

## Procédure d’intégration

1. Définir outils, données accessibles, identité et classification dans le dépôt d’instance.
2. Auditer source/licence, version/digest, endpoints et risques de lecture/écriture.
3. Fournir une identité déléguée ou un compte de service explicitement borné ; séparer les connexions personnelles.
4. Déployer l’adaptateur et autoriser seulement ses flux nécessaires. Aucun Internet général dans Hermes.
5. Imposer les droits côté serveur avant accès aux résultats ; refuser les identifiants de périmètre non autorisés.
6. Filtrer questions envoyées à un MCP externe et résultats avant modèle cloud ; contrôler aussi fichiers, logs et caches.
7. Tester OAuth, révocation, perte réseau, injection documentaire, refus croisés et actions sensibles.
8. Reporter code, configuration chiffrée, recette, rollback et bootstrap dans le dépôt concerné.

Le filtre LLM actuel protège les appels aux modèles ; il n’assainit pas automatiquement une requête envoyée à n’importe quel SaaS. C’est pourquoi les connecteurs externes restent fermés tant que leur propre chemin n’est pas qualifié.

## Source vivante ou corpus RAG ?

MCP convient aux informations courantes et à des outils ciblés. Le RAG fournit index, versionnement, citations et recherche sur un corpus sélectionné. Une collecte peut copier des documents via MCP/API vers l’ingestion privée, à condition de propager les ACL, suppressions et révocations. Une synchronisation périodique demande une file durable, des checkpoints et des tests ; elle n’est pas activée actuellement.
