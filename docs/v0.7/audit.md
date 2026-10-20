> Audit historique du socle au 19 octobre. Le [contrat du 20 octobre](contrat-applicatif.md) remplace LiteLLM par agentgateway dans la cible ; les constats ci-dessous ne sont pas une évaluation d’agentgateway.

# Audit critique préalable à ArcIA v0.7

Photographie initiale, antérieure au verrouillage des versions et aux nouvelles recettes Kubernetes : voir [versions actuelles](../guides/versions-officielles.md) et [complément de vérification](verification.md). Les constats ci-dessous décrivent la base de départ.

Date : 19 octobre 2026. Périmètre : sources génériques locales au commit `09dd2a5` et documentation officielle publique. Aucun kubeconfig, secret d'instance, cluster privé ou contenu métier réel n'a été consulté. Les recettes historiques ci-dessous sont des attestations du dépôt, pas des exécutions répétées pendant cette étude.

## Socle réutilisable

| Élément | Constat et preuve | Conséquence |
|---|---|---|
| DLP Hermes | Bootstrap, ancrage `.pth`, garde SQLite/HTTP, entrée native et batch dans [services/hermes](../../services/hermes/README.md) | Conserver et requalifier sur chaque changement d'image et nouveau transport |
| Qualification historique | L'[état réel](../etat-des-fonctionnalites.md) consigne 43 contrôles API/isolation et 24 DLP natifs, avec Presidio réel et fournisseur déterministe | Ne plus présenter la DLP native comme absente ; le véritable proxy LiteLLM et le rebuild restent des périmètres distincts |
| Fichiers privés | [Relais Hermes](../../services/hermes/files.py) et [intégration WebUI](../../services/open_webui/arcia_hermes_files.py), avec compte vérifié, liens opaques, contrôles de taille, quota et propriétaire | Réutiliser le stockage et les contrôles ; remplacer seulement le transport devenu inutile après parité A2A |
| Power Users | Provisionnement, association au runtime existant, préférences et PVC préservés | Ne pas créer un second état pour raccorder le portail |
| Sauvegarde | [services/instance_backup](../../services/instance_backup), AES-GCM, identités conservées, fichiers portables, file chiffrée et historique | Extraire le moteur commun, conserver le format et la lecture des archives existantes |
| Déploiement | [deploy.py](../../scripts/deploy.py), wrappers, configuration synthétique et synchronisation des sources | Étendre le bootstrap existant, pas un second déployeur |
| Wizard | Administration modèles, Power Users, mises à jour, infra, sauvegarde et restauration dans [wizard.py](../../scripts/wizard.py) | Extraire des opérations réutilisables, puis déplacer les parcours après recette |

## Faiblesses qui changent réellement le plan

| Réf. | Gravité | Constat | Solution et preuve attendue |
|---|---|---|---|
| A01 | Bloquant | LiteLLM reste fixé à `v1.72.6-stable`. Les fonctions A2A/MCP/Auto Router consultées appartiennent à une documentation plus récente | Lot 01 : matrice versions, licences et comportement ; aucun numéro récent déclaré certifié sans tests |
| A02 | Bloquant | Le pont Chat Completions vers A2A n'atteste ni la continuité des chats, ni les artefacts téléchargeables, ni la délégation vers un propriétaire privé | Canari complet WebUI → LiteLLM → Hermes ; conserver le relais historique jusqu'à parité démontrée |
| A03 | Critique | Les NetworkPolicies [actuelles](../../deploy/manifests/09-network-policy.yaml) autorisent certains ports HTTP/HTTPS sans destination. Ce n'est pas un Internet exclusivement public | Proxy de sortie obligatoire, refus des réseaux privés, métadonnées cloud, API K8s et DNS rebinding ; tests TCP, UDP, IPv4 et IPv6 |
| A04 | Critique | Un pod outillé sur un cluster partagé n'est pas une frontière suffisante contre du code hostile au noyau commun | Runtime sandbox qualifié, Pod Security, volumes bornés, absence de socket hôte et de jeton K8s, CNI qui applique réellement les politiques ; dédié en option |
| A05 | Critique | La configuration générée contient `approvals.unattended_mode: approve` dans [deploy.py](../../scripts/deploy.py) | Auditer le contrat natif exact ; aucune écriture sensible non supervisée ; approbation serveur obligatoire pour les actions risquées |
| A06 | Élevée | Teams `/agent` utilise encore une cible Hermes centrale dans [app.py](../../services/teams/app.py) | Étendre à Teams le même binding tenant/utilisateur ; refuser les contextes partagés sans périmètre explicite |
| A07 | Élevée | Le wizard est une application locale protégée par Host/Origin, sans modèle d'autorisation multi-tenant | Ne pas l'exposer sur Internet ; nouvelle API avec identité vérifiée et worker borné ; réemploi de la logique métier uniquement |
| A08 | Élevée | Déplacer la sauvegarde hors du wizard arrête aussi son observateur local et son contexte DPAPI | Worker durable par tenant, coffre serveur, déclaration réconciliée et migration réversible ; restauration locale autonome conservée |
| A09 | Élevée | Le bundle de configuration ne sauvegarde pas les bases, corpus ou volumes | Catalogue de sauvegardes comprenant configurations, PostgreSQL, WebUI et PVC ; restauration ciblée et cohérence des identités |
| A10 | Élevée | Un filtre de dashboard Grafana n'isole pas ses données. Un Viewer peut interroger sa datasource | Prometheus/datasource et Grafana isolés par tenant au départ ; télémétrie provider agrégée séparée ; tests de requêtes forgées |
| A11 | Élevée | Une DLP désactivable par modèle contredit un simple booléen fail-closed global dans un runtime réutilisé | Politique effective signée, évaluée avant persistance et à chaque appel ; garde toujours chargé ; contexte d'exécution isolé et révocation prioritaire |
| A12 | Élevée | Les connexions MCP et les documents RAG partagés ne propagent pas automatiquement les droits individuels des systèmes sources | Identité déléguée ou compte de service déclaré ; autorisation serveur et provenance avant résultats ; révocation des caches et des résultats dérivés |
| A13 | Élevée | Un builder pouvant modifier le harness et publier librement cumulerait création de code et pouvoir d'exécution | Builder produit un paquet et une proposition ; sandbox, tests, revue des permissions et publication par service contrôlé |
| A14 | Moyenne | Plusieurs versions de base restent des tags de famille (`python:3.11-slim`, `postgres:16-alpine`) | Verrouiller les digests dans le lot de qualification ; un tag numéroté ne garantit pas l'immuabilité |
| A15 | Moyenne | La CI déclenche les pushes sur `main` uniquement et les dépendances de validation ne sont pas toutes bornées | Ajouter la branche de programme et verrouiller les environnements lors des lots d'implémentation ; distinguer échec de code et dépendance absente |
| A16 | Moyenne | « Zero-Downtime » n'est pas une garantie pour Hermes/WebUI mono-écrivain | Drainage, fenêtre annoncée et `Recreate` lorsque nécessaire ; pas de second écrivain SQLite pour simuler la HA |
| A17 | Critique | Le contrôle DLP des appels LLM et le `.pth` n'empêchent pas un programme hostile d'utiliser un binaire SQLite ou une sortie HTTPS autorisée | Ne pas monter l'état Hermes dans la sandbox des programmes publiés ; limiter les sorties et passer les flux de données tenant par un broker ; annoncer les limites de toute exception Internet libre |

## Corrections issues de la revue indépendante

La relecture a relevé cinq frontières à préciser : contexte de pseudonymisation partagé entre transports A2A/LLM, sandbox distincte pour les programmes publiés, refus des dérives d'habilitation natives, attestation de recette indépendante du builder et découverte Prometheus bornée. Elles sont intégrées dans la [conception](conception.md) et dans les recettes des lots 02, 03, 05, 06, 07 et 10. Aucune de ces corrections n'est présentée comme déjà codée.

## Limites des promesses produit

- Les objets LiteLLM « Organization » et « Team » organisent des droits de passerelle ; ils n'isolent pas les PVC, les processus, les corpus ou les sauvegardes des clients.
- Le modèle Simple effectue une inférence ; le mode Agentic exécute une mission. Auto Router peut choisir le modèle dans un périmètre autorisé, jamais attribuer un outil ou une nouvelle habilitation.
- « ZDR demandé » et « rétention garantie par le fournisseur » sont deux états différents. Une route sans fournisseur admissible échoue ; elle ne se replie pas silencieusement vers une autre politique.
- Un administrateur de tenant n'accède pas automatiquement aux conversations privées. Le provider supervise l'infrastructure ; un accès de support aux contenus est une procédure exceptionnelle explicite. L'administrateur du cluster conserve des privilèges techniques : l'architecture ne promet pas un chiffrement contre lui.
- Un utilisateur peut récupérer un fichier déjà téléchargé hors de la plateforme ; la révocation ne peut effacer cette copie. L'accès aux nouvelles lectures et aux liens existants reste contrôlé.
- « Publier pour Julien » désigne un identifiant d'annuaire résolu sans ambiguïté. Un nom libre dans un prompt ne vaut ni identité ni approbation.

## Arbitrages retenus

Le demandeur a confirmé le cluster partagé renforcé et la possibilité de désactivation complète DLP/ZDR. Le [contrat de confidentialité](conception.md#politiques-de-confidentialité) et le [contrat d'isolation](conception.md#isolation-des-tenants-et-des-utilisateurs) définissent les conditions proposées. Les objectifs RPO/RTO et la capacité par tenant seront mesurés au lot 01 avant engagement d'exploitation ; ils ne sont pas inventés à partir d'une CI synthétique.
