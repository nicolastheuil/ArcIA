# Manifests Kubernetes — ArcIA v0.4 (Namespace unifié `arcia`)

Ce dossier regroupe les manifests Kubernetes ordonnés pour déployer l'intégralité de la plateforme ArcIA v0.4 sur n'importe quel cluster Kubernetes. Tous les services sont déployés dans le namespace unifié `arcia`.

## Ordre d'Application & Cartographie des Manifests

Les manifests sont préfixés de `00` à `09` pour garantir un déploiement déterministe respectant les dépendances :

| N° | Fichier | Composants Déployés | Description & Ports |
|:---:|---|---|---|
| **00** | [00-traefik-chart.yaml](00-traefik-chart.yaml) | `HelmChartConfig` (Traefik) | Configuration de l'Ingress Controller Traefik. |
| **01** | [01-cert-manager-issuer.yaml](01-cert-manager-issuer.yaml) | `ClusterIssuer` (Let's Encrypt) | Émission automatique des certificats TLS via HTTP-01. |
| **02** | [02-oauth2-proxy.yaml](02-oauth2-proxy.yaml) | `Deployment`, `Service`, `Middleware` | Passerelle d'authentification SSO OpenID Connect (OIDC) avec Microsoft Entra ID (`/oauth2/auth`, port 4180). |
| **03** | [03-presidio.yaml](03-presidio.yaml) | `Deployment`, `Service` | Bouclier DLP souverain fail-closed (secrets, IP, PII fr+en) monté depuis le ConfigMap `presidio-code` (port 8080). |
| **04** | [04-ingress.yaml](04-ingress.yaml) | `Ingress`, `Middleware` Traefik | Routage HTTPS centralisé (`/`, `/v1`, `/studio`, `/gateway`, `/api/teams/messages`) avec ForwardAuth et RateLimiting. |
| **05a**| [05-litellm-db.yaml](05-litellm-db.yaml) | `StatefulSet`, `Service`, `PVC` | Base de données PostgreSQL 16 pour la comptabilité LiteLLM, budgets d'équipe et clés virtuelles nominatives (port 5432). |
| **05b**| [05-litellm.yaml](05-litellm.yaml) | `Deployment`, `Service`, `ConfigMap` | Passerelle d'inférence universelle v0.4 (`simple/free`, `simple/auto`, `openrouter/deepseek/deepseek-v4.1-flash`, `openrouter/*`), ZDR, guardrail Presidio et quotas (port 4000). |
| **06** | [06-hermes-agent.yaml](06-hermes-agent.yaml) | `Deployment`, `Service`, `PVC`, `ConfigMap` | Moteur d'agents Hermes (`agentic/free`, `agentic/auto`, `agentic/expert`), Studio Kanban (port 9119), Gateway (port 8642) et plugin `hermes-governance-plugin`. |
| **07** | [07-open-webui.yaml](07-open-webui.yaml) | `Deployment`, `Service`, `PVC` | Portail web conversationnel hybride (`simple/*` & `agentic/*`), verrouillage strict (SSO O365 / création locale manuelle uniquement, signup et BYOK désactivés, port 8080). |
| **08** | [08-teams-bot.yaml](08-teams-bot.yaml) | `Deployment`, `Service` | Adaptateur bot Microsoft Teams monté depuis le ConfigMap `teams-bot-code`, connecté à `simple/auto` et `/agent` → Hermes `agentic/auto` (port 3978). |
| **09** | [09-network-policy.yaml](09-network-policy.yaml) | `NetworkPolicy` | Isolation réseau intra-namespace (Default DenyAll, flux stricts inter-pods et bouclier DLP étanche). |
| **PU** | [templates/hermes-poweruser.template.yaml](templates/hermes-poweruser.template.yaml) | `Deployment`, `Service`, `PVC`, `Ingress` | Gabarit de provisionnement à la demande des pods Hermes dédiés pour Power Users (`.\scripts\Spawn-PowerUser.ps1`). |

## Application Manuelle ou Automatisée

* **Via les scripts de déploiement (Recommandé)** :
  ```powershell
  .\scripts\Deploy-ArcIA.ps1
  ```
  ```bash
  ./scripts/deploy-arcia.sh
  ```
* **Application Kustomize déclarative** :
  ```bash
  kubectl apply -k deploy/manifests/
  ```

Pour le détail des volumes, des variables d'environnement et des secrets requis, consulter le [Guide du Déploiement Universel](../../docs/guides/deploiement-universel.md).
