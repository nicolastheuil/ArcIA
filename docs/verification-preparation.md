# Vérification de la préparation — 11 octobre 2026

## Exécuté localement

| Contrôle | Résultat |
|---|---|
| Python 3.14.7, unittest | 28 tests synthétiques réussis |
| PowerShell, quatre scripts | Parse sans erreur |
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
commit résolu sur leurs tags officiels. Aucun runner avec route vers les clients.

## Non exécuté

Préflight de VM réelle, application Kubernetes et admission serveur, installation
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
SSH authentifié, contrôle machine-id, horloge Linux, CSI ou rebuild exécuté.
