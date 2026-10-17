# Service Presidio DLP Sanitizer — ArcIA

Ce dossier contient l'implémentation de référence de la passerelle de détection et de caviardage de données sensibles **Presidio DLP**, développée avec FastAPI et Microsoft Presidio (`fr_core_news_sm` + `en_core_web_sm`).

## Contenu

* **[app.py](app.py)** : Application FastAPI constituant la source unique du microservice (synchronisée dans le ConfigMap `presidio-code` par `scripts/deploy.py`) :
  * `POST /sanitize` (et alias `POST /v1/sanitize`) : Analyse le texte soumis, identifie les secrets techniques (`sk-...`, `ghp_...`, `AKIA...`, tokens Bearer, clés PEM, mots de passe), adresses IPv4 et données personnelles (emails, téléphones, IBAN, cartes bancaires, entités NLP), et renvoie le texte caviardé (`[SECRET_REMOVED]`, `[ARCIA_<TYPE>_n]`).
  * `POST /analyze` : Retourne la liste structurée des entités détectées (offsets, types, scores) pour le guardrail LiteLLM.
  * `POST /anonymize` : Anonymise un texte à partir des résultats d'analyse pour le guardrail `pre_call` LiteLLM.
  * `GET /healthz` (et alias `GET /health`) : Contrôle de disponibilité utilisé par les probes Kubernetes.
* **[Dockerfile](Dockerfile)** : Image Docker autonome incluant Python 3.11, Presidio Analyzer/Anonymizer et les modèles spaCy français et anglais.

## Intégration Double Barrière dans la Chaîne d'Inférence

1. **Barrière 1 (Amont — Hermes Agent)** : [services/hermes/plugin.py](../hermes/plugin.py) appelle `POST /sanitize` en mode *fail-closed* avant toute sauvegarde SQLite et tout appel LLM.
2. **Barrière 2 (Aval — LiteLLM Proxy)** : [deploy/manifests/05-litellm.yaml](../../deploy/manifests/05-litellm.yaml) exécute le guardrail `presidio` (`pre_call`, `default_on: true`) via `/analyze` et `/anonymize`.

Pour plus d'informations :
* [Guide Confidentialité Presidio DLP](../../docs/guides/confidentialite-presidio.md)
* [Manifeste Kubernetes 03-presidio.yaml](../../deploy/manifests/03-presidio.yaml)
