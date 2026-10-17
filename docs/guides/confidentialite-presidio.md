# Presidio DLP — Gouvernance & Double Barrière de Confidentialité (v0.4)

> **Statut : Implémenté (v0.4)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

Presidio DLP est la brique de sécurité de premier plan d'ArcIA. Elle garantit qu'aucune information personnelle identifiable (PII), clé d'API, mot de passe ou adresse IP d'entreprise n'est persistée en clair ni envoyée vers des modèles d'IA hébergés dans le cloud.

---

## 1. Architecture Double Barrière & Mode Fail-Closed

Le microservice est développé en Python dans [services/presidio/app.py](../../services/presidio/app.py) (source unique synchronisée dans le ConfigMap `presidio-code` par `scripts/deploy.py` et déployée via [deploy/manifests/03-presidio.yaml](../../deploy/manifests/03-presidio.yaml)).

Dans ArcIA v0.4, le caviardage DLP opère selon une **double barrière en mode Fail-Closed** :
1. **Barrière 1 (Amont — Hermes Agent)** : Le plugin de gouvernance ([services/hermes/plugin.py](../../services/hermes/plugin.py)) intercepte les prompts et les sorties d'outils et appelle `POST http://presidio-dlp.arcia.svc:8080/sanitize` *avant* toute sauvegarde dans `state.db` (SQLite) et *avant* tout appel LLM.
2. **Barrière 2 (Aval — LiteLLM Proxy)** : Le guardrail natif `presidio` (`mode: pre_call`, `default_on: true` dans [deploy/manifests/05-litellm.yaml](../../deploy/manifests/05-litellm.yaml)) appelle `POST /analyze` et `POST /anonymize` sur 100 % des flux traversant la passerelle (`simple/*`, `agentic/*`, Teams, API `/v1`).
3. **Mode Fail-Closed Strict** : Si le service DLP est arrêté ou dégradé, Hermes et LiteLLM bloquent immédiatement la requête et lèvent une erreur explicite (`RuntimeError` / HTTP 503), interdisant tout contournement silencieux vers le cloud.

---

## 2. Entités et Motifs Détectés

- **Secrets techniques** : Clés d'API (`sk-`), tokens Bearer, tokens GitHub (`ghp_`), clés AWS (`AKIA`), clés privées PEM, mots de passe et chaînes de connexion (`password=`) → `[SECRET_REMOVED]`.
- **Adresses IP** : IPv4 complète (`\b(?:\d{1,3}\.){3}\d{1,3}\b`) → `[ARCIA_IP_ADDRESS_n]`.
- **Emails** : Professionnels et personnels → `[ARCIA_EMAIL_n]`.
- **Téléphones** : Formats français et internationaux (`+33`, `06...`) → `[ARCIA_PHONE_n]`.
- **Coordonnées Bancaires** : IBAN et numéros de cartes → `[ARCIA_IBAN_n]`, `[ARCIA_CREDIT_CARD_n]`.
- **Analyse NLP Avancée** : Modèles spaCy `fr_core_news_sm` et `en_core_web_sm` via `NlpEngineProvider` pour les noms de personnes, organisations et lieux.

---

## 3. Endpoints Disponibles

Le service expose 4 routes REST sur le port interne `8080` :

* **`POST /sanitize`** (et alias `/v1/sanitize`) : Endpoint direct de désensibilisation unifiée avec rapport d'entités, consommé par la Barrière 1 (plugin Hermes) et les scripts de validation.
* **`POST /analyze`** : Endpoint d'analyse retournant la liste structurée des entités détectées (offsets, types, scores de confiance) pour le guardrail LiteLLM.
* **`POST /anonymize`** : Endpoint d'anonymisation standard consommé par la Barrière 2 (guardrail `pre_call` LiteLLM).
* **`GET /healthz`** (et alias `/health`) : Vérification de disponibilité immédiate, confirmant que le moteur NLP est chargé et opérationnel.

---

## 4. Qualification & Non-Régression

Le bouclier DLP est activement testé et qualifié par la suite de tests automatisés :
```bash
python -m unittest tests/test_dlp.py
```
Ce test valide en continu le caviardage effectif des adresses IP, secrets, emails, IBAN et numéros de téléphone ainsi que le comportement *fail-closed* du plugin Hermes.
