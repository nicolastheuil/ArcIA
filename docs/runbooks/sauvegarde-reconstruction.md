# Sauvegarde et Reconstruction de la Plateforme ArcIA v0.4

Ce runbook détaille les procédures de sauvegarde, de restauration et de reprise après sinistre pour l'ensemble des composants d'**ArcIA v0.4**.

---

## 1. Cartographie des Données et État Persistant

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

## 2. Procédure de Sauvegarde

### A. Snapshot etcd K3s

Sur le nœud principal du cluster K3s :
```bash
sudo k3s etcd-snapshot save --name arcia-backup-$(date +%Y%m%d%H%M%S)
```
Les snapshots sont stockés par défaut dans `/var/lib/rancher/k3s/server/db/snapshots/`.

### B. Sauvegarde des Volumes Persistants (PVC)

Les volumes applicatifs (`hermes-user-pvc`, `open-webui-pvc`) sont hébergés sur le datastore VMware via la StorageClass CSI.
- Exécuter un snapshot VMware du datastore ou des disques virtuels attachés.
- En cas de sauvegarde au niveau fichier, arrêter temporairement les écritures ou planifier la sauvegarde en heures creuses.

### C. Sauvegarde Chiffrée dans le Dépôt Git d'Instance

Le Setup Wizard (`wizard.sh` / `wizard.ps1`) synchronise automatiquement votre instance vers votre dépôt privé (GitHub ou GitLab) :
- Les métadonnées et choix d'architecture sont stockés dans `instance.json`.
- L'intégralité des secrets (clés LLM, secrets Entra ID, mots de passe Teams, hashs admin) est chiffrée en **AES-256-GCM** avec dérivation **PBKDF2 HMAC-SHA256 à 100 000 itérations** dans `instance-secrets.enc`.
- Aucun secret en clair n'est transmis sur le réseau Git.

---

## 3. Procédure de Reconstruction sur Nouveau Cluster

### Méthode Recommandée : Restauration 1-Clic via le Setup Wizard

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
   - Le Wizard télécharge `instance-secrets.enc`, déchiffre les clés et réinjecte instantanément la configuration.
5. **Cliquer sur Déployer** : l'instance est redéployée à 100% sur le nouveau cluster avec récapitulatif complet des URLs.

### Méthode Manuelle Alternative (Ligne de commande)

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
