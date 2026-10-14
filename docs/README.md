# Documentation d’ArcIA

Le [README principal](../README.md) donne la vue synthétique du projet.
L’[état de reprise](etat-reprise.md) est l’unique handoff courant ; le
[backlog](backlog.md) porte les suites. Les documents ci-dessous sont les
références complètes, regroupées par fonction.

## Architecture et cadrage

| Document | Portée |
|---|---|
| [Architecture](architecture.md) | Composants, réseau, stockage et carte du code |
| [Contrat intégral](plan-integration-hermes.md) | Périmètre et exigences de la plateforme, notamment §26 |
| [Schémas](schemas-plateforme-hermes.md) | Flux actuels et contrats cibles |
| [Installation K3s/Codex](installation-k3s-codex.md) | Fondations et parcours initial |
| [Organisation et maintenance](organisation.md) | Responsabilités des dossiers, reprise unique et validation |
| [AGENTS.md](../AGENTS.md) / [rôle builder](../builder/role.md) | Instructions de construction |

## Guides fonctionnels

| Besoin | Référence complète |
|---|---|
| Comprendre ArcIA, les instances et le partage | [Plateforme](guides/plateforme-arcia.md) |
| Administrer comptes, portail et SSO | [Identité et utilisateurs](guides/identite-utilisateurs.md) |
| Qualifier les espaces et les refus croisés | [Multi-utilisateur](guides/multi-utilisateur.md) |
| Alimenter le RAG et rechercher avec citations | [Connaissance documentaire](guides/connaissance-documentaire.md) |
| Ajouter une source vivante ou un outil | [Connecteurs MCP](guides/connecteurs-mcp.md) |
| Contrôler modèles, filtrage et sorties | [Confidentialité cloud](guides/confidentialite-cloud.md) |
| Configurer OmniRoute, abonnements et overrides autorisés | [OmniRoute](guides/omniroute.md) |
| Comprendre les frontières et leurs preuves | [Sécurisation plateforme et données](guides/securisation-plateforme-donnees.md) |
| Appliquer les règles de sécurité | [Politique de sécurité](guides/securite.md) |
| Découvrir et maintenir les compétences | [Skills](guides/skills.md) |
| Réduire le contexte et comprendre les mesures | [Tokenmaxing](guides/tokenmaxing.md) |
| Administrer les outils et leur provenance | [Outillage builder](guides/outillage-builder.md) |
| Vérifier versions, locks et support | [Versions](guides/versions-officielles.md), [lock](../versions.lock.yaml), [crédits](../THIRD_PARTY_NOTICES.md) |
| Préparer Entra, Teams, SharePoint et Outlook | [Annexe Microsoft 365](annexes/integration-microsoft365.md) |

<a id="exploitation"></a>
## Exploitation

| Procédure | Référence |
|---|---|
| Plan / Fresh / Reconcile / Verify / Audit | [Bootstrap](runbooks/bootstrap.md) |
| Démarrer : authentification, OmniRoute, ArcIA et Teams optionnel | [Quickstart complet](runbooks/quickstart.md) |
| Prérequis de déploiement | [Préparation](runbooks/preparer-deploiement.md) |
| Inventaire et préparation VMware | [vCenter](runbooks/vcenter.md) |
| Exploiter le pilote existant | [Exploitation de qualification](runbooks/exploitation-qualification.md) |
| Émission, DNS et renouvellement TLS | [Certificats](runbooks/certificats-dns.md) |
| Évaluer les résultats et les gates | [Recette fondatrice](runbooks/recette-fondatrice.md) |
| Sauvegarder, restaurer et reconstruire | [Sauvegarde/reconstruction](runbooks/sauvegarde-reconstruction.md) |

## Pilotage et preuves

L’[état de reprise](etat-reprise.md) résume les derniers résultats consignés et
l’ordre de reprise. Le [backlog](backlog.md) indique les travaux ouverts.
Les [preuves de qualification](qualification/) sont datées et assainies.
Les [archives](archives/README.md) conservent les anciennes transmissions et
rapports ; leur lecture n’est pas un prérequis de reprise.

**Proposé** : cible décidée ; **codé** : artefact présent ; **déployé** : appliqué
à une cible désignée ; **vérifié** : scénario exécuté et preuve consignée.
Une CI synthétique ne qualifie pas une reconstruction VMware neuve.

<a id="decisions"></a>
## Décisions

| ADR | Décision |
|---|---|
| [0001](adr/0001-cible-et-limites.md) | Cible fondatrice et périmètre de préparation |
| [0002](adr/0002-secrets-et-configuration.md) | Configuration locale protégée |
| [0003](adr/0003-bootstrap-k3s-et-stockage.md) | Bootstrap K3s épinglé et stockage explicite |
| [0004](adr/0004-vcenter-et-image-debian.md) | Connexion vCenter privée et disque Debian |
| [0005](adr/0005-verification-ssh-hors-bande.md) | Vérifier SSH depuis le canal VMware approuvé |
| [0006](adr/0006-reseaux-evolutifs-et-fondations.md) | Réseaux évolutifs et qualification des fondations |
| [0007](adr/0007-vip-et-bootstrap-synthetique.md) | VIP et périmètre des gates de bootstrap |
| [0008](adr/0008-qualification-applicative-et-tls.md) | Qualification applicative, état exclusif et TLS différé |
| [0009](adr/0009-connaissance-hybride-multivecteur.md) | Recherche hybride et multi-vecteur locale |
| [0010](adr/0010-outils-hermes-main-et-acces.md) | Outils dans Hermes/K3s et livraison main |
| [0011](adr/0011-bootstrap-exhaustif.md) | Bootstrap exhaustif et évolutif d’ArcIA |
| [0012](adr/0012-arcia-generique-et-confidentialite.md) | ArcIA générique, instances distinctes et cloud filtré |
| [0013](adr/0013-qualification-multi-utilisateur.md) | Runtimes personnels et qualification locale multi-utilisateur |
| [0014](adr/0014-catalogue-skills-et-responsabilites.md) | Catalogue riche de skills et responsables des fonctions |
| [0015](adr/0015-preparation-microsoft365.md) | Préparation Microsoft 365 et configuration d'instance |
| [0016](adr/0016-identite-locale-permanente.md) | Identité locale permanente, par défaut, et fédération parallèle |
| [0017](adr/0017-espaces-personnels-premiere-connexion.md) | Espace personnel à la première connexion |
| [0018](adr/0018-plan-reparation-sortie-keycloak.md) | Plan borné de réparation de la sortie Keycloak |
| [0019](adr/0019-organisation-documentaire.md) | Documentation par fonction et reprise unique |
| [0020](adr/0020-perimetre-harness-et-politiques-instance.md) | Périmètre générique et politiques de routage d’instance |
| [0021](adr/0021-cles-fournisseurs-personnelles.md) | Clés personnelles chiffrées, rôle explicite et activation distincte |
| [0022](adr/0022-providers-personnels-sous-arcia.md) | Providers personnels en parallèle d'OmniRoute, avec tous les contrôles ArcIA |
