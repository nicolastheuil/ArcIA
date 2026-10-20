# Contrat applicatif de la plateforme v0.7

Décision du 20 octobre 2026 : **agentgateway OSS remplace LiteLLM dans la cible v0.7**. Ce contrat gouverne la [conception](conception.md), les [lots](lots.md), les projections de configuration et leurs tests. Il ne constitue pas une attestation de déploiement ou de parité fonctionnelle.

## Responsabilités

| Bloc | Contrat |
|---|---|
| Open-WebUI par tenant | Chat et collaboration ; SSO Entra ; une connexion de chat vers agentgateway, catalogue aux noms libres et sans `category` |
| agentgateway par tenant | Routage LLM, MCP et A2A ; authentification JWT stricte, autorisation CEL et télémétrie sans contenu privé ; fonctions de la version OSS épinglée uniquement |
| API ArcIA | Identité canonique, appartenances, droits, routes, politiques, connexions et versions d'agents ; interfaces provider et tenant |
| Worker ArcIA | Projections déclaratives agentgateway et applications ; opérations typées, idempotentes et réconciliées ; permissions séparées de l'API |
| Hermes privé | Un runtime et un état par propriétaire ; sessions distinctes par conversation, outils, programmes et artefacts privés |
| Presidio | Pseudonymisation et réhydratation ; contrôle avant persistance Hermes et avant sortie fournisseur, suivant la politique effective |
| PostgreSQL de gestion | Tenants, memberships, opérations, politiques et références ; aucune dépendance à la base ou aux tables LiteLLM |

Le mode standalone agentgateway est retenu sur le cluster existant : config déclarative et Deployment Kubernetes, sans ajout d'un contrôleur Gateway API ou remplacement de Traefik. Le provider et les tenants conservent leurs frontières, namespaces, stockages et identités distincts.

## Identité et autorisation

- `tenant_id` est l'UUID ArcIA ; `tid` désigne l'annuaire Entra et n'est jamais sa valeur implicite. L'identité vérifiée est reliée à `(iss, sub)` et, lorsque pertinent, `(tid, oid)` par correspondances administrées.
- La gateway refuse token absent, signature invalide, émetteur ou audience inattendus, expiration et appartenance insuffisante. Les règles CEL d'autorisation sont en refus par défaut ; claims et headers fournis par le client ne créent aucun droit.
- Open-WebUI peut transmettre un access token OAuth destiné à l'API ArcIA/gateway. Son JWT interne signé est une alternative à qualifier, pas un JWT Entra : le format v0.12.3 ne fournit pas à lui seul groupes, audience et appartenance ArcIA.
- Résoudre les groupes par leurs IDs, gérer les claims incomplets/overage, les caches bornés et les révocations. Aucun nom de groupe ou domaine email ne sélectionne seul un tenant.
- Les backends n'acceptent que les appels autorisés de leur gateway ou broker, avec identité vérifiable et audience adaptée. Ne pas retransmettre arbitrairement un token Microsoft Graph ou un ID token à Hermes/MCP.
- Les ACL de sources, artefacts et ressources restent contrôlées côté serveur. Le filtrage des outils MCP n'est pas une preuve de cloisonnement documentaire ou d'isolation du code.

## Catalogue et parcours

Une route a un ID stable, un alias libre, une destination typée (`inference` ou `a2a`), une politique et des attributions. Ce type technique ne réintroduit pas une catégorie de modèles côté Open-WebUI.

- Inférence : WebUI → agentgateway → contrôle Presidio → fournisseur autorisé ; streaming, erreurs et absence de fournisseur éligible sont explicites.
- Agent : WebUI → agentgateway → binding autorisé → A2A Hermes privé ; les inférences internes Hermes repassent par agentgateway et leur politique effective.
- MCP/RAG : appel authentifié → autorisation CEL → serveur d'outil isolé → contrôle documentaire avant extrait. Le choix du moteur vectoriel n'est pas imposé par le remplacement de gateway.
- Artefact : conversation → run → fichier privé ; téléchargement authentifié depuis le chat, vérification des ACL actuelles et refus croisés après restart.

Le support natif d'OpenAI Chat Completions et d'A2A ne prouve pas leur conversion. Qualifier d'abord identité, contexte, streaming, annulation, erreurs et fichiers ; n'ajouter qu'un adaptateur minimal si un écart est démontré. Ne pas annoncer une connexion unique opérationnelle avant cette parité.

## Confidentialité et exploitation

- DLP active et ZDR requise par défaut ; désactivation complète par route/modèle seulement sur politique administrée explicite, versionnée et auditée. Droits, isolation et protection des secrets de plateforme restent obligatoires.
- Le protocole webhook guardrail d'agentgateway n'est pas l'API Presidio `/analyze`/`anonymize`. Adapter et tester le contrat natif ; panne, erreur, réponse invalide ou format non qualifié refusent une route protégée. Conserver la réhydratation et l'ancrage Hermes.
- Tester également outils, historique, sorties d'agent et streaming. La détection PII intégrée à une gateway n'est pas réputée équivalente au bouclier ArcIA.
- Budgets, quotas, routage conditionnel et métriques utilisent les primitives OSS réellement qualifiées. L'Auto Router, les clés virtuelles et les callbacks LiteLLM ne sont pas des API de la nouvelle cible.
- Aucun achat Enterprise implicite. Les limites natives sont consignées ; pas de remplacement maison d'une gateway entière ni de promesse de HA depuis un simple Deployment.

## Migration et recette

Le choix de cible est définitif pour le programme ; l'ancien transport LiteLLM reste uniquement une compatibilité de migration. Préserver ses secrets, clés, base, volumes et preuves historiques jusqu'à bascule recettée et retour arrière vérifié. Il n'est plus la dépendance cible de la console, des politiques ou des nouveaux agents.

La nouvelle configuration utilise `gateway.implementation: agentgateway`. Un ancien fichier sans ce champ reste identifié comme historique ; aucune réapplication ne convertit silencieusement l'instance. Un bootstrap fermé ou une recette synthétique n'autorise pas la migration des utilisateurs.

Portes : schéma natif et digest → JWT/CEL avec deux identités et refus croisés → DLP réelle et panne → parcours Hermes/artefacts → pilote explicitement désigné → retrait des dépendances historiques. Les [lots](lots.md) portent les critères détaillés. La version de développement reste celle du bundle v0.7 en construction ; aucune version installée ou preuve historique n'est réétiquetée.
