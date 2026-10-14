# État de reprise d’ArcIA — 14 octobre 2026

**Ce fichier est l’unique handoff courant.** Il remplace les consignes de reprise des [instantanés archivés](archives/README.md). Le [backlog](backlog.md) porte les travaux restants ; les [runbooks](README.md#exploitation) portent les procédures. Les résultats ci-dessous sont les dernières preuves consignées, sans nouvelle inspection du cluster pendant le nettoyage documentaire.

## Référence et lot courant

Dépôt privé `nicolastheuil/arcia-harness`, branche **main**. Dernière révision livrée avant ce lot : `18d45ee` (transfert administratif). Révision fonctionnelle du pilote : `1361605`, CI réussie selon la [clôture du 13 octobre](archives/handoff-2026-10-13-fin-session.md).

Lot courant : README synthétique, guides regroupés, 15 handoffs suivis et deux rapports historiques archivés, index complet et règles de maintenance. Les chemins imposés par AGENTS.md et les entrées techniques sont conservés. Aucun composant, version, secret requis, étape d’installation ou migration runtime ne change. Le runbook de bootstrap est aligné sur les 56 étapes existantes ; le hash documentaire Microsoft 365 est actualisé dans son lock après correction du lien vers le guide d’identité. Une validation des liens documentaires rejoint la CI. Les fichiers locaux non suivis préexistants restent en place et ne sont pas intégrés à la livraison.

## Dernier état fonctionnel consigné

| Domaine | Résultat acquis | Limite / prochaine vérification |
|---|---|---|
| Infrastructure | Trois serveurs K3s/VMware, CPI/CSI, CNPG/PostgreSQL, Hermes et HTTPS ; bascule contrôlée | Panne brutale, fencing, restore complet et rebuild neuf non qualifiés |
| Knowledge / Privacy | RAG synthétique local, RLS, modèles locaux ; appel gratuit HTTP 200 sous ZDR/prix nul ; refus Internet/DNS depuis Hermes | Groupes, corpus large, OCR et collecte métier à compléter |
| Skills / contexte | 539 entrées upstream, sept adaptations ; RTK et Headroom bornés ; 55 sondes par runtime | Context7 externe fermé, OmniRoute automatique différé ; aucune route payante |
| Identité | Comptes locaux permanents, portail personnel, admin nommé récupéré ; rôle et espace d’un compte Microsoft relus | Login Microsoft confirmé par le propriétaire ; recette interactive complète, autre tenant, groupes et HA/restore à qualifier |
| Réseau Keycloak | Sortie IPv4 publique TCP/443 configurée pour le pilote ; snapshot `/32` retiré ; TLS Microsoft/Graph 4/4 et refus HTTP/80 vérifiés | Filtrage des destinations au pare-feu amont ; IPv6 non qualifié ; défaut générique fermé |
| Portail du pilote | Pool privé 32 places, trois liées et 29 libres au dernier relevé ; deux comptes désactivés conservés | Huit places par défaut dans le harness ; charge de trente utilisateurs non qualifiée |
| Nettoyage d’espace | Un espace d’un compte absent et ses deux PVC/PV supprimés sur exception précise, puis place recréée vide ; autres bindings/volumes préservés | Ancien plan consommé : ne pas le rejouer ; nouvelle suppression = nouveau plan et autorisation |
| Microsoft 365 métier | Annexe, contrat YAML, schéma et validation hors ligne codés | Bot Teams à créer ; identité administrative et cible Azure à enrôler localement ; Graph métier et approbations serveur absents |

Preuves : [skills et Verify du 13 octobre](qualification/2026-10-13-skills.json), [identité et portail](qualification/2026-10-13-portail-personnel.json), [réseau, admission et nettoyage](qualification/2026-10-13-identity-public-https.json). Les résultats à 25 étapes Reconcile, sept étapes Verify et 200 contrôles multi-utilisateur sont des recettes datées distinctes, pas une reconstruction complète. [Matrice et limites](runbooks/recette-fondatrice.md).

## Transfert administratif

L’export du 14 octobre est terminé et vérifié : 347 fichiers opérationnels, dont les 254 bundles DPAPI inventoriés. Archive chiffrée et SHA-256 dans `secrets/local/`, hors Git. Les originaux du PC source sont conservés. La synchronisation effective OneDrive, la restauration de cet export et le nettoyage de l’état sur le PC cible restent à exécuter/confirmer.

Conserver le projet OneDrive et utiliser le programme versionné `Manage-PortableState.ps1 -Action Import -ReplaceExisting` selon le [runbook de transfert](runbooks/transfert-second-pc.md). La clé est saisie exclusivement dans le formulaire local. L’export administratif ne sauvegarde pas les bases/PVC et ne transporte pas les sessions personnelles. [Preuve assainie](qualification/2026-10-14-portable-state.json).

## Ordre de reprise

1. Relire AGENTS.md et ses trois références, ce fichier et le backlog. Vérifier main et l’état Git ; examiner séparément les fichiers non suivis.
2. Si reprise sur l’autre PC : confirmer archive/SHA-256 disponibles, restaurer selon le runbook et vérifier les bundles localement sans rendre leurs valeurs.
3. Avant toute intervention sur le pilote, relire son état avec `inspect_identity_microsoft_egress`, `inspect_identity_access_policy` et `inspect_personal_portal` via les wrappers protégés. Une preuve historique n’autorise pas à sauter cette vérification.
4. Suivre le backlog. Pour Teams/Azure, recueillir uniquement les accès manquants dans les programmes protégés ; aucune création Azure n’est déjà engagée.
5. Pour une release : compléter backup/restore, fencing/perte de nœud, support des versions et reconstruction VMware neuve en mode sûr.

La clôture du 13 octobre concernait cette soirée ; elle reste archivée. Aucune automation de reprise n’est programmée. Les exceptions humaines déjà consommées pour réseau/admin/nettoyage ne valent pas autorisation générale. Ne jamais afficher bundle, Secret, kubeconfig ou journal brut.

## Validation du nettoyage documentaire

Exécuté localement : 74 Markdown suivis, 369 liens locaux et leurs ancres,
15 schémas Mermaid ; sources JSON Schema/YAML et hashes vérifiés sur une copie
des seuls fichiers suivis. Couverture du bootstrap : 56 étapes, neuf composants
et huit outils/catalogues. Six tests Python bootstrap et neuf tests du contrat
Microsoft 365 réussis ; contrôles PowerShell du bootstrap et Plan Fresh réussis.
Les tests Microsoft 365 ont été relancés avec un répertoire temporaire dans le
workspace après un refus d’accès au Temp du sandbox Windows.
Ces résultats ne comprennent aucune inspection ou réapplication du cluster,
recette HA ou reconstruction neuve. La CI de ce lot se consulte dans GitHub
sur sa révision ; les CI historiques restent liées à leurs propres commits.
