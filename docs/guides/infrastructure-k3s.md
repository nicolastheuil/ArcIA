# Infrastructure K3s, Stockage & Déploiement

ArcIA est déployé sur un cluster Kubernetes K3s haute disponibilité hébergé sur des machines virtuelles VMware sous Debian.

---

## 1. Topologie du Cluster

- **Nœuds du Cluster** :
  - `arcia-k3s-01` (`172.31.210.61`) : Control-plane / etcd / worker
  - `arcia-k3s-02` (`172.31.210.62`) : Control-plane / etcd / worker
  - `arcia-k3s-03` (`172.31.210.63`) : Control-plane / etcd / worker
- **Namespace Dédié** : `arcia` (Namespace applicatif unifié pour tous les services).
- **Stockage Persistant** :
  - StorageClass par défaut : `arcia-vsphere` (VMware Cloud Provider Interface / Container Storage Interface).
  - Mode d'accès : `ReadWriteOnce` (RWO).
  - Volumes créés :
    - `open-webui-pvc` : 20Gi
    - `hermes-user-pvc` : 20Gi

---

## 2. Ingress & Certificats TLS Automatiques

1. **Contrôleur d'Ingress Traefik** :
   - Installé dans `kube-system` avec ses Custom Resource Definitions (CRDs).
   - Route les flux HTTP (`80`) et HTTPS (`443`).
   - Gère les middlewares (ex: `ForwardAuth` via `oauth2-proxy`).
2. **Cert-Manager & Let's Encrypt** :
   - Version : `v1.16.1`.
   - `ClusterIssuer` : `letsencrypt-prod` ([deploy/manifests/01-cert-manager-issuer.yaml](../../deploy/manifests/01-cert-manager-issuer.yaml)).
   - Challenge ACME HTTP-01 automatique dès que le nom DNS public `arcia.arcitek.io` pointe sur le cluster.

---

## 3. Outils d'Administration & Scripts

Les opérations sur le cluster sont entièrement outillées dans le dossier `scripts/` :

- **Exécution à distance** :
  ```powershell
  .\scripts\Invoke-K3s.ps1 "get pods -n arcia -o wide"
  ```
- **Injection et mise à jour des Secrets** :
  ```powershell
  .\scripts\Apply-Secrets.ps1
  ```
- **Recette & Suite de Validation Automatisée** :
  ```powershell
  Get-Content .\scripts\test-validation.sh -Raw | .\scripts\Invoke-K3s.ps1 -RawShell "bash -s"
  ```
