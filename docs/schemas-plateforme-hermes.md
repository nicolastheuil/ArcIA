# ArcIA — schémas explicatifs

Les schémas 1–3 décrivent le socle actuellement déployé en qualification ; les schémas 4–5 décrivent des contrats cibles qui restent à intégrer. [Architecture](architecture.md) · [Partage](guides/plateforme-arcia.md) · [Contrat complet](plan-integration-hermes.md).

## 1. Composants du socle v0.2

```mermaid
flowchart TB
  U[Collaborateur Web] --> TR[Traefik Ingress : HTTPS / 443]
  T[Équipe Teams] --> TB[Teams Bot Adapter : 3978]
  D[Hermes Desktop] --> TR
  TR --> FA[OAuth2-Proxy : SSO Microsoft Entra ID]
  FA --> W[Open-WebUI : 8080 / PVC 20Gi]
  FA --> H[Hermes Agent : Studio 9119 & Gateway 8642 / PVC 20Gi]
  TB --> L
  W --> L[LiteLLM Proxy : 4000 / Modèle auto]
  H --> L
  H --> SK[Volume partagé /opt/shared-skills : ECC, Superpowers, ArcIA]
  H --> GF[ArcIA Graphify : AST déterministe local 0 token]
  L --> P[Presidio DLP : 8080 / Caviardage PII & secrets]
  P --> C[Modèles Cloud : OpenRouter / Claude 3.5, GPT-4o, DeepSeek]
  ADMIN[Poste Administrateur] --> K3S[3 VM Debian : K3s HA et etcd]
  K3S --> CSI[vSphere CSI : StorageClass arcia-vsphere]
```

Hermes ne possède pas de clé fournisseur en clair et ne contacte pas directement Internet. LiteLLM achemine les flux à travers Presidio DLP pour anonymisation systématique. Les données privées restent sur les volumes persistants sécurisés par VMware CSI.

## 2. Parcours d'Analyse Locale & Compétences (Graphify & Skills)

```mermaid
flowchart LR
  SRC[Code source Python, JS, Go, Rust] --> G[ArcIA Graphify : analyseur AST local déterministe]
  G --> AST[Extraction des nœuds, fonctions, classes et dépendances]
  AST --> GR[Génération locale : graph.json et GRAPH_REPORT.md]
  GR --> H[Hermes Agent : contexte enrichi 0 token dépensé]
  SK[Shared Skills : Ponytail, Public-APIs, ECC] --> H
  H --> SOL[Solution minimale et sobre : respect YAGNI]
```

L'analyse de code et la documentation interne sont traitées localement sans aucun envoi vers des API cloud tierces, garantissant l'hermétisme de la propriété intellectuelle.

## 3. Filtrage et sortie modèle (LiteLLM & Presidio DLP)

```mermaid
sequenceDiagram
  participant Client as Open-WebUI / Hermes / Teams
  participant LLM as LiteLLM Proxy (:4000)
  participant DLP as Presidio DLP (:8080)
  participant Cloud as OpenRouter Cloud API
  Client->>LLM: Requête d'inférence (model: auto)
  LLM->>DLP: POST /sanitize (corps du prompt et contexte)
  DLP->>DLP: Détection PII, regex secrets, emails, IPs, clés
  DLP-->>LLM: Texte caviardé ([ARCIA_EMAIL_1], [SECRET_REMOVED])
  LLM->>Cloud: POST /v1/chat/completions (données assainies)
  Cloud-->>LLM: Réponse générée
  LLM-->>Client: Restitution fluide et sécurisée
```

Le caviardage DLP Presidio s'applique avant toute sortie vers des modèles d'inférence externes, préservant la stricte confidentialité des données métier.

## 4. Partage entreprise et isolation : cible

L'identification repose sur Open-WebUI et le SSO Microsoft Entra ID (via OAuth2-Proxy). [Portail et SSO Entra ID](guides/portail-webui-entraid.md).

```mermaid
flowchart TB
  UA[Utilisateur A] --> IAM[Identité et autorisation serveur]
  UB[Utilisateur B] --> IAM
  IAM --> RA[Open-WebUI : historique et sessions propres]
  IAM --> RB[Hermes Agent : studio et gateway propres]
  RA --> KB[LiteLLM : routage et modèles d'entreprise]
  RB --> KB
  KB --> DLP[Presidio DLP : caviardage PII et secrets]
  DLP --> CLOUD[Modèles Cloud sécurisés]
```

La séparation des espaces et le cloisonnement sont détaillés dans le [guide plateforme](guides/plateforme-arcia.md). Les agents délégués n’obtiennent pas des droits plus larges.

## 5. Harness et instances

```mermaid
flowchart LR
  H[ArcIA : plateforme ArcIA] --> V[Révision fixée et bootstrap générique]
  V --> I[Déploiement d’une instance]
  CUSTOM[Dépôt d’instance : usages et connecteurs] --> I
  SEC[Configuration chiffrée et clés externes] --> I
  SOURCES[Corpus et systèmes autorisés] --> I
  I --> REC[Recette, exploitation et reprise]
  REC --> H
```

Les capacités génériques remontent au harness. Les usages, comptes, habilitations et corpus particuliers restent dans l’instance. Git reconstruit le logiciel ; la récupération des données exige des sauvegardes indépendantes.
