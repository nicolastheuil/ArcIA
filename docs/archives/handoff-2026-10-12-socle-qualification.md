> Instantané historique de qualification. Voir l’état de reprise pour le statut courant ; les noms d’exemple sont synthétiques.

> Archive historique. Pour la reprise actuelle, lire [l’état courant](../etat-reprise.md).

# Handoff — socle et Hermes de qualification — 12 octobre 2026, 17:24 Paris

Référence prioritaire de reprise. Arrêt demandé par Nicolas pour quitter le poste.
Périmètre confirmé : **socle et Hermes de qualification**. Services métier,
Entra/Teams/coffres/VPN et assainissement des appels IA exclus de ce lot.
Ne pas redemander les décisions déjà prises ni réimporter l'archive sur cet état.

## Vérifié sur la cible désignée

- Trois serveurs K3s v1.37.1+k3s1 Ready, control-plane/etcd. API locale et VIP
  `/readyz` accessibles ; chiffrement des Secrets actif, hashes cohérents.
- CPI v1.37.0, compatible avec le minor Kubernetes ; CSI v3.7.3. Rollouts
  CPI/CSI prêts, providerID vSphere et retrait du taint sur trois nœuds.
  vCenter joint par son DNS SAN et certificat accepté vérifié, TLS non désactivé.
- StorageClass `arcia-vsphere`, ext4, Retain, WaitForFirstConsumer. Sélection
  de la policy VMware par `storagepolicyname` corrigée et appliquée.
- Cinq essais CSI réussis : provisionnement/écriture/lecture, refus du second
  writer RWOP, persistance après recréation, déplacement ordonné entre nœuds,
  suppression du volume synthétique. Aucun volume de test restant.
- CNPG v1.30.1 : opérateur prêt 2/2 ; PostgreSQL 18.6 standard avec pgvector,
  instances prêtes 3/3, anti-affinité obligatoire, volumes 20 Gi, réplication
  synchrone requise à une réplique. Le failover et les requêtes SQL de recette
  n'ont PAS été exécutés.
- Dernière inspection : Hermes v0.21.6 prêt 1/1, UID/GID 10000, PVC 10 Gi RWOP,
  Deployment Recreate, sans token Kubernetes, authentification locale scrypt.
  Aucun credential LLM, sorties réseau Hermes interdites. Pas d'inférence IA.

## Point d'arrêt exact : HTTPS non prêt

Le premier `install_hermes` s'est terminé en échec de rollout du proxy HTTPS.
Les trois Pods NGINX rencontraient le chemin par défaut
`/var/cache/nginx/fastcgi_temp` sur un filesystem volontairement en lecture seule.
La correction est **codée mais NON appliquée** : tous les chemins temporaires
NGINX vont sous `/tmp`, error_log vers stderr, checksum de ConfigMap dans le
PodTemplate pour déclencher le rollout. Hermes lui-même est prêt.

Reprise immédiate, depuis PowerShell dans le projet :

```powershell
pwsh -NoProfile -File scripts/Invoke-ClusterFoundation.ps1 -Action install_hermes
pwsh -NoProfile -File scripts/Invoke-ClusterFoundation.ps1 -Action inspect_apps
pwsh -NoProfile -File scripts/Verify-PilotAccess.ps1
pwsh -NoProfile -File scripts/Show-PilotAccess.ps1
```

`Verify-PilotAccess.ps1` et son worker sont codés, **non exécutés** : contrôle
TLS avec certificat épinglé et hostname, refus anonyme/mauvais mot de passe,
login correct, cookies Secure/HttpOnly et accès authentifié. Le formulaire
Show-PilotAccess affiche les accès uniquement localement, jamais dans le chat.
L'accès HTTPS n'est donc pas livré ni qualifié à cet arrêt.

## État privé et preuves

Conserver `%LOCALAPPDATA%\ArcIA-Harness` et ses ACL. Les bundles restent DPAPI,
les clés SSH et known_hosts existants sont réutilisés en SSH strict. Les alias
MSIX LocalCache sont gérés par comparaison d'identité de répertoire `samefile`.
Ne jamais afficher les bundles, secrets Kubernetes, stderr ou logs privés.

Statuts JSON expurgés et preuves détaillées chiffrées :

- `cluster-inspect_cluster-status.json` / `.dpapi`
- `cluster-install_vmware-status.json` / `.dpapi`
- `cluster-qualify_storage-status.json` / `.dpapi` : cinq checks vrais
- `cluster-install_postgres-status.json` / `.dpapi` : instances 3/3
- `cluster-install_hermes-status.json` / `.dpapi` : rollout proxy en échec
- `cluster-inspect_apps-status.json` / `.dpapi` : dernier instantané
- `pilot-credentials.dpapi` : identifiants locaux et TLS 90 jours, réutilisés

Les codes d'erreur des inspections peuvent provenir d'événements historiques ;
ils ne prouvent pas une panne actuelle. Une inspection fondation précédente
comptait 11 Pods Ready sur 12 sans Pending : identifier le Pod non prêt.

L'archive `secrets/local/arcia-private.arciap` date d'avant ce lot : elle ne
contient PAS les nouvelles preuves ni les credentials du pilote. Réexporter
par le programme local protégé avec la clé personnelle 1Password avant tout
nouveau transfert de poste ; ne jamais demander la clé dans le chat.

## Code et validations

Nouveaux workers : `node_kubernetes.py`, `kubernetes_vmware.py`,
`kubernetes_apps.py`, `public_oci.py`, `pin_foundation_apps.py`.
Manifest CNPG vendored, SHA256 comparé à la release et au commit verrouillé ;
écriture UTF-8 explicite pour éviter l'altération Windows. Images applicatives
et VMware fixées par digest dans `versions.lock.yaml`. Le tag PostgreSQL doit
être conservé EN PLUS du digest : CNPG y lit la version majeure.

Exécuté : **91 tests Python passent sous WSL**, dont 8 tests de rendu Kubernetes
et sécurité VMware/applications. Schéma PostgreSQL validé contre le CRD épinglé.
Validations YAML/JSON/Ansible et gate synthétique avant SSH réussies avant les
derniers ajouts d'accès ; syntaxe du wrapper et PilotCredentials validée.
Génération du certificat, stockage DPAPI et réutilisation des credentials testés
avec un état synthétique séparé, ensuite supprimé.
Les deux scripts d'accès ajoutés au point d'arrêt restent à exécuter/qualifier.

## Restant avant recette complète

1. Appliquer la correction NGINX et qualifier HTTPS/auth, puis SQLite/persistance
   Hermes, refus d'egress réellement observé et kill switch.
2. Qualifier SQL/pgvector, réplication et bascule contrôlée PostgreSQL avec
   canary synthétique. Aucune connexion Hermes à PostgreSQL n'est annoncée :
   Hermes conserve son état natif SQLite exclusif.
3. Perte brutale de nœud/fencing, endpoint réel après panne, sauvegardes
   chiffrées cohérentes et rebuild sur cluster neuf. RWX non qualifié.
4. Examiner le contournement K3s hérité (wrappers et suppression du répertoire
   d'extraction `data` à chaque démarrage) avant toute recette de rebuild.
5. Verrouiller les paquets Debian/dépendances, SBOM/provenance et support :
   CNPG 1.30 documente Kubernetes 1.34–1.36 ; 1.37 testé mais non supporté,
   K3s non couvert comme vanilla. CSI 3.7 avec K3s 1.37 reste une limite de support.

Aucune déclaration HA de production, release installable ou recette/rebuild
complète. Aucun environnement privé ni service métier utilisé.

Des scripts de diagnostic non suivis préexistaient ; certains affichent des
états privés (`read-inspect.ps1`, `check-target.ps1`, etc.). Ne pas les exécuter.
L'ancien handoff `handoff-2026-10-12-k3s-ready.md` n'est plus la référence.
