# Préparation des VM vCenter

Cible confirmée : vCenter / cluster ESXi, image Debian à préparer. Noms confirmés :
arcia-k3s-01, arcia-k3s-02, arcia-k3s-03. Autorisation de création déjà donnée.

## Connexion locale

Dans PowerShell local de confiance, sans transcription :

```powershell
python -m venv "$env:LOCALAPPDATA\ArcIA-Validation\venv"
& "$env:LOCALAPPDATA\ArcIA-Validation\venv\Scripts\python.exe" -m pip install --require-hashes -r requirements-vmware.txt
pwsh -NoProfile -STA -File scripts/Connect-VMware.ps1 -PromptFingerprint
```

Au premier lancement, renseigner les champs puis cliquer « Afficher / accepter
empreinte SHA-256 ». Comparer l'empreinte avec celle du vCenter attendu et accepter
localement. Le certificat épinglé est vérifié avant authentification sur chaque
socket. Aucun mode TLS arbitrairement permissif n'est exposé. Une CA PEM est aussi
acceptée dans le formulaire pour une validation PKI normale.

Les tentatives sont enregistrées chiffrées pour permettre une correction locale.
Les relances reprennent ces champs sans les rendre au modèle. Les erreurs DNS,
réseau, TLS, mot de passe et droits ont des diagnostics génériques distincts.
`-CheckOnly` relit la connexion protégée et ne rend qu'un statut générique.

Sous `%LOCALAPPDATA%\ArcIA-Harness` : `vmware.dpapi` et
`vmware-inventory.dpapi` sont privés chiffrés. Seul `vmware-status.json` peut être
lu par Codex : codes fixes et compte d'objets, aucune identité ou destination.
Ne jamais invoquer directement `vmware_inventory.py` avec des valeurs réelles :
son stdout privé est exclusivement capturé par le programme local protégé.

## Disque Debian

L'image est verrouillée dans `infra/vmware/debian-image.lock.json`. Depuis Linux
avec qemu-img 10.2.1 et Python 3.14 :

```bash
python3 scripts/prepare_debian_image.py --output "$HOME/.local/share/arcia-images" --qemu /path/to/qemu-img
```

Le script télécharge la source officielle, contrôle SHA512, refuse un cache
corrompu, convertit en VMDK streamOptimized et écrit une receipt avec empreintes.
Un répertoire de sortie dans le dépôt est refusé. Aucune connexion VMware.

Lors de cette préparation, qemu-utils Ubuntu 1:10.2.1+ds-1ubuntu3.2 et ses
bibliothèques libaio1t64 0.3.113-8build1, libnuma1 2.0.19-1build1, liburing2 2.14-1
ont été téléchargés via les index apt et extraits sous le profil WSL, sans modifier
les paquets système. Leur répertoire de bibliothèques doit figurer dans
LD_LIBRARY_PATH pour utiliser ce qemu-img extrait.

## Placement, création et vérification

`Select-VMwareTarget.ps1` saisit localement les objets VMware, trois IP privées
stables libres avec préfixe, passerelle, DNS/NTP, compte Linux personnel et chemin
de clé publique `.pub`. Aucun mot de passe SSH n'est configuré. Le brouillon et
le résultat restent chiffrés. La version corrigée affiche une confirmation modale
et ferme la fenêtre après enregistrement.

`Protect-DeploymentKey.ps1` déplace une paire créée dans le sous-dossier `secrets`
du projet vers `%LOCALAPPDATA%\ArcIA-Harness\ssh`, avec ACL individuelle ; aucun
contenu de clé n'est rendu. La référence privée de déploiement est mise à jour.

Copier le VMDK et sa receipt dans `%LOCALAPPDATA%\ArcIA-Harness\images`, répertoire
à ACL individuelle. Un autre chemin de cache public se passe via `-ImageRoot`.

```powershell
pwsh -NoProfile -STA -File scripts/Select-VMwareTarget.ps1
pwsh -NoProfile -File scripts/Protect-DeploymentKey.ps1
pwsh -NoProfile -File scripts/Deploy-VMware.ps1 -ValidateOnly
pwsh -NoProfile -File scripts/Deploy-VMware.ps1
pwsh -NoProfile -File scripts/Verify-VMware.ps1
```

Le préflight contrôle IP, ressources, stockage partagé, réseau accessible depuis
les hôtes, dossier VM, absence d'existants et import specs avant la première
mutation. Le profil invité choisi est celui disponible dans vCenter ; l'OS réel
provient toujours du disque Debian 13 vérifié. Ce profil ne certifie pas la matrice
VMware/Debian/K3s. La création importe trois disques propres, expose leurs UUID,
étend à 150 Gio et ajoute un ISO NoCloud par VM, avec MAC/instance-id propres.
Il installe open-vm-tools 2:12.5.0-2+deb13u1 depuis les snapshots Debian du 1 octobre,
configure réseau/SSH personnel, puis allume les VM. Les endpoints NFC utilisent
les certificats/pins transmis par le vCenter authentifié ; les uploads de seed
passent par vCenter. Aucun paramètre privé en arguments ou dans les sorties.

Une règle DRS d'anti-affinité optionnelle, limitée aux trois VM, préserve la
préférence de séparation sans interdire un redémarrage HA sur capacité réduite.
Le déploiement réconcilie le placement ; `Verify-VMware.ps1 -EnforcePlacement`
applique cette même action aux trois VM portant l'annotation de l'opération
courante, et refuse une règle homonyme qui référencerait d'autres VM.

Les résultats privés sont dans `vmware-deployment.dpapi`. Les fichiers
`vmware-deploy-status.json` et `vmware-verify-status.json` contiennent uniquement
codes fixes, comptes et booléens. Une opération incertaine ne se rejoue pas : les
VM existantes sont refusées, la reprise nécessite réconciliation de l'état privé.
Ne pas supprimer ou adopter une VM existante pour faire passer le préflight.

La vérification distingue création/allumage, ressources, tools, OS déclaré,
réseau, UUID/MAC et répartition. Les clés hôte SSH et machine-id sont contrôlés
séparément par le préflight ci-dessous. Aucun CSI, stockage
persistant de plateforme ou endpoint HA n'est qualifié par ces seuls contrôles.

## Valider l'accès SSH et Linux

Le bootstrap actuel publie la clé hôte publique Ed25519 et un challenge propre à
la VM via VMware Tools. Aucun secret dans cette variable guestinfo. Après une
nouvelle création avec cette version, collecter la preuve sans redémarrage :

```powershell
pwsh -NoProfile -File scripts/Test-NodeAccess.ps1 -CollectHostKeys
pwsh -NoProfile -File scripts/Test-NodeAccess.ps1 -ValidateOnly
```

La première commande lit les challenges dans le résultat chiffré du déploiement,
vérifie les VM de l'opération via le vCenter approuvé puis enregistre la confiance
SSH en DPAPI. La seconde utilise uniquement cette confiance, un known_hosts
individuel et la clé personnelle. Elle exécute la sonde en lecture seule par sudo.
Le statut sûr est `ssh-preflight-status.json` ; aucune sortie distante brute.
La sonde DNS vérifie la résolution, pas les téléchargements HTTPS/registre.

Pour les seules VM vierges créées avant cet ajout, `-PublishHostKeys` met à jour
NoCloud en conservant les clés hôte, contrôle le CD connecté, puis redémarre chaque
VM successivement. L'intention est enregistrée avant l'appel ; une seconde
exécution collecte seulement les preuves, sans rejouer le changement. Ne jamais
utiliser ce rattrapage sur un nœud déjà enrôlé. `-StatusOnly` relève les compteurs
de réconciliation ; `-RepairDisconnectedSeed` est réservé au défaut constaté et
journalisé du lecteur client ATAPI avant la correction, pas à un retry générique.

La capture console/OCR (`-DiscoverOnly`, PowerShell Windows classique requis)
reste une aide locale ; elle n'accepte que la clé/empreinte exacte observée sur
le canal vCenter. Un simple keyscan ou une console illisible ne valide pas SSH.

Exécution du 11 octobre : trois preuves hors bande, trois connexions SSH/sudo et
tous les checks Linux réussis, clés hôte conservées, machine-id/UUID distincts.
Voir ADR 0005. K3s reste soumis aux gates réseau, endpoints et CPI/CSI.
