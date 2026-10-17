# Quickstart ArcIA v0.4

Ce guide vous accompagne pas-à-pas pour déployer, configurer et utiliser la plateforme d'entreprise **ArcIA v0.4** sur n'importe quel cluster Kubernetes (ou en mode Lab Docker).

---

## 1. Prérequis

Pour déployer ArcIA, vous devez disposer de :
1. **Un cluster Kubernetes opérationnel** (EKS, AKS, GKE, K3s, kubeadm, Kubernetes 1.28+) :
   - Contrôleur d'Ingress (Traefik ou NGINX) installé.
   - Cert-Manager pour l'émission automatique des certificats SSL/TLS Let's Encrypt.
   - Une `StorageClass` provisionnant des volumes persistants (PVC).
2. **Outil CLI `kubectl`** configuré avec les droits d'administration sur le cluster.
3. **Python 3.8+** (utilisé par le moteur de déploiement universel, sans dépendance tierce requise).
4. **Une clé d'API LLM Cloud** (ex: [OpenRouter](https://openrouter.ai/)).

---

## 2. Déploiement Simplifié en 2 Étapes

### Étape 1 : Cloner le dépôt

```bash
git clone https://github.com/votre-org/ArcIA.git
cd ArcIA
```

### Étape 2 : Lancer le Setup Wizard Graphique

Pour une installation fluide sans manipulation manuelle de fichiers YAML, lancez le Wizard interactif depuis la racine du dépôt :

```powershell
# Sous Windows (PowerShell) :
.\wizard.ps1
```
```bash
# Sous Linux / macOS :
./wizard.sh
```

Le Wizard ([scripts/wizard.py](../../scripts/wizard.py) + interface [scripts/wizard_ui/index.html](../../scripts/wizard_ui/index.html)) s'ouvre dans votre navigateur et vous propose deux parcours :

#### Parcours A : Installer une nouvelle instance ArcIA
1. **Dépôt Git d'Instance Privé** :
   - Connectez votre compte **GitHub** ou **GitLab** avec un jeton personnel (PAT).
   - Le Wizard teste les permissions et **crée automatiquement le dépôt privé** d'instance (ex: `ArcIA-instance-prod`).
   - Définissez un **mot de passe maître de chiffrement** : tous les secrets d'instance (`instance-secrets.enc`) sont chiffrés en **AES-256-GCM** (dérivation PBKDF2 100 000 itérations) avant d'être sauvegardés sur votre Git privé. Le dépôt racine ArcIA reste ainsi 100% générique et inviolable.
2. **Cible & Infrastructure d'Hébergement** :
   Le Wizard propose trois cibles d'hébergement selon vos besoins :
   - **Connexion à un environnement Kubernetes existant (EKS, AKS, GKE, K3s, kubeadm...)** :
     - Connexion via contexte `kubeconfig` local ou accès SSH distant.
     - **Audit de qualification exhaustif en 6 volets** avant déploiement (API Server, version >= 1.28, capacité CPU/RAM des nœuds, contrôleur Ingress, Cert-Manager CRD, StorageClass CSI dynamique, droits RBAC).
   - **Cluster K3s sur VMware (vCenter / ESXi)** :
     - Dimensionnement matériel interactif par tranche d'utilisateurs avec **espace RAG & base vectorielle ChromaDB dédié** (`50Gi` à `2Ti`).
     - Test de connectivité TLS/vSphere intégré en un clic.
   - **Déploiement local sur ce poste avec Docker (Mode Lab)** :
     - Démarrage instantané via Docker Compose ([docker-compose.lab.yml](../../docker-compose.lab.yml)) sans cluster Kubernetes.
     - Détection en direct du daemon Docker Engine et accès immédiat sur `http://localhost:3000`.
3. **Réseau & Certificats** : FQDN public (`https://assistant.example.org/`) et émission automatique Let's Encrypt (ou port local `3000` en mode Lab).
4. **Passerelle LLM & Sélection des 5 Profils Canoniques** : Saisie de votre clé [OpenRouter](https://openrouter.ai/) et choix du profil par défaut (`simple/auto`, `simple/free`, `agentic/auto`, `agentic/free`, `agentic/expert`).
5. **Hermes Studio & Desktop** : Génération automatique des mots de passe admin et du jeton PAT.
6. **Modules Optionnels Ré-exécutables** : Activez à votre rythme le SSO Microsoft Entra ID ou le bot Teams avec les guides intégrés.
7. **Auto-configuration intégrale** : Presidio DLP (double barrière), Open-WebUI, LiteLLM (avec base PostgreSQL 16), le plugin CCR/RTK (`services/hermes/plugin.py`) et les compétences natives (Ponytail, Graphify, Public-APIs) sont provisionnés automatiquement.
8. **Déploiement & Sauvegarde** : Déploiement en streaming, suivi de l'export et de la synchronisation chiffrée vers votre dépôt d'instance privé.

#### Parcours B : Restaurer une instance existante
1. Indiquez l'URL de votre dépôt Git d'instance privé (`https://github.com/mon-orga/ArcIA-instance-prod.git`) et votre token d'accès.
2. Saisissez votre **mot de passe maître de déchiffrement**.
3. Le Wizard récupère et déchiffre automatiquement `instance-secrets.enc` et pré-remplit l'intégralité de la configuration.
4. Cliquez sur **Déployer** pour reconstruire fidèlement l'instance sur n'importe quel cluster Kubernetes.

---

### Alternative en ligne de commande (Mode Headless)

Si vous déployez dans un pipeline CI/CD ou préférez l'édition manuelle :
1. Copiez `arcia.config.yaml.example` vers `arcia.config.yaml` :
   ```bash
   cp arcia.config.yaml.example arcia.config.yaml
   ```
2. Renseignez les paramètres obligatoires (`public_fqdn`, `openrouter_api_key`).
3. Lancez le déploiement :
   ```powershell
   # Déploiement sous Windows PowerShell
   .\scripts\Deploy-ArcIA.ps1

   # Déploiement sous Linux / Bash
   ./scripts/deploy-arcia.sh
   ```

---

## 3. Configuration de LiteLLM & Catalogue des 5 Profils Canoniques

### Où renseigner les clés d'entreprise ?

La passerelle d'inférence d'entreprise **LiteLLM Proxy** centralise les modèles et masque les clés d'API derrière des profils virtuels sécurisés :

1. Les secrets d'entreprise sont stockés dans les secrets Kubernetes `arcia-env-secret` et `litellm-secret`.
2. Pour ajouter ou modifier des clés de fournisseurs, éditez `secrets/arcia.env` :
   ```env
   OPENROUTER_API_KEY=sk-or-v1-votre-cle-reelle
   ```
3. Appliquez immédiatement la mise à jour des secrets dans le cluster :
   ```powershell
   # Sous Windows
   .\scripts\Apply-Secrets.ps1

   # Sous Linux
   ./scripts/apply-secrets.sh
   ```
4. Redémarrez la passerelle LiteLLM pour prise en compte immédiate :
   ```powershell
   .\scripts\Invoke-K3s.ps1 "rollout restart deployment litellm-proxy -n arcia"
   ```

### Les 5 Profils Canoniques Disponibles

Dès le premier déploiement, Open-WebUI expose les **5 profils canoniques ArcIA v0.4** grâce à son raccordement hybride (LiteLLM Direct + Hermes Agent) :
- **`simple/free`** : Chat direct rapide sans coût via OpenRouter Free (`openrouter/openrouter/free`).
- **`simple/auto`** *(Défaut)* : Chat direct polyvalent équilibrant performance et coût (`openrouter/auto`).
- **`agentic/free`** : Session autonome Hermes outillée sur palier gratuit (`openrouter/openrouter/free`).
- **`agentic/auto`** : Session autonome Hermes avec outils, recherche web, compression CCR et skills (`openrouter/auto`).
- **`agentic/expert`** : Session autonome Hermes haute performance (`openrouter/deepseek/deepseek-v4.1-flash`) pour l'architecture et le code complexe.

Toutes les requêtes sortant vers des modèles cloud bénéficient de :
1. **Zero Data Retention (ZDR)** : Forcé au niveau de LiteLLM via `extra_body: {provider: {zdr: true}}`.
2. **Double Barrière Presidio DLP Fail-Closed** : Caviardage préalable en amont dans Hermes (`/sanitize`) et en aval dans LiteLLM (`/analyze` + `/anonymize`).
3. **Comptabilité et Budgets PostgreSQL** : Chaque requête est tracée dans la base PostgreSQL 16 (`litellm-db`).

---

## 4. Portail Open-WebUI, SSO Entra ID & Pods Dédiés Power Users

### Accès au Portail Web & Configuration SSO Entra ID

Ouvrez votre navigateur sur `https://<public_fqdn>/` (ex: `https://assistant.example.org`).

- **Avec SSO Entra ID activé** (`entra_id_sso.enabled: true`) :
  - L'authentification OIDC v2.0 est déléguée à Microsoft Entra ID.
  - Dans le portail Azure, déclarez impérativement :
    - `https://<public_fqdn>/oauth/oidc/callback` *(Callback OIDC natif Open-WebUI)*
    - `https://<public_fqdn>/oauth2/callback` *(Callback OAuth2-Proxy pour Hermes Studio `/studio`)*
- **Sans SSO (Mode local)** : Le premier compte créé devient le compte administrateur d'Open-WebUI (`ENABLE_SIGNUP=false` verrouille ensuite toute auto-inscription publique).

### Utilisateurs Standards vs Power Users

- **Utilisateurs Standards** : Accèdent directement à Open-WebUI (profils `simple/*` et `agentic/*`) ainsi qu'au bot Microsoft Teams.
- **Power Users** : En plus d'Open-WebUI (`simple/*` + `agentic/*`), chaque Power User dispose d'un **Pod Hermes dédié sur Kubernetes** (`/poweruser/<slug>/studio`) provisionné via [scripts/Spawn-PowerUser.ps1](../../scripts/Spawn-PowerUser.ps1) :
  ```powershell
  .\scripts\Spawn-PowerUser.ps1 dev-lead@example.org -Team engineering
  ```
  Cette commande crée un pod Hermes isolé avec un PVC `10Gi` dédié, une `SOUL.md` personnalisée et un Studio Kanban personnel.

---

## 5. Hermes Studio (Port 9119) & Gateway (Port 8642)

- **Hermes Studio (Kanban)** : Accessible à `https://<public_fqdn>/studio` (protégé par SSO Entra ID et mot de passe admin). Permet de suivre l'exécution des missions longues, les réflexions (Chain of Thought) et l'utilisation des outils.
- **Hermes Gateway & Desktop** : L'application client lourd **Hermes Desktop** se connecte sur `https://<public_fqdn>/gateway` avec votre jeton PAT.
- **Tokenmaxing CCR & RTK** : Le plugin [services/hermes/plugin.py](../../services/hermes/plugin.py) compresse automatiquement les résultats JSON volumineux (> 8 Ko) avec cache SHA-256 réversible (`arcia_restore_tool_result`) et compacte les appels `git log`.

---

## 6. Intégration Microsoft Teams (Optionnel)

1. Dans `arcia.config.yaml`, configurez la section `teams_bot` :
   ```yaml
   teams_bot:
     enabled: true
     app_id: "VOTRE-APP-ID-AZURE-BOT"
     app_password: "VOTRE-SECRET-AZURE-BOT"
   ```
2. Redéployez la plateforme avec `.\scripts\Deploy-ArcIA.ps1` ou `./scripts/deploy-arcia.sh`.
3. Côté Azure Bot Service, définissez le Webhook de messagerie sur :
   `https://<public_fqdn>/api/teams/messages`
4. Les collaborateurs discutent en direct (`simple/auto`) ou lancent une mission agentique via `/agent <mission>` (`agentic/auto`).

---

## 7. Vérification & Recette Automatisée

Pour valider l'intégrité opérationnelle de la plateforme déployée, exécutez la suite de recette complète :

```powershell
# Exécution des tests unitaires locaux
python -m unittest discover -s tests -v

# Exécution à distance de la recette sur le cluster via Invoke-K3s
Get-Content .\scripts\test-validation.sh -Raw | .\scripts\Invoke-K3s.ps1 -RawShell "bash -s"
```

Cette suite valide automatiquement :
1. Le statut opérationnel de tous les pods du namespace `arcia`.
2. Le caviardage DLP Presidio sur `/sanitize` et `/healthz`.
3. La disponibilité LiteLLM sur `/health/liveliness`.
4. La réactivité d'Hermes Studio (9119) et Gateway (8642).
5. La réponse de l'adaptateur Teams Bot sur `/healthz`.
6. La disponibilité du portail Open-WebUI sur `/health`.

---

## 8. Exploitation Quotidienne & Liens Utiles

- [Runbook d'Exploitation & Maintenance](exploitation.md) : Consultation des logs, redémarrage des services, injection de secrets.
- [Sauvegarde et Reconstruction](sauvegarde-reconstruction.md) : Sauvegarde d'etcd, persistance des PVC et reprise après incident.
- [Gouvernance Presidio DLP](../guides/confidentialite-presidio.md) : Détail de la double barrière DLP et politiques de caviardage.
- [Passerelle LiteLLM](../guides/inference-litellm.md) : Configuration avancée des quotas et des fournisseurs.
