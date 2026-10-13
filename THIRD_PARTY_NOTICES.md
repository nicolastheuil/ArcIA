# Crédits, sources et licences des composants directs d'ArcIA

ArcIA assemble des projets tiers. Leurs auteurs conservent leurs droits ; les
adaptations du harness ne changent pas leurs licences. Les liens ci-dessous
pointent vers les projets officiels. Les versions réellement retenues sont dans
[versions.lock.yaml](versions.lock.yaml), [tools.lock.json](builder/tools.lock.json)
et les locks propres aux services. Une licence compatible ne prouve ni une
qualification technique ni la conformité d'une future redistribution.

## Skills

| Projet et GitHub | Crédits | Licence / référence |
|---|---|---|
| [Hermes skills](https://github.com/NousResearch/hermes-agent) | Nous Research et contributeurs Hermes | [MIT racine](https://github.com/NousResearch/hermes-agent/blob/818c13be1dc4fd28987e1e881a9408224afd4535/LICENSE) ; exceptions propres aux skills |
| [ECC](https://github.com/affaan-m/ECC) | Affaan Mustafa et contributeurs ECC | [MIT](https://github.com/affaan-m/ECC/blob/b92f181b3b748d1abbc2afd94af6aa7d8c8fca29/LICENSE) ; éventuelles notices de fichiers spécifiques |
| [Superpowers](https://github.com/obra/superpowers) | Jesse Vincent et contributeurs Superpowers | [MIT](https://github.com/obra/superpowers/blob/bb92a77741419a4ab5f06e711a283343f1ada0c3/LICENSE) |
| [Vercel skills CLI et find-skills](https://github.com/vercel-labs/skills) | Vercel Labs et contributeurs | [MIT](https://github.com/vercel-labs/skills/blob/671e8c320810d36fed80fac5f1a2c1bf7e82d812/LICENSE) |
| [LintLang](https://github.com/hermes-labs-ai/lintlang) | Hermes Labs AI et contributeurs | Apache-2.0 ; notice dans la distribution épinglée |

Les crédits, liens et licences de **chaque entrée** sont dans
[skills-index.json](builder/skills-index.json) et restitués par `catalog_load`.
Les fichiers LICENSE des sources et des skills sont conservés dans le miroir.
Les contenus spécialisés hérités d'autres auteurs peuvent avoir leur propre
licence : « projet MIT » ne veut pas dire « chaque fichier du catalogue MIT ».

## Tokenmaxing — contexte et sorties

| Projet et GitHub | Crédits | Licence |
|---|---|---|
| [RTK](https://github.com/rtk-ai/rtk) | RTK et contributeurs | MIT |
| [Headroom](https://github.com/headroomlabs-ai/headroom) | Headroom Labs et contributeurs | Apache-2.0 |

## Model Routing

| Projet et GitHub | Crédits | Licence / statut |
|---|---|---|
| [OmniRoute](https://github.com/diegosouzapw/OmniRoute) | Diego Souza et contributeurs OmniRoute | MIT |
| [OpenRouter](https://openrouter.ai/docs) | OpenRouter | Service externe : conditions fournisseur, pas une licence open source du harness ; aucun dépôt logiciel incorporé |

## Moteur, connaissance et documentation

| Projet et GitHub | Crédits | Licence |
|---|---|---|
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | Nous Research et contributeurs | MIT |
| [Context7](https://github.com/upstash/context7) | Upstash et contributeurs | MIT |
| [PostgreSQL](https://github.com/postgres/postgres) | PostgreSQL Global Development Group | PostgreSQL License |
| [pgvector](https://github.com/pgvector/pgvector) | Andrew Kane et contributeurs | PostgreSQL License |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | Artifex et contributeurs | GNU AGPL-3.0 ou licence commerciale Artifex ; choix à vérifier avant distribution |
| [Sentence Transformers](https://github.com/huggingface/sentence-transformers) | Auteurs et contributeurs Sentence Transformers | Apache-2.0 ; modèles sous leurs propres licences |
| [E5](https://github.com/microsoft/unilm/tree/master/e5) | Microsoft et auteurs E5 | MIT pour le modèle retenu ; voir sa carte et le lock Knowledge |
| [mLateOn](https://huggingface.co/lightonai/mLateOn) | LightOn et auteurs mLateOn | Apache-2.0 pour le modèle retenu ; carte de modèle de référence |

Knowledge, les services de filtrage, le relais et l'adaptateur de catalogue sont du
code du harness. Leur existence ne les transforme pas en produits upstream tiers.

## Confidentialité, entrée et certificats

| Projet et GitHub | Crédits | Licence |
|---|---|---|
| [Presidio](https://github.com/microsoft/presidio) | Microsoft et contributeurs | MIT |
| [spaCy](https://github.com/explosion/spaCy) | Explosion et contributeurs | MIT ; modèles linguistiques selon leurs notices |
| [NGINX](https://github.com/nginx/nginx) | Auteurs et contributeurs NGINX | BSD-2-Clause |
| [Certbot](https://github.com/certbot/certbot) | Electronic Frontier Foundation et contributeurs | Apache-2.0 |

## Infrastructure

| Projet et GitHub | Crédits | Licence |
|---|---|---|
| [K3s](https://github.com/k3s-io/k3s) | Contributeurs K3s | Apache-2.0 |
| [vSphere CSI](https://github.com/kubernetes-sigs/vsphere-csi-driver) | Kubernetes SIGs et contributeurs | Apache-2.0 |
| [vSphere CPI](https://github.com/kubernetes/cloud-provider-vsphere) | Kubernetes et contributeurs | Apache-2.0 |
| [CloudNativePG](https://github.com/cloudnative-pg/cloudnative-pg) | Contributeurs CloudNativePG | Apache-2.0 |
| [Keepalived](https://github.com/acassen/keepalived) | Alexandre Cassen et contributeurs | GPL-2.0 ; consulter les notices des fichiers |

Cette page couvre les composants directs présentés par ArcIA. Les distributions
conservent aussi les licences de leurs dépendances. Elle ne remplace pas un SBOM
complet ni la revue juridique d'une release. Les versions verrouillées et leurs
notices font foi, plutôt que la licence d'une branche upstream qui évolue.
