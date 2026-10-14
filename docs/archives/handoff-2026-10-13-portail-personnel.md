# Handoff — comptes administrés et premier espace personnel

> Archive historique. Pour la reprise actuelle, lire [l’état courant](../etat-reprise.md).

## Cause du refus de connexion

Le retour `Invalid code: ARCIA_LOGIN_REFUSED` venait du dashboard Hermes après
une authentification Keycloak réussie. L'inspection protégée a confirmé que
les deux UUID propriétaires historiques avaient été supprimés du realm, et
que les nouvelles connexions utilisaient d'autres UUID. Le refus protégeait
les anciens états. Aucun compte ni volume historique n'a été réaffecté.

L'administrateur a demandé qu'un nouvel utilisateur obtienne automatiquement
un espace personnel vide à sa première connexion. L'[ADR 0017](../adr/0017-espaces-personnels-premiere-connexion.md)
décrit le choix du pool borné et les droits du contrôleur.

## Codé et déployé

- Point d'entrée `/portal/` à la racine du domaine, client public PKCE, state
  signé, nonce, signature RS256, issuer/audience et validation UserInfo en ligne.
- Rôle explicite `ArcIA.User` ; message d'habilitation compréhensible et option
  de connexion avec un autre compte. `Open-ArcIA.ps1` ouvre le parcours privé
  depuis le poste de qualification avec un profil distinct de l'administration.
- Huit namespaces préparés, Jobs d'outillage suspendus et runtimes arrêtés.
  Le premier login alloue par `(issuer, sub)`, installe les outils épinglés puis
  active un runtime avec état et outillage RWOP propres. Aucun état importé.
- Roles Kubernetes limités à des objets nommés : binding ConfigMap, Secret OIDC,
  Job fixé et `deployments/scale`. Pas de création de PodSpec, namespace,
  ClusterRole, ni accès exec/logs ; aucun ServiceAccount dans les agents.
- Tokens Knowledge/privacy propres, corpus personnel seulement, NetworkPolicies
  et DNS privés, sortie cloud filtrée gratuite et politique synthétique conservée.
- Refus HTTP supplémentaire dans la boundary si le provider ne valide pas la
  session ; un plugin indisponible ne peut pas exposer une API sans authentification.
- Réapplication : allocation arrêtée pendant le snapshot, bindings et Secrets
  existants jamais écrasés, UUID/PV des claims revérifiés ; refus d'une réduction
  de capacité ou migration d'outillage actif sans procédure distincte.

Le bootstrap compte 51 étapes. Les anciens raccordements/recettes HTTP à deux
propriétaires sont réservés à Fresh, pour ne pas recréer des utilisateurs
supprimés lors d'une réconciliation. Les trois nouvelles étapes sont
install/verify/inspect du portail. Les sources, wrappers et helper sont hashés
dans le lock d'identité. Le client secret hérité, devenu inutile après passage
aux clients publics PKCE, est supprimé explicitement des deux anciens Secrets.

## Vérifié sur la cible existante

Les [preuves assainies](../qualification/2026-10-13-portail-personnel.json) couvrent
31 contrôles : deux connexions au portail et aux dashboards personnels,
historique vide, stabilité de l'attribution, refus des cookies croisés,
API anonyme, CSRF, suspension/révocation, propriétaire unique, absence de jeton
Kubernetes et quatre volumes distincts. Deux comptes synthétiques de recette
restent désactivés après vérification et occupent leurs places réservées.

La réapplication a vérifié huit bindings et seize PVC sans changement d'identité
ni remplacement de volume lié. Les phases de recette ont corrigé un endpoint
OIDC interne incomplet, puis le traitement des champs zéro omis dans Scale.
Les 12 tests spécifiques, six tests du provider, cinq de la frontière
multi-utilisateur, les tests PowerShell et les validations des sources/bootstrap
ont été exécutés. La CI Linux/Windows est le contrôle final de publication.

## Exploitation et limites

Créer/activer le compte et attribuer le rôle de realm `ArcIA.User`, puis ouvrir
la racine du domaine. La première préparation peut prendre plusieurs minutes.
Une suppression suivie d'une recréation du même login alloue un autre espace.
Capacité : huit emplacements au départ, dont deux utilisés par la recette ;
`identity.personal_slots` permet d'étendre à 32 après dimensionnement.

Transfert, purge, récupération de capacité, upgrade des outils actifs, backup/
restore, panne de nœud et rebuild neuf restent à qualifier. Une erreur de
réconciliation après arrêt du contrôleur peut le laisser arrêté : réparer
la cause puis réappliquer, sans modifier les bindings ou recycler un PVC.
HA du contrôleur et matrice complète des flux longs ne sont pas qualifiées.
La fédération Entra réelle, SMTP et ACL de groupes restent distincts. Aucun
contenu privé réel, mot de passe ou jeton n'a été rendu au modèle ou publié.
