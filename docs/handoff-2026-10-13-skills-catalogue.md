# Reprise ArcIA — catalogue de skills et fonctions sans doublons

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

Le README présente une ligne par outil, par catégories. Voir [skills](skills.md),
[tokenmaxing et fonctions écartées](tokenmaxing.md),
[ADR 0014](adr/0014-catalogue-skills-et-responsabilites.md) et
[crédits/licences](../THIRD_PARTY_NOTICES.md).

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

142 tests Linux réussis, dont 13 tests de catalogue/plugin/chemins et contrats ;
validation sources/locks/couverture bootstrap et gardes PowerShell réussies.
47 contrôles d'outillage réussis dans le premier runtime : catalogue, MCP,
intégrité des 539 instructions, provenance/licences, chargeur natif, plugin réel,
orientation, hook RTK et outil Headroom, original accessible et configuration
privée refusée. Les résultats finaux des deux runtimes et de Verify sont ajoutés
dans ce fichier après leur exécution ; ne pas déduire leur réussite de ce paragraphe.

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
