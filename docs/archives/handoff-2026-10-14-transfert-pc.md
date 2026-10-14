# Handoff — transfert du poste administratif, 14 octobre 2026

> Archive historique. Pour la reprise actuelle, lire [l’état courant](../etat-reprise.md).

## Demande et périmètre

Le propriétaire rebascule sur l'autre PC. Il demande un export de tous les
secrets ArcIA et le nettoyage de l'ancien état avant restauration. Il précise
que OneDrive est déjà synchronisé et doit rester en place : seuls les secrets
et l'état opérationnel local ArcIA hors OneDrive sont à remplacer.
Le travail autorisé ici concerne le transfert du poste ; aucun changement
K3s, identité, volume, fournisseur ou création Teams n'est engagé.

## Inventaire du PC source

Une seule racine physique d'état ArcIA est retrouvée ; les vues Windows/MSIX
peuvent apparaître comme plusieurs chemins de la même racine. L'inventaire a
relu 254 bundles DPAPI, tous déchiffrables et JSON lisibles sous le compte
Windows courant. Aucun contenu, identifiant ou secret n'a été rendu au modèle.

Les profils de navigateur occupaient la majorité du supplément de taille et
faisaient dépasser la limite de l'ancien export. L'exporteur sélectionne
maintenant 347 fichiers opérationnels avant ajout des références externes,
environ 403 Mio, dont les 254 bundles. Profils, cookies et caches de navigateur
sont exclus ; trouver un bundle DPAPI dans un tel profil entraîne un refus.
Tous les bundles ArcIA de cet inventaire restent sélectionnés.

L'export réel du 14 octobre est **terminé et vérifié** : 347 fichiers, dont
254 bundles DPAPI, archive chiffrée d'environ 394,35 Mio. Le programme l'a
déchiffrée et relue intégralement, puis le SHA-256 du fichier final a été
comparé au statut avec succès. Tous les bundles inventoriés sont inclus.
Les fichiers référencés présents appartenaient déjà à l'arborescence exportée.
Les originaux du PC source sont conservés.

L'ancienne archive du 11 octobre (86 fichiers/44 bundles) est remplacée ; sa
copie `.previous` reste un historique, pas l'archive à restaurer. Les contrôles
courants sont dans `secrets/local/portable-export-status.json` et
`arcia-private.arciap.sha256`. Aucun mot de passe n'est dans ces fichiers.
[Preuve assainie](../qualification/2026-10-14-portable-state.json).

## Code de transfert préparé et tests

`Manage-PortableState.ps1 -Action Export` prend la clé dans une fenêtre locale.
L'entrée 1Password est **ArcIA Platform Encryption Key** ; aucune clé dans le
chat ou un argument de commande. L'export chiffré reste dans
`secrets/local/arcia-private.arciap`, ignoré par Git et synchronisé par OneDrive.
Le source DPAPI et les clés originales sont conservés sur le PC de départ.

`Manage-PortableState.ps1 -Action Import -ReplaceExisting` remplace l'ancien
état local hors OneDrive. Il authentifie l'archive, prépare et vérifie un
staging protégé, vide le chemin cible par déplacement temporaire de l'ancien
dossier, publie et relit le nouvel état, puis supprime l'ancien dossier.
Aucune fusion : les anciens secrets absents de l'archive ne restent pas.
Un échec de publication remet l'ancien dossier en place. Les protections
refusent profil Windows/LocalAppData entier, workspace/OneDrive, liens et
archive située dans le dossier à remplacer. Sans option explicite, le refus
d'un état local non vide est conservé.

Tests synthétiques exécutés : chiffrement/intégrité, mauvais mot de passe,
DPAPI et chemins réécrits, refus d'écrasement par défaut, remplacement sans
fusion, rollback après échec de lecture finale, refus des racines larges,
workspace et junction, archive dans la cible, exclusion des profils,
bundle mal placé et ajout de secret pendant l'export. Les tests ne constituent
pas une restauration réelle exécutée sur le second PC.

Le contrat portable, ses hashes et les contrôles de couverture rejoignent
`bootstrap/qualification.json`, `bootstrap/portable.lock.json`, le Plan du
bootstrap et `versions.lock.yaml`. Aucune restauration automatique n'est
ajoutée aux 56 étapes de qualification.

## Exploitation du programme local

Un premier lancement masqué a créé un formulaire inaccessible à l'utilisateur.
Ce processus a été fermé, puis le formulaire a été relancé de façon visible,
avec la racine source explicite dans l'environnement local du processus.
Le propriétaire a confirmé voir la fenêtre et a saisi la clé localement.
L'export a réussi ; les champs ont été vidés par le programme et le formulaire
a été fermé à la clôture. Aucune clé n'a été rendue au modèle. Le statut récent
avec `verified_at` et le contrôle SHA-256 remplacent l'ancien statut.

## Reprise sur le PC cible

Suivre [le runbook de transfert](../runbooks/transfert-second-pc.md).
Attendre que l'archive courante et son SHA-256 soient réellement synchronisés
et disponibles localement : l'upload OneDrive n'a pas été confirmé par une
API de synchronisation. Garder le dossier de projet OneDrive en place.
Fermer les fenêtres ArcIA et opérations locales qui verrouillent l'ancien état.
Puis exécuter dans PowerShell 7.4+ depuis le projet à jour :

```powershell
pwsh -NoProfile -STA -File .\scripts\Manage-PortableState.ps1 -Action Import -ReplaceExisting
```

Saisir la clé uniquement dans le formulaire. Vérifier le résultat
`PORTABLE_STATE_RESTORED_FOR_CURRENT_WINDOWS_USER`, `merge_performed=false`
et `deployment_started=false`, puis la lisibilité locale des bundles et les
références de fichiers. Préparer les dépendances du contrôleur séparément si
nécessaire. Ne pas réutiliser un ancien plan de suppression ou recréer les VM.
La restauration réelle et le nettoyage du PC cible n'ont pas été exécutés
sur le PC source. Le script local non suivi `scripts/import-portable.ps1` est
un ancien dépannage ; utiliser la commande versionnée ci-dessus.

Lire ensuite le [handoff fonctionnel du 13 octobre](handoff-2026-10-13-fin-session.md).
La plateforme reste dans cet état : HTTPS public TCP/443 pour Keycloak,
admission utilisateur du tenant, admin local récupéré, pool 32 places dont 29
libres et deux comptes désactivés conservés. Bot Teams encore à créer après
réenrôlement administratif Azure ; aucun travail Azure automatique lancé.

Le transfert administratif ne vaut pas sauvegarde des PVC/bases, ni recette
HA ou rebuild VMware neuf. Les sessions personnelles Windows/Microsoft/GitHub/
1Password et les programmes installés ne sont pas copiés par cette archive.
