# Architecture cible ArcIA v0.7.0

Décision du 20 octobre 2026 : **agentgateway OSS remplace LiteLLM**. Le [contrat applicatif](v0.7/contrat-applicatif.md) gouverne les interfaces ; la [conception détaillée](v0.7/conception.md) contient les schémas et parcours. Les [lots](v0.7/lots.md) et leurs [preuves](v0.7/verification.md) distinguent cible et état réel.

## Provider, tenants et composants

La console expose `/provider/` pour le cycle de vie des tenants et l'infrastructure, puis `/tenant/<slug>/` pour administrer une instance. Le slug est une présentation ; un UUID immuable porte l'autorisation. Le provider ne reçoit aucun droit applicatif implicite sur les contenus privés.

| Composant cible | Responsabilité |
|---|---|
| Open-WebUI par tenant | Chat, collaboration et SSO ; une connexion de chat vers agentgateway après parité |
| agentgateway par tenant | Routage LLM/MCP/A2A, JWT strict, autorisation CEL et métriques ; mode standalone avec configuration déclarative, sans remplacement de Traefik |
| API et worker ArcIA | Identité canonique, droits, politiques, catalogue, publication et opérations réconciliées ; permissions séparées |
| Hermes privé par compte | Sessions, mémoire et outils, PVC privé et un propriétaire actif par état ; même environnement pour le Power User et son canal Desktop/IDE |
| Presidio par tenant | DLP/pseudonymisation avant persistance Hermes et transport fournisseur ; adaptation du webhook natif à qualifier |
| PostgreSQL de gestion | État administratif ArcIA, indépendant des tables LiteLLM ; les données natives restent dans leurs stockages propriétaires |
| Prometheus/Grafana | Supervision intégrée et authentifiée ; métriques tenant et provider séparées |

Le cluster existant est la cible désignée. Le profil multi-tenant exige namespaces, identités, bases/rôles, secrets, PVC et sauvegardes distincts ; un cluster dédié reste une option. RAG, connexions MCP et définitions d'agents sont partagés selon les ACL du tenant, jamais l'état personnel Hermes.

## Identité et parcours

- Entra authentifie l'utilisateur. Son `tid` désigne l'annuaire, pas le tenant ArcIA ; les appartenances sont vérifiées côté serveur.
- Open-WebUI transmet une identité vérifiable avec une audience adaptée. La gateway valide le jeton et applique CEL ; les headers en clair ou prompts ne créent aucun droit.
- L'inférence appelle le fournisseur autorisé après application de la politique de données. Les inférences internes Hermes passent par la même gateway.
- Le parcours agentique sélectionne un binding privé. Conversation, contexte A2A, session et artefacts restent liés ; le support de deux protocoles ne prouve pas leur conversion.
- Les accès MCP, sources, outils et téléchargements recontrôlent les droits. Le builder propose des versions testables ; les services vérifient publication et attributions.

## Confidentialité et isolation

DLP active et ZDR requise par défaut. Leur désactivation complète par modèle/route doit être explicite, administrée, auditée et compatible avec les contraintes de l'agent et des données. Elle ne déclasse pas l'historique et n'accorde aucun accès aux secrets.

Le webhook guardrail agentgateway n'est pas l'API Presidio historique. Conversion, fail-closed, réhydratation, outils, streaming et formats sont des portes de recette. L'ancrage Hermes `.pth` reste obligatoire ; il ne remplace pas la sandbox d'un programme hostile.

Refus réseau par défaut, sorties bornées, interdiction inter-tenants et inter-runtimes. L'exécution de code exige sandbox, CNI et admission qualifiés ; un namespace seul ne suffit pas. Aucun agent ne reçoit de jeton Kubernetes, montage hôte, PodSpec arbitraire ou droit de provisionnement. Une écriture externe incertaine n'est pas rejouée au restart.

## État réel et migration

agentgateway v1.6.0 et son image sont [épinglés](../deploy/versions.json). Bootstrap fermé et 13 cas HTTP JWT/CEL qualifiés sur le cluster existant ; namespace jetable vérifié supprimé. Cet émetteur synthétique ne qualifie ni Entra réel, ni LLM/Presidio, ni MCP/A2A, ni artefacts, ni HA.

`gateway.implementation: agentgateway`, `mode: qualification_only` sélectionne la cible. Son déploiement global reste refusé avant migration recettée, sans repli vers LiteLLM. L'[architecture historique](architecture-legacy.md), ses clés et sa base restent uniquement pour continuité et retour arrière ; aucune preuve antérieure n'est renommée.

Le wizard cible garde installation/restauration ; le reste passe dans la console après parité. Chaque lot synchronise code, manifests, migrations, sauvegardes, tests et runbooks. Une recette synthétique n'est ni une mise à jour de production, ni un rebuild sur cluster neuf.
