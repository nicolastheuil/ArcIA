# ArcIA — plateforme IA agentique d’entreprise

**ArcIA réunit des agents Hermes, une connaissance documentaire privée et des outils contrôlés dans une plateforme réutilisable.** `arcia-harness` contient le code générique, le bootstrap et les procédures d’exploitation. Les usages, corpus, comptes, domaines et connecteurs d’une organisation appartiennent à son dépôt d’instance ; sa configuration sensible reste chiffrée, avec des clés externes.

→ [Périmètre et principes](docs/guides/plateforme-arcia.md) · [Contrat complet](docs/plan-integration-hermes.md)

## État du projet

Le socle est **déployé et partiellement vérifié en qualification**, sur trois VM Debian/K3s dans VMware avec stockage partagé. Les essais documentaires et d’isolation utilisent des fixtures synthétiques. **La release installable reste à qualifier** : reconstruction sur cluster neuf, sauvegarde/restauration complète, panne brutale et fencing sont encore ouverts.

| Domaine | Disponible | Limites principales |
|---|---|---|
| Agents | Hermes, dashboard, mémoire personnelle, délégation et outils | Un seul écrivain par état ; launcher de missions et kill switch à construire |
| Identité | Keycloak local permanent, administration, portail personnel et SSO optionnel | Login Microsoft constaté sur le pilote ; groupes, restore, HA et recette SSO complète à qualifier |
| Connaissance | RAG privé, PostgreSQL/pgvector, recherche hybride et reclassement multi-vecteur | Corpus synthétique ; OCR, import général, collecte et benchmark large à compléter |
| Confidentialité | Presidio local, relais authentifié, OpenRouter gratuit/ZDR ; agents sans Internet direct | Détection imparfaite ; formats opaques refusés ; aucune route payante autorisée |
| Outillage | Catalogue local de skills, RTK et Headroom ; outils dans K3s | Context7 externe fermé ; OmniRoute automatique différé |
| Infrastructure | K3s/etcd, CPI/CSI, CNPG, HTTPS et bascule contrôlée | Support des versions, fencing, reprise et renouvellement TLS automatique à terminer |
| Intégrations | Contrat Microsoft 365 hors ligne et extension par MCP | Bot Teams, Graph métier, coffres, VPN et approbations serveur à développer |

« Codé », « déployé » et « vérifié » désignent des résultats distincts. Les chiffres et preuves sont datés ; ils ne constituent pas une surveillance en temps réel.

→ [État courant et prochaine reprise](docs/etat-reprise.md) · [Backlog](docs/backlog.md) · [Recette et gates de release](docs/runbooks/recette-fondatrice.md)

## Architecture et parcours d’une demande

```mermaid
flowchart LR
  U[Utilisateur] --> I[HTTPS, Keycloak et portail]
  I --> H[Hermes : espace personnel]
  H --> K[Knowledge : MCP et droits documentaires]
  K --> D[PostgreSQL, index et originaux privés]
  H --> T[Skills et outils autorisés]
  H --> P[Presidio et politique de sortie]
  P --> R[Relais authentifié]
  R --> M[OpenRouter gratuit et ZDR]
```

Les services imposent les droits avant recherche, téléchargement et appel d’outil. Les documents et résultats d’outils sont des données non fiables. Les agents délégués restent dans un périmètre borné. Hermes conserve son état sur un volume exclusif ; PostgreSQL réplique ses données indépendamment du quorum K3s. Les outils applicatifs tournent dans le cluster ; le poste porte le contrôleur d’administration protégé.

→ [Architecture réelle et carte des composants](docs/architecture.md) · [Schémas détaillés, présent et cible](docs/schemas-plateforme-hermes.md)

## Utilisateurs, espaces et partage

Les comptes locaux Keycloak sont permanents. `/admin/users` administre les utilisateurs, `/account` leur compte et `/portal/` attribue un espace vide au premier login autorisé par `ArcIA.User`. L’identité stable est `(issuer, subject)` ; conversations, état, outils et connexions restent personnels. Le pool est borné : huit places par défaut dans le harness, configuration distincte dans chaque instance. Une suppression de compte ne réaffecte pas automatiquement ses volumes.

Le RAG permet la lecture commune et personnelle avec contrôle serveur. Les ACL dynamiques de groupes restent à développer. Entra ID et les autres SSO s’ajoutent par brokering ; les comptes locaux restent disponibles.

→ [Comptes, portail et SSO](docs/guides/identite-utilisateurs.md) · [Partage et cloisonnement](docs/guides/plateforme-arcia.md#partage-et-cloisonnement) · [Recette multi-utilisateur](docs/guides/multi-utilisateur.md)

## Connaissance documentaire et connecteurs

L’ingestion locale conserve les originaux, empreintes, versions, provenance et périmètres. PDF textuels, texte/Markdown, OpenAPI, JSON Schema et schémas éditables alimentent la recherche. PostgreSQL full-text et vecteurs E5 produisent les candidats ; RRF puis MaxSim/mLateOn les classent. La réponse restitue les extraits autorisés avec leurs références. OCR et compréhension visuelle avancée restent différés.

Les MCP consultent des sources vivantes ou exposent des outils bornés ; le RAG indexe un corpus sélectionné. Chaque nouveau connecteur fixe version, destinations, outils, identité protégée et recette. Microsoft 365 dispose d’un contrat d’instance et d’une annexe administrateur ; ses services métier restent à construire.

→ [Formats, ingestion, recherche et API](docs/guides/connaissance-documentaire.md) · [Guide des connecteurs MCP](docs/guides/connecteurs-mcp.md) · [Annexe Microsoft 365](docs/annexes/integration-microsoft365.md)

## Modèles, confidentialité et sécurité

Les appels cloud passent par **Presidio → relais authentifié → OpenRouter**. Hermes ne reçoit aucune clé fournisseur et n’a ni Internet direct ni DNS général. La route de qualification impose gratuité, ZDR et collecte interdite ; une indisponibilité provoque un refus. OmniRoute est installé, son routage automatique et tout repli payant restent différés. RTK et Headroom réduisent le contexte ; la confidentialité repose sur les contrôles dédiés.

DPAPI/ACL protège les entrées administratives du poste. Secrets, kubeconfigs et inventaires privés ne sont jamais transmis au modèle. Les actions externes sensibles exigent un plan et une approbation serveur ; l’intégration Teams correspondante reste à implémenter. La réplication et le stockage partagé doivent être complétés par des sauvegardes cohérentes.

→ [Politique cloud et limites](docs/guides/confidentialite-cloud.md) · [Frontières et preuves de sécurité](docs/guides/securisation-plateforme-donnees.md) · [Politique de sécurité](docs/guides/securite.md)

## Skills, outils et versions

Le catalogue local contient 539 entrées upstream Hermes/ECC/Superpowers, 58 skills Hermes embarquées exposées au chargeur et sept adaptations/orientations ArcIA. Les instructions sont chargées à la demande ; chaque procédure garde ses dépendances et ses limites. Hermes porte la mémoire et la délégation. Vercel skills sert à la découverte/import d’ingénierie ; LintLang analyse les instructions.

RTK raccourcit automatiquement `git log` simple. Headroom réduit les gros résultats JSON de lectures déclarées avec récupération de l’original dans un cache personnel borné. Context7 externe reste fermé jusqu’à qualification de son adaptateur filtrant.

→ [Catalogue et mises à jour](docs/guides/skills.md) · [Tokenmaxing et mesures](docs/guides/tokenmaxing.md) · [Outillage et administration](docs/guides/outillage-builder.md) · [Versions et support](docs/guides/versions-officielles.md) · [Lock](versions.lock.yaml) · [Crédits et licences](THIRD_PARTY_NOTICES.md)

## Installer, exploiter et reprendre

Le point d’entrée est `scripts/Bootstrap-Harness.ps1`, piloté par les 56 étapes de `bootstrap/qualification.json`. **Fresh** prépare une cible vierge désignée ; **Reconcile** réapplique la cible possédée en préservant identités et volumes ; **Verify** exécute les recettes ; **Audit** inspecte. Le bootstrap vérifie les résultats de l’exécution courante, journalise sous protection et s’arrête à la première erreur.

```powershell
# Découvrir le parcours sans déploiement
./scripts/Bootstrap-Harness.ps1 -Mode Plan -Profile Fresh -ProvisionVMs
```

Avant Apply, enregistrer les accès, endpoints, DNS et secrets dans les programmes locaux protégés. La cible d’exploitation est K3s/VMware ; Compose/Kilo restent des options de laboratoire. Un transfert du poste administratif conserve des bundles protégés ; le restore des bases et volumes suit une procédure distincte.

→ [Bootstrap : prérequis, modes et reprise](docs/runbooks/bootstrap.md) · [Installation K3s/Codex](docs/installation-k3s-codex.md) · [Exploitation](docs/runbooks/exploitation-qualification.md) · [Certificats](docs/runbooks/certificats-dns.md) · [Sauvegarde/reconstruction](docs/runbooks/sauvegarde-reconstruction.md) · [Transfert de poste](docs/runbooks/transfert-second-pc.md)

## Carte du dépôt et contribution

| Chemin | Responsabilité |
|---|---|
| [`services/`](services/) | Services identité/portail, connaissance, confidentialité, isolation et skills |
| [`scripts/`](scripts/) | Contrôleur PowerShell protégé, CLI Python, renderers, workers et sondes |
| [`bootstrap/`](bootstrap/) | Parcours de qualification et locks de contrats |
| [`infra/`](infra/) | Ansible Debian/K3s, image et spécification VMware |
| [`deploy/`](deploy/README.md) | Fondations statiques, manifests fournisseurs et skills embarquées |
| [`builder/`](builder/role.md) | Rôle d’ingénierie, catalogue, dépendances et licences d’outillage |
| [`schemas/`](schemas/) / [`examples/`](examples/) | Contrats de configuration et fixtures synthétiques |
| [`tests/`](tests/) / [`validation/`](validation/) / [`.github/workflows/`](.github/workflows/) | Tests de frontières, validation des sources, liens et schémas, CI |
| [`docs/`](docs/README.md) | Références, guides, runbooks, ADR, preuves et archives historiques |
| `versions.lock.yaml` / `requirements*` | Versions, digests et dépendances fixées |

Les répertoires locaux `secrets/`, `artifacts/`, les environnements virtuels et caches sont ignorés par Git. Ils ne font pas partie du dépôt GitHub.

Lire [AGENTS.md](AGENTS.md) avant toute modification. Les livraisons vont sur `main`. Chaque évolution technique actualise bootstrap, locks, couverture, runbooks et état de reprise. Un seul état de reprise est maintenu ; les anciens handoffs restent dans les archives et ne définissent pas la cible courante.

→ [Organisation, règles documentaires et validation locale](docs/organisation.md) · [Index complet de documentation](docs/README.md) · [Décisions ADR](docs/README.md#decisions) · [Travaux restants](docs/backlog.md)
