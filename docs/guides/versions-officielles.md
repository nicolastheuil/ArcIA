# Versions et compatibilités — ArcIA v0.7.0

Le registre [deploy/versions.json](../../deploy/versions.json) fixe les **cibles en développement**, vérifiées auprès des sources officielles le **19 octobre 2026**. Il ne certifie ni leur déploiement sur l’instance ni la recette de la plateforme complète. Les tags sont accompagnés du digest OCI exact dans les manifestes, Dockerfile et le laboratoire.

## Composants gérés par ArcIA

| Composant | Version cible | Image (digest dans le registre) |
|---|---|---|
| presidio-dlp | `2.2.364` | `python:3.14.8-slim-bookworm` |
| oauth2-proxy | `v7.15.5` | `quay.io/oauth2-proxy/oauth2-proxy:v7.15.5` |
| litellm-proxy | `v1.106.0` | `ghcr.io/berriai/litellm:v1.106.0` |
| hermes-agent | `v0.22.2` | `nousresearch/hermes-agent:v0.22.2` |
| teams-bot | `v4.17.1` | `python:3.14.8-slim-bookworm` |
| open-webui | `v0.12.3` | `ghcr.io/open-webui/open-webui:v0.12.3` |
| litellm-db | `18.6` | `postgres:18.6-alpine` |

Presidio utilise les paquets `presidio-analyzer` et `presidio-anonymizer` 2.2.364 ; son image Python est un support d’exécution. Les dépendances directes sont fixées dans [requirements.txt](../../services/presidio/requirements.txt), celles de Teams dans son [requirements.txt](../../services/teams/requirements.txt). La synchronisation en ConfigMaps et les Dockerfile consomment les mêmes fichiers. Les dépendances transitives ne constituent pas encore un lock avec hashes : reconstruire les images nécessite une qualification, même si le digest des bases ne change pas.

## Exceptions de compatibilité explicites

- Python global : **3.15.0** ; Python retenu : **3.14.8**, car Presidio 2.2.364 et spaCy 3.8.16 exigent `<3.15`.
- NumPy global : **2.5.4** ; version retenue : **2.4.6**, car Presidio exige `<2.5`.
- Modèles spaCy : `fr_core_news_sm` et `en_core_web_sm` **3.8.0**, compatibles avec spaCy **3.8.16**.
- Docker Lab : dernières images Microsoft publiées **2.2.362**, distinctes des paquets Python **2.2.364** du service ArcIA. Les tags 2.2.364 n’existent pas dans MCR ; aucune image fictive n’est déclarée. Le Lab reste un outil de développement.
- Bot Framework Python : **4.17.1**, SDK archivé. Mettre à jour ce paquet ne rétablit pas son support ; migration vers Microsoft 365 Agents SDK à prévoir dans un lot distinct.

## Infrastructure du cluster partagé et supervision prévue

| Composant | Dernière stable relevée | Application de cette décision |
|---|---|---|
| K3s | `v1.37.1+k3s1` | Version observée du serveur Kubernetes ; trois nœuds prêts sur le cluster existant ; aucune mise à niveau effectuée |
| Traefik | `v3.7.15` | Cible du contrôleur partagé ; version installée à inventorier avant changement du chart K3s |
| cert-manager | `v1.21.2` | Cible ; CRD, webhook et contrôleurs à traiter ensemble, aucun changement global effectué |
| Prometheus | `v3.15.0` | Image et digest préparés ; installation prévue au lot supervision |
| Grafana | `13.2.4` | Image et digest préparés ; installation prévue au lot supervision |

Ces composants ne sont pas ajoutés à la liste des mises à jour applicatives du wizard : le provider doit gérer les changements partagés. Aucun nom de nœud, adresse, identité ou secret d’instance n’est enregistré dans le dépôt générique.

## PostgreSQL et réapplication d’une instance existante

PostgreSQL **18.6** est la dernière stable ; la branche 19 est encore en préversion. Le passage depuis PostgreSQL 16 est une migration majeure, jamais un simple remplacement d’image sur l’ancien volume. `deploy.py` vérifie le StatefulSet et le PVC **avant toute mutation**, et refuse un changement majeur, une version inconnue, un volume orphelin ou une lecture impossible. L’application directe par Kustomize ne possède pas ce précontrôle : ne pas l’utiliser pour une migration majeure.

Parcours de migration à recetter avant l’instance :

1. Relever la version effective, l’espace disponible et les extensions par un programme local protégé ; vérifier une sauvegarde restaurable et conserver l’ancien volume.
2. Suspendre les écritures LiteLLM et les modifications de clés/budgets. Exporter la base dans le stockage privé chiffré de l’instance ; aucun export dans le dépôt public.
3. Restaurer sur une base 18.6 et un **nouveau** volume, dans un périmètre isolé. L’image officielle 18 modifie son emplacement de données par défaut ; le manifeste ArcIA conserve explicitement `PGDATA=/var/lib/postgresql/data/pgdata` et son montage existant pour éviter une initialisation à un autre emplacement.
4. Vérifier schéma/migrations LiteLLM, clés existantes, identités, budgets et comptabilité avec le nouveau proxy. Recetter arrêt/reprise et restauration avant la bascule.
5. Basculer la connexion avec fenêtre de maintenance ; garder l’ancien ensemble arrêté pour un retour arrière avant nouvelles écritures. Un retour après écritures demande une réconciliation, pas un simple rollback Kubernetes.

Ce parcours est **proposé**, pas un outil de migration déjà implémenté. Le blocage du déploiement reste actif tant que cette étape n’est pas réalisée. Les essais synthétiques utilisent une base jetable indépendante.

## Pods Power Users existants

Le relais refuse désormais une image de runtime ne correspondant pas exactement au verrou du registre. Un ancien pod déclaré avec le seul tag `v0.22.2` doit donc être vérifié et sa déclaration épinglée sur le digest qualifié avant réassociation. Conserver son Deployment, sa commande, son identité, `SOUL.md` et son PVC ; ne pas créer un runtime de remplacement ni réinitialiser ses données pour contourner ce refus. Cette adaptation des pods de l’instance reste une étape du rollout, non exécutée pendant la qualification synthétique.

## Sources officielles

- [LiteLLM 1.106.0 et nom de l’image publiée](https://github.com/BerriAI/litellm/releases/tag/v1.106.0), [Hermes 0.22.2](https://github.com/NousResearch/hermes-agent/releases/tag/v0.22.2), [Open-WebUI 0.12.3](https://github.com/open-webui/open-webui/releases/tag/v0.12.3).
- [Presidio 2.2.364](https://github.com/data-privacy-stack/presidio/releases/tag/2.2.364), [contraintes Python Presidio](https://pypi.org/project/presidio-analyzer/2.2.364/), [spaCy 3.8.16](https://pypi.org/project/spacy/3.8.16/).
- [OAuth2 Proxy 7.15.5](https://github.com/oauth2-proxy/oauth2-proxy/releases/tag/v7.15.5), [versions PostgreSQL](https://www.postgresql.org/support/versioning/), [image officielle PostgreSQL et données](https://hub.docker.com/_/postgres), [versions Python](https://www.python.org/downloads/).
- [K3s 1.37.1](https://github.com/k3s-io/k3s/releases/tag/v1.37.1%2Bk3s1), [Traefik 3.7.15](https://github.com/traefik/traefik/releases/tag/v3.7.15), [cert-manager 1.21.2](https://github.com/cert-manager/cert-manager/releases/tag/v1.21.2).
- [Prometheus 3.15.0](https://github.com/prometheus/prometheus/releases/tag/v3.15.0), [Grafana 13.2.4](https://github.com/grafana/grafana/releases/tag/v13.2.4), [fin du support Bot Framework](https://learn.microsoft.com/en-us/azure/bot-service/what-is-new?view=azure-bot-service-4.0).
