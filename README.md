# ArcIA — plateforme IA agentique d’entreprise

**ArcIA associe des agents capables de collaborer, une connaissance documentaire privée et des outils pour consulter des systèmes ou produire des livrables.** La plateforme ne présuppose aucun métier : ce sont les données ingérées, les connecteurs et les droits configurés dans chaque instance qui déterminent ses usages. `arcia-harness` contient le socle réutilisable et son installation ; les adaptations d’une organisation vivent dans un dépôt d’instance distinct. [Périmètre et philosophie](docs/plateforme-arcia.md).

## Comment fonctionne ArcIA ?

Une demande arrive au moteur d’agents Hermes. Celui-ci peut rechercher des sources, appeler des outils MCP, déléguer une partie du travail à des agents spécialisés et réunir les résultats. La réponse doit conserver ses références et ses incertitudes. Les permissions sont imposées par les services ; ni un document ni un agent ne peut s’octroyer des droits. Les actions externes sensibles nécessiteront une autorisation vérifiée côté serveur. [Fonctionnement et frontières](docs/plan-integration-hermes.md).

```mermaid
flowchart LR
  U[Utilisateur] --> E[Entrée HTTPS et identité]
  E --> A[Hermes : agents et outils]
  A --> R[RAG privé : sources et citations]
  A --> M[Connecteurs MCP autorisés]
  A --> P[Presidio et politique de sortie]
  P --> G[Relais cloud contrôlé]
  G --> L[Modèles autorisés]
  R --> D[PostgreSQL et stockage privé]
```

Le socle tourne dans **K3s sur trois VM Debian/VMware**. PostgreSQL/pgvector conserve la connaissance et ses index ; Hermes conserve son propre état sur un volume exclusif. Les outils applicatifs sont installés dans le cluster. Le poste sert uniquement à administrer le déploiement avec un état protégé. [Architecture et schémas](docs/architecture.md) · [Schémas détaillés](docs/schemas-plateforme-hermes.md).

## À quoi servent les composants ?

| Composant | Apport à ArcIA | Activation actuelle |
|---|---|---|
| **Hermes** | Conversations, outils, profils, skills et délégation à des sous-agents | Moteur et dashboard de qualification |
| **Knowledge / PostgreSQL / pgvector** | RAG avec versions, citations, recherche textuelle, vecteurs et reclassement multi-vecteur | Déployé ; corpus synthétique |
| **Presidio** | Détection FR/EN, pseudonymisation et suppression de secrets avant cloud | Déployé avec filtres techniques et contrôle du payload complet |
| **OmniRoute** | Choix et routage entre modèles/fournisseurs | Installé ; routage automatique à qualifier |
| **Headroom** | Réduction du contexte transmis aux modèles | Installé ; compression automatique différée |
| **RTK** | Réduction des sorties de commandes pour limiter le contexte | Installé ; sans interception automatique |
| **Context7 MCP** | Recherche de documentation de bibliothèques | Installé ; requêtes externes bloquées en attendant leur adaptateur filtrant |
| **Superpowers / ECC** | Skills sélectionnés de méthode, vérification et développement | Six skills natifs chargés ; aucun apprentissage partagé automatique |
| **skills CLI / LintLang** | Distribution contrôlée des skills et analyse statique des instructions | Installés et versions vérifiées |
| **NGINX / Certbot** | Entrée HTTPS et certificats | TLS actif ; renouvellement DNS manuel à automatiser |

Installation, versions, limites et provenance : [outillage](docs/outillage-builder.md), [locks](versions.lock.yaml). Aucun outil de compression ne remplace le filtrage de confidentialité.

## Donner de la matière au RAG

On sélectionne des PDF textuels, guides, spécifications OpenAPI, JSON Schema ou schémas éditables, puis on associe à chaque source **provenance, version et périmètre d’accès**. L’ingestion locale conserve l’original et son empreinte, extrait le contenu, découpe les passages et calcule les représentations de recherche. Une question retrouve des extraits autorisés avec leur page/opération, version et source ; les schémas originaux peuvent être téléchargés pour adaptation. [Formats, alimentation et API](docs/connaissance-documentaire.md).

Exemple : charger le guide PDF et la spécification OpenAPI d’un produit fictif, puis demander « Compare les paramètres de restauration entre les versions 1 et 2, avec les sources » ou « Retrouve le schéma d’architecture et prépare une adaptation ». Le parcours combine full-text, vecteurs titre/corps et **MaxSim multi-vecteur**. L’OCR des scans, la compréhension visuelle avancée et l’interface d’import générale restent à qualifier. [Choix et coûts](docs/connaissance-documentaire.md).

## Brancher d’autres sources et outils MCP

Un MCP expose des fonctions à l’agent : rechercher dans SharePoint, consulter HubSpot, lire une API interne, etc. On choisit un serveur ou un adaptateur vérifié, fixe sa version, limite ses outils, enregistre l’identité dans un stockage protégé, puis autorise uniquement les flux nécessaires. Ses résultats repassent par le filtre avant tout modèle cloud. Les connecteurs propres à une organisation se configurent dans son dépôt d’instance. [Guide MCP, exemples HubSpot/SharePoint et recette](docs/connecteurs-mcp.md).

**MCP et RAG se complètent** : MCP interroge une source vivante ; le RAG indexe un corpus sélectionné et versionné. Un connecteur peut alimenter le RAG, mais la synchronisation et la reprise des droits doivent être développées explicitement. HubSpot/SharePoint ne sont pas installés dans le socle actuel.

## Partager la connaissance sans partager tous les accès

La cible sépare les **sources d’entreprise communes aux personnes habilitées**, les espaces restreints à un groupe et les espaces personnels. Les conversations, mémoires et connexions personnelles restent distinctes. Chaque recherche, téléchargement, outil et cache doit respecter les droits côté serveur ; un agent délégué hérite d’un périmètre borné. [Modèle de partage et de cloisonnement](docs/plateforme-arcia.md#partage-et-cloisonnement).

**Aujourd’hui :** deux espaces Hermes de qualification avec authentification locale, états/outils/volumes distincts et connaissance commune + personnelle sous RLS. La recette vérifie sessions, accès concurrents, redémarrages et refus croisés. Le SSO d’entreprise, les groupes et l’onboarding général restent à intégrer ; les essais utilisent uniquement des données synthétiques. [Séparation et recette multi-utilisateur](docs/multi-utilisateur.md).

## Modèles cloud et confidentialité

Les appels passent par **Presidio → relais authentifié → OpenRouter**, sans clé fournisseur dans Hermes, sans Internet direct ni DNS libre depuis ses agents. La qualification autorise seulement `openrouter/free`, avec ZDR, collecte interdite et plafond de prix nul ; aucune bascule payante. Images, fichiers encodés et payloads non pris en charge sont refusés. Presidio réduit les risques de fuite mais ne garantit pas une anonymisation exhaustive. [Politique, filtres et limites](docs/confidentialite-cloud.md).

La protection combine identités, sessions, états séparés, droits documentaires serveur, segmentation réseau et filtrage du contexte. Les secrets, historiques, originaux et sauvegardes ont des exigences distinctes. [Sécurisation de la plateforme et des données : frontières, preuves et limites](docs/securisation-plateforme-donnees.md).

La trajectoire de routage est OmniRoute automatique → OpenRouter free → OpenRouter auto, toujours sous la même politique. L’automatisation et le dernier repli payant restent différés ; un fournisseur indisponible ou non conforme provoque un refus.

## Installer, vérifier et reprendre

Le bootstrap couvre les VM/fondations, K3s, VMware CSI, PostgreSQL, Hermes, connaissance, outils, filtrage et vérifications. Il s’arrête à la première erreur et conserve un journal protégé. Secrets, domaines et inventaires réels restent hors Git en clair. [Procédure complète, prérequis et reprise](docs/runbooks/bootstrap.md).

```powershell
./scripts/Bootstrap-Harness.ps1 -Mode Plan -Profile Fresh -ProvisionVMs
./scripts/Bootstrap-Harness.ps1 -Mode Apply -Profile Reconcile
./scripts/Bootstrap-Harness.ps1 -Mode Verify
./scripts/Show-PilotAccess.ps1
```

Les livraisons vont directement sur `main`. La réconciliation du cluster existant est testée ; **rebuild sur cluster neuf, sauvegarde/restauration complète et panne brutale restent des gates de release**. [État de reprise](docs/etat-reprise.md) · [Backlog](docs/backlog.md) · [Documentation complète](docs/README.md).
