<p align="left">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.7.0-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <a href="../README.md"><img src="https://img.shields.io/badge/📖_Docs-Hub_Central-0C2762?style=flat-square" alt="Documentation"></a>
  <img src="https://img.shields.io/badge/Guides-Références_techniques-6BE7DD?style=flat-square&logoColor=050712" alt="Guides techniques">
</p>

# 📘 Guides techniques et fonctionnels — ArcIA

> **[🏠 Accueil ArcIA](../../README.md)** › **[📖 Documentation](../README.md)** › **Guides Techniques**

Ce répertoire rassemble les guides thématiques qui détaillent chaque brique fonctionnelle, les flux de sécurité et les composants d'infrastructure de la plateforme **ArcIA v0.7.0**.

---

## 🧭 Index thématique des guides

### 🏛️ 1. Architecture et principes fondateurs
| Guide | Résumé |
|---|---|
| **[plateforme-arcia.md](plateforme-arcia.md)** | Vision globale d'ArcIA, séparation stricte entre le socle générique et le dépôt d'instance privé chiffré. |
| **[securite.md](securite.md)** | Périmètre de sécurité Defense-in-Depth, gouvernance *fail-closed* Presidio DLP, blocage du BYOK sauvage et clés PAT. |
| **[versions-officielles.md](versions-officielles.md)** | Matrice des images Docker, versions logicielles de référence et cartographie des ports internes. |

### 🤖 2. Moteur d'agents Hermes et outillage cognitif
| Guide | Résumé |
|---|---|
| **[hermes-agent.md](hermes-agent.md)** | Moteur d'exécution Hermes Agent, Studio Kanban (`:9119`), Gateway Desktop (`:8642`) et Pods dédiés Power Users (`.\scripts\Spawn-PowerUser.ps1`). |
| **[skills.md](skills.md)** | Catalogue des compétences partagées (`/var/data/arcia/shared-skills`), structure `SKILL.md` et synchronisation à chaud. |
| **[tokenmaxing.md](tokenmaxing.md)** | Compression réversible CCR (cache mémoire SHA-256), compaction RTK `git log` et économie de fenêtre de contexte. |
| **[outillage-builder.md](outillage-builder.md)** | Compétences natives intégrées d'office : **Graphify** (GraphRAG AST local), **Ponytail** (sobriété YAGNI) et **Public-APIs**. |
| **[connecteurs-mcp.md](connecteurs-mcp.md)** | Intégration du protocole *Model Context Protocol (MCP)* pour raccorder des outils métiers et bases documentaires. |

### 🧠 3. Inférence LLM, routage hybride et confidentialité DLP
| Guide | Résumé |
|---|---|
| **[chaine-de-routage.md](chaine-de-routage.md)** | Routage hybride (`Simple` & `Agentic`), catalogue administré des modèles Simple et Agentic et diagrammes de séquence complets. |
| **[inference-litellm.md](inference-litellm.md)** | Configuration du proxy LiteLLM (`:4000`), *Zero Data Retention* (`zdr: true`), fallback et base comptable PostgreSQL 18.6. |
| **[confidentialite-presidio.md](confidentialite-presidio.md)** | Double barrière d'anonymisation DLP Microsoft Presidio (Hermes amont + LiteLLM aval) en mode *fail-closed*. |

### 💬 4. Interfaces collaborateurs et canaux d'équipe
| Guide | Résumé |
|---|---|
| **[portail-webui-entraid.md](portail-webui-entraid.md)** | Portail conversationnel Open-WebUI, authentification SSO Microsoft Entra ID (OIDC) et RAG documentaire d'entreprise. |
| **[integration-teams.md](integration-teams.md)** | Adaptateur Bot Framework Microsoft Teams (`conversation` en réponse directe et commande `/agent` vers Hermes). |

### ☸️ 5. Infrastructure Kubernetes et déploiement
| Guide | Résumé |
|---|---|
| **[deploiement-universel.md](deploiement-universel.md)** | Centre de pilotage Wizard (`.\wizard.ps1`), séquence de mise à jour Zero-Downtime et moteur de déploiement universel. |
| **[infrastructure-k3s.md](infrastructure-k3s.md)** | Déploiement sur tout cluster Kubernetes (K3s, EKS, AKS, GKE, VMware), stockage CSI persistant et Ingress TLS. |


## Espaces privés et fichiers depuis le portail

Le [guide des espaces utilisateurs WebUI](espaces-utilisateurs-webui.md) explique le routage par compte, la réutilisation des pods Power Users, les droits de téléchargement et la recette.
