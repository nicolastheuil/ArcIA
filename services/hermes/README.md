<p align="left">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.5.1-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <a href="../README.md"><img src="https://img.shields.io/badge/🧩_Services-Microservices-0C2762?style=flat-square" alt="Services"></a>
  <img src="https://img.shields.io/badge/Plugin-DLP_+_CCR_+_RTK-6BE7DD?style=flat-square&logoColor=050712" alt="Plugin Hermes">
</p>

# 🤖 Service Hermes Agent et plugin de gouvernance / tokenmaxing — ArcIA

> **[🏠 Accueil ArcIA](../../README.md)** › **[🧩 Microservices](../README.md)** › **Hermes Agent (`services/hermes/`)**

Ce dossier contient le plugin natif de gouvernance DLP amont et de sobriété Tokenmaxing ainsi que la définition de conteneur pour le moteur d'agents autonomes **Hermes Agent**.

---

## 📦 Composants du dossier

| Fichier | Rôle & Responsabilités |
|---|---|
| **[plugin.py](plugin.py)** | Plugin natif ArcIA (`arcia-governance-tokenmaxing` v0.5.1) exposant le point d'entrée officiel `register(ctx)`. |
| **[Dockerfile](Dockerfile)** | Image basée sur `nousresearch/hermes-agent:v0.2.0` intégrant `/opt/hermes/plugins/arcia_governance.py`. |

### 🛡️ Les 3 mécanismes actifs dans `plugin.py`
1. **Barrière 1 DLP *Fail-Closed* (`sanitize_via_presidio`)** : Assainit tous les prompts et sorties d'outils via `http://presidio-dlp.arcia.svc:8080/sanitize` *avant* écriture dans `state.db` et *avant* envoi au LLM. Bloque immédiatement la requête si Presidio est injoignable.
2. **Compression Réversible CCR (*Compress-Cache-Retrieve*)** : Compresse automatiquement les résultats JSON volumineux (> 8 Ko) dans `transform_tool_result`, stocke l'original assaini dans un cache RAM privé indexé par hash SHA-256 (`_CCR_CACHE`, TTL 5 min, max 32 entrées / 4 Mo) et expose les outils `arcia_compress_json_file` et `arcia_restore_tool_result`.
3. **Compaction RTK (`transform_command`)** : Réécrit et compacte les commandes `git log` verbeuses pour économiser la fenêtre de contexte.

---

## ☸️ Synchronisation et déploiement Kubernetes

> [!NOTE]
> Lors du déploiement ou d'une mise à jour Zero-Downtime, [`scripts/deploy.py`](../../scripts/deploy.py) synchronise automatiquement `plugin.py` dans le ConfigMap `hermes-governance-plugin`, monté sous `/opt/hermes/plugins/arcia_governance.py` à la fois dans le Pod Hermes partagé ([`deploy/manifests/06-hermes-agent.yaml`](../../deploy/manifests/06-hermes-agent.yaml)) et dans les Pods dédiés des Power Users ([`deploy/manifests/templates/hermes-poweruser.template.yaml`](../../deploy/manifests/templates/hermes-poweruser.template.yaml)).

### 🔗 Références associées
* 📘 [Guide Hermes Agent & Mode Power User](../../docs/guides/hermes-agent.md)
* 🗜️ [Guide Tokenmaxing & CCR v0.5.1](../../docs/guides/tokenmaxing.md)
