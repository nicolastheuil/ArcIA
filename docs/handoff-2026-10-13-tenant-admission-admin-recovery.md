# Reprise — récupération admin et admission Microsoft du tenant

État au 13 octobre 2026 : code livré, corrections appliquées sur exception
humaine limitée aux deux changements et lectures serveur vérifiées. Les
preuves privées restent sous DPAPI ; aucune identité, UUID, donnée de tenant
ou valeur secrète dans Git.

Le compte local nommé par le propriétaire existait et portait `ArcIA.Admin`,
mais pas `realm-management.realm-admin`. Le compte initial avait été supprimé.
Le rôle existant `realm-admin` a été attribué au seul UUID du compte nommé,
sans création d'utilisateur, reset password ou modification MFA. Lecture
ultérieure : rôle effectif présent. L'accès interactif à la console depuis
le poste du propriétaire reste à confirmer séparément.

Un seul fournisseur Microsoft activé pour un tenant UUID précis était
configuré. Le mapper `arcia-tenant-users` lui attribue désormais `ArcIA.User`
avec `oidc-hardcoded-role-idp-mapper`, synchronisation FORCE. L'inspection
retrouve le mapper attendu sans dérive. Un compte fédéré observé porte le rôle
utilisateur et a obtenu un espace personnel. Aucun rôle administrateur n'est
attribué automatiquement au tenant. Les comptes locaux, l'inscription locale,
la fusion automatique par email et les autres fournisseurs sont inchangés.

Les sessions créées avant cette correction peuvent nécessiter une déconnexion
et un nouveau parcours Microsoft depuis l'accueil. Un refus `/admin/users`
pour un compte Microsoft simplement utilisateur est attendu : employer le
compte local récupéré pour administrer. Sur le premier PC, l'ancien message
« OAuth state mismatch (CSRF check failed) » doit conduire à recommencer depuis
l'accueil, sans désactiver la vérification CSRF. L'utilisateur a confirmé que
Microsoft fonctionnait sur son second PC.

Le plan et l'apply sont séparés : opération, realm, UUID du compte, alias,
tenant, hash et validité de dix minutes. Ressources étrangères, comptes
inactifs/service accounts pour la récupération, collisions de mapper et de
client `ArcIA`, changements de tenant et plans expirés sont refusés.
`identity-access-policy.dpapi` conserve la politique appliquée. Audit détecte
une dérive sans réattribuer de privilèges automatiquement. L'exception est
tracée comme humaine ; aucune approbation Teams serveur n'est revendiquée.

Population précisée : environ trente collaborateurs. Le pool initial de huit
places doit être porté à trente-deux après le nettoyage explicitement demandé
de l'espace appartenant au compte supprimé. Deux espaces de comptes présents
mais désactivés restent conservés. Voir le
[handoff courant](handoff-2026-10-13-identity-public-https.md) pour le réseau,
la capacité et les résultats du nettoyage.

Demandes à conserver : créer entièrement le bot Teams, les anciens objets
Azure ayant été supprimés. Aucune ressource Teams/Azure créée ici. Réenrôler
l'identité administrative et la cible Azure par programme local protégé ;
les anciens secrets ne doivent pas être considérés comme valides.

Sources primaires :
[mapper Keycloak 26.8.1](https://github.com/keycloak/keycloak/blob/26.8.1/services/src/main/java/org/keycloak/broker/provider/HardcodedRoleMapper.java),
[résolution des rôles](https://github.com/keycloak/keycloak/blob/26.8.1/server-spi-private/src/main/java/org/keycloak/models/utils/KeycloakModelUtils.java).