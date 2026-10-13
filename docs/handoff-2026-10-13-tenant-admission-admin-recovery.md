# Handoff — récupération admin et admission automatique du tenant

13 octobre 2026. Travail préparé ; **aucun droit modifié dans ce lot**.

## Demandes à conserver

Le propriétaire confirme que la connexion Microsoft fonctionne sur son second
PC ; sur le premier, « OAuth state mismatch (CSRF check failed) » appelle un
nouveau parcours depuis l'accueil, sans désactiver CSRF. Il demande ensuite
un bot Teams complet, précise avoir supprimé les anciens objets et vouloir
tout recréer, puis signale avoir supprimé l'administrateur Keycloak initial.
Enfin, il demande un accès ArcIA automatique pour tous les utilisateurs du
tenant, sans habilitation administrative par utilisateur.

Priorité actuelle : récupérer l'admin existant et préparer l'admission
automatique ; conserver la demande Teams après cette réparation. Aucun bot,
credential Azure, consentement, canal ou app Teams créé dans cette session.
Les anciens credentials du bot présents sous DPAPI ne doivent pas être pris
pour des ressources encore valides après la déclaration de suppression.

## Inspection exécutée et correction préparée

Le compte technique Keycloak protégé authentifie et peut lire le realm possédé.
Le nouveau compte nommé par le propriétaire existe, est actif et n'est pas un
service account. Il a `ArcIA.Admin`, mais pas le rôle effectif
`realm-management.realm-admin`. Le compte initial a disparu. Les identités
réelles/UUID sont dans les plans protégés, pas dans Git.

Un seul fournisseur Microsoft activé est configuré pour un tenant UUID précis.
Aucun mapper ne lui attribue actuellement `ArcIA.User`. Le pool personnel
contient huit places, dont trois attribuées : cinq places libres constatées.
La population à accueillir a été demandée ; réponse attendue. Aucun ancien
binding ou volume ne doit être recyclé pour augmenter cette capacité.

`scripts/identity_access.py` prépare deux changements typés : attribuer le
rôle existant `realm-admin` au seul compte existant sélectionné par UUID ;
créer le mapper `arcia-tenant-users`, `oidc-hardcoded-role-idp-mapper`,
`ArcIA.User`, syncMode FORCE, sur le seul fournisseur Microsoft/tenant attendu.
Pas de reset password/MFA, création d'utilisateur, modification des rôles par
défaut du realm, d'ouverture d'inscription locale ou de fusion par email.
Un éventuel client `ArcIA` est refusé pour éviter la résolution ambiguë du
nom de rôle contenant un point dans Keycloak.

Plan et apply sont séparés ; hash, opération, realm, UUID du compte, alias,
tenant et validité de dix minutes sont contrôlés. Une seconde application est
idempotente. Les ressources étrangères, compte désactivé/service account,
autre tenant, collision de mapper privilégié et dérive d'identité sont refusés.
L'inspection Audit détecte la dérive du mapper sans réattribuer de droits.
Le bootstrap et ses locks décrivent cette capacité ; aucune élévation ne fait
partie du parcours automatique. Les décisions administratives restent préservées.

## Autorisation manquante et suite

AGENTS.md exige « Toute action externe à risque a son plan et son approbation
Teams vérifiés côté serveur ». Le canal de vérification n'est pas livré.
L'exception humaine précédente portait sur la réparation réseau Microsoft,
pas sur cette nouvelle élévation d'identité. Une nouvelle exception limitée
aux deux corrections a été demandée, avec leur périmètre concret et les tests.
**Réponse attendue ; ne pas appliquer avant autorisation.**

Le plan courant est dans `cluster-plan_identity_access_repair.dpapi` ; son hash
et son état sont dans le statut assaini correspondant. Les inspections
initiales restent dans `identity-admin-recovery-plan.dpapi` et
`identity-tenant-access-plan.dpapi`. Un plan expiré impose une nouvelle
préparation, jamais la suppression de ses contrôles. Après application
autorisée, `identity-access-policy.dpapi` conservera les références d'admission.

Ensuite, vérifier la console avec le compte récupéré, un premier login d'un
utilisateur du tenant sans rôle attribué manuellement, les refus croisés et
la capacité. Une restriction d'affectation obligatoire dans l'application
Entra peut aussi demander une configuration initiale côté tenant ; le mapper
Keycloak ne la supprime pas. Les invités n'ont pas encore de recette distincte.

## Réseau et Teams à reprendre

Une inspection postérieure a observé cinq IP DNS Microsoft absentes de la
règle `/32` appliquée lors du lot précédent. Aucun élargissement n'a été fait
ici. La connexion déclarée réussie par l'utilisateur ne qualifie pas la
stabilité des snapshots IP. Conserver l'alerte et prévoir une sortie durable
adaptée aux changements DNS, sans Internet arbitraire pour Hermes.

L'état protégé contient un hostname bot distinct du portail et d'anciens
client ID/credential ; le tenant n'est pas rempli dans l'ancien formulaire.
Aucun Azure CLI ou module Graph/Azure/Teams n'a été trouvé sur ce poste.
Il faut réenrôler une identité administrative nominative, la souscription et
la cible Azure par programme protégé avant de créer les objets Teams.
Le SDK Agents Python officiel 1.8.0 et l'adaptateur Teams natif de la révision
Hermes sont des candidats à examiner ; aucun SDK installé/intégré ici.

Sources primaires consultées :
[mapper Keycloak 26.8.1](https://github.com/keycloak/keycloak/blob/26.8.1/services/src/main/java/org/keycloak/broker/provider/HardcodedRoleMapper.java),
[résolution des rôles](https://github.com/keycloak/keycloak/blob/26.8.1/server-spi-private/src/main/java/org/keycloak/models/utils/KeycloakModelUtils.java),
[sécurité Agents SDK](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/secure-your-agent),
[release Agents Python](https://github.com/microsoft/Agents-for-python/releases/tag/v1.8.0).
