# Vérification de la préparation — 11 octobre 2026

> Archive historique. Pour la reprise actuelle, lire [l’état courant](../etat-reprise.md).

## Résultat courant — 12 octobre 2026

98 tests Python WSL réussis. Validation JSON Schema/YAML, hashes des sources
VMware et CNPG, digests applicatifs, syntaxe Ansible et refus de l’installation
synthétique avant SSH réussis. Les avertissements Ansible sur le dossier WSL
monté inscriptible concernent la lecture d’ansible.cfg, pas un accès SSH par ces tests.

Sur cible : CSI 5 checks ; applications 12 (pgvector, réplication/bascule PG,
persistance SQLite et refus réseau) ; HTTPS/auth 6 ; VIP réelles 9 API + 9 HTTPS.
Voir [matrice de recette et limites](recette-fondatrice-2026-10-12.md) et
[handoff courant](handoff-2026-10-12-qualification-verifiee.md).
TLS public différé, WebSocket/SSE complet, perte brutale/fencing,
backups/rebuild et services métier non qualifiés.

Lot documentation/outillage : 50 scripts PowerShell parsés sans erreur,
19 schémas Mermaid validés par le parseur 12.1.0, 128 liens locaux résolus.
Le contrôle Mermaid est syntaxique, sans recette visuelle exhaustive.
Context7 4.3.0 : initialize/tools-list et requête publique PostgreSQL réussis ;
skills CLI 1.7.2 exécuté ; LintLang 0.8.2 exécuté sur deux instructions, PASS
structurel avec confiance heuristique faible (65 % de couverture).
Six skills Superpowers/ECC installés/adaptés, licences et 23 empreintes validées.
Trois tests nouveaux protègent la mise à jour Codex : préservation/idempotence,
refus de table homonyme étrangère, refus d’un TOML existant invalide.

**Les sections suivantes sont historiques et décrivent les lots antérieurs.**

## Exécuté localement

| Contrôle | Résultat |
|---|---|
| Python 3.14.4 WSL, unittest | 78 tests synthétiques réussis (dernier lot) |
| PowerShell, tous les scripts | Parse sans erreur |
| ProtectedState, DPAPI et ACL | Roundtrip réussi, canari absent du fichier chiffré, ACL restreinte |
| ProtectedState, refus | Écrasement existant et chemin dans le workspace refusés |
| JSON Schema draft 2020-12 | Schéma et fixture valides |
| YAML | Tous les manifests/playbooks parsés |
| Ansible 2.21.5 sur WSL Python 3.14.4 | Syntaxe preflight.yml et site.yml valide |
| Ansible sur inventaire synthétique | Installation refusée au premier play local, avant SSH |
| CLI plan synthétique | safe_mode=true, installation_ready=false, release_ready=false |
| Sources officielles | Tags/commits et SHA256 K3s relevés ; pas d'image applicative qualifiée |

Commandes reproductibles : README.md, requirements-validation.txt et
scripts/validate_sources.py. Le test DPAPI utilise seulement un canari synthétique
et supprime ses fichiers exacts après essai. Le wizard interactif complet et la
mise à jour administrative des gates ne sont pas qualifiés de bout en bout.

La CI reproduit tests Python, schéma/YAML/Ansible et test DPAPI sur runners hébergés
sans secret d'entreprise. Les actions checkout/setup-python sont épinglées par
commit résolu sur leurs tags officiels. Aucun runner avec route vers les périmètres.

## Non exécuté

Application Kubernetes et admission serveur, installation
K3s, idempotence sur cible, CSI/CPI, propriété unique/fencing, bascule PG et endpoints,
Desktop/OIDC/Teams, coffres, assainissement, tunnels/kill switch, sauvegarde chiffrée
et rebuild neuf. Aucune release installable ou disponibilité garantie.

## Limites

Les tests statiques de manifests ne démontrent pas le datapath réseau réel. Le mode
sûr déclaratif doit être implémenté par les futurs services. Paquets apt et
dépendances transitives ne constituent pas encore un lock de release avec hashes.
Les scripts refusent l'adoption/migration d'un cluster existant ; la reprise réelle
d'une interruption doit être testée sur les VM de qualification.
# Complément VMware — 11 octobre 2026

Trois VM arcia-k3s-01/02/03 créées et allumées sur la cible vCenter saisie localement.
Source Debian generic amd64 20261001-2618, SHA512 vérifié, VMDK streamOptimized
converti avec qemu-img 10.2.1, import puis bootstrap NoCloud exécutés.

Vérification via API VMware authentifiée avec pin accepté localement : 3/3 tools
actifs, Debian 13 déclaré, IP/hostname attendus, 8 vCPU/32 Gio/150 Gio, PVSCSI,
VMXNET3 et disk.EnableUUID conformes. UUID/MAC distincts, 3/3 SSH en écoute,
trois ESXi distincts et règle d'anti-affinité active après réconciliation DRS.
Les détails privés restent DPAPI locaux ; aucun identifiant ni accès en Git.

48 tests Python passés sous Linux, y compris TLS synthétique réel, intégrité
image/cache, ISO NoCloud relu, refus de règle de placement étrangère. Tests Windows
DPAPI/ACL/remplacement atomique passés, scripts parsés, JSON Schema/YAML/Ansible
syntaxe et gate sans SSH passés. Le test réel n'est pas un test HA/K3s : aucun
SSH authentifié, contrôle machine-id, horloge Linux, CSI ou rebuild exécuté dans ce lot VMware initial.

## Complément SSH/Linux — 11 octobre 2026

Les trois clés publiques hôte Ed25519 sont validées hors bande par l'API vCenter
approuvée et VMware Tools, avec challenges distincts. La réconciliation du lecteur
CD virtuel est codée et journalisée ; les clés hôte ont été conservées. Après les
redémarrages, les trois VM restent démarrées, conformes et sur trois ESXi distincts
avec anti-affinité. La vérification VMware et le préflight SSH sont séparés.

Connexions SSH strictes et sudo exécutés avec succès. Checks 3/3 : Debian 13 amd64,
ressources et espace libre, cgroups v2, NTP synchronisé, DNS des sources officielles,
swap absent, support TUN, VMware Tools et cloud-init terminé. Machine-id et UUID
Linux valides et uniques. Aucune valeur d'identité ou adresse privée dans le rapport.
Le DNS contrôlé est une résolution, pas une recette des téléchargements HTTPS.

62 tests synthétiques Python sous Linux, dont les refus de confiance réseau seule,
clé changée/dupliquée, challenge périmé, erreur privée, identité clonée, conservation
des clés au rattrapage et absence de reboot avant confirmation du média. Syntaxe
PowerShell, DPAPI/ACL et validation structurelle restent contrôlés. K3s/CPI/CSI,
endpoints, services métier, disponibilité et rebuild restent non déployés/non testés.

## Complément fondations et DNS — 11 octobre 2026

Lecture réelle du vCenter/ESXi 9.1.1 : datastore vSAN accessible aux trois hôtes,
au moins 1 Tio libre lors du relevé, dix policies compatibles PBM. Depuis les trois
VM : TCP SSH entre pairs, routes, MTU >=1500, TLS GitHub/registry, certificat
vCenter approuvé et absence de chevauchement Pod/Service avec les routes IPv4
visibles. Le poste Windows ne présente pas non plus de conflit sur ses routes.
Ces mesures ne qualifient ni les futurs VPN, ni les flux K3s, ni les VIP.

Les deux FQDN ne correspondaient pas encore aux IP réservées. Le défaut local de
paramétrage DCOM est corrigé et testé sous Windows PowerShell 5.1. La tentative
suivante en lecture seule retourne 0x80070005 avant lecture des zones : accès DCOM
refusé, aucune création DNS effectuée. Un package local privé sans credentials est
prêt pour exécution sur le serveur DNS désigné. Aucun droit/firewall AD modifié.
L'ouverture initiale d'Explorateur n'était pas visible ; la fenêtre dédiée et le
chemin physique MSIX permettent d'accéder au package. L'ingénieur confirme ensuite
la création. Les requêtes directes vérifient les IP réservées, puis la purge des
caches négatifs systemd permet la résolution exacte sur les trois VM.

Le compte SSO local arcia-cpi-csi a été créé, propriété vérifiée par journal et
description liée à l'opération. Une inspection après refactorisation vérifie
qu'il existe toujours. Client public épinglé, quatre hashes contrôlés, TLS SHA256
sur les endpoints SSO ; mot de passe généré selon policy relevée, sans changement
de policy. Quatre rôles et dix grants du compte sont vérifiés. Quatre autres
grants de groupe avec propagation à la racine sont conservés sans modification,
origine non établie. Aucun rôle existant n'est édité ; ses privilèges exacts sont
revérifiés. Le défaut était le vmFolder racine du datacenter, alias d'entité complexe :
le grant manquant est appliqué au datacenter sans propagation. Une session technique
vérifie les droits attendus et les refus d'arrêt/suppression des VM et de modification
de disque d'une VM extérieure. La seconde vérification n'ajoute aucun grant.
Aucun test de volume CSI ni installation K3s.

78 tests Python réussis. Tests Windows : DPAPI/ACL ; sélection de zone et refus
de conflits DNS ; création et readback simulés, rejeu sans écriture, refus d'une
autre cible et d'un provider défaillant ; options DCOM chiffrées ; secrets SSO
conformes aux bornes de policy ; certificat accepté/changé/absent. Les tests DNS
simulés n'accèdent à aucun serveur et ne prouvent pas les droits AD réels.
Quatre manifests CPI/CSI et neuf images sont épinglés, hashes vérifiés localement.
# Vérification finale du handoff du 11 octobre 2026

83 tests Python sous Linux passent. Compilation Python, syntaxe PowerShell,
schéma/YAML, hashes VMware, syntaxe Ansible et refus de cible synthétique avant
SSH vérifiés. Contrôleur WSL temporaire nettoyé (zéro dossier restant).
Intégrations DPAPI relues sans exposition des valeurs : Teams, Passbolt et
OpenRouter enregistrés. Arrêt K3s appartenant à l'opération vérifié, sans suppression
de données ; trois Keepalived actifs, zéro VIP sans API saine. Le démarrage K3s
reste en échec sur le premier nœud : voir docs/archives/handoff-2026-10-11.md.
