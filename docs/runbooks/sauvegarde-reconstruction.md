# Sauvegarde et reconstruction de la plateforme ArcIA v0.7.0

Ce runbook détaille les procédures de sauvegarde, de restauration et de reprise après sinistre pour l'ensemble des composants d'**ArcIA v0.7.0**.

---

## 1. Cartographie des données et état persistant

| Donnée / Composant | Emplacement | Mode de Persistance | Procédure de Sauvegarde |
|---|---|---|---|
| **Code & Manifests** | Dépôt Git `ArcIA` | Versionné dans GitHub | `git push` vers le dépôt distant |
| **Configuration d'Instance** | `arcia.config.yaml` & `secrets/arcia.env` | Fichiers locaux protégés | Sauvegarde chiffrée hors ligne (DPAPI / coffre d'entreprise) |
| **Dépôt d'Instance Privé** | Git distant (`ArcIA-instance-XXXX`) | Dépôt privé externe sécurisé | `instance.json` + `instance-secrets.enc` chiffré en AES-256-GCM via mot de passe maître |
| **Cluster K3s (etcd)** | `/var/lib/rancher/k3s/server/db/snapshots` | Snapshot etcd natif K3s | Snapshot etcd périodique automatique ou manuel |
| **État Hermes Agent** | PVC 20Gi `hermes-user-pvc` | Volume CSI (`state.db`, mémoire SQLite) | Snapshot de volume CSI VMware ou backup fichier SQLite |
| **Données Open-WebUI** | PVC 20Gi `open-webui-pvc` | Volume CSI (comptes, préférences, historiques) | Snapshot de volume CSI VMware |
| **Base LiteLLM (PostgreSQL)** | PVC 10Gi `litellm-db-pvc` | Volume CSI (`/var/lib/postgresql/data`, virtual keys, budgets) | Snapshot de volume CSI VMware ou `pg_dump` |

---

## 2. Procédure de sauvegarde

### A. Snapshot etcd K3s

Sur le nœud principal du cluster K3s :
```bash
sudo k3s etcd-snapshot save --name arcia-backup-$(date +%Y%m%d%H%M%S)
```
Les snapshots sont stockés par défaut dans `/var/lib/rancher/k3s/server/db/snapshots/`.

### B. Sauvegarde des volumes persistants (PVC)

Les volumes applicatifs (`hermes-user-pvc`, `open-webui-pvc`) sont hébergés sur le datastore VMware via la StorageClass CSI.
- Exécuter un snapshot VMware du datastore ou des disques virtuels attachés.
- En cas de sauvegarde au niveau fichier, arrêter temporairement les écritures ou planifier la sauvegarde en heures creuses.

### C. Sauvegarde chiffrée dans le dépôt Git d'instance

Le Setup Wizard (`wizard.sh` / `wizard.ps1`) synchronise automatiquement votre instance vers votre dépôt privé (GitHub ou GitLab) :
- `instance.json` contient uniquement le format, le chiffrement et la date ; les choix d’architecture sont dans l’archive chiffrée.
- L'intégralité des secrets (clés LLM, secrets Entra ID, mots de passe Teams, hashs admin) est chiffrée en **AES-256-GCM** avec dérivation **PBKDF2 HMAC-SHA256 à 100 000 itérations** dans `instance-secrets.enc`.
- Aucun secret en clair n'est transmis sur le réseau Git.

---

## 3. Procédure de reconstruction sur nouveau cluster

### Méthode recommandée : reprise guidée via le Setup Wizard

En cas de reconstruction ou de migration sur un cluster vierge :
1. **Provisionner le cluster K3s**.
2. **Cloner le socle générique ArcIA** :
   ```bash
   git clone https://github.com/nicolastheuil/ArcIA.git
   cd ArcIA
   ```
3. **Lancer le Wizard** :
   ```bash
   # Sous Linux / macOS :
   ./wizard.sh

   # Sous Windows :
   .\wizard.ps1
   ```
4. **Sélectionner "Restaurer une instance existante"** :
   - Renseigner l'URL du dépôt Git privé d'instance (`https://github.com/mon-orga/ArcIA-instance-prod.git`) et le token d'accès.
   - Saisir le **mot de passe maître** défini lors de l'installation initiale.
   - Le wizard télécharge `instance-secrets.enc`, valide son intégrité et restaure localement la configuration. Il conserve un retour arrière local chiffré avant de remplacer une configuration existante.
5. **Vérifier la cible et cliquer sur Déployer** : le socle réapplique la configuration déclarée. Restaurer séparément les données et extensions d’instance, puis effectuer la recette. Cette étape n’atteste pas à elle seule une reconstruction complète.

### Méthode manuelle alternative (ligne de commande)

1. Restaurer manuellement `arcia.config.yaml` et `secrets/arcia.env`.
2. Restaurer les volumes PVC si nécessaire (rattacher les snapshots CSI existants).
3. Appliquer le déploiement universel :
   ```powershell
   .\scripts\Deploy-ArcIA.ps1
   ```
4. Vérifier l'intégrité opérationnelle :
   ```powershell
   Get-Content .\scripts\test-validation.sh -Raw | .\scripts\Invoke-K3s.ps1 -RawShell "bash -s"
   ```

Voir également : [Guide Quickstart](quickstart.md) · [Exploitation Quotidienne](exploitation.md) · [Infrastructure K3s](../guides/infrastructure-k3s.md).


## Sauvegarde des configurations par le wizard

Le menu **Sauvegarde et reprise** utilise le dépôt privé déclaré par l'administrateur, sans réutiliser le dépôt du harness. Après déverrouillage local du coffre, chaque enregistrement de configuration déclenche un bundle AES-256-GCM et un push limité à `instance-secrets.enc` et `instance.json`. Le processus ne force jamais l'historique Git ; les erreurs produisent un état `pending`, avec instantanés chiffrés locaux et nouvelle tentative après 30 secondes. Un état `locked` requiert le déverrouillage dans le formulaire local ; aucun mot de passe ne doit être transmis dans le chat.

Le dépôt, l'historique, le coffre, la couverture et les actions sont affichés séparément. Une restauration déchiffre et valide les fichiers avant remplacement local ; elle remplace l’état de configuration par celui du point choisi, sans fusionner les réglages plus récents. Elle ne réapplique pas automatiquement les workloads. Les sauvegardes de bases/PVC/etcd décrites dans ce runbook restent nécessaires.

## Configuration prise en charge et responsabilités

Le quatrième écran d’installation est consacré au dépôt d’instance. Le menu **Sauvegarde et reprise** réutilise ce dépôt et le coffre local. Une configuration enregistrée déclenche la sauvegarde ; les modifications locales sont également surveillées pendant que le wizard fonctionne. Les accès Git et le mot de passe du même dépôt peuvent être réutilisés sans ressaisie ; un autre dépôt dispose de son propre contexte d’accès.

Le déploiement conserve dans le YAML les secrets effectifs qu’il génère ou reprend du cluster (identités LiteLLM, sel, mot de passe PostgreSQL, Hermes, Presidio, SSO et Teams). Ils entrent ainsi dans l’archive chiffrée suivante. Une identité locale signalée à récupérer bloque le déploiement et l’annonce d’une sauvegarde complète jusqu’à son rétablissement depuis le cluster ou une archive de référence ; le signalement ne modifie pas la clé.

| Centre de pilotage | Administrateurs de l’instance |
|---|---|
| YAML entier, y compris champs personnalisés, routage, fournisseurs, infrastructure, dimensionnement, DLP, SSO, Teams et secrets déclarés | Déclarer les changements locaux ; les modifications effectuées uniquement dans Kubernetes ou une application ne sont pas découvertes automatiquement |
| `secrets/arcia.env`, éventuel `arcia.env` racine et variables supplémentaires | Sauvegarder bases, conversations, corpus, PVC, `state.db`, etcd et données applicatives avec leurs outils adaptés |
| Fichiers de configuration locaux référencés et identités de déploiement disponibles ; certificats externes du kubeconfig embarqués dans sa copie portable | Maintenir skills, MCP maison, services, code, images, versions, dépendances et procédures dans le dépôt privé ; conserver leurs secrets dans les fichiers de configuration chiffrés |
| Déclarations des Power Users enregistrées par le wizard : identité, personnalité, stockage demandé, suspension et identifiants conservés à la réapplication | Exporter les utilisateurs historiques uniquement présents sur le cluster ; restaurer les données de leurs volumes séparément |
| Chiffrement AES-256-GCM, historique Git, file locale chiffrée en cas de coupure, reprise locale avant déploiement explicite | Garder le mot de passe maître hors du dépôt, prévoir les droits Git/IAM, plugins d’identité cloud, accès réseau et infrastructure nécessaires ; tester régulièrement la reconstruction |

Les fichiers automatiquement reconnus sont `kubernetes.kubeconfig`, `kubernetes.remote_ssh.ssh_key`, `vmware.auth.ssh_key_path` et les champs `config_file`, `cert_file`, `key_file`, `ca_file`, `deny_list_file`, `known_hosts_file` des modules actifs. Un kubeconfig local implicite et les fichiers SSH du harness effectivement utilisés sont rendus explicites dans l’archive. Aucune commande d’un plugin d’authentification du kubeconfig n’est exécutée lors de la sauvegarde. Pour un fichier supplémentaire, le déclarer dans `instance_backup.additional_files` (liste de fichiers locaux ; aucun parcours automatique de répertoires). Les chemins relatifs partent de la racine ArcIA ; les chemins des certificats du kubeconfig partent de son dossier. Les fichiers internes référencés depuis une configuration maison doivent aussi être déclarés.

L’archive conserve les versions déclarées dans `deploy/versions.json`. Garder le socle correspondant disponible pour la reconstruction. Limites explicites : 128 fichiers référencés, 8 Mio par fichier, 32 Mio au total ; les modules désactivés ne provoquent pas de collecte de fichiers. Les accès Kubernetes suivent le mode actif : kubeconfig pour kubectl local, clé et hôtes connus pour SSH distant. Les réglages des autres modes restent dans le YAML sans imposer leurs fichiers inutilisés. Un fichier requis absent, un lien symbolique ou une limite dépassée produit un état incomplet, sans push annoncé comme réussi. Le mot de passe maître et son coffre DPAPI ne font jamais partie des fichiers exportés.

À la reprise, les fichiers sont vérifiés puis relocalisés sous `secrets/restored-assets/`, avec réécriture des références dans le YAML et conservation des extensions de fichier. Aucun chemin arbitraire de l’archive ne peut écraser le code du socle. Le contenu d’un fichier maison est conservé : ses éventuels chemins internes nécessitent une configuration portable ou une adaptation par les administrateurs ; seul le kubeconfig bénéficie de l’intégration automatique de ses certificats. Les archives anciennes YAML/environnement restent lisibles, avec avertissement sur leurs fichiers manquants. Le retour arrière local `secrets/pre-restore-*.enc` utilise le mot de passe saisi pour la reprise. Les sauvegardes Git conservent les points historiques ; elles ne font jamais de force-push.

Seuls `instance-secrets.enc` et `instance.json` sont poussés par le wizard. Les fichiers ajoutés par les administrateurs au dépôt restent intacts. Le Centre de pilotage ne publie pas automatiquement les skills ou MCP maison, ne restaure pas les bases depuis Git et n’installe pas implicitement leurs dépendances.

## Espaces privés WebUI et exports Hermes

`hermes_workspaces.users` et ses références sont inclus dans le YAML d’instance chiffré. Les clés nominatives correspondantes doivent être restaurées par le programme protégé avant réapplication. Les exports, bases SQLite, mémoires et personnalisations se trouvent dans les PVC privés ; le bundle de configuration ne les sauvegarde pas. Conserver le propriétaire associé à chaque volume et refuser sa réaffectation à un autre ID WebUI. Un Power User restauré doit être raccordé à son PVC et à son pod existants. Voir les [règles de conservation et de téléchargement](../guides/espaces-utilisateurs-webui.md).
