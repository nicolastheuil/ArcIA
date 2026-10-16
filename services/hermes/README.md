# Service Hermes Agent & Plugin Tokenmaxing — ArcIA

Ce dossier contient les personnalisations, scripts d'extension et définitions de conteneur pour le moteur d'agents **Hermes Agent**.

## Contenu

* **[plugin.py](plugin.py)** : Plugin natif ArcIA *Tokenmaxing*. Intercepte les sorties d'outils (`terminal`, `bash`, `read_file`, `fetch_url`) pour :
  * Compresser les sorties shell verbeuses (ex. `git log` tronqué intelligemment).
  * Résumer les charges JSON volumineuses (> 8 Ko) pour économiser la fenêtre de contexte.
  * Exploiter le binaire de compression `rtk` s'il est présent dans l'environnement.
* **[Dockerfile](Dockerfile)** : Image Docker basée sur l'image officielle Hermes, intégrant les prérequis système, les outils de diagnostic et le montage des plugins d'entreprise.

## Fonctionnement avec le Cluster

Dans le cluster K3s, le code de `plugin.py` est projeté sous forme de `ConfigMap` (`hermes-plugin-code`) et monté dans le conteneur sous `/opt/hermes/plugins/arcia_tokenmaxing.py` (défini dans [deploy/manifests/06-hermes-agent.yaml](../../deploy/manifests/06-hermes-agent.yaml)).

Pour approfondir le fonctionnement du moteur et du mode power user :
* [Guide Hermes Agent](../../docs/guides/hermes-agent.md)
* [Guide Tokenmaxing](../../docs/guides/tokenmaxing.md)
