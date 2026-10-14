# ArcIA — confidentialité et modèles cloud

État du 12 octobre 2026 : **Presidio déployé dans K3s, Hermes raccordé et réponse cloud gratuite obtenue sur fixture synthétique**. Les refus réseau et payloads non autorisés sont testés. Cela ne qualifie ni l’ingestion de données confidentielles réelles ni l’IAM multi-utilisateur.

## Chemin obligatoire

Hermes appelle `privacy.arcia-privacy.svc.cluster.local:8091/v1` avec un token local. Presidio assainit le contenu puis signe une enveloppe HMAC, avec timestamp et nonce. Le service `cloud-egress` accepte cette enveloppe uniquement depuis le Pod Privacy et appelle le seul endpoint TLS OpenRouter prévu. La clé OpenRouter est montée uniquement dans le relais ; elle n’est ni dans Hermes ni dans le service Presidio. Les deux processus n’enregistrent pas les corps ni les en-têtes d’authentification.

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

Un identifiant de protocole contenant une donnée détectée provoque un refus. Les clés de schéma sensibles sont refusées plutôt que renommées silencieusement. Les champs de texte et arguments sont assainis avant l’attestation ; une signature incorrecte, un nonce rejoué ou une enveloppe expirée est refusé par le relais.

Le service expose `/v1/sanitize` pour un aperçu local : ce résultat ne constitue pas une permission cloud. `/v1/chat/completions` applique ensuite une politique serveur indépendante. `/v1/models` expose uniquement le modèle autorisé ; les autres routes sont refusées.

## Fournisseur et budget

Le pilote fixe `model=openrouter/free`, `data_collection=deny`, `zdr=true`, `require_parameters=true`, `allow_fallbacks=false` et `max_price` à zéro pour prompt, completion, request et image. Les sorties sont plafonnées à 2 048 tokens. L’appelant ne peut pas choisir un modèle payant, changer ces paramètres ni ajouter une destination. [Politique officielle OpenRouter](https://openrouter.ai/docs/guides/routing/provider-selection).

Une indisponibilité, un quota gratuit ou l’absence de fournisseur conforme produit un refus ; aucune seconde route payante n’est activée. La disponibilité des modèles gratuits peut changer entre deux requêtes. Le contrôle du coût retourné détecte une incohérence ; le plafond de prix est envoyé avant génération, ce n’est pas une garantie financière indépendante du fournisseur.

La cible OmniRoute automatique → OpenRouter free → OpenRouter auto est documentée, mais seul le chemin gratuit filtré est activé. Pour OmniRoute, il faudra qualifier son choix de providers, ses caches, ses retries et son accès au relais sans perte d’attestation ou élargissement de politique. L’étage payant demande une autorisation et un budget persisté avant activation.

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
