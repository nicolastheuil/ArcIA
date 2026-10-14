# Transfert ArcIA vers l'autre PC

Procédure courante du 14 octobre 2026. Le dossier OneDrive du projet reste en
place : code et documentation sont synchronisés et versionnés sur GitHub.
Seul l'ancien état opérationnel local ArcIA, hors OneDrive, est remplacé.
La configuration réelle et ses secrets sont exclus de Git.

## Archive chiffrée et clé

Archive : `secrets/local/arcia-private.arciap`, dans le projet synchronisé.
Clé : entrée 1Password personnelle **ArcIA Platform Encryption Key**, à saisir
uniquement dans le formulaire local. Aucun mot de passe dans le chat, Git ou
un fichier en clair à côté de l'archive.

Le format ARCIAP01 conserve AES-256-GCM et PBKDF2-SHA256 avec un million
d'itérations, sel et nonce aléatoires. L'export relit/déchiffre l'archive et
contrôle les tailles et SHA-256 de chaque entrée avant de remplacer le fichier.
Les bundles DPAPI sont déchiffrés en mémoire, puis inclus dans l'archive chiffrée.
Ils seront rechiffrés pour le compte Windows du PC cible lors de l'import.

L'export comprend tous les bundles locaux ArcIA, les clés SSH et fichiers
locaux référencés existants, les configurations et les preuves privées.
Les profils navigateur, leurs sessions et caches sont exclus ; un bundle
DPAPI trouvé dans un de ces profils provoque un refus plutôt qu'une omission.
Les fichiers de verrouillage transitoires sont exclus. Un changement d'un
fichier source, ou l'ajout d'un fichier pendant l'export, invalide l'opération.
Les originaux de ce PC sont conservés.

Ce transfert ne copie pas les comptes/sessions personnels Windows, GitHub,
Microsoft ou 1Password, et ne sauvegarde pas les bases/PVC du cluster.
Les outils du poste sont préparés séparément avec les scripts du projet.

## Export sur le PC de départ

Depuis PowerShell 7.4+ dans le projet :

```powershell
pwsh -NoProfile -STA -File .\scripts\Manage-PortableState.ps1 -Action Export
```

Saisir et confirmer la clé 1Password, puis lancer l'export. Attendre le message
« Archive créée et relue intégralement ». L'état sûr dans
`secrets/local/portable-status.json` doit avoir le code
`PORTABLE_ARCHIVE_CREATED_AND_VERIFIED` et une date `verified_at` récente.
Un ancien statut sans date ne prouve pas l'export courant.

Le SHA-256 courant est dans ce statut et dans le fichier voisin
`arcia-private.arciap.sha256`. L'ancienne archive est conservée en `.previous`.
Attendre la synchronisation OneDrive complète de l'archive et de ses fichiers
de contrôle avant de changer de PC. Vérifier sa disponibilité locale sur la
cible et comparer son SHA-256 ; un clone Git seul ne contient pas l'archive.

Les placeholders Cloud Files OneDrive sont acceptés dans le dossier d'archive ;
les redirections SymbolicLink/Junction restent refusées. Il n'est plus nécessaire
de recopier les scripts dans un staging qui changerait artificiellement le
workspace enregistré.

## Restaurer sur le PC cible et nettoyer l'ancien état

Fermer les fenêtres de navigateur ArcIA et les opérations d'administration
locales qui utilisent l'ancien état. Conserver le projet dans OneDrive, puis
ouvrir PowerShell 7.4+ dans ce projet à jour :

```powershell
pwsh -NoProfile -STA -File .\scripts\Manage-PortableState.ps1 -Action Import -ReplaceExisting
```

Saisir la même clé 1Password dans le formulaire local. Le dossier cible est
l'état ArcIA-Harness découvert pour ce compte Windows, normalement
`%LOCALAPPDATA%\ArcIA-Harness` ; le transport MSIX peut désigner sa copie
physique sous LocalCache. Le programme conserve les chemins privés hors chat.

L'option **-ReplaceExisting** autorise le remplacement de cet ancien état.
Le programme vérifie l'archive et prépare un staging privé hors OneDrive avant
de vider la cible. Il déplace temporairement l'ancien dossier, publie l'état
neuf, relit les bundles DPAPI, puis supprime l'ancien dossier. Il n'effectue
aucune fusion : les anciens secrets absents de l'archive ne subsistent pas.
Si la publication ou la lecture finale échoue, l'ancien dossier est remis en
place. Un mauvais mot de passe ou une archive altérée ne nettoie pas la cible.

La cible ne peut être le profil Windows, LocalAppData entier, le projet ou
un dossier OneDrive. Les liens de système de fichiers sont refusés. L'archive
ne doit pas se trouver dans le dossier local à remplacer. Aucun autre dossier
Windows ni volume Kubernetes n'est supprimé. Sans `-ReplaceExisting`, l'import
continue de refuser un état local non vide.

Le succès est `PORTABLE_STATE_RESTORED_FOR_CURRENT_WINDOWS_USER`, avec
`merge_performed=false` et `deployment_started=false`. Les chemins de l'ancien
poste sont adaptés au nouveau poste/workspace, et les fichiers DPAPI sont
lisibles uniquement par le compte Windows de restauration. Il n'y a aucun
déploiement ni reprise automatique d'un plan d'administration sauvegardé.

## Vérifier et reprendre

Préparer les dépendances du contrôleur local si nécessaire :

```powershell
pwsh -NoProfile -File .\scripts\Prepare-SecondPcRuntime.ps1 -IncludeWsl
```

Ce script prépare les outils locaux ; il ne recrée pas le cluster. Vérifier
ensuite la découverte de l'état complet, les références SSH/certificats et
les accès de l'ingénieur. Les diagnostics privés restent sous DPAPI/ACL ;
aucun dump de bundle, kubeconfig ou inventaire dans le chat.

Lire le [handoff de transfert](../handoff-2026-10-14-transfert-pc.md), puis le
[handoff fonctionnel de clôture](../handoff-2026-10-13-fin-session.md).
Ne pas régénérer les identités, VM, tokens ou volumes existants et ne pas
rejouer un ancien plan destructif. Le bot Teams reste à créer après reprise
explicite de ce travail.

## Résultats historiques et limites

Le premier transfert du 12 octobre portait 86 fichiers et 44 bundles DPAPI.
Ces nombres ne décrivent pas le nouvel export : son statut courant donne le
compte vérifié. Les tests synthétiques exécutés couvrent chiffrement,
intégrité, mauvais mot de passe, réécriture des références, refus d'écrasement
par défaut, remplacement sans fusion, retour arrière après échec, refus des
racines larges/OneDrive/liens, exclusion des profils et ajout tardif d'un secret.

La préparation et le test synthétique du nettoyage ne valent pas restauration
réelle exécutée sur l'autre PC. Le nouveau compte Windows doit effectuer cette
restauration et ses lectures de contrôle. Aucune qualification HA, sauvegarde
cohérente des applications ou reconstruction VMware neuve n'est annoncée.