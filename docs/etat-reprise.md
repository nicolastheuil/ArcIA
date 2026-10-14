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
**59 étapes**, dont installation/vérification/inspection OmniRoute. Le
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
| OmniRoute | Serveur privé déployé/vérifié, une instance avec volumes conservés, trois relais TLS LAN 20129 ; HTTPS sur VIP par domaine et IP, confiance Windows explicitement installée sur le PC autorisé | Raccordement d'inférence générique, self-service utilisateur et routes internes à intégrer/qualifier ; aucune activation implicite de fournisseur |
| Identité | Comptes locaux permanents, portail personnel, admin nommé récupéré ; rôle et espace d'un compte Microsoft relus | Login Microsoft confirmé par le propriétaire ; recette interactive complète, autre tenant, groupes et HA/restore à qualifier |
| Réseau Keycloak | Sortie IPv4 publique TCP/443 du pilote ; TLS Microsoft/Graph 4/4 et refus HTTP/80 vérifiés | Destinations au pare-feu amont ; IPv6 non qualifié ; défaut générique fermé |
| Portail du pilote | Pool privé 32 places, trois liées et 29 libres au dernier relevé ; comptes désactivés conservés | Défaut générique huit ; charge de trente utilisateurs non qualifiée |
| Microsoft 365 / Teams | Annexe, contrat YAML, schéma, plan hors ligne et setup Teams documentés | Adaptateur Bot, importeur, services Graph et approbations serveur absents ; aucune configuration Azure appliquée |

Les règles génériques sont : **OmniRoute auto administré en premier routage**,
Presidio pour tous les modèles cloud par défaut, pas pour Ollama/vLLM internes
par défaut ; budgets, abonnement, gratuité et ZDR propres à l'instance. La
connexion personnelle exige **ArcIA.ProviderSelfService**, activation explicite
et propriété serveur. Le contrat documenté ne transforme pas le relais actuel
en intégration générique déjà qualifiée.

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

1. Relire AGENTS.md, ses trois références, ce fichier et le backlog ; vérifier
   main et examiner les fichiers locaux non suivis sans les publier.
2. Inspecter l'état réel via les wrappers protégés : OmniRoute, identité,
   admission Microsoft, portail et réseau. Une preuve historique n'autorise
   pas à sauter la vérification courante.
3. Achever/qualifier le raccordement générique OmniRoute et le self-service
   serveur avant activation des overrides. Le dashboard admin n'est pas une
   interface utilisateur multi-tenant.
4. Pour Teams/Azure, suivre le quickstart et l'annexe, enrôler les accès par
   programme local ; aucun secret à demander dans le chat et aucune création
   Azure déjà engagée. Garder le contrat Microsoft 365 inactif sans adaptateur.
5. Pour une release : compléter backup/restore, fencing/perte de nœud, support
   des versions et reconstruction VMware neuve en mode sûr.

Les exceptions déjà consommées pour récupération admin, admission et nettoyage
nommé ne valent pas autorisation générale. Le plan de suppression d'espace
historique est consommé : ne pas le rejouer. Ne jamais afficher bundle, Secret,
kubeconfig ou journal brut. Aucune automation de reprise n'est programmée.
