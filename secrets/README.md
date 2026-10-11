# Emplacement des secrets

Ce dossier ne contient pas de clé ni d'identifiant. Les clés SSH initialement
présentes ici ont été déplacées hors du projet et de OneDrive, sans suppression,
par scripts/Protect-DeploymentKey.ps1. Les références de déploiement ont été mises à jour.

Emplacement logique Windows : `%LOCALAPPDATA%\ArcIA-Harness`.
Avec l'application Codex MSIX, l'emplacement physique se trouve sous le
`LocalCache\Local\ArcIA-Harness` du package Codex de l'utilisateur.
Les programmes de ce dépôt résolvent cet emplacement automatiquement.

- `integrations.dpapi` : saisies Teams, Passbolt, OpenRouter et autres champs enregistrés.
- `installation-decisions.dpapi` : choix local auth, Entra différé, TLS auto-signé.
- `ssh/` : paire SSH existante, accès limité au propriétaire Windows.
- Autres bundles `.dpapi` : accès VMware, cible, token K3s, journaux et preuves privées.

Les bundles DPAPI sont chiffrés pour le compte Windows courant ; les fichiers SSH
sont protégés par ACL. Ne pas copier ces valeurs dans Git, OneDrive ou le chat.
DPAPI local ne constitue pas encore le dispositif de récupération externe :
le backup chiffré SOPS/age et le parcours second ingénieur restent à qualifier.
