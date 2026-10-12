# Installation d’ArcIA : fondations Debian / K3s


Version 1.1 — actualisation opérationnelle du 12 octobre 2026.

## Point d’entrée actuel

Utiliser le [bootstrap exhaustif](runbooks/bootstrap.md) pour Plan/Apply/Reconcile/Verify/Audit. Il couvre maintenant le RAG, Presidio et le cloud gratuit filtré. Les étapes détaillées ci-dessous expliquent les fondations et restent soumises aux prérequis/propriétés contrôlés par le bootstrap. Les customisations métier se font dans le dépôt d’instance.

## État et chemin de reprise

Le socle décrit aux étapes 1–13 existe désormais sur les trois VM désignées :
K3s, CPI/CSI, CNPG/PostgreSQL/pgvector, Hermes et NGINX privés. Les preuves et
limites sont dans [la recette](runbooks/recette-fondatrice.md) et
[l’architecture réelle](architecture.md). Pour cette instance, suivre
[l’exploitation](runbooks/exploitation-qualification.md), sans recréer VM,
token, compte technique ou configuration. Le dépôt réel est
`nicolastheuil/arcia-harness`, privé ; les noms des étapes initiales sont des exemples.

Les commandes des étapes suivantes constituent le parcours d’une nouvelle cible.
Une release/reconstruction neuve n’est pas encore qualifiée. Les wrappers K3s
hérités, le nettoyage du répertoire d’extraction au démarrage, le verrouillage
des paquets et les matrices CSI/CNPG doivent être revus avant rebuild.
Le TLS public est déployé, le renouvellement manuel reste à automatiser ; voir [certificats](runbooks/certificats-dns.md).

Ce guide remplace le parcours Compose envisagé avant la confirmation des VM multiples. Infrastructure confirmée : VMware et stockage partagé. Les extensions d’usage appartiennent à chaque instance ; le socle possède un bootstrap logiciel, dont le rebuild neuf reste à qualifier. Les étapes ci-dessous définissent le travail réel à effectuer et les preuves requises.

## 1. Préparer trois VM
Réutiliser la VM Debian vierge comme hermes-k3s-01 et créer hermes-k3s-02 et hermes-k3s-03. Proposition initiale par VM : 8 vCPU, 32 Go RAM, 150 Go système/runtime, x86_64, sans GPU. Prévoir environ 1 To de volumes persistants partagés à ajuster aux rétentions et à la réplication.

Répartir les VM sur des ESXi distincts si disponibles. Configurer nom, IP stable, DNS, heure et accès SSH. Vérifier les identités uniques d’une VM clonée : UUID VMware, MAC, hostname et machine-id ; ne pas cloner un serveur K3s déjà enrôlé pour fabriquer un autre nœud.

La VM seule peut servir aux premiers tests ; la recette HA exige les trois nœuds et des domaines de panne identifiés.

## 2. Préparer le poste Codex
Sur Windows, vérifier que Git et OpenSSH sont accessibles. GitHub CLI est une option administrative si déjà disponible ; elle n’est pas une dépendance du bootstrap. Ouvrir un terminal PowerShell :
```powershell
git --version
ssh -V
```
Installer les outils manquants par le canal approuvé de l’entreprise. Les identités GitHub et SSH restent personnelles à l’ingénieur. Le workspace Codex doit pouvoir exécuter les commandes nécessaires et atteindre les VM par le réseau privé ; un environnement Codex distant sans route vers ces IP ne peut pas déployer directement.

## 3. Ouvrir le pack dans Codex
Extraire bootstrap-harness-codex.zip, ouvrir son dossier racine dans Codex et conserver AGENTS.md à cette racine. Ce fichier est court et renvoie aux documents complets ; ne pas tenter de mettre tout le cahier de 100 Ko dans les instructions automatiques.

Premier message :
> Lis AGENTS.md puis les documents référencés. Construis et déploie la plateforme sur les trois VM Debian K3s selon le guide. Commence par le préflight, le dépôt GitHub dédié et le backlog. Recueille seulement les paramètres manquants ; les secrets passent par un programme protégé. Chaque modification doit être versionnée et accompagnée de preuves. Ne présente pas une infrastructure ou une protection comme installée sans vérification.

Un prompt de départ reste nécessaire pour déclencher l’action. Les permissions effectives de Codex et l’accès réseau ne sont pas créés par AGENTS.md.

## 4. Créer le dépôt GitHub du harness
Nom proposé : hermes-platform-harness. Codex collecte l’organisation exacte et vérifie les droits avant création. Le dépôt démarre privé pendant le build ; la publication du générique nécessite la revue de confidentialité prévue dans le plan.

Après extraction, si le dossier n’est pas déjà un dépôt et après choix de l’organisation :
```powershell
git init -b main
git add AGENTS.md README.md .gitignore docs
git commit -m "Initial architecture and Codex bootstrap"
# Option si gh est déjà disponible et un nouveau dépôt est explicitement demandé
gh repo create ORGANISATION/arcia-harness --private --source . --remote origin --push
```
Remplacer ORGANISATION par la destination confirmée. Si le dépôt existe, le cloner et intégrer le pack ; ne pas créer un doublon.

Le dépôt est la source du code, pas un dump des machines. Les configs privées, données privéess et sauvegardes vont dans les dépôts dédiés sous chiffrement. Ni clé age, kubeconfig administrateur, token K3s, fichier .env ni secret de coffre n’est commité en clair.

## 5. Générer le squelette de travail
Codex crée et commite progressivement :
- AGENTS.md et builder/role.md : rôle et instructions.
- docs/adr/ et docs/backlog.md : décisions et avancement.
- infra/ansible/ : préflight Debian, préparation et installation K3s idempotente.
- deploy/ : charts Helm ou overlays Kustomize, politiques et templates.
- services/ : API, gouvernance, assainissement, secrets, launcher, collecte.
- schemas/ : contrats périmètre, mission, binding et configuration.
- tests/ : scénarios synthétiques et tests de frontières.
- scripts/ : wizard, doctor, backup, restore et migrations.
- versions.lock.yaml : versions précises, commits et digests qualifiés.
- docs/runbooks/ : installation, panne de nœud, reprise et rebuild.

Ces éléments sont à implémenter ; leur présence dans une liste n’indique pas qu’ils existent déjà dans le pack.

## 6. Faire le préflight Debian et VMware
Sur chaque VM, l’ingénieur ou Codex via SSH relève :
```bash
cat /etc/os-release
hostnamectl
uname -m
nproc
free -h
df -h /
lsblk -f
ip -brief address
ip route
timedatectl status
```
Les inventaires réels sont confidentiels : stockage local protégé ou fichier chiffré, jamais collage brut dans une discussion cloud ou rapport public.

Vérifier version Debian, sudo, SSH et son empreinte, DNS/NTP, disque, cgroups, proxy et accès aux dépôts nécessaires. Inspecter vCenter/ESXi, datastore, storage policy et prérequis du driver CSI compatible. La création du compte technique vSphere suit les droits minimums documentés pour ce driver.

Arrêter l’étape concernée si une compatibilité ou permission indispensable manque. Ne pas contourner le contrôle en utilisant un stockage local silencieusement pour les données devant survivre à une panne.

## 7. Fixer réseau, entrée et versions
Définir avant K3s :
- les IP des nœuds et l’endpoint API privé avec bascule ;
- le domaine HTTPS métier et son endpoint avec bascule ;
- les CIDR Pods et Services, sans chevauchement connu avec entreprise et accès VPN ;
- les règles de communication internes ;
- la combinaison K3s/Kubernetes, vSphere CSI, CNI, ingress et opérateur PostgreSQL.

Privilégier les moyens de load balancing de l’entreprise. Si un VIP ou autre mécanisme est déployé, vérifier qu’il convient au réseau VMware et aux contraintes L2/L3. Le NAT HTTPS ne pointe pas vers un seul nœud sans bascule.

K3s avec le réseau Flannel VXLAN implique notamment API 6443/TCP, etcd 2379–2380/TCP entre serveurs, VXLAN 8472/UDP entre nœuds et kubelet 10250/TCP selon usages. Les ports exacts sont recalculés pour le CNI retenu. Ils restent sur les réseaux privés ; ne pas ouvrir ces ports sur Internet.

Choisir une release précise après contrôle de la matrice de compatibilité et l’enregistrer dans versions.lock.yaml. Le script d’installation et ses contrôles de hash sont eux aussi fixés ; pas de version flottante pour le rebuild.

## 8. Préparer Debian par Ansible
Codex automatise : packages système utiles, horloge, modules/réseau requis, permissions, répertoires, pare-feu compatible, identités administratives et réglages de secrets temporaires.

K3s apporte containerd ; Docker Engine sur les nœuds n’est pas requis. La construction des images peut se faire sur le poste de build ou en CI, puis être publiée avec digest dans le registre retenu.

Les scripts Ansible et les configurations génériques sont commités ; les variables privées réelles sont chiffrées. Une seconde exécution ne doit ni recréer le cluster ni régénérer ses identités.

## 9. Installer K3s sur le premier serveur
Codex génère /etc/rancher/k3s/config.yaml avec accès root limité. Exemple de forme à générer, NON applicable tel quel :
```yaml
node-name: hermes-k3s-01
cluster-init: true
write-kubeconfig-mode: "0600"
secrets-encryption: true
token-file: /etc/rancher/k3s/cluster-token
tls-san:
  - "<ENDPOINT_API_VALIDE>"
cluster-cidr: "<CIDR_PODS_VALIDE>"
service-cidr: "<CIDR_SERVICES_VALIDE>"
```

Le token est généré et placé dans un fichier protégé via le wizard/Ansible avec sorties masquées. Les placeholders sont refusés par le préflight.

Codex applique le script d’installation officiel fixé par révision/hash avec INSTALL_K3S_VERSION fixé à la release retenue. Vérifications :
```bash
sudo systemctl status k3s --no-pager
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl get pods -A
sudo k3s secrets-encrypt status
```
Les sorties peuvent contenir des IP et noms internes : les preuves destinées à Git sont assainies.

## 10. Ajouter les deux autres serveurs
Ils rejoignent comme serveurs avec etcd, pas comme simples agents. Même version et paramètres critiques ; node-name unique, server pointant sur l’endpoint validé, token-file protégé. cluster-init est réservé à l’initialisation.

Contrôles : trois Nodes Ready, état des services, réseau entre Pods sur nœuds différents et fonctionnement des politiques. Enregistrer la procédure idempotente dans Ansible. Le kubeconfig administrateur reste protégé et hors Git.

## 11. Déployer et qualifier le stockage
Installer le CSI vSphere compatible, avec compte technique et secrets protégés. Créer la StorageClass utilisant la policy retenue. Vérifier :
1. création de PVC ;
2. écriture et lecture d’un fichier de test ;
3. persistance après recréation du Pod ;
4. accès depuis un autre nœud après libération réelle du volume ;
5. suppression contrôlée et politique de rétention.

Le volume bloc sera formaté comme un système de fichiers Linux local. L’état SQLite/Hermes a un seul propriétaire actif. Utiliser ReadWriteOncePod si supporté ; sinon qualifier la prévention des doubles écrivains et le fencing. Ne pas croire que ReadWriteOnce seul interdit deux Pods sur le même nœud.

Pour une panne brutale, confirmer que l’ancien propriétaire ne peut plus écrire avant de forcer une réattribution de volume.

## 12. Installer les fondations applicatives
Par manifests versionnés : espaces de travail, identités techniques, quotas, politiques réseau, ingress, certificats et PostgreSQL/pgvector avec réplication qualifiée.

Codex sélectionne le mécanisme PostgreSQL compatible et prépare un test de bascule ; le quorum etcd du cluster ne réplique pas la base métier.

Activer les contrôles d’admission adaptés et limiter les permissions du lanceur. Les agents ne reçoivent aucune capacité cluster-admin. Les composants de tunnel ont une exception technique étroite, vérifiée séparément ; cette exception ne s’étend pas aux runtimes.

## 13. Installer un Hermes de qualification
Utiliser l’image officielle résolue puis fixée par digest, un PVC propre et une instance active. Vérifier les paramètres de runtime UID/GID, le wizard et la disponibilité réelle des services supervisés.

Premiers essais uniquement synthétiques. Le backend de terminal local d’Hermes s’exécute dans le Pod, pas sur le nœud. Pas de montage de socket containerd/Docker ni clé SSH administrateur.

Desktop distant utilise le backend dashboard, généralement sur 9119, pas l’API compatible OpenAI 8642. Pour les premiers tests, utiliser un accès privé/port-forward et une authentification de qualification ; pas de NAT public tant que le contrôle Entra métier n’est pas validé.

Une duplication de ce Pod avec le même état n’est pas un test de scaling autorisé.

## 14. Développer puis activer les intégrations métier
Codex construit les lots, teste puis déploie :
1. Identité Entra, registre périmètres/tâches et RBAC serveur.
2. Passerelle d’assainissement et contrôle des sorties cloud.
3. Opérations typées, plan immuable et validation Teams.
4. Connecteurs de coffres persistants individuels.
5. Launcher de missions, OpenConnect personnel et kill switch.
6. Collecte documentaire et recherche avec ACL.
7. Routage Desktop et partage des livrables.
8. OmniRoute, fournisseurs qualifiés et budgets.
9. Sauvegardes chiffrées et restauration.

Cette séquence peut comporter du travail parallèle, mais aucune mission réelle ne doit emprunter une protection non encore qualifiée. Le MVP complet exige les frontières essentielles ; le premier chat Hermes n’en est pas la preuve.

## 15. Tester la résilience et les limites
Préparer des missions synthétiques et une fenêtre de test administrative. Démontrer :
- panne d’un nœud : entrée et contrôle restent disponibles selon objectifs ;
- PostgreSQL : bascule sans perte non maîtrisée et queue cohérente ;
- état Hermes : reprise avec propriétaire unique ;
- VPN : reconnexion à la demande, éventuel MFA, aucune réutilisation de session ;
- action interrompue : état incertain suspendu et réconcilié, jamais rejoué aveuglément ;
- budgets : ingestion mise en file lorsque la capacité restante est insuffisante.

Mesurer temps d’interruption et données potentiellement perdues. Un Pod Running ou un restart réussi ne suffit pas à annoncer le succès métier.

## 16. Sauvegarder et reconstruire depuis GitHub
Automatiser les snapshots K3s/etcd avec leur matériel de récupération, les sauvegardes cohérentes PostgreSQL/Hermes et les objets. Chiffrer avant GitHub/LFS ; clés et secrets racines hors dépôts.

Sur un autre cluster de test : cloner la release, fournir les moyens de récupération protégés, appliquer Ansible/manifests, restaurer, revérifier les droits actuels et exécuter la recette en mode sûr. Ne pas réactiver les VPN ni capacités d’écriture sauvegardés.

Produire une release avec versions.lock.yaml, migrations, rapport de recette assaini, checklist de paramètres et runbooks. Le dépôt devient alors la source des nouvelles installations.

## 17. Informations à fournir au wizard
Organisation GitHub et nom du harness ; IP/FQDN/SSH des trois VM ; version Debian et ressources ; vCenter/ESXi/datastore/policy ; réseau et endpoints avec bascule ; tenant Entra et application Teams existante ; Passbolt et références de récupération ; clés fournisseurs ; catalogue documentaire.

Codex relève automatiquement les valeurs techniques accessibles. Il demande les informations humaines ou droits qu’il ne peut pas déduire. Les secrets sont saisis dans le programme protégé ; leurs valeurs ne sont ni exposées au modèle ni commitées.

## 18. Sources et portée
Sources officielles consultées le 11 octobre 2026 :
- K3s HA : https://docs.k3s.io/datastore/ha-embedded
- Prérequis : https://docs.k3s.io/installation/requirements
- Configuration : https://docs.k3s.io/installation/configuration
- Chiffrement : https://docs.k3s.io/security/secrets-encryption
- vSphere CSI : https://github.com/kubernetes-sigs/vsphere-csi-driver
- Volumes : https://kubernetes.io/docs/concepts/storage/persistent-volumes/
- Hermes Docker/runtime : https://hermes-agent.nousresearch.com/docs/user-guide/docker
- Desktop : https://hermes-agent.nousresearch.com/docs/user-guide/desktop
- Codex AGENTS.md : https://developers.openai.com/codex/guides/agents-md/
- GitHub CLI : https://cli.github.com/manual/gh_repo_create

À la rédaction initiale du 11 octobre, ce guide était l’entrée du build. Le
socle et ses scripts ont depuis été construits/déployés ; les services métier
et la recette de reconstruction restent à réaliser. L’état courant est celui
du [handoff](handoff-2026-10-12-qualification-verifiee.md).
