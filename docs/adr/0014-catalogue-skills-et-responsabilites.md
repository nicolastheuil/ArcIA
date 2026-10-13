# ADR 0014 — Catalogue riche de skills et responsables des fonctions

Date : 13 octobre 2026. Statut : retenu ; déploiement et recette consignés dans le handoff.

## Besoin

ArcIA doit couvrir de nombreux usages sans se limiter aux six skills retenus lors
du build. Une skill est un contenu procédural avec des références et parfois des
scripts ; sa disponibilité ne prouve ni ses dépendances ni son efficacité.

## Options examinées

| Option | Intérêt | Limite pour ArcIA |
|---|---|---|
| Six adaptations uniquement | Petit périmètre initial | Couverture insuffisante et trop orientée développement |
| Installer tous les packs et leurs hooks | Catalogue large | Mélange les contenus et plusieurs gestionnaires de mémoire, délégation et configuration |
| Télécharger depuis GitHub à chaque demande | Découverte ouverte | Requêtes externes, versions mobiles, indisponibilité et instructions non maîtrisées au moment de l'usage |
| Charger tous les catalogues dans l'index natif | Lecture native progressive | Les descriptions de centaines de skills grossissent tout de même l'index envoyé au modèle ; collisions de noms |
| Catalogue complet local, recherche MCP et chargement à la demande | Richesse, versions reproductibles, requêtes privées locales | Ajoute un petit adaptateur de recherche ; les nouveaux fournisseurs passent par une mise à jour du catalogue |

La dernière option est retenue. Le chargement natif Hermes est conservé pour ses
skills embarquées et les adaptations ArcIA. Le catalogue large est exposé en MCP
stdio dans chaque runtime, sans nouveau service réseau ni état partagé mutable.
Les ids qualifiés par fournisseur et chemin évitent les collisions.

## Place de Vercel

Le CLI `skills` est un gestionnaire de découverte, installation et mise à jour.
Il n'analyse pas spontanément les conversations. `find-skills` fournit à l'agent
la méthode pour chercher une compétence ; ArcIA adapte cette méthode à son
catalogue local. Hermes possède déjà un Skills Hub avec une source skills.sh.
Activer simultanément ces deux installateurs autonomes serait redondant.

Le CLI reste disponible dans K3s pour les opérations d'ingénierie. Il n'est pas le
gestionnaire d'installation des agents. Un catalogue public peut être consulté
depuis un Job d'outillage isolé avec des termes publics ; aucun chemin live externe
de découverte n'est ouvert dans Hermes. Le miroir ne prétend pas couvrir tout
GitHub/skills.sh : il couvre intégralement les racines canoniques retenues.

## Un responsable par fonction

| Fonction | Responsable retenu | Alternatives et configuration |
|---|---|---|
| Mémoire personnelle/profil | Hermes natif | ECC learning/instincts/unified-memory restent des références ; aucun hook ni service mémoire ECC déployé |
| Connaissance commune | Knowledge/RAG avec ACL | Pas de mémoire conversationnelle globale partagée |
| Délégation et état d'agent | Hermes natif | Méthodes Superpowers/ECC consultables ; pas de second orchestrateur ni de lanceur externe activé |
| Gestion de contexte | Hermes natif | Headroom traite les fichiers JSON du workspace avant leur lecture ; pas de proxy global |
| Réduction de sorties CLI | RTK, hook natif limité à git log simple | Complément local ; pas d'interception automatique de toutes les commandes |
| Routage modèle | Passerelle ArcIA filtrée | OmniRoute automatique reste différé ; les skills ne configurent pas les fournisseurs ni budgets |
| Découverte et lecture des skills | Catalogue local ArcIA + chargeur natif Hermes | Vercel est un outil complémentaire de catalogue, pas une seconde autorité d'exécution |

Ces choix ne suppriment pas les textes correspondants du catalogue. Leur lecture
ne déploie aucun plugin, hook, dépendance ou accès supplémentaire. Ce sont des
règles d'intégration et de permissions existantes, pas une garantie qu'un modèle
obéira à toutes les instructions ni qu'un agent ne peut modifier son propre état.

## Mise à jour et qualification

Sources fixées par commit et archive SHA256 ; index déterministe et empreintes de
chaque fichier texte. Les licences particulières sont référencées par entrée et
leurs fichiers restent dans le miroir. Révision candidate → revue → tests → Job
contrôlé → recettes des deux runtimes → livraison main. Aucun suivi flottant de
main ni auto-update depuis une session utilisateur. Le rebuild neuf reste non
exécuté. [Fonctionnement complet](../skills.md).

## Sources primaires

- [Hermes Skills System](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)
- [Hermes épinglé : adaptateur skills.sh](https://github.com/NousResearch/hermes-agent/blob/818c13be1dc4fd28987e1e881a9408224afd4535/tools/skills_hub_skillssh.py)
- [Vercel CLI épinglé](https://github.com/vercel-labs/skills/tree/671e8c320810d36fed80fac5f1a2c1bf7e82d812)
- [Sources et révisions du catalogue](../../builder/skills.lock.json)
