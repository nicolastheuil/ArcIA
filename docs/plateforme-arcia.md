# ArcIA : périmètre, fonctionnement et partage

ArcIA est une plateforme IA agentique d’entreprise. Hermes est son moteur d’agents ; `arcia-harness` est le dépôt de son socle générique. Aucun domaine, métier, compte fournisseur ou corpus privé d’une organisation ne définit le produit.

## Capacités et exemples

Les agents utilisent des outils autorisés, consultent une connaissance documentaire, délèguent des tâches bornées et produisent des réponses ou fichiers vérifiables. Une même plateforme peut servir uniquement à rechercher dans des manuels, comparer des versions d’API, réutiliser des schémas, croiser plusieurs documents ou préparer un livrable. Des connecteurs supplémentaires peuvent ouvrir d’autres capacités après qualification. Ce sont des exemples ; aucun workflow métier n’est imposé.

Le contenu retrouvé est une preuve à citer, jamais une instruction de sécurité. Les services fixent les droits et classifications indépendamment du texte produit par le modèle. Les agents n’obtiennent ni privilège Kubernetes ni autorité implicite d’exécution.

## Deux dépôts, deux responsabilités

| Socle générique : arcia-harness | Dépôt de chaque instance |
|---|---|
| Architecture, moteur, outillage et interface des connecteurs | Populations, usages, sources et adaptateurs spécifiques |
| Contrôles de confidentialité et contrats d’autorisation | Groupes, habilitations et classifications de l’organisation |
| Bootstrap, manifests, locks, tests synthétiques et runbooks | Surcharges, références de secrets et bootstrap d’instance |
| Exemples synthétiques et documentation produit | Documentation d’exploitation spécifique et sauvegardes chiffrées autorisées |

Un dépôt privé ne remplace pas le chiffrement. Les documents et secrets bruts restent dans le stockage privé ; les clés de récupération sont externes à Git. Le code d’instance référence une révision précise du harness. Une capacité réutilisable remonte au harness ; une règle d’usage particulière reste dans l’instance.

## Partage et cloisonnement

L'identité par défaut repose sur des comptes locaux permanents Keycloak,
administrés via `/admin/users`. Les SSO comme Entra ID peuvent fonctionner
en parallèle et se lier explicitement à la même identité. Le provider OIDC
impose propriétaire et client du runtime ; authentification, provisioning et
ACL restent des responsabilités distinctes. [Référence identité](identite-utilisateurs.md).

| Niveau cible | Lecture et partage | État actuel |
|---|---|---|
| Connaissance commune | Sources approuvées accessibles aux utilisateurs habilités de l’entreprise | Corpus commun synthétique accessible aux lecteurs A/B |
| Espace restreint | Groupe/équipe avec ACL explicites, y compris recherche, assets et caches | Périmètres personnels A/B sous RLS ; groupes dynamiques non intégrés |
| Espace personnel | Conversations, mémoire, fichiers et connexions propres à une identité | Deux runtimes et quatre PVC distincts ; authentification locale de qualification |
| Tâche déléguée | Capacité limitée aux ressources et actions nécessaires | Délégation Hermes disponible ; propagation d’identité/permissions à intégrer |

L’authentification identifie l’utilisateur. Une politique serveur calcule les périmètres accessibles et choisit les connexions autorisées. L’agent ne fournit jamais la preuve de ses propres droits. Le filtre des ACL doit intervenir avant classement, téléchargement et restitution ; la confidentialité s’applique également aux titres, logs, exports et caches.

Le service Knowledge impose une liste de lecture et un périmètre d’écriture liés au jeton serveur. FORCE RLS PostgreSQL applique « commun + personnel » avant recherche et téléchargement. Les groupes, l’identité Entra et leur cycle de révocation restent à intégrer. La [recette multi-utilisateur](multi-utilisateur.md) distingue ces limites des refus croisés réellement testés.

Chaque runtime Hermes conserve un propriétaire unique de son état SQLite. Des
profils ou sous-agents ne constituent pas une isolation de sécurité. Les deux
espaces de qualification sont rattachés à l'annuaire local central ; le
provisioning général de nouveaux runtimes et les ACL dynamiques restent à livrer.

## Parcours d’une demande

1. Identifier la session et établir son périmètre côté serveur.
2. Consulter les sources pertinentes ou un MCP autorisé ; conserver provenance et version.
3. Assainir l’ensemble du contexte avant un modèle cloud et vérifier la classe de données autorisée.
4. Produire une réponse avec sources ou un livrable relié à ses originaux.
5. Pour une action externe, recontrôler permissions, plan, approbation et idempotence avant exécution.

L’étape 1 reste une authentification locale de qualification. Les actions externes approuvées, les connecteurs d’entreprise et l’IAM complet restent à construire. La [recette](runbooks/recette-fondatrice.md), le [guide MCP](connecteurs-mcp.md) et le [filtrage cloud](confidentialite-cloud.md) indiquent ce qui est réellement vérifié.
