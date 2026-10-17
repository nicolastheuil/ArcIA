# Service Hermes Agent & Plugin de Gouvernance / Tokenmaxing — ArcIA

Ce dossier contient le plugin natif de gouvernance DLP et de sobriété Tokenmaxing ainsi que la définition de conteneur pour le moteur d'agents **Hermes Agent**.

## Contenu

* **[plugin.py](plugin.py)** : Plugin natif ArcIA (`arcia-governance-tokenmaxing` v0.4) exposant le point d'entrée officiel `register(ctx)` :
  * **Barrière 1 DLP Fail-Closed (`sanitize_via_presidio`)** : Assainit tous les prompts et sorties d'outils via `http://presidio-dlp.arcia.svc:8080/sanitize` avant écriture dans `state.db` et avant envoi au LLM. Bloque la requête si Presidio est injoignable.
  * **Compression Réversible CCR (`Compress-Cache-Retrieve`)** : Compresse automatiquement les résultats JSON volumineux (> 8 Ko) dans `transform_tool_result`, stocke l'original assaini dans un cache RAM privé indexé par hash SHA-256 (`_CCR_CACHE`, TTL 5 min, max 32 entrées / 4 Mo) et expose les outils `arcia_compress_json_file` et `arcia_restore_tool_result`.
  * **Compaction RTK (`transform_command`)** : Réécrit et compacte les commandes `git log` simples.
* **[Dockerfile](Dockerfile)** : Image Docker basée sur `nousresearch/hermes-agent:v0.2.0`, intégrant le plugin sous `/opt/hermes/plugins/arcia_governance.py`.

## Fonctionnement avec le Cluster

Dans le cluster K3s, le fichier `plugin.py` est synchronisé par `scripts/deploy.py` dans le ConfigMap `hermes-governance-plugin` et monté dans `/opt/hermes/plugins/arcia_governance.py` au sein de [deploy/manifests/06-hermes-agent.yaml](../../deploy/manifests/06-hermes-agent.yaml) et des pods Power Users ([deploy/manifests/templates/hermes-poweruser.template.yaml](../../deploy/manifests/templates/hermes-poweruser.template.yaml)).

Pour approfondir le fonctionnement du moteur et du mode Power User :
* [Guide Hermes Agent](../../docs/guides/hermes-agent.md)
* [Guide Tokenmaxing v0.4](../../docs/guides/tokenmaxing.md)
