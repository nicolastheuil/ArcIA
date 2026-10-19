# Sources et capacités à qualifier pour ArcIA v0.7

Consultation publique du 19 octobre 2026. Ces sources donnent des contrats et pistes de réutilisation ; elles ne certifient pas l'installation ArcIA. Les liens de documentation courante peuvent évoluer : le lot 01 fixe les versions et commits correspondant au code réellement qualifié.

## Sources locales

| Référence | Utilisation |
|---|---|
| [Architecture actuelle](../architecture.md) | Topologie, ports, catégories et source du code |
| [État des fonctionnalités](../etat-des-fonctionnalites.md) | 43 contrôles API et 24 DLP natifs attestés historiquement ; limites de recette |
| [Quickstart](../runbooks/quickstart.md) | Parcours et fonctions à migrer du wizard |
| [Déploiement universel](../guides/deploiement-universel.md) | Bootstrap, headless et requalification du `.pth` |
| [Confidentialité](../guides/confidentialite-presidio.md) | Filtrage, panne fermée, pseudonymisation et ZDR |
| [Sauvegarde et reconstruction](../runbooks/sauvegarde-reconstruction.md) | Format existant, coffre local, fichiers et exclusions des volumes |
| [Versions déclarées](../../deploy/versions.json) | ArcIA 0.6.0 ; LiteLLM 1.72.6-stable ; Hermes 0.22.2 ; Open-WebUI 0.12.3 ; Presidio 2.2.364 ; OAuth2-Proxy 7.8.1 |

## Sources officielles externes

| Source | Fait utile et limite |
|---|---|
| [Galene.AI](https://galene.ai/) | Séparation infrastructure, console d'organisation et applications ; inspiration de responsabilités et de navigation, sans qualification de leur release |
| [Agent Gateway LiteLLM](https://docs.litellm.ai/docs/a2a) | Agents A2A, permissions et opérations de tâches ; protocoles à fixer |
| [Invocation A2A](https://docs.litellm.ai/docs/a2a_invoking_agents) | Pont Chat Completions `a2a/`, streaming et API de tâches ; fichiers et continuité privée à tester |
| [Permissions d'agents](https://docs.litellm.ai/docs/a2a_agent_permissions) | Contrôle d'invocation ; ne remplace pas les ACL documentaires ou l'isolation des runtimes |
| [MCP Gateway](https://docs.litellm.ai/docs/mcp) | Catalogue et accès techniques aux serveurs MCP ; délégation des droits métier à qualifier |
| [Auto Router](https://docs.litellm.ai/docs/auto_router/) | Fonction présentée comme add-on ; éligibilité/licence et coût du classifier à vérifier ; pas de dépendance obligatoire avant confirmation |
| [Notes LiteLLM](https://docs.litellm.ai/release_notes) | Introduction annoncée de l'A2A Agent Gateway en 1.80.8 ; version nécessaire au pont complet à établir, pas supposée |
| [A2A Hermes au tag 0.22.2](https://github.com/NousResearch/hermes-agent/blob/v0.22.2/plugins/platforms/a2a/README.md) | Plugin natif, sessions actives et jetons de pairs ; sa présence dans le source ne prouve pas son activation sur l'image |
| [API Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server) | Runs, sessions, événements et contrôles ; réutiliser les capacités disponibles dans la version choisie |
| [Groupes Open-WebUI](https://docs.openwebui.com/features/authentication-access/rbac/groups/) | Groupes et partage ; ne pas confondre groupe et tenant indépendant |
| [Permissions Open-WebUI](https://docs.openwebui.com/features/authentication-access/rbac/permissions/) | Permissions natives à projeter et tester au lieu de recoder le chat |
| [Sécurité Grafana](https://grafana.com/docs/grafana/latest/setup-grafana/configure-security/) | Un Viewer peut interroger ses datasources au-delà des panels : le filtre du dashboard n'est pas une isolation |
| [Proxy d'authentification Grafana](https://grafana.com/docs/grafana/latest/setup-grafana/configure-access/configure-authentication/auth-proxy/) | Authentification par proxy et contrôle de provenance des headers ; pas d'accès anonyme pour faciliter l'iframe |
| [Modèle de sécurité Prometheus](https://prometheus.io/docs/operating/security/) | Endpoints de métriques et de requêtes à protéger ; séparation provider/tenant |
| [Multitenancy Kubernetes](https://kubernetes.io/docs/concepts/security/multi-tenancy/) | Namespace seul insuffisant, RBAC/réseau/données et besoin éventuel de séparation plus forte |

## Matrice de réutilisation et limites

| Besoin | Premier choix | Ce qu'ArcIA doit encore assurer |
|---|---|---|
| Chat et historique | Open-WebUI natif | Identité commune, projection des accès, conservation et migration |
| Inférence | LiteLLM AI Gateway | Politiques administrées, secrets hors modèle et tests de non-contournement |
| Appel d'agent | LiteLLM Agent Gateway + Hermes A2A | Binding au propriétaire, contexte, droits et fichiers |
| Boucle agentique et tâches | API Hermes | Contrat des approbations, attachement, résultat incertain et gouvernance |
| Outils distants | LiteLLM MCP Gateway | Identité déléguée, autorisation métier et isolation du serveur d'outils |
| RAG | Connaissances natives WebUI | API commune et qualification ACL/citations ; remplacement seulement si écart démontré |
| Choix de modèle | Auto Router natif optionnel | Routes éligibles, classification protégée, licence et tests qualité/coût |
| Métriques et dashboards | Prometheus/Grafana | Partition des données, SSO/proxy et provisioning |
| Builder | Hermes, compétences et outils typés | Contrat de paquet, sandbox, recette, approbation et publication |
| Administration | Nouvelle console ArcIA | Pas de clonage des consoles complètes des composants ; ne présenter que les opérations utiles |

Les tags récents de documentation, les éditions commerciales et les digests non résolus ne sont pas inscrits comme versions certifiées. Les licences des versions retenues sont vérifiées avant packaging, y compris les conditions de marque des composants. Les fonctions payantes restent optionnelles avec un état explicite ; le plan ne suppose ni abonnement ni achat autorisé.
