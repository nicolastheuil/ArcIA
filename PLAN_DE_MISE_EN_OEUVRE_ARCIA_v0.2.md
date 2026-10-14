# Blueprint Maître : Mise en Œuvre Complète d'ArcIA v0.2

Ce document est le **plan d'exécution unique et autonome** du projet **ArcIA v0.2**. Un agent démarrant dans une nouvelle session sans historique peut exécuter **100 % du déploiement à partir de ce seul fichier**.

---

## 1. Fiche d'Identité & Arbitrages Validés

| Paramètre | Valeur Validée | Justification & Détails |
| :--- | :--- | :--- |
| **Domaine Public / Ingress** | **`arcia.arcitek.io`** | Traefik (Ingress natif K3s) avec redirection HTTPS et support WebSocket. |
| **Certificats TLS** | **Cert-Manager (Let's Encrypt)** | Délivrance et renouvellement 100% automatiques via HTTP-01 challenge. |
| **Stockage Persistant (CSI)** | **VMware vSphere CSI** | StorageClass par défaut du cluster K3s (hébergé sur 3 VMs VMware). |
| **Passerelle & Routage IA** | **LiteLLM Proxy (`:4000/v1`)** | Standard d'entreprise : gestion du modèle `auto`, failover, et budget. |
| **Fournisseur Cloud Initial** | **OpenRouter (`openrouter/auto`)** | Clé unique donnant accès à Claude 3.5 Sonnet, GPT-4o et Mistral Large. |
| **Modèles Locaux Souverains** | **vLLM On-Premise** | Serveurs GPU internes de l'entreprise (données ultra-sensibles). |
| **Bouclier de Confidentialité** | **Presidio DLP (Guardrail LiteLLM)** | **Obligatoire sur TOUT flux sortant Cloud (Entreprise ET comptes perso)**.<br>*Bypass pour les modèles internes vLLM.* |
| **Runtime Agentique** | **Hermes Agent (Nous Research)** | 1 Pod par utilisateur avec son volume persistant (`~/.hermes`). |
| **Tokenmaxing (Réduction Tokens)** | **RTK + Headroom (Dans Hermes)** | Hooks natifs : compression des sorties shell (`git log`) et des gros JSON (>8 Ko). |
| **Catalogue de Skills** | **`npx skills` / `SKILL.md`** | Pipeline d'ingestion synchronisant ECC, Superpowers et Vercel sur un volume partagé. |
| **Portail Web Utilisateur (Grand Public)** | **Open-WebUI (`:8080`)** | Interface ChatGPT/Gemini, SSO Entra ID natif, chat épuré, RAG drag & drop. |
| **Studio Agentique Web (Avancé)** | **Hermes Native Dashboard (`:9119`)** | Orchestrateur Kanban multi-agents (Triage, Todo, In Progress, Blocked, Done), file de tâches SQLite, dispatcher de sous-agents en temps réel via WebSockets. Accessible à tous les collaborateurs authentifiés. |
| **Client Lourd Desktop** | **Hermes Desktop (Remote Gateway `:8642`)** | Client natif (Mac/Win/Linux) connecté en WebSocket sur `https://arcia.arcitek.io/gateway` avec streaming de session et Bot Screen (bureau distant Xfce). |
| **Authentification Unifiée MS365** | **`oauth2-proxy` + Traefik ForwardAuth** | **Zero-Trust Enterprise Gateway :** Sécurise `/studio` et `/gateway` via le tenant Microsoft Entra ID de l'entreprise. Tous les collaborateurs de l'organisation y ont accès avec leur compte MS365. Supporte sessions Web et jetons Bearer (JWT Entra ID ou Personal Access Token PAT). |
| **Intégration Microsoft Teams** | **Bot Teams (Bot Framework)** | **Chat rapide en DM 1:1** + **Intervention sur mention `@ArcIA` en canal d'équipe**. |
| **Gestion des Secrets** | **`secrets/arcia.env`** | Fichier d'environnement unique appliqué en une commande K8s. |

---

## 2. Schéma d'Architecture de Production

```mermaid
flowchart TD
    subgraph Clients["Clients & Identité d'Entreprise"]
        UserBrowser["Navigateur Web Grand Public\n(https://arcia.arcitek.io)"]
        TeamsClient["Client Microsoft Teams\n(DM 1:1 & Mentions @ArcIA)"]
        StudioBrowser["Navigateur Web Studio\n(https://arcia.arcitek.io/studio)"]
        HermesDesktop["Hermes Desktop Client\n(Remote Gateway: https://arcia.arcitek.io/gateway)"]
        EntraID["Microsoft Entra ID / MS365\n(Tenant ID Entreprise, SSO, MFA)"]
    end

    subgraph K3sIngress["Entrée Réseau K3s & Authentification Zero-Trust"]
        IngressPublic["Traefik Ingress Public\n(Certificat Let's Encrypt arcia.arcitek.io)"]
        IngressProtected["Traefik Ingress Studio & Gateway\n(ForwardAuth Middleware)"]
        OAuth2Proxy["oauth2-proxy (:4180)\n- Validation Compte MS365 Collaborateur\n- Support Session Web & Bearer Token / PAT"]
    end

    subgraph CoreServices["Socle Applicatif (Namespace : arcia)"]
        WebUI["Open-WebUI (:8080)\n- Chat Copilot épuré\n- RAG Drag & Drop\n- SSO Entra ID natif"]
        HermesStudio["Hermes Studio Dashboard (:9119)\n- Tableau Kanban Multi-Agents\n- Suivi des sous-agents en direct (WebSockets)\n- File de tâches SQLite & Cron jobs"]
        HermesGateway["Hermes API & Gateway (:8642)\n- WebSocket streaming pour Hermes Desktop\n- Dispatcher multi-profils OS\n- Remote Desktop / Bot Screen"]
        TeamsBot["Teams Bot Adapter (:3978)\n- Bot Framework SDK\n- Routage par User AAD ID"]
        SharedSkills["Volume Partagé (/opt/shared-skills)\nCatalogue ECC + Superpowers + Vercel"]
    end

    subgraph SecurityRouting["Passerelle IA & Egress DLP"]
        LiteLLM["LiteLLM Proxy (:4000/v1)\n- Modèle 'Auto (Entreprise)'\n- Failover OpenRouter\n- Réception clés BYOK perso"]
        PresidioDLP["Presidio DLP Guardrail (:8080)\n- Regex secrets (clés API, IP, mots de passe)\n- Pseudonymisation PII (noms, emails, IBAN)"]
    end

    subgraph InferenceEndpoints["Destinations des Modèles"]
        InternalvLLM["Serveurs vLLM Internes On-Premise\n(Données confidentielles, Bypass Presidio)"]
        CloudOpenRouter["OpenRouter Cloud Gateway\n(Claude 3.5, GPT-4o, Mistral - AVEC Presidio)"]
        PersonalEndpoints["Providers Personnels Utilisateurs\n(Comptes BYOK - AVEC Presidio)"]
    end

    UserBrowser & TeamsClient & StudioBrowser & HermesDesktop --> EntraID

    UserBrowser -->|/ (Portail Chat)| IngressPublic
    TeamsClient -->|/api/teams/messages| IngressPublic
    StudioBrowser -->|/studio (Kanban)| IngressProtected
    HermesDesktop -->|/gateway (WebSocket/API)| IngressProtected

    IngressProtected <-->|ForwardAuth Vérif SSO/Bearer| OAuth2Proxy
    OAuth2Proxy <-->|Validation Jeton Entreprise| EntraID

    IngressPublic --> WebUI
    IngressPublic --> TeamsBot
    IngressProtected -->|Session OK| HermesStudio
    IngressProtected -->|Bearer OK| HermesGateway

    WebUI -->|Pont Délégation Tâche| HermesGateway
    TeamsBot --> HermesGateway
    SharedSkills -.->|Monté Read-Only| HermesGateway

    HermesGateway --> LiteLLM
    LiteLLM --> PresidioDLP

    LiteLLM -->|Flux interne souverain| InternalvLLM
    PresidioDLP -->|Flux Cloud d'entreprise assaini| CloudOpenRouter
    PresidioDLP -->|Flux Compte perso assaini| PersonalEndpoints
```

---

## 3. Template Unique des Secrets (`secrets/arcia.env.template`)

Créer le fichier `secrets/arcia.env` à partir de ce template :

```bash
# ==============================================================================
# SECRETS D'ENTREPRISE ARCIA v0.2
# ==============================================================================

# 1. Fournisseur Cloud d'Entreprise (OpenRouter)
OPENROUTER_API_KEY="sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 2. Microsoft Entra ID (Azure AD SSO Entreprise pour Open-WebUI, Hermes Studio et Hermes Desktop)
ENTRA_TENANT_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
ENTRA_CLIENT_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
ENTRA_CLIENT_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Clé de chiffrement des cookies de session oauth2-proxy (générer via : openssl rand -base64 32)
OAUTH2_PROXY_COOKIE_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 3. Hermes Gateway & Remote API Server
HERMES_API_SERVER_KEY="sk-arcia-hermes-gateway-master-key-32b"

# 4. Microsoft Teams Bot (Azure Bot Service)
TEAMS_BOT_APP_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
TEAMS_BOT_APP_PASSWORD="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 5. Serveur d'Inférence Interne (vLLM On-Premise - Optionnel pour phase 1)
VLLM_INTERNAL_URL="http://vllm-internal.corp.local:8000/v1"

# 6. Clé Maître de Chiffrement Interne Presidio (32 caractères aléatoires)
PRESIDIO_MASTER_KEY="arcia-sanitizer-master-secret-key-32b"
```

---

## 4. Script d'Exécution Séquentielle (Les 6 Phases)

Dans la nouvelle session, il suffit d'exécuter chronologiquement les commandes ci-dessous :

### Phase 1 : Historisation Git intégrale & Réinitialisation de `main`

```bash
cd /chemin/vers/ArcIA

# 1. Tag annoté permanent de la version précédente (v0.1 legacy)
git tag -a v0.1-legacy-archive -m "Sanctuaire intégral du code ArcIA v0.1 legacy"

# 2. Branche d'archive poussée sur GitHub
git branch archive/v0.1-legacy
git push origin archive/v0.1-legacy
git push origin v0.1-legacy-archive

# 3. Purge complète de l'ancienne tuyauterie sur main
git rm -r --ignore-unmatch bootstrap/ infra/ schemas/ validation/ tests/
git rm -f scripts/vmware_* scripts/Bootstrap* scripts/Verify* scripts/Test* scripts/wsl_*
git rm -f requirements-controller-* requirements-vmware.txt versions.lock.yaml

# 4. Création de la nouvelle arborescence propre v0.2
mkdir -p deploy/manifests services/{hermes,presidio,litellm,teams} skills/ secrets/ docs/

# 5. Commit d'initialisation propre
git commit -m "chore: bascule officielle vers ArcIA v0.2 (feuille blanche)"
git push origin main
```

---

### Phase 2 : Connexion SSH K3s & Application des Secrets

```bash
# 1. Connexion SSH au cluster K3s
ssh <user>@<k3s-master-ip>

# 2. Vérification du cluster et de la StorageClass VMware CSI
kubectl get nodes
kubectl get storageclass
# Vérifier que la StorageClass VMware est bien présente et par défaut

# 3. Création du namespace unifié
kubectl create namespace arcia --dry-run=client -o yaml | kubectl apply -f -

# 4. Nettoyage des anciens namespaces résiduels de la v0.1
kubectl delete namespace arcia-hermes arcia-routing arcia-identity --ignore-not-found=true

# 5. Création du dossier hôte partagé pour les skills
sudo mkdir -p /var/data/arcia/shared-skills
sudo chmod 777 /var/data/arcia/shared-skills
```

#### Script d'application des Secrets Kubernetes (`scripts/apply-secrets.sh`) :
```bash
#!/bin/bash
set -e
source secrets/arcia.env

echo "[*] Création des Secrets Kubernetes dans le namespace arcia..."

# Secret OpenRouter
kubectl create secret generic enterprise-llm-secret \
  --namespace arcia \
  --from-literal=openrouter-key="$OPENROUTER_API_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

# Secret Entra ID (utilisé par Open-WebUI et oauth2-proxy)
kubectl create secret generic entraid-secret \
  --namespace arcia \
  --from-literal=client-id="$ENTRA_CLIENT_ID" \
  --from-literal=client-secret="$ENTRA_CLIENT_SECRET" \
  --from-literal=tenant-id="$ENTRA_TENANT_ID" \
  --from-literal=cookie-secret="$OAUTH2_PROXY_COOKIE_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -

# Secret Hermes Gateway API
kubectl create secret generic hermes-gateway-secret \
  --namespace arcia \
  --from-literal=api-server-key="$HERMES_API_SERVER_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

# Secret Teams Bot
kubectl create secret generic teams-bot-secret \
  --namespace arcia \
  --from-literal=app-id="$TEAMS_BOT_APP_ID" \
  --from-literal=app-password="$TEAMS_BOT_APP_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

# Secret Presidio
kubectl create secret generic presidio-secret \
  --namespace arcia \
  --from-literal=master-key="$PRESIDIO_MASTER_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "[+] Tous les secrets Kubernetes ont été appliqués avec succès."
```

---

### Phase 3 : Déploiement de Cert-Manager, OAuth2-Proxy, Presidio & Ingress

#### A. Cert-Manager (Let's Encrypt automatique) (`deploy/manifests/01-cert-manager-issuer.yaml`)
```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: contact@arcitek.io
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
    - http01:
        ingress:
          class: traefik
```

#### B. Authentification Zero-Trust MS365 (`deploy/manifests/02-oauth2-proxy.yaml`)
Ce manifest installe `oauth2-proxy` et configure le middleware Traefik `ForwardAuth` pour sécuriser l'accès aux interfaces (`/studio` et `/gateway`) avec Microsoft Entra ID pour l'ensemble des collaborateurs du tenant :

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: oauth2-proxy
  namespace: arcia
spec:
  replicas: 1
  selector:
    matchLabels:
      app: oauth2-proxy
  template:
    metadata:
      labels:
        app: oauth2-proxy
    spec:
      containers:
      - name: oauth2-proxy
        image: quay.io/oauth2-proxy/oauth2-proxy:v7.6.0
        args:
        - --provider=azure
        - --azure-tenant=$(ENTRA_TENANT_ID)
        - --client-id=$(ENTRA_CLIENT_ID)
        - --client-secret=$(ENTRA_CLIENT_SECRET)
        - --cookie-secret=$(OAUTH2_PROXY_COOKIE_SECRET)
        - --cookie-secure=true
        - --email-domain=*
        - --skip-jwt-bearer-tokens=true
        - --extra-jwt-issuers=https://login.microsoftonline.com/$(ENTRA_TENANT_ID)/v2.0=$(ENTRA_CLIENT_ID)
        - --pass-authorization-header=true
        - --pass-user-headers=true
        - --set-xauthrequest=true
        - --reverse-proxy=true
        - --http-address=0.0.0.0:4180
        env:
        - name: ENTRA_TENANT_ID
          valueFrom:
            secretKeyRef:
              name: entraid-secret
              key: tenant-id
        - name: ENTRA_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: entraid-secret
              key: client-id
        - name: ENTRA_CLIENT_SECRET
          valueFrom:
            secretKeyRef:
              name: entraid-secret
              key: client-secret
        - name: OAUTH2_PROXY_COOKIE_SECRET
          valueFrom:
            secretKeyRef:
              name: entraid-secret
              key: cookie-secret
        ports:
        - containerPort: 4180
          name: http
---
apiVersion: v1
kind: Service
metadata:
  name: oauth2-proxy
  namespace: arcia
spec:
  selector:
    app: oauth2-proxy
  ports:
  - port: 4180
    targetPort: 4180
    name: http
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: entra-id-auth
  namespace: arcia
spec:
  forwardAuth:
    address: http://oauth2-proxy.arcia.svc.cluster.local:4180/
    trustForwardHeader: true
    authResponseHeaders:
      - "X-Auth-Request-User"
      - "X-Auth-Request-Email"
      - "X-Auth-Request-Preferred-Username"
      - "Authorization"
```

#### C. Presidio DLP Service (`deploy/manifests/03-presidio.yaml`)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: presidio-dlp
  namespace: arcia
spec:
  replicas: 1
  selector:
    matchLabels:
      app: presidio-dlp
  template:
    metadata:
      labels:
        app: presidio-dlp
    spec:
      containers:
      - name: presidio
        image: python:3.11-slim
        command: ["/bin/sh", "-c", "pip install fastapi uvicorn presidio-analyzer spacy && python -m spacy download fr_core_news_sm && python -m spacy download en_core_web_sm && uvicorn app:app --host 0.0.0.0 --port 8080"]
        ports:
        - containerPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: presidio-dlp
  namespace: arcia
spec:
  selector:
    app: presidio-dlp
  ports:
  - port: 8080
    targetPort: 8080
```

#### D. Ingress Traefik Séparé (Public vs Studio & Gateway) (`deploy/manifests/04-ingress.yaml`)
```yaml
# 1. Ingress Public (Open-WebUI, Bot Teams, Callback OAuth2)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: arcia-public-ingress
  namespace: arcia
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    traefik.ingress.kubernetes.io/router.entrypoints: "web,websecure"
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  tls:
  - hosts:
    - arcia.arcitek.io
    secretName: arcia-tls-cert
  rules:
  - host: arcia.arcitek.io
    http:
      paths:
      - path: /oauth2
        pathType: Prefix
        backend:
          service:
            name: oauth2-proxy
            port:
              number: 4180
      - path: /api/teams/messages
        pathType: Prefix
        backend:
          service:
            name: teams-bot-adapter
            port:
              number: 3978
      - path: /
        pathType: Prefix
        backend:
          service:
            name: open-webui
            port:
              number: 8080
---
# 2. Ingress Studio & Gateway (Hermes Studio & Hermes Desktop Gateway - Sécurisé par Entra ID)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: arcia-studio-ingress
  namespace: arcia
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    traefik.ingress.kubernetes.io/router.entrypoints: "web,websecure"
    traefik.ingress.kubernetes.io/router.tls: "true"
    # Authentification obligatoire via MS365 Entra ID
    traefik.ingress.kubernetes.io/router.middlewares: arcia-entra-id-auth@kubernetescrd
spec:
  tls:
  - hosts:
    - arcia.arcitek.io
    secretName: arcia-tls-cert
  rules:
  - host: arcia.arcitek.io
    http:
      paths:
      - path: /studio
        pathType: Prefix
        backend:
          service:
            name: hermes-studio
            port:
              number: 9119
      - path: /gateway
        pathType: Prefix
        backend:
          service:
            name: hermes-studio
            port:
              number: 8642
```

---

### Phase 4 : Déploiement de LiteLLM Proxy & Synchronisation Skills

#### A. LiteLLM Proxy (`deploy/manifests/05-litellm.yaml`)
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: litellm-config
  namespace: arcia
data:
  config.yaml: |
    model_list:
      # Modèle 'auto' d'entreprise routé sur OpenRouter avec failover
      - model_name: auto
        litellm_params:
          model: openrouter/auto
          api_key: os.environ/OPENROUTER_API_KEY
          fallbacks: ["openrouter/anthropic/claude-3.5-sonnet", "openrouter/openai/gpt-4o"]
      
      # Modèle interne d'entreprise souverain (vLLM local)
      - model_name: local-internal
        litellm_params:
          model: openai/hermes-3-70b
          api_base: http://vllm-internal.corp.local:8000/v1
          api_key: "none"

    litellm_settings:
      # Anonymisation universelle obligatoire vers le Cloud
      guardrails:
        - guardrail_name: "presidio-guard"
          mode: "pre_call"
          default_on: true
          presidio_analyzer_url: "http://presidio-dlp:8080"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: litellm-proxy
  namespace: arcia
spec:
  replicas: 1
  selector:
    matchLabels:
      app: litellm-proxy
  template:
    metadata:
      labels:
        app: litellm-proxy
    spec:
      containers:
      - name: litellm
        image: ghcr.io/berriai/litellm:main-latest
        ports:
        - containerPort: 4000
        env:
        - name: OPENROUTER_API_KEY
          valueFrom:
            secretKeyRef:
              name: enterprise-llm-secret
              key: openrouter-key
        volumeMounts:
        - name: config
          mountPath: /app/config.yaml
          subPath: config.yaml
      volumes:
      - name: config
        configMap:
          name: litellm-config
---
apiVersion: v1
kind: Service
metadata:
  name: litellm-proxy
  namespace: arcia
spec:
  selector:
    app: litellm-proxy
  ports:
  - port: 4000
    targetPort: 4000
```

#### B. Synchronisation des Compétences (`skills/sync-skills.sh`)
```bash
#!/bin/bash
set -e
TARGET="/var/data/arcia/shared-skills"
mkdir -p "$TARGET"

echo "[*] Synchronisation des catalogues de compétences standards..."
# Installation et mise en cache des skills vérifiées
npx skills add anthropics/anthropic-quickstarts --destination "$TARGET/anthropics" || true
npx skills add vercel/ai-sdk --destination "$TARGET/vercel" || true
npx skills add obra/superpowers --destination "$TARGET/superpowers" || true

echo "[+] Synchronisation réussie dans $TARGET"
```

---

### Phase 5 : Déploiement d'Hermes, Open-WebUI & Bot Teams

#### A. Dockerfile Hermes avec Tokenmaxing (`services/hermes/Dockerfile`)
```dockerfile
FROM ghcr.io/nousresearch/hermes-agent:latest
RUN apt-get update && apt-get install -y git curl python3-pip jq procps && rm -rf /var/lib/apt/lists/*
RUN curl -L https://github.com/rtk-ai/rtk/releases/latest/download/rtk-linux-x86_64 -o /usr/local/bin/rtk \
    && chmod +x /usr/local/bin/rtk
COPY plugin.py /opt/hermes/plugins/arcia_tokenmaxing.py
ENV OPENAI_API_BASE=http://litellm-proxy.arcia.svc:4000/v1
ENV OPENAI_MODEL_NAME=auto
```

#### B. Pod Hermes Core, Studio Dashboard & Gateway API (`deploy/manifests/06-hermes-agent.yaml`)
Ce manifest déploie le runtime Hermes avec persistance PVC, monte le catalogue de compétences partagées, et lance simultanément :
1. **Hermes Studio Dashboard (port 9119)** : L'orchestrateur Kanban multi-agents et la supervision en direct.
2. **Hermes Gateway & API Server (port 8642)** : Le serveur WebSocket / HTTP pour connecter le client **Hermes Desktop** et recevoir les délégations d'OpenWebUI.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: hermes-user-pvc
  namespace: arcia
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 20Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hermes-agent
  namespace: arcia
spec:
  replicas: 1
  selector:
    matchLabels:
      app: hermes-agent
  template:
    metadata:
      labels:
        app: hermes-agent
    spec:
      containers:
      - name: hermes
        image: arcia/hermes-agent:v0.2
        command:
        - /bin/sh
        - -c
        - |
          # Démarrage de la Gateway API (port 8642) en arrière-plan pour Hermes Desktop
          hermes gateway --host 0.0.0.0 --port 8642 &
          # Démarrage du Studio Dashboard (port 9119) au premier plan pour le pilotage Kanban
          hermes dashboard --host 0.0.0.0 --port 9119
        ports:
        - containerPort: 9119
          name: studio
        - containerPort: 8642
          name: gateway
        env:
        - name: API_SERVER_ENABLED
          value: "true"
        - name: API_SERVER_KEY
          valueFrom:
            secretKeyRef:
              name: hermes-gateway-secret
              key: api-server-key
        volumeMounts:
        - name: user-state
          mountPath: /root/.hermes
        - name: shared-skills
          mountPath: /opt/shared-skills
          readOnly: true
      volumes:
      - name: user-state
        persistentVolumeClaim:
          claimName: hermes-user-pvc
      - name: shared-skills
        hostPath:
          path: /var/data/arcia/shared-skills
          type: DirectoryOrCreate
---
apiVersion: v1
kind: Service
metadata:
  name: hermes-studio
  namespace: arcia
spec:
  selector:
    app: hermes-agent
  ports:
  - port: 9119
    targetPort: 9119
    name: studio
  - port: 8642
    targetPort: 8642
    name: gateway
```

#### C. Open-WebUI (`deploy/manifests/07-open-webui.yaml`)
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: open-webui-pvc
  namespace: arcia
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 20Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: open-webui
  namespace: arcia
spec:
  replicas: 1
  selector:
    matchLabels:
      app: open-webui
  template:
    metadata:
      labels:
        app: open-webui
    spec:
      containers:
      - name: open-webui
        image: ghcr.io/open-webui/open-webui:main
        ports:
        - containerPort: 8080
        env:
        - name: OPENAI_API_BASE_URL
          value: "http://litellm-proxy.arcia.svc:4000/v1"
        - name: DEFAULT_MODELS
          value: "auto"
        - name: ENABLE_OAUTH_SIGNUP
          value: "true"
        - name: OAUTH_MERGE_ACCOUNTS_BY_EMAIL
          value: "true"
        - name: OAUTH_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: entraid-secret
              key: client-id
        - name: OAUTH_CLIENT_SECRET
          valueFrom:
            secretKeyRef:
              name: entraid-secret
              key: client-secret
        - name: OPENID_PROVIDER_URL
          valueFrom:
            secretKeyRef:
              name: entraid-secret
              key: tenant-id
        volumeMounts:
        - name: webui-data
          mountPath: /app/backend/data
      volumes:
      - name: webui-data
        persistentVolumeClaim:
          claimName: open-webui-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: open-webui
  namespace: arcia
spec:
  selector:
    app: open-webui
  ports:
  - port: 8080
    targetPort: 8080
```

#### D. Adaptateur Microsoft Teams Bot (`deploy/manifests/08-teams-bot.yaml`)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: teams-bot-adapter
  namespace: arcia
spec:
  replicas: 1
  selector:
    matchLabels:
      app: teams-bot-adapter
  template:
    metadata:
      labels:
        app: teams-bot-adapter
    spec:
      containers:
      - name: adapter
        image: python:3.11-slim
        command: ["/bin/sh", "-c", "pip install botbuilder-core botbuilder-schema aiohttp && python app.py"]
        env:
        - name: MICROSOFT_APP_ID
          valueFrom:
            secretKeyRef:
              name: teams-bot-secret
              key: app-id
        - name: MICROSOFT_APP_PASSWORD
          valueFrom:
            secretKeyRef:
              name: teams-bot-secret
              key: app-password
        - name: LITELLM_URL
          value: "http://litellm-proxy.arcia.svc:4000/v1"
        ports:
        - containerPort: 3978
---
apiVersion: v1
kind: Service
metadata:
  name: teams-bot-adapter
  namespace: arcia
spec:
  selector:
    app: teams-bot-adapter
  ports:
  - port: 3978
    targetPort: 3978
```

---

### Guide de Connexion du Client Hermes Desktop

1. **Génération du Token d'Accès** :
   * L'utilisateur se connecte via son navigateur sur `https://arcia.arcitek.io/studio`.
   * L'authentification SSO Microsoft 365 valide son appartenance à l'organisation.
   * Dans ses paramètres de profil, il récupère son **Personal Access Token (PAT)** ou le token de passerelle d'entreprise.
2. **Configuration dans l'application Hermes Desktop** :
   * Ouvrir l'application **Hermes Desktop** sur son poste de travail.
   * Aller dans **Settings → Gateways → Add Gateway** :
     * **Name** : `ArcIA Enterprise Cluster`
     * **URL** : `https://arcia.arcitek.io/gateway`
     * **Auth Token / Key** : Coller le jeton (PAT)
   * Le client établit immédiatement la liaison WebSocket sécurisée. L'utilisateur dispose de ses onglets de session, de l'observabilité des sous-agents en direct et de la fonction **Bot Screen** (prise de contrôle graphique de l'agent si besoin).

---

### Phase 6 : Validation & Protocole de Recette Complet

Exécuter le script de validation automatique :

```bash
# 1. Vérification des Pods, Services et Ingress
kubectl get pods -n arcia -o wide
kubectl get ingress -n arcia

# 2. Test Presidio DLP (Caviardage Secrets & PII)
curl -s -X POST http://presidio-dlp.arcia.svc:8080/sanitize \
  -H "Content-Type: application/json" \
  -d '{"text": "Bonjour, mon mot de passe est SecretPass123 et mon email est nicolas@arcitek.io"}'
# Vérifier la présence de [SECRET_REMOVED] et [ARCIA_EMAIL_...]

# 3. Test du Routage LiteLLM via OpenRouter en mode 'auto'
curl -s -X POST http://litellm-proxy.arcia.svc:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Ping test ArcIA v0.2"}]}'

# 4. Test de protection Entra ID sur /studio et /gateway
# Sans authentification : doit renvoyer HTTP 302 vers login.microsoftonline.com
curl -Iv https://arcia.arcitek.io/studio
# Avec Bearer Token valide : doit répondre HTTP 200
curl -Iv https://arcia.arcitek.io/gateway -H "Authorization: Bearer VOTRE_TOKEN_PAT"

# 5. Test d'accès Web public sécurisé OpenWebUI
curl -Iv https://arcia.arcitek.io
# Vérifier que le certificat SSL Let's Encrypt est valide (HTTP 200)

# 6. Validation de bout en bout Teams
# - Ouvrir Teams > Bot @ArcIA > Envoyer "Bonjour" en DM
# - Vérifier la réponse instantanée en Markdown
# - Dans un canal, mentionner "@ArcIA quel temps fait-il ?"
```

---

## 5. Prêt pour l'Exécution

Ce document constitue la **spécification maîtresse absolue**.
Pour démarrer la nouvelle session :
1. Ouvrir le nouveau chat dans le répertoire racine du dépôt ArcIA.
2. Écrire : *"Exécute le plan de mise en œuvre contenu dans PLAN_DE_MISE_EN_OEUVRE_ARCIA.md"*.
3. L'agent déroulera les phases 1 à 6 sans aucune ambiguïté !
