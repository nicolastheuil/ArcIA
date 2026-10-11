# État de reprise — 11 octobre 2026

## Décisions utilisateur

- Publier en privé sur le compte **nicolastheuil**, dépôt **arcia-harness**.
- Les VM sont **à créer** ; aucune cible SSH n'a été fournie ou contactée.
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
THREE_DEBIAN_VMS_VERIFIED. Aucun SSH authentifié, aucun K3s/CSI/CPI/PG/ingress/Hermes installé,
aucune entrée publique, aucun accès client. Accès vCenter saisis uniquement dans
le formulaire local et chiffrés DPAPI ; aucune valeur rendue au modèle. Aucun test
de disponibilité, kill switch, IAM, Teams, DLP ou rebuild sur cluster exécuté.
Les services métier et le chiffrement/restore portable restent au backlog.

## Reprise

1. Consulter docs/verification-preparation.md et l'état CI du dépôt.
2. Lire uniquement les statuts sûrs locaux VMware ; contrôler les clés hôte SSH
   hors bande et machine-id/NTP Linux, sans relancer la création ni adopter/supprimer.
3. Inventorier localement VMware, empreintes SSH, réseau et endpoints avec bascule.
4. Utiliser scripts/Configure-Local.ps1 dans un terminal de confiance.
5. Qualifier CPI/CSI et leurs images, fixer les digests et preuves ; enregistrer
   les gates via programme protégé, sans modifier un résultat non observé.
6. Déployer le bootstrap en mode synthétique après revue, puis exécuter les lots 0+.
7. Recette et rebuild sur cluster neuf avant toute déclaration de release.

Ne pas redemander le compte, le nom du dépôt, sa visibilité ou le choix K3s.

## Vérification de ce lot

48 tests Python synthétiques passés sous Linux, dont TLS réel local (certificat
accepté, changement bloqué avant authentification), intégrité du cache image,
ISO NoCloud relu, refus d'une règle DRS étrangère. DPAPI roundtrip, réouverture
du dossier privé, remplacement atomique, refus d'écrasement et ACL vérifiés sous
PowerShell. Syntaxe de tous les scripts contrôlée. Ansible/schema/YAML/gate
synthétique revérifiés : aucune tentative SSH par ce test.

Défauts corrigés : réouverture ACL sans privilège SACL, remplacement .NET avec
NullString plutôt que chaîne vide, diagnostics de connexion distincts, empreinte
vérifiée sur chaque socket, saisie de cible avec brouillon chiffré/retour explicite.
Les références de clés créées dans secrets/ ont été déplacées hors OneDrive/Git.
