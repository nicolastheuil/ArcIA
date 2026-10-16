# OmniRoute : routage complémentaire, combos et abonnements (v0.2)

Dans **ArcIA v0.2**, **[LiteLLM Proxy](inference-litellm.md)** (`litellm-proxy:4000`) est devenu la **passerelle LLM centrale par défaut** (car elle porte nativement le guardrail `pre_call` Presidio DLP pour Open-WebUI, Hermes Agent et Teams Bot).

**OmniRoute v3.8.51** (`omniroute:20128` / `:20129`) est **conservé comme brique complémentaire optionnelle** ([deploy/manifests/09-omniroute.yaml](../../deploy/manifests/09-omniroute.yaml)) pour répondre à trois besoins que LiteLLM ne couvre pas nativement de la même façon :
1. **Un portail graphique d'administration LAN (`:20129/dashboard`)** pour construire visuellement des chaînes de fallback (*Combos* `auto`, `auto/smart`, `auto/coding`, `auto/cheap`).
2. **L'agrégation d'abonnements OAuth et de pools de clés en rotation**, utilisables comme fournisseur amont (*upstream*) derrière LiteLLM (`http://omniroute.arcia.svc.cluster.local:20128/v1`).
3. **La séparation stricte entre profils administrés et self-service** : un utilisateur standard utilise toujours le mode intelligent/automatique choisi par l'administrateur, sans pouvoir imposer de destination libre depuis son prompt. Le budget, les fournisseurs et les exigences ZDR/résidence appartiennent à l'instance. Voir le [Quickstart](../runbooks/quickstart.md).

## État et version

Version verrouillée **3.8.51**, source
[`c1e30b7`](https://github.com/diegosouzapw/OmniRoute/tree/c1e30b7676975feb298b49eff6ff58923c04b89e).
Le paquet npm est vérifié par SHA-512 avant extraction, sans scripts npm
d'installation ; l’arbre de dépendances est celui du lock npm existant. Les
manifests imposent un seul écrivain et deux PVC RWOP
(runtime 5 Gio, données 5 Gio), sans compte Kubernetes dans le Pod. La
réapplication conserve clés, mot de passe modifié et volumes ; une modification
de runtime nécessite une migration administrative explicite.

Le serveur et le portail LAN sont codés dans le bootstrap ; leurs résultats
de déploiement sont consignés dans [l'état courant](../etat-reprise.md).
La bibliothèque de politique contrôle mode, rôle, propriétaire et classe
de route. **Le raccordement générique Hermes → OmniRoute, les fournisseurs
personnels dans le portail utilisateur sont codés et restent à qualifier ; les routes internes restent à intégrer/qualifier.** Le pilote conserve son relais historique filtré tant
que cette migration n'est pas qualifiée.

## Déploiement et Accès dans ArcIA v0.2

OmniRoute est déployé dans le namespace applicatif unifié `arcia` via [deploy/manifests/09-omniroute.yaml](../../deploy/manifests/09-omniroute.yaml) :
- **Service interne** : `omniroute.arcia.svc:20128`
- **Volume persistant** : PVC 5Gi (`omniroute-pvc`) pour stocker la configuration et les clés
- **Portail d'administration LAN** : port `20129`, accessible en réseau local ou VPN

Pour activer OmniRoute dans votre déploiement :
1. Renseigner `omniroute.enabled: true` dans `arcia.config.yaml`.
2. Déployer via `python scripts/deploy.py --config arcia.config.yaml` ou `.\scripts\Deploy-ArcIA.ps1`.
3. Vérifier le bon fonctionnement du service :
   ```powershell
   .\scripts\Invoke-K3s.ps1 "get pods -n arcia -l app=omniroute"
   ```

Le dashboard natif donne une vue administrative globale des connexions et des quotas.
**Ne pas distribuer son mot de passe aux utilisateurs** : il ne fournit pas
à lui seul la séparation de leurs comptes personnels.

Le namespace du relais porte l'exception PSA nécessaire au hostPort, comme
l'ingress HTTPS existant. Le routeur garde PSA restricted ; chaque conteneur
du relais reste non-root, sans capacités, avec rootfs readonly et sans token
Kubernetes. Cette exception ne donne aucun droit Kubernetes aux agents.

## Configuration de base administrateur

1. Garder le login obligatoire, désactiver tunnels/synchronisation cloud,
   journalisation des corps et clés, et exposition publique. Les noms des
   menus peuvent évoluer ; utiliser la documentation de la version verrouillée.
2. Dans les connexions/providers, ajouter les identités d'entreprise requises :
   clé API, endpoint compatible ou OAuth officiellement supporté. Conserver
   ownership, inventaire, rotation et autorisation d'usage dans l'instance.
3. Constituer un pool explicite de connexions et modèles, limites de requêtes,
   concurrence, budgets et replis. Séparer les pools **cloud** et **internes**.
   Les quotas du routeur complètent les contrôles/budgets du fournisseur ;
   `0` n'est pas une façon générique d'interdire une dépense.
4. Choisir un mode automatique : `auto` équilibré, `auto/smart` intelligent,
   `auto/coding`, `auto/fast`, `auto/cheap` ou `auto/offline`, selon les modèles
   autorisés et disponibles. Le défaut ArcIA est `auto/smart`. Les modes et
   candidats doivent être relus avec la version épinglée.
5. Émettre une clé technique par périmètre, avec `allowedConnections`
   explicites, `modelAccessMode=restricted`, `allowedModels/allowedCombos`
   explicites et `allowAutoCombos=true`. Fixer `noLog=true`,
   `compressionEnabled=false`, `cacheDefaultMode=bypass` ; limiter les endpoints
   au parcours réellement exposé. Stocker seulement sa référence dans Git,
   sa valeur dans le coffre/Secret du service de routage.
6. Qualifier les refus : autre connexion, autre modèle, clé révoquée, budget
   atteint, absence de route conforme et tentative de destination fournie par
   l'appelant. Ne pas activer un repli qui élargit la politique de l'instance.

Les [modes auto de cette version](https://github.com/diegosouzapw/OmniRoute/blob/c1e30b7676975feb298b49eff6ff58923c04b89e/docs/getting-started/AUTO-COMBO-GUIDE.md)
et les [permissions des clés](https://github.com/diegosouzapw/OmniRoute/blob/c1e30b7676975feb298b49eff6ff58923c04b89e/src/shared/validation/schemas/keys.ts)
définissent les capacités natives. ArcIA ajoute ses propres contrôles de
propriétaire et de sortie : une API key native ne remplace pas son RBAC.

## Entreprise et fournisseurs personnels

### Capacités natives et responsabilité d'ArcIA

Dans la version 3.8.51, l'unité de contrôle native est principalement **la clé
API**, avec connexions autorisées, modèles/combos, quotas et réglages par clé.
Les scopes self-service natifs `self:usage` et `self:account-quota` concernent
la consultation de consommation/quota. Ils ne donnent pas le droit de créer
une connexion fournisseur personnelle. L'API de création de providers utilise
le contrôle de gestion ; une session dashboard authentifiée ou un token de
gestion peut agir sur les connexions globales.

Sources de la version épinglée :
[permissions des clés](https://github.com/diegosouzapw/OmniRoute/blob/c1e30b7676975feb298b49eff6ff58923c04b89e/src/shared/validation/schemas/keys.ts),
[scopes self-service](https://github.com/diegosouzapw/OmniRoute/blob/c1e30b7676975feb298b49eff6ff58923c04b89e/src/shared/constants/selfServiceScopes.ts),
[contrôle des API de gestion](https://github.com/diegosouzapw/OmniRoute/blob/c1e30b7676975feb298b49eff6ff58923c04b89e/src/lib/api/requireManagementAuth.ts).

ArcIA porte donc les comptes humains et leurs droits, et conserve OmniRoute
comme routeur. Exemple : l'admin configure la chaîne d'entreprise et ses API
keys ; tous les utilisateurs suivent cette chaîne automatique. Pour les seuls
comptes `ArcIA.ProviderSelfService`, la page ArcIA `/personal/` permet de saisir une clé
personnelle par connexion HTTPS protégée. Le service vérifie rôle et identité,
crée une connexion liée à ce propriétaire, émet une clé technique restreinte et
applique un override borné. Il ne remet jamais le token global de gestion à
l'utilisateur. La politique d'instance et Presidio cloud restent applicables.

Ce parcours est **codé, déployé et vérifié** sur fixtures locales, avec page
`/personal/` sur le même portail LAN OmniRoute, OIDC/PKCE ArcIA, contrôle en ligne
des rôles et filtrage Presidio. Aucune inférence n'est exécutée par cette recette. Le dashboard natif `/dashboard`
reste une interface globale d'administration ; son login OIDC global est fermé
sur le relais LAN pour éviter de transformer une connexion ArcIA en droit admin.

#### Parcours utilisateur et administrateur

L'administrateur configure les abonnements/endpoints d'entreprise dans le
dashboard natif, puis ouvre `/personal/` avec son compte **ArcIA.User + ArcIA.Admin**.
Il sélectionne les connexions d'entreprise, les modèles autorisés et le mode
intelligent/automatique. Le pool initial est vide : aucune route ni dépense
n'est activée implicitement. Il active ensuite les connexions personnelles
et attribue les droits aux seuls comptes concernés via le SSO d'entreprise.
Ce rôle n'est attribué automatiquement à personne.

Un utilisateur standard suit le pool d'entreprise. Un utilisateur autorisé voit
« Mes clés API », ajoute sa connexion puis choisit de l'utiliser ou de revenir
au pool d'entreprise. Les fournisseurs API personnels initiaux sont OpenAI,
Anthropic, Gemini et OpenRouter, restreints par l'admin. Aucun endpoint libre,
proxy, priorité globale ou rôle ne vient du navigateur. Un pool personnel
indisponible refuse la demande sans débiter implicitement le pool d'entreprise.
Le retrait du rôle revient au pool d'entreprise ; la désactivation du compte
ferme toute inférence. Les droits sont relus auprès du fournisseur d'identité à chaque demande.

Hermes appelle le gateway interne avec son identité technique bornée ;
le propriétaire vient du binding serveur, jamais du prompt. Le mode imposé et
le pool choisi produisent une clé native limitée aux connexions/modèles, sans
scope de gestion, sans logs ni cache partagé. Presidio filtre ensuite le contenu
avant l'appel OmniRoute cloud. Le relais LAN n'expose pas cette API d'inférence.
L'ajout d'une clé personnelle utilise l'API bulk sans validation automatique :
aucun test de modèle payant n'est déclenché par ArcIA à la saisie.

```powershell
.\scripts\Deploy-ArcIA.ps1
.\scripts\Apply-Secrets.ps1
```

Les sessions et clés techniques ArcIA sont chiffrées dans un volume persistant
dédié sur PVC. Les clés fournisseurs restent dans le stockage natif chiffré
OmniRoute. Un état de création incertain se réconcilie par nom serveur unique ;
un restart ne rejoue pas la création. Sauvegarder les volumes de manière
cohérente, avec les clés de chiffrement externes.

### Règles de connexion et de routage

| Situation | Connexion et routage | Autorisation ArcIA |
|---|---|---|
| Utilisateur standard | Pool d'entreprise, mode auto administré, credentials serveur | `ArcIA.User` |
| Abonnement d'entreprise | Compte/contrat/API ou OAuth autorisé ajouté par l'admin ; quotas et restrictions propres | Administration de l'instance |
| Fournisseur personnel | Connexion isolée, clé scoped à ses connexions, override borné au propriétaire ; mode dans les limites admin | `ArcIA.User` + **ArcIA.ProviderSelfService**, fonction activée |
| Ollama/vLLM interne | Endpoint privé et modèle déclaré par l'admin ; pool distinct | Accès ArcIA + droit de route interne |

Ne pas assimiler abonnement ChatGPT/Claude/Copilot et accès API : utiliser
uniquement la méthode et les conditions supportées pour le fournisseur concerné.
Une connexion personnelle n'élargit ni budget d'entreprise, ni ACL, ni sortie
cloud, ni droits d'outil. Sans rôle spécifique, aucune option de connexion
personnelle et aucun override ne sont proposés.

Le rôle **ArcIA.ProviderSelfService** n'est ni un rôle admin, ni un droit
automatiquement déduit d'une adresse email. Avant connexion, un service doit
vérifier la session SSO, le compte actif et les droits attribués.
Le propriétaire stable est identifié par le jeton SSO Microsoft Entra ID `(tid, oid)`. Les clés/connexions ne sont
jamais partagées avec un autre sujet, y compris après suppression/recréation
d'un compte portant le même nom.

Le retrait du rôle ferme immédiatement l'override à la prochaine demande
contrôlée et revient au pool d'entreprise si le compte reste autorisé. Le
changement de pool remplace sa clé technique ; désactivation/suppression
du compte refuse toute demande. Les clés techniques restent privées côté
service. La purge des connexions d'un compte supprimé et la rotation globale
exigent une procédure d'exploitation ; elles ne réaffectent pas ses clés à
un autre propriétaire. La fonction reste désactivée par défaut dans chaque instance.

## Confidentialité et classement des routes

Le choix de profil et de pool précède l'export. Pour une route cloud,
Presidio assainit messages, documents et résultats d'outils **avant que leur
contenu arrive dans un routeur ayant une sortie cloud**. Le gateway appelle le filtre local authentifié, puis la seule API loopback
OmniRoute avec la clé scoped ; Hermes n'accède pas directement à cette API.
Le relais historique OpenRouter conserve, séparément, son attestation HMAC. Les hooks
OmniRoute ne constituent pas cette frontière : leur erreur ne garantit pas
à elle seule le blocage de l'appel.

Ollama/vLLM hébergés dans l'entreprise restent dans un pool interne, avec
endpoint/ports privés explicitement autorisés ; Presidio n'y est pas imposé
par défaut. La bibliothèque de politique refuse un pool mélangeant local et cloud.
Le gateway déployé de ce lot qualifie uniquement la classe cloud : ne pas
ajouter Ollama/vLLM aux pools actuellement utilisés par celui-ci.
Un repli interne → cloud requiert une nouvelle sélection et le filtrage avant
le premier export ; on ne laisse pas OmniRoute basculer spontanément entre
ces classes sur une requête brute.

Le pilote a choisi gratuité, ZDR et collecte interdite. Ces contraintes sont
sa politique propre, pas le comportement obligatoire d'une autre instance.
Ni `auto/cheap`, ni un nom « free » ne prouvent ZDR, résidence ou coût nul.
Les restrictions doivent être appliquées et testées au niveau du fournisseur
effectif. [Gouvernance Presidio DLP](confidentialite-presidio.md).

## Déploiement et exploitation

Le déploiement applique le binding OmniRoute, conserve les versions et volumes PVC, et refuse une modification non contrôlée du runtime. Les contrôles rejettent dashboard public et sortie cloud sans filtrage Presidio. Le [déploiement universel](deploiement-universel.md)
installe les services dans l'ordre strict de dépendance.
La vérification du portail n'exécute aucune inférence et ne contourne pas TLS.

Sauvegarder de manière cohérente le PVC des données et les secrets de
chiffrement/signature dans le dispositif de sauvegarde de l'instance ; la
perte d'une clé peut rendre les connexions irrécupérables. Tester restauration,
rotation et refus d'un second propriétaire avant une release. Le runtime
SQLite unique ne devient pas HA parce que les trois relais TLS sont présents.
[Sauvegarde/reconstruction](../runbooks/sauvegarde-reconstruction.md) ·
[Backlog](../backlog.md) · [Architecture](../architecture.md).

La synchronisation cloud native est désactivée et relue après application,
avec la route officielle `POST /api/sync/cloud` limitée à `action=disable`.
Cette opération exige l'absence d'URL cloud et n'effectue aucun appel cloud.
Les routes de synchronisation, tunnel et login OIDC global restent fermées sur
le relais LAN ; le mot de passe admin existant est préservé.

L'état de qualification opérationnelle du service est documenté dans [l'état de reprise](../etat-reprise.md).
La compatibilité des endpoints fournisseurs, les quotas, le débit payant et
le streaming token par token ne sont pas attestés par cette recette.
