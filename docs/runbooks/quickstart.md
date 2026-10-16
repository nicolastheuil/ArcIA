# Quickstart ArcIA v0.3

Ce guide vous accompagne pas-à-pas pour déployer, configurer et utiliser la plateforme souveraine d'entreprise **ArcIA v0.3** sur votre cluster Kubernetes K3s.

---

## 1. Prérequis

Pour déployer ArcIA, vous devez disposer de :
1. **Un cluster Kubernetes opérationnel** (K3s recommandé, Kubernetes 1.28+) :
   - Contrôleur d'Ingress Traefik installé.
   - Cert-Manager pour l'émission automatique des certificats SSL/TLS Let's Encrypt.
   - Une `StorageClass` provisionnant des volumes persistants (PVC).
2. **Outil CLI `kubectl`** configuré avec les droits d'administration sur le cluster.
3. **Python 3.8+** (utilisé par le moteur de déploiement universel, sans dépendance tierce requise).
4. **Une clé d'API LLM Cloud** (ex: [OpenRouter](https://openrouter.ai/) fournissant l'accès unifié à Claude 3.5 Sonnet, GPT-4o, DeepSeek-V3).

---

## 2. Déploiement Simplifié en 2 Étapes

### Étape 1 : Cloner le dépôt

```bash
git clone https://github.com/nicolastheuil/ArcIA.git
cd ArcIA
```

### Étape 2 : Lancer le Setup Wizard Graphique

Pour une installation fluide sans manipulation manuelle de fichiers YAML, lancez le Wizard interactif :

```bash
# Sous Linux / macOS :
./wizard.sh

# Sous Windows (PowerShell) :
.\wizard.ps1

# Ou avec Python directement :
python scripts/wizard.py
```

Le Wizard s'ouvre dans votre navigateur et vous propose deux parcours :

#### Parcours A : Installer une nouvelle instance ArcIA
1. **Dépôt Git d'Instance Privé** :
   - Connectez votre compte **GitHub** ou **GitLab** avec un jeton personnel (PAT).
   - Le Wizard teste les permissions et **crée automatiquement le dépôt privé** d'instance (ex: `ArcIA-instance-prod`).
   - Définissez un **mot de passe maître de chiffrement** : tous les secrets d'instance (`instance-secrets.enc`) sont chiffrés en **AES-256-GCM** (dérivation PBKDF2 100 000 itérations) avant d'être sauvegardés sur votre Git privé. Le dépôt racine ArcIA reste ainsi 100% générique et inviolable.
2. **Cible & Infrastructure d'Hébergement** :
   Le Wizard propose trois cibles d'hébergement selon vos besoins :
   - **Nouveau cluster K3s sur VMware (vCenter / ESXi)** :
     - Provisionnement automatisé de machines virtuelles Debian avec initialisation K3s HA (`scripts/Deploy-VMwareCluster.ps1`).
     - Dimensionnement matériel interactif par tranche d'utilisateurs avec **espace RAG & base vectorielle ChromaDB dédié** :
       - *Pilote (jusqu'à 20 utilisateurs)* : 1 VM All-in-One (4 vCPU, 8 Go RAM, 100 Go SSD dont 50 Go RAG, PVC `50Gi`).
       - *PME / Équipe Métier (jusqu'à 100 utilisateurs) [Recommandé]* : 3 VMs K3s HA multi-master etcd (12 vCPU, 48 Go RAM, 450 Go SSD total dont 200 Go RAG / index HNSW, PVC `200Gi`).
       - *Entreprise (jusqu'à 500 utilisateurs)* : 5 VMs (3 Master HA + 2 Workers dédiés, 28 vCPU, 112 Go RAM, 1,25 To SSD dont 600 Go RAG multi-équipes, PVC `600Gi`).
       - *Grande Entreprise (> 500 utilisateurs)* : 7+ VMs (3 Master HA + 4+ Workers extensibles, support vGPU, 88+ vCPU, 352+ Go RAM, 3,5 To SSD dont 2 To à 5 To RAG, PVC `2Ti`).
     - Test de connectivité TLS/vSphere intégré en un clic.
   - **Connexion à un environnement Kubernetes existant** :
     - Connexion via contexte `kubeconfig` local ou accès SSH distant.
     - **Audit de qualification exhaustif en 6 volets** avant déploiement (API Server, version >= 1.28, capacité CPU/RAM des nœuds, contrôleur Ingress, Cert-Manager CRD, StorageClass CSI dynamique, droits RBAC).
   - **Déploiement local sur ce poste avec Docker (Mode Lab)** :
     - Démarrage instantané via Docker Compose (`docker-compose.lab.yml`) sans cluster Kubernetes.
     - Détection en direct du daemon Docker Engine et accès immédiat sur `http://localhost:3000`.
3. **Réseau & Certificats** : FQDN public (`https://assistant.votre-entreprise.com/`) et émission automatique Let's Encrypt (ou port local `3000` en mode Lab).
4. **Passerelle LLM** : Saisie de votre clé [OpenRouter](https://openrouter.ai/) (accès à Claude 3.5 Sonnet, GPT-4o, DeepSeek-V3).
5. **Hermes Studio & Desktop** : Génération automatique des mots de passe admin et du jeton PAT.
6. **Modules Optionnels Ré-exécutables** : Activez à votre rythme le SSO Microsoft Entra ID ou le bot Teams avec les guides intégrés.
7. **Auto-configuration intégrale** : Presidio DLP, Open-WebUI, LiteLLM (avec base PostgreSQL 16) et les compétences natives (Ponytail, Graphify, Public-APIs) sont provisionnés automatiquement sans aucune manipulation technique.
8. **Déploiement & Sauvegarde** : Déploiement en streaming, suivi de l'export et de la synchronisation chiffrée vers votre dépôt d'instance privé.
9. **Accès 100% Opérationnel** : Récapitulatif instantané avec toutes les URLs prêtes à l'emploi et le lien direct vers votre dépôt d'instance.

#### Parcours B : Restaurer une instance existante
1. Indiquez l'URL de votre dépôt Git d'instance privé (`https://github.com/mon-orga/ArcIA-instance-prod.git`) et votre token d'accès.
2. Saisissez votre **mot de passe maître de déchiffrement**.
3. Le Wizard récupère et déchiffre automatiquement `instance-secrets.enc`, pré-remplit instantanément l'intégralité des 10 écrans de configuration.
4. Cliquez sur **Déployer** pour reconstruire fidèlement l'instance sur n'importe quel cluster Kubernetes en quelques minutes.

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
   bash scripts/deploy-arcia.sh
   ```


---

## 3. Configuration de LiteLLM & Clés API d'Entreprise

### Où renseigner les clés d'entreprise ?

La passerelle d'inférence d'entreprise **LiteLLM Proxy** centralise les modèles et masque les clés d'API derrière des modèles virtuels sécurisés :

1. Les secrets d'entreprise sont stockés dans le secret Kubernetes `arcia-env-secret` et `litellm-secret`.
2. Pour ajouter ou modifier des clés de fournisseurs (OpenRouter, OpenAI, Anthropic, DeepSeek, etc.), éditez `secrets/arcia.env` :
   ```env
   OPENROUTER_API_KEY=sk-or-v1-votre-cle-reelle
   OPENAI_API_KEY=sk-proj-votre-cle-openai-si-besoin
   ANTHROPIC_API_KEY=sk-ant-votre-cle-anthropic-si-besoin
   ```
3. Appliquez immédiatement la mise à jour des secrets dans le cluster :
   ```powershell
   # Sous Windows
   .\scripts\Apply-Secrets.ps1

   # Sous Linux
   bash scripts/apply-secrets.sh
   ```
4. Redémarrez la passerelle LiteLLM pour prise en compte immédiate :
   ```powershell
   .\scripts\Invoke-K3s.ps1 "rollout restart deployment litellm-proxy -n arcia"
   ```

### Modèles d'Entreprise Disponibles

Dès le premier déploiement, le catalogue managé d'entreprise est strictement aligné sur les **trois tiers canoniques ArcIA** servis par Hermes Agent à Open-WebUI :
- **`arcia/free`** : Découverte et qualification sans coût via OpenRouter Free (`openrouter/openrouter/free`).
- **`arcia/auto`** *(Défaut)* : Profil généraliste intelligent équilibrant performance et coût (`openrouter/auto`). Conçu pour le travail quotidien, l'assistance et les interactions courantes.
- **`arcia/expert`** : Profil d'élite de haute précision pour l'architecture, la revue de code et les missions agentiques complexes. Permet également la sélection dynamique de modèle dans le prompt (`/model <fournisseur/modèle>`).

Toutes les requêtes sortant vers des modèles cloud bénéficient de :
1. **Zero Data Retention (ZDR)** : Forcé au niveau de LiteLLM via `extra_body: {provider: {zdr: true}}` pour interdire l'entraînement des fournisseurs sur vos données.
2. **Caviardage Presidio DLP Fail-Closed** : Filtrage préalable des PII (emails, téléphones, cartes, IPs, IBAN) et secrets d'entreprise. En cas d'indisponibilité du filtre, la requête est bloquée pour prévenir toute fuite.
3. **Comptabilité et Budgets PostgreSQL** : Chaque requête est tracée dans la base PostgreSQL 16 (`litellm-db`) avec suivi précis de la consommation en euros.

---

## 4. Portail Open-WebUI, SSO Entra ID & Accès Power Users (PAT N3)

### Accès au Portail Web & Configuration SSO Entra ID

Ouvrez votre navigateur sur `https://<public_fqdn>/` (ex: `https://assistant.entreprise.com`).

- **Avec SSO Entra ID activé** (`entra_id_sso.enabled: true`) :
  - L'authentification OIDC v2.0 est déléguée à Microsoft Entra ID (`https://login.microsoftonline.com/<TENANT_ID>/v2.0/.well-known/openid-configuration`).
  - Dans le portail Azure (**Microsoft Entra ID > Inscriptions d'applications > Votre App > Authentification > Plateforme Web > URI de redirection**), déclarez impérativement :
    - `https://<public_fqdn>/oauth/oidc/callback` *(Callback OIDC natif Open-WebUI)*
    - `https://<public_fqdn>/oauth2/callback` *(Callback OAuth2-Proxy pour Hermes Studio / Gateway)*
- **Sans SSO (Mode local)** : Le premier compte créé devient le compte administrateur d'Open-WebUI.

### Gouvernance DLP & Proscription du BYOK non contrôlé

En conformité avec les règles de sécurité d'entreprise ArcIA v0.3 :
- `ENABLE_DIRECT_CONNECTIONS: "false"` est activé dans [deploy/manifests/07-open-webui.yaml](../../deploy/manifests/07-open-webui.yaml). Les connexions directes vers des LLM externes contournant le DLP et le stockage des clés en clair dans SQLite sont proscrits.
- Tous les échanges sur le portail WebUI transitent obligatoirement par la passerelle d'inférence d'entreprise et le bouclier DLP.

### Accès Développeurs / Power Users (Niveau N3 via /v1)

Pour les développeurs, scripts CI/CD ou IDEs (Cursor, VS Code, continue.dev) nécessitant un accès programmatique direct :
1. Les accès sont délivrés sous forme de **Personal Access Tokens (PAT)** virtuels LiteLLM gérés par l'administrateur :
   ```bash
   # Création d'une clé virtuelle d'entreprise avec budget mensuel de 25€
   python scripts/arcia_keys.py create --user dev-lead@entreprise.com --tier N3 --budget 25 --duration 30
   ```
2. Le développeur configure son IDE avec le endpoint d'entreprise :
   - **Base URL** : `https://<public_fqdn>/v1`
   - **API Key** : `sk-arcia-xxxxxxxx` (la clé virtuelle générée)
   - **Modèle** : `arcia/auto` ou `arcia/expert`
3. Les requêtes passent par l'Ingress Traefik (middleware RateLimit), Presidio DLP et LiteLLM avec décompte automatique sur le budget alloué.

---

## 5. Hermes Studio (Port 9119) & Gateway (Port 8642)

Pour les ingénieurs IA et utilisateurs avancés souhaitant orchestrer des agents autonomes :

- **Hermes Studio (Kanban)** : Accessible à `https://<public_fqdn>/studio`. Connectez-vous avec `admin` et le mot de passe défini dans `hermes.admin_password`. Il permet de suivre l'exécution des missions longues, les réflexions (Chain of Thought), l'utilisation des outils et la collaboration multi-agents.
- **Hermes Gateway & Desktop** : L'application client lourd **Hermes Desktop** se connecte en WebSocket sur `https://<public_fqdn>/gateway` avec votre jeton PAT.
- **Gestion de Contexte & Sobriété** : Hermes s'appuie sur ses mécanismes natifs de gestion de contexte (compaction d'historique, troncature de résultats) configurés dans `~/.hermes/config.yaml`, sans plugin ConfigMap tiers instable.
- **Gouvernance des Clés d'Accès** : L'outil CLI `scripts/arcia_keys.py` permet de superviser, lister et révoquer les clés d'agents et de développeurs en temps réel.

---

## 6. Intégration Microsoft Teams (Optionnel)

Pour permettre à vos collaborateurs d'échanger avec ArcIA directement dans Microsoft Teams :

1. Dans `arcia.config.yaml`, configurez la section `teams_bot` :
   ```yaml
   teams_bot:
     enabled: true
     app_id: "VOTRE-APP-ID-AZURE-BOT"
     app_password: "VOTRE-SECRET-AZURE-BOT"
   ```
2. Redéployez la plateforme avec `.\scripts\Deploy-ArcIA.ps1` ou `python scripts/deploy.py`.
3. Côté Azure Bot Service, définissez le Webhook de messagerie sur :
   `https://<public_fqdn>/api/teams/messages`
4. Les collaborateurs peuvent immédiatement discuter avec le bot en direct message (1:1) ou le mentionner dans les canaux d'équipe : `@ArcIA quelle est la procédure pour X ?`.

---

## 7. Vérification & Recette Automatisée

Pour valider l'intégrité opérationnelle de la plateforme déployée, exécutez la suite de recette complète (6/6 tests end-to-end) :

```powershell
# Exécution à distance sur le cluster via Invoke-K3s
Get-Content .\scripts\test-validation.sh -Raw | .\scripts\Invoke-K3s.ps1 -RawShell "bash -s"
```

Cette suite valide automatiquement :
1. Le statut opérationnel de tous les pods du namespace `arcia`.
2. Le caviardage DLP Presidio sur `/sanitize`.
3. La disponibilité LiteLLM sur `/health/readiness`.
4. La réactivité d'Hermes Studio (9119) et Gateway (8642).
5. La réponse de l'adaptateur Teams Bot sur `/health`.
6. La disponibilité du portail Open-WebUI sur `/health`.

---

## 8. Exploitation Quotidienne & Liens Utiles

- [Runbook d'Exploitation & Maintenance](exploitation.md) : Consultation des logs, redémarrage des services, injection de secrets.
- [Sauvegarde et Reconstruction](sauvegarde-reconstruction.md) : Sauvegarde d'etcd, persistance des PVC et reprise après incident.
- [Gouvernance Presidio DLP](../guides/confidentialite-presidio.md) : Détail des motifs de détection et politiques de caviardage.
- [Passerelle LiteLLM](../guides/inference-litellm.md) : Configuration avancée des quotas et des fournisseurs.
