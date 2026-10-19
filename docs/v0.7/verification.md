# Vérifications de l'étude ArcIA v0.7

Date : 19 octobre 2026. Base : commit `09dd2a5`, branche locale `v0.7`. Cette page distingue les commandes réellement exécutées des recettes futures du [plan](lots.md).

## Git et conservation du travail

- `git fetch origin` exécuté ; `HEAD` et `origin/main` étaient identiques à `09dd2a5`.
- Les contenus des 179 fichiers suivis correspondaient au distant ; l'index présentait un ancien état incohérent. Copie binaire de l'index conservée dans `.git/index.arcia-pre-sync-20261019-215951`, empreinte vérifiée avant réalignement.
- Index réaligné sans remplacer les fichiers ; cache de deux fichiers CRLF rafraîchi sans delta de contenu.
- Branche `v0.7` créée, répertoire propre avant création de ce dossier. Aucun push ou accès à un environnement privé.

## Exécutions locales

| Contrôle | Résultat effectivement observé |
|---|---|
| Suite sur Python système 3.14 | 269 tests découverts, échec avec 3 erreurs d'import ; dépendances de validation absentes (`httpx`, `yaml`) |
| Ancien `.venv` | Interpréteur historique absent ; aucun test lancé avec cet environnement |
| Environnement temporaire | Créé sous le dossier temporaire Windows ; installation de `requirements-validation.txt` sans modifier les dépendances du dépôt |
| Suite complète dans cet environnement | **303 tests, 14,002 s, OK** ; commande `python -m unittest discover -s tests -v` avec son interpréteur |
| Documentation avant nouveaux documents | **49 fichiers, 412 liens locaux, aucune erreur** |
| Documentation avec le dossier de conception | **55 fichiers, 448 liens locaux, aucune erreur** |
| Diagrammes Mermaid | **22 schémas analysés, dont 5 nouveaux**, avec le parseur Mermaid 12.2.0 dans un environnement temporaire ; analyse syntaxique, pas recette visuelle navigateur |
| PowerShell | **7 fichiers `scripts/*.ps1`, aucune erreur syntaxique** |
| Bash | **5 fichiers** : scripts de déploiement, secrets et validation, `wizard.sh`, `skills/sync-skills.sh` ; `bash -n` avec Git Bash, aucune erreur |
| Dry-run | Fixture `tests/fixtures/deploy.synthetic.yaml`, sortie 0 ; avertissement attendu de fournisseur cloud absent ; aucun déploiement |

Le log de la suite complète est local temporaire : `arcia-v07-valid-20261019-220233.log`. Il ne fait pas partie du dépôt. Le premier échec d'environnement est conservé ici afin de ne pas le présenter comme une exécution réussie.

## Contrôles de livraison documentaire

- [x] Validation de tous les liens des nouveaux documents.
- [x] Analyse syntaxique des nouveaux diagrammes Mermaid.
- [x] Relecture indépendante de la conception, intégration des corrections et vérification du diff.
- [x] Vérification que seuls les six documents `docs/v0.7/` et leur entrée dans `docs/README.md` ont été modifiés.

La revue indépendante a conduit à préciser cinq contrats avant livraison : contexte DLP entre transports, sandbox des programmes publiés, autorité sur les habilitations natives, attestation de recette du builder et collecte Prometheus limitée. `git diff --check` ne relève aucune erreur d'espacement. Aucun fichier applicatif, manifeste ou registre de version n'est modifié par cette étude.

## Ce qui n'a pas été exécuté

Aucun déploiement, test réseau de cluster, appel à un fournisseur LLM, accès HubSpot/PGI, migration de base, recette de navigateur ou rebuild n'a été lancé pour cette étude. Les 43 contrôles API et 24 contrôles DLP décrits dans l'état réel sont des résultats historiques du socle. Les recettes A2A, multi-tenants, exceptions DLP/ZDR, builder et dashboards de ce plan sont futures.
