# Tokenmaxing : choix, mesures et intégration dans Hermes

Le harness distingue trois fonctions. **Hermes conserve la gestion et la
compaction de l'historique. RTK réduit certaines sorties CLI. Headroom produit
une vue réduite d'un fichier JSON avant que son contenu arrive au modèle.**
Ces fonctions ne remplacent pas Presidio ni les droits d'accès.

## Vérifications du 13 octobre 2026

Mesures exécutées dans Hermes/K3s, sans appel modèle, sur fixtures synthétiques :

| Scénario | Original | Résultat | Observation |
|---|---:|---:|---|
| RTK, git status avec 120 fichiers non suivis | 2 474 octets | 2 475 octets | Aucun gain sur cette fixture |
| RTK, journal de 15 commits | 3 169 octets | 1 670 octets | Réduction de 47,3 %, sujet du dernier commit conservé |
| Headroom, messages comprenant 150 événements JSON | 14 252 octets | 7 402 octets | Réduction de 48,1 %, marqueur FATAL synthétique conservé |

Ces chiffres concernent des **octets sur ces fixtures**, pas une facture, un
nombre exact de tokens ni une garantie d'exhaustivité. La conservation d'un
marqueur ne démontre pas l'équivalence de toutes les réponses possibles.
Le modèle `gpt-4o` utilisé par le SDK Headroom dans la mesure sélectionne le
comptage/format de compression ; aucun modèle OpenAI n'a été appelé.

## RTK retenu, automatisation bornée

RTK apporte une réduction démontrée sur le journal Git ; il n'est donc pas retiré.
Le plugin natif ArcIA réécrit automatiquement **seulement `git log ...` simple**
vers RTK. Il conserve les arguments de travail d'Hermes. Les commandes shell
composées, substitutions, écritures, formats `--oneline`/`--format`/`--pretty`,
diffs et sorties structurées restent inchangés. Les autres filtres RTK demeurent
accessibles explicitement, sans être annoncés comme automatiquement qualifiés.

`git --no-pager log ...` fournit un chemin brut sans réécriture ; les originaux
restent récupérables. Le hook n'active ni accès supplémentaire ni hook upstream
global. Il s'agit d'une intégration native du harness testée sur la version fixée,
pas de l'exécution de `rtk init` sur tous les profils.

## Headroom retenu pour la lecture préalable de JSON

Headroom a produit une réduction utile sur la fixture structurée ; le supprimer
comme « inutile » serait contredit par cette mesure. Son proxy global, ses
wrappers d'agents, mémoire partagée et apprentissage ne sont en revanche **pas
retenus** : ils recouvriraient des fonctions gérées par Hermes et augmenteraient
les frontières à qualifier.

L'outil natif `arcia_compress_json_file` lit un fichier JSON de
`/opt/data/workspace` avant que l'agent en demande le contenu complet. Il retourne
une vue potentiellement réduite, l'empreinte et le chemin de l'original. Fichiers
de plus de 512 Kio, chemins hors workspace, liens sortants et contenus non JSON
sont refusés ; les petits fichiers restent intacts. La compression s'exécute
localement dans un sous-processus sans clés fournisseur ou session. Son état
temporaire est détruit à la fin ; l'original demeure dans le workspace personnel.

Ce mécanisme évite le défaut d'une compression demandée après avoir envoyé tout
le fichier au modèle. Il ne compresse pas automatiquement tous les résultats MCP,
citations RAG, contrats ou historiques. Pour un décompte exact, une citation, une
preuve ou un détail absent, l'agent doit lire l'original avec ses outils habituels.
Un échec produit un refus de l'outil ; le fichier original reste disponible.

## Fonctions concurrentes non retenues

| Fonction | Choix du harness | Alternative non activée et justification |
|---|---|---|
| Mémoire personnelle/profil | Hermes natif, runtime/PVC propre | ECC learning/instincts/unified-memory : second système de mémoire et exports inutiles au socle actuel |
| Connaissance commune | RAG sous ACL | Mémoire globale de conversations : incompatible avec le cloisonnement attendu |
| Historique/contexte | Hermes natif | Headroom proxy et wrapper global : pas de second gestionnaire automatique de tout le contexte |
| Délégation | Hermes natif | Orchestrateurs et launchers ECC/Superpowers : doublons non installés |
| Découverte des skills | Miroir local et chargeur natif | Installations concurrentes Hub/Vercel depuis les conversations : versions et sorties non maîtrisées |
| Routage | Passerelle ArcIA filtrée | Routage Headroom non activé ; OmniRoute demeure une cible distincte à qualifier |

Les contenus de skills restent consultables ; aucun package/plugin ECC ou
Superpowers complet n'est déployé. Les fonctions écartées n'étaient pas des
services actifs à désinstaller. Les deux binaires RTK/Headroom sont conservés
parce que les tests montrent une utilité distincte et que leur usage est borné.

[RTK, MIT](https://github.com/rtk-ai/rtk) ·
[Headroom, Apache-2.0](https://github.com/headroomlabs-ai/headroom) ·
[Crédits et licences](../THIRD_PARTY_NOTICES.md) ·
[Décision générale](adr/0014-catalogue-skills-et-responsabilites.md).
