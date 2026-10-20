# Capacités natives d'agentgateway et portes de qualification

Décision du 20 octobre 2026 : **agentgateway OSS remplace LiteLLM dans la cible v0.7**. Le [contrat applicatif](../v0.7/contrat-applicatif.md) gouverne les interfaces. Les [anciennes capacités LiteLLM](gateway-capabilities-legacy-litellm.md) et [preuves datées](../v0.7/verification.md) restent historiques.

## Version et périmètre

- Dernière stable officielle vérifiée : [v1.6.0](https://github.com/agentgateway/agentgateway/releases/tag/v1.6.0), publiée le 2 octobre 2026 ; [source épinglée](https://github.com/agentgateway/agentgateway/tree/ea5608642b9d5c94c5baf5fd9f2f9849b808e963).
- Image officielle `ghcr.io/agentgateway/agentgateway:v1.6.0`, digest OCI `sha256:9d3e6044ddcdc0878b1787f77bd401252b95e22684203fb5e874c4c42d2ed90c` ; Linux amd64/arm64. Le tag sans `v` n'existe pas.
- Licence du socle : [Apache 2.0](https://github.com/agentgateway/agentgateway/blob/ea5608642b9d5c94c5baf5fd9f2f9849b808e963/LICENSE). Aucun achat d'une offre Enterprise n'est présumé.
- Le [schéma exact](https://github.com/agentgateway/agentgateway/blob/ea5608642b9d5c94c5baf5fd9f2f9849b808e963/schema/config.json) fait référence ; ne pas recopier une option de la documentation courante sans vérifier sa présence dans cette version.

Première porte exécutée le 20 octobre : bootstrap fermé et 13 cas HTTP JWT/CEL réussis sur le cluster existant ; nettoyage vérifié. Voir les [preuves et limites](../v0.7/verification.md). Toutes les autres capacités restent à qualifier.

## Matrice native

| Capacité | Contrat de qualification |
|---|---|
| Bootstrap fermé | Configuration déclarative, refus avant tout backend, sans clé fournisseur ; DenyAll et aucune identité Kubernetes dans le pod |
| JWT et CEL | `jwtAuth.mode: strict`, émetteur, audience et claims requis ; deux identités, absence de token, falsification, expiration, audience/émetteur erronés et refus croisés |
| Entra/Open-WebUI | Jeton destiné à la bonne API ; groupe overage, expiration/refresh et révocation réels. Un test avec émetteur synthétique ne qualifie pas Entra |
| Inférence LLM | OpenAI-compatible, aliases libres, fournisseurs retenus, streaming, erreurs et réapplication ; aucune API de clés virtuelles LiteLLM supposée |
| Presidio | Adaptation du webhook natif request/response vers le bouclier ArcIA, pseudonymisation, panne fail-closed et formats couverts explicitement |
| MCP | Catalogue filtré et invocation selon identité, droits documentaires côté source, révocation et isolation des serveurs |
| A2A/Hermes | Cartes, tâches et bindings privés ; le support protocolaire ne prouve pas le pont Chat Completions ni sa continuité de contexte |
| Artefacts | CSV exact téléchargeable dans WebUI, refus entre comptes/tenants et accès après restart, sur le nouveau transport |
| Budgets et routage | Primitives OSS observées, plafonds effectifs, concurrence et destinations admissibles ; pas d'Auto Router LiteLLM transposé |
| Reprise | Configuration, droits et opérations restaurables ; pas de base agentgateway déduite de la base LiteLLM historique |

Le registre distingue cible et qualification. Aucun résultat antérieur LiteLLM n'est transféré à cette matrice. Le rapport machine conserve `qualified: false` pour les capacités non éprouvées et `activation_allowed: false` tant que le contrat complet n'est pas recetté.

## Première recette reproductible

```bash
python scripts/qualify_gateway_stack.py --config arcia.config.yaml --report artifacts/agentgateway-qualification.json
```

Cette première porte déploie le vrai binaire agentgateway et un témoin HTTP dans un namespace à nonce. Elle vérifie le bootstrap fermé puis JWT/CEL avec des clés RSA synthétiques, sans donnée d'instance, fournisseur cloud, PVC ou migration. Le témoin ne constitue ni un LLM, ni Hermes, ni un serveur MCP.

La configuration privée sert uniquement à joindre le cluster existant. Une identité administrée ArcIA synthétique figure dans les claims ; les headers de tenant/utilisateur servent à éprouver les refus, jamais à créer une autorité. Le rapport expose uniquement statuts, compteurs, références de code et résultat de nettoyage ; aucun jeton ou clé privée.

`passed` signifie que cette porte limitée réussit, pas que la plateforme est installable. Vérifier aussi `cleanup_verified` et les capacités non testées. Une panne de connexion ou de workload garde la recette en échec. Le script contrôle le nonce avant mutation et suppression ; seul son namespace peut être nettoyé.

Les recettes suivantes du [lot 01](../v0.7/lots.md) couvrent LLM/Presidio réels, MCP, A2A et artefacts. Le déploiement global sélectionnant agentgateway reste refusé avant parité et migration, au lieu d'installer LiteLLM par repli.
