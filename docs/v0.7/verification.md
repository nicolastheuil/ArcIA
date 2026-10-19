# Vérifications de l'étude ArcIA v0.7

> Les premières sections attestent uniquement l’étude documentaire (lot 00). Les changements de versions et recettes sur le cluster existant appartiennent au complément du lot 01 en fin de document.

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


## Complément du lot 01 — Versions et cluster existant

Le 19 octobre 2026, le cadrage a évolué sur instruction utilisateur : aucun champ `category` dans le catalogue cible, les destinations LiteLLM portent le transport vers un fournisseur ou un agent A2A. Le code de routage historique reste conservé jusqu’à parité A2A. Le registre cible devient **v0.7.0, canal development** ; les versions stables compatibles et digests sont fixés sans publication d’une release installable.

### Changements codés

- Images gérées par ArcIA et laboratoire épinglés par digest ; dernières versions stables relevées dans les sources officielles. Python 3.14.8 et NumPy 2.4.6 sont les dernières compatibles avec les contraintes Presidio/spaCy, et non les dernières globales. Les cibles des composants partagés et de la supervision future restent séparées.
- Dépendances directes Presidio, Teams et validation fixées ; même fichier Teams consommé par Docker et ConfigMap. Les dépendances transitives restent à verrouiller par hashes pour un rebuild certifié.
- Précontrôle PostgreSQL avant mutation : refus du changement majeur, de la version inconnue, du PVC orphelin et de l’erreur de lecture. Aucun volume d’instance remplacé ni migration exécutée. PostgreSQL 18.6 reste une cible à migrer avant bascule de l’instance.
- Le wizard ne peut plus retirer un digest pour appliquer un tag absent du registre. Le synchroniseur de versions ne réécrit plus les attestations historiques ; l’état réel v0.6.0 est conservé.

### Défaut découvert avec le proxy réel

Un appel direct synthétique avec en-tête PEM a obtenu **HTTP 200** avec l’ancien paramétrage du guardrail sur LiteLLM 1.106.0. Les tests Hermes seuls ne détectaient pas cet écart puisque leur barrière amont bloquait déjà cette entrée. Le code officiel de la version fixe montre qu’une réponse d’analyse invalide peut être remplacée par une liste vide si aucune politique PII n’est explicitée.

Le correctif réutilise le guardrail natif : politique `EMAIL_ADDRESS: MASK` explicite, configuration identique dans rendu/manifeste/Lab/fixture, délai borné et normalisation des erreurs DLP en HTTP 422. Les tests de configuration et d’indisponibilité ont échoué avant correction puis réussi. Aucun secret réel ni fournisseur cloud n’a servi à cette recherche.

Le premier essai complet avec LiteLLM réel a aussi exposé un défaut du canari : son compteur supposait que `/health` était celui du fournisseur déterministe. Ses **43 contrôles API avaient réussi**, puis la recette native s’était arrêtée. Le compteur cible désormais explicitement le fournisseur synthétique, avec des permissions réseau réservées aux trois runtimes de la recette. Ce changement ne touche aucune politique de production.

### Périmètre et limites

Le serveur Kubernetes du cluster existant répond en `v1.37.1+k3s1` et trois nœuds sont prêts. La configuration de connexion protégée est consommée localement ; aucun accès, adresse ou identité d’instance n’est versionné. Les recettes créent leurs propres namespaces à nonce, comptes, Secrets et volumes synthétiques. La base PostgreSQL de qualification est un `emptyDir` indépendant ; aucun PVC ou Secret d’instance n’est monté.

Commandes de recette :

```text
python scripts/qualify_hermes_workspaces.py --config arcia.config.yaml --report artifacts/v07-versions-hermes-qualification.json
python scripts/qualify_hermes_workspaces.py --config arcia.config.yaml --real-gateway --report artifacts/v07-real-gateway-qualification.json
```

La première commande conserve le fournisseur déterministe à la place de LiteLLM. La seconde utilise le vrai LiteLLM et la vraie base PostgreSQL avant ce fournisseur. Elle teste directement la barrière aval sans assainissement préalable par Hermes, puis la panne et la reprise. Les rapports restent locaux et ignorés par Git.

Ces essais ne qualifient pas le pont A2A, MCP Gateway, Auto Router, les licences, les budgets, les autres API d’inférence (embeddings ou multimodal), l’annulation, le SSO réel, le bot Teams, l’isolation hostile complète, les tableaux Grafana ni le rebuild neuf. Aucun composant partagé du cluster ni service de production n’est mis à jour. Le lot 01 reste ouvert et `security_release_ready` reste faux.


### Résultats finaux du complément

| Contrôle exécuté | Résultat observé |
|---|---|
| `python -m unittest discover -s tests -v` avec l’environnement temporaire actualisé | **314 tests, 14,697 s, OK** |
| Documentation | **55 fichiers, 459 liens locaux, aucune erreur** |
| Cohérence des versions | `python scripts/sync_versions.py --check`, sortie 0 ; attestations historiques préservées |
| Syntaxe des scripts | **7 fichiers PowerShell et 5 fichiers Bash**, aucune erreur ; fichiers Python de la recette compilés sans erreur |
| Simulation de déploiement | Fixture synthétique, sortie 0 ; aucun déploiement de cette fixture |
| Recette Hermes avec fournisseur déterministe | **43 contrôles API/isolation et 23 contrôles DLP natifs, tous réussis** |
| Recette avec vrais LiteLLM 1.106.0, PostgreSQL 18.6, Open-WebUI 0.12.3, Hermes 0.22.2 et Presidio | **43 contrôles API/isolation, 23 contrôles DLP natifs et 13 contrôles directs du guardrail, tous réussis** |
| Refus aval vérifiés directement | PEM, CIDR, MAC et FQDN : HTTP 422, compteur fournisseur inchangé ; message bénin et streaming acceptés |
| Panne et reprise aval | HTTP 422 sans appel au fournisseur pendant la panne ; HTTP 200 après reprise. Le canari laisse expirer le keep-alive avant d’éprouver le retrait des endpoints |
| Nettoyage | **Trois namespaces de cette session vérifiés absents** après suppression à nonce ; aucune instance réelle modifiée |

Les 23 indicateurs natifs de ces rapports ne doivent pas être rebaptisés « 24 » à partir d’un ancien texte : ce complément reprend les clés réellement émises. Les comptes et préférences du Power User synthétique sont préservés ; les fichiers restent exacts et les droits croisés sont refusés, y compris après redémarrage. Le compteur du fournisseur confirme l’absence de PII brute du canari d’outil dans les inférences.

Une revue indépendante a conduit à corriger les anciennes versions encore affichées dans l’architecture et la promotion automatique d’une attestation tokenmaxing vers v0.7. Les régressions du synchroniseur, du verrouillage des images et de la confidentialité sont couvertes par des tests observés en échec avant correction puis en réussite. Le passage PostgreSQL de l’instance, les capacités A2A et les autres limites énumérées plus haut restent à recetter avant le rollout correspondant.
