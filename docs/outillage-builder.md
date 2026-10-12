# Outillage builder et GitHub

Installation autorisée le 12 octobre 2026, conformément aux outils retenus au
[plan §25](plan-integration-hermes.md). Périmètre : poste ingénieur et code
synthétique du harness. Aucun de ces outils n’a été ajouté au runtime client,
au Pod Hermes ou à un exécuteur métier.

## Installé et vérifié

| Outil | Version / source fixée | Installation et preuve |
|---|---|---|
| Context7 MCP | `@upstash/context7-mcp` 4.3.0, MIT | NPM utilisateur ; initialize, tools/list et requête documentaire générique PostgreSQL réussis |
| CLI skills | `skills` 1.7.2, MIT | NPM utilisateur ; version 1.7.2 exécutée ; télémétrie désactivée par wrapper |
| LintLang | 0.8.2, Apache-2.0 | Venv WSL ; version et scans AGENTS.md/builder/role.md exécutés |
| Superpowers ciblé | Commit `bb92a77741419a4ab5f06e711a283343f1ada0c3`, MIT | 4 skills projet installés, adaptés et hashés |
| ECC ciblé | Commit `b92f181b3b748d1abbc2afd94af6aa7d8c8fca29`, MIT | 2 skills projet installés, adaptés et hashés |

Sources officielles : [Context7](https://github.com/upstash/context7),
[skills](https://github.com/vercel-labs/skills),
[LintLang](https://github.com/hermes-labs-ai/lintlang),
[Superpowers](https://github.com/obra/superpowers), [ECC](https://github.com/affaan-m/ECC).
Les numéros désignent le lot installé ; ils ne promettent pas de rester les dernières versions.

Les packages NPM et leurs dépendances ont un package-lock avec intégrité ;
l’installation désactive les lifecycle scripts. LintLang et PyYAML ont un lock
avec hashes. Les sources de skills ont été installées avec `skill-installer`
aux commits fixés ; les fichiers sélectionnés sont versionnés dans le harness.
Voir [tools.lock.json](../builder/tools.lock.json),
[catalog.lock.json](../builder/catalog.lock.json),
[package-lock.json](../builder/npm/package-lock.json) et
[licences](../builder/licenses/README.md).

## Catalogue de skills

Superpowers : `verification-before-completion`, `systematic-debugging`,
`receiving-code-review`, `test-driven-development`.
ECC : `python-patterns`, `postgres-patterns`.
Ils vivent sous `.agents/skills`, sont détectables par Codex au prochain tour et
se déclenchent explicitement. S’ils n’apparaissent pas, rouvrir la session.

L’adaptation ArcIA borne leur usage au builder : instructions utilisateur et
AGENTS.md prioritaires, tests proportionnés, aucune donnée client brute ni secret,
revue dans la session, délégation seulement sur demande explicite. Les exemples
ECC ne sont pas un schéma applicatif déjà migré ; notamment les exemples Supabase
doivent être adaptés à PostgreSQL/Entra et vérifiés avant usage.

Le bootstrap Superpowers complet et les agents/hooks ECC ne sont pas activés.
Aucun apprentissage, export de sessions, mémoire interclients ou publication
automatique de skills. Les références techniques amont ne remplacent pas les
gates du harness. `validate_sources.py` contrôle les empreintes du catalogue.

## Réinstaller sur un poste

Préparer les runtimes du [runbook second PC](runbooks/transfert-second-pc.md),
cloner ce dépôt, puis depuis sa racine :

```powershell
pwsh -NoProfile -File scripts/Install-BuilderTools.ps1
pwsh -NoProfile -File scripts/Register-BuilderContext7.ps1
```

NPM est installé sous `%LOCALAPPDATA%\ArcIA-Builder\npm` ; LintLang sous
`~/.local/share/arcia-builder/python` dans WSL. Le script utilise le Node présent
sur le poste (26.7.0 / npm 11.19.0 observés), sans changer le PATH système.
Le venv utilise le Python 3.14.7 déjà préparé ; uv 0.13.0 est contrôlé.
Les six skills arrivent avec le clone Git, sans téléchargement flottant.

Context7 est enregistré comme `arcia_context7` dans la configuration utilisateur
Codex. Le script ne remplace aucune autre table et refuse une table homonyme
différente. Une sauvegarde de configuration est chiffrée DPAPI avant modification.
La configuration contient les chemins locaux ; ceux-ci ne vont pas dans Git.
Le serveur sera chargé à la prochaine session prenant en compte cette configuration.
Source : [configuration MCP officielle](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Utilisation et confidentialité

```powershell
& ./scripts/Invoke-BuilderTool.ps1 -Tool skills -ToolArguments @('--version')
& ./scripts/Invoke-BuilderTool.ps1 -Tool lintlang -ToolArguments @('scan','AGENTS.md','builder/role.md','--format','json')
```

Le wrapper force `DISABLE_TELEMETRY=1` pour son processus. Le CLI skills est
réservé au catalogue revu ; ne pas lancer une mise à jour globale depuis un agent.
Context7 est un service documentaire externe : uniquement produit/version et
question générique, jamais configuration, identité ou inventaire client.
Le smoke test a envoyé seulement une demande publique sur PostgreSQL.

LintLang scanne localement. Le rapport de ce lot donne PASS structurel pour les
deux fichiers, mais **confiance heuristique faible (couverture 65 %)**, notamment
sur les frontières formulées en français. Ne pas en déduire une absence de risque.
Il est ajouté en CI en mode rapport, sans `--fix` ni seuil bloquant sur les findings.
Une erreur d’entrée/exécution reste une erreur CI, pas un rapport positif.

## Outils non adoptés

| Outil | Décision conservée |
|---|---|
| RTK | Pilote builder avant adoption ; benchmark sorties/coûts non réalisé |
| Graphify | Pilote code-only après qualification réseau ; aucun graphe documentaire activé |
| Headroom | Option après benchmark de compression ; pas d’empilement avec OmniRoute |
| Ponytail | Option de revue ponctuelle |
| public-apis | Catalogue de veille, pas un service à installer |

Ils n’étaient pas des outils validés pour activation générale. Leur statut reste
celui du plan ; aucune dépendance facultative ne bloque le socle.
OmniRoute/Docling/embeddings appartiennent aux lots applicatifs futurs, pas à
cette installation des outils du builder.

## GitHub : source de vérité et livraison

Dépôt actuel : **nicolastheuil/arcia-harness**, visibilité privée et droits
push/admin vérifiés via le connecteur. Branches de travail préfixées `codex/`.
La branche du lot est `codex/socle-qualification-handoff` ; ne pas assimiler son
contenu à une release de production ou à la branche principale avant intégration.

Versionner code générique, manifests sans secrets, locks, tests, ADR, README,
runbooks et handoffs assainis. Les credentials et inventaires restent protégés ;
`secrets/local` et les archives portables sont ignorés. Ne pas ajouter les
scripts de debug non suivis ou anciens handoffs contenant des détails privés.

Avant push : diff revu, contrôle de confidentialité, liens locaux et schémas,
tests et validation sources, syntaxe PowerShell. La CI hébergée n’a aucun secret
ni route entreprise/client. Les workflows et dépendances fixés sont dans
[validate.yml](../.github/workflows/validate.yml). LintLang produit un rapport
complémentaire aux tests ; les tests de frontières demeurent indispensables.

Une PR décrit problème, résultat, validations exécutées et limites. La publication
publique du générique et une release installable attendent revue de confidentialité,
recette et rebuild. Configurations/backup privés utilisent des dépôts séparés
avec chiffrement avant upload, conformément au plan.

## Désactivation et mise à jour

Arrêter l’usage du wrapper pour les CLI. Pour Context7, mettre `enabled=false`
dans sa seule table `mcp_servers.arcia_context7`, puis recharger Codex.
Les skills ont déjà l’invocation implicite désactivée ; ils peuvent être désactivés
individuellement par la configuration Codex sans effacer le catalogue.
Voir [skills officiels](https://learn.chatgpt.com/docs/build-skills).

Une mise à jour passe par une branche : nouvelles versions/commits, revue des
instructions/dépendances/licences, locks/hashes, tests, puis installation ciblée.
Ne pas remplacer un dossier ou une configuration existants sans contrôle de propriété.
