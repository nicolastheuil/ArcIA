# Reprise — sortie HTTPS et accès Microsoft, 13 octobre 2026

> Archive historique. Pour la reprise actuelle, lire [l’état courant](../etat-reprise.md).

## Déployé et vérifié

Sur instruction explicite du propriétaire, Keycloak dispose d'une sortie
IPv4 publique TCP/443. La règle sélectionne uniquement `app=keycloak` dans
`arcia-identity`. Le filtrage des destinations publiques relève du pare-feu
amont ; la disponibilité et les règles de ce pare-feu n'ont pas été auditées.
Les plages privées, locales, réservées, Pod et Service restent exclues de
cette nouvelle règle. Les accès internes précédemment autorisés restent séparés.
Aucun Internet direct supplémentaire n'est accordé aux runtimes Hermes.

L'ancienne règle Microsoft fondée sur quatorze adresses `/32` est retirée
fonctionnellement : `keycloak-microsoft-egress` reste possédée mais sans règle
egress. La migration utilise `replace` avec `resourceVersion`, sans reprise
forcée des champs SSA. Une première exécution avait créé la règle publique
puis rencontré un conflit SSA sur le snapshot ; le code corrigé et sa
réapplication ont terminé le retrait. Aucun restart Keycloak ni changement
de compte, credential ou volume dans cette opération réseau.

Depuis le namespace réseau réel du Pod Keycloak, DNS Microsoft/Graph réussi,
TLS vérifié sur quatre adresses IPv4 issues du DNS courant, compteur REJECT
Keycloak inchangé. TLS vers une autre destination publique réussi ; TCP/80
vers cette même destination refusé. PostgreSQL demeure accessible. IPv6
reste sans route : aucun fonctionnement IPv6 n'est revendiqué.

Le compte Microsoft fédéré constaté possède `ArcIA.User` et un espace a été
attribué. Le rôle effectif `realm-admin` du compte local nommé récupéré a été
relu et confirmé. L'utilisateur avait déjà confirmé une connexion Microsoft
réussie. La recette interactive complète sur son poste et les tests invités/
refus d'un autre tenant restent distincts de ces lectures serveur.

## Configuration reproductible

La configuration privée choisit `identity.https_egress_mode=public_ipv4_443`.
Le harness conserve `disabled` par défaut et n'active jamais cette sortie à
partir d'un simple diagnostic DNS. Le renderer, l'étape bootstrap
`install_identity_public_https_egress`, le schéma, les contrôles et le lock
portent le même contrat. Une réapplication relit les ressources possédées.
Désactiver le flag ne supprime pas silencieusement une règle déjà déployée :
l'Audit signale alors la dérive ; le retrait exige une migration explicite.

La commande `inspect_identity_microsoft_egress` inspecte le mode public sans
résoudre une liste d'IP. Le mode historique `/32` reste disponible pour des
plans ponctuels explicitement approuvés, sans refresh automatique.

## Capacité et nettoyage demandé

Inventaire avant nettoyage : huit places, quatre liées, dont une à un compte
actif, deux à des comptes présents mais désactivés, une à un compte supprimé.
Trois nœuds : 24 CPU allouables, environ 94 Gio mémoire allouable ; demandes
observées 7,1 CPU et 12,39 Gio. Datastore partagé accessible avec au moins
1 Tio libre. Ce relevé ne constitue pas une recette de charge simultanée.

Le propriétaire a demandé de supprimer les anciens espaces des comptes
supprimés, données comprises, puis a accordé une exception Teams limitée à
ce nettoyage. Le plan typé ne retient que les sujets renvoyant HTTP 404 dans
le realm possédé ; un compte désactivé, une erreur 403/500, une place libre ou
une ressource étrangère ne sont jamais des candidats. Un unique espace et
ses deux PVC/PV vSphere sont ciblés. Leur politique initiale `Retain` exige
un passage à `Delete`, borné aux UID et versions exactes du plan. Attendre
les finalizers Kubernetes/CSI ; ne pas les forcer.

Le nettoyage arrête l'allocation du portail, revalide le plan, attend la
suppression du namespace et des PV puis réapplique le pool fixe. Les autres
bindings et UID/volumeName des PVC sont contrôlés. Les anciennes données ne
sont pas transférées à un nouvel utilisateur. Une place recréée est vide,
avec de nouveaux objets Kubernetes. Aucun effacement de sauvegarde ni
écrasement physique sécurisé des blocs n'est revendiqué.

Application exécutée : `PERSONAL_CLEANUP_VERIFIED`, un espace, deux PVC et deux
PV supprimés ; namespace recréé avec une nouvelle identité Kubernetes.
Réapplication du portail réussie, capacité 32, autres bindings et PVC préservés
selon la lecture après installation. Les PV d'origine ont disparu avant
recréation de la place vide. Les comptes désactivés n'ont pas été supprimés.

La cible privée est portée à 32 places pour trente collaborateurs et les
deux bindings désactivés conservés. Les nouvelles places sont dormantes,
les Jobs suspendus et les PVC en WaitForFirstConsumer. Les limites génériques
restent huit par défaut, trente-deux maximum. La charge de trente utilisateurs
simultanés n'a pas été qualifiée.

## Reprise et limites

Les plans, décisions, données d'inventaire et résultats bruts restent sous
DPAPI/ACL. En cas d'échec après suppression, relancer `install_personal_portal`
pour restaurer le pool ; ne pas rejouer un ancien plan destructif. Le nettoyage
n'est jamais une étape automatique Fresh/Reconcile. Audit avec
`-PlanPersonalCleanup` prépare seulement un plan valable dix minutes.

Le bot Teams reste à créer entièrement, comme demandé. Les anciens credentials
protégés ne prouvent pas l'existence d'objets Azure après leur suppression.
L'enrôlement administratif Azure nominatif et la cible de souscription sont
encore nécessaires ; aucune ressource Bot, canal Teams ou app Teams créée ici.
Bootstrap codé et réapplications ciblées sur le cluster existant sont distincts
d'un rebuild VMware neuf, qui n'a pas été exécuté.

Validation locale exécutée : 222 tests Python, 220 réussis et deux ignorés,
contrôles PowerShell du bootstrap et validation des sources réussis. Le test
de refus réseau synthétique utilise désormais une fixture resolv.conf plutôt
que le fichier Linux du poste d'exécution. L'audit accepte l'omission par
l'API Kubernetes d'une liste egress vide et refuse sa réactivation.
[Preuve assainie](../qualification/2026-10-13-identity-public-https.json).
