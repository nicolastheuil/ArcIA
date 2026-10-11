# ADR 0005 — Vérifier SSH depuis le canal VMware approuvé

Date : 2026-10-11. Statut : implémenté et vérifié sur les trois VM.

La collecte réseau d'une clé par ssh-keyscan ne prouve pas l'identité du serveur.
Le vCenter est déjà authentifié avec son certificat accepté et vérifié sur chaque
socket. Le bootstrap publie donc uniquement la clé **publique** Ed25519 du serveur
dans `guestinfo.arcia.ssh-key-proof`, accompagnée d'un challenge propre à cette VM.
Le lecteur résout les trois VM par nom et annotation de l'opération, contrôle leur
réseau, puis récupère cette preuve via l'API vCenter. Il n'envoie aucune clé privée
ou information d'authentification dans guestinfo.

Pour les trois VM créées avant cet ajout, une mise à jour NoCloud conserve les
clés hôte et le compte personnel ; elle ne réinstalle aucun paquet, ne redimensionne
aucun disque et n'installe pas K3s. Un redémarrage invité est effectué successivement
sur ces seules VM neuves. Le challenge et l'intention sont enregistrés en DPAPI
avant l'appel ; une relance du programme réconcilie en lecture seule, sans rejouer
un redémarrage dont l'état serait incertain. Ce mode de rattrapage est réservé au
bootstrap de VM vierges, jamais à un nœud Kubernetes déjà enrôlé.

Une variable guestinfo est précréée côté vCenter pour recevoir la preuve. Le
changement de média utilise un objet CD propre et contrôle le backing ISO et sa
connexion avant de redémarrer. La première tentative sans ces contrôles n'avait
pas fourni de preuve ; une réconciliation explicite du lecteur client ATAPI a
précédé la correction. Les clés observées avant/après sont identiques sur les
trois VM. Le préflight SSH/Linux a ensuite réussi sur chacune.

La console vCenter peut aussi fournir la preuve si une empreinte ou clé publique
exacte y est lisible. L'OCR Windows travaille uniquement en mémoire locale et
n'accepte aucune substitution de caractère. Les consoles actuelles n'affichent
plus les empreintes du premier boot ; cette voie n'a établi aucune confiance.

Le client ssh-keyscan Windows 9.5 propose un KEX non pris en charge par son propre
binaire sur ce poste. Le scanner OpenSSH fourni par Git est utilisé s'il existe.
Le défaut est documenté par le [projet Win32-OpenSSH](https://github.com/PowerShell/Win32-OpenSSH/issues/2140).
Aucun réglage du serveur SSH n'est abaissé pour le contourner.

Après validation hors bande, les connexions utilisent StrictHostKeyChecking=yes,
un known_hosts dédié, Ed25519, le compte et la clé personnels, sans mot de passe,
agent SSH ou configuration implicite. Les résultats détaillés restent locaux et
chiffrés ; seules des vérifications booléennes et des erreurs fixes sont publiées.
La confiance est limitée à la confiance déjà accordée au vCenter et à son contrôle
des VM ; elle n'est pas une attestation matérielle du système invité.

Sources : [OpenSSH keyscan](https://man.openbsd.org/ssh-keyscan.1),
[cloud-init SSH](https://cloudinit.readthedocs.io/en/latest/topics/modules.html#ssh),
[GuestInfo VMware](https://knowledge.broadcom.com/external/article/377294/accessing-or-modifying-a-guestinfo-vari.html).
