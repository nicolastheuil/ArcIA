# ADR 0006 — Réseaux évolutifs et qualification des fondations

Date : 2026-10-11. Statut : décisions enregistrées, sondes exécutées ; K3s non installé.

Les CIDR entreprise/VPN/périmètres ne sont pas tous connus et évolueront. Une saisie
initiale ne peut donc pas constituer une preuve d'absence perpétuelle de conflit.
Le bootstrap synthétique compare les CIDR choisis aux réseaux des VM, aux CIDR
explicitement connus et aux routes actuellement visibles sur les VM et le poste.
Les routes par défaut ne représentent pas un inventaire de tous les réseaux.
La preuve est datée et limitée à cette visibilité. Le gate réseau reste pending
jusqu'à revue des résultats, flux K3s et mécanisme d'endpoint.

Les futurs VPN restent désactivés. Leur admission exigera un contrôle serveur
des routes déclarées puis réellement installées à chaque connexion/reconnexion,
une politique de traitement des conflits avec les réseaux protégés, l'isolation
du tunnel et un kill switch. Ce contrôle métier n'est pas encore implémenté.
Un namespace seul ne prouve pas cette protection. Une modification des CIDR du
cluster déjà installé exige une migration dédiée ; ne pas les modifier pour chaque VPN.

La VIP sur les VM est le mécanisme saisi localement. Aucune VIP, aucun DNS et
aucun répartiteur n'ont été créés par ce lot. Les DNS Windows AD sont créés par
l'ingénieur après refus DCOM 0x80070005 ; les deux résolutions exactes sont vérifiées
sur les trois VM après purge des caches négatifs. Le compte technique est créé dans le SSO
local avec journal d'appartenance à l'opération, mot de passe aléatoire conforme
à la policy relevée et validation TLS SHA256 sur chaque endpoint du client SSO.
Les rôles existants ne sont jamais édités, leurs privilèges exacts sont vérifiés ;
les attributions de groupes autres que le compte technique restent intactes.
Les permissions du vmFolder racine d'un datacenter sont appliquées sur le datacenter
(entité complexe), sans propagation. Droits effectifs positifs/négatifs vérifiés sur
dix objets via une session technique ; CSI reste à qualifier. La connexion personnelle sert à
l'inventaire et au provisioning autorisés ; ses credentials ne seront pas
installés dans Kubernetes. Les droits proposés sont limités aux volumes bloc et
objets désignés ; revoir les exigences éditeur, tester droits effectifs, opérations
sur volume synthétique et refus hors périmètre avant qualification.

La présence de dix policies PBM compatibles et d'au moins 1 Tio libre sur vSAN
n'est pas une preuve de persistance, de fencing ou de HA. CPI/CSI sont des sources
épinglées avec licences et hashes ; aucune installation n'est déclenchée par leur
résolution. Les gates de compatibilité et CPI restent pending.
