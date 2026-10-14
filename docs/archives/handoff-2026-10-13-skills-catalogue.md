# Reprise ArcIA — catalogue de skills et fonctions sans doublons

> Archive historique. Pour la reprise actuelle, lire [l’état courant](../etat-reprise.md).

Date : 13 octobre 2026. Livraison directe sur main ; aucun outil applicatif sur le
poste. Les customs d'organisation restent dans leur dépôt d'instance.

## Décision et implémentation

Après comparaison des options, catalogue complet local : 539 entrées upstream
(Hermes 212, ECC 311, Superpowers 15, Vercel 1), sources immuables et fichiers
textuels avec SHA256, licences et crédits par entrée. Sept skills ArcIA natives,
dont l'orientation ; 58 skills Hermes embarquées exposées nativement. MCP stdio
`arcia_skills` fournit recherche/lecture/sources sans réseau, écriture ou secret.

Hermes possède déjà un Hub et une source skills.sh : le CLI Vercel reste un outil
d'ingénierie, pas un second installateur autonome dans les conversations. Le
plugin natif readonly `arcia-platform` ajoute l'orientation de découverte à chaque
nouvelle session. Mémoire et délégation restent Hermes ; ni apprentissage/mémoire
ECC, ni orchestrateur/launcher supplémentaire ne sont activés.

RTK et Headroom ont montré des réductions distinctes sur fixtures : journal Git
3 169 → 1 670 octets ; messages avec JSON d'événements 14 252 → 7 402 octets,
marqueur critique conservé. RTK git status n'a pas réduit la fixture. Le hook RTK
automatique est limité aux git log simples ; Headroom fournit un outil natif de
lecture compressée de JSON dans le workspace personnel, sans proxy global,
mémoire partagée ou clés dans le sous-processus. Les originaux restent disponibles.

Le hook natif `transform_tool_result` étend Headroom aux gros résultats JSON de
lectures déclarées, avant entrée en contexte. `read_file` est la politique par
défaut ; le cache privé RAM est borné à 32 entrées/4 Mio et références de 5 minutes,
avec récupération exacte/paginée. RAG/citations, skills, erreurs, écritures et
outils non déclarés sont exclus. Les nouveaux MCP devront être qualifiés avant
ajout à cette politique. Aucun nouveau fournisseur ou budget n'est activé.

Le README présente une ligne par outil, par catégories. Voir [skills](../guides/skills.md),
[tokenmaxing et fonctions écartées](../guides/tokenmaxing.md),
[ADR 0014](../adr/0014-catalogue-skills-et-responsabilites.md) et
[crédits/licences](../../THIRD_PARTY_NOTICES.md).

## Bootstrap et mises à jour

Manifeste toujours à 43 étapes, avec couverture explicite de skills_catalog et
du service skills. Le contrat lie les locks aux étapes d'installation outils,
second runtime et vérification. Job d'installation contrôlé, montages readonly,
révisions préservées et contrôle d'ownership. La recette multi-utilisateur inclut
les sondes d'outillage de chacun des deux runtimes.

`refresh_skills_catalog.py` vérifie ou prépare des locks candidats ; `--latest`
ne déploie rien. Un workflow GitHub manuel inspecte les candidats upstream sans
écriture Git ni accès privé. Promotion = revue, tests, bootstrap et recette.

## Vérification exécutée et état de livraison

**151 tests Linux réussis**, dont 22 tests ajoutés de catalogue, plugin, migration,
chemins, compression et cache. Validation sources/locks/couverture bootstrap et
gardes PowerShell réussies. [CI verte sur le code qualifié](https://github.com/nicolastheuil/arcia-harness/actions/runs/38369447167).

**55 contrôles d'outillage réussis par runtime**, incluant l'intégrité des 539
instructions, MCP, crédits/licences, chargeur natif, plugin réel, orientation,
hook RTK, outil Headroom, réduction automatique avant contexte, original exact
récupérable, refus d'une référence inconnue, référence préservée après Presidio,
exclusions RAG/écritures et digest correspondant au catalogue courant.

**200 contrôles multi-utilisateur réussis** : les 90 contrôles d'isolation et de
corpus précédents, plus les 55 sondes d'outillage de chacun des deux runtimes.
Les autres recettes conservent leurs 25 contrôles Knowledge et 15 Privacy.
Les installations/réapplications d'outillage et du second runtime ont réussi ;
un **Bootstrap Verify complet de 7 étapes** a réussi sur la révision publiée
`ae07bd0a109a29b6c6a96df882e07b9c7965f8eb`.
[Preuves assainies](../qualification/2026-10-13-skills.json).

L'extension de la recette a révélé une sonde d'outillage qui recherchait le guide
privé de A depuis B. Le refus était correct ; la sonde commune utilise désormais
la fixture `1-COMMON`, sans élargir les droits. Les refus croisés restent testés.
La préparation/merge de configuration se fait dans le contrôleur protégé, avec
contrôle de dérive, pour permettre la reprise quand le propriétaire est arrêté.

## Limites conservées

Une skill cataloguée n'est pas une mission ni un script individuellement qualifié.
Les dépendances, accès externes et permissions ne sont pas installés à sa lecture.
La sélection par le modèle reste variable ; les recettes déterministes prouvent
les interfaces, hooks et refus, pas le meilleur choix sur chaque demande.
Les sorties Headroom sont une vue avec perte, pas une preuve exhaustive.
Le miroir couvre les racines retenues, pas tout GitHub/skills.sh. Les traductions
et copies ECC par agent ne sont pas des compétences supplémentaires.

Le pilote reste synthétique et gratuit. SSO/groupes, restauration complète,
rebuild neuf, panne brutale/fencing et renouvellement DNS automatisé restent des
gates de production ; ce lot ne les déclare pas réalisés. État privé et diagnostics
sous DPAPI/ACL ; ne pas lire les scripts de debug non suivis ou afficher les bundles.
