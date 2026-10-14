# OmniRoute : routage, configuration et abonnements

OmniRoute constitue le premier choix de routage d'ArcIA. Son portail privé
est déployé et vérifié ; le raccordement générique de l'inférence reste à intégrer.
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
de route. **Le raccordement générique Hermes → OmniRoute, l'activation des
fournisseurs personnels et les routes internes restent à intégrer/qualifier.**
La configuration chiffrée des clés dispose de son parcours distinct dans ArcIA.
Le pilote conserve son relais historique filtré tant
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
comptes `ArcIA.ProviderSelfService`, une page ArcIA permettra de saisir une clé
personnelle par connexion HTTPS protégée. La cible retenue est une connexion
gérée par ArcIA et liée au propriétaire, hors du routeur OmniRoute central.
La passerelle ArcIA choisira cette route après les mêmes contrôles d'identité,
droits, budgets et filtrage cloud. Les tokens de gestion restent côté serveur.
[Décision des routes personnelles](../adr/0022-providers-personnels-sous-arcia.md).

La **configuration des clés** est codée dans `/portal/keys` : OpenRouter,
OpenAI, Anthropic et Google Gemini, une clé API par fournisseur. Saisie HTTPS,
champ mot de passe, ajout/remplacement/suppression et liste de métadonnées
uniquement. Les valeurs ne sont jamais restituées. La page est proposée
seulement avec `ArcIA.User` et `ArcIA.ProviderSelfService` ; le rôle admin seul
ne suffit pas. Les rôles sont relus via UserInfo à chaque requête.

Les valeurs sont chiffrées par AES-256-GCM dans le Secret nommé de l'emplacement
personnel ; le chiffrement authentifie `(operation, issuer, subject)`. La clé
racine séparée est conservée dans `portal-key-encryption`, montée uniquement
dans le portail. Aucun Secret fournisseur n'est monté dans Hermes.

**Enregistrée ne signifie pas active.** Le parcours conserve les clés pour la
future intégration, sans créer de connexion globale OmniRoute, appeler un
fournisseur ou modifier le relais historique. Adaptateurs personnels, OAuth,
raccordement à la passerelle et révocation d'inférence restent à qualifier.
Le statut de déploiement et les preuves courantes figurent dans
[l'état de reprise](../etat-reprise.md). [Décision](../adr/0021-cles-fournisseurs-personnelles.md).

### Installer et utiliser la configuration personnelle

```powershell
./scripts/Invoke-ClusterFoundation.ps1 -Action install_personal_keys
./scripts/Invoke-ClusterFoundation.ps1 -Action verify_personal_keys
./scripts/Invoke-ClusterFoundation.ps1 -Action inspect_personal_keys
```

L'installateur met à jour uniquement le portail existant, ses ressources de clés
et le mapper UserInfo. Fresh/Reconcile intègrent également ce parcours. Les
Secrets existants et la clé de chiffrement ne sont pas remplacés ; une clé
racine perdue avec un store non vide bloque la réapplication.

Dans Keycloak `/admin/users`, attribuer explicitement le rôle de realm
`ArcIA.ProviderSelfService` aux comptes choisis, en plus de `ArcIA.User`.
Ne pas ajouter ce rôle aux rôles par défaut ni à une règle d'admission du tenant.
Après connexion à `/portal/`, suivre **Mes clés IA**, sélectionner un fournisseur
et saisir sa clé dans le formulaire. La valeur n'est transmise ni au chat ni à
Git. Une seconde saisie remplace la clé du même fournisseur. Le bouton Supprimer
retire sa valeur du store courant ; les sauvegardes chiffrées ont leur propre rétention.

Le retrait du rôle ou la désactivation du compte interdit les requêtes suivantes.
Les configurations inactives restent conservées, sans partage avec un autre
subject. Sauvegarder les stores et la clé racine ensemble via le dispositif privé
de l'instance ; restauration et rotation restent à qualifier avant release.

### Mutualisation, secrets et OAuth

OmniRoute est partagé ; chaque utilisateur possède son runtime Hermes et ses
volumes, pas une instance complète d'OmniRoute. Les clés personnelles du lot
courant sont stockées dans ArcIA, hors du dashboard OmniRoute. L'administrateur
OmniRoute n'y a donc pas accès via ce dashboard. Les administrateurs de
l'infrastructure et du service détenant le chiffrement restent des personnes
de confiance ; le chiffrement au repos n'est pas une séparation contre eux.

La cible retenue conserve les connexions personnelles dans ArcIA, hors
OmniRoute central. Une clé technique OmniRoute par utilisateur n'est donc pas
nécessaire à ce parcours. Les comptes d'entreprise restent administrés dans
OmniRoute ; les comptes personnels restent liés à leur propriétaire dans ArcIA.

OAuth personnel reste à intégrer : bouton de connexion depuis ArcIA, state/PKCE
ou device flow selon le fournisseur, retour lié au propriétaire, stockage
chiffré, renouvellement et révocation. Le rôle spécifique reste obligatoire.
Ne pas confondre OAuth d'accès à ArcIA et OAuth d'accès à un fournisseur IA.
Les parcours supportés et conditions d'usage doivent être qualifiés par provider.

Le propriétaire a retenu OmniRoute pour les routes d'entreprise et des
providers personnels en parallèle, toujours derrière la passerelle ArcIA.
Aucune nouvelle route n'est activée par ce lot. Tous les appels cloud
restent filtrés avant export et les valeurs secrètes ne sont pas rendues au
modèle. Un endpoint libre déclaré dans Hermes ne doit pas contourner cette
frontière.

### Règles de connexion et de routage

| Situation | Connexion et routage | Autorisation ArcIA |
|---|---|---|
| Utilisateur standard | Pool d'entreprise, mode auto administré, credentials serveur | `ArcIA.User` |
| Abonnement d'entreprise | Compte/contrat/API ou OAuth autorisé ajouté par l'admin ; quotas et restrictions propres | Administration de l'instance |
| Fournisseur personnel | Route ArcIA liée au propriétaire, hors OmniRoute central ; API/OAuth protégés, contrôles et Presidio conservés ; raccordement à construire | `ArcIA.User` + **ArcIA.ProviderSelfService**, fonction activée |
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

Retrait du rôle, désactivation ou retrait du compte : révoquer l'override et
sa clé, retirer les sessions et revenir au pool d'entreprise si le compte
reste autorisé. L'activation de cette fonction reste fermée jusqu'à recette
du service serveur et du portail utilisateur ; la bibliothèque de politique
ne constitue pas une interface de self-service déployée.

## Confidentialité et classement des routes

Le choix de profil et de pool précède l'export. Pour une route cloud,
Presidio assainit messages, documents et résultats d'outils **avant que leur
contenu arrive dans un routeur ayant une sortie cloud**. Une enveloppe
authentifiée permet au relais de refuser un appel non filtré. Les hooks
OmniRoute ne constituent pas cette frontière : leur erreur ne garantit pas
à elle seule le blocage de l'appel.

Ollama/vLLM hébergés dans l'entreprise restent dans un pool interne, avec
endpoint/ports privés explicitement autorisés ; Presidio n'y est pas imposé
par défaut. Le moteur de sélection refuse un pool mélangeant local et cloud.
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
helper d'accès et enrôlement TLS IP. Les contrôles rejettent dashboard public,
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
