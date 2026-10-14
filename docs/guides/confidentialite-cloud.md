# ArcIA — confidentialité et modèles cloud

État du 12 octobre 2026 : **Presidio déployé dans K3s, Hermes raccordé et réponse cloud gratuite obtenue sur fixture synthétique**. Les refus réseau et payloads non autorisés sont testés. Cela ne qualifie ni l’ingestion de données confidentielles réelles ni l’IAM multi-utilisateur.

## Règles du harness et choix d’instance

Par défaut, **tous les modèles cloud passent par Presidio**, indépendamment du
fournisseur et du prix. Chaque instance choisit modèles, fournisseurs, budgets,
ZDR, collecte et résidence ; gratuité et ZDR ne définissent pas le harness.
Ces paramètres sont imposés côté serveur, pas par une instruction de l’agent.

Une route Ollama ou vLLM interne à l’entreprise ne passe pas par Presidio par
défaut. Son endpoint est déclaré et autorisé par l’instance ; identité, droits
documentaires, isolation et contrôle de destination continuent de s’appliquer.
Un repli vers un modèle cloud reprend le filtrage Presidio et la politique cloud.
Le filtrage local peut devenir une exigence d’instance si l’organisation le décide.

Le parcours cloud via OmniRoute est déployé, avec sélection serveur du pool
et du mode administré, filtrage Presidio et clés techniques restreintes. Sa
recette vérifie les droits et le filtrage sur fixtures ; elle n'appelle aucun
fournisseur. Les connexions et modèles réels doivent être configurés par
l'administrateur. Les routes internes Ollama/vLLM restent à intégrer/qualifier.
[Guide et preuve OmniRoute](omniroute.md).

## Chemin cloud générique déployé

Hermes appelle `omniroute.arcia-routing.svc.cluster.local:20131/v1` avec son token
de périmètre. Le gateway lit le binding issuer/subject et les rôles courants,
sélectionne le pool et impose le mode auto administré. Il appelle le filtre
local authentifié `/v1/sanitize-completion` ; le contenu assaini est ensuite
transmis à OmniRoute uniquement sur loopback, avec une clé limitée aux
connexions et modèles choisis, sans scope de gestion, logs ou cache partagé.
Aucun prompt, navigateur ou agent ne choisit un endpoint ou une clé fournisseur.

Le relais historique `cloud-egress` reste distinct : son parcours OpenRouter
free/ZDR, attesté par HMAC, a été qualifié le 12 octobre. Il conserve sa politique
propre ; le service Presidio n'impose pas cette politique tarifaire au gateway
générique. Les clés fournisseurs restent dans le stockage natif OmniRoute ;
Hermes et Presidio n'en possèdent aucune.

NetworkPolicies interdisent à Hermes Internet, le relais direct et le DNS général. Un serveur DNS statique ne répond qu’aux services internes autorisés et ne transmet aucune requête externe. Les privilèges d’installation publique sont limités au Job de construction du runtime ; les modèles spaCy restent locaux et leur volume est monté readonly au runtime.

## Filtres présents

| Couche | Traitement |
|---|---|
| Presidio + spaCy FR/EN | Détection dans les deux langues, noms/personnes/organisations/lieux et reconnaisseurs structurés disponibles |
| Secrets | Clés privées, mots de passe, tokens, API keys, Bearer, JWT et motifs de clés connus : suppression irréversible |
| Infrastructure | IPv4/IPv6, réseaux, MAC, UUID, FQDN et noms d’hôtes usuels |
| Dictionnaire serveur | Identifiants privés connus d’un périmètre ; exemples synthétiques dans le pilote |
| Pseudonymisation | HMAC stable dans un même scope, différent entre scopes ; aucune table de correspondance brute persistée |
| Payload complet | Messages système/utilisateur, historique, extraits RAG, résultats d’outils, définitions et arguments JSON, métadonnées autorisées |
| Contrôles de forme | Taille, profondeur, types, champs autorisés, résidus structurés, caractères invisibles et identifiants de protocole |
| Refus explicites | Images, fichiers binaires/base64, contenu opaque, schémas/options non pris en charge, tentative d’override fournisseur |

Un identifiant de protocole contenant une donnée détectée provoque un refus. Les clés de schéma sensibles sont refusées plutôt que renommées silencieusement. Les champs de texte et arguments sont assainis avant export. Sur le relais historique, une signature incorrecte, un nonce rejoué ou une enveloppe expirée est refusé.

Le service expose `/v1/sanitize` pour un aperçu local et `/v1/sanitize-completion` pour le gateway authentifié : leurs résultats ne constituent pas une permission autonome d'export. Les prix et modèles du parcours générique relèvent de l'instance. Les anciennes routes `/v1/chat/completions` et `/v1/models` de Privacy restent spécialisées pour la recette gratuite ; les autres routes sont refusées.

## Fournisseur et budget du pilote

Le pilote fixe `model=openrouter/free`, `data_collection=deny`, `zdr=true`, `require_parameters=true`, `allow_fallbacks=false` et `max_price` à zéro pour prompt, completion, request et image. Les sorties sont plafonnées à 2 048 tokens. L’appelant ne peut pas choisir un modèle payant, changer ces paramètres ni ajouter une destination. [Politique officielle OpenRouter](https://openrouter.ai/docs/guides/routing/provider-selection).

Une indisponibilité, un quota gratuit ou l’absence de fournisseur conforme produit un refus ; aucune seconde route payante n’est activée. La disponibilité des modèles gratuits peut changer entre deux requêtes. Le contrôle du coût retourné détecte une incohérence ; le plafond de prix est envoyé avant génération, ce n’est pas une garantie financière indépendante du fournisseur.

OmniRoute est le premier routeur du parcours générique, en mode auto administré.
Le pool initial reste vide et les overrides désactivés. Une autre instance choisit
ses abonnements, modèles, budgets et conditions. La recette de ce lot ne vérifie
pas de débit réel, quota fournisseur ou coût ; ces vérifications restent à
exécuter après configuration explicite. [Configuration et droits](omniroute.md).

## Classification et limites

Les tokens de qualification sont liés côté serveur au scope synthétique. Les classes confidentielles ne sont pas activées pour le cloud. Ne pas monter de nouveaux corpus privés dans ce runtime sous prétexte que Presidio est présent : l’identité, les ACL et la classification doivent d’abord être qualifiées.

Presidio peut manquer une donnée sensible. Une information confidentielle sans nom propre, une paraphrase ou une combinaison de faits peut être reconnaissable. Les filtres actuels n’assurent pas une anonymisation exhaustive ; une classe trop sensible reste locale/refusée. Les petits modèles FR/EN exigent un benchmark avec des jeux représentatifs et des dictionnaires d’instance avant ouverture. [Limites Presidio](https://github.com/data-privacy-stack/presidio/blob/main/docs/faq.md).

ZDR et l’interdiction de collecte sont des contraintes de routage fournisseur, pas une attestation indépendante de ses pratiques ni une garantie de résidence UE. Le routage régional OpenRouter relève d’offres spécifiques ; il n’est pas activé ici. Les métadonnées techniques du fournisseur restent soumises à ses conditions. Les contrats et restrictions de chaque instance doivent être validés avant données réelles.

Les requêtes à un MCP externe, navigateur, outil web, télémétrie ou récupération de cache sont aussi des sorties. Elles ne passent pas magiquement par le filtre LLM. Context7 est donc bloqué pour les requêtes externes ; l’ajout d’un MCP externe exige sa recette propre. Les originaux, embeddings et assets Knowledge restent locaux. Les réponses cloud n’autorisent aucune action externe par elles-mêmes.

## Installation et recette

Presidio Analyzer/Anonymizer **2.2.364**, spaCy **3.8.16**, modèles FR/EN **3.8.0** ; wheels et modèles fixés par hashes. Les scripts ne les installent pas sur le poste. [Sources](../../services/privacy) · [Rendu K3s](../../scripts/privacy_deploy.py) · [Worker contrôlé](../../scripts/node_privacy.py).

```powershell
./scripts/Invoke-ClusterFoundation.ps1 -Action install_privacy
./scripts/Invoke-ClusterFoundation.ps1 -Action install_hermes
./scripts/Invoke-ClusterFoundation.ps1 -Action verify_privacy
./scripts/Invoke-ClusterFoundation.ps1 -Action inspect_privacy
```

Préférer le [bootstrap](../runbooks/bootstrap.md) qui ordonne ces étapes avec les autres composants. `verify_privacy` exécute des fixtures synthétiques dans Hermes et restitue uniquement les résultats, codes et booléens. Il distingue la réussite des contrôles de la disponibilité instantanée d’une complétion gratuite. La preuve d’une réponse effectivement obtenue est enregistrée séparément, sans son contenu. Les tests unitaires adverses ne nécessitent pas Presidio installé sur le contrôleur.
