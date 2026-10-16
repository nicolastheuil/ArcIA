# Infrastructure K3s, Stockage & Déploiement

ArcIA est déployé sur un cluster Kubernetes K3s haute disponibilité hébergé sur des machines virtuelles VMware sous Debian.

---

## 1. Cibles d'Hébergement & Déploiement

Le Setup Wizard ArcIA supporte nativement trois modes d'infrastructure adaptés aux différents contextes d'entreprise :

1. **Nouveau Cluster K3s sur VMware vSphere / ESXi** : Déploiement automatisé de machines virtuelles Debian et configuration K3s HA.
2. **Cluster Kubernetes Existant** : Déploiement sur une infrastructure K8s déjà qualifiée et auditée en 6 points.
3. **Mode Lab Local (Docker Compose)** : Déploiement immédiat mono-poste sans Kubernetes pour test, démo et développement.

---

## 2. Dimensionnement Matériel par Tranche d'Utilisateurs (VMware)

Pour garantir la réactivité d'Open-WebUI, du proxy LiteLLM, du filtre Presidio DLP et des agents autonomes Hermes, l'infrastructure doit être dimensionnée selon l'effectif actif, **en intégrant spécifiquement l'espace requis pour le RAG (Retrieval-Augmented Generation)** :

### Architecture de Stockage RAG dans ArcIA
Le RAG d'entreprise sous Open-WebUI requiert du stockage pour :
1. **Le corpus documentaire brut** : PDFs, présentations, documents bureautiques, procédures, code source.
2. **Le texte extrait et découpé** : Chunks de 500 à 1000 tokens avec overlap et métadonnées.
3. **La base vectorielle ChromaDB** : Embeddings denses (ex: 1536 float32 pour `text-embedding-3-small`, ou modèles locaux 768/1024d) avec index **HNSW** (Hierarchical Navigable Small World) assurant des recherches de similarité cosinus en moins de 10 ms. L'index vectoriel consomme environ 1,5× à 2× la taille brute des vecteurs en RAM et sur disque.
4. **Le cache local d'inférence et d'embeddings** : Poids des modèles d'embedding et SQLite `webui.db` pour l'historique et les citations.

### Matrice de Dimensionnement (OS, K3s, Hermes et RAG Dédié)

| Tranche d'utilisateurs | Type de Déploiement | Nœuds | CPU / RAM / Disque par VM | Ressources Totales | Espace Dédié RAG & Vecteurs | PVC `open-webui-pvc` | Recommandation |
|---|---|---|---|---|---|---|---|
| **Jusqu'à 20 utilisateurs** | Pilote / Équipe restreinte | 1 VM All-in-One | 4 vCPU, 8 Go RAM, 100 Go SSD | 4 vCPU, 8 Go RAM, 100 Go SSD | **50 Go dédiés** (~10 000 pages, base ChromaDB) | `50Gi` | Test rapide et qualification fonctionnelle |
| **Jusqu'à 100 utilisateurs** | PME / Département métier | 3 VMs K3s HA (etcd) | 4 vCPU, 16 Go RAM, 150 Go SSD | 12 vCPU, 48 Go RAM, 450 Go SSD | **200 Go dédiés** (~100 000 pages, base HNSW inter-services) | `200Gi` | **Configuration de référence recommandée** |
| **Jusqu'à 500 utilisateurs** | Entreprise / Multi-filiales | 5 VMs (3 Masters + 2 Workers) | Masters : 4 vCPU / 16 Go / 100 Go<br>Workers : 8 vCPU / 32 Go / 250 Go | 28 vCPU, 112 Go RAM, 1,25 To SSD | **600 Go dédiés** (~500 000 pages, multi-collections) | `600Gi` | Haute disponibilité, RAG hybride et charge continue |
| **Plus de 500 utilisateurs** | Grande Entreprise / Groupe | 7+ VMs (3 Masters + 4+ Workers) | Masters : 8 vCPU / 32 Go / 200 Go<br>Workers : 16 vCPU / 64 Go / 500 Go | 88+ vCPU, 352+ Go RAM, 3,5 To SSD | **2 To à 5 To dédiés** (Millions de documents, index distribué) | `2Ti` | Déploiement extensible, support vGPU |

L'automatisation du provisionnement sous VMware est assurée par le script [`scripts/Deploy-VMwareCluster.ps1`](../../scripts/Deploy-VMwareCluster.ps1) ou directement orchestrée par le Wizard graphique, qui injecte automatiquement la taille optimale du PVC `open-webui-pvc` selon la tranche sélectionnée.

---

## 3. Grille d'Audit & Qualification Kubernetes

Avant tout déploiement sur un cluster existant, le Wizard exécute un audit de qualification automatisé en 6 volets :

1. **API Server & Version** : Vérification de la joignabilité et version Kubernetes `>= 1.28`.
2. **Capacité des Nœuds** : Nœuds en état `Ready` et capacité CPU / Mémoire allouable suffisante.
3. **Contrôleur d'Ingress** : Présence d'un contrôleur Ingress actif (Traefik ou NGINX).
4. **Cert-Manager** : Présence des CRDs `cert-manager.io` pour l'émission automatique des certificats SSL/TLS.
5. **StorageClass Dynamique** : Présence d'au moins une StorageClass par défaut (CSI) provisionnant des PVCs `ReadWriteOnce`.
6. **Droits RBAC** : Vérification des privilèges de création de ressources (`kubectl auth can-i create`).

---

## 4. Mode Lab Local (Docker Compose)

Pour évaluer ArcIA ou développer localement sans cluster Kubernetes :
- Fichier de stack : [`docker-compose.lab.yml`](../../docker-compose.lab.yml)
- Passerelle LLM : [`deploy/litellm-lab.yaml`](../../deploy/litellm-lab.yaml)
- Services conteneurisés : Open-WebUI (`:3000`), LiteLLM Proxy (`:4000`), Presidio DLP Anonymizer (`:8080`) et Analyzer (`:8081`).
- Accès direct via le navigateur : `http://localhost:3000`.

---

## 5. Topologie de Référence K3s

- **Nœuds du Cluster (Exemple)** :
  - `node-01` (`192.168.1.11`) : Control-plane / etcd / worker
  - `node-02` (`192.168.1.12`) : Control-plane / etcd / worker
  - `node-03` (`192.168.1.13`) : Control-plane / etcd / worker
- **Namespace Dédié** : `arcia` (Namespace applicatif unifié pour tous les services).
- **Stockage Persistant** :
  - StorageClass par défaut : `arcia-vsphere` (VMware Cloud Provider Interface / Container Storage Interface).
  - Mode d'accès : `ReadWriteOnce` (RWO).
  - Volumes créés :
    - `open-webui-pvc` : 20Gi
    - `hermes-user-pvc` : 20Gi

---

## 6. Ingress & Certificats TLS Automatiques

1. **Contrôleur d'Ingress Traefik** :
   - Installé dans `kube-system` avec ses Custom Resource Definitions (CRDs).
   - Route les flux HTTP (`80`) et HTTPS (`443`).
   - Gère les middlewares (ex: `ForwardAuth` via `oauth2-proxy`).
2. **Cert-Manager & Let's Encrypt** :
   - Version : `v1.16.1`.
   - `ClusterIssuer` : `letsencrypt-prod` ([deploy/manifests/01-cert-manager-issuer.yaml](../../deploy/manifests/01-cert-manager-issuer.yaml)).
   - Challenge ACME HTTP-01 automatique dès que le nom DNS public configuré (ex: `assistant.example.org`) pointe sur le cluster.

---

## 7. Outils d'Administration & Scripts

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
