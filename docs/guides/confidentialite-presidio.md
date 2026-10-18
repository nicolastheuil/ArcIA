# Presidio DLP — gouvernance et double barrière de confidentialité (v0.5.2)

> **Statut : Implémenté (v0.5.2)** · [Consulter l'état des fonctionnalités](../etat-des-fonctionnalites.md)

Presidio DLP est la brique de sécurité de premier plan d'ArcIA. Elle garantit qu'aucune information personnelle identifiable (PII), clé d'API, mot de passe, adresse IP ou identifiant d'infrastructure d'entreprise n'est persistée en clair ni transmise vers des modèles d'IA hébergés dans le cloud.

---

## 1. Architecture on-premise durcie en 4 couches

Le microservice est développé en Python dans [services/presidio/app.py](../../services/presidio/app.py) (source unique synchronisée dans le ConfigMap `presidio-code` par `scripts/deploy.py` et déployée via [deploy/manifests/03-presidio.yaml](../../deploy/manifests/03-presidio.yaml)).

Il fonctionne à 100 % sur CPU sans nécessiter de GPU et applique une stratégie de confidentialité structurée en **4 couches complémentaires** :

```mermaid
flowchart TD
    User["Prompt Agent / Sortie d'Outil"] --> C1["Couche 1 : Filtre Déterministe Pré-NLP"]
    C1 -- "Dump Secret / Kubeconfig" --> Block["Rejet Immédiat Fail-Closed HTTP 422"]
    C1 -- "Secrets en ligne" --> Strip["Caviardage Non-Réversible [SECRET_REMOVED]"]
    C1 -- "Infra / CIDR / MAC / FQDN" --> Vault["Vault Éphémère In-Memory"]
    Strip --> C2["Couche 2 : NER & Deny-Lists"]
    Vault --> C2
    C2 -- "FR_NIR, FR_SIRET, Deny-List" --> C3["Couche 3 : Pseudonymisation Cohérente [TYPE_01]"]
    C3 --> LiteLLM["Couche 4 : LiteLLM Proxy (Guardrail + ZDR Forcé)"]
    LiteLLM --> Cloud["OpenRouter ZDR (data_collection: deny)"]
    Cloud --> Response["Réponse LLM avec Jetons"]
    Response --> Deanon["Dé-anonymisation / Ré-hydratation (/deanonymize)"]
    Deanon --> Agent["Restitution Claire à l'Agent / Utilisateur"]
```

### Couche 1 : filtre déterministe pré-NLP (secrets, infra et formats opaques)
- **Politique `FAIL-CLOSED` (Blocage strict HTTP 422)** : Si un bloc de type clé privée PEM/SSH brute (`-----BEGIN RSA PRIVATE KEY-----`), dump d'extraction `kubeconfig` ou extrait de hash `/etc/shadow` est détecté, la requête est immédiatement **rejetée** avec le statut HTTP 422 (`FAIL_CLOSED_SECRET_REJECTED`) avant tout appel au réseau externe, pour exécution ou diagnostic local.
- **Caviardage irréversible des secrets en ligne** : Clés d'API (`sk-`), tokens Bearer, tokens GitHub (`ghp_`), clés AWS (`AKIA`), mots de passe et chaînes de connexion (`postgres://...`) sont remplacés par `[SECRET_REMOVED]`. Ces secrets ne sont **jamais** enregistrés dans le Vault de dé-anonymisation.
- **Détection d'infrastructure réseau** :
  - Adresses IPv4 avec validation d'octets et distinction RFC1918 (privées) vs publiques → `[IPV4_01]`.
  - Sous-réseaux CIDR (`10.0.0.0/16`) → `[CIDR_01]`.
  - Adresses MAC (`00:1A:2B:3C:4D:5E`) → `[MAC_01]`.
  - FQDN internes (`.local`, `.lan`, `.internal`, `.corp`, `.cluster.local`) → `[HOST_01]`.
  - Chemins système critiques (`/etc/shadow`, `/root/.ssh/id_rsa`) → `[PATH_01]`.

### Couche 2 : NER multilingue, PII françaises et deny-lists d'instance
- **Entités PII Françaises Déterministes** :
  - **`FR_NIR`** : Numéro de sécurité sociale français (13 ou 15 chiffres avec clé de contrôle modulo 97) → `[NIR_01]`.
  - **`FR_SIRET`** : Numéro d'établissement à 14 chiffres avec validation de l'algorithme de Luhn → `[SIRET_01]`.
- **Deny-Lists Dynamiques d'Instance** :
  - Schéma standardisé : [schemas/arcia-deny-list.schema.json](../../schemas/arcia-deny-list.schema.json).
  - Fixture d'exemple : [examples/deny-list.synthetic.json](../../examples/deny-list.synthetic.json).
  - Chargement dynamique depuis `/etc/arcia/deny-list.json` ou la variable d'environnement `ARCIA_DENY_LIST` (permettant à chaque organisation d'injecter ses noms de clients ou de projets confidentiels sans jamais les coder en dur dans le dépôt générique `arcia-harness`).
- **Moteur Sémantique Presidio / GLiNER** :
  - Modèles spaCy CPU `fr_core_news_sm` et `en_core_web_sm` pour la détection contextuelle des personnes (`[PERSON_01]`).
  - Architecture prête pour l'intégration de recognizers GLiNER quantifiés en ONNX Runtime.

### Couche 3 : pseudonymisation cohérente et réversible (vault éphémère)
- **Topologie Préservée** : Chaque entité unique reçoit un jeton canonique typé et incrémental (`[IPV4_01]`, `[IPV4_02]`, `[HOST_01]`). Si une même valeur apparaît plusieurs fois au cours d'un tour ou d'une session, elle reçoit systématiquement le **même jeton**, garantissant au LLM une cohérence logique parfaite pour le raisonnement.
- **Vault Éphémère en Mémoire Vive** :
  - La table de correspondance inverse (`[IPV4_01]` ↔ `10.24.12.5`) est conservée **exclusivement en mémoire vive (RAM)** avec un TTL de 1800 secondes (30 minutes) et un plafond de 5000 sessions actives.
  - **Zéro écriture disque, zéro journalisation en clair dans les logs applicatifs.**
- **Ré-hydratation & Buffer Streaming** :
  - L'endpoint `POST /deanonymize` restitue les valeurs réelles dans les réponses de l'agent.
  - La classe `DeanonymizingStreamBuffer` prend en charge la ré-hydratation glissante sur les flux Server-Sent Events (SSE) sans rupture de syntaxe des jetons découpés entre deux chunks.

### Couche 4 : verrouillage ZDR côté serveur (LiteLLM Proxy / OpenRouter)
Dans [deploy/manifests/05-litellm.yaml](../../deploy/manifests/05-litellm.yaml) et [deploy/litellm-lab.yaml](../../deploy/litellm-lab.yaml), la configuration LiteLLM Proxy force côté serveur sur chaque modèle OpenRouter :
```yaml
extra_body:
  provider:
    data_collection: "deny"
    zdr: true
    allow_fallbacks: false
```
Ce paramétrage est non-surchargeable par les requêtes entrantes, garantissant contractuellement la politique Zero Data Retention (ZDR) et interdisant tout fallback silencieux vers des fournisseurs non certifiés.

---

## 2. Endpoints disponibles

Le service expose ses routes REST sur le port interne `8080` :

| Méthode | Route | Rôle & Usage |
| :--- | :--- | :--- |
| `POST` | `/sanitize` | Désensibilisation universelle avec session Vault éphémère (utilisé par Hermes Barrière 1). |
| `POST` | `/deanonymize` | Ré-hydratation inverse des réponses LLM à partir du Vault éphémère de session. |
| `POST` | `/anonymize` | Endpoint compatible guardrail LiteLLM `pre_call` (Barrière 2). |
| `POST` | `/analyze` | Rapport structuré des entités détectées pour guardrails d'audit. |
| `GET` | `/healthz` | Bilan de santé : état de l'analyzer NLP, nombre de sessions actives dans le Vault, état Deny-List. |

---

## 3. Qualification et non-régression

Le bouclier DLP durci est validé en continu par la suite de tests automatisés :
```bash
python -m unittest tests/test_dlp.py
```
Cette suite couvre :
1. Le rejet strict `HTTP 422 Fail-Closed` des clés privées PEM/SSH et extraits `kubeconfig`.
2. La détection déterministe d'infrastructure (CIDR, MAC, FQDN internes, chemins sensibles).
3. La validation des PII françaises (`FR_NIR` avec clé modulo 97, `FR_SIRET` avec Luhn).
4. Le chargement dynamique des Deny-Lists d'instance sans fuite dans le harness générique.
5. L'aller-retour réversible complet (`sanitize` → `deanonymize`) et le buffer streaming.
6. Le verrouillage non-surchargeable des paramètres OpenRouter ZDR (`data_collection: deny`, `zdr: true`, `allow_fallbacks: false`).
