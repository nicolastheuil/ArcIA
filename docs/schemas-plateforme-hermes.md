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
  H --> P[Presidio FR et EN : filtrage intégral]
  P --> R[Relais cloud : attestation HMAC]
  R --> C[OpenRouter free : ZDR et prix nul]
  H --> DNS[DNS interne statique sans forwarding]
  H --> T[Outils et skills : volume en lecture seule]
  ADMIN[Contrôleur administratif protégé] --> K3S[3 VM Debian : K3s et etcd]
  K3S --> CSI[vSphere CSI : datastore partagé]
```

Hermes ne possède pas de clé fournisseur et ne contacte pas directement Internet. Le relais ne reçoit que les payloads assainis et attestés. Knowledge calcule ses vecteurs localement. Les comptes et domaines sont des paramètres d’instance.

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
  participant P as Presidio et politique
  participant R as Relais isolé
  participant C as OpenRouter
  H->>P: Messages, historique, outils et extraits RAG
  P->>P: Authentifier scope et classe de données
  P->>P: Détecter FR/EN, retirer secrets, pseudonymiser
  P->>P: Refuser formats opaques et options non autorisées
  P->>R: Payload assaini avec signature, nonce et date
  R->>R: Vérifier attestation, modèle, prix nul et ZDR
  R->>C: Appel TLS au seul endpoint autorisé
  C-->>R: Réponse ou indisponibilité d’une route conforme
  R-->>P: Résultat sans message d’erreur fournisseur brut
  P-->>H: Réponse OpenAI compatible ou refus
```

Le mode streaming actuel restitue des événements SSE après réception de la réponse complète ; il ne garantit pas la latence d’un flux fournisseur token par token. Les appels à des MCP externes demandent une qualification distincte.

## 4. Partage entreprise et isolation : cible

L'identification par défaut passe par Keycloak : comptes locaux permanents,
portail d'administration et fédération SSO optionnelle en parallèle. Le
raccordement des deux espaces synthétiques ne qualifie pas encore le
provisioning général ni les ACL de groupes. [Identité](guides/identite-utilisateurs.md).

```mermaid
flowchart TB
  UA[Utilisateur A] --> IAM[Identité et autorisation serveur]
  UB[Utilisateur B] --> IAM
  IAM --> RA[Runtime A : historique et connexions propres]
  IAM --> RB[Runtime B : historique et connexions propres]
  RA --> KB[Service documentaire : ACL avant recherche et téléchargement]
  RB --> KB
  KB --> COMMUN[Corpus commun : personnes habilitées]
  KB --> GROUPE[Corpus restreint : groupe autorisé]
  KB --> PERSO[Documents personnels : propriétaire]
```

Deux runtimes locaux distincts et une lecture « commun + personnel » existent en qualification synthétique. Le schéma reste une cible pour l’IAM central et les groupes. La [recette multi-utilisateur](guides/multi-utilisateur.md) détaille les preuves et limites. Les agents délégués n’obtiennent pas des droits plus larges.

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
