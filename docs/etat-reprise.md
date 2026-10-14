# État de reprise d’ArcIA — 14 octobre 2026

**Unique handoff courant.** Les [archives](archives/README.md) sont historiques.
Le [backlog](backlog.md) porte les suites ; les [runbooks](README.md#exploitation)
portent les procédures. Distinguer proposé, codé, déployé et vérifié.

## Référence et lot courant

Dépôt **[nicolastheuil/ArcIA](https://github.com/nicolastheuil/ArcIA)**,
branche **main** ; renommage GitHub exécuté et remote local aligné. Le dépôt
est actuellement public ; les paramètres sensibles et corpus d'instance restent
externes et protégés. Le nom historique de répertoire administratif
`ArcIA-Harness` est conservé pour préserver identités, bundles et volumes.
Dernière livraison avant les corrections VIP/TLS : `e111ffc`.

Le nettoyage documentaire précédent a regroupé 12 guides, archivé 15 handoffs
suivis et deux rapports, créé un index exhaustif et ajouté la validation des
liens/ancres en CI. Ce lot retire les outils de transfert personnel du périmètre
Git/bootstrap/CI, corrige les politiques d'instance, documente Teams et ajoute
le [quickstart complet](runbooks/quickstart.md) et le
[guide OmniRoute](guides/omniroute.md). Les copies personnelles sont conservées
localement hors Git ; aucun contenu secret ni archive réelle n'est déplacé ou
affiché. Les fichiers locaux non suivis préexistants sont conservés.

OmniRoute 3.8.51 dispose de son renderer, worker, politique de droits,
installation verrouillée et helper d'accès local. Le manifeste comprend
**63 étapes codées**, dont installation/vérification/inspection OmniRoute. Le
[lock](../bootstrap/routing.lock.json), les contrôles de couverture, le
[runbook](runbooks/bootstrap.md) et l'[ADR 0020](adr/0020-perimetre-harness-et-politiques-instance.md)
sont alignés. La bibliothèque refuse dashboard public, override sans rôle,
autre propriétaire et pool mélangeant cloud/interne.

## Dernier état fonctionnel consigné

| Domaine | Résultat acquis | Limites |
|---|---|---|
| Infrastructure | Trois serveurs K3s/VMware, CPI/CSI, CNPG/PostgreSQL, Hermes et HTTPS ; bascule contrôlée | Panne brutale, fencing, restore complet et rebuild neuf non qualifiés |
| Knowledge / Privacy | RAG synthétique local, RLS, modèles locaux ; appel HTTP 200 sous politique d'instance gratuite/ZDR ; refus Internet/DNS depuis Hermes | Groupes, OCR et collecte métier à compléter ; relais pilote spécialisé |
| Skills / contexte | 539 entrées upstream, sept adaptations ; RTK et Headroom bornés ; 55 sondes par runtime | Context7 externe fermé ; procédures et benchmarks à élargir |
| OmniRoute | Serveur privé déployé/vérifié, une instance avec volumes conservés, trois relais TLS LAN 20129 ; HTTPS sur VIP par domaine et IP, confiance Windows explicitement installée sur le PC autorisé | Self-service PKCE et binding cloud déployés/vérifiés sur fixtures ; providers réels et routes internes à configurer/qualifier ; aucune activation implicite |
| Identité | Comptes locaux permanents, portail personnel, admin nommé récupéré ; rôle et espace d'un compte Microsoft relus | Login Microsoft confirmé par le propriétaire ; recette interactive complète, autre tenant, groupes et HA/restore à qualifier |
| Réseau Keycloak | Sortie IPv4 publique TCP/443 du pilote ; TLS Microsoft/Graph 4/4 et refus HTTP/80 vérifiés | Destinations au pare-feu amont ; IPv6 non qualifié ; défaut générique fermé |
| Portail du pilote | Pool privé 32 places, trois liées et 29 libres au dernier relevé ; comptes désactivés conservés | Défaut générique huit ; charge de trente utilisateurs non qualifiée |
| Microsoft 365 / Teams | Annexe, contrat YAML, schéma, plan hors ligne et setup Teams documentés | Adaptateur Bot, importeur, services Graph et approbations serveur absents ; aucune configuration Azure appliquée |

Les règles génériques sont : **OmniRoute auto administré en premier routage**,
Presidio pour tous les modèles cloud par défaut, pas pour Ollama/vLLM internes
par défaut ; budgets, abonnement, gratuité et ZDR propres à l'instance. La
connexion personnelle exige **ArcIA.ProviderSelfService**, activation explicite
et propriété serveur. Le binding générique cloud est déployé ; la recette de
droits et filtrage n'atteste aucun appel fournisseur réel.

Preuves historiques : [skills](qualification/2026-10-13-skills.json),
[identité et portail](qualification/2026-10-13-portail-personnel.json),
[réseau et admission](qualification/2026-10-13-identity-public-https.json).
Preuve du lot : [portail OmniRoute, VIP et TLS](qualification/2026-10-14-omniroute.json).
Les recettes 25 étapes Reconcile, sept Verify et 200 contrôles multi-utilisateur
sont des preuves datées distinctes, pas un rebuild complet.
[Matrice de recette](runbooks/recette-fondatrice.md).

## Déploiement OmniRoute du lot

Un premier essai a rencontré un timeout SSH avant reconnexion du VPN. Sur la
cible accessible, le démarrage a révélé un répertoire de cache manquant sous
montage readonly et les dépendances absentes du paquet npm extrait seul.
Corrections reportées dans le bootstrap : préparation du cache et installation
`npm ci --ignore-scripts` depuis le lock existant, contrôle du runtime Next/SQLite
avant lancement. La réparation du démarrage initial refuse runtime prêt,
preuve de qualification antérieure et base SQLite existante ; secrets/PVC
conservés. Les service links Kubernetes sont désactivés sur le Pod : l'injection
`OMNIROUTE_PORT=tcp://…` contredisait le schéma de port entier d'OmniRoute.
Le relais `hostPort` est isolé dans `arcia-routing-lan`, exception PSA nécessaire,
avec processus non root et capacités supprimées ; le serveur et ses volumes
restent dans le namespace restreint `arcia-routing`. Les chemins temporaires
NGINX sont inscriptibles sous `/tmp`, sa configuration est immuable et versionnée
par hash ; les sondes attendent l'ouverture effective du listener TLS.

Réapplication exécutée : `OMNIROUTE_PRIVATE_PORTAL_INSTALLED`, puis
`OMNIROUTE_PRIVATE_PORTAL_VERIFIED`. Serveur prêt 1/1, relais prêts 3/3 ; HTTPS/auth,
refus d'inférence et de publication cloud/proxy vérifiés sur les trois nœuds,
depuis le contrôleur et par la VIP. Le helper pointe sur la VIP et conserve
le port dans les en-têtes du proxy.

L'ajout automatique d'une source VPN individuelle avait été refusé par la
revue automatique. Le propriétaire a ensuite explicitement autorisé toutes
les sources derrière son pare-feu LAN/VPN : exception d'instance appliquée
et conservée à la réconciliation, sans Ingress public ni tunnel. Le défaut du
harness demeure limité aux CIDR privés. L'authentification reste obligatoire.

L'accès HTTPS par IP dispose d'un certificat interne avec SAN de la VIP,
clé privée protégée hors Git et dans le Secret TLS dédié. Sa confiance a été
installée dans le magasin Windows de l'utilisateur sur son PC, après son
accord explicite. La sonde HTTPS par IP a réussi avec la confiance système,
sans désactivation de validation TLS ; aucune confiance n'a été installée sur
un autre poste. Le nom DNS conserve son certificat distinct. Voir la procédure
[HTTPS par IP](guides/omniroute.md#accès-https-directement-par-ip).

OmniRoute natif limite les clés techniques à des connexions/modèles et dispose
de scopes de consommation personnels. La gestion des providers reste une
fonction d'administration globale : le portail BYOK ArcIA par utilisateur,
avec rôle et propriétaire vérifiés côté serveur, reste à développer. Aucun
provider ni appel de modèle n'a été activé par cette recette.

## CI et contrôles du lot

Les emails « Validate synthetic preparation » venaient du job PowerShell,
`Test-PortableState.ps1`, code `PUBLICATION_FAILURE_ROLLBACK_FAILED`, également
présent avant le nettoyage. Ce test concerne le transfert personnel entre PC,
que le propriétaire a explicitement exclu d'ArcIA. Ses sources et preuves ont
été conservées localement hors Git et son contrat retiré de la CI ; les tests
DPAPI/ACL et identité de plateforme restent exécutés.

Exécuté localement : **238 tests Python exécutés sans échec, deux skips TLS faute d'OpenSSL
sur Windows**, dont 14 tests de frontières de routage ; couverture bootstrap
59 étapes ; tests PowerShell bootstrap, protection DPAPI, identité, DNS, DNS
local et SSO réussis. Sources YAML/JSON Schema, hashes et digests validés sur
une copie des seuls fichiers suivis ; 74 Markdown et 409 liens/ancres, 15
schémas Mermaid vérifiés. La [CI de la livraison documentaire](https://github.com/nicolastheuil/ArcIA/actions/runs/38546105216)
a réussi dans ses deux jobs ; les vérifications des corrections VIP/TLS sont
consignées dans la preuve du lot. Une CI synthétique
ne vaut ni réapplication du cluster entier ni reconstruction VMware neuve.

## Ordre de reprise

### Incident SESSION_REVOKED — corrigé dans le harness générique

Après le correctif réseau, le login Microsoft accédait au dashboard puis
recevait un refus de session. Compte actif, rôle et binding relus sans
modification. La recette synthétique a reproduit API 200 avant expiration,
puis 401 avec access token expiré et 401 avec refresh seul ; le compte de
recette a été remis désactivé.

Correctif **codé, déployé et vérifié** après accord explicite pour le rollout :
refresh natif single-flight, revalidation signature/issuer/audience,
propriétaire/rôle et UserInfo ; cookies Secure/HttpOnly au préfixe de l'espace,
révocation du refresh au logout et refus des rejeux. Les cookies racine
hérités ne masquent plus une session personnelle. Le renderer neuf embarque
le même code générique ; Fresh/Reconcile comportent sa réconciliation par
ConfigMaps immuables et Recreate. Aucun domaine ou compte d'instance dans
le code ; aucune nouvelle permission ni prolongation du TTL Keycloak.

Canari synthétique : API 200 avant et après expiration réelle, refresh seul
200 ; logout 302 puis rejeux AT et RT refusés (401). Déploiement du pool :
34 runtimes relus, un canari puis 33 autres templates mis à jour, six rollouts
actifs au total ; mêmes PVC, credentials et comptes conservés. Les quatre
espaces personnels actifs montent exactement le nouveau hash ; OIDC/JWKS
200, départ login 302, douze sondes nœuds réussies et anonyme p03 refusé.
Le propriétaire doit confirmer son nouveau parcours Microsoft interactif.
[Preuve assainie](qualification/2026-10-14-session-refresh.json).

Validation : 75 tests ciblés (12 session/rollout, 46 identité, 12 portail,
5 multi-utilisateur) et suite complète **254 tests sans échec, deux skips TLS
faute d'OpenSSL Windows**. Les tests async ont réussi hors sandbox. Sources,
locks, couverture bootstrap 61 étapes, PowerShell et liens vérifiés sur le
lot isolé des travaux OmniRoute concurrents. La reconstruction VMware neuve
et HA ne sont pas qualifiées.

Les premiers rollouts avaient été rejetés par revue automatique ; l'accord
explicite a permis le canari, puis le même accord couvrant p03 et les autres
runtimes a été fourni au réexamen du rollout global. Aucune validation Teams
n'est prétendue. [Procédure](runbooks/bootstrap.md).

### Incident OIDC du runtime personnel — corrigé

Le 14 octobre, refus reproduit sur un espace personnel : découverte OIDC
`ConnectError` et login HTTP 503, malgré un DNS exact vers la VIP. Chaque
runtime refusait HTTPS vers son propre nœud et atteignait les deux autres.
Le DNAT hostPort (443 → Pod ingress 8443) exige une règle vers la destination
interne, en complément des adresses de nœuds et VIP sur 443.

Correctif **codé, déployé et vérifié** après l'accord explicite du propriétaire
pour cette seule règle interne. Les 34 politiques possédées ont été réconciliées
et relues ; aucun runtime n'a redémarré, aucun compte ni volume n'a changé.
Découverte/JWKS 200 et départ login 302 dans les quatre espaces personnels
actifs ; les douze sondes HTTPS (quatre runtimes × trois nœuds) réussissent.
Le chemin navigateur de l'espace concerné redirige vers l'identité ArcIA et
son API refuse l'anonyme (401). Le retour Microsoft interactif complet reste
à confirmer par le propriétaire avec un nouveau login.
[Preuve assainie](qualification/2026-10-14-identity-runtime-network.json).

Renderer partagé et étape Fresh/Reconcile `reconcile_identity_runtime_network`
après installation du portail ; l'inspection sonde désormais l'OIDC de tous
les espaces actifs. Les 46 tests identité et deux tests de rendu personnel,
les contrôles PowerShell bootstrap et les liens documentaires passent.
Couverture bootstrap de 60 étapes et sources validées sur une copie du seul
lot livré, excluant le développement concurrent.
La suite complète du portail a été interrompue après blocage dans le sandbox ;
ne pas la déclarer réussie. La première application avait été rejetée par la
revue automatique sans accord explicite ; l'accord ultérieur est propre à
ce correctif, sans approbation Teams prétendue ni ouverture Internet générale.
[Procédure](runbooks/bootstrap.md).

Les lots OIDC/réseau et refresh (`3c14f2b`, `5c2affa`) ont été publiés séparément
puis intégrés comme base du lot OmniRoute. Aucun travail local de l'autre chat
n'a été repris ou publié par ce lot. La recette
VMware neuve et HA reste inchangée, non qualifiée.

### Connexions personnelles dans OmniRoute : résultat du lot

Le service et la page `/personal/` sont codés, déployés et vérifiés sur les VM
existantes : PKCE, droits admin/utilisateur, propriétaires, clés natives limitées,
retrait live du rôle, compte désactivé, Presidio et nettoyage des fixtures.
[Preuve sans inférence](qualification/2026-10-14-omniroute-self-service.json).
La synchronisation cloud native est désactivée avec lecture de contrôle ; les
routes sync/tunnel/inférence et OIDC global sont fermées sur le relais LAN.
Le mot de passe admin et les volumes existants sont préservés.

L'admin crée les connexions d'entreprise dans le dashboard natif puis configure
pool, modèles et mode dans `/personal/` avec ArcIA.User + ArcIA.Admin. La fonction
personnelle reste fermée jusqu'à activation explicite et attribution du rôle
ArcIA.ProviderSelfService. Aucun rôle réel n'a été attribué automatiquement.
Aucune clé réelle ni inférence payante n'a été utilisée pendant ce lot.

Le renderer et le worker conservent le binding canonique OmniRoute à la
réapplication. Les migrations de config utilisent les UID/resourceVersion
relus et ne reprennent pas de force les champs d'un autre gestionnaire. Les
lots identité déjà publiés restent présents. Le worktree de ce chat est isolé ;
le dossier principal de l'autre chat n'a pas été modifié pour cette livraison.

Vérifications locales de livraison : 274 tests réussis (deux skips sur Windows),
coverage bootstrap 63 étapes, 74 documents/422 liens et 15 schémas Mermaid.
La recette réelle apporte 26 contrôles réussis sans inférence, avec suppression
des trois fixtures et de leurs sessions. HTTPS VIP par domaine/IP est revérifié.

Restent à qualifier : providers réels et quotas après configuration, streaming
fournisseur progressif, routes internes Ollama/vLLM, purge/rotation/restore des
connexions et sauvegarde/reconstruction VMware neuve. Le relais gratuit ancien
reste une recette historique distincte. Les résultats CI et sources sont
consignés à la livraison ; aucune release installable n'est déclarée.

1. Relire AGENTS.md, ses trois références, ce fichier et le backlog ; vérifier
   main et examiner les fichiers locaux non suivis sans les publier.
2. Inspecter l'état réel via les wrappers protégés : OmniRoute, identité,
   admission Microsoft, portail et réseau. Une preuve historique n'autorise
   pas à sauter la vérification courante.
3. Configurer les abonnements d'entreprise, les modèles et le mode admin
   dans OmniRoute puis qualifier leur usage. Activer explicitement le rôle
   self-service pour les comptes concernés ; garder les routes internes fermées
   jusqu'à leur recette.
4. Pour Teams/Azure, suivre le quickstart et l'annexe, enrôler les accès par
   programme local ; aucun secret à demander dans le chat et aucune création
   Azure déjà engagée. Garder le contrat Microsoft 365 inactif sans adaptateur.
5. Pour une release : compléter backup/restore, fencing/perte de nœud, support
   des versions et reconstruction VMware neuve en mode sûr.

Les exceptions déjà consommées pour récupération admin, admission et nettoyage
nommé ne valent pas autorisation générale. Le plan de suppression d'espace
historique est consommé : ne pas le rejouer. Ne jamais afficher bundle, Secret,
kubeconfig ou journal brut. Aucune automation de reprise n'est programmée.
