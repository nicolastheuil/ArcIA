# Presidio DLP — Gouvernance & Confidentialité des Données (v0.3)

> **Statut : Implémenté (v0.3)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

Presidio DLP est la brique de sécurité de premier plan d'ArcIA. Elle garantit qu'aucune information personnelle identifiable (PII), clé d'API, mot de passe ou adresse IP d'entreprise n'est envoyée en clair vers des modèles d'IA hébergés dans le cloud.

---

## 1. Mécanisme de Fonctionnement & Mode Fail-Closed

Le microservice est développé en Python dans [services/presidio/app.py](../../services/presidio/app.py) et projeté dans le ConfigMap de [deploy/manifests/03-presidio.yaml](../../deploy/manifests/03-presidio.yaml) :

1. **Architecture Fail-Closed** : Si le service DLP est arrêté ou dégradé, LiteLLM bloque immédiatement les requêtes et lève une erreur explicite, interdisant tout contournement silencieux vers le cloud.
2. **Entités et Motifs Détectés** :
   - **Secrets techniques** : Clés d'API (`sk-`), tokens Bearer, tokens GitHub (`ghp_`), clés AWS (`AKIA`), mots de passe et chaînes de connexion (`password=`) → `[SECRET_REMOVED]`.
   - **Adresses IP** : IPv4 complète (`\b(?:\d{1,3}\.){3}\d{1,3}\b`) → `[ARCIA_IP_ADDRESS_n]`.
   - **Emails** : Professionnels et personnels → `[ARCIA_EMAIL_n]`.
   - **Téléphones** : Formats français et internationaux (`+33`, `06...`) → `[ARCIA_PHONE_n]`.
   - **Coordonnées Bancaires** : IBAN et numéros de cartes → `[ARCIA_IBAN_n]`, `[ARCIA_CREDIT_CARD_n]`.
   - **Analyse NLP Avancée** : Modèles spaCy `fr_core_news_sm` et `en_core_web_sm` via `NlpEngineProvider` pour les noms de personnes, organisations et lieux.

---

## 2. Endpoints Disponibles

Le service expose 4 routes REST sur le port interne `8080` :

* **`POST /anonymize`** : Endpoint standard consommé par LiteLLM Proxy dans son guardrail `pre_call`. Retourne le texte assaini.
* **`POST /analyze`** : Endpoint d'analyse retournant la liste structurée des entités détectées (offsets, types, scores de confiance).
* **`POST /sanitize`** : Endpoint direct de désensibilisation unifiée avec rapport d'entités.
* **`GET /healthz`** : Vérification de disponibilité immédiate, confirmant que le moteur NLP est chargé et opérationnel.

---

## 3. Qualification & Non-Régression

Le bouclier DLP est activement testé et qualifié par la suite de tests automatisés :
```bash
python -m unittest tests/test_dlp.py
```
Ce test valide en continu le caviardage effectif des adresses IP, secrets, emails, IBAN et numéros de téléphone.
