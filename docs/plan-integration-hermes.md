# ArcIA — contrat intégral de plateforme

Révision du 12 octobre 2026. Ce document décrit le **socle générique ArcIA**, distinct des usages et configurations de chaque organisation. Les noms de fichiers historiques contenant « hermes » sont conservés pour la stabilité des liens ; Hermes est un composant d’ArcIA.

Les spécifications d’usage initiales ont été transférées dans l’archive du dépôt d’instance. Elles ne définissent plus le périmètre du harness. [Philosophie et partage](guides/plateforme-arcia.md) · [Architecture déployée](architecture.md) · [État de reprise](etat-reprise.md).

## 1. Finalité et périmètre

Fournir une plateforme IA agentique d’entreprise : agents, outils contrôlés, connaissance privée, exécution locale et accès filtré aux modèles. Une instance peut n’utiliser que la recherche documentaire ou ajouter des connecteurs et workflows spécifiques. Le harness n’impose aucune population métier, fournisseur documentaire ni méthode de travail particulière.

## 2. Fonctionnement

Une session authentifiée obtient un périmètre serveur. Hermes utilise des outils, cherche des sources et délègue des tâches bornées ; les résultats alimentent un contexte assaini. La réponse conserve sources, versions et incertitudes. Les contenus retrouvés ne deviennent pas des instructions d’autorisation. [Schémas](schemas-plateforme-hermes.md).

## 3. Hébergement

Cible actuelle : trois VM Debian sur VMware, serveurs K3s/etcd et stockage partagé vSphere CSI. Docker Compose/Kilo sont des options de laboratoire ou portabilité, pas la cible d’exploitation. Les versions et digests sont fixés dans le lock ; compatibilité/support doivent être qualifiés séparément.

## 4. Source de vérité et dépôts

`ArcIA` contient code générique, automation, manifests, tests synthétiques, ADR et runbooks. Chaque instance a un dépôt distinct pour usages, connecteurs spécifiques, surcharges et références de secrets. Les configurations sensibles sont chiffrées avant Git ; corpus privés et clés externes restent séparés. Une correction manuelle est reportée dans Git avant livraison. Les livraisons actuelles vont sur main selon la décision du propriétaire.

## 5. Données et classification

Distinguer données publiques, synthétiques, privées et confidentielles selon une politique propre à l’instance. Les noms de personnes ne sont qu’un type de donnée sensible : contrats, secrets industriels et agrégats peuvent rester confidentiels sans PII. Le stockage local, la classification et les droits précèdent le filtrage cloud. Le pilote actuel n’autorise que des fixtures synthétiques et les routes de qualification prévues.

## 6. Identité et autorisation

L'identification par défaut utilise des **comptes locaux permanents Keycloak**,
avec portail d'administration `/admin/users` et compte personnel `/account`.
Entra ID et d'autres SSO sont optionnels et peuvent fonctionner en parallèle
via brokering, sans supprimer l'identité locale. La clé stable est `(issuer,
sub)` ; une liaison vérifiée à Entra conserve le même subject. OIDC authentifie ;
propriétaire de runtime, rôles, groupes, périmètre, ressource et action sont
contrôlés côté serveur. Le portail `/portal/` attribue au premier login un
espace vide dans un pool borné, à la clé issuer/subject et sans réaffectation
d'un ancien état. Le rôle `ArcIA.User` est obligatoire. Les ACL de groupes,
fédération réelle et restauration demandent des preuves distinctes.
[Référence identité](guides/portail-webui-entraid.md).

## 7. Partage et cloisonnement

Une connaissance commune peut être accessible à plusieurs utilisateurs habilités, tout en conservant espaces restreints, conversations et connexions personnelles. Recherche, assets, caches, exports et sous-agents respectent le même périmètre. Le service Knowledge actuel impose un périmètre par token et FORCE RLS ; la lecture commun + personnel est qualifiée ; les groupes et ACL d’annuaire restent à développer. [Détails](guides/plateforme-arcia.md#partage-et-cloisonnement).

## 8. Agents et état

Hermes fournit profils, skills, mémoire et délégation. Ces primitives ne constituent pas à elles seules une frontière de sécurité. Un état SQLite a un propriétaire actif unique, PVC RWOP et stratégie Recreate ; aucun HPA sur state.db. La propagation de capacités limitées aux sous-agents et le lancement multi-utilisateur relèvent du harness et nécessitent une recette.

## 9. Outils et connecteurs

MCP expose des outils stdio/HTTP vérifiés et bornés. Les connecteurs propres à une organisation sont définis dans son dépôt d’instance. Permissions, destinations, versions, secrets, filtres de requêtes et résultats sont imposés avant activation. HubSpot/SharePoint sont des exemples d’intégration, pas des services déployés. [Guide MCP](guides/connecteurs-mcp.md).

## 10. Confidentialité et cloud

Tous les appels aux modèles cloud passent par Presidio par défaut, avec détecteurs supplémentaires et relais authentifié. Les modèles Ollama/vLLM internes déclarés par l’entreprise ne passent pas par Presidio par défaut ; identité, droits et destinations restent contrôlés. Tout repli cloud reprend le filtrage. Fournisseurs, modèles, coûts, ZDR, collecte et résidence sont des politiques d’instance. Hermes ne possède pas de clé fournisseur, d’Internet général ni de DNS libre. Les règles serveur ne sont pas modifiables dans un prompt. [Politique complète](guides/confidentialite-presidio.md).

## 11. Routage et coûts

Chaque instance choisit ses routes internes/cloud, fournisseurs, budgets et replis. Le harness impose les droits et la politique de filtrage selon la destination ; un repli ne contourne pas les règles de l’instance.

## 12. Compression et caches

RTK réduit les sorties CLI ; Headroom réduit le contexte. Ils ne sont pas des anonymiseurs. Hermes gère l’historique ; RTK raccourcit automatiquement git log simple et Headroom prévisualise les JSON du workspace. Les mesures et limites sont dans [tokenmaxing](guides/tokenmaxing.md). Toute récupération d’original repasse par droits et filtre avant cloud. Pas de mémoire globale ni apprentissage automatique partagé. Les caches doivent être cloisonnés, bornés et révocables.

## 13. Connaissance documentaire

Le catalogue de compétences et les connaissances de travail sont organisés sous `skills/` avec indexation locale et conformité DLP. [Compétences et documentation](guides/skills.md).

## 14. Recherche hybride et multi-vecteur

PostgreSQL full-text et deux vecteurs E5 par fragment produisent les candidats, fusionnés par RRF. mLateOn reclasse au maximum 30 candidats avec MaxSim de tokens. Les modèles locaux sont fixés à révision/hash, hors ligne et sans remote code. Les gains sur un large corpus et le dimensionnement doivent être mesurés ; une recette synthétique ne constitue pas un benchmark de centaines de PDF.

## 15. Rôle de construction et catalogue

Codex assure le build initial depuis AGENTS.md. Les sources sont versionnées : 539 entrées upstream dans un catalogue local, chargeur natif Hermes et sept adaptations/orientations. Vercel skills complète la découverte/import d’ingénierie. [Fonctionnement](guides/skills.md). Les outils applicatifs sont installés dans K3s ; le poste ne porte que le contrôleur d’administration. [Catalogue et limites](guides/outillage-builder.md).

## 16. Actions externes

Lecture et écriture ont des politiques distinctes. Une action sensible exige plan immuable, périmètre et approbation vérifiés côté serveur, capacité bornée et contrôle d’idempotence. Un redémarrage ne rejoue pas une écriture incertaine. Les canaux d’approbation, coffres, VPN et exécuteurs particuliers sont optionnels par instance ; leurs adaptateurs et leur recette restent à construire.

## 17. Sauvegarde et reconstruction

Git reconstruit le logiciel ; il ne restaure pas spontanément les documents et bases. Préserver séparément état administratif, etcd, PostgreSQL/WAL, SQLite cohérent, corpus et clés de récupération. Chiffrer avant externalisation. Le restore invalide sessions/capacités anciennes et reprend en mode sûr. [Runbook et gates](runbooks/sauvegarde-reconstruction.md).

## 18. Bootstrap exhaustif et évolutif

Le point d’entrée est le script de déploiement universel (`scripts/deploy.py` ou `Deploy-ArcIA.ps1`). Il valide la configuration `arcia.config.yaml`, injecte les secrets et applique les manifests dans l'ordre strict de dépendance. [Procédure](guides/deploiement-universel.md).

## 19. Secrets et administration

DPAPI/ACL sous le compte ingénieur protège l’enrôlement local. Les wrappers transmettent les données privées par stdin et rechiffrent les preuves ; aucun secret au modèle. Les clés SSH sont validées hors bande. Les ressources Kubernetes portent l’identifiant d’opération ; un objet étranger est refusé. Les agents n’ont ni token cluster-admin, ni socket containerd, ni PodSpec arbitraire.

## 20. Réseau et publication

L’API K3s reste privée ; l’entrée HTTPS est stable et Traefik Ingress route les flux avec terminaison TLS Cert-Manager. Les noms sont des entrées privées d’instance, jamais des constantes métier. NetworkPolicies deny-all et allowlists sont appliquées aux workloads. Les MCP externes ont leur propre qualification de sortie.

## 21. Disponibilité et quotas

Quorum etcd et persistance SQLite répondent à des problèmes différents. Trois VM et un stockage partagé ne suffisent pas à déclarer HA. Mesurer perte de nœud, fencing, capacité restante et RPO/RTO. Les workers sans état peuvent être répliqués après qualification ; contexte et tokens ont des limites explicites. Pas de scaling arbitraire des états personnels.

## 22. Recette et statuts

Distinguer proposé, codé, déployé et vérifié. La recette inclut isolation, droits négatifs, confidentialité, restauration, perte de nœud, reprise sans double écriture et reconstruction indépendante. Les preuves détaillées restent protégées ; seuls booléens, codes et compteurs sont publiés. [Matrice historique](archives/recette-fondatrice-2026-10-12.md).

## 23. Livraison

Une livraison du code n’est pas une release de production. Versionner digests, dépendances et modèles, garder bootstrap et docs cohérents, puis vérifier CI et réconciliation. Une release installable complète exige recette et rebuild sur cluster neuf ; ils restent incomplets. Les services factices ne remplacent pas des fonctionnalités absentes.

## 24. Sources officielles

[Hermes](https://github.com/NousResearch/hermes-agent), [K3s HA](https://docs.k3s.io/datastore/ha-embedded), [vSphere CSI](https://github.com/kubernetes-sigs/vsphere-csi-driver), [CNPG](https://cloudnative-pg.io/docs/), [pgvector](https://github.com/pgvector/pgvector), [Presidio](https://microsoft.github.io/presidio/), [OpenRouter routing](https://openrouter.ai/docs/guides/routing/provider-selection). Les locks enregistrent les versions retenues ; une documentation courante n’atteste pas leur compatibilité effective.

## 25. Intégration des outils

Retenir uniquement les composants listés dans les locks et le catalogue revu. Vérifier licences, provenance, hooks, télémétrie, caches et capacité de désactivation. Context7 reste fermé pour les requêtes externes tant que son adaptateur DLP n’est pas qualifié. RTK et Headroom ont des intégrations natives bornées et testables. OmniRoute est le premier routeur du contrat, mode auto administré et portail exclusivement LAN ; raccordement d’inférence et overrides personnels restent à intégrer/qualifier. Les overrides exigent `ArcIA.ProviderSelfService` et un contrôle serveur du propriétaire. Ponytail est intégré en skill de sobriété logicielle (YAGNI). Graphify est intégré en analyseur AST déterministe local (`scripts/arcia_graphify.py`). Public-APIs est qualifié comme référentiel de veille pour l'intégration sécurisée d'APIs tierces ([ADR 0021](adr/0021-evaluation-et-integration-ponytail-graphify-public-apis.md)). La CI vérifie les sources, pas l’activation des fournisseurs. [Configuration OmniRoute](guides/omniroute.md).

## 26. Cible Kubernetes, VMware et build initial Codex

### 26.1 Décision et limites

Build initial Codex, trois VM Debian K3s sur VMware et stockage partagé. Docker Compose est une option de laboratoire. Les trois nœuds sont serveurs/control-plane/etcd et hébergent les workloads. Les tailles initiales 8 vCPU/32 Gio/150 Gio par VM sont des paramètres de qualification, pas un minimum universel garanti.

### 26.2 Topologie et endpoint

Vérifier domaines ESXi, anti-affinité, ressources, policy et datastore via inventaire privé. Qualifier les VIP API/HTTPS, DNS et ports avant K3s. L’API administrative n’est jamais publiée sur Internet. Une bascule Keepalived contrôlée ne démontre pas une panne brutale d’ESXi ou datastore.

### 26.3 Workloads

Hermes : un propriétaire actif par état, Recreate, non-root, readonly et sans token SA. Knowledge : service privé, modèles locaux et PostgreSQL. Privacy : service Presidio sans clé fournisseur, relay séparé et DNS interne sans forwarding pour Hermes. Les Jobs d’installation ont un accès public temporaire limité aux artefacts. Les futurs runtimes par utilisateur ne partagent aucun state.db en écriture.

### 26.4 Stockage et reprise

CPI/CSI, ext4 bloc, WaitForFirstConsumer, Retain et RWOP sont les choix actuels. Qualifier attachement, second écrivain, déplacement ordonné puis fencing en panne réelle. PostgreSQL réplique indépendamment du stockage. Une interruption ne réexécute pas une action externe incertaine. Les sauvegardes cohérentes et clés externes sont obligatoires avant production.

### 26.5 Scaling

Scaler les services sans état et les workers selon mesure de file, CPU/RAM et capacités disponibles après perte de nœud. Les budgets et limites fonctionnelles d’une instance sont indépendants du nombre de Pods. L’ingestion CPU lourde est bornée ; OCR/visuel ne s’activent pas uniformément sans benchmark.

### 26.6 Construction et recette

Inventaire → versions/ADR/backlog → VM/confiance SSH → réseau/VIP → K3s → CSI → PostgreSQL → Hermes minimal → Knowledge/Privacy → outils/MCP → Hermes complet → recettes. Reporter toute correction dans Git et mettre à jour le manifeste de bootstrap. Les statuts actuels et derniers essais figurent dans l’état de reprise ; aucune release installable n’est déclarée avant rebuild neuf en mode sûr.
