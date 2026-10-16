# Sauvegarde et Reconstruction de la Plateforme ArcIA v0.2

Ce runbook détaille les procédures de sauvegarde, de restauration et de reprise après sinistre pour l'ensemble des composants d'**ArcIA v0.2**.

---

## 1. Cartographie des Données et État Persistant

| Donnée / Composant | Emplacement | Mode de Persistance | Procédure de Sauvegarde |
|---|---|---|---|
| **Code & Manifests** | Dépôt Git `ArcIA` | Versionné dans GitHub | `git push` vers le dépôt distant |
| **Configuration d'Instance** | `arcia.config.yaml` & `secrets/arcia.env` | Fichiers locaux protégés | Sauvegarde chiffrée hors ligne (DPAPI / coffre d'entreprise) |
| **Cluster K3s (etcd)** | `/var/lib/rancher/k3s/server/db/snapshots` | Snapshot etcd natif K3s | Snapshot etcd périodique automatique ou manuel |
| **État Hermes Agent** | PVC 20Gi `hermes-user-pvc` | Volume CSI (`state.db`, mémoire SQLite) | Snapshot de volume CSI VMware ou backup fichier SQLite |
| **Données Open-WebUI** | PVC 20Gi `open-webui-pvc` | Volume CSI (comptes, préférences, historiques) | Snapshot de volume CSI VMware |
| **Configuration OmniRoute** | PVC 5Gi `omniroute-pvc` | Volume CSI (clés et profils LAN) | Snapshot de volume CSI VMware |

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

---

## 3. Procédure de Reconstruction sur Nouveau Cluster

En cas de reconstruction complète :
1. **Provisionner un cluster K3s vierge** (ou restaurer un snapshot etcd).
2. **Cloner le dépôt ArcIA** :
   ```bash
   git clone https://github.com/nicolastheuil/ArcIA.git
   cd ArcIA
   ```
3. **Restaurer la configuration d'instance** :
   - Restaurer `arcia.config.yaml` et `secrets/arcia.env`.
4. **Restaurer les volumes PVC si nécessaire** (rattacher les volumes CSI existants).
5. **Appliquer le déploiement universel** :
   ```powershell
   .\scripts\Deploy-ArcIA.ps1
   ```
6. **Vérifier l'intégrité opérationnelle** :
   ```powershell
   Get-Content .\scripts\test-validation.sh -Raw | .\scripts\Invoke-K3s.ps1 -RawShell "bash -s"
   ```

Voir également : [Guide Quickstart](quickstart.md) · [Exploitation Quotidienne](exploitation.md) · [Infrastructure K3s](../guides/infrastructure-k3s.md).
