# Quickstart ArcIA v0.5.2

Ce guide vous accompagne pas-à-pas pour déployer, configurer et utiliser la plateforme d'entreprise **ArcIA v0.5.2** sur n'importe quel cluster Kubernetes (ou en mode Lab Docker).

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

## 2. Déploiement simplifié en 2 étapes

### Étape 1 : cloner le dépôt

```bash
git clone https://github.com/votre-org/ArcIA.git
cd ArcIA
```

### Étape 2 : lancer le Setup Wizard graphique

Pour une installation fluide sans manipulation manuelle de fichiers YAML, lancez le Wizard interactif depuis la racine du dépôt :

```powershell
# Sous Windows (PowerShell) :
.\wizard.ps1
```
```bash
# Sous Linux / macOS :
./wizard.sh
```

Le Wizard ([scripts/wizard.py](../../scripts/wizard.py) + interface [scripts/wizard_ui/index.html](../../scripts/wizard_ui/index.html)) s'ouvre sur un **centre de pilotage graphique épuré** (conforme à la charte *taste-skill v2* / *minimalist-ui*), doté d'une barre de navigation supérieure fluide et de **cinq espaces dédiés** :

#### Parcours A : installer une nouvelle instance
Dans la page dédiée d'installation (munie d'un bandeau supérieur permettant de pré-remplir toutes les étapes depuis un fichier `arcia.config.yaml` ou `arcia.env` existant) :
1. **Dépôt Git d'instance privé** :
   - Connectez votre compte **GitHub** ou **GitLab** avec un jeton personnel (PAT).
   - Le Wizard teste les permissions et **crée automatiquement le dépôt privé** d'instance (ex: `ArcIA-instance-prod`).
   - Définissez un **mot de passe maître de chiffrement** : tous les secrets d'instance (`instance-secrets.enc`) sont chiffrés en **AES-256-GCM** (dérivation PBKDF2 100 000 itérations) avant d'être sauvegardés sur votre Git privé. Le dépôt racine ArcIA reste ainsi 100% générique et inviolable.
2. **Cible & infrastructure d'hébergement** :
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
3. **Réseau et certificats** : FQDN public (`https://assistant.example.org/`) et émission automatique Let's Encrypt (ou port local `3000` en mode Lab).
4. **Passerelle LLM et sélection des 5 profils canoniques** : Saisie de votre clé [OpenRouter](https://openrouter.ai/) et choix du profil par défaut (`simple/auto`, `simple/free`, `agentic/auto`, `agentic/free`, `agentic/expert`).
5. **Hermes Studio et desktop** : Génération automatique des mots de passe admin et du jeton PAT.
6. **Modules optionnels ré-exécutables** : Activez à votre rythme le SSO Microsoft Entra ID ou le bot Teams avec les guides intégrés.
7. **Auto-configuration intégrale** : Presidio DLP (double barrière), Open-WebUI, LiteLLM (avec base PostgreSQL 16), le plugin CCR/RTK (`services/hermes/plugin.py`) et les compétences natives (Ponytail, Graphify, Public-APIs) sont provisionnés automatiquement.
8. **Déploiement et sauvegarde** : Déploiement en streaming, suivi de l'export et de la synchronisation chiffrée vers votre dépôt d'instance privé.

#### Parcours B : gérer les power users
Accessible via l'onglet **Power users** ou la carte d'accueil correspondante :
1. **Supervision des pods et volumes** : Affichage bento des métriques clés (utilisateurs nominatifs, pods actifs vs en veille, stockage PVC total alloué).
2. **Tableau interactif des collaborateurs** :
   - Statut en temps réel du Pod (`Actif (Running)`, `En veille (0/0)`, `Démarrage (Pending)`, `Erreur`).
   - Jauge visuelle de remplissage et capacité du PVC avec code couleur dynamique (vert &lt; 70%, ambre &ge; 70%, rouge &ge; 85%).
   - Accès direct au Studio web du collaborateur (`/poweruser/<slug>/studio`).
3. **Actions unitaires et administration** :
   - **Mise en veille / réveil instantané** via `kubectl scale deployment --replicas=0/1` pour optimiser la mémoire RAM du cluster.
   - **Agrandissement du PVC à chaud** sans interruption de service (*Kubernetes Online Volume Expansion*) avec validation de dimensionnement (10Gi, 20Gi, 50Gi, 100Gi+).
   - **Provisionnement d'un nouveau collaborateur** (nom, slug K8s, email, template de personnalité `SOUL.md` et capacité initiale).
   - **Suppression sécurisée** avec option de conservation ou destruction du volume de données.
   - **Synchronisation globale des modèles** vers tous les pods Power Users.

#### Parcours C : routage des modèles et passerelle d'inférence
Accessible via l'onglet **Routage des modèles** ou la carte d'accueil :
1. **Fournisseurs et clés d'API** :
   - Cartes dédiées pour chaque fournisseur d'inférence : **OpenRouter** (ZDR Cloud recommandé), **OpenAI**, **Anthropic**, **Mistral AI**, **Google Gemini** et **vLLM / Ollama local** (souverain sur site).
   - Test de connectivité en un clic avec validation des clés et des quotas en direct.
   - Masquage sécurisé des clés d'API et sauvegarde protégée dans `arcia.config.yaml`.
2. **Noms communs d'entreprise et correspondance vers les vrais modèles** :
   - Définition des identifiants vus par les utilisateurs dans Open-WebUI et Teams (`simple/auto`, `simple/free`, `agentic/auto`, `agentic/free`, `agentic/expert`, + alias personnalisés).
   - Association vers le vrai modèle amont (ex: `openrouter/anthropic/claude-3-5-sonnet`, `openrouter/deepseek/deepseek-v4.1-flash`, `local_vllm/mistral-large-instruct`).
   - Configuration du modèle de repli automatique (*fallback*) en cas d'indisponibilité du modèle principal.
   - Boutons de préréglages instantanés (*Tout OpenRouter ZDR*, *Hybride souverain vLLM local*, *Multi-fournisseurs directs*).
   - Synchronisation à chaud de la ConfigMap `litellm-config` sur le cluster Kubernetes.

#### Parcours D : mettre à jour mon instance
1. Sur la page d'accueil ou l'onglet **Mises à jour**, ouvrez le centre de mise à jour.
2. Vous pouvez y charger votre fichier `arcia.config.yaml` pour cibler votre contexte Kubernetes.
3. Le Wizard interroge en direct les dépôts officiels amont (*Open-WebUI, Hermes Agent, LiteLLM Proxy, Presidio DLP, OAuth2-Proxy, Teams Bot, ArcIA Core & Skills*) et compare avec les versions de vos manifestes locaux.
4. Sélectionnez les composants souhaités et lancez la séquence (ou testez-la via **Simuler la séquence (Dry-Run)**).
5. L'orchestrateur conserve le catalogue déclaré dans le wizard pendant les **6 phases séquentielles**. Les services sans état utilisent `RollingUpdate (maxUnavailable=0, maxSurge=1)` ; Hermes et Open-WebUI conservent `Recreate`, avec interruption prévue pour protéger leurs volumes et états persistants. Les sondes `readinessProbe` sont contrôlées et un rollback (`kubectl rollout undo`) est déclenché en cas d'échec. Les ressources d'icônes sont vérifiées après le rechargement du portail ; leur contrôle HTTP ne remplace pas une recette navigateur authentifiée.

#### Parcours E : restaurer une instance (PRA)
1. Sur la page d'accueil ou l'onglet **Sauvegarde et PRA**, ouvrez la page de reprise.
2. Choisissez entre le chargement direct d'un fichier `arcia.config.yaml` / `arcia.env` local (**Option A**) ou la récupération depuis votre dépôt Git d'instance privé chiffré (**Option B**).
3. En Option B, indiquez l'URL de votre dépôt Git d'instance privé (`https://github.com/mon-orga/ArcIA-instance-prod.git`), votre token d'accès PAT et votre **mot de passe maître de déchiffrement**.
4. Le Wizard récupère et déchiffre automatiquement `instance-secrets.enc`, pré-remplit l'intégralité de la configuration et vous permet de redéployer l'instance sur le cluster cible.

---

### Alternative en ligne de commande (mode headless)

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

## 3. Configuration de LiteLLM et catalogue des 5 profils canoniques

Si l'onglet **Models** de LiteLLM retourne `token_not_found_in_db`, commencez par
renouveler la session d'administration. Vérifiez ensuite le parcours avec
`python scripts/diagnose_litellm.py --config arcia.config.yaml` : aucune inférence
ni modification de ressource, aucune clé affichée. Consultez le
[diagnostic du catalogue et de la session LiteLLM](../guides/inference-litellm.md#diagnostic-du-catalogue-et-de-la-session-dadministration)
avant de redémarrer ou de réappliquer une configuration différente.

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

### Les 5 profils canoniques disponibles

Dès le premier déploiement, Open-WebUI expose les **5 profils canoniques ArcIA v0.5.2** grâce à son raccordement hybride (LiteLLM Direct + Hermes Agent) :
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

## 4. Portail Open-WebUI, SSO Entra ID et pods dédiés Power Users

### Accès au portail web et configuration SSO Entra ID

Ouvrez votre navigateur sur `https://<public_fqdn>/` (ex: `https://assistant.example.org`).

- **Avec SSO Entra ID activé** (`entra_id_sso.enabled: true`) :
  - L'authentification OIDC v2.0 est déléguée à Microsoft Entra ID.
  - Dans le portail Azure, déclarez impérativement :
    - `https://<public_fqdn>/oauth/oidc/callback` *(Callback OIDC natif Open-WebUI)*
    - `https://<public_fqdn>/oauth2/callback` *(Callback OAuth2-Proxy pour Hermes Studio `/studio`)*
- **Sans SSO (Mode local)** : Le premier compte créé devient le compte administrateur d'Open-WebUI (`ENABLE_SIGNUP=false` verrouille ensuite toute auto-inscription publique).

### Utilisateurs standards vs power users

- **Utilisateurs standards** : Accèdent directement à Open-WebUI (profils `simple/*` et `agentic/*`) ainsi qu'au bot Microsoft Teams.
- **Power Users** : En plus d'Open-WebUI (`simple/*` + `agentic/*`), chaque Power User dispose d'un **Pod Hermes dédié sur Kubernetes** (`/poweruser/<slug>/studio`) provisionné via [scripts/Spawn-PowerUser.ps1](../../scripts/Spawn-PowerUser.ps1) :
  ```powershell
  .\scripts\Spawn-PowerUser.ps1 dev-lead@example.org -Team engineering
  ```
  Cette commande crée un pod Hermes isolé avec un PVC `10Gi` dédié, une `SOUL.md` personnalisée et un Studio Kanban personnel.

---

## 5. Hermes Studio (port 9119) et Gateway (port 8642)

- **Hermes Studio (Kanban)** : Accessible à `https://<public_fqdn>/studio` (protégé par SSO Entra ID et mot de passe admin). Permet de suivre l'exécution des missions longues, les réflexions (Chain of Thought) et l'utilisation des outils.
- **Hermes Gateway & Desktop** : L'application client lourd **Hermes Desktop** se connecte sur `https://<public_fqdn>/gateway` avec votre jeton PAT.
- **Tokenmaxing CCR & RTK** : Le plugin [services/hermes/plugin.py](../../services/hermes/plugin.py) compresse automatiquement les résultats JSON volumineux (> 8 Ko) avec cache SHA-256 réversible (`arcia_restore_tool_result`) et compacte les appels `git log`.

---

## 6. Intégration Microsoft Teams (optionnel)

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

## 7. Vérification et recette automatisée

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

## 8. Exploitation quotidienne et liens utiles

- [Runbook d'Exploitation & Maintenance](exploitation.md) : Consultation des logs, redémarrage des services, injection de secrets.
- [Sauvegarde et Reconstruction](sauvegarde-reconstruction.md) : Sauvegarde d'etcd, persistance des PVC et reprise après incident.
- [Gouvernance Presidio DLP](../guides/confidentialite-presidio.md) : Détail de la double barrière DLP et politiques de caviardage.
- [Passerelle LiteLLM](../guides/inference-litellm.md) : Configuration avancée des quotas et des fournisseurs.


## Icônes et sauvegardes depuis le wizard

Le détail de l'intégration figure dans le [correctif du wizard](../brief-icones-modeles-wizard.md). L'icône normale, ZDR ou locale est calculée à partir des déclarations de l'administrateur ; `hosting` peut préciser l'hébergement sans modifier la politique d'inférence. Dans une instance existante, **Enregistrer le routage** applique aussi les icônes ; en cas d'échec partiel, réutiliser ce même bouton. Dans le parcours d'une nouvelle instance, les icônes sont appliquées automatiquement au déploiement, avec les modèles et fournisseurs personnalisés déclarés.

Installer les dépendances AES-GCM avec `python -m pip install -r requirements-wizard.txt` (Python 3.9+). Dans **Sauvegarde et reprise**, reprendre le dépôt privé déclaré et déverrouiller le coffre dans le formulaire local. Après une première sauvegarde réussie, chaque modification de configuration du wizard déclenche un instantané chiffré et un push limité aux fichiers d'instance. Le YAML et l'environnement sont également surveillés tant que le wizard fonctionne. Les erreurs restent affichées ; les instantanés chiffrés en attente sont réessayés sans force-push. Le coffre persiste via DPAPI sous Windows ; sous Linux/macOS, le déverrouillage est à renouveler après redémarrage du wizard.

Le rechargement des icônes Kubernetes redémarre Open-WebUI selon sa stratégie `Recreate`. Le contrôle HTTP des ressources ne remplace pas une recette avec session authentifiée. La restauration remet les fichiers locaux ; réappliquer ensuite depuis le wizard pour mettre à jour le cluster.


### Rechargement des déclarations de modèles

Le wizard relit les déclarations enregistrées, y compris les listes YAML sur plusieurs lignes produites par un export. Une liste explicitement vide reste vide. Sur une instance existante, l'absence ou l'illisibilité des déclarations ne réintroduit pas un catalogue historique : une erreur de lecture est signalée et la vue courante est conservée. Le lecteur autonome prend en charge les séquences indentées ou sans retrait supplémentaire, les descriptions repliées et les commentaires dans les chaînes citées.
