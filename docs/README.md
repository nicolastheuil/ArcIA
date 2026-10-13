# Documentation d’ArcIA

Référence opérationnelle : **12 octobre 2026**. Le [README principal](../README.md)
présente l’essentiel. Les documents ci-dessous expliquent le fonctionnement,
les procédures et leurs limites. [L’état de reprise](etat-reprise.md) désigne
le handoff courant ; les anciens handoffs restent des instantanés historiques.

## Parcours de lecture

| Besoin | Documentation complète |
|---|---|
| Comprendre la plateforme et son périmètre | [Philosophie ArcIA](plateforme-arcia.md) |
| Ajouter des sources et outils | [Connecteurs MCP](connecteurs-mcp.md) |
| Protéger les appels modèles | [Confidentialité cloud](confidentialite-cloud.md) |
| Installer et réconcilier automatiquement | [Bootstrap exhaustif](runbooks/bootstrap.md) |
| Comprendre le socle et trouver le code | [Architecture réelle](architecture.md) |
| Visualiser flux actuels et futurs | [Schémas explicatifs](schemas-plateforme-hermes.md) |
| Connaître les protections | [Sécurisation de la plateforme et des données](securisation-plateforme-donnees.md), [politique de sécurité](securite.md) |
| Partager les données et séparer les utilisateurs | [Qualification multi-utilisateur](multi-utilisateur.md) |
| Comprendre PostgreSQL, pgvector et les PDF | [Connaissance documentaire](connaissance-documentaire.md) |
| Installer une nouvelle cible | [Guide K3s/Codex](installation-k3s-codex.md), [préparation](runbooks/preparer-deploiement.md), [VMware](runbooks/vcenter.md) |
| Exploiter le pilote existant | [Exploitation de qualification](runbooks/exploitation-qualification.md) |
| Reprendre les certificats | [DNS et Certbot](runbooks/certificats-dns.md) |
| Évaluer les preuves | [Recette fondatrice](runbooks/recette-fondatrice.md), [rapport de vérification](verification-preparation.md) |
| Sauvegarder ou transférer | [Sauvegarde/reconstruction](runbooks/sauvegarde-reconstruction.md), [second PC](runbooks/transfert-second-pc.md) |
| Installer/utiliser l’outillage et GitHub | [Outillage Hermes/K3s](outillage-builder.md) |
| Reprendre les travaux | [Handoff courant](handoff-2026-10-12-arcia-cloud-bootstrap.md), [backlog](backlog.md) |
| Vérifier versions et support | [Versions officielles](versions-officielles.md), [lock](../versions.lock.yaml) |

## Sources de cadrage

[AGENTS.md](../AGENTS.md), le [plan intégral](plan-integration-hermes.md),
le [guide d’installation](installation-k3s-codex.md) et les
[schémas](schemas-plateforme-hermes.md) sont les entrées du builder.
Le plan définit la plateforme complète ; son arborescence de services et sa CLI
`hermes-platform` constituent des contrats à implémenter. La CLI actuelle est
`scripts/harness.py`, complétée par les wrappers PowerShell.

**Proposé** désigne une décision cible ; **codé** un artefact présent ;
**déployé** une application sur les cibles désignées ; **vérifié** un scénario
effectivement exécuté avec une preuve. Une spécification n’est pas une preuve.

<a id="decisions"></a>
## Décisions

| ADR | Sujet |
|---|---|
| [0001](adr/0001-cible-et-limites.md) | Cible et limites |
| [0002](adr/0002-secrets-et-configuration.md) | Secrets et configuration |
| [0003](adr/0003-bootstrap-k3s-et-stockage.md) | Bootstrap et stockage |
| [0004](adr/0004-vcenter-et-image-debian.md) | VMware et image Debian |
| [0005](adr/0005-verification-ssh-hors-bande.md) | Confiance SSH hors bande |
| [0006](adr/0006-reseaux-evolutifs-et-fondations.md) | Réseaux connus et futurs VPN |
| [0007](adr/0007-vip-et-bootstrap-synthetique.md) | VIP et qualification synthétique |
| [0008](adr/0008-qualification-applicative-et-tls.md) | État applicatif, entrée et TLS différé |
| [0009](adr/0009-connaissance-hybride-multivecteur.md) | Recherche documentaire, API et schémas |
| [0010](adr/0010-outils-hermes-main-et-acces.md) | Placement K3s, main et accès dashboard |
| [0011](adr/0011-bootstrap-exhaustif.md) | Bootstrap exhaustif et contrôlé |
| [0012](adr/0012-arcia-generique-et-confidentialite.md) | Périmètre ArcIA, instances et cloud gratuit filtré |
| [0013](adr/0013-qualification-multi-utilisateur.md) | Runtimes personnels, RLS commun/personnel et révocation locale |

## Historique et maintenance

Le [handoff du 11 octobre](handoff-2026-10-11.md) et le
[premier arrêt du 12 octobre](handoff-2026-10-12-socle-qualification.md) sont
historiques. Leurs échecs K3s/NGINX ont été corrigés.
À chaque lot, actualiser recette, backlog et état de reprise, puis architecture
et runbooks si nécessaire. Garder les preuves détaillées privées et publier
seulement leurs résultats assainis. Une évolution de version exige le lock,
les artefacts correspondants et une qualification proportionnée.

- [Multi-utilisateur : espaces locaux, corpus commun et recette](multi-utilisateur.md).

- [Sécurisation de la plateforme et des données](securisation-plateforme-donnees.md) : frontières, contrôles, preuves et limites.

## Skills, choix d’outillage et crédits

- [Skills natifs, ECC, Superpowers et Vercel : fonctionnement et mises à jour](skills.md).
- [Tokenmaxing : mesures RTK/Headroom et fonctions concurrentes écartées](tokenmaxing.md).
- [ADR 0014 : catalogue complet local et responsables des fonctions](adr/0014-catalogue-skills-et-responsabilites.md).
- [Crédits, GitHub et licences par outil](../THIRD_PARTY_NOTICES.md).
