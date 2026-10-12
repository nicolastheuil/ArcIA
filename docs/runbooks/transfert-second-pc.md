# Transfert du dossier ArcIA sur le second PC

Le dossier de travail est l'ensemble à copier : code, documentation, historique Git
et **secrets/local/**. L'archive privée est volontairement absente de GitHub :
un clone Git seul ne suffit donc pas. Copier le dossier entier ou synchroniser
son contenu OneDrive, en vérifiant que l'archive est réellement disponible localement.

## Archive et clé de restauration

- Archive : `secrets/local/arcia-private.arciap` (~413 Mo lors du premier export).
- **Clé/mot de passe : 1Password personnel, entrée « ArcIA Platform Encryption Key ».**
- Ne conserver aucune copie en clair de cette valeur dans le dossier de travail.
- Format versionné AES-256-GCM, clé dérivée par PBKDF2-SHA256, 1 000 000 itérations,
  sel et nonce aléatoires ; intégrité authentifiée de l'en-tête et de l'archive.

L'export contient tout l'état local ArcIA-Harness, hors fichiers de verrouillage
transitoires : accès et configuration VMware, journaux/proofs, token K3s, intégrations,
paire SSH, known_hosts, fichiers de qualification privés et cache image/outils.
Les fichiers locaux référencés à l'extérieur, dont la clé d'intégration, sont inclus
et leurs chemins sont réécrits à l'import. Les bundles DPAPI sont déchiffrés uniquement
en mémoire avant chiffrement portable ; ils sont rechiffrés pour le compte Windows
du second PC à la restauration. La copie exploitable du PC actuel est conservée.

Export réellement exécuté et relu : 86 fichiers, 44 bundles DPAPI, un fichier externe
référencé. Tests locaux exécutés : restauration, réécriture des chemins, intégrité,
refus de mauvais mot de passe, altération et écrasement. **Restauration réelle sur
le second PC vérifiée le 12 octobre 2026** : 86 fichiers présents, 44 bundles DPAPI
lisibles par le compte courant, dix références privées valides et ACL limitées
au compte courant. Voir [l'état de reprise](../etat-reprise.md) pour les limites
du poste et le nettoyage temporaire restant.

Sur ce second PC, OneDrive marque `secrets/local` comme ReparsePoint : le
formulaire actuel refuse ce dossier dès son initialisation. L'import réussi a
utilisé une copie chiffrée et les scripts existants dans un staging local hors
synchronisation. Attention : le script déduit le workspace de son propre
emplacement ; une copie des scripts peut donc réécrire des références de projet
vers le staging. Vérifier ces références avant tout nettoyage. Pour cette
restauration, aucune référence DPAPI vers le staging n'a été relevée.

## Préparer le poste et restaurer

Prérequis : Windows, PowerShell 7.4+ (.NET 8+ ; 7.6.5 sur le poste de build),
Git, OpenSSH périmètre, Python 3.14 accessible sous `python`. Pour Ansible : WSL2 avec
distribution Linux et Python >=3.12, module venv/pip. Le réseau doit permettre les
téléchargements des dépendances et l'accès aux seules cibles désignées.
Les programmes installés, le profil Codex et les sessions Microsoft/GitHub/1Password
du système ne sont pas remplacés par une copie du projet : reconnecter l'ingénieur
sur le second PC. Aucun compte personnel ou mot de passe du système n'est exporté.

Depuis PowerShell 7, dans le dossier copié :

```powershell
pwsh -NoProfile -File .\scripts\Initialize-SecondPc.ps1 -IncludeWsl
pwsh -NoProfile -File .\scripts\Manage-PortableState.ps1 -Action Import
```

Saisir localement la valeur de l'entrée 1Password. La restauration refuse un dossier
ArcIA-Harness local déjà rempli ; ne pas l'effacer aveuglément. Elle prépare et
relit les fichiers dans un dossier temporaire protégé, puis le renomme à la fin.
Une restauration incomplète ne remplace donc pas l'état local. Elle recrée l'état
opérationnel sous `%LOCALAPPDATA%\ArcIA-Harness`, ACL propriétaire, et adapte les
chemins de l'ancien poste/dossier. Elle n'exécute aucun déploiement. Le stockage
opérationnel déchiffré reste hors du dossier synchronisé ; sa sauvegarde transportable
chiffrée est dans le dossier de travail demandé par l'utilisateur.

Lire ensuite docs/handoff-2026-10-11.md. Vérifier les empreintes/cibles existantes,
la résolution réseau et l'authentification gh de l'ingénieur avant toute reprise.
Ne pas recréer les VM, le compte technique, le token ou les clés SSH.

## Mettre à jour la copie transportable

Après chaque lot modifiant l'état privé :

```powershell
pwsh -NoProfile -File .\scripts\Manage-PortableState.ps1 -Action Export
```

Utiliser la même entrée 1Password. L'export relit/déchiffre l'archive et vérifie
chaque fichier avant remplacement ; il refuse un changement de source pendant
l'opération. La précédente archive est conservée en `.previous`. Copier l'archive
mise à jour avec le dossier de travail. Les fichiers `portable-status.json` et
`portable-form-status.json` contiennent seulement des états sûrs et restent ignorés.

Ce transfert ne qualifie ni HA, ni sauvegarde cohérente d'un cluster actif, ni
rebuild par un deuxième ingénieur. Ces recettes restent dans le backlog de release.
