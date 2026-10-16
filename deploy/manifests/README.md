# Manifests Kubernetes — ArcIA (Namespace unifié `arcia`)

Ce dossier regroupe les manifests Kubernetes ordonnés pour déployer l'intégralité de la plateforme ArcIA sur un cluster K3s. Tous les services sont déployés dans le namespace unifié `arcia`.

## Ordre d'Application & Cartographie des Manifests

Les manifests sont préfixés de `00` à `10` pour garantir un déploiement déterministe respectant les dépendances :

| N° | Fichier | Composants Déployés | Description & Ports |
|:---:|---|---|---|
| **00** | [00-traefik-chart.yaml](00-traefik-chart.yaml) | `HelmChartConfig` (K3s Traefik) | Configuration de l'Ingress Controller Traefik embarqué dans K3s. |
| **01** | [01-cert-manager-issuer.yaml](01-cert-manager-issuer.yaml) | `ClusterIssuer` (Let's Encrypt) | Émission automatique des certificats TLS via HTTP-01. |
| **02** | [02-oauth2-proxy.yaml](02-oauth2-proxy.yaml) | `Deployment`, `Service` | Passerelle d'authentification SSO OpenID Connect (OIDC) avec Microsoft Entra ID (port 4180). |
| **03** | [03-presidio.yaml](03-presidio.yaml) | `Deployment`, `Service` | Passerelle DLP souveraine de caviardage des secrets, tokens et PII avant envoi aux LLMs cloud (port 8080). |
| **04** | [04-ingress.yaml](04-ingress.yaml) | `Ingress`, `Middleware` Traefik | Routage HTTPS centralisé (`/`, `/studio`, `/gateway`, `/api/teams/messages`) avec protection ForwardAuth SSO. |
| **05** | [05-litellm.yaml](05-litellm.yaml) | `Deployment`, `Service` | Passerelle d'inférence d'entreprise, équilibrage de charge, routage virtuel `auto` / `expert` et gestion des quotas (port 4000). |
| **06** | [06-hermes-agent.yaml](06-hermes-agent.yaml) | `Deployment`, `Service`, `PVC`, `ConfigMap` | Moteur d'agents Hermes, Studio Kanban (port 9119), Gateway Desktop (port 8642) et plugin Tokenmaxing. |
| **07** | [07-open-webui.yaml](07-open-webui.yaml) | `Deployment`, `Service`, `PVC` | Portail web conversationnel grand public, gestion des modèles, BYOK et base vectorielle RAG (port 8080). |
| **08** | [08-teams-bot.yaml](08-teams-bot.yaml) | `Deployment`, `Service` | Adaptateur bot Microsoft Teams pour les conversations privées (DM) et mentions en canal (port 3978). |
| **09** | [09-omniroute.yaml](09-omniroute.yaml) | `Deployment`, `Service`, `PVC` | Routeur multi-fournisseurs optionnel et portail LAN d'administration (ports 20128 & 20129). |
| **10** | [10-skills-sync-cronjob.yaml](10-skills-sync-cronjob.yaml) | `CronJob`, `ConfigMap` | Tâche planifiée de synchronisation et mise à jour du catalogue de compétences partagées dans `/var/data/arcia/shared-skills`. |

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
