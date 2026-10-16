# 🔀 Chaîne de Routage IA & Cycle de Vie d'une Requête dans ArcIA

Ce guide détaille l'intégralité du parcours d'une requête d'inférence au sein de la plateforme **ArcIA v0.2**, depuis la saisie du collaborateur jusqu'à la réponse générée par les modèles de fondation, en passant par le bouclier de confidentialité et les mécanismes d'auto-sélection.

---

## 1. Vue d'Ensemble : Le Voyage d'un Prompt en 30 Secondes

Dans une entreprise, l'accès aux modèles d'IA générative doit répondre à **trois impératifs simultanés** :
1. **Simplicité & Clarté** pour les collaborateurs : Ne pas leur imposer de choisir parmi des dizaines de modèles bruts techniques ou non configurés.
2. **Confidentialité & Souveraineté Absolues** : Empêcher rigoureusement la moindre fuite de secrets d'entreprise, mots de passe, tokens ou données personnelles (PII) vers des nuages tiers.
3. **Autonomie Budgétaire & BYOK (Bring Your Own Key)** : Permettre aux équipes avancées (R&D, ingénieurs) d'utiliser leurs propres clés ou abonnements personnels sans compromettre le budget de l'organisation.

Pour résoudre ce triptyque, ArcIA organise son routage selon une **architecture en couches étanches** :

```mermaid
flowchart TD
    subgraph Clients ["👥 Points d'Entrée Utilisateurs"]
        UserWeb["Collaborateur Web (Open-WebUI)"]
        UserTeams["Collaborateur Teams (Teams Bot)"]
        PowerUser["Power User / Développeur (BYOK)"]
        HermesRunner["Hermes Agent (Missions Autonomes)"]
    end

    subgraph SecurityGate ["🛡️ Périmètre Souverain ArcIA (Cluster K3s)"]
        WebUIGate["Open-WebUI (:8080)<br/>• Catalogue managé épuré<br/>• Isolation BYOK"]
        LiteLLMGate["LiteLLM Proxy (:4000)<br/>• Pivot central souverain<br/>• Modèles virtuels managés<br/>• Masquage des clés d'instance"]
        PresidioGate["Presidio DLP (:8080)<br/>• Guardrail Pre-Call obligatoire<br/>• Caviardage PII & Secrets"]
        OmniRouteGate["OmniRoute v3.8.51 (:20128)<br/>• Routeur LAN optionnel<br/>• Combos auto/smart, auto/coding"]
    end

    subgraph CloudInference ["☁️ Fournisseurs de Modèles Externes"]
        OpenRouterHub["OpenRouter d'Entreprise<br/>(Claude 3.5 Sonnet, GPT-4o, DeepSeek)"]
        PersonalKeys["Fournisseurs Cloud Directs<br/>(Clés privées OpenAI, Anthropic, Gemini)"]
    end

    UserWeb -->|Modèles ArcIA-Agentic| WebUIGate
    UserTeams -->|Requête Bot| LiteLLMGate
    PowerUser -->|Clé Privée Déclarée| WebUIGate
    HermesRunner -->|Inférence Agentique| LiteLLMGate

    WebUIGate -->|Inférence Managée d'Entreprise| LiteLLMGate
    WebUIGate -->|Connexion Directe Isolée BYOK| PersonalKeys

    LiteLLMGate <-->|Interception Pré-Vol Obligatoire| PresidioGate
    LiteLLMGate -->|Routage Direct Managé| OpenRouterHub
    LiteLLMGate -.->|Upstream Optionnel Combos| OmniRouteGate
    OmniRouteGate -->|Exécution Combos & Failover| OpenRouterHub
```

---

## 2. Le Catalogue de Modèles Présenté aux Utilisateurs

Pour éviter la dispersion et les erreurs d'authentification, le menu déroulant des modèles d'ArcIA dans [Open-WebUI](../../deploy/manifests/07-open-webui.yaml) est strictement articulé autour de **deux modèles managés souverains**, complétés par le canal personnel **BYOK** :

| Modèle Affiché | Public Cible | Rôle & Intelligence de Routage | Traitement DLP | Source de Financement |
|---|---|---|---|---|
| **`ArcIA-Agentic (auto)`** *(Par défaut)* | Tous les collaborateurs (usage quotidien, synthèses, rédaction) | **Auto-sélection dynamique** : Évalue la complexité du prompt et choisit en temps réel le meilleur modèle disponible (latence, coût, pertinence) avec bascule automatique sans coupure. | ✅ Caviardage Presidio systématique | Compte central d'organisation |
| **`ArcIA-Agentic (expert)`** | Collaborateurs experts (architecture, code lourd, audits) | **Raisonnement frontière haute fidélité** : Modèle de pointe (ex: Claude 3.5 Sonnet / o1 / DeepSeek Reasoner). Le collaborateur peut **orienter la réflexion ou forcer un moteur précis directement dans son prompt**. | ✅ Caviardage Presidio systématique | Compte central d'organisation |
| **BYOK (Modèles Personnels)** | Développeurs, data scientists, power users | **Inférence directe autonome** : Connexions directes déclarées par le collaborateur dans ses paramètres personnels (**Paramètres > Connexions**). | 🔒 Clé privée isolée (navigateur / session) | Carte bancaire ou quota personnel de l'utilisateur |

> [!NOTE]
> **Pourquoi avoir supprimé les modèles bruts (`gpt-4o`, `claude-3.5-sonnet`, `deepseek-chat`) ?**
> Auparavant, ces entrées nécessitaient des clés d'API individuelles pour chaque éditeur, ce qui entraînait des erreurs si l'organisation n'avait pas souscrit à chacun d'entre eux. En unifiant le catalogue managé sur `ArcIA-Agentic (auto)` et `ArcIA-Agentic (expert)`, toute la complexité des fournisseurs sous-jacents est absorbée par la plateforme, avec la garantie d'une disponibilité continue et d'un coût maîtrisé.

---

## 3. Les 5 Briques de la Chaîne et leur Rôle Précis

### Brique 1 : Open-WebUI (Port `:8080`) — L'Interface et l'Aiguillage Frontal
* **Rôle** : Portail web collaboratif moderne intégrant le SSO Microsoft Entra ID.
* **Connexion amont** : Reçoit les requêtes HTTP/WebSocket des navigateurs collaborateurs.
* **Connexion aval** : Envoie les requêtes de chat managées vers `http://litellm-proxy.arcia.svc:4000/v1`.
* **Fonctionnalité clé (BYOK)** : Grâce au paramètre `ENABLE_DIRECT_CONNECTIONS=true`, Open-WebUI permet aux utilisateurs d'ajouter des connexions directes vers OpenAI, Anthropic, Mistral ou Gemini. Ces requêtes partent directement du navigateur du collaborateur vers le cloud tiers sans transiter par LiteLLM ni impacter le budget de l'entreprise.

### Brique 2 : LiteLLM Proxy (Port `:4000`) — Le Pivot Central Souverain
* **Rôle** : Passerelle centrale d'inférence de l'entreprise. C'est l'unique point de sortie réseau vers les fournisseurs d'IA pour tous les services internes (Open-WebUI, Hermes Agent, Teams Bot).
* **Masquage des Secrets** : La clé réelle d'entreprise (`OPENROUTER_API_KEY`) est conservée dans le secret Kubernetes `enterprise-llm-secret`. Elle n'est jamais transmise aux clients frontaux.
* **Gestion des Alias Invisibles (`router_settings.model_group_alias`)** :
  ```yaml
  router_settings:
    model_group_alias:
      "auto": "ArcIA-Agentic (auto)"
      "ArcIA-Agentic": "ArcIA-Agentic (auto)"
      "hermes-agent": "ArcIA-Agentic (auto)"
  ```
  Grâce à cette directive, les microservices qui appellent historiquement `auto` ou `hermes-agent` continuent de fonctionner parfaitement, tandis que l'API publique `/v1/models` ne présente aux utilisateurs que les deux modèles canoniques : `ArcIA-Agentic (auto)` et `ArcIA-Agentic (expert)`.

### Brique 3 : Presidio DLP (Port `:8080`) — Le Bouclier de Sécurité Pré-Vol
* **Rôle** : Caviardage en coupure automatique de toutes les requêtes avant leur départ vers le Cloud.
* **Mode opératoire (`pre_call_rules`)** : Avant qu'un prompt ne quitte le cluster vers OpenRouter, LiteLLM transmet le payload à `http://presidio-dlp:8080/sanitize`.
* **Éléments détectés et caviardés** :
  - **Identifiants & Données personnelles** : Adresses emails (`[ARCIA_EMAIL_1]`), numéros de téléphone (`[ARCIA_PHONE_1]`), cartes bancaires, adresses IP.
  - **Secrets techniques** : Clés privées RSA/ED25519, tokens JWT, clés d'API (`sk-...`), mots de passe et chaînes de connexion de bases de données (`[SECRET_REMOVED]`).
* **Zéro Fuite Cloud** : Même si un collaborateur colle par mégarde un fichier de configuration contenant un mot de passe de production, le modèle Cloud ne reçoit que la version caviardée.

### Brique 4 : OmniRoute v3.8.51 (Port `:20128` / `:20129`) — L'Orchestrateur Avancé LAN (Optionnel)
* **Rôle** : Routeur complémentaire activable à la demande (`omniroute.enabled: true`) pour les besoins complexes de multi-tenancy et de gestion avancée de clés.
* **Positionnement dans la chaîne** : OmniRoute se positionne en **fournisseur amont (*Upstream*) derrière LiteLLM**.
* **Intérêt combiné** : LiteLLM applique d'abord le caviardage Presidio DLP, puis relaie la requête saine à OmniRoute (`http://omniroute.arcia.svc:20128/v1`). OmniRoute exécute ensuite sa propre logique de pools de clés d'équipes ou de combos intelligents (`auto/coding`, `auto/smart`).
* **Console LAN Dédiée** : Son tableau de bord (`:20128/dashboard`) permet aux administrateurs réseau d'observer la latence en temps réel et la répartition de charge par fournisseur.

### Brique 5 : Hermes Agent (Ports `:9119` & `:8642`) — Le Moteur d'Agents Autonome
* **Rôle** : Exécuteur de missions longues, d'analyses de code complexes et d'orchestration multi-agents.
* **Consommateur d'Inférence** : Hermes ne dispose pas de clé API directe. Il s'appuie sur `litellm-proxy.arcia.svc:4000/v1` en appelant le modèle `ArcIA-Agentic (auto)`.
* **Optimisation Tokenmaxing (`arcia_tokenmaxing.py`)** : Avant de transmettre son contexte à LiteLLM, Hermes utilise le plugin natif ArcIA pour compresser les volumineuses sorties terminales (`git log`) et tronquer intelligemment les gros payloads JSON pour économiser les tokens et la mémoire de contexte.

---

## 4. Diagrammes de Séquence Temporelle Pas-à-Pas

### Scénario 1 : Collaborateur Standard posant une question avec `ArcIA-Agentic (auto)`

```mermaid
sequenceDiagram
    autonumber
    actor User as Collaborateur
    participant WebUI as Open-WebUI (:8080)
    participant LiteLLM as LiteLLM Proxy (:4000)
    participant Presidio as Presidio DLP (:8080)
    participant OpenRouter as OpenRouter Cloud
    participant Engine as LLM (DeepSeek / Claude / GPT)

    User->>WebUI: Saisie : "Corrige ce script d'accès à la DB : mot de passe root123"
    Note over WebUI: Modèle sélectionné : ArcIA-Agentic (auto)
    WebUI->>LiteLLM: POST /v1/chat/completions (model="ArcIA-Agentic (auto)")
    Note over LiteLLM: Déclenchement du guardrail Pre-Call
    LiteLLM->>Presidio: POST /sanitize (texte brut)
    Note over Presidio: Détection PASSWORD_PATTERN ("root123")
    Presidio-->>LiteLLM: Texte caviardé : "mot de passe [SECRET_REMOVED]"
    Note over LiteLLM: Résolution vers openrouter/auto
    LiteLLM->>OpenRouter: Inférence avec texte caviardé + OPENROUTER_API_KEY
    OpenRouter->>Engine: Routage dynamique vers le meilleur modèle disponible
    Engine-->>OpenRouter: Flux de réponse (streaming)
    OpenRouter-->>LiteLLM: Réponse du modèle
    LiteLLM-->>WebUI: Restitution de la correction sans fuite de mot de passe
    WebUI-->>User: Affichage du script corrigé dans le navigateur
```

---

### Scénario 2 : Collaborateur Expert guidant le modèle depuis son prompt avec `ArcIA-Agentic (expert)`

```mermaid
sequenceDiagram
    autonumber
    actor Expert as Collaborateur Expert
    participant WebUI as Open-WebUI (:8080)
    participant LiteLLM as LiteLLM Proxy (:4000)
    participant Presidio as Presidio DLP (:8080)
    participant OpenRouter as OpenRouter Cloud
    participant Frontier as Modèle Raisonnement (Claude 3.5 Sonnet / o1)

    Expert->>WebUI: Saisie : "[Consigne: Raisonnement approfondi] Conçois l'architecture distribuée de notre CSI..."
    Note over WebUI: Modèle sélectionné : ArcIA-Agentic (expert)
    WebUI->>LiteLLM: POST /v1/chat/completions (model="ArcIA-Agentic (expert)")
    LiteLLM->>Presidio: POST /sanitize (vérification PII & secrets)
    Presidio-->>LiteLLM: Prompt vérifié et assaini
    Note over LiteLLM: Modèle ciblé : openrouter/anthropic/claude-3.5-sonnet<br/>(Fallback : openrouter/openai/gpt-4o)
    LiteLLM->>OpenRouter: Envoi avec consigne de raisonnement haute fidélité
    OpenRouter->>Frontier: Exécution de la chaîne de pensée (Chain of Thought)
    Frontier-->>OpenRouter: Synthèse d'architecture approfondie
    OpenRouter-->>LiteLLM: Réponse haute précision
    LiteLLM-->>WebUI: Restitution du plan d'architecture
    WebUI-->>Expert: Affichage détaillé dans le portail
```

---

### Scénario 3 : Power User utilisant sa propre clé personnelle (BYOK)

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Développeur / Chercheur
    participant WebUI as Open-WebUI (Navigateur Dev)
    participant Vendor as Fournisseur Tiers (OpenAI / Anthropic Direct)

    Note over Dev,WebUI: Configuration unique dans Open-WebUI :<br/>Paramètres > Connexions > Clé personnelle sk-proj-...
    Dev->>WebUI: Sélection du modèle personnel : perso/gpt-4o
    Dev->>WebUI: Saisie du prompt expérimental
    Note over WebUI: ENABLE_DIRECT_CONNECTIONS=true actif :<br/>Bypass total du réseau interne ArcIA
    WebUI->>Vendor: POST direct https://api.openai.com/v1/chat/completions<br/>Authorization: Bearer sk-proj-...
    Vendor-->>WebUI: Flux de réponse chiffré HTTPS
    WebUI-->>Dev: Affichage de la réponse
    Note over Dev,WebUI: Zéro impact sur les quotas de l'entreprise<br/>Clé privée conservée dans le profil utilisateur
```

---

### Scénario 4 : Mission Autonome exécutée par Hermes Agent

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Administrateur / Ingénieur
    participant Studio as Hermes Studio (:9119)
    participant Hermes as Hermes Agent (:8642)
    participant Tokenmaxing as Plugin ArcIA Tokenmaxing
    participant LiteLLM as LiteLLM Proxy (:4000)
    participant Presidio as Presidio DLP (:8080)
    participant Cloud as Fournisseur Cloud

    Admin->>Studio: Lancement de mission : "Auditer l'arborescence et générer un rapport de dépendances"
    Studio->>Hermes: Création de tâche autonome
    Note over Hermes: Exécution shell interne : git log & analyse fichiers
    Hermes->>Tokenmaxing: Interception sortie shell brute (1500 lignes)
    Tokenmaxing-->>Hermes: Sortie compressée RTK (50 lignes utiles)
    Note over Hermes: Émission du plan de raisonnement
    Hermes->>LiteLLM: POST /v1/chat/completions (model="ArcIA-Agentic (auto)")
    LiteLLM->>Presidio: POST /sanitize
    Presidio-->>LiteLLM: Prompt assaini
    LiteLLM->>Cloud: Requête d'inférence
    Cloud-->>LiteLLM: Décision d'outil / Synthèse
    LiteLLM-->>Hermes: Restitution du plan validé
    Hermes-->>Studio: Mise à jour temps réel sur le tableau Kanban
```

---

## 5. Exemple Concret de Caviardage en Direct

Voici ce qui se produit concrètement lorsqu'un prompt franchit la barrière Presidio DLP :

### 1. Payload émis par l'utilisateur (Open-WebUI)
```text
Bonjour, peux-tu analyser cette anomalie survenue sur le serveur de Jean Dupont (jean.dupont@example.org) ?
Voici la chaîne de connexion utilisée : postgresql://app_user:SuperSecretPassword2026@192.168.1.45:5432/production_db
```

### 2. Payload intercepté et transformé par Presidio DLP
```text
Bonjour, peux-tu analyser cette anomalie survenue sur le serveur de Jean Dupont ([ARCIA_EMAIL_1]) ?
Voici la chaîne de connexion utilisée : postgresql://app_user:[SECRET_REMOVED]@[IP_ADDRESS_1]:5432/production_db
```

### 3. Payload transmis au modèle Cloud (OpenRouter)
Le modèle d'IA externe analyse le problème technique, comprend la structure de la requête PostgreSQL et formule ses recommandations de configuration **sans jamais avoir vu le mot de passe réel, l'adresse email nominative ou l'adresse IP interne**.

---

## 6. Foire Aux Questions (FAQ) Décisionnelle

### Q1. Pourquoi avoir à la fois LiteLLM et OmniRoute ? Ne font-ils pas doublon ?
**Non, leurs responsabilités sont complémentaires et distinctes :**
* **LiteLLM Proxy** est le **point d'ancrage de sécurité central** : c'est lui qui héberge le guardrail d'interception `pre_call` Presidio DLP pour garantir qu'aucune donnée ne fuit. Il présente une interface ultra-simple aux utilisateurs (`auto` et `expert`).
* **OmniRoute** est un **orchestrateur amont optionnel** : il est déployé si l'organisation souhaite gérer graphiquement des pools de clés multi-équipes, construire des chaînes de repli sur mesure (*combos* `auto/coding`, `auto/smart`) ou observer les métriques réseau fines sur son portail LAN. Lorsqu'il est activé, il se place *derrière* LiteLLM, bénéficiant ainsi du caviardage DLP préalable.

### Q2. Comment fonctionne le guidage par prompt dans `ArcIA-Agentic (expert)` ?
Dans `ArcIA-Agentic (expert)`, la requête est acheminée vers un modèle de raisonnement de pointe (Claude 3.5 Sonnet par défaut, avec replis sur GPT-4o).
Le collaborateur peut orienter l'exécution en précisant ses exigences au début de son prompt :
* *Exemple 1* : `[Modèle: Claude] Rédige un contrat d'architecture conforme aux spécifications ci-jointes.`
* *Exemple 2* : `[Raisonnement: Pas-à-pas] Démontre la résilience de ce quorum Raft en cas de perte simultanée de deux nœuds.`
Le modèle de pointe interprète ces consignes pour adapter sa profondeur de réflexion, structurer sa chaîne de pensée (Chain of Thought) et fournir un niveau d'exigence technique maximal.

### Q3. Les clés d'API des utilisateurs (BYOK) sont-elles visibles par les administrateurs du cluster ?
**Non.** Avec `ENABLE_DIRECT_CONNECTIONS=true`, la clé d'API personnelle saisie par un utilisateur dans Open-WebUI est enregistrée dans sa propre session (`localStorage` du navigateur ou champ chiffré dans la base SQLite locale `webui.db`).
La requête HTTP part directement du poste client vers les serveurs publics d'OpenAI ou d'Anthropic. Elle ne passe ni par le Pod LiteLLM, ni par Presidio, et n'apparaît dans aucun log Kubernetes du cluster.

### Q4. Que se passe-t-il si le fournisseur principal Cloud subit une panne ?
Le mécanisme de repli (*fallback*) configuré dans `05-litellm.yaml` prend immédiatement le relais de manière transparente :
* Pour `ArcIA-Agentic (auto)` : si `openrouter/auto` échoue, LiteLLM bascule instantanément sur `openrouter/anthropic/claude-3.5-sonnet`, puis sur `openrouter/openai/gpt-4o`.
* Pour `ArcIA-Agentic (expert)` : si Claude subit une coupure ou un rate-limit, LiteLLM bascule automatiquement sur GPT-4o puis sur le profil auto.
L'utilisateur final ne reçoit aucune erreur 500 : sa requête aboutit sans friction.

---

Voir également :
- [Passerelle d'Inférence d'Entreprise LiteLLM](inference-litellm.md)
- [Gouvernance & Confidentialité Presidio DLP](confidentialite-presidio.md)
- [Routeur Complémentaire OmniRoute](omniroute.md)
- [Moteur d'Agents Autonome Hermes](hermes-agent.md)
- [Portail Open-WebUI & Authentification SSO](portail-webui-entraid.md)
- [Quickstart & Configuration Pratique](../runbooks/quickstart.md)
