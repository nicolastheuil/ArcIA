# Handoff — réparation réseau de l'authentification Microsoft

13 octobre 2026. Suite du [diagnostic](handoff-2026-10-13-m365-auth-diagnostic.md).

## Autorisation et périmètre

Le propriétaire demande d'appliquer les corrections et de rétablir
l'authentification. Après présentation du plan et des limites, il autorise
explicitement l'exception Teams « pour ce correctif uniquement ». Cette
exception administrative est enregistrée comme telle, sans prétendre à une
approbation Teams côté serveur ni modifier AGENTS.md.

## Codé et déployé

`scripts/identity_egress.py` construit une règle additive réservée à Keycloak,
TCP/443 et adresses IPv4 publiques `/32` de Microsoft login/Graph. Le plan
est lié à l'opération, au Deployment UID/resourceVersion, à la règle
antérieure, au document et à un hash, avec validité dix minutes. La collecte
croise des résolutions répétées sur les trois nœuds ; aucune IP privée,
IPv6, plage CIDR ou destination supplémentaire n'est acceptée.

L'action de réparation exige le hash du plan autorisé, vérifie la cible,
les réponses DNS actuelles et la propriété, puis utilise create/replace
avec préconditions. La règle `keycloak-microsoft-egress` contient 14 `/32`.
La relecture est conforme et une seconde application a conservé son UID.
Pas de rollout, changement de compte, permission Entra, secret ou volume.

Bootstrap : commande de plan opt-in, inspection réseau dans Audit, lock
d'identité et couverture actualisés. Aucune réparation automatique dans
Fresh/Reconcile/Verify/Audit. La réapplication standard ne supprime pas
cette règle additive. Le renderer local reste fermé à Internet par défaut.

## Vérifié sur la cible

Les réponses A actuelles du DNS du Pod permettent quatre connexions
TCP/TLS validées vers Microsoft/Graph ; compteur REJECT inchangé pendant
ces essais. DNS A/AAAA 4/4 et PostgreSQL restent accessibles. Une destination
hors liste (`example.com:443`) est refusée. L'inspection de la règle vérifie
ses bornes et la couverture DNS actuelle. Aucune route IPv6 n'a été ajoutée.

Un premier rejeu des anciennes adresses du diagnostic a réussi pour Graph
mais a refusé deux IP de login. Le test final utilise les réponses DNS
actuelles du Pod et réussit 4/4 ; les anciens résultats restent dans les
preuves protégées. Cela illustre la limite des snapshots IP : une rotation
DNS peut nécessiter un nouveau plan, pas un élargissement silencieux.

[Preuves assainies](qualification/2026-10-13-m365-egress-repair.json).
Plans, états antérieurs, relectures et sondes détaillées restent DPAPI hors
dépôt : `cluster-plan_identity_microsoft_egress.dpapi`,
`cluster-apply_identity_microsoft_egress_repair.dpapi`,
`m365-routing-pod-after-repair.dpapi`,
`m365-routing-pod-currentdns-after-repair.dpapi`,
`m365-repair-negative.dpapi`.

## Reprise et limites

Validation locale exécutée : 27 tests identité/provider/réparation et 5 tests
bootstrap réussis ; contrôle Bootstrap PowerShell et validate_sources réussis.
Les 13 tests de réparation couvrent notamment les IP interdites, les snapshots
multi-nœuds, les plans altérés/expirés, les ressources étrangères, la dérive
DNS et l'absence de mutation sans exception explicite. Couverture du bootstrap
et hashes d'identité vérifiés. La suite Windows générale n'a pas été relancée
et aucune CI distante de ce lot n'est revendiquée.

La connexion Microsoft complète nécessite le login/MFA de l'utilisateur
dans son navigateur. Le réseau réparé ne prouve ni la validité du credential
Entra, ni la liaison des comptes, ni l'accès au runtime. L'essai utilisateur
est demandé et son résultat reste attendu. Aucune authentification complète,
recette SSO, réapplication complète ou reconstruction neuve déclarée.

Le filtrage IP ne garantit pas un hostname exclusif ; TLS valide le nom.
La règle Kubernetes ne s'expire pas à l'expiration du plan. Audit détecte
les IP manquantes, sans refresh automatique. Une sortie durable avec
contrôle de noms et gestion des changements DNS reste à qualifier ; voir
[ADR 0018](adr/0018-plan-reparation-sortie-keycloak.md).
