# Presidio DLP — Gouvernance & Confidentialité des Données

Presidio DLP est la brique de sécurité de premier plan d'ArcIA. Elle garantit qu'aucune information personnelle identifiable (PII), clé d'API, mot de passe ou secret d'entreprise n'est envoyée en clair vers des modèles d'IA hébergés dans le cloud.

---

## 1. Mécanisme de Fonctionnement

Le microservice est développé en Python (FastAPI + Microsoft Presidio Analyzer & Anonymizer) dans [services/presidio/app.py](../../services/presidio/app.py) :

1. **Interception du Texte** : Le texte soumis est analysé par des modèles NLP et des reconnaisseurs par expressions régulières (Regex).
2. **Entités Détectées par Défaut** :
   - Adresses email (`EMAIL_ADDRESS`)
   - Numéros de téléphone (`PHONE_NUMBER`)
   - Numéros de carte bancaire (`CREDIT_CARD`)
   - Adresses IP (`IP_ADDRESS`)
3. **Reconnaisseurs Spécifiques Entreprise** :
   - Mots de passe et jetons secrets (`PASSWORD_PATTERN`, `API_KEY_PATTERN`)
   - Jetons bearer, hashs et certificats
4. **Anonymisation / Caviardage** :
   - Les entités détectées sont substituées par des placeholders identifiés : `[ARCIA_EMAIL_1]`, `[ARCIA_PHONE_1]`, `[SECRET_REMOVED]`.

---

## 2. Déploiement Kubernetes & Endpoints

Déployé via [deploy/manifests/03-presidio.yaml](../../deploy/manifests/03-presidio.yaml) :
- **Service** : `presidio-dlp.arcia.svc:8080`
- **Route `/sanitize`** :
  - **Méthode** : `POST`
  - **Payload** : `{"text": "Mon mot de passe est SecretPass123 et mon email collaborateur@example.org"}`
  - **Réponse** :
    ```json
    {
      "text": "Mon mot de passe est [SECRET_REMOVED] et mon email [ARCIA_EMAIL_1]",
      "sanitized_text": "...",
      "original_length": 68,
      "sanitized_length": 65,
      "entities_detected": ["EMAIL_ADDRESS", "PASSWORD"]
    }
    ```
- **Route `/health`** : Vérification de disponibilité immédiate.
