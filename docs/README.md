<p align="left">
  <a href="../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.7.0-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <img src="https://img.shields.io/badge/Documentation-Hub_Central-6BE7DD?style=flat-square&logoColor=050712" alt="Documentation Hub">
  <img src="https://img.shields.io/badge/Liens_Vérifiés-validate__docs.py-10B981?style=flat-square" alt="Liens Vérifiés">
</p>

# 📖 Centre de documentation — ArcIA

> **[🏠 Accueil ArcIA](../README.md)** › **Documentation**

Bienvenue dans la base documentaire officielle de la plateforme **ArcIA**.
Le [README principal](../README.md) offre une vue synthétique des macro-concepts, tandis que la spécification d’[Architecture](architecture.md) constitue la **source de vérité technique unique** du socle générique.

---

## 🏛️ 1. Architecture et cadrage

| Document | Portée & Contenu |
|---|---|
| 📐 **[Architecture Technique](architecture.md)** | Topologie Kubernetes complète, schémas détaillés des Pods/Services, routage hybride, stockage CSI et carte du code |
| 📊 **[État des Fonctionnalités](etat-des-fonctionnalites.md)** | Tableau de bord de traçabilité v0.7.0, matrice de qualification et durcissements de sécurité |
| 🤖 **[Charte d'Ingénierie (`AGENTS.md`)](../AGENTS.md)** | Règles d'architecture, séparation socle générique / dépôt d'instance et exigences de qualification |

---

## 📘 2. Guides fonctionnels et techniques

| Domaine | Besoin Opérationnel | Guide de Référence |
|---|---|---|
| **Socle** | Comprendre ArcIA, la séparation socle/instance et l'écosystème | [Plateforme ArcIA](guides/plateforme-arcia.md) |
| **Déploiement** | Centre de Pilotage Wizard (3 parcours dédiés), audit K8s et déploiement universel | [Déploiement Universel](guides/deploiement-universel.md) |
| **Infrastructure** | Cluster Kubernetes, stockage CSI, Traefik et Cert-Manager | [Infrastructure Kubernetes](guides/infrastructure-k3s.md) |
| **Portail Web** | Portail collaborateur Open-WebUI, SSO Entra ID et RAG documentaire | [Portail Open-WebUI & Entra ID](guides/portail-webui-entraid.md) |
| **Agents & Studio** | Moteur Hermes Agent, Studio Kanban (`:9119`), Gateway (`:8642`) et Pods dédiés Power Users | [Hermes Agent & Power Users](guides/hermes-agent.md) |
| **Routage IA** | Chaîne de routage hybride (`Simple` & `Agentic`) et cycle de vie d'un prompt | [Chaîne de Routage IA](guides/chaine-de-routage.md) |
| **Passerelle LLM** | Proxy LiteLLM, routage auto, fallbacks, ZDR et clés virtuelles PAT | [Inférence LiteLLM](guides/inference-litellm.md) |
| **Bouclier DLP** | Double barrière de caviardage automatique des secrets et PII (Presidio) | [Confidentialité Presidio DLP](guides/confidentialite-presidio.md) |
| **Microsoft 365** | Bot conversationnel Microsoft Teams (`conversation` et commande `/agent`) | [Intégration Microsoft Teams](guides/integration-teams.md) |
| **Sécurité** | Frontières réseau (`NetworkPolicy`), chiffrement et gouvernance RSSI | [Politique de Sécurité](guides/securite.md) |
| **Compétences** | Découvrir, synchroniser et maintenir le catalogue de compétences | [Catalogue de Skills](guides/skills.md) |
| **Sobriété** | Compression réversible CCR, RTK et économie de tokens | [Tokenmaxing & CCR](guides/tokenmaxing.md) |
| **Outillage Code** | Analyse AST locale Graphify, sobriété Ponytail et Public-APIs | [Outillage Builder & Sobriété](guides/outillage-builder.md) |
| **Connecteurs** | Ajouter une source vivante ou un serveur d'outils standardisé | [Connecteurs MCP](guides/connecteurs-mcp.md) |
| **Référentiel** | Vérifier les versions logicielles, images Docker et ports officiels | [Versions Officielles](guides/versions-officielles.md) |

---

<a id="exploitation"></a>
## 🛠️ 3. Runbooks d'exploitation (MCO et PRA)

| Procédure | Runbook de Référence |
|---|---|
| 🚀 **Installation guidée (Wizard 3 parcours), Power Users, mises à jour Zero-Downtime et recette** | [Quickstart Complet](runbooks/quickstart.md) |
| 🔍 **Maintenance quotidienne, diagnostic, logs et rotation des secrets** | [Exploitation & Maintenance](runbooks/exploitation.md) |
| 🔄 **Sauvegarde chiffrée (`AES-256-GCM`), restauration et reconstruction sur cluster neuf** | [Sauvegarde & Reconstruction](runbooks/sauvegarde-reconstruction.md) |

---

## ✅ 4. Gouvernance documentaire et preuves

> [!NOTE]
> **Séparation Socle Générique / Dépôt d'Instance :**
> Le dépôt `ArcIA` porte uniquement le socle générique. Les secrets, domaines et états de reprise propres à une organisation appartiennent à son dépôt d'instance privé chiffré.
>
> **Niveaux de qualification :**
> * **Proposé** : cible décidée en conception.
> * **Codé** : artefact présent et testé unitairement dans Git.
> * **Déployé** : appliqué sur une cible désignée.
> * **Vérifié** : scénario exécuté de bout en bout avec preuve consignée.


## Espaces privés et fichiers depuis le portail

Le [guide des espaces utilisateurs WebUI](guides/espaces-utilisateurs-webui.md) explique le routage par compte, la réutilisation des pods Power Users, les droits de téléchargement et la recette.

## Conception de la prochaine plateforme

Le [dossier ArcIA v0.7.0](v0.7/README.md) réunit l'audit critique, la conception multi-tenant, les flux, le plan de réalisation par lots et les preuves de cette étude. Son statut est proposé ; il ne remplace pas la documentation du socle actuellement livré.
