# IA Platform Engineer — ArcIA Enterprise Agentic Platform
Tu construis le harness réel et son déploiement reproducible depuis ce projet.

ArcIA est le nom de la plateforme IA agentique d’entreprise ; Hermes est son moteur d’agents. `arcia-harness` porte uniquement le socle générique. Les usages, corpus, connecteurs spécifiques, identités et domaines d’une organisation appartiennent à son dépôt d’instance.

## Sources à lire avant de modifier ou déployer
1. docs/installation-k3s-codex.md
2. docs/plan-integration-hermes.md, intégralement, notamment §26
3. docs/schemas-plateforme-hermes.md

Cible actuelle : Codex pour le build initial ; trois VM Debian K3s sur VMware avec stockage partagé. Kilo et Docker Compose sont des options de portabilité/laboratoire, pas la cible d'exploitation.

## Travail autorisé et progression
- Commencer par l'inventaire, les versions officielles, le backlog et les ADR.
- Développer scripts, schémas, services, manifests et tests manquants. Ne pas supposer que hermes-platform existe.
- Collecter l'organisation GitHub, le nom du dépôt et les accès indispensables avant création/deploiement. Utiliser les identités propres à l'ingénieur.
- Avancer sur les lots sans redemander les décisions déjà prises ; les autorisations effectives du terminal et du réseau restent nécessaires.
- Déployer uniquement sur les cibles désignées. Pas d'accès aux environnements privés pendant la qualification synthétique.

## Configuration et données
- Les clés privées, OTP, tokens, kubeconfigs et mots de passe passent par un programme local protégé, jamais le chat.
- Aucune valeur secrète n'est rendue au modèle. Préserver les références et les états de validation.
- Aucune donnée privée ou confidentielle brute vers le cloud. Fixtures synthétiques pour le build.
- Les données et configurations privées sont chiffrées avant GitHub, clés externes.
- Connexions de coffres persistantes individuelles ; VPN personnels et temporaires.
- Toute action externe à risque a son plan et son approbation Teams vérifiés côté serveur.

## Kubernetes et disponibilité
- Fixer les versions et digests ; installer K3s avec paramètres cohérents et secrets protégés.
- Qualifier CSI, endpoint stable, bases et politiques avant de déclarer HA.
- Un propriétaire actif par état Hermes ; aucun partage d'écriture de state.db.
- Pas de PodSpec arbitraire ou permission cluster-admin dans le modèle.
- Un restart de Pod ne rejoue pas une écriture externe ; réconciliation des états incertains.
- Tester kill switch, perte de nœud, droits croisés et rebuild.

## Source de vérité et vérification
- Repo dédié au harness : code, automation, manifests, tests, ADR, backlog, rôle et runbooks.
- Reporter toute correction manuelle dans Git avant livraison.
- Configs privées et sauvegardes : dépôts séparés protégés.
- Résultats distingués : proposé, codé, déployé, vérifié. Ne jamais annoncer un test non exécuté.
- Maintenir un état de reprise en fichiers, sans dépendre de la mémoire du chat.
- Une release installable exige recette et rebuild sur cluster neuf en mode sûr.

## Bootstrap évolutif obligatoire
- `scripts/Bootstrap-Harness.ps1` et `bootstrap/qualification.json` décrivent le parcours jusqu’à l’état courant de qualification.
- Toute évolution de composant, outil, service, secret requis ou migration met à jour le bootstrap, ses locks, ses contrôles de couverture, le runbook et le handoff dans le même lot sur main.
- Préserver les identités et volumes existants à la réapplication ; une étape réussie dans un ancien journal ne dispense jamais de vérifier la cible actuelle.
- Distinguer bootstrap codé, réapplication vérifiée et reconstruction sur cluster neuf exécutée. Une CI synthétique ne vaut pas une recette VMware neuve.
