# Outils Hermes, installation K3s et GitHub

La décision actuelle remplace l’ancien placement sur le poste : **les outils sont installés dans l’instance Hermes du cluster K3s**. Le nom historique `builder/` désigne désormais les locks et le catalogue de fabrication, sans autoriser une installation locale.

## Emplacement et versions

Namespace `arcia-hermes`, PVC `hermes-tools` 10 Gi RWOP, monté à `/opt/arcia-tools` en lecture seule dans Hermes. Le Job d’installation utilise la même image Hermes fixée par digest, UID 10000, sans token Kubernetes. Il est supprimé avant de rattacher le PVC au runtime. Les versions et intégrités sont dans [tools.lock.json](../builder/tools.lock.json), [NPM lock](../builder/npm/package-lock.json), [Python lock](../builder/requirements-tools.lock.txt) et [catalogue](../builder/catalog.lock.json).

| Outil | Version | Chemin / usage |
|---|---|---|
| Context7 | 4.3.0 | `/opt/arcia-tools/bin/context7`, MCP natif |
| skills | 1.7.2 | `/opt/arcia-tools/bin/skills`, catalogue revu |
| LintLang | 0.8.2 | `/opt/arcia-tools/bin/lintlang`, rapport |
| RTK | 0.51.0 | `/opt/arcia-tools/bin/rtk`, invocation explicite |
| Headroom | 0.40.0 | `/opt/arcia-tools/bin/headroom`, Python isolé |
| OmniRoute | 3.8.51 | `node /opt/arcia-tools/npm/node_modules/omniroute/bin/omniroute.mjs` |
| Certbot | 5.8.0 | `/opt/arcia-tools/bin/certbot` |

Sources : [RTK](https://github.com/rtk-ai/rtk), [Headroom](https://github.com/headroomlabs-ai/headroom), [OmniRoute](https://github.com/diegosouzapw/OmniRoute), [Context7](https://github.com/upstash/context7), [skills](https://github.com/vercel-labs/skills), [LintLang](https://github.com/hermes-labs-ai/lintlang). Les sources Superpowers/ECC et licences sont conservées dans [le catalogue de licences](../builder/licenses/README.md).

Six skills sont versionnés sous `deploy/hermes/skills` et chargés via `skills.external_dirs` : verification-before-completion, systematic-debugging, receiving-code-review, test-driven-development, python-patterns et postgres-patterns. Aucun bootstrap, hook, export de sessions ou apprentissage automatique n’est activé.

## Réseau et activation

Hermes accède au DNS interne, au service Knowledge privé et à un relais Context7. Le relais autorise seulement les GET documentaires Context7 vers sa destination HTTPS fixée. Ce relais ne constitue pas un assainisseur : les requêtes restent génériques et synthétiques. Hermes ne dispose pas de sortie Internet directe ni de credentials LLM ou PostgreSQL.

RTK est installé sans interception automatique des commandes. Headroom est disponible sans compression automatique ni mémoire interclients. OmniRoute est installé, sa version CLI est vérifiée, mais son serveur et ses fournisseurs restent désactivés tant que la frontière IA n’est pas qualifiée. Graphify et Ponytail restent optionnels ; le catalogue public-apis est une veille, pas un service.

## Installer et vérifier

```powershell
./scripts/Invoke-ClusterFoundation.ps1 -Action install_hermes_tools
./scripts/Invoke-ClusterFoundation.ps1 -Action verify_hermes_tools
```

Ces commandes s’exécutent sur le contrôleur d’administration existant et déploient sur la cible K3s désignée. Le runtime ne peut pas modifier le catalogue monté en lecture seule. NPM utilise son lock avec intégrités et sans scripts lifecycle ; Python exige les hashes et des wheels. Le binaire RTK est vérifié par SHA256. La réapplication Hermes conserve outils et MCP documentaires.

Une mise à jour de catalogue arrête Hermes de façon contrôlée, attend la disparition de son Pod, réinstalle sur le PVC RWOP puis rétablit une seule instance. Ce parcours a été exécuté pour corriger le chargement UTF-8 des instructions. Un échec laisse le propriétaire arrêté et exige inspection/reprise du Job, sans second writer. Le rebuild neuf doit installer le volume d’outils avant d’activer son montage dans Hermes. Cette orchestration complète reste une gate de release, pas une recette déjà réussie.

## Correction du poste et livraison

`Uninstall-WorkstationTools.ps1` a supprimé les anciennes installations utilisateur ArcIA-Builder et leur enregistrement MCP Codex, après sauvegarde protégée de la configuration. Les autres paramètres Codex et les runtimes d’administration préexistants sont conservés. Les anciennes commandes d’installation locale sont désactivées. Le compte/runtime ACME WSL reste temporairement nécessaire à la reprise du certificat jusqu’à sa migration protégée ; Certbot est également installé dans K3s.

GitHub : dépôt privé `nicolastheuil/arcia-harness`, livraison directe sur **main**, sans nouvelle branche ni PR. Les sources génériques, locks et preuves assainies sont versionnés ; les scripts de debug privés et inventaires ne le sont pas. La CI ne reçoit aucun secret ni accès entreprise. [Handoff et preuves](handoff-2026-10-12-documentation-multivecteur.md).
