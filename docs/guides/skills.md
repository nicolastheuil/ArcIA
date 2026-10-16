# Skills dans ArcIA : disponibilité, découverte et fonctionnement

Une skill décrit comment accomplir une tâche : méthode, critères de vérification,
modèles, références et parfois scripts. Elle complète les outils de l'agent ; elle
ne constitue ni une identité, ni une permission, ni l'installation d'un logiciel.
ArcIA conserve les skills dans K3s et charge les instructions pertinentes au besoin.

## Les différentes origines

| Origine | Ce qu'elle apporte | Intégration ArcIA |
|---|---|---|
| Hermes embarqué | Procédures compatibles avec son moteur et ses outils, dont documents et productivité | 58 skills canoniques dans le miroir ; répertoire natif readonly exposé au chargeur Hermes |
| Hermes optionnel | Compétences supplémentaires : recherche, création, analyse, finance, opérations, etc. | 154 skills consultables dans le catalogue ; dépendances et connexions non activées par la lecture |
| ECC | Méthodes de développement, rédaction, recherche, analyse, organisation et autres domaines | Les 311 skills canoniques sont cataloguées ; les copies traduites et variantes par agent ne sont pas dupliquées |
| Superpowers | Méthodes de préparation, développement, diagnostic et revue | Les 15 skills sont cataloguées ; les hooks et l'orchestrateur du pack ne sont pas installés |
| Vercel `find-skills` | Méthode de découverte de compétences dans l'écosystème ouvert | Workflow disponible ; recherche et chargement remplacés par le parcours local ArcIA |
| Adaptations ArcIA | Six adaptations initiales et une skill d'orientation `arcia-skills` | Chargées nativement ; règles adaptées à l'exploitation et à la confidentialité d'ArcIA |
| Ponytail | Sobriété logicielle, échelle de décision YAGNI et prévention de l'over-engineering | Skill native ArcIA intégrée au catalogue partagé (`skills/ponytail`) |
| Graphify | Cartographie structurelle AST de codebase et GraphRAG local | Skill native ArcIA (`skills/graphify`) couplée à `arcia_graphify.py` (0 token, 0 fuite) |
| Public-APIs | Référentiel de veille et règles de sécurisation des APIs externes | Skill de gouvernance ArcIA (`skills/public-apis`) avec isolation Presidio/NetworkPolicy |

Le miroir compte **539 entrées upstream**, dont les 58 skills Hermes embarquées.
Les entrées ArcIA natives s'ajoutent comme adaptations, compétences de méthode et orientation ([Guide outillage](outillage-builder.md)).

## Parcours d'une demande

```mermaid
flowchart LR
  U[Demande utilisateur] --> H[Hermes identifie une compétence utile]
  H --> N[Chargeur natif : skills embarquées et adaptées]
  H --> S[MCP arcia_skills : recherche locale]
  S --> I[Index : descriptions, source, licence, révision]
  I --> L[Chargement de la skill choisie]
  L --> R[Références ou scripts lus selon le besoin]
  R --> T[Outils déjà autorisés et dépendances disponibles]
  T --> V[Résultat et vérifications]
```

Un plugin natif readonly ajoute une courte orientation au prompt de chaque nouvelle session.
L'agent peut déclencher cette recherche sans demander à l'utilisateur de choisir
un dépôt ou une commande. Sa sélection dépend du modèle et de la demande ; elle
n'est pas un classement universel garanti. Le catalogue ne reçoit que les appels
locaux et ne journalise pas les recherches. Aucune demande n'est envoyée à GitHub
ou skills.sh par ce parcours. Le contexte chargé continue de passer par Presidio
avant un modèle cloud, comme tout résultat d'outil.

Le chargeur natif `skills_list`/`skill_view` conserve son rôle. Les centaines de
descriptions supplémentaires ne sont pas toutes placées dans le prompt initial :
`catalog_search` retourne au plus 30 résultats, 12 par défaut. `catalog_load`
retourne le texte choisi et les noms de références, avec pagination de 48 000
caractères. Lire un script ne l'exécute pas. Les fichiers binaires et fichiers
texte de plus de 2 Mio ne sont pas intégrés ; les instructions SKILL.md dépassant
la limite font échouer le build. Les packs externes ne sont pas installés comme
plugins globaux.

Le panneau Skills et les commandes slash natives montrent le catalogue natif
Hermes et les adaptations. Les 539 entrées du miroir sont accessibles par la
recherche de compétences dans la conversation, via le MCP local ; elles ne sont
pas toutes transformées en commandes slash ou installées dans le profil. Lire
une entrée par ce chemin ne déclenche pas de prétraitement shell upstream. Ce
choix conserve un petit index natif et évite les collisions entre fournisseurs.

Exemples de recherches : `rédaction`, `research`, `pdf`, `presentation`, `market
research`, `security`, `postgres`. Un besoin absent du miroir demande d'ajouter
une source au harness ou une skill propre à l'instance ; l'agent ne prétend pas
l'avoir téléchargée. Une compétence référencée peut demander un logiciel, un
compte ou un MCP absent : cette limite doit être annoncée.

## Ce que Vercel complète réellement

[`skills`](https://github.com/vercel-labs/skills) est un CLI de distribution :
`find` cherche, `add` installe et `update` actualise les installations gérées par
ce CLI. Installer son binaire ne crée pas une découverte automatique dans Hermes.
La skill `find-skills` décrit cette démarche à l'agent.

Hermes dispose déjà d'un Hub et d'un adaptateur skills.sh. ArcIA conserve un seul
parcours utilisateur local : rechercher → lire → appliquer avec les outils
autorisés. Le CLI Vercel reste installé dans le cluster pour les inspections et
imports d'ingénierie. Ses commandes d'update ne gèrent pas le miroir ArcIA, dont
les adaptations, révisions et hashes sont maintenus par le harness. **Il n'existe
pas de téléchargement libre de GitHub à chaque conversation.** Ce choix réduit
les requêtes externes et garantit la reproductibilité sans limiter le catalogue
aux six compétences du build initial.

## Mémoire et fonctions qui se recouvrent

Hermes est le responsable de la mémoire personnelle, du profil et de la délégation.
Chaque runtime conserve son état sur son propre PVC. Les mécanismes ECC de mémoire,
instincts, apprentissage ou export ne sont pas activés ; leurs skills restent
consultables comme méthodes. Les connaissances communes vivent dans le RAG sous
ACL, pas dans une mémoire globale de conversations.

La gestion de contexte native Hermes reste la référence. RTK et Headroom restent cantonnés à des usages explicites d'outillage. La passerelle d'inférence LiteLLM Proxy unifiée gère l'ensemble des flux d'inférence en v0.3 (OmniRoute ayant été retiré du socle par défaut). Aucune instruction de skill ne crée un droit réseau, un budget, un fournisseur ou une autorisation d'action externe.

## Versions, cycle d'installation et mises à jour

Le fonctionnement détaillé, l'inventaire complet des dépôts (ECC, Superpowers, Vercel, Anthropics, ArcIA natifs) et la gouvernance sont documentés dans le guide de référence : [skills/README.md](../../skills/README.md).

### 1. À quel moment les skills sont-elles installées ?
- **Instantanément au déploiement (deploy.py / Setup Wizard)** : Le volume partagé `/var/data/arcia/shared-skills` est monté en lecture seule dans Hermes Agent (`/opt/shared-skills`). Les compétences souveraines ArcIA (**Ponytail**, **Graphify**, **Public-APIs**) sont injectées d'office via le ConfigMap Kubernetes `arcia-native-skills`. Elles sont disponibles dès la première seconde sans accès internet requis.
- **Initialisation des catalogues étendus** : L'administrateur ou le script d'initialisation exécute la synchronisation initiale pour rapatrier les fiches méthodologiques communautaires (ECC, Superpowers, Vercel AI SDK, Anthropics) dans le volume partagé.

### 2. Comment les garder à jour ? (Est-ce un one-shot ?)
L'installation de base n'est pas obligatoirement figée :
- **Mise à jour manuelle à la demande (Recommandée en entreprise)** :
  ```powershell
  # Actualisation sous PowerShell
  .\scripts\Sync-Skills.ps1 -Update
  ```
  ```bash
  # Actualisation sous Linux / Bash
  bash skills/sync-skills.sh --update
  ```
- **Mise à jour automatisée programmée (Kubernetes CronJob optionnel)** :
  ArcIA fournit le manifeste [deploy/manifests/10-skills-sync-cronjob.yaml](../../deploy/manifests/10-skills-sync-cronjob.yaml) pour planifier une synchronisation hebdomadaire automatique. En v0.3, ce CronJob est suspendu par défaut (`suspend: true`) pour prévenir toute dérive externe non sollicitée en environnement d'entreprise.
- **Mode Souverain / Air-Gapped** :
  Toutes les compétences sont figées dans le dépôt Git ou le volume persistant ; aucun flux réseau externe n'est sollicité à l'exécution.


## Crédits, licences et qualification

Chaque compétence intégrée référence son auteur original, sa licence open-source et ses fichiers contrôlés. La licence racine du projet n'écrase pas une licence propre à une skill ou à un script.

« Cataloguée » signifie recherchable et lisible, avec provenance et intégrité.
Cela ne signifie pas « chaque script exécuté », « dépendances installées », ni
« efficacité métier démontrée ». La recette vérifie recherche, chargement, MCP,
crédits, intégrité, refus de chemins/options non autorisés et maintien des
frontières existantes. Les résultats exécutés figurent dans le handoff daté.

Les intégrations RTK et Headroom et leurs mesures sont détaillées dans
[tokenmaxing](tokenmaxing.md). Aucun proxy de compression ou mémoire partagée
Headroom n’est activé.

Les gros résultats JSON des outils de lecture déclarés sont également réduits
automatiquement par un hook natif avant leur entrée en contexte, avec original
exact récupérable dans un cache privé borné. Les résultats RAG, instructions de
skills, erreurs et écritures sont exclus. Les nouvelles connexions MCP d'une
instance doivent qualifier leurs propres outils avant ajout à cette politique.
