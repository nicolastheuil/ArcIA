# ADR 0017 — Espace personnel à la première connexion

Décision du 13 octobre 2026, suite au remplacement des comptes synthétiques
par des comptes administrés dans Keycloak.

## Problème

L'identification réussissait, mais les deux runtimes historiques n'acceptaient
que leurs propriétaires synthétiques. Supprimer ces comptes puis recréer des
comptes ne transfère pas leurs UUID. Le message générique `ARCIA_LOGIN_REFUSED`
masquait un refus légitime de propriété. Un portail d'annuaire seul ne suffit
pas à rendre un nouvel utilisateur opérationnel.

## Décision

Le domaine principal ouvre `/portal/`. Ce point d'entrée utilise un client OIDC
public PKCE distinct, vérifie signature/issuer/audience, state/nonce, session
en ligne et rôle `ArcIA.User`. À la première connexion, une requête de même
origine protégée contre CSRF attribue un emplacement personnel vide à la clé
`(issuer, sub)`. Le login, l'email et le nom ne déterminent jamais la propriété.

Le bootstrap prépare un pool borné de namespaces, manifests, clients OIDC,
Secrets applicatifs et Jobs d'installation suspendus. Le contrôleur ne crée ni
namespace ni PodSpec : ses Roles limités à ces namespaces lui permettent de
lier le subject, reprendre le Job fixé et utiliser `deployments/scale` pour
deux noms précis. Les agents n'ont aucun jeton Kubernetes. Le contrôleur n'a
aucun accès administrateur Keycloak, coffre, fournisseur cloud ou cluster.

Chaque emplacement possède son état et ses outils RWOP, son client public,
son subject et ses tokens de connaissance/privacy. Les scopes documentaires
sont personnels, sans héritage des corpus de qualification. Le routage privé
et les contrôles du provider restent actifs même si l'URL d'un autre espace
est connue. Les appels modèles conservent le filtre et la politique gratuite
de qualification ; aucune ouverture de données réelles n'est déduite du login.

## Conséquences

L'allocation est idempotente et conservée en ConfigMap contrôlée ; elle utilise
une version de ressource et un contrôleur actif unique. Une réapplication
conserve les bindings, credentials, volumes et états d'installation. La capacité
par défaut est huit emplacements, extensible à 32 dans la configuration
protégée après dimensionnement. Une capacité atteinte produit un refus explicite.

Un compte supprimé conserve son emplacement réservé et ses volumes. Une
nouvelle identité reçoit un espace distinct. Transfert, purge, récupération
de capacité, sauvegarde/restauration et upgrade des outils d'un espace actif
exigent des opérations administratives séparées ; aucun recyclage automatique.
La première installation peut prendre plusieurs minutes. La haute disponibilité
du contrôleur et le rebuild neuf ne sont pas qualifiés.

Les deux anciens espaces ne deviennent pas des espaces partagés. Leurs tests
de qualification restent historiques et réservés au profil Fresh ; la recette
du portail personnel couvre le parcours courant après administration du realm.
