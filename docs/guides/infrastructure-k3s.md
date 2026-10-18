# Infrastructure Kubernetes, stockage et déploiement

ArcIA est conçu pour être déployé sur **n'importe quel cluster Kubernetes** (EKS, AKS, GKE, K3s sur VMware/Debian, kubeadm) ou en local via Docker Compose.

---

## 1. Cibles d'hébergement et déploiement

L'installeur interactif (`.\wizard.ps1` / `./wizard.sh`) et le moteur universel (`.\scripts\Deploy-ArcIA.ps1` / `./scripts/deploy-arcia.sh`) supportent trois modes d'infrastructure adaptés aux différents contextes d'entreprise :

1. **Cluster Kubernetes Existant (EKS, AKS, GKE, K3s, kubeadm...)** : Déploiement sur n'importe quelle infrastructure Kubernetes `>= 1.28` auditée automatiquement en 6 points.
2. **Cluster K3s sur VMware vSphere / ESXi** : Déploiement sur machines virtuelles avec stockage partagé CSI.
3. **Mode Lab Local (Docker Compose)** : Déploiement immédiat mono-poste sans Kubernetes pour test, démo et développement ([docker-compose.lab.yml](../../docker-compose.lab.yml)).

---

## 2. Dimensionnement matériel par tranche d'utilisateurs

Pour garantir la réactivité d'Open-WebUI, du proxy LiteLLM, du filtre Presidio DLP et des agents autonomes Hermes, l'infrastructure doit être dimensionnée selon l'effectif actif, **en intégrant spécifiquement l'espace requis pour le RAG (Retrieval-Augmented Generation)** :

### Architecture de stockage RAG dans ArcIA
Le RAG d'entreprise sous Open-WebUI requiert du stockage pour :
1. **Le corpus documentaire brut** : PDFs, présentations, documents bureautiques, procédures, code source.
2. **Le texte extrait et découpé** : Chunks de 500 à 1000 tokens avec overlap et métadonnées.
3. **La base vectorielle ChromaDB** : Embeddings denses avec index **HNSW** (Hierarchical Navigable Small World) assurant des recherches de similarité cosinus en moins de 10 ms.
4. **Le cache local d'inférence et d'embeddings** : Poids des modèles d'embedding et SQLite `webui.db` pour l'historique et les citations.

### Matrice de dimensionnement (cluster, Hermes et RAG dédié)

| Tranche d'utilisateurs | Type de Déploiement | Nœuds | CPU / RAM / Disque par VM | Ressources Totales | Espace Dédié RAG & Vecteurs | PVC `open-webui-pvc` | Recommandation |
|---|---|---|---|---|---|---|---|
| **Jusqu'à 20 utilisateurs** | Pilote / Équipe restreinte | 1 Nœud All-in-One | 4 vCPU, 8 Go RAM, 100 Go SSD | 4 vCPU, 8 Go RAM, 100 Go SSD | **20 Go à 50 Go dédiés** (~10 000 pages, base ChromaDB) | `20Gi` / `50Gi` | Test rapide et qualification fonctionnelle |
| **Jusqu'à 100 utilisateurs** | PME / Département métier | 3 Nœuds HA | 4 vCPU, 16 Go RAM, 150 Go SSD | 12 vCPU, 48 Go RAM, 450 Go SSD | **200 Go dédiés** (~100 000 pages, base HNSW inter-services) | `200Gi` | **Configuration de référence recommandée** |
| **Jusqu'à 500 utilisateurs** | Entreprise / Multi-filiales | 5 Nœuds (3 Masters + 2 Workers) | Masters : 4 vCPU / 16 Go / 100 Go<br>Workers : 8 vCPU / 32 Go / 250 Go | 28 vCPU, 112 Go RAM, 1,25 To SSD | **600 Go dédiés** (~500 000 pages, multi-collections) | `600Gi` | Haute disponibilité, RAG hybride et charge continue |
| **Plus de 500 utilisateurs** | Grande Entreprise / Groupe | 7+ Nœuds (3 Masters + 4+ Workers) | Masters : 8 vCPU / 32 Go / 200 Go<br>Workers : 16 vCPU / 64 Go / 500 Go | 88+ vCPU, 352+ Go RAM, 3,5 To SSD | **2 To à 5 To dédiés** (Millions de documents, index distribué) | `2Ti` | Déploiement extensible, support vGPU |

---

## 3. Grille d'audit et qualification Kubernetes

Avant tout déploiement sur un cluster existant, le Wizard exécute un audit de qualification automatisé en 6 volets :

1. **API Server & Version** : Vérification de la joignabilité et version Kubernetes `>= 1.28`.
2. **Capacité des Nœuds** : Nœuds en état `Ready` et capacité CPU / Mémoire allouable suffisante.
3. **Contrôleur d'Ingress** : Présence d'un contrôleur Ingress actif (Traefik ou NGINX).
4. **Cert-Manager** : Présence des CRDs `cert-manager.io` pour l'émission automatique des certificats SSL/TLS.
5. **StorageClass Dynamique** : Présence d'au moins une StorageClass par défaut (CSI) provisionnant des PVCs `ReadWriteOnce`.
6. **Droits RBAC** : Vérification des privilèges de création de ressources (`kubectl auth can-i create`).

---

## 4. Mode lab local (Docker Compose)

Pour évaluer ArcIA ou développer localement sans cluster Kubernetes :
- Fichier de stack : [docker-compose.lab.yml](../../docker-compose.lab.yml)
- Passerelle LLM : [deploy/litellm-lab.yaml](../../deploy/litellm-lab.yaml)
- Services conteneurisés : Open-WebUI (`:3000`), LiteLLM Proxy (`:4000`), Presidio DLP (`:8080`).
- Accès direct via le navigateur : `http://localhost:3000`.

---

## 5. Topologie de référence et volumes persistants

- **Namespace Dédié** : `arcia` (Namespace applicatif unifié pour tous les services).
- **Stockage Persistant** :
  - Mode d'accès : `ReadWriteOnce` (RWO).
  - Volumes créés :
    - `open-webui-pvc` : `20Gi` (extensible selon tranche RAG)
    - `hermes-user-pvc` : `20Gi` (instance Hermes partagée)
    - `litellm-db-pvc` : `10Gi` (base PostgreSQL 16)
    - `hermes-user-<slug>-pvc` (par Power User dédié) : `10Gi`

---

## 6. Ingress et certificats TLS automatiques

1. **Contrôleur d'Ingress (Traefik ou NGINX)** :
   - Route les flux HTTP (`80`) et HTTPS (`443`).
   - Gère les middlewares (`entra-id-auth` via `oauth2-proxy` et `litellm-ratelimit` sur `/v1`).
2. **Cert-Manager & Let's Encrypt** :
   - Version : `v1.16.1`.
   - `ClusterIssuer` : `letsencrypt-prod` ([deploy/manifests/01-cert-manager-issuer.yaml](../../deploy/manifests/01-cert-manager-issuer.yaml)).
   - Challenge ACME HTTP-01 automatique dès que le nom DNS public configuré (ex: `assistant.example.org`) pointe sur le cluster.

---

## 7. Outils d'administration et scripts

Les opérations sur le cluster sont entièrement outillées dans le dossier `scripts/` :

- **Exécution de commandes Kubernetes** :
  ```powershell
  .\scripts\Invoke-K3s.ps1 "get pods -n arcia -o wide"
  ```
- **Provisionnement d'un Pod Power User dédié** :
  ```powershell
  .\scripts\Spawn-PowerUser.ps1 prenom.nom@example.org -Team engineering
  ```
- **Injection et mise à jour des Secrets** :
  ```powershell
  .\scripts\Apply-Secrets.ps1
  ```
- **Recette & Suite de Validation Automatisée** :
  ```powershell
  Get-Content .\scripts\test-validation.sh -Raw | .\scripts\Invoke-K3s.ps1 -RawShell "bash -s"
  ```
