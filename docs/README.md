# Documentation d’ArcIA

Le [README principal](../README.md) donne la vue synthétique du projet.
L’[architecture](architecture.md) est la source de vérité technique unique du socle générique. Les documents ci-dessous sont les
références complètes, regroupées par fonction.

## Architecture et cadrage

| Document | Portée |
|---|---|
| [Architecture](architecture.md) | Composants, réseau, stockage, flux et carte du code |
| [AGENTS.md](../AGENTS.md) | Instructions d'ingénierie et règles de développement |

## Guides fonctionnels

| Besoin | Référence complète |
|---|---|
| Comprendre ArcIA, les instances et le partage | [Plateforme](guides/plateforme-arcia.md) |
| Déployer ArcIA sur n'importe quel cluster Kubernetes | [Déploiement universel](guides/deploiement-universel.md) |
| Infrastructure, stockage CSI, Traefik et Cert-Manager | [Infrastructure K3s](guides/infrastructure-k3s.md) |
| Portail conversationnel, SSO Entra ID, BYOK & OAuth | [Portail Open-WebUI & Entra ID](guides/portail-webui-entraid.md) |
| Moteur d'agents, Studio Kanban et Gateway Desktop | [Hermes Agent](guides/hermes-agent.md) |
| Chaîne de routage IA, modèles et cycle de vie d'un prompt | [Chaîne de Routage IA](guides/chaine-de-routage.md) |
| Passerelle LLM, routage auto et fallbacks | [Inférence LiteLLM](guides/inference-litellm.md) |
| Caviardage automatique des secrets et des PII | [Confidentialité Presidio DLP](guides/confidentialite-presidio.md) |
| Bot conversationnel Microsoft Teams | [Intégration Teams](guides/integration-teams.md) |
| Routage multi-fournisseurs et portail LAN | [OmniRoute](guides/omniroute.md) |
| Frontières de sécurité et protection des données | [Politique de sécurité](guides/securite.md) |
| Découvrir et maintenir les compétences | [Skills](guides/skills.md) |
| Réduire le contexte et économiser les tokens | [Tokenmaxing](guides/tokenmaxing.md) |
| Analyse AST Graphify, Ponytail et Public-APIs | [Outillage Builder & Sobriété](guides/outillage-builder.md) |
| Ajouter une source vivante ou un outil | [Connecteurs MCP](guides/connecteurs-mcp.md) |
| Vérifier versions, images et support | [Versions](guides/versions-officielles.md) |

<a id="exploitation"></a>
## Exploitation

| Procédure | Référence |
|---|---|
| Déploiement en 3 étapes, clés LiteLLM, usage et recette | [Quickstart complet](runbooks/quickstart.md) |
| Maintenance quotidienne, diagnostic, logs et validation | [Exploitation & Maintenance](runbooks/exploitation.md) |
| Sauvegarder, restaurer et reconstruire | [Sauvegarde/reconstruction](runbooks/sauvegarde-reconstruction.md) |

## Pilotage et preuves

L’[architecture](architecture.md) constitue la source de vérité technique unique du socle déployé. Les états de reprise, secrets et configurations particulières d'une instance appartiennent à son dépôt privé d'instance.

**Proposé** : cible décidée ; **codé** : artefact présent ; **déployé** : appliqué
à une cible désignée ; **vérifié** : scénario exécuté et preuve consignée.
Une CI synthétique ne qualifie pas une reconstruction VMware neuve.

