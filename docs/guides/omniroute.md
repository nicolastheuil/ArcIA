# OmniRoute : routage, configuration et abonnements

OmniRoute constitue le premier choix de routage d'ArcIA. Son portail privé
est déployé et vérifié ; le self-service et le raccordement cloud sont codés, en cours de recette.
Un utilisateur
standard utilise toujours le mode intelligent/automatique choisi par
l'administrateur ; il ne choisit ni destination libre, ni credential, ni
repli depuis son prompt. Le budget, les fournisseurs et les exigences
ZDR/résidence appartiennent à l'instance. [Quickstart](../runbooks/quickstart.md#3-configurer-omniroute-sur-le-lan).

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

## Portail d'administration privé

Namespace applicatif `arcia-routing` sous PSA restricted, Service interne
`omniroute:20128` ; relais TLS LAN dans `arcia-routing-lan`
sur **20129**, accessible par la **VIP HTTPS privée**. Le défaut filtre les
CIDR RFC1918 explicites du réseau cible. Une instance dont les VM/VIP sont
exclusivement LAN/VPN derrière son firewall peut autoriser explicitement toutes
les IP sources : `-AuthorizeAllPrivateRouterSources` enregistre cette frontière
privée dans sa politique, préservée à la réapplication. Ce choix ne publie
aucun service sur Internet. L'authentification reste obligatoire.
Le nom HTTPS de l'instance sert de SNI ; le navigateur administratif le résout
vers la VIP. Aucun Ingress, LoadBalancer, NAT ou tunnel public n'est
créé. Avec le filtre CIDR par défaut, une connexion venant d'un autre réseau
est refusée ; les chemins
d'inférence du dashboard sont fermés sur ce relais de gestion.

```powershell
./scripts/Invoke-ClusterFoundation.ps1 -Action install_omniroute
./scripts/Invoke-ClusterFoundation.ps1 -Action verify_omniroute
./scripts/Invoke-ClusterFoundation.ps1 -Action inspect_omniroute
./scripts/Show-RoutingAccess.ps1 -OpenPortal
```

JWT, chiffrement du stockage, signature des API keys et mot de passe initial
sont générés localement côté worker. Les valeurs ne sortent que par I/O
protégée vers DPAPI et formulaire local. Changer le mot de passe initial
dans le dashboard ; sa valeur nouvelle n'est pas récupérable par le helper.
Vérifier le certificat et le DNS privé après renouvellement. Une adresse
administrative VPN privée peut être enrôlée seule avec
`-AuthorizePrivateRouterController`, sur autorisation explicite. Une autorisation
de toutes les sources exige la déclaration de frontière firewall privée ci-dessus ;
elle n'est pas le défaut d'une nouvelle instance.

### Accès HTTPS directement par IP

Un certificat public pour le domaine ne couvre pas une VIP RFC1918. Le listener
IP nécessite un certificat interne avec cette VIP dans son SAN, et une confiance
explicite sur chaque poste client. Le domaine conserve son certificat public.
Le listener IP accepte le Host de la VIP et refuse les autres noms ; le proxy
conserve le port dans Host/Origin pour les contrôles d'authentification/CSRF.

```powershell
# Générer/enrôler le certificat IP sans modifier la confiance du poste
./scripts/Enable-RoutingIpAccess.ps1
# Seulement après accord de l'opérateur : confiance pour ce compte Windows
./scripts/Enable-RoutingIpAccess.ps1 -TrustCurrentUser
./scripts/Show-RoutingAccess.ps1 -OpenPortal -UseIp
```

La clé serveur reste dans `routing-ip-tls.dpapi` et le Secret TLS dédié ; seul
le certificat public `.cer` est exporté. La confiance ne fait pas partie de
Fresh/Reconcile ; aucun autre poste n'est modifié. Le certificat est valable
un an et sa rotation exige une procédure contrôlée ; ni certificat ni clé
existants ne sont régénérés silencieusement. Une autre instance peut fournir
sa PKI interne après adaptation/qualification de l'enrôlement.

Le dashboard natif donne une vue administrative globale des connexions.
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
et attribue **ArcIA.ProviderSelfService** aux seuls comptes concernés dans Keycloak.
Ce rôle est créé par le bootstrap et n'est attribué automatiquement à personne.

Un utilisateur standard suit le pool d'entreprise. Un utilisateur autorisé voit
« Mes clés API », ajoute sa connexion puis choisit de l'utiliser ou de revenir
au pool d'entreprise. Les fournisseurs API personnels initiaux sont OpenAI,
Anthropic, Gemini et OpenRouter, restreints par l'admin. Aucun endpoint libre,
proxy, priorité globale ou rôle ne vient du navigateur. Un pool personnel
indisponible refuse la demande sans débiter implicitement le pool d'entreprise.
Le retrait du rôle revient au pool d'entreprise ; la désactivation du compte
ferme toute inférence. Les droits sont relus auprès de Keycloak à chaque demande.

Hermes appelle le gateway interne sur 20131 avec son identité technique bornée ;
le propriétaire vient du binding serveur, jamais du prompt. Le mode imposé et
le pool choisi produisent une clé native limitée aux connexions/modèles, sans
scope de gestion, sans logs ni cache partagé. Presidio filtre ensuite le contenu
avant l'appel OmniRoute cloud. Le relais LAN n'expose pas cette API d'inférence.
L'ajout d'une clé personnelle utilise l'API bulk sans validation automatique :
aucun test de modèle payant n'est déclenché par ArcIA à la saisie.

```powershell
./scripts/Invoke-ClusterFoundation.ps1 -Action install_omniroute
./scripts/Invoke-ClusterFoundation.ps1 -Action install_routing_access
./scripts/Invoke-ClusterFoundation.ps1 -Action verify_routing_access
```

Les sessions et clés techniques ArcIA sont chiffrées dans un SQLite distinct,
`arcia-self-service/state.db`, sur le même PVC et le même propriétaire Pod que
le routeur. Les clés fournisseurs restent dans le stockage natif chiffré
OmniRoute. Un état de création incertain se réconcilie par nom serveur unique ;
un restart ne rejoue pas la création. Sauvegarder les deux bases de manière
cohérente, avec les clés de chiffrement externes. Le service technique Keycloak
est limité à la lecture des utilisateurs/rôles ; le token Kubernetes du seul
sidecar lit uniquement les ConfigMaps `slot-binding` des espaces fixés.

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
vérifier signature OIDC, compte actif, `ArcIA.User`, rôle spécifique et switch
d'instance. Le propriétaire stable est `(issuer, subject)` Keycloak, avec
mapping contrôlé depuis `(tid, oid)` pour Entra. Les clés/connexions ne sont
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
effectif. [Politique cloud et limites Presidio](confidentialite-cloud.md).

## Bootstrap, preuves et exploitation

`bootstrap/routing.lock.json` couvre runtime, politique, renderer, worker,
helper d'accès, enrôlement TLS IP, page personnelle, stockage, identité, gateway
et rendus canoniques. Le bootstrap réapplique le binding OmniRoute, conserve
les versions/UID/PVC et refuse une modification concurrente du runtime. Les contrôles rejettent dashboard public,
ouverture de toutes les sources sans déclaration firewall privée, absence du rôle
spécifique et sortie cloud sans défaut Presidio. Le [bootstrap](../runbooks/bootstrap.md)
installe après Privacy, vérifie le service et les trois relais LAN, puis
inspecte lors d'Audit. La recette vérifie TLS/SNI et refus des routes de gestion,
inférence et publication depuis le LAN et, si autorisé, le contrôleur et la VIP.
La vérification du portail n'exécute aucune inférence et ne contourne pas TLS.

Sauvegarder de manière cohérente le PVC des données et les secrets de
chiffrement/signature dans le dispositif de sauvegarde de l'instance ; la
perte d'une clé peut rendre les connexions irrécupérables. Tester restauration,
rotation et refus d'un second propriétaire avant une release. Le runtime
SQLite unique ne devient pas HA parce que les trois relais TLS sont présents.
[Sauvegarde/reconstruction](../runbooks/sauvegarde-reconstruction.md) ·
[Backlog](../backlog.md) · [ADR du périmètre](../adr/0020-perimetre-harness-et-politiques-instance.md).

La synchronisation cloud native est désactivée et relue après application,
avec la route officielle `POST /api/sync/cloud` limitée à `action=disable`.
Cette opération exige l'absence d'URL cloud et n'effectue aucun appel cloud.
Les routes de synchronisation, tunnel et login OIDC global restent fermées sur
le relais LAN ; le mot de passe admin existant est préservé.

Preuve datée : [self-service, droits et filtrage sans inférence](../qualification/2026-10-14-omniroute-self-service.json).
La compatibilité des endpoints fournisseurs, les quotas, le débit payant et
le streaming token par token ne sont pas attestés par cette recette.
