# ADR 0019 — Documentation par fonction et reprise unique

Statut : adopté le 14 octobre 2026 pour le nettoyage demandé par le propriétaire.

## Problème

Les handoffs successifs occupent la racine documentaire et mélangent des états
remplacés avec les consignes actuelles. Plusieurs index et résumés conservent
des références périmées, ce qui rend la reprise et la lecture du projet difficiles.

## Décision

README synthétique avec un lien vers chaque référence complète. Guides dans
`docs/guides/`, procédures dans `docs/runbooks/`, anciennes transmissions dans
`docs/archives/`. Un seul handoff courant : `docs/etat-reprise.md`, mis à jour
en place. Le backlog porte les travaux, les ADR les décisions et les preuves
assainies les essais datés. Les trois références AGENTS.md et les chemins
techniques des scripts/services/bootstrap restent stables.

## Conséquences

Les liens relatifs sont réécrits lors du déplacement et contrôlés en CI,
y compris leurs ancres. L’index couvre tous les guides/runbooks/ADR/archives.
Les archives gardent leurs résultats historiques et ne commandent plus la
reprise courante. Aucun composant déployé, secret, volume ou version ne change.
Les diagnostics et brouillons non suivis restent locaux, examinés séparément.
Voir les [règles de maintenance](../organisation.md).
