# Guide de Déploiement Universel d'ArcIA v0.4 sur Kubernetes

Ce guide décrit comment déployer l'intégralité de la plateforme d'entreprise **ArcIA v0.4** sur **n'importe quel cluster Kubernetes** (EKS, AKS, GKE, K3s, vanilla Kubernetes / kubeadm, KinD, Minikube...) à partir d'un **seul et unique fichier de configuration** ou via l'assistant interactif.

---

## 1. Prérequis

Pour déployer ArcIA, vous devez disposer de :
1. **Un cluster Kubernetes opérationnel** (v1.28 ou supérieure) :
   - Un contrôleur Ingress (ex: Traefik ou NGINX).
   - Une `StorageClass` (par défaut ou spécifique) capable de provisionner des PVC dynamiques.
   - `Cert-Manager` installé si vous souhaitez l'émission automatique des certificats SSL Let's Encrypt.
2. **L'outil de ligne de commande `kubectl`** configuré avec les droits d'administration sur le cluster.
3. **Python 3.8+** (utilisé par le moteur de déploiement universel, sans aucune dépendance pip requise).
4. **Une clé d'API LLM Cloud** (ex: [OpenRouter](https://openrouter.ai/)).

---

## 2. Déploiement en 3 Étapes

### Étape 1 : Cloner le dépôt

```bash
git clone https://github.com/votre-org/ArcIA.git
cd ArcIA
```

### Étape 2 : Préparer la configuration (ou lancer le Wizard)

Vous pouvez utiliser l'installeur et centre de mise à jour interactif à la racine du dépôt (qui inclut la présentation d'architecture sur la page d'accueil, la vérification en ligne des nouvelles versions d'*Open-WebUI, Hermes, LiteLLM, Presidio, OAuth2* et la séquence de mise à jour **Zero-Downtime RollingUpdate**) :
```powershell
# Sous Windows PowerShell
.\wizard.ps1
```
```bash
# Sous Linux / macOS
./wizard.sh
```

Ou préparer manuellement le fichier de configuration unique :
```bash
# Sous Linux / macOS
cp arcia.config.yaml.example arcia.config.yaml

# Sous Windows PowerShell
Copy-Item arcia.config.yaml.example arcia.config.yaml
```

Ouvrez `arcia.config.yaml` et renseignez les sections ci-dessous.

---

## 3. Détail du Fichier de Configuration Unique

Le fichier est structuré en deux catégories clairement séparées :

### A. Éléments OBLIGATOIRES

| Section | Paramètre | Description | Exemple |
|---|---|---|---|
| `kubernetes` | `mode` | Mode d'exécution de kubectl (`local` ou `remote-ssh`) | `"local"` |
| `kubernetes` | `namespace` | Namespace Kubernetes applicatif | `"arcia"` |
| `kubernetes` | `storage_class` | StorageClass pour les volumes PVC (laisser `""` pour la classe par défaut) | `""` (ou `"gp3"`, `"local-path"`) |
| `network` | `public_fqdn` | **FQDN public** pour accéder à l'assistant | `"assistant.example.org"` |
| `network` | `ingress_class` | Contrôleur Ingress (`traefik` ou `nginx`) | `"traefik"` |
| `network` | `tls_mode` | Mode TLS (`letsencrypt-prod`, `custom-secret`, `disabled`) | `"letsencrypt-prod"` |
| `network` | `acme_email` | Email de contact Let's Encrypt | `"admin@example.org"` |
| `llm_gateway` | `openrouter_api_key` | Clé d'API OpenRouter | `"sk-or-v1-..."` |
| `hermes` | `admin_password` | Mot de passe admin pour Hermes Studio (:9119) | `"MotDePasseFort123"` |
| `hermes` | `api_token` | Jeton PAT pour Hermes Desktop Gateway (:8642) | `"arcia-pat-secret-key"` |
| `presidio` | `enabled` | Active la double barrière DLP de caviardage PII et clés | `true` |

### B. Éléments OPTIONNELS

| Section | Paramètre | Description |
|---|---|---|
| `kubernetes.remote_ssh` | `node_ip`, `ssh_user`, `ssh_port`, `ssh_key` | Paramètres de connexion SSH au nœud maître (si `mode: "remote-ssh"`), incluant le chemin vers la clé privée |
| `llm_gateway` | `local_vllm_endpoint` | URL d'un serveur GPU souverain on-premise (ex: `http://vllm.corp:8000/v1`) |
| `entra_id_sso` | `enabled` | Active l'authentification obligatoire Microsoft Entra ID pour Open-WebUI et `/studio` |
| `entra_id_sso` | `tenant_id`, `client_id`, `client_secret`, `cookie_secret` | Identifiants Microsoft Entra ID d'entreprise |
| `teams_bot` | `enabled` | Active le connecteur Bot Microsoft Teams |
| `teams_bot` | `app_id`, `app_password`, `system_prompt` | Identifiants Azure Bot Service et prompt système |
| `microsoft365_integration` | `enabled` | Active l'intégration Graph / SharePoint / Transcriptions |

---

## 4. Lancement du Déploiement

Exécutez le script selon votre système d'exploitation :

### Sous Windows (PowerShell) :
```powershell
.\scripts\Deploy-ArcIA.ps1
```

Pour tester la configuration sans l'appliquer :
```powershell
.\scripts\Deploy-ArcIA.ps1 -DryRun
```

### Sous Linux / macOS / Serveur CI :
```bash
chmod +x ./scripts/deploy-arcia.sh
./scripts/deploy-arcia.sh
```

Pour tester la configuration sans l'appliquer :
```bash
./scripts/deploy-arcia.sh arcia.config.yaml --dry-run
```

### Alternative Kustomize Déclarative :
Pour les environnements GitOps (ArgoCD, Flux) ou déploiements natifs :
```bash
kubectl apply -k deploy/manifests/
```

---

## 5. Ce que fait le Script Automatiquement

Le moteur universel de déploiement ([scripts/deploy.py](../../scripts/deploy.py)) :
1. **Teste la connectivité** avec le cluster Kubernetes et inspecte les nœuds disponibles.
2. **Détecte automatiquement la `StorageClass`** par défaut du cluster si aucune n'a été spécifiée.
3. **Crée le namespace** cible (`arcia`).
4. **Provisionne les secrets** Kubernetes sécurisés (`arcia-env-secret`, `litellm-secret`, `hermes-gateway-secret`, `presidio-secret`...) directement en mémoire via `stdin`.
5. **Synchronise les ConfigMaps des microservices** (`sync_service_configmaps` : `presidio-code`, `teams-bot-code`, `hermes-governance-plugin`) et des compétences natives (`arcia-native-skills`).
6. **Rend et applique les manifestes** adaptés à votre FQDN et à votre classe d'Ingress (incluant la base relationnelle PostgreSQL 16 `litellm-db`, LiteLLM avec Zero Data Retention et le middleware SSO `/studio`).
7. **Active ou désactive** automatiquement les composants optionnels (Teams Bot, SSO Entra ID) selon votre configuration.
8. **Surveille le rollout** et la santé de tous les Pods jusqu'à leur mise en service.
9. **Affiche la synthèse d'accès** avec les URL prêtes à l'emploi.

---

## 6. Vérification & Provisionnement Power Users

Dès que le déploiement est terminé :
1. Créez l'enregistrement DNS de type A pour votre FQDN pointant vers l'adresse IP publique de votre Ingress.
2. Ouvrez votre navigateur sur :
   - `https://<public_fqdn>/` : Portail collaborateur Open-WebUI (5 profils canoniques `simple/free`, `simple/auto`, `agentic/free`, `agentic/auto`, `agentic/expert`).
   - `https://<public_fqdn>/studio` : Dashboard Kanban multi-agents Hermes.
   - `https://<public_fqdn>/gateway` : Passerelle client lourd Hermes Desktop.
3. Déployez un pod Hermes dédié pour un Power User :
   ```powershell
   .\scripts\Spawn-PowerUser.ps1 alice@example.org -Team engineering
   ```
4. Exécutez la suite de recette automatisée :
   ```bash
   bash scripts/test-validation.sh
   ```
