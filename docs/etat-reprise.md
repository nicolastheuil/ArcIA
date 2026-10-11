# État de reprise — 11 octobre 2026

## Décisions utilisateur

- Publier en privé sur le compte **nicolastheuil**, dépôt **arcia-harness**.
- Les VM sont **à créer** ; aucune cible SSH n'a été fournie ou contactée.
- Cible inchangée : trois VM Debian/K3s sur VMware avec stockage partagé.

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

## Non déployé et non qualifié

Aucune VM créée, aucun SSH distant, aucun K3s/CSI/CPI/PG/ingress/Hermes installé,
aucune entrée publique, aucun accès client. Aucun secret réel collecté. Aucun test
de disponibilité, kill switch, IAM, Teams, DLP ou rebuild sur cluster exécuté.
Les services métier et le chiffrement/restore portable restent au backlog.

## Reprise

1. Consulter docs/verification-preparation.md et l'état CI du dépôt.
2. Créer les VM selon infra/vmware/vm-spec.yaml dans l'infrastructure désignée.
3. Inventorier localement VMware, empreintes SSH, réseau et endpoints avec bascule.
4. Utiliser scripts/Configure-Local.ps1 dans un terminal de confiance.
5. Qualifier CPI/CSI et leurs images, fixer les digests et preuves ; enregistrer
   les gates via programme protégé, sans modifier un résultat non observé.
6. Déployer le bootstrap en mode synthétique après revue, puis exécuter les lots 0+.
7. Recette et rebuild sur cluster neuf avant toute déclaration de release.

Ne pas redemander le compte, le nom du dépôt, sa visibilité ou le choix K3s.
