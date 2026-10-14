# Quickstart ArcIA

Ce parcours prépare le socle K3s/VMware, l'authentification, OmniRoute et une
première utilisation. Teams est une entrée optionnelle préparée à la fin.
La [matrice de recette](recette-fondatrice.md) précise les fonctions effectivement
qualifiées : le pilote est utilisable, une reconstruction VMware neuve et une
release de production restent à qualifier.

## 1. Préparer le contrôleur et la cible

Prévoir trois VM Debian sur VMware, stockage CSI partagé, DNS API privé et DNS
HTTPS, certificat valide, accès personnels VMware/SSH et PowerShell 7/WSL sur
le contrôleur. Les ports Kubernetes restent privés. Les dimensions et privilèges
sont détaillés dans [l'installation](../installation-k3s-codex.md) et
[la préparation](preparer-deploiement.md).

Cloner [ArcIA](https://github.com/nicolastheuil/ArcIA), puis lire `AGENTS.md`.
Sur une nouvelle cible, utiliser les formulaires locaux ; ils conservent les
valeurs sous DPAPI/ACL, hors Git et hors chat :

```powershell
./scripts/Connect-VMware.ps1
./scripts/Select-VMwareTarget.ps1
```

Fresh crée/vérifie les VM puis appelle `Configure-Foundation.ps1` lorsque
la cible est prête. `Configure-Integrations.ps1` est le formulaire historique
du pilote OpenRouter ; saisir les accès requis localement quand le bootstrap
les réclame, sans utiliser son ancien champ bot pour activer Teams. Les saisies DNS/TLS et
les préflights sont détaillés dans [le bootstrap](bootstrap.md#prérequis-et-saisies-externes).
Un certificat existant s'enrôle avec `Import-BootstrapTls.ps1` ; ne jamais le
placer dans Git. Pour une instance déjà enrôlée, conserver son état protégé et
ses identités ; passer directement au Plan Reconcile.

```powershell
# Lire les étapes et leurs dépendances, sans déploiement
./scripts/Bootstrap-Harness.ps1 -Mode Plan -Profile Fresh -ProvisionVMs
# Cible vierge désignée, après préparation des entrées et gates
./scripts/Bootstrap-Harness.ps1 -Mode Apply -Profile Fresh -ProvisionVMs
# Cible existante possédée : vérifier puis réappliquer
./scripts/Bootstrap-Harness.ps1 -Mode Plan -Profile Reconcile
./scripts/Bootstrap-Harness.ps1 -Mode Apply -Profile Reconcile
```

Fresh et Reconcile sont deux choix de cible, pas deux commandes à enchaîner.
Le manifeste comporte 59 étapes. Un arrêt sur gate/secret manquant doit être
résolu avec sa preuve et le programme local prévu ; ne pas marquer un gate
réussi pour forcer le passage. [Modes, journaux et reprise](bootstrap.md).

## 2. Activer l'authentification et créer le premier utilisateur

Keycloak local est installé par défaut, même sans Microsoft 365.

```powershell
./scripts/Show-IdentityAccess.ps1 -OpenPortal
```

Le formulaire local montre l'URL et le compte initial sans les écrire sur
stdout. Se connecter à `/admin/users`, changer le mot de passe initial et
enrôler le MFA. Créer un compte actif, mot de passe temporaire et rôle de
realm **ArcIA.User**. L'utilisateur ouvre `/`, termine sa première connexion,
puis `/portal/` prépare un espace personnel vide et ouvre Hermes. Le défaut
est huit emplacements, réglable par instance après dimensionnement.

L'administrateur peut ajouter Entra ID dans Keycloak sans retirer les comptes
locaux. Limiter le tenant et mapper explicitement `ArcIA.User` ; un login
Microsoft seul n'accorde aucun droit d'administration ou de fournisseur.
[Comptes, MFA, SSO et admission](../guides/identite-utilisateurs.md).

## 3. Configurer OmniRoute sur le LAN

OmniRoute est le routeur par défaut du contrat ArcIA. Installer et vérifier son
portail si ces étapes n'ont pas déjà été exécutées par le bootstrap :

```powershell
./scripts/Invoke-ClusterFoundation.ps1 -Action install_omniroute
./scripts/Invoke-ClusterFoundation.ps1 -Action verify_omniroute
./scripts/Show-RoutingAccess.ps1 -OpenPortal
```

Le helper ouvre `https://<domaine-instance>:20129/dashboard` vers une adresse
privée de nÅ“ud, avec validation TLS conservée, et montre le mot de passe initial
uniquement dans le formulaire local. Changer ce mot de passe dans OmniRoute.
Pour les autres postes, résoudre ce nom vers le nÅ“ud privé sur le réseau
administratif, ou utiliser le helper avec VPN. **Ne créer aucun NAT, publication
Internet, tunnel public ou règle d'Ingress publique pour ce port.**

Dans OmniRoute, préparer les connexions d'entreprise autorisées, leur
authentification API/OAuth selon le fournisseur, puis le pool de modèles et
le mode automatique retenus par l'administrateur (`auto/smart` par défaut).
Vérifier que l'abonnement couvre cet usage API : un abonnement de chat ne
constitue pas automatiquement un accès API. Définir budgets, quotas, conditions
de confidentialité et replis dans l'instance. Garder la synchronisation cloud,
les journaux de contenus et les tunnels désactivés.

Créer une clé technique ArcIA limitée aux connexions et modèles du pool,
autoriser les auto combos, désactiver compression/cache de réponses côté
routeur et conserver `noLog`. Cette clé reste côté service, jamais dans Hermes
ou les navigateurs des utilisateurs. Le portail natif est réservé aux admins.
[Configuration complète, abonnements et overrides](../guides/omniroute.md).

**État de l'intégration :** le portail privé et le contrat de sélection sont
codés ; le raccordement générique de l'inférence et le self-service fournisseur
restent à qualifier/intégrer. La configuration du dashboard ne rebascule pas
à elle seule le pilote existant. Celui-ci conserve son chemin Presidio → relais
OpenRouter avec sa politique d'instance gratuite/ZDR jusqu'à une migration
qualifiée. [État courant](../etat-reprise.md).

## 4. Démarrer l'utilisation d'ArcIA

Sur un poste utilisateur disposant du DNS privé, ouvrir le domaine HTTPS
de l'instance ; sur le contrôleur de qualification :

```powershell
./scripts/Open-ArcIA.ps1
```

Se connecter avec le compte `ArcIA.User`, attendre la préparation de l'espace,
puis envoyer une demande synthétique simple, par exemple « Explique les
capacités disponibles dans cet espace ». Revenir au portail et vérifier que
le même compte retrouve son espace. Avec un second compte, vérifier que les
conversations et documents personnels du premier ne sont pas visibles.

Le RAG et les outils n'affichent que les ressources déjà autorisées. Importer
les corpus réels dans le dépôt/configuration d'instance après qualification de
leur ingestion et de leurs ACL. Par défaut, **Presidio précède chaque sortie
cloud** ; Ollama/vLLM internes suivent une route privée sans Presidio par
défaut. Un repli cloud impose le filtrage avant export. Ni gratuité ni ZDR
ne sont des obligations du produit : ce sont des politiques d'instance.
[RAG](../guides/connaissance-documentaire.md) ·
[Confidentialité](../guides/confidentialite-cloud.md) ·
[Recette multi-utilisateur](../guides/multi-utilisateur.md).

Pour un utilisateur standard, le modèle et les replis sont ceux du mode
intelligent/automatique administré. La connexion d'un fournisseur personnel
exige le rôle distinct **ArcIA.ProviderSelfService**, une fonction activée par
l'admin, et une liaison serveur au propriétaire. Aucun rôle fournisseur n'est
attribué automatiquement par SSO. Le parcours self-service n'est pas encore
une fonction du portail utilisateur déployé.

## 5. Setup Teams optionnel

Teams n'est pas requis pour utiliser le portail. L'adaptateur de messages et
le service d'approbations restent à développer ; préparer Azure ne les rend
pas opérationnels. L'[annexe Microsoft 365](../annexes/integration-microsoft365.md)
est la procédure administrateur complète, avec séparation des applications,
permissions minimales, références protégées et recette.

1. Réserver un domaine bot HTTPS distinct du portail, une application Entra
   **ArcIA-Teams** mono-tenant et une ressource **Azure Bot Single Tenant**
   utilisant ce client ID. Conserver tenant/client/Object IDs dans l'instance,
   credential du bot dans le programme/coffre protégé. Configurer le messaging
   endpoint `https://<domaine-bot>/api/teams/messages` et activer le canal Teams.
   Cet endpoint public étroit concerne le bot ; il n'expose ni OmniRoute ni K3s.
2. Dans **Expose an API**, définir `api://botid-<client-id>`, le scope délégué
   `access_as_user` et les tokens v2. Préautoriser les clients Teams desktop/mobile
   `1fec8e78-bce4-4aaf-ab1b-5451cc387264` et web
   `5e3ce6c0-2b1f-4285-8d4b-75ee78787346` pour ce seul scope. Ajouter le redirect
   Web `https://token.botframework.com/.auth/web/redirect`.
3. Créer la connexion OAuth Azure Bot **ArcIA-Teams-SSO**, Entra v2, tenant
   explicite, Token Exchange URL égale à l'API URI, scopes `openid profile`.
   Affecter les pilotes à `ArcIA.User` et imposer MFA selon la politique du tenant.
   Les droits Graph Mail/Sites/lecture globale des chats ne sont pas requis.
4. Préparer le package Teams validé : GUID d'app stable distinct du client ID,
   icônes conformes, `bots[0].botId` = client ID, `scopes=["personal"]`,
   `webApplicationInfo.id/resource` cohérents et `validDomains` explicites.
   Publier dans le catalogue de l'organisation pour le groupe pilote uniquement.
   [Package, SSO et publication](../annexes/integration-microsoft365.md#63-package-et-publication-teams).
5. Copier le [gabarit d'instance](../../examples/microsoft365/microsoft365.yaml),
   renseigner les IDs et références de credentials, laisser les fonctions
   métier non utilisées inactives. Valider puis inspecter le plan hors ligne :

   ```powershell
   python scripts/microsoft365_config.py validate --config <fichier-instance-protege>
   python scripts/microsoft365_config.py plan --config <fichier-instance-protege>
   ```

   Le plan ne déploie rien. Garder `enabled=false` et `teams.enabled=false`
   jusqu'à la disponibilité et la recette de l'adaptateur.
6. Avant activation, qualifier signature du canal, tenant, identité SSO et RBAC
   serveur, liaison au même propriétaire Hermes, déduplication des messages et
   retrait d'accès. Tester Desktop/Web/mobile avec deux comptes et un compte
   hors tenant. Une activité Teams ne peut pas déclarer elle-même son identité.
   Les cartes d'approbation nécessitent ensuite hash de plan, rôle éligible,
   expiration, usage unique et contrôle serveur ; leur absence garde les
   écritures externes à risque fermées.

Les URI/permissions exactes et les évolutions du SDK sont à relire dans
[la procédure Teams](../annexes/integration-microsoft365.md#6-teams--bot-personnel-et-authentification-utilisateur)
et les sources Microsoft qu'elle référence avant chaque activation.

## 6. Vérifier et exploiter

```powershell
./scripts/Bootstrap-Harness.ps1 -Mode Apply -Profile Verify
./scripts/Bootstrap-Harness.ps1 -Mode Audit
```

Verify peut exécuter des requêtes synthétiques au fournisseur déjà autorisé ;
Audit inspecte les états. Consulter [l'état de reprise](../etat-reprise.md),
[l'exploitation](exploitation-qualification.md), [la sauvegarde](sauvegarde-reconstruction.md)
et [la matrice de recette](recette-fondatrice.md). Une CI synthétique ou un
portail accessible ne prouve pas la HA, la reprise de données ou un rebuild neuf.
