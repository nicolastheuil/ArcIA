# Service Presidio DLP Sanitizer — ArcIA

Ce dossier contient l'implémentation de la passerelle de détection et de caviardage de données sensibles **Presidio DLP**, développée avec FastAPI.

## Contenu

* **[app.py](app.py)** : Application FastAPI exposant les endpoints de nettoyage et de détection :
  * `POST /v1/sanitize` : Analyse le texte soumis, identifie les secrets (mots de passe, jetons GitHub, clés OpenAI/OpenRouter `sk-...`, tokens Bearer) et les données personnelles (emails, adresses IP, IBAN), et renvoie le texte caviardé avec le masque `[CONFIDENTIAL_<TYPE>]`.
  * `GET /health` : Contrôle de disponibilité utilisé par les probes Kubernetes.

## Intégration dans la Chaîne d'Inférence

Dans l'architecture ArcIA, le proxy d'inférence LiteLLM est configuré avec un hook pré-appel qui achemine systématiquement les prompts utilisateurs vers ce service avant toute transmission vers un fournisseur LLM externe.

Pour plus d'informations :
* [Guide Confidentialité Presidio DLP](../../docs/guides/confidentialite-presidio.md)
* [Manifeste Kubernetes 03-presidio.yaml](../../deploy/manifests/03-presidio.yaml)
