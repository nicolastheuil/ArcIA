# ADR 0016 — Identité locale permanente, par défaut, et fédération parallèle

Statut : adopté le 13 octobre 2026 sur instruction du propriétaire.

L'annuaire local Keycloak est une fonction permanente du harness et sa solution
d'identification par défaut. Il offre console de gestion et compte utilisateur.
Entra ID/autres SSO peuvent fonctionner en parallèle, via brokering OIDC, sans
supprimer les comptes locaux. Les identités liées conservent le même subject ;
aucune fusion ou attribution de propriété automatique fondée sur l'email.

Keycloak porte comptes, MFA, parcours de connexion et administration du realm.
ArcIA porte propriétaire de runtime, rôles applicatifs, ACL, outils, quotas et
approbations. Un compte authentifié ne devient pas administrateur d'annuaire
ou propriétaire de tous les espaces. Les clients runtimes sont publics PKCE,
PKCE, sans password grant/service account ; signature + validation UserInfo et
propriétaire imposés par le provider ArcIA. Les anciens mots de passe de
qualification ne restent pas un bypass une fois l'espace rattaché.

Déploiement typed K3s sur la cible existante, PostgreSQL dédié, portail sur
`/admin/users`, compte sur `/account`, aucune nouvelle ouverture publique.
Versions/digests, bootstrap, preuves et runbooks sont livrés ensemble.
Utilisateurs, domaines et secrets restent hors du harness générique.

La console native Keycloak couvre la gestion des comptes ; pas de second
annuaire artisanal dans Hermes. Les deux runtimes existants servent à qualifier
l'intégration ; la création de nouveaux runtimes et les ACL dynamiques sont des
capacités séparées au backlog. HA et restore identité restent à qualifier.
Voir [la documentation de référence](../guides/portail-webui-entraid.md) et [l'ADR 0018](0018-plan-reparation-sortie-keycloak.md).
