# ADR 0002 — Configuration locale protégée

Date : 2026-10-11. Statut : implémenté, qualification locale partielle.

Le wizard PowerShell stocke le document complet sous DPAPI CurrentUser, hors du
workspace et hors OneDrive, avec ACL limitée au compte courant. Il génère le token
K3s une fois, ne l'affiche pas et refuse d'écraser une configuration existante.
La clé SSH reste référencée par chemin ; aucune copie de son contenu.

L'outil de préparation déchiffre en mémoire et transmet via stdin à Python.
Le rendu Ansible contient un token en clair dans un dossier de transit à ACL
restreinte hors synchronisation ; ce transit doit être supprimé après transfert
vers un contrôleur Linux protégé. Ne jamais lire ces fichiers avec Codex.
DPAPI n'est ni une sauvegarde portable ni le chiffrement GitHub final : SOPS/age,
deux ingénieurs de récupération et kit externe restent à implémenter/qualifier.

Les diagnostics ne rendent que codes fixes et états, sans exceptions brutes,
adresses, chemins privés, identité ou stdout SSH. Les outils s'exécutent dans un
terminal local de confiance, jamais avec leurs sorties détaillées dans le chat.
