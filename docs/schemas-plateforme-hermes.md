# Plateforme Hermes — schémas détaillés d’architecture
Date : 11 octobre 2026. Architecture cible proposée, complément du plan d’intégration v1.2.

Ces schémas décrivent un système à construire et à qualifier. Ils ne représentent pas une plateforme déjà déployée. Les boîtes de services sont des responsabilités logiques : certaines peuvent partager un service ou un conteneur au démarrage.

Hermes apporte le moteur d’agent, ses profils, sa mémoire et ses interfaces compatibles. Le RBAC métier, le routage multi-consultants, les connecteurs de secrets, le contrôle d’exécution, les approbations intercanal et le filtre de sortie sont des intégrations de plateforme. La compatibilité exacte de Desktop et des plugins doit être prouvée sur les versions retenues.

## 1. Entrées, contrôle et composants

```mermaid
flowchart TD
  subgraph ENT["Points d’entrée"]
    direction TB
    D["Consultant : Hermes Desktop"]
    T["Consultant : Teams"]
    E["Entra ID : identité commune"]
  end
  D --> N["NAT entrant : HTTPS 443"]
  N --> RP["Reverse proxy : TLS"]
  RP --> G["Gateway Desktop : session vérifiée"]
  T --> MS["Service Teams Microsoft"]
  MS --> RP
  RP --> B["Webhook bot : validation SDK Teams"]
  E -.-> G
  E -.-> B

  subgraph VM["Cluster privé K3s : trois VM Debian"]
    direction TB
    G --> A["API métier : identité, client, mission"]
    B --> A
    A --> P["RBAC et politique d’opérations"]
    P --> O["Orchestrateur et file de missions"]
    O --> H["Runtime Hermes : consultant / client"]
    O --> X["Lanceur restreint : exécuteur de mission"]
    H --> K["Connaissances : filtrage ACL"]
    H --> IA["Passerelle IA : assainissement"]
    H --> P
    P --> AP["Approbations et capacités d’exécution"]
    AP --> X
    X --> V["OpenConnect personnel temporaire"]
    A -.-> J["Audit local protégé"]
    AP -.-> J
    X -.-> J
  end
  AP -->|"carte au demandeur"| MS
  V --> SI["SI client : cibles autorisées"]
  IA --> R["OmniRoute local"]
  R --> C["Modèles cloud autorisés"]
  AD["Ingénieur : Codex et dépôt harness"] -->|"SSH sur accès privé"| DP["Déploiement administrateur"]
  DP --> O
```

Desktop et Teams utilisent la même identité métier tenant + object_id. L’email est un attribut d’affichage. Le serveur associe chaque session au périmètre autorisé.

Deux authentifications distinctes protègent l’entrée HTTPS : OIDC/session pour Desktop, protocole et validation SDK pour les callbacks Teams. Un callback Teams ne passe pas par une page de connexion humaine.

Seul le reverse proxy est publié par le NAT. Bases, OmniRoute, coffres et API internes restent privés. L’administration SSH passe par le réseau d’entreprise ou un accès administratif privé. Le schéma omet la sortie Internet documentaire, détaillée au §7.

## 2. Parcours de raisonnement et d’une mission

Le diagramme expose les étapes opérationnelles observables : tâches, hypothèses, preuves, décisions et validations. Il ne représente pas une extraction du raisonnement interne privé du modèle.

```mermaid
flowchart TD
  U["Demande Desktop ou Teams"] --> I["Identifier consultant, client et mission"]
  I --> S{"Périmètre autorisé et suffisamment précis ?"}
  S -->|"non"| Q["Clarification ou refus"]
  Q --> I
  S -->|"oui"| CO["Coordinateur : objectifs et plan de collecte"]
  CO --> KB["Recherche documentaire avec ACL et version"]
  CO --> COL["Proposer une collecte bornée"]
  COL --> POL["Politique : autoriser ou demander Teams"]
  POL --> EX["Exécuteur : collecte via VPN personnel"]
  EX --> EV["Preuves brutes locales et résultats assainis"]
  KB --> SP["Spécialistes à la demande"]
  EV --> SP
  SP --> HY["Hypothèses, preuves et incertitudes"]
  HY --> REV["Relecture : vérifier les conclusions"]
  REV --> MORE{"Preuves supplémentaires nécessaires ?"}
  MORE -->|"oui"| COL
  MORE -->|"non"| CH{"Changement client nécessaire ?"}
  CH -->|"non"| REP["Rapport et recommandations"]
  CH -->|"oui"| PLAN["Plan exact : cibles, risque et rollback"]
  PLAN --> AP["Circuit d’approbation Teams"]
  AP --> ACT["Exécution contrôlée"]
  ACT --> VER["Vérifier l’état après action"]
  VER --> REP
  REP --> END["Clôture : arrêter VPN et exécuteur"]
  END --> REX["Proposer un REX générique à la KB"]
```

Le coordinateur délègue aux spécialistes utiles : VMware, réseau ou autres produits du catalogue. Tous restent dans le périmètre de la mission. Le relecteur améliore les conclusions ; il ne délivre pas une autorisation d’écriture.

Les boucles sont bornées par une durée, un nombre d’appels, un débit et un budget. Une collecte lourde ou intrusive passe aussi par Teams. L’absence de preuve devient une incertitude visible dans le rapport.

La clôture normale suit la production du rapport ; expiration, annulation, crash et perte de tunnel déclenchent un nettoyage indépendant. La publication d’un REX nécessite assainissement et revue de promotion.

## 3. Cloisonnement des consultants, missions et VPN

```mermaid
flowchart TD
  CTRL["Contrôle partagé : RBAC, missions et lanceur"]
  subgraph AX["Consultant A / Client X"]
    direction TB
    HAX["Runtime Hermes A-X"]
    XAX["Exécuteur mission M1"]
    VAX["VPN A-X : namespace M1"]
    HAX -->|"proposition contrôlée"| XAX
    XAX --> VAX
  end
  subgraph BX["Consultant B / Client X"]
    direction TB
    HBX["Runtime Hermes B-X"]
    XBX["Exécuteur mission M2"]
    VBX["VPN B-X : namespace M2"]
    HBX -->|"proposition contrôlée"| XBX
    XBX --> VBX
  end
  subgraph AY["Consultant A / Client Y"]
    direction TB
    HAY["Runtime Hermes A-Y"]
    XAY["Exécuteur mission M3"]
    VAY["VPN A-Y : namespace M3"]
    HAY -->|"proposition contrôlée"| XAY
    XAY --> VAY
  end
  CTRL --> HAX
  CTRL --> HBX
  CTRL --> HAY
  VAX --> SX["SI Client X"]
  VBX --> SX
  VAY --> SY["SI Client Y"]
  HAX --> RET["Service de recherche : droits avant résultats"]
  HBX --> RET
  HAY --> RET
  RET --> DOCX["KB Client X : ACL et clé propres"]
  RET --> DOCY["KB Client Y : ACL et clé propres"]
  RET --> COM["Documentation commune"]
```

Les flèches runtime → exécuteur représentent une demande passant par le contrôle partagé ; elles ne constituent pas un accès shell direct. Chaque exécuteur reçoit une capacité limitée et des volumes calculés côté serveur.

| Élément | Partage |
|---|---|
| Documentation générale | Commune aux utilisateurs autorisés du scope entreprise. |
| Dossier et livrables Client X | Entre consultants A et B si habilités. |
| Historique privé A-X | Propre au consultant A, sauf passation explicite. |
| Runtime A-X et runtime A-Y | Séparés malgré le même consultant. |
| Connexion VPN A-X et B-X | Comptes, certificats, MFA, routes et sessions distincts. |
| Exécuteurs et namespaces | Temporaires, rattachés à une mission. |
| Administration de l’hôte | Ingénieurs de confiance, périmètre privilégié audité. |

Client X et Client Y peuvent avoir les mêmes adresses IP privées. Le routage est séparé par namespace. Une route ou un DNS poussés par le client n’affectent pas l’hôte ni les autres missions.

Chaque exécuteur utilise le namespace de son tunnel ou un rattachement réseau équivalent validé. Le pare-feu interdit tout trafic client hors tunnel et tout rebond vers l’entreprise. Les communications vers les services de contrôle utilisent des destinations étroites approuvées.

Le partage de Client X impose un verrou de changement sur les cibles : deux VPN personnels ne doivent pas permettre deux modifications concurrentes incompatibles.

Les conteneurs d’un nœud partagent son noyau Linux. Les frontières dépendent des mounts, identités, privilèges et règles réseau. Seul le composant VPN possède les capacités réseau nécessaires ; les runtimes n’ont ni mode privileged, ni réseau hôte, ni socket Docker. Une VM d’exécution dédiée reste possible si un client exige une isolation renforcée.

## 4. Autorisation et validation Teams

```mermaid
flowchart TD
  PROP["Proposition de l’agent"] --> RES["Résolution locale : cibles et paramètres réels"]
  RES --> P["Contrôle des droits et de l’impact"]
  P --> RISK{"Risque pour le SI client ?"}
  RISK -->|"non, lecture bornée"| CAPR["Capacité de lecture limitée"]
  RISK -->|"oui"| IMM["Plan immuable : empreinte et expiration"]
  IMM --> CARD["Carte Teams : action, risque et rollback"]
  CARD --> US["Demandeur habilité : décision"]
  US --> DEC{"Décision reçue et identité vérifiée"}
  DEC -->|"refus"| STOP["Arrêt de l’opération"]
  DEC -->|"modifier"| PROP
  DEC -->|"approbation"| CAPW["Capacité unique liée au plan"]
  CAPR --> CHECK["Recontrôle : droits, fenêtre et état cible"]
  CAPW --> CHECK
  CHECK --> VALID{"Préconditions toujours valides ?"}
  VALID -->|"non"| REPLAN["Réviser le plan et renouveler la validation"]
  REPLAN --> PROP
  VALID -->|"oui"| EXEC["Exécuter exactement l’opération autorisée"]
  EXEC --> POST{"Résultat et état vérifiés ?"}
  POST -->|"oui"| LOG["Journaliser les preuves et informer"]
  POST -->|"échec confirmé"| RB["Rollback prévu si autorisé et applicable"]
  POST -->|"état incertain"| REC["Suspendre et réconcilier l’état réel"]
  RB --> LOG
  REC --> LOG
```

La carte est liée à la mission, même si la demande initiale vient de Desktop. Elle affiche le périmètre réel uniquement aux personnes habilitées.

L’approbation porte sur une action précise, pas sur toute la session. Toute modification significative des cibles ou paramètres invalide la capacité. Le service recontrôle les habilitations à l’exécution.

Un rollback automatique n’est possible que si ses étapes et conditions font partie du plan approuvé. Un rollback différent repasse par la politique et, si nécessaire, par Teams. Une écriture au résultat incertain ne se rejoue pas automatiquement.

En attente de décision, le tunnel est fermé à l’inactivité ; une approbation ultérieure peut nécessiter reconnexion, MFA et nouvelle vérification des préconditions. Teams indisponible signifie écritures en attente.

## 5. Coffres persistants et injection de secrets

```mermaid
flowchart TD
  USER["Consultant authentifié"] --> W["Enrôlement protégé de ses connecteurs"]
  W --> PP["Passbolt : identité et droits du consultant"]
  W --> P1["1Password : délégation personnelle bornée"]
  W --> BW["Bitwarden : connecteur adapté au produit"]
  PP --> META["Recherche de métadonnées accessibles"]
  P1 --> META
  BW --> META
  META --> CH["Confirmation de la bonne entrée"]
  CH --> MAP["Binding durable : utilisateur, client et UUID"]
  MAP --> REG["Registre chiffré des bindings"]
  REG --> BROK["Broker de secrets : capacité vérifiée"]
  PP --> BROK
  P1 --> BROK
  BW --> BROK
  BROK -->|"injection locale limitée"| X["Exécuteur ou authentification OpenConnect"]
  X --> ZERO["Expiration et nettoyage des secrets temporaires"]
  MFA["Formulaire protégé : OTP ou SAML"] --> X
```

L’agent aide à identifier l’entrée en demandant les informations nécessaires ; le consultant confirme. Le mapping est conservé par identifiant stable. Passbolt est utilisé en l’état.

La connexion au coffre peut persister côté serveur, avec sa délégation stockée sous chiffrement. Cela ne rend ni l’OTP, ni le tunnel VPN, ni un cookie de session client persistants.

Le modèle reçoit une référence de secret, jamais le mot de passe ou le token. Le broker injecte seulement dans le composant autorisé, pour l’opération prévue. Les sorties sont filtrées pour éviter qu’un outil ne réaffiche un secret.

Les coffres personnels restent individuels. La prise en charge d’un fournisseur suppose un mode d’authentification serveur compatible et une qualification de ses permissions ; une intégration qui dépend uniquement du coffre Desktop déverrouillé ne satisfait pas l’autonomie demandée.

## 6. Données et appels aux modèles cloud

```mermaid
flowchart TD
  subgraph LOCAL["Zone privée : données identifiantes"]
    direction TB
    SI["Collectes et configurations clients"] --> RAW["Preuves brutes : stockage local protégé"]
    DOC["RAG avec ACL, fichiers et historiques"] --> MIN["Extraction et minimisation"]
    RAW --> MIN
    MIN --> DET["Presidio, règles métier et scanner de secrets"]
    DET --> AL["Substitution cohérente par mission"]
    AL --> VAL["Contrôle du payload complet"]
    AL -.-> MAP["Correspondances locales chiffrées"]
    VAL --> OK{"Format couvert et sortie autorisée ?"}
    OK -->|"non"| QU["Blocage et revue locale"]
    OK -->|"oui"| COMP["Une couche de compression qualifiée"]
    COMP --> ROUTE["OmniRoute : politique, budget et fournisseurs"]
    RESP["Réponse : hypothèses ou propositions"]
    CONTROL["Validation locale des sorties et actions"]
    FINAL["Livrable : résolution locale pour affichage autorisé"]
    NEXT["Nouvel appel : repasser par le filtre"]
  end
  ROUTE --> FREE["Modèle gratuit qualifié"]
  ROUTE -->|"repli autorisé"| OR["OpenRouter prépayé : modèle qualifié"]
  FREE --> RESP
  OR --> RESP
  RESP --> CONTROL
  CONTROL --> FINAL
  MAP -.-> FINAL
  CONTROL --> NEXT
  NEXT --> MIN
```

Toutes les sorties modèle passent par la même passerelle : messages, historique, RAG, fichiers, résultats d’outils et arguments. La politique de routage porte aussi sur les fournisseurs derrière les modèles gratuits. Aucun runtime ne possède une clé fournisseur ou une sortie réseau directe permettant de contourner ce chemin.

Exemple : un nom d’hôte réel devient HOST_007 et conserve cette correspondance dans la mission. Le rapport destiné au consultant peut retrouver le nom réel localement. Un secret ne bénéficie jamais de cette restitution dans une sortie modèle.

Presidio apporte des détecteurs, complétés par règles techniques et scanner de secrets. Ce dispositif réduit le risque ; il n’offre pas une garantie exhaustive de détection. Un format opaque ou non qualifié est bloqué.

La récupération d’un original depuis un cache RTK ou Headroom repasse par le filtre. Recherche Web, Context7, MCP externes et extraction sémantique Graphify sont aussi des sorties contrôlées.

## 7. Alimentation documentaire automatique et partage

```mermaid
flowchart TD
  CAT["Catalogue : éditeurs, produits, versions et sources"] --> SCH["Planificateur : contrôles quotidiens ou hebdomadaires"]
  SCH --> FETCH["Collecteur : domaines et accès autorisés"]
  SRC["Portails, PDF, HTML et release notes officiels"] --> FETCH
  FETCH --> DIFF{"Nouveau contenu ou nouvelle version ?"}
  DIFF -->|"non"| FRESH["Mettre à jour la date de contrôle"]
  DIFF -->|"oui"| LAND["Zone locale : hash, provenance et contrôle de fichier"]
  LAND --> PAR["Docling local : texte, tableaux et OCR"]
  PAR --> CHUNK["Fragments : produit, version, page et ACL"]
  CHUNK --> EMB["Embeddings locaux"]
  EMB --> IDX["Index hybride : texte et pgvector"]
  CHUNK --> ARCH["Archive versionnée selon droits et politique"]
  IDX --> RET["Recherche : identité et ACL avant résultats"]
  CKB["Connaissances client et rapports"] --> CIDX["Index client séparé ou filtrage éprouvé"]
  CIDX --> RET
  RET --> AG["Agents : extraits pertinents et citations"]
  REX["REX proposé par une mission"] --> CLEAN["Assainissement et revue du curateur"]
  CLEAN --> COMMON["Connaissance générique commune"]
  COMMON --> IDX
```

L’ajout d’un produit dans le catalogue déclenche son alimentation sans réinstallation de la plateforme. La documentation ciblant les versions client reste disponible même si une version plus récente existe.

Les documents sont des données non fiables : aucune instruction contenue dans un PDF ou une page n’autorise un outil. L’indexation locale ne nécessite pas Ollama ; un modèle d’embedding CPU peut être utilisé.

Les fichiers éditeurs peuvent dépendre d’une licence ou d’un portail authentifié : le collecteur suit les droits acquis. « Disponible aux agents » signifie accessible via recherche autorisée, pas injecté en totalité dans chaque prompt.

Le dossier client ne devient pas commun par simple indexation. Seul un REX assaini et promu rejoint la connaissance générale. Les exports, caches et citations conservent leur périmètre.

## 8. GitHub, clés et reconstruction

```mermaid
flowchart TD
  CODE["GitHub : code, manifests et versions"] --> BUILD["Builder : reconstruire les composants"]
  STATE["État local : bases, missions et corpus"] --> SNAP["Snapshot cohérent et manifeste"]
  SNAP --> ENC["Chiffrement local par périmètre"]
  ENC --> GIT["GitHub privé et LFS : objets chiffrés"]
  KEYS["Clés de récupération : Passbolt ou kit hors GitHub"] --> REST["Restore protégé"]
  GIT --> REST
  BUILD --> VM["Cluster neuf : déploiement en mode sûr"]
  REST --> VM
  VM --> VERIFY["Vérifier Entra, ACL, coffres, Teams et filtres"]
  VERIFY --> INVALID["Invalider anciens VPN et capacités d’écriture"]
  INVALID --> RECON["Réconcilier les missions interrompues"]
  RECON --> ACCEPT["Recette : lecture, validation et arrêt du VPN"]
  ACCEPT --> ENABLE["Ouvrir les nouvelles missions et les collectes documentaires"]
```

GitHub est la source de reconstruction du code et des données chiffrées. Les moyens de déchiffrement et l’accès initial à la cible existent hors GitHub. Un vol du dépôt seul ne doit pas fournir ces clés. Le build initial passe par Codex ; la release contient les manifests Kubernetes et l’automation Debian/K3s.

Les bindings et délégations protégées peuvent être restaurés, mais les droits actuels sont revérifiés ; certains coffres peuvent nécessiter un nouvel enrôlement. Ni VPN actif ni ancienne approbation d’écriture ne sont réactivés.

L’accès administrateur à la VM constitue une frontière de confiance : un ingénieur privilégié peut accéder aux données de l’hôte. Les contrôles de consultant ne protègent pas contre un administrateur root malveillant.

## 9. Carte des contrôles

| Frontière | Contrôle attendu | Preuve de recette |
|---|---|---|
| Entrée Internet → VM | TLS, session/OIDC ou validation SDK Teams selon endpoint | Accès non authentifié et callback falsifié refusés. |
| Identité → client | Autorisation serveur tenant + object_id + client + mission | Consultant non habilité refusé, y compris par API/fichier. |
| Client → connaissance | ACL avant résultats, citations et caches | Recherche croisée et accès direct à un objet refusés. |
| Agent → exécuteur | Opération typée, capacité limitée, plan exact | Shell libre et cible ajoutée refusés. |
| Exécuteur → VPN | Namespace, cibles autorisées et kill switch | Perte de tunnel bloque les flux, aucun rebond entreprise. |
| Consultant → secret | Binding individuel, droits du coffre et injection locale | Binding d’un autre consultant refusé ; secret absent des prompts. |
| Plateforme → cloud | Assainissement complet, fournisseur autorisé et absence de sortie directe | Payload brut, cache original et format inconnu bloqués. |
| Proposition → changement | Teams, empreinte, expiration et capacité unique | Rejeu, autre approbateur et plan modifié refusés. |
| Sauvegarde → GitHub | Chiffrement avant upload, clés externes | Restore réalisable par ingénieur autorisé ; dépôt seul insuffisant. |

Ces contrôles sont des objectifs de mise en œuvre et de test, pas des garanties déjà démontrées. Les diagrammes emploient des données fictives et ne contiennent aucun identifiant client réel.

## 10. Vue physique de la cible K3s et GitHub

```mermaid
flowchart TD
  DEV["Codex : rôle Platform Engineer"] --> GIT["GitHub : dépôt dédié du harness"]
  GIT --> DEP["Ansible et manifests épinglés"]
  DEP --> API["Endpoint API K3s privé avec bascule"]
  API --> N1["VM Debian 1 : serveur K3s et workloads"]
  API --> N2["VM Debian 2 : serveur K3s et workloads"]
  API --> N3["VM Debian 3 : serveur K3s et workloads"]
  N1 -.-> Q["etcd : quorum de trois serveurs"]
  N2 -.-> Q
  N3 -.-> Q
  N1 --> CSI["CSI vSphere : volumes persistants"]
  N2 --> CSI
  N3 --> CSI
  CSI --> DS["Datastore VMware partagé"]
  ENTRY["NAT HTTPS vers endpoint avec bascule"] --> ING["Ingress répliqué"]
  ING --> APP["Services métier et backends autorisés"]
  APP --> PG["PostgreSQL : réplication qualifiée"]
  APP --> H["Hermes : un propriétaire actif par état"]
  PG --> CSI
  H --> CSI
```

Proposition de départ : trois VM de 8 vCPU / 32 Go / 150 Go système, et 1 To partagé à ajuster selon la réplication et la volumétrie. Répartir les VM sur des hôtes ESXi distincts si disponibles ; le stockage partagé ne prouve pas à lui seul la tolérance aux pannes du datastore.

L’entrée et l’endpoint API doivent survivre à une panne de nœud. Leur mécanisme exact et le CSI sont qualifiés au préflight. Un runtime Hermes ne reçoit pas deux réplicas écrivant son état ; une reprise nécessite arrêt/fencing du précédent propriétaire. Les exécuteurs et tunnels VPN interrompus ne rejouent pas automatiquement les opérations client.

Le dépôt harness contient le code et les procédures. Les configurations privées et sauvegardes chiffrées restent dans leurs dépôts séparés ; les clés de récupération restent hors GitHub. Cette topologie complète les schémas logiques précédents et ne signifie pas que le cluster est déjà déployé.
