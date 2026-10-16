# ArcIA — schémas explicatifs

Les schémas 1–3 décrivent le socle actuellement déployé en qualification ; les schémas 4–5 décrivent des contrats cibles qui restent à intégrer. [Architecture](architecture.md) · [Partage](guides/plateforme-arcia.md) · [Contrat complet](plan-integration-hermes.md).

## 1. Composants du socle

```mermaid
flowchart TB
  U[Utilisateur de qualification] --> TLS[Entrée NGINX : HTTPS]
  TLS --> H[Hermes : état exclusif RWOP]
  H --> K[Knowledge : MCP de lecture]
  K --> PG[PostgreSQL : 3 instances et pgvector]
  K --> O[Originaux et schémas : PVC privé]
  H --> G[Gateway : identité et pool administré]
  G --> P[Presidio FR et EN : filtrage intégral]
  P --> R[OmniRoute : clé scoped et mode auto]
  R --> C[Modèles cloud : politique d’instance]
  LAN[Portail OmniRoute privé : admin et personnel] --> G
  H --> DNS[DNS interne statique sans forwarding]
  H --> T[Outils et skills : volume en lecture seule]
  ADMIN[Contrôleur administratif protégé] --> K3S[3 VM Debian : K3s et etcd]
  K3S --> CSI[vSphere CSI : datastore partagé]
```

Hermes ne possède pas de clé fournisseur et ne contacte pas directement Internet. OmniRoute ne reçoit que le contenu assaini du gateway ; le relais gratuit historique conserve son attestation HMAC. Knowledge calcule ses vecteurs localement. Les comptes et domaines sont des paramètres d’instance.

## 2. Parcours RAG

```mermaid
flowchart LR
  F[PDF textuel, OpenAPI, texte ou schéma] --> I[Ingestion privée : provenance et périmètre]
  I --> A[Original, hash, version, assets]
  I --> E[Extraction et fenêtres de tokens]
  E --> V[E5 : titre et corps]
  E --> L[mLateOn : vecteurs de tokens]
  Q[Question autorisée] --> S[FTS et recherche dense sous RLS]
  V --> S
  S --> R[RRF : 30 candidats]
  L --> X[MaxSim local]
  R --> X
  X --> REP[Extraits et citations]
  A --> REP
```

Les ACL s’appliquent avant la restitution. Les matrices de tokens affinent le classement ; elles ne permettent pas encore de comprendre visuellement toutes les illustrations. Les sources éditables sont conservées pour adaptation.

## 3. Filtrage et sortie modèle

```mermaid
sequenceDiagram
  participant H as Hermes
  participant G as Gateway ArcIA
  participant P as Presidio local
  participant R as OmniRoute loopback
  participant C as Fournisseur cloud autorisé
  H->>G: Requête et token de périmètre
  G->>G: Relire identité et rôles, choisir pool et mode admin
  G->>P: Messages, historique, outils et extraits RAG
  P->>P: Vérifier scope et classe, filtrer FR/EN, retirer secrets
  P-->>G: Corps assaini ou refus
  G->>R: Corps assaini et clé limitée aux connexions et modèles
  R->>C: Appel TLS sous politique d’instance
  C-->>R: Réponse ou refus
  R-->>G: Résultat
  G-->>H: Réponse OpenAI compatible ou erreur bornée
```

Le mode streaming actuel restitue des événements SSE après réception de la réponse complète ; il ne garantit pas la latence d’un flux fournisseur token par token. Les appels à des MCP externes demandent une qualification distincte.

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
