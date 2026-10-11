# Préparer le déploiement ArcIA

## État et destination

Destination confirmée : **nicolastheuil/arcia-harness**, privé. Les trois VM
sont à créer. Cette livraison prépare le socle ; aucun cluster ou service métier
n'est installé et aucune HA n'est annoncée. Voir docs/etat-reprise.md et backlog.

## 1. Créer les VM désignées

Appliquer `infra/vmware/vm-spec.yaml` dans l'infrastructure VMware retenue :
trois Debian 13 amd64, chacune 8 vCPU / 32 Gio / 150 Gio système, NIC vmxnet3,
open-vm-tools, UUID de disque exposé (`disk.enableUUID=TRUE`). Le stockage partagé
proposé est 1 Tio, à ajuster aux bases répliquées et sauvegardes.

Répartir sur des ESXi distincts si disponibles ; relever les domaines de panne
dans l'inventaire protégé. Cloner une image Debian propre, jamais une VM K3s
enrôlée. Vérifier UUID VMware, MAC, hostname, machine-id et clés hôte uniques.
Configurer DNS, heure synchronisée, SSH personnel et sudo ; relever les empreintes
depuis la console VMware et les confirmer dans known_hosts hors bande.

Le contrôleur Ansible est Linux/WSL (Ansible ne s'exécute pas nativement sous
Windows). Le wizard utilise les chemins SSH Windows pour le préflight ; le rendu
les convertit en chemins `/mnt/<disque>/...` pour WSL du même ingénieur. Vérifier
leur accès et leurs permissions Linux avant Ansible. Un contrôleur Linux distinct
utilise ses propres chemins et identité dans une configuration locale protégée.
Ne pas déplacer une clé privée d'un ingénieur vers un autre pour ces chemins.

## 2. Collecter localement les paramètres

Depuis un terminal PowerShell local de confiance, sans transcription ni capture
de contenu privé dans le chat :

```powershell
python scripts/harness.py doctor
powershell -NoProfile -File scripts/Configure-Local.ps1
powershell -NoProfile -File scripts/Prepare-Local.ps1 -Action plan
```

Le wizard écrit `%LOCALAPPDATA%\ArcIA-Harness\instance.dpapi`, chiffré pour le
compte Windows courant, ACL restreinte, hors OneDrive et Git. Il n'est à lancer
qu'après création des VM et choix réseau/stockage. Aucun mot de passe, clé privée,
kubeconfig ou OTP à fournir dans le chat. Le token K3s est généré localement une
seule fois ; une seconde configuration est refusée plutôt que de le remplacer.

Le wizard couvre le bootstrap K3s. L'enrôlement Entra/Teams/Passbolt et des coffres
personnels du harness métier reste à développer. Il ne revendique aucun accès
autonome déjà en place. Après réalisation d'une qualification, l'ingénieur peut
enregistrer son état et sa référence de preuve locale via `Set-Qualification.ps1`
(`-Gate`, `-Status`, `-EvidenceRef`). Ce programme ne teste pas le fait déclaré :
la preuve mesurée doit exister et être revue. Aucun gate n'a été validé ici.

## 3. Qualifier les prérequis

- Relever vCenter/ESXi, datastore, storage policy, CPI, CSI, privilèges minimums
  et disponibilité des domaines de panne. Résoudre les images et sidecars par digest.
- Définir l'endpoint API privé et le futur HTTPS avec bascule, puis vérifier le
  routage et les probes sans supposer qu'un NAT sur une seule VM assure la HA.
- Comparer les CIDR Pods/Services à tous les réseaux entreprise, VPN et clients
  connus. Les valeurs d'exemple ne sont pas des choix de réseau approuvés.
- Faire approuver/appliquer les flux firewall sur les réseaux privés : API
  6443/TCP ; etcd 2379–2380/TCP entre serveurs ; VXLAN 8472/UDP entre nœuds ;
  kubelet 10250/TCP selon usages. Recenser DNS/NTP/SSH et les sorties artefacts.
  Aucun de ces ports Kubernetes/VXLAN n'est publié sur Internet.
- Vérifier le préflight Debian, ressources, horloge, cgroups, TUN et absence de
  swap non qualifié. Le probe ne configure ni pare-feu ni système.

```powershell
powershell -NoProfile -File scripts/Prepare-Local.ps1 -Action preflight
powershell -NoProfile -File scripts/Prepare-Local.ps1 -Action render
```

Le rendu produit un sous-dossier `transit-*` à ACL restreinte sous le répertoire
local protégé. Il contient le token nécessaire à Ansible ; ne pas le lire depuis
Codex, l'envoyer au chat, synchroniser ou commiter. Transférer vers un contrôleur
protégé, mode 0700 pour le répertoire et 0600 pour l'inventaire. Éliminer le transit
après usage. DPAPI n'est pas un kit de récupération : prévoir les clés externes.

## 4. Appliquer uniquement le bootstrap qualifié

Après validation administrative des gates et revue du diff, depuis Linux :

```bash
python3 -m venv /protected/validation-venv
/protected/validation-venv/bin/pip install -r requirements-validation.txt
cd infra/ansible
/protected/validation-venv/bin/ansible-playbook -i /protected/inventory.private.json preflight.yml
/protected/validation-venv/bin/ansible-playbook -i /protected/inventory.private.json site.yml
```

Le playbook bloque le rendu actuel : cibles non établies, gates pending, CPI non
épinglé. La première installation est une qualification synthétique safe-mode,
pas un lancement métier. Installer ensuite CPI/CSI/ingress qualifiés. Les logs
Ansible contiennent les noms d'hôtes : ils restent locaux protégés, jamais bruts
dans Git ou le chat. Aucun kubeconfig administrateur n'est rapatrié par ces scripts.

La réexécution reprend la même installation. Version, token ou configuration
modifiés sont refusés. Aucun uninstall, reset etcd, adoption d'existant ou reboot
automatique. Les paquets apt ne sont pas encore figés par snapshot Debian :
la reproductibilité binaire complète reste un gate de release.

## 5. Recette et release

Qualifier PVC création/écriture/recréation/déplacement/rétention et prévention
double écrivain. Tester entrée et API sous perte d'un nœud, PG failover, fencing,
kill switch et absence de rejouage. Développer le lot 0 avant tout client pilote.

Pour le rebuild : cluster de test neuf distinct, sauvegardes chiffrées cohérentes,
clé externe et deuxième ingénieur. VPN, anciennes capacités, scheduler métier et
notifications de production désactivés ; droits actuels revérifiés. REC-01/02,
§19/25/26 et cinq missions doivent avoir des preuves avant release installable.
