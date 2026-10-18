<p align="left">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.5.2-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <a href="../README.md"><img src="https://img.shields.io/badge/☸️_Deploy-IaC_Root-0C2762?style=flat-square" alt="Deploy"></a>
  <img src="https://img.shields.io/badge/Namespace-arcia-6BE7DD?style=flat-square&logoColor=050712" alt="Namespace arcia">
</p>

# 📦 Manifestes Kubernetes — ArcIA v0.5.2

> **[🏠 Accueil ArcIA](../../README.md)** › **[☸️ Déploiement](../README.md)** › **Manifestes Kubernetes**

Ce dossier regroupe les manifestes Kubernetes ordonnés permettant de déployer et de mettre à jour sans coupure (`RollingUpdate`) l'intégralité de la plateforme **ArcIA v0.5.2** sur n'importe quel cluster Kubernetes dans le namespace unifié `arcia`.

---

## 🔢 Ordre d'application et cartographie des manifestes

Les manifestes sont préfixés de `00` à `09` afin de garantir un déploiement déterministe respectant la chaîne de dépendances (Réseau/TLS → Sécurité DLP → Base & Passerelle IA → Agents → Portail → Isolation) :

| N° | Fichier manifeste | Ressources K8s | Rôle et ports internes |
|:---:|---|---|---|
| **00** | **[00-traefik-chart.yaml](00-traefik-chart.yaml)** | `HelmChartConfig` | Configuration avancée de l'Ingress Controller Traefik (timeouts SSE/WebSocket). |
| **01** | **[01-cert-manager-issuer.yaml](01-cert-manager-issuer.yaml)** | `ClusterIssuer` | Émission et renouvellement automatiques des certificats TLS Let's Encrypt (HTTP-01). |
| **02** | **[02-oauth2-proxy.yaml](02-oauth2-proxy.yaml)** | `Deployment`, `Service`, `Middleware` | Passerelle d'authentification SSO OpenID Connect (OIDC) Microsoft Entra ID (`/oauth2/auth`, `:4180`). |
| **03** | **[03-presidio.yaml](03-presidio.yaml)** | `Deployment`, `Service` | Bouclier DLP souverain *fail-closed* (secrets, IP, PII `fr`+`en`) monté depuis `presidio-code` (`:8080`). |
| **04** | **[04-ingress.yaml](04-ingress.yaml)** | `Ingress`, `Middleware` | Routage HTTPS unifié (`/`, `/v1`, `/studio`, `/gateway`, `/api/teams/messages`) avec ForwardAuth et RateLimit. |
| **05a** | **[05-litellm-db.yaml](05-litellm-db.yaml)** | `StatefulSet`, `Service`, `PVC` | Base PostgreSQL 16 dédiée à la comptabilité LiteLLM, aux budgets d'équipe et aux clés PAT (`:5432`). |
| **05b** | **[05-litellm.yaml](05-litellm.yaml)** | `Deployment`, `Service`, `ConfigMap` | Passerelle d'inférence LiteLLM v0.5.2 (5 profils canoniques, `zdr: true`, guardrail Presidio aval, `:4000`). |
| **06** | **[06-hermes-agent.yaml](06-hermes-agent.yaml)** | `Deployment`, `Service`, `PVC`, `ConfigMap` | Moteur Hermes Agent (`agentic/*`), Studio Kanban (`:9119`), Gateway (`:8642`) et plugin `hermes-governance-plugin`. |
| **07** | **[07-open-webui.yaml](07-open-webui.yaml)** | `Deployment`, `Service`, `PVC` | Portail collaborateur hybride (`simple/*` & `agentic/*`), SSO Entra ID, RAG ChromaDB et BYOK désactivé (`:8080`). |
| **08** | **[08-teams-bot.yaml](08-teams-bot.yaml)** | `Deployment`, `Service` | Adaptateur Bot Framework Microsoft Teams (`simple/auto` + commande `/agent` → Hermes, `:3978`). |
| **09** | **[09-network-policy.yaml](09-network-policy.yaml)** | `NetworkPolicy` | Cloisonnement réseau Zero-Trust intra-namespace (*Default DenyAll* + règles explicites inter-pods). |
| **PU** | **[templates/hermes-poweruser.template.yaml](templates/hermes-poweruser.template.yaml)** | `Deployment`, `Service`, `PVC`, `Ingress` | Gabarit de provisionnement des Pods Hermes dédiés par Power User (`.\scripts\Spawn-PowerUser.ps1`). |

---

## ⚡ Application et mise à jour Zero-Downtime

* **Via l'assistant graphique (Installation ou RollingUpdate en ligne)** :
  ```powershell
  .\wizard.ps1
  ```
* **Via les orchestrateurs CLI multiplateformes** :
  ```powershell
  .\scripts\Deploy-ArcIA.ps1
  ```
  ```bash
  ./scripts/deploy-arcia.sh
  ```
* **Via Kustomize déclaratif** :
  ```bash
  kubectl apply -k deploy/manifests/
  ```

> [!TIP]
> Pour connaître le détail des variables injectées et des volumes persistants, consultez le [Guide du déploiement universel](../../docs/guides/deploiement-universel.md).
