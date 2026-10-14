# Outillage d’ArcIA : rôle, installation K3s et GitHub

La décision actuelle remplace l’ancien placement sur le poste : **les outils sont installés dans l’instance Hermes du cluster K3s**. Le nom historique `builder/` désigne désormais les locks et le catalogue de fabrication, sans autoriser une installation locale.

## Emplacement et versions

Namespace `arcia-hermes`, PVC `hermes-tools` 10 Gi RWOP, monté à `/opt/arcia-tools` en lecture seule dans Hermes. Le Job d’installation utilise la même image Hermes fixée par digest, UID 10000, sans token Kubernetes. Il est supprimé avant de rattacher le PVC au runtime. Les versions et intégrités sont dans [tools.lock.json](../../builder/tools.lock.json), [NPM lock](../../builder/npm/package-lock.json), [Python lock](../../builder/requirements-tools.lock.txt) et [catalogue](../../builder/catalog.lock.json).

| Outil | Version | Chemin / usage |
|---|---|---|
| Context7 | 4.3.0 | `/opt/arcia-tools/bin/context7`, MCP natif |
| skills | 1.7.2 | `/opt/arcia-tools/bin/skills`, catalogue revu |
| LintLang | 0.8.2 | `/opt/arcia-tools/bin/lintlang`, rapport |
| RTK | 0.51.0 | `/opt/arcia-tools/bin/rtk`, invocation explicite |
| Headroom | 0.40.0 | Outil natif `arcia_compress_json_file`, SDK dans Python isolé |
| OmniRoute | 3.8.51 | `node /opt/arcia-tools/npm/node_modules/omniroute/bin/omniroute.mjs` |
| Certbot | 5.8.0 | `/opt/arcia-tools/bin/certbot` |

Sources : [RTK](https://github.com/rtk-ai/rtk), [Headroom](https://github.com/headroomlabs-ai/headroom), [OmniRoute](https://github.com/diegosouzapw/OmniRoute), [Context7](https://github.com/upstash/context7), [skills](https://github.com/vercel-labs/skills), [LintLang](https://github.com/hermes-labs-ai/lintlang). Les sources Superpowers/ECC et licences sont conservées dans [le catalogue de licences](../../builder/licenses/README.md).

Les six adaptations initiales et l'orientation `arcia-skills` sont versionnées sous `deploy/hermes/skills`. Le catalogue complet ajoute 539 entrées upstream recherchables localement, avec crédits et licences par entrée ; les 58 skills embarquées Hermes sont aussi exposées au chargeur natif. Un plugin ArcIA natif guide la découverte, borne RTK et fournit la lecture compressée de JSON Headroom. Aucun hook de pack, export de sessions ou apprentissage ECC/Headroom n'est activé. [Fonctionnement et mises à jour](skills.md) · [Crédits et licences](../../THIRD_PARTY_NOTICES.md).

## Réseau et activation

Hermes accède au DNS statique privé, à Knowledge et à la passerelle Presidio. Les requêtes Context7 externes sont désormais refusées : leur adaptateur filtrant reste à qualifier. Hermes n’a ni Internet direct, ni clé fournisseur, ni identifiants PostgreSQL ; il dispose seulement d’un token de passerelle et de lecture documentaire. [Confidentialité cloud](confidentialite-cloud.md).

RTK réécrit automatiquement seulement les commandes `git log` simples ; les formats structurés, écritures et shells composés restent inchangés. Headroom réduit automatiquement les gros résultats JSON des lectures déclarées avant entrée en contexte, avec original privé récupérable ; `arcia_compress_json_file` reste disponible pour les JSON du workspace. Aucun proxy global ni mémoire partagée. Hermes conserve la mémoire personnelle et la compaction de l'historique. [Mesures, choix et limites](tokenmaxing.md). Le CLI OmniRoute est installé et vérifié dans les outils. Son serveur de gestion LAN dispose maintenant de son bootstrap distinct ; le raccordement d’inférence générique et les fournisseurs personnels restent à intégrer/qualifier. [Configuration OmniRoute](omniroute.md). Graphify et Ponytail restent optionnels ; le catalogue public-apis est une veille, pas un service.

## Installer et vérifier

```powershell
./scripts/Invoke-ClusterFoundation.ps1 -Action install_hermes_tools
./scripts/Invoke-ClusterFoundation.ps1 -Action verify_hermes_tools
```

Ces commandes s’exécutent sur le contrôleur d’administration existant et déploient sur la cible K3s désignée. Le runtime ne peut pas modifier le catalogue monté en lecture seule. NPM utilise son lock avec intégrités et sans scripts lifecycle ; Python exige les hashes et des wheels. Le binaire RTK est vérifié par SHA256. La réapplication Hermes conserve outils et MCP documentaires.

Une mise à jour de catalogue arrête Hermes de façon contrôlée, attend la disparition de son Pod, réinstalle sur le PVC RWOP puis rétablit une seule instance. Ce parcours a été exécuté pour corriger le chargement UTF-8 des instructions. Un échec laisse le propriétaire arrêté et exige inspection/reprise du Job, sans second writer. Le rebuild neuf doit installer le volume d’outils avant d’activer son montage dans Hermes. Le bootstrap orchestre maintenant ce parcours et sa réconciliation sur la cible existante ; le rebuild neuf demeure une gate de release.

## Correction du poste et livraison

`Uninstall-WorkstationTools.ps1` a supprimé les anciennes installations utilisateur ArcIA-Builder et leur enregistrement MCP Codex, après sauvegarde protégée de la configuration. Les autres paramètres Codex et les runtimes d’administration préexistants sont conservés. Les anciennes commandes d’installation locale sont désactivées. Le compte/runtime ACME WSL reste temporairement nécessaire à la reprise du certificat jusqu’à sa migration protégée ; Certbot est également installé dans K3s.

GitHub : dépôt `nicolastheuil/ArcIA`, livraison directe sur **main**, sans nouvelle branche ni PR. Les sources génériques, locks et preuves assainies sont versionnés ; les scripts de debug privés et inventaires ne le sont pas. La CI ne reçoit aucun secret ni accès entreprise. [Handoff et preuves](../archives/handoff-2026-10-12-arcia-cloud-bootstrap.md).

La présentation par catégories, une ligne par outil, est dans le README. La veille
de catalogue est disponible par script et workflow GitHub manuel
`Check upstream skills candidates` ; elle ne modifie ni Git ni un cluster.
La promotion d'une mise à jour reste une révision du harness suivie de sa recette.
