# ADR 0023 — Entra ID direct et un seul administrateur local

Date : 14 octobre 2026. Statut : cible acceptée ; test préalable à la bascule.

## Contexte et décision

Le propriétaire privilégie les capacités natives Hermes. Il demande Entra ID
directement pour les utilisateurs et un seul compte local `admin`, sans annuaire
local général. L'instance n'est pas en production ; la suppression de Keycloak
et de ses comptes de test est autorisée, **après configuration de Hermes et test
de connexion effectué par le propriétaire**. Cette instruction remplace le
maintien permanent de comptes locaux et du broker décrit dans
[ADR 0020](0020-perimetre-harness-et-politiques-instance.md).

La première étape est un runtime isolé `/entra-test`, utilisant le provider OIDC
natif Hermes, avec garde `(tenant, object ID)` du compte explicitement enrôlé.
Son unique compte local est `admin`, via le provider mot de passe natif.
Keycloak et les autres runtimes restent en place pendant cette recette.
Le test d'authentification n'active ni modèle, ni fournisseur personnel.

## Conséquences

Le code source verrouillé du provider self-hosted supporte un client Web
confidentiel avec PKCE et secret applicatif. Cette capacité est vérifiée dans
le code ; la page documentaire qui annonce seulement un client public est
incomplète sur ce point.
[Source verrouillée](https://github.com/NousResearch/hermes-agent/blob/818c13be1dc4fd28987e1e881a9408224afd4535/plugins/dashboard_auth/self_hosted/__init__.py).

Tenant, client, secret et propriétaire passent par le programme protégé local.
Le canary ne peut atteindre que le relais TLS d'authentification, lui-même
limité à `login.microsoftonline.com:443`. Il n'a pas de sortie d'inférence.
Cette restriction évite de faire de la nouvelle sortie OIDC un contournement
de Presidio. Les adaptateurs OAuth et la vérification JWT restent natifs.

La généralisation exige ensuite le provisioning Entra des utilisateurs et la
gestion des rôles d'entreprise. `ArcIA.ProviderSelfService` reste un droit
explicite, sans attribution automatique et sans équivalence avec admin.
La suppression des ressources Keycloak n'est ni un effet de Fresh/Reconcile
ni une conséquence automatique de l'enrôlement des paramètres du test.

La [procédure](../runbooks/entra-hermes-test.md) et
l'[état de reprise](../etat-reprise.md) distinguent code, déploiement,
vérification technique et validation humaine du login.
