# Historique de qualification du socle ArcIA

> Historique uniquement ; consulter etat-reprise.md pour le statut courant.

## Historique — arrêt initial du 12 octobre, socle de qualification

Lire en priorité [handoff-2026-10-12-socle-qualification.md](handoff-2026-10-12-socle-qualification.md).
K3s 3/3, CPI/CSI et cinq essais RWOP vérifiés ; PostgreSQL prêt 3/3,
Hermes prêt 1/1. Proxy HTTPS non prêt : correction NGINX codée à appliquer.
91 tests Python passent sous WSL. Arrêt demandé pour quitter le poste.
Archive portable antérieure au lot, à renouveler localement avant transfert.
Les sections ci-dessous sont historiques et ne décrivent plus l'état courant.

## Restauration privée sur le second PC — vérifiée le 12 octobre 2026

L'import de `secrets/local/arcia-private.arciap` a réellement réussi sur le
second PC après saisie locale de la clé de récupération. Code retourné :
`PORTABLE_STATE_RESTORED_FOR_CURRENT_WINDOWS_USER`, 86 fichiers restaurés sous
`%LOCALAPPDATA%\ArcIA-Harness`. Les 44 bundles DPAPI ont tous été déchiffrés et
relus comme JSON par un programme local ne retournant que des compteurs.
Les dix références vers des fichiers privés existent, les deux fichiers SSH
sont présents, aucun accès ACL supplémentaire ni reparse point n'a été relevé
dans l'état restauré ; l'héritage des ACL est bloqué à sa racine.

Le formulaire initial refusait `secrets/local`, marqué ReparsePoint par OneDrive.
L'import a été exécuté avec les scripts existants et une copie chiffrée dans un
staging local hors synchronisation. Aucune référence DPAPI ne pointe vers ce
staging. L'égalité SHA256 de sa copie avec l'archive d'origine a été vérifiée.
L'archive d'origine est conservée et le formulaire terminé a été fermé.
La suppression du staging a été refusée par le contrôle automatique d'exécution,
y compris avec son chemin explicite vérifié. Nettoyage restant :
`%LOCALAPPDATA%\Temp\arcia-import-fc120d82377b4b21a595e7ed01840132`
(copie chiffrée, scripts, petit dépôt Git temporaire et statuts de l'import).

`Initialize-SecondPc.ps1 -IncludeWsl` s'est arrêté avec
`PYTHON_3_14_REQUIRED` : le poste résout Python 3.13.15. La préparation des
dépendances Windows/WSL reste à terminer avant reprise du déploiement.
Aucune connexion aux VM, relance K3s ou action de déploiement n'a été exécutée
pendant cette restauration. Les validations d'infrastructure du handoff restent
historiques ; ce transfert ne qualifie pas un rebuild de cluster ni un second
ingénieur. Ne pas réimporter sur l'état local désormais rempli.

## Arrêt demandé et handoff final

Sauvegarde transportable vérifiée dans secrets/local/arcia-private.arciap,
exclue de Git (86 fichiers / 44 bundles DPAPI / un fichier référencé).
Clé : 1Password personnel, entrée « ArcIA Platform Encryption Key ».
Procédure complète : docs/runbooks/transfert-second-pc.md. Copier ce sous-dossier
avec le projet ; le clone Git seul ne contient pas l'archive privée.

Voir [handoff-2026-10-11.md](handoff-2026-10-11.md), référence prioritaire de reprise.
Le bootstrap K3s a été tenté : premier nœud préparé mais service en échec
(`k3s-server` introuvable dans PATH, cause à diagnostiquer), nœuds 2/3 non installés.
Le service appartenant à l'opération est arrêté/désactivé, sans suppression de données.
Keepalived actif 3/3, zéro VIP attribuée sans API saine. Aucun déploiement planifié.
Choix récents : auth locale, Entra différé, TLS auto-signé. Teams/Passbolt/OpenRouter
enregistrés en DPAPI, non qualifiés. Identités/token/VM/journaux existants à conserver.

## Dernière progression : VIP et bootstrap

Keepalived et arping installés sur les trois VM avec versions/SHA256 fixés.
54/54 flux K3s directionnels vérifiés ; 12/12 contrôles VIP API/HTTPS avant/après
bascule du propriétaire. Propriétaire unique, nopreempt et retrait sans API saine
vérifiés. Listeners temporaires arrêtés ; aucune modification de firewall/VMAC.
Voir ADR 0007 pour le périmètre synthétique, distinct de HA K3s/CSI/production.
83 tests Python passent sous Linux ; les tests de sonde Linux s'exécutent sous WSL.
Le contrôleur Ansible protégé est codé ; K3s n'est pas encore installé à ce point.

Formulaire Configure-Integrations ouvert, sauvegarde partielle DPAPI reçue :
champs Teams et Passbolt présents, non qualifiés. Entra, TLS, OpenRouter et
récupération restent à renseigner/qualifier ; aucune valeur dans ce fichier.
Ne pas redemander les décisions ni les champs déjà enregistrés. Continuer le socle.

Ordre de reprise : Qualify-Preinstallation.ps1 vérifie les preuves privées de
l'opération ; Invoke-ClusterFoundation.ps1 -Action install_k3s exécute le rôle
Ansible existant via le contrôleur WSL protégé. Puis vérifier l'API réelle/VIP,
déployer CPI/CSI et qualifier des volumes synthétiques avant les bases et Hermes.
La certification éditeur vSphere et la recette/rebuild restent des limites explicites.

## Décisions utilisateur

- Publier en privé sur le compte **nicolastheuil**, dépôt **arcia-harness**.
- Les VM étaient à créer ; elles sont maintenant déployées et leur préflight SSH/Linux est vérifié.
- Cible inchangée : trois VM Debian/K3s sur VMware avec stockage partagé.
- Destination précisée : **vCenter / cluster ESXi** ; **image Debian à préparer**.
- Noms : **arcia-k3s-01**, **arcia-k3s-02**, **arcia-k3s-03**.
- L'utilisateur demande l'acceptation locale de l'empreinte du certificat vCenter.

## Inventaire initial vérifié

Le pack contenait seulement AGENTS.md, README.md et trois documents de cadrage.
Pas de dépôt Git ni de code harness. Sources lues intégralement, y compris §25/26.
Windows : Git 2.55.0, OpenSSH 9.5p2, gh 2.102.0, Python 3.14.7.
Identité gh authentifiée : nicolastheuil. Git local initialisé après confirmation,
auteur configuré localement sur cette identité avec adresse GitHub noreply.
Dépôt GitHub créé : https://github.com/nicolastheuil/arcia-harness ; visibilité
privée et permission ADMIN vérifiées avant le premier envoi de code.
kubectl, Helm, Docker, age et SOPS absents du poste au relevé.

WSL Ubuntu disponible, Python 3.14.4. Environnement de validation isolé créé sous
`/home/nicolas/.local/share/arcia-validation` avec ansible-core 2.21.5,
PyYAML 6.0.3, jsonschema 4.26.0. Pas de modification des paquets système WSL.
Sous /mnt/f, Ansible ignore ansible.cfg automatiquement car montage world-writable :
exécuter le déploiement depuis un clone Linux protégé, pas ce montage synchronisé.

## Codé

Wizard DPAPI/ACL, lecteur/rendu local, enregistrement administratif des gates,
CLI doctor/validate/plan/preflight/render, probe Debian, schéma bootstrap et fixture,
playbooks série de bootstrap K3s, socle Kustomize fermé, CI synthétique, ADR,
spécification VMware, backlog et runbooks. Révisions et SHA K3s vérifiés depuis
les sources officielles ; digests applicatifs manquants explicitement null.

## Déploiement VMware vérifié

Les trois VM ont été créées et allumées sur le vCenter désigné. Préflight validé
avec capacité et placement possibles sur trois ESXi ; VMDK officiel contrôlé par
SHA512, import, extension à 150 Gio et ISO NoCloud exécutés. DRS a ensuite regroupé
deux VM ; règle d'anti-affinité et réconciliation ajoutées. Vérification finale :
3 créées, 3 allumées, 3 tools actifs, 3 Debian 13 déclarés, 3 réseaux/hostnames
conformes, 3 ressources 8 vCPU/32 Gio/150 Gio conformes, 3 ports SSH en écoute,
3 ESXi distincts, UUID/MAC uniques et règle d'anti-affinité active. Statut local :
THREE_DEBIAN_VMS_VERIFIED. Aucun K3s/CSI/CPI/PG/ingress/Hermes installé,
aucune entrée publique, aucun accès périmètre. Accès vCenter saisis uniquement dans
le formulaire local et chiffrés DPAPI ; aucune valeur rendue au modèle. Aucun test
de disponibilité, kill switch, IAM, Teams, DLP ou rebuild sur cluster exécuté.
Les services métier et le chiffrement/restore portable restent au backlog.

## Validation SSH et Linux vérifiée

Les trois clés hôte Ed25519 ont été récupérées hors bande par VMware Tools et
l'API vCenter authentifiée, avec challenges distincts liés aux VM de l'opération.
Elles correspondent aux clés relevées avant les redémarrages : clés conservées.
Les connexions SSH strictes avec la clé personnelle et sudo sans interaction ont
réussi. Sur chaque VM : Debian 13 amd64, 8 CPU, mémoire/disque/espace libre,
NTP synchronisé, DNS des sources officielles, cgroups v2, swap absent, TUN pris
en charge, VMware Tools actif et cloud-init terminé. Machine-id et UUID Linux
valides et distincts. Statut local `ssh-preflight-status.json` :
`THREE_LINUX_NODES_PREFLIGHT_PASSED`, 3/3 vérifiées, passed=true.

Le premier rattrapage a redémarré une VM sans obtenir la preuve attendue : le
lecteur CD restait de type client ATAPI. La réconciliation a constaté l'absence
des ISO attendus, puis une nouvelle opération journalisée a utilisé des objets CD
propres, un contrôle de connexion avant reboot et une variable guestinfo précréée.
Cette correction est dans Git. Les trois VM sont revenues ; ressources, réseau,
tools, trois ESXi distincts et anti-affinité revérifiés après l'opération.
Les consoles capturées et l'OCR local n'avaient établi aucune confiance ; aucune
authentification SSH n'a précédé la preuve via vCenter. Aucune valeur privée en Git.

## Reprise

### Dernier lot : fondations réseau et stockage

Inventaire en lecture seule du vCenter désigné : vCenter/ESXi 9.1.1, trois VM
dans le périmètre, datastore vSAN partagé accessible en lecture/écriture aux trois
hôtes, au moins 1 Tio libre au relevé. Dix politiques compatibles selon PBM.
Inventaire complet chiffré dans `foundation-inventory.dpapi`, résumé assaini dans
`foundation-status.json`. Aucun test de provisionnement CSI effectué.

Le formulaire local a enregistré `instance.dpapi` en reprenant dépôt/VM/SSH.
Choix : VIP sur les VM ; FQDN, IP réservées, CIDR et policy restent privés.
L'utilisateur précise que les CIDR entreprise/VPN/périmètres sont encore inconnus
et évolueront. La déclaration d'exhaustivité initiale a été révoquée par
`Set-NetworkInventoryScope.ps1`, sans changer token ni adresses. Tous les gates
restent pending. Ne pas demander une liste exhaustive des futurs VPN pour le
cluster synthétique ; qualifier les routes visibles et bloquer les futurs VPN
jusqu'à implémentation/qualification du contrôle de conflits et du kill switch.

Préflight réseau réellement exécuté via SSH strict, sans mutation : 3/3 pour
routes vers pairs, TCP SSH entre nœuds, MTU sous-jacent >=1500, TLS GitHub et
registry.k8s.io, certificat vCenter conforme à l'empreinte acceptée. Aucun
chevauchement des CIDR choisis avec les routes IPv4 actuellement visibles sur les
VM et le poste Windows, hors routes par défaut. Les deux FQDN ne correspondent
pas aux IP réservées depuis les VM ; l'utilisateur confirme DNS à créer.
Sources confirmées : DNS Windows Server / AD, identité technique SSO local vCenter.
Le compte technique arcia-cpi-csi est créé et son appartenance à l'opération vérifiée.
Le journal `sso-service.dpapi` conserve son secret localement ; ne pas le recréer.
Le client VMware .NET Framework est épinglé (quatre DLL), cache reproductible via
`Initialize-SsoClient.ps1`. Windows PowerShell 5.1 requis pour ce périmètre ; le
validateur SHA256 contrôle lookup/STS/SSO. La longueur du secret est adaptée à la
policy du serveur sans la modifier. Aucune adhésion à un groupe ajoutée par le script.

Quatre rôles créés et dix attributions au compte technique sont désormais vérifiées.
La tentative initiale n'a pas terminé ; une inspection en lecture seule relève
quatre attributions de groupe supplémentaires avec propagation sur la racine.
Elles ne sont pas produites explicitement par notre script, leur origine n'est
pas établie. Elles sont conservées sans modification. Aucun rôle existant n'est
édité : son ensemble exact de privilèges est revérifié avant usage. Le défaut
de grants venait du vmFolder racine d'un datacenter (alias de permission d'une
entité complexe) ; l'attribution manquante est posée sur le datacenter, sans
propagation. Une session du compte technique vérifie les privilèges effectifs :
attendus présents, arrêt/suppression des trois VM et modification de disques sur
une VM extérieure refusés. Statut SCOPED_SERVICE_PRIVILEGES_VERIFIED, dix objets,
un seul grant ajouté à la reprise. CSI reste non qualifié. État détaillé chiffré dans
`service-permissions-inventory.dpapi`, intent et erreurs DPAPI séparés.

Les accès DNS AD ont été saisis et enregistrés dans `dns-access.dpapi`.
Le premier échec était local : paramètres incompatibles de New-CimSessionOption.
Correction testée. Le nouvel essai en lecture seule échoue à New-CimSession avec
DCOM E_ACCESS_DENIED 0x80070005, avant lecture des zones et avant toute écriture.
Ne pas conclure à un mauvais mot de passe. Code sûr : DNS_DCOM_ACCESS_DENIED.
Un package `dns-local-*`, propriétaire seul, contient plan privé et deux scripts,
sans credentials ; exécution possible sur le serveur DNS désigné avec l'identité
AD de l'ingénieur. Aucune modification de TrustedHosts, firewall, UAC ou droits AD.
L'utilisateur n'a pas vu l'Explorateur ; une fenêtre dédiée `Show-LocalDnsPackage.ps1`
affiche le chemin physique MSIX et les commandes. L'utilisateur confirme ensuite
la création des DNS. Les requêtes directes au serveur retournent les deux IP
réservées. Les résolveurs systemd des VM gardaient la réponse négative précédente :
`Inspect-Foundation.ps1 -Network -FlushDnsCache` purge uniquement leurs caches.
La résolution des deux endpoints est maintenant vérifiée sur 3/3 VM.

CPI v1.35.1 commit 59582fbcc054eb42106d7d31ab543ae8e3333e67, CSI v3.7.3
commit 27ec91d0a0fc820724cc5d7a0a2f69d12bc4ff34 : quatre manifests amont
conservés avec licences, seules les neuf références d'images remplacées par leurs
digests OCI. SHA256 amont/rendus et digests dans le lock ; validation CI ajoutée.
Ce sont des sources préparées, pas un overlay qualifié/installé. La matrice
Broadcom détaillée a renvoyé HTTP403 ; ne pas prétendre à une certification
documentaire vSphere 9.1.1. Le problème public CSI #4236 concerne un mélange
vCenter9.1/ESXi9.0 ; les trois hôtes relevés ici sont9.1.1, sans preuve suffisante
pour lever la qualification CSI.

78 tests Python locaux passent. Tests Windows DNS (création/replay/conflits/cible/
provider simulés), DCOM options et secret SSO/TLS passent. Syntaxe PowerShell, hash des manifests/images,
schema/YAML, syntaxe Ansible et gate synthétique vérifiés. Les ports etcd/VXLAN,
la bascule VIP/API/HTTPS, CPI/CSI et K3s restent non déployés/non qualifiés.

1. Consulter docs/verification-preparation.md et l'état CI du dépôt.
2. Lire les statuts sûrs locaux VMware et SSH ; les clés hôte, machine-id et NTP
   sont vérifiés. Répéter au besoin `Test-NodeAccess.ps1 -ValidateOnly`, sans mutation.
3. Qualifier réseau, endpoint API/HTTPS avec bascule et CIDR, puis CPI/CSI.
4. La configuration locale existe : ne pas la recréer ni régénérer son token.
   Utiliser `Inspect-Foundation.ps1 -Network` pour les contrôles en lecture seule.
   Afficher `Show-FoundationRequirements.ps1` pour les records DNS et le plan de
   droits, uniquement sur le poste local. Ne pas redemander les sources d'identité.
   DNS confirmé et vérifié sur les trois VM ; ne pas redemander sa création.
   Inspecter les rôles via `Inspect-Foundation.ps1 -ServicePermissions -ReadOnly` ;
   `-VerifyOnly` vérifie les grants sans mutation. Les rôles existants restent
   intacts, les grants du compte technique sont vérifiés ; poursuivre les volumes CSI.
5. Qualifier CPI/CSI et leurs images, fixer les digests et preuves ; enregistrer
   les gates via programme protégé, sans modifier un résultat non observé.
6. Déployer le bootstrap en mode synthétique après revue, puis exécuter les lots 0+.
7. Recette et rebuild sur cluster neuf avant toute déclaration de release.

Ne pas redemander le compte, le nom du dépôt, sa visibilité ou le choix K3s.

## Vérification de ce lot

62 tests Python synthétiques passés sous Linux, dont TLS réel local (certificat
accepté, changement bloqué avant authentification), intégrité du cache image,
ISO NoCloud relu, refus d'une règle DRS étrangère. DPAPI roundtrip, réouverture
du dossier privé, remplacement atomique, refus d'écrasement et ACL vérifiés sous
PowerShell. Syntaxe de tous les scripts contrôlée. Ansible/schema/YAML/gate
synthétique revérifiés : aucune tentative SSH par ce test.

Défauts corrigés : réouverture ACL sans privilège SACL, remplacement .NET avec
NullString plutôt que chaîne vide, diagnostics de connexion distincts, empreinte
vérifiée sur chaque socket, saisie de cible avec brouillon chiffré/retour explicite.
Les références de clés créées dans secrets/ ont été déplacées hors OneDrive/Git.
Le lot SSH ajoute des tests de refus avant authentification sans preuve, de
challenge périmé, de clé changée/dupliquée, de fuite d'erreur, de préflight assaini
et de seed conservant les clés sans installation de paquets. Le préflight réel
a également été répété avec succès après les dernières corrections de sonde.
