# Plan de réalisation progressive d'ArcIA v0.7

Objectif : fournir une plateforme multi-tenant isolée avec Open-WebUI, LiteLLM AI/MCP/Agent Gateways, Hermes privé, consoles provider/tenant et supervision intégrée.

Architecture : [conception et flux](conception.md). Contraintes et écarts : [audit](audit.md). Tous les lots ci-dessous sont **proposés et non exécutés**. Les tests déjà exécutés sur le socle sont consignés dans [la vérification](verification.md). Ce document est le plan directeur ; chaque lot donne les unités de code, interfaces et assertions à détailler avant son implémentation. Aucun code produit ni changement de version n'est livré avec ce plan.

## Contraintes globales

- Branche de programme `v0.7`, sans merge ni déploiement de production implicite. Toute intervention sur une cible réelle exige qu'elle soit désignée. Fixtures synthétiques et namespace jetable pour qualification.
- Sources applicatives exclusivement sous `services/`. Le moteur `sync_service_configmaps` projette les sources ; pas de Python incorporé dans les YAML.
- Pas de secret de coffre, kubeconfig, token ou mot de passe dans les prompts, traces, exports publics ou réponses d'API. Valeurs saisies uniquement dans les programmes locaux/formulaires protégés.
- Cluster partagé renforcé en référence, dédié optionnel. Aucun agent n'a de jeton Kubernetes ou privilège de provisionnement. Un propriétaire actif de chaque `state.db`.
- Open-WebUI conservé ; catégorie `simple|agentic` et noms libres. Une seule connexion d'inférence vers LiteLLM après parité A2A ; l'API sécurisée des artefacts reste distincte.
- DLP/ZDR intégralement désactivables par modèle sur politique explicite ; garde obligatoire, absence de politique refusée, panne DLP fail-closed sur les routes protégées, aucun relâchement implicite par fallback.
- Source de vérité des versions : `deploy/versions.json`. Digests vérifiés, pas de tags flottants, licences et migrations qualifiées. Une évolution d'un composant impose l'incrément mineur de plateforme prévu par la gouvernance. La cible commerciale v0.7 n'autorise pas à figer artificiellement le numéro pendant plusieurs évolutions incompatibles : livrer un bundle de versions qualifié, et réviser le numéro au besoin.
- Chaque lot code ajoute ses manifests, config d'exemple, wizard/headless, tests, runbook et déclarations de sauvegarde. Les voies de récupération demeurent disponibles.

## Contrats transverses proposés

| Contrat | Interface et responsabilité |
|---|---|
| Identité | `Principal(tenant_id: UUID, user_id: UUID, grants: frozenset[str])`, issu de la session OIDC vérifiée ; jamais construit depuis un prompt |
| Autorisation | `authorize(principal, action: str, resource: ResourceRef) -> Decision` ; refus par défaut, contrôle de l'organisation et des attributs de ressource |
| Opération de gestion | `submit_operation(principal, command: Command, expected_revision: int, idempotency_key: str) -> OperationRef` ; aucun shell/PodSpec arbitraire |
| Contexte d'exécution | `ExecutionContext(tenant_id, user_id, conversation_id, agent_version_id, model_route_id, policy_revision, audience, expires_at, nonce)` signé et validé ; jamais passé dans les messages LLM |
| Politique | `resolve_execution_policy(principal, route_id, resource_classification) -> EffectivePolicy` ; nouvelle restriction prioritaire sur l'ancienne révision |
| Artefact | `ArtifactRef(id, tenant_id, owner_id, run_id, source_acl_refs, sha256, size, expires_at)` ; l'URL opaque n'est pas un droit |
| Catalogue | `AgentRelease(id, digest, parent_release_id, tool_refs, connection_refs, grants, tests_digest, policy_ref)` ; paquet immuable et attributions réévaluées |
| Projection | `reconcile_projection(desired_revision, observed_revision) -> ReconcileResult` ; propriété de chaque champ documentée, absence de réécriture globale des objets natifs |

Objets de gestion en PostgreSQL : tenants, memberships, operations, policy_revisions, agent_releases, grants et projections. Schémas de migrations et rôles séparés des tables LiteLLM. Contenu métier, transcripts natifs, corpus et binaires dans leur stockage propriétaire ; garder des références évite une troisième copie des conversations. Résultats d'opération et audit assainis, rétention explicite.

## Risques de revue obligatoires

1. Deux onglets changent de tenant pendant une requête : tenant lié à chaque requête, aucune variable globale « tenant actif » ne sélectionne un backend.
2. Un utilisateur est révoqué pendant un run : prochain outil, accès documentaire, téléchargement et approbation refusés ; pas seulement disparition du menu.
3. Un timeout survient après une écriture externe : `uncertain`, consultation de l'état distant et pas de rejeu automatique.
4. Un chat change de modèle ou de politique : la classification des anciens contenus reste applicable ; pas de fuite par relecture, cache, Auto Router ou fallback.
5. Le worker, le proxy, Grafana ou le coffre redémarre : propriétaire d'état conservé, credentials non régénérés, archive restaurable et état de l'opération réconcilié.

## Portes de recette communes

Pour chaque lot code : écrire d'abord les tests comportementaux du contrat, constater les échecs attendus, implémenter le minimum puis exécuter la suite complète. Ne pas fabriquer un test qui valide seulement la présence d'une chaîne.

Commandes obligatoires avec l'interpréteur de validation disponible :

```bash
python -m unittest discover -s tests -v
python scripts/validate_docs.py
python scripts/deploy.py --config tests/fixtures/deploy.synthetic.yaml --dry-run
bash -n scripts/deploy-arcia.sh
bash -n scripts/apply-secrets.sh
bash -n scripts/test-validation.sh
```

Analyser également tous les `scripts/*.ps1` avec le parseur PowerShell, et les autres scripts Bash modifiés. Les validations frontend utilisent les scripts de build/typecheck et une recette navigateur authentifiée dès le lot UI. Tests et rapports propres à chaque lot s'ajoutent à ce socle.

Une preuve indique commit, versions/digests, environnement, données synthétiques, commande, résultat, anomalies et nettoyage. Le déploiement utilise flags, périmètre pilote et retour arrière ; jamais un utilisateur réel choisi implicitement. Pas de passage au lot dépendant avant réussite de ses critères ; les travaux indépendants de documentation peuvent continuer.

## Lot 00 — Cadrage et preuves de départ

Livrable : ce dossier, les décisions confirmées et une carte des responsabilités.

- [x] Récupérer `origin`, vérifier le contenu de travail, conserver une sauvegarde de l'ancien index et créer `v0.7` depuis `09dd2a5`.
- [x] Lire architecture, état réel, installation, déploiement et confidentialité ; inventorier DLP, LiteLLM, sauvegarde et surfaces du wizard.
- [x] Confirmer cluster partagé renforcé et exception DLP/ZDR complète par modèle.
- [x] Relire la conception et enregistrer les corrections de la revue indépendante.
- [x] Vérifier les nouveaux liens, schémas et commandes locales avant livraison du dossier.

Ouverture : documentation seulement. Sortie : plan traçable et aucun changement de comportement du socle. Retour arrière : retirer uniquement les documents de conception de cette branche.

## Lot 01 — Qualification des capacités natives et versions

Fichiers à créer : `tests/fixtures/a2a_synthetic_agent.py`, `scripts/qualify_gateway_stack.py`, `tests/test_gateway_qualification.py` et une matrice sous `docs/reference/` lors de la restructuration. Réutiliser `scripts/qualify_hermes_workspaces.py`, `tests/test_runtime_governance.py`, `tests/test_routing_pipeline.py` et `deploy/versions.json`.

- [ ] Construire une matrice version/API/licence pour LiteLLM AI, MCP, A2A Chat bridge, authentification, budgets, Auto Router et métriques ; vérifier tags, digests et migrations de la base.
- [ ] Ajouter un scénario synthétique avec deux comptes, deux chats par compte, vrais LiteLLM/Hermes/Presidio et modèles déterministes ; aucun fournisseur cloud requis.
- [ ] Vérifier catalogue `/models`, aliases libres, streaming, reprise de contexte, erreurs, annulation et contrôle de l'agent pour chaque identité technique.
- [ ] Générer un CSV avec l'outil terminal, télécharger les octets depuis un chat WebUI, refuser les accès croisés et conserver le fichier après redémarrage.
- [ ] Requalifier `.pth`, entrées, sorties d'outils, SQLite, transport LLM, panne/reprise DLP, réhydratation et limites de vault.
- [ ] Mesurer le contrat natif de reprise/approbation et les besoins d'adaptation. Fixer les objectifs RPO/RTO et capacité de pilote à partir de ce scénario.

Interface produite : `GatewayCapabilityReport` avec capacités observées et `qualified: bool` par fonction. Une simple présence dans Swagger ne donne pas `qualified=true`.

Recette : vrais chemins réseau de la stack, aucun appel fournisseur lors d'un refus ; 404/403 croisés, 422 protégé en panne ; CSV exact et absence de contenu brut des canaris protégés dans toutes les persistances examinées. Vérifier explicitement si la version minimale A2A supporte aussi le pont et l'authentification requis : ne pas supposer que `v1.80.8` suffit.

Ouverture : aucun changement de production. Retour arrière : supprimer seulement le namespace jetable après contrôle de son nonce. En cas de capacité native manquante, préciser le petit adaptateur nécessaire ou différer la bascule ; conserver le chemin historique.

## Lot 02 — API de gestion, identité et état désiré

Créer `services/control_plane/{app,auth,authorization,operations,projections}.py`, `services/control_plane/migrations/`, son Dockerfile, `schemas/arcia-tenant.schema.json` et `tests/test_control_plane_identity.py`. Extraire les opérations métier du wizard vers ces modules ou des bibliothèques `services/management/` ; conserver les anciens appels pendant la transition.

- [ ] Implémenter `Principal`, `authorize`, les memberships et les routes `/api/provider/tenants` et `/api/tenants/{tenant_id}/...` avec refus par défaut.
- [ ] Tester IDOR, headers forgés, confusion de tenant, deux onglets concurrents, UUID non autorisé et compte supprimé.
- [ ] Ajouter `submit_operation`, révision optimiste, idempotence et états `queued/running/succeeded/failed/uncertain` ; travailleur distinct, pas de commande utilisateur exécutée par l'API.
- [ ] Définir l'autorité de chaque objet natif et les projections ; détecter la dérive sans effacer préférences ou identités existantes.
- [ ] Tester une attribution native expansive, une révocation pendant réconciliation et une ancienne projection restaurée ; aucune dérive ne donne un droit nouveau avant validation de la déclaration ArcIA.
- [ ] Introduire sauvegarde et migration réversibles de la base de gestion ; restaurer une première archive sur stockage synthétique isolé.

Recette : même opération répétée avec même clé produit le même ID ; charge différente refusée ; crash du worker réconcilié ; aucune réponse ne restitue de secret. Révocation vérifiée sur un accès déjà ouvert.

Ouverture : API en lecture seule pour l'opérateur de qualification puis opérations synthétiques. Retour arrière : arrêter le nouveau worker, garder wizard et anciens formats, restaurer la base de gestion sans modifier les données natives.

## Lot 03 — Provisionnement et isolation des tenants

Créer `services/control_plane/{tenants,provisioning}.py`, `deploy/manifests/provider/`, `deploy/manifests/tenant/`, `tests/test_tenant_isolation.py`, `scripts/qualify_tenant_isolation.py`. Adapter le rendu namespace de `scripts/deploy.py` ; pas de copie des sources par tenant.

- [ ] Rendre une instance par tenant : WebUI, LiteLLM, Presidio, bases/rôles, PVC, secrets, clé de sauvegarde et identités de service distincts.
- [ ] Qualifier CNI, runtime sandbox et admission ; refuser le profil outillé partagé quand une exigence manque. Ajouter l'option cluster dédié sans changer les contrats applicatifs.
- [ ] Déployer des NetworkPolicies fermées, budgets/quota, proxy de sortie et contrôle DNS ; supprimer les règles « port 443 partout » du profil cible.
- [ ] Tester tentatives de connexion inter-tenant/inter-Power User, API K8s, métadonnées cloud, réseaux privés, DNS rebinding, IPv6 et endpoint privé présenté comme URL publique.
- [ ] Tester la réapplication, changement de slug, suspension, réveil et restauration d'un tenant sans effet sur un autre ; suppression de PVC avec choix explicite de conservation.
- [ ] Qualifier la séparation d'une sandbox de programme publié sans montage de l'état personnel ; un programme utilisant son propre binaire SQLite ne peut atteindre `state.db` Hermes.

Interface : `provision_tenant(command: ProvisionTenantCommand) -> OperationRef`, cible issue d'un inventaire administré ; aucun kubeconfig ou PodSpec envoyé dans la conversation.

Recette : deux tenants synthétiques simultanés et deux runtimes par tenant ; tous les refus effectivement observés sur réseau et stockage, y compris après redémarrage et réapplication. Un utilisateur outillé ne lit aucune identité d'un autre workload. Les limites contre l'administrateur du cluster et la compromission hôte sont écrites.

Ouverture : tenants jetables, puis nouveau tenant pilote explicitement désigné. Retour arrière : désactiver les opérations et conserver les volumes ; ne jamais déplacer automatiquement les données de l'instance historique.

## Lot 04 — Console provider/tenant et socle visuel multilingue

Créer `console/` (React/TypeScript/Vite, versions fixées), `console/src/{app,features,locales}`, `services/control_plane/console.py`, tests UI et routage ingress ; réutiliser des composants accessibles plutôt que recoder un kit de formulaire.

- [ ] Construire `/provider/` : inventaire, création, statut de provisionnement, ressources et incidents infra ; pas de lien donnant implicitement accès aux contenus privés.
- [ ] Construire `/tenant/<slug>/` : accueil, modèles, agents, connexions, utilisateurs/Power Users, confidentialité, sauvegardes, mises à jour et observabilité.
- [ ] Appliquer une direction propre issue des principes taste v2 : navigation stable, tableaux comparables, espace actif visible, états d'erreur et actions hiérarchisées. Ne pas reprendre la DA du wizard.
- [ ] Fournir FR/EN, pluralisation, dates/nombres/fuseaux, chaînes longues, navigation clavier, focus, contraste et comportement responsive.
- [ ] Brancher d'abord les vues en lecture seule sur l'API, puis les opérations qui ont passé leur lot ; afficher état réel et échecs partiels.

Contrat : aucune autorisation dans le seul frontend ; les boutons sont une projection des droits serveur. L'accès à Open-WebUI reste une navigation SSO, pas une réécriture du chat. Qualifier un sous-domaine de chat par tenant si Open-WebUI ne supporte pas le sous-chemin choisi ; les chemins de console imposés ne sont pas sacrifiés.

Recette : sessions provider, tenant A, tenant B et standard ; accès directs aux routes et API refusés ; deux langues sans chaînes manquantes ; aucune clé dans DOM/storage/console navigateur. Captures et parcours réels avec états de chargement, vide, succès et échec.

Ouverture : console en lecture seule au départ. Retour arrière : flag console désactivé, wizard inchangé ; aucune migration d'état de chat.

## Lot 05 — Modèles, politiques et AI Gateway

Créer `services/control_plane/{models,policies,litellm_adapter}.py`, `schemas/arcia-inference-policy.schema.json`, `tests/test_execution_policies.py`. Adapter `services/hermes/runtime_guard.py`, `services/presidio/app.py`, le guardrail LiteLLM et les projections WebUI uniquement après tests.

- [ ] Exposer le catalogue administré avec aliases libres, catégories, hébergement et fournisseurs ; préserver les clés et identifiants existants.
- [ ] Implémenter `resolve_execution_policy` et son contexte signé ; modes `enforce/off` et `required/not_required` sans variable globale de requête.
- [ ] Tester l'exception complète sur canaris synthétiques, la route protégée concurrente, l'absence de politique, la révocation et la panne Presidio.
- [ ] Interdire déclassement d'historique/corpus, fallback non admissible, override client de fournisseur/ZDR et réactivation involontaire de logs bruts.
- [ ] Implémenter le cumul route Agentic/modèle réel/classification et le contexte de pseudonymisation propriétaire commun aux transports ; vérifier réhydratation locale et absence de réhydratation dans les logs ou vers le cloud.
- [ ] Ajouter Auto Router uniquement si la fonction et sa licence sont disponibles ; classifier et candidates dans le même périmètre de données, budget et habilitations. Sinon conserver le routage explicite natif sans inventer un routeur parallèle.

Recette : la route `off` se comporte réellement comme annoncée sur payload synthétique ; elle n'affecte pas `enforce` ; les secrets du coffre ne sont jamais injectés ; l'UI affiche la politique effective. Une politique ZDR impossible échoue au lieu de revenir vers une route plus permissive. Les droits documentaires restent applicables en mode `off`.

Ouverture : catalogue en lecture, puis édition pour admin pilote ; exceptions désactivées par défaut. Retour arrière : restaurer les déclarations et projections qualifiées ; nouvelles restrictions immédiates ; ne pas tenter de « réanonymiser » rétroactivement une transmission déjà effectuée.

## Lot 06 — Bascule A2A et conservation des fichiers

Créer `services/control_plane/{agent_bindings,a2a_adapter}.py` si les fonctions natives ne suffisent pas, `tests/test_a2a_workspaces.py`. Réutiliser `services/hermes/files.py`, `services/open_webui/arcia_hermes_files.py`, `scripts/hermes_files.py` et les fixtures du lot 01.

- [ ] Projeter les agents et droits vers LiteLLM ; l'identité nominative sélectionne uniquement les bindings autorisés. Les IDs de trace ne servent jamais d'habilitation.
- [ ] Mapper conversation WebUI → contexte A2A → session privée sans employer le prompt ou l'email comme autorité. Qualifier propriété, annulation et reprise.
- [ ] Tester identité/enveloppe non transformées, chat mixte `enforce/off`, modèles internes, perte du vault et CSV contenant des marqueurs ; refuser la transformation de formats binaires non qualifiés.
- [ ] Préserver l'API d'artefacts authentifiée et publier uniquement les fichiers existants d'un tour terminé ; adapter la présentation des références dans le chat.
- [ ] Étendre le même binding au canal Teams et aux liens de fichiers ; interdire le repli vers le runtime central partagé.
- [ ] Basculer `gateway.agent_transport: legacy|a2a` par tenant pilote. Retirer le second backend de chat seulement après parité de génération, stockage, streaming, droits et personnalisation.

Recette : matrice Standard/Power User/admin/non associé, deux chats par compte, CSV exact, liens copiés entre comptes et tenants refusés ; restart du portail/Hermes, timeout, annulation et ancienne conversation. Une mission doit utiliser `SOUL.md` du bon propriétaire. Un alias Agentic ne peut devenir le modèle LLM de sa propre boucle.

Ouverture : synthétique → comptes pilotes → tenant pilote → autres tenants après preuve. Retour arrière : restaurer le transport historique pour nouvelles soumissions, réconcilier les runs existants sans les rejouer ; conserver les artefacts déjà publiés.

## Lot 07 — Prometheus, Grafana et alertes intégrées

Créer `deploy/observability/` pour chart values/version/digests, dashboards JSON et règles, `services/control_plane/observability.py`, `tests/test_observability_scope.py` et recette navigateur.

- [ ] Provisionner Prometheus/Grafana par tenant et une supervision provider distincte ; exporters de nœud administrés par provider, aucune permission hôte accordée au tenant.
- [ ] Collecter santé, saturation, erreurs, latence, capacité et fraîcheur des sauvegardes ; pas de contenu conversationnel ni label nominatif à forte cardinalité.
- [ ] Intégrer les dashboards derrière proxy authentifié même origine, anonyme désactivé, headers reconstruits, datasource bornée et accès backend direct fermé.
- [ ] Ajouter alertes disponibilité, DLP indisponible, stockage, budgets et sauvegarde absente ; leurs destinations sont administrées, pas de notification réelle envoyée pendant la qualification.
- [ ] Tester `/api/ds/query`, changement de datasource, UUID/slug forgé, injection de header d'auth et requête sans filtre tenant ; interdire toute lecture des métriques d'un autre tenant.
- [ ] Tester les API de labels/séries, la découverte K8s limitée au namespace, les cibles interdites et l'absence d'accès tenant à l'exporter global de nœud.

Recette : dashboards intégrés avec SSO, FR/EN de la console, refus anonymes/croisés et cardinalité bornée. Les agrégats provider excluent noms de documents, prompts, identités fournisseur et secrets. Ne pas confondre budget LLM et coût total infra/outils.

Ouverture : provider puis tenant pilote ; lecture seule pour les tableaux intégrés. Retour arrière : désactiver l'intégration sans arrêter les contrôles de sécurité ; conserver les historiques selon rétention.

## Lot 08 — RAG, MCP et connexions partagés

Créer `services/control_plane/{knowledge,connections,mcp_adapter}.py`, `services/knowledge/adapter.py` si nécessaire, `tests/test_tenant_knowledge_acl.py`, `tests/test_mcp_delegation.py` et un corpus synthétique.

- [ ] Qualifier les API RAG natives Open-WebUI pour recherche, citations et droits ; exposer leur contrat commun via `arcia_knowledge` pour Hermes et applications.
- [ ] Gérer les MCP avec la passerelle native LiteLLM ; identités personnelles et connexions de service distinctes, scopes minimaux et révocation.
- [ ] Déployer les programmes MCP dans des workloads séparés ; interdire les commandes stdio arbitraires dans la passerelle partagée et les téléchargements de dépendances non qualifiées.
- [ ] Ajouter un premier connecteur documentaire et les mocks CRM/PGI ; synchronisation à checkpoints, suppressions, cache borné et provenance des artefacts dérivés.
- [ ] Tester injection documentaire, accès d'un autre groupe, révocation pendant un run, disparition source et résultat périmé ; filtrer avant extrait et avant transfert externe.

Recette : même réponse sourcée et mêmes droits depuis chat et Hermes ; droits du système source respectés sans compte applicatif qui prétend représenter automatiquement chaque personne. Une désactivation DLP ne change pas les ACL. Ne pas ouvrir un graphe de connaissances global avant un besoin mesuré.

Ouverture : corpus synthétique puis une source pilote explicitement désignée, lecture seule. Retour arrière : arrêter synchronisation et couper la connexion ; purge des caches et contrôle des dérivés ; préserver les corpus natifs non migrés.

## Lot 09 — Catalogue d'agents et publication administrée

Créer `services/control_plane/{agents,releases,directory}.py`, `schemas/arcia-agent-package.schema.json`, écrans de catalogue et `tests/test_agent_publication.py`.

- [ ] Construire un formulaire structuré de mission, comportement, outils, programmes, sources et limites ; rendre SOUL/AGENTS à partir de ces champs et conserver l'édition avancée autorisée.
- [ ] Produire un paquet versionné avec digest, dépendances fixées, tests, données synthétiques et permissions demandées. Distinguer définition et état personnel.
- [ ] Implémenter brouillon → qualification → prêt → publié → retiré ; publier vers IDs de comptes, rôles ou IDs de groupes M365.
- [ ] Résoudre les destinataires sans ambiguïté, gérer overage de groupes, départ de l'organisation et version précédente ; aucune délégation implicite d'une connexion personnelle.
- [ ] Projeter la publication dans les catalogues natifs WebUI/LiteLLM/Hermes et montrer les échecs partiels jusqu'à réconciliation.

Recette : deux versions d'un agent synthétique, publication à un groupe puis retrait ; un non-membre ne peut l'appeler par ID direct ; le package ne contient ni mémoire Power User ni credential ; changer SOUL ne modifie pas les permissions serveur.

Ouverture : administrateurs pilotes puis utilisateurs ciblés. Retour arrière : réaffecter une version immuable précédente sans migrer/rejouer les écritures des missions en cours.

## Lot 10 — Builder conversationnel et actions approuvées

Créer `services/control_plane/{builder,approvals,publication_executor}.py`, `services/builder_tools/`, templates de sandbox, `tests/test_builder_permissions.py`, `tests/test_action_reconciliation.py`. Réutiliser les runs/approbations natifs Hermes quand qualifiés ; ne pas créer un second état pour le même contrôle.

- [ ] Provisionner un profil builder privé à l'administrateur, borné au tenant et à son périmètre ; aucun accès cluster-admin, clé master ou autre utilisateur.
- [ ] Donner des outils typés pour inspecter contrats, préparer un paquet, lancer tests synthétiques et proposer une publication. Les prompts peuvent itérer sur une release précédente.
- [ ] Construire code et programmes en sandbox sans données métier réelles ; dépendances/image fixées, analyse des permissions, sorties réseau bornées.
- [ ] Exécuter les programmes publiés dans une sandbox sans volume personnel ni credential général, avec capacités serveur par utilisateur/agent/version/run ; fallback vers runtime séparé si Hermes ne borne pas les outils par run.
- [ ] Produire la recette de confiance avec un exécuteur plateforme indépendant ; tests proposés par le builder plus contrôles obligatoires, attestation liée au digest et aux permissions, substitution de paquet refusée.
- [ ] Lier l'approbation au digest, arguments normalisés, destinataires, identité, génération et expiration ; usage unique et revérification avant effet. Réutiliser Teams pour les actions risquées selon la règle du projet.
- [ ] Tester refus de publication sans droits, prompt injection de source CRM, destinataire ambigu, paquet modifié après validation, approbation rejouée et crash après écriture externe.
- [ ] Démontrer « construire un agent de forecast CRM/PGI puis le modifier et le publier à un utilisateur synthétique » avec connexions simulées ; une évolution du harness générique produit une proposition de code revue, jamais un patch direct de production.

Recette : version publiée réellement invocable par le seul destinataire habilité, résultats vérifiables, modifications traçables, aucun privilège issu du prompt. Timeout distant donne `uncertain` ; le système consulte l'état avant toute reprise.

Ouverture : builder en proposition seule, puis publication approuvée sur tenant pilote. Retour arrière : désactiver le builder et retirer la nouvelle release ; aucune promesse d'annuler automatiquement une action métier irréversible.

## Lot 11 — Migration des fonctions du wizard et reprise autonome

Créer `services/management/{updates,backup,sizing,powerusers}.py` au besoin, adapter `services/instance_backup/`, `scripts/wizard.py`, `scripts/wizard_ui/index.html`, wrappers, console et `tests/test_wizard_console_parity.py`.

- [ ] Finir l'extraction de logique déjà utilisée par les lots précédents ; le wizard et la console appellent le même moteur, sans copie de fonctions.
- [ ] Livrer console pour routage, modèles, Power Users, resize, veille/réveil, mise à jour, sauvegarde continue, historique et restauration ciblée ; provider limité à son périmètre infra.
- [ ] Migrer le contexte d'accès sauvegarde vers le coffre serveur par tenant, conserver lecture AES-GCM existante et récupération locale sans dépendance à la console.
- [ ] Qualifier sauvegarde de toutes les données, restauration de tenant isolée, identités stables, changements de mot de passe/clé et file durable après crash.
- [ ] Réduire le wizard à installation et restauration uniquement lorsque la matrice de parité passe. Conserver les champs initiaux nécessaires à installer une instance ; ne pas maintenir un deuxième écran d'administration.
- [ ] Tester console inaccessible et cluster vierge : le wizard/headless doit pouvoir reconstruire le socle et rétablir les données avec credentials protégés.

Recette : chaque ancienne fonction a une destination, une commande, un test et un retour arrière ; arrêt du poste initial n'interrompt plus les sauvegardes serveur. Le dashboard distingue configuration sauvegardée, données sauvegardées et restauration réellement vérifiée.

Ouverture : écrans de console un à un puis retrait des anciennes routes d'admin. Retour arrière : réactiver l'ancien parcours seulement si son moteur et son archive restent compatibles ; le runbook décrit les migrations non réversibles et la restauration préalable.

## Lot 12 — Documentation, recette finale et extension progressive

Adapter `docs/README.md`, guides/runbooks, `AGENTS.md`, README, `.github/workflows/validate.yml`, `scripts/validate_docs.py` si nécessaire et les contrôles de versions.

- [ ] Réorganiser selon le [plan documentaire](README.md#réorganisation-documentaire-prévue), avec liens de transition et titres en casse de phrase ; séparer compréhension, tâches, procédures et référence.
- [ ] Documenter chaque rôle, les limites réelles de l'isolation partagée, exceptions DLP/ZDR, support exceptionnel, politique des fichiers et droits des sources.
- [ ] Étendre CI à la branche de programme et ajouter contrats, isolation, UI, artefacts, i18n et dashboards au périmètre réellement exécuté.
- [ ] Exécuter recette navigateur, kill switch, perte de nœud, mises à jour, rollback, charge/capacité, PRA et rebuild sur cluster neuf sur une cible désignée.
- [ ] Collecter la satisfaction du lot avec scénarios mesurables : tâche accomplie, refus attendus, temps d'attente, coût, absence de fuite et état sauvegarde ; corriger avant élargissement.
- [ ] Étendre nouveau tenant pilote → pilote interne → tenants désignés ; migration des anciennes instances seulement après preuve de conservation des données et identités.

Recette : aucun échec ouvert sur le périmètre livré, aucun test annoncé sans exécution, inventaire des exceptions, RPO/RTO mesurés et artefacts de reconstruction disponibles. La qualification synthétique et le rebuild neuf restent deux preuves différentes.

## Ordre et périmètres d'ouverture

```mermaid
flowchart LR
    L0["00 Conception"] --> L1["01 Capacités et preuves"]
    L1 --> L2["02 API et identité"]
    L2 --> L3["03 Tenants isolés"]
    L3 --> L4["04 Console"]
    L4 --> L5["05 Modèles et politiques"]
    L5 --> L6["06 A2A et fichiers"]
    L6 --> L7["07 Observabilité"]
    L7 --> L8["08 RAG et MCP"]
    L8 --> L9["09 Publication"]
    L9 --> L10["10 Builder"]
    L10 --> L11["11 Wizard et PRA"]
    L11 --> L12["12 Recette et extension"]
```

Les documentations et sauvegardes sont mises à jour dans chaque lot, pas reportées au lot 12. Le lot 12 ferme la cohérence globale. La réduction définitive du wizard arrive après la parité pour préserver la voie de secours. Aucun calendrier ou dimensionnement de production n'est déduit du seul nombre de lots.
