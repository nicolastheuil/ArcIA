# ADR 0004 — Connexion vCenter privée et disque Debian

Date : 2026-10-11. Statut : retenu ; trois VM créées, allumées et vérifiées via VMware.

## Décisions confirmées

L'utilisateur désigne vCenter / cluster ESXi et demande de préparer l'image
Debian. Les VM se nomment arcia-k3s-01, arcia-k3s-02 et arcia-k3s-03.
Il demande une acceptation locale de l'empreinte du certificat plutôt que de
fournir une CA PEM. Ces décisions ne sont pas à redemander.

## Connexion

SDK officiel pyvmomi 9.1.1.0, wheel verrouillée par SHA256. Formulaire Windows :
identité personnelle, mot de passe et destination ne transitent ni en arguments
de processus ni dans les sorties du modèle. Connexion et inventaire sont chiffrés
DPAPI CurrentUser, ACL limitée au compte courant, hors Git/OneDrive.

La vérification CA reste le mode par défaut. Le mode demandé par l'utilisateur
affiche localement le SHA256 du certificat récupéré sans authentification. Une
acceptation explicite dans cette fenêtre épingle ce certificat pour cette cible.
Chaque nouvelle socket TLS vérifie ce pin avant toute requête HTTP/identifiant,
y compris lorsque le contexte TLS est réutilisé. Un changement bloque la connexion.
Un changement de serveur ou de port dans le formulaire invalide le pin en mémoire.
L'empreinte se compare à une source de confiance lors de la première acceptation.

Ne pas utiliser simplement le fallback thumbprint du SDK : dans cette version,
la mutation du contexte après un premier échec CA peut empêcher la vérification
du pin sur une connexion ultérieure. Le contexte du harness vérifie chaque socket.
Les tests TLS synthétiques locaux couvrent l'acceptation et le remplacement du
certificat avant l'envoi d'un canary d'authentification.

Seuls des codes fixes et comptes d'objets peuvent être rendus au modèle. Aucune
trace VMware brute, aucun nom d'inventaire et aucun contenu DPAPI déchiffré.

## Image

Source Debian officielle generic amd64 20261001-2618, SHA512 tiré de SHA512SUMS
en HTTPS, kernel standard pour VMware. QCOW2 converti en VMDK streamOptimized
avec qemu-img 10.2.1 ; source et sortie contrôlées, receipt locale, aucun écrasement
d'une sortie non attestée. Le cache binaire reste hors du dépôt.

La source contient cloud-init 25.1.4-1+deb13u1 et OpenSSH, mais **pas open-vm-tools**.
Le VMDK obtenu n'est donc pas un template qualifié prêt à cloner. Il reste à
préparer un bootstrap NoCloud local, installer open-vm-tools épinglé, configurer
les paramètres réseau privés, importer et vérifier le boot sur le vCenter choisi.
Ne pas utiliser guestinfo comme seul bootstrap avant installation des tools.

Le choix cluster/datastore/réseau/dossier, les adresses privées et l'identité SSH
ont été saisis localement après inventaire. Trois import specs et la capacité sur
trois hôtes ont été validés avant création. L'import, l'ISO NoCloud, l'extension
des disques et l'allumage ont été exécutés. Le profil invité vCenter disponible
est une métadonnée de matériel ; le disque reste Debian 13, sans certification
de la combinaison à ce stade. Aucun K3s, CSI ou service métier n'est installé.

DRS a regroupé deux VM après le placement initial. Une règle d'anti-affinité
optionnelle limitée aux VM de cette opération et une réconciliation de placement
sont donc codées. Les règles homonymes avec d'autres VM sont refusées. La règle
reste optionnelle pour permettre le redémarrage HA lorsque moins d'hôtes sont
disponibles. La séparation réelle sur trois hôtes, le réseau attendu, les tools,
Debian 13 déclaré par les guests, les ressources et UUID/MAC distincts ont été
contrôlés. Les empreintes SSH/machine-id et la recette K3s/HA restent distinctes.

Sources : [SDK](https://github.com/vmware/pyvmomi),
[image et checksums](https://cloud.debian.org/images/cloud/trixie/20261001-2618/),
[datasource VMware](https://docs.cloud-init.io/en/latest/reference/datasources/vmware.html),
[paquet Debian open-vm-tools](https://packages.debian.org/trixie/open-vm-tools).
