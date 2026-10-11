# ADR 0007 — VIP et périmètre des gates de bootstrap

Date : 2026-10-11. Statut : VIP installée et transport qualifié, K3s à installer.

Keepalived 1:2.3.3-1 et iputils-arping 3:20240905-3 sont fixés avec SHA256
dans versions.lock.yaml ; téléchargement depuis le snapshot Debian signé des VM.
Le mode unicast utilise les interfaces/MAC existantes, sans VMAC, changement
de sécurité VMware ou modification du pare-feu. Trois priorités, état BACKUP,
nopreempt et contrôle de santé à échec initial évitent de publier une API absente.
Un journal DPAPI réserve l'identité VRRP avant mutation. Une configuration étrangère,
un changement manuel, une adresse déjà utilisée ou un VRID visible provoquent un refus.

Qualification exécutée : 54/54 contrôles directionnels des ports K3s ; 12/12
contrôles des deux VIP/ports depuis les trois VM avant/après arrêt du keepalived
propriétaire. Un seul propriétaire observé, bascule vers un autre nœud, absence
de préemption au retour, retrait des VIP après fin de la santé synthétique.
Tous les listeners temporaires sont arrêtés. Aucun test de panne VM, etcd ou
API K3s réelle n'est encore couvert par cette preuve.

Les quatre gates historiques de scripts/harness.py autorisent seulement le
bootstrap de qualification synthétique. Leurs preuves sont explicitement marquées
preinstallation_synthetic_only ; leurs noms ne constituent ni certification éditeur
ni acceptation de production. Le gate VMware couvre ici l'inventaire/API, le datastore
partagé, PBM et les privilèges effectifs ; le gate CPI couvre les sources/digests,
le compte technique et le design externe aligné sur Kubernetes 1.35. Le guide impose
ensuite la qualification réelle CPI/CSI sur le cluster, impossible avant son existence.
La certification documentaire vSphere 9.1.1 reste non vérifiée (documentation Broadcom
HTTP403). Tout échec indispensable CSI bloque les workloads persistants ; aucun
repli silencieux sur local-path. Aucune déclaration HA/release avant recette complète.

Le contrôleur Ansible s'exécute sous WSL avec copie temporaire de la même identité
SSH personnelle dans un dossier ext4 0700, fichiers 0600, afin de satisfaire OpenSSH.
L'identité n'est pas partagée, affichée ou conservée dans le dépôt. Inventaire et sorties
privées passent par stdin/stdout capturés et DPAPI ; le dossier temporaire est supprimé
à la fin. La configuration Ansible explicite évite l'ignorance du fichier sur le montage
Windows accessible en écriture. Une interruption du contrôleur exige revue de ses fichiers
temporaires par l'ingénieur ; les journaux d'appartenance sur les VM permettent la reprise.

Sources : [manuel Keepalived 2.3.3](https://github.com/acassen/keepalived/blob/v2.3.3/doc/man/man5/keepalived.conf.5.in),
[paquet Debian trixie](https://packages.debian.org/trixie/keepalived),
[matrice CPI 1.35.1](https://github.com/kubernetes/cloud-provider-vsphere/blob/v1.35.1/README.md),
[guide local](../installation-k3s-codex.md).
