# Manifests Kubernetes — ArcIA v0.3 (Namespace unifié `arcia`)

Ce dossier regroupe les manifests Kubernetes ordonnés pour déployer l'intégralité de la plateforme ArcIA v0.3 sur un cluster K3s. Tous les services sont déployés dans le namespace unifié `arcia`.

## Ordre d'Application & Cartographie des Manifests

Les manifests sont préfixés de `00` à `10` pour garantir un déploiement déterministe respectant les dépendances :

| N° | Fichier | Composants Déployés | Description & Ports |
|:---:|---|---|---|
| **00** | [00-traefik-chart.yaml](00-traefik-chart.yaml) | `HelmChartConfig` (K3s Traefik) | Configuration de l'Ingress Controller Traefik embarqué dans K3s. |
| **01** | [01-cert-manager-issuer.yaml](01-cert-manager-issuer.yaml) | `ClusterIssuer` (Let's Encrypt) | Émission automatique des certificats TLS via HTTP-01. |
| **02** | [02-oauth2-proxy.yaml](02-oauth2-proxy.yaml) | `Deployment`, `Service`, `Middleware` | Passerelle d'authentification SSO OpenID Connect (OIDC) avec Microsoft Entra ID (`/oauth2/auth`, port 4180). |
| **03** | [03-presidio.yaml](03-presidio.yaml) | `Deployment`, `Service`, `ConfigMap` | Bouclier DLP souverain fail-closed (secrets, IP, PII fr+en) avant envoi aux LLMs cloud (port 8080). |
| **04** | [04-ingress.yaml](04-ingress.yaml) | `Ingress`, `Middleware` Traefik | Routage HTTPS centralisé (`/`, `/v1`, `/studio`, `/gateway`, `/api/teams/messages`) avec ForwardAuth et RateLimiting. |
| **05a**| [05-litellm-db.yaml](05-litellm-db.yaml) | `StatefulSet`, `Service`, `PVC` | Base de données PostgreSQL pour la comptabilité LiteLLM, budgets d'équipe et clés virtuelles nominatives (port 5432). |
| **05b**| [05-litellm.yaml](05-litellm.yaml) | `Deployment`, `Service`, `ConfigMap` | Passerelle d'inférence universelle v0.3, catalogue à 3 paliers (`standard`, `expert`, `reasoning`), ZDR et quotas (port 4000). |
| **06** | [06-hermes-agent.yaml](06-hermes-agent.yaml) | `Deployment`, `Service`, `PVC`, `ConfigMap` | Moteur d'agents Hermes, Studio Kanban (port 9119) et Gateway (port 8642) configuré sur LiteLLM. |
| **07** | [07-open-webui.yaml](07-open-webui.yaml) | `Deployment`, `Service`, `PVC` | Portail web conversationnel grand public, verrouillage strict (SSO O365 / création locale manuelle uniquement, signup désactivé), sans contournement BYOK (port 8080). |
| **08** | [08-teams-bot.yaml](08-teams-bot.yaml) | `Deployment`, `Service`, `ConfigMap` | Adaptateur bot Microsoft Teams branché sur le palier `arcia/standard` (port 3978). |
| **09** | [09-network-policy.yaml](09-network-policy.yaml) | `NetworkPolicy` | Isolation réseau intra-namespace (Default DenyAll, flux stricts inter-pods et bouclier DLP étanche). |
| **10** | [10-skills-sync-cronjob.yaml](10-skills-sync-cronjob.yaml) | `CronJob` | Tâche planifiée de mise à jour des compétences (suspendue par défaut en v0.3 : compétences revues dans le dépôt d'instance). |

## Application Manuelle ou Automatisée

* **Via le script de déploiement (Recommandé)** :
  ```bash
  python scripts/deploy.py --config arcia.config.yaml
  ```
* **Application directe kubectl** :
  ```bash
  kubectl apply -f deploy/manifests/
  ```

Pour le détail des volumes, des variables d'environnement et des secrets requis, consulter le [Guide du Déploiement Universel](../../docs/guides/deploiement-universel.md).
