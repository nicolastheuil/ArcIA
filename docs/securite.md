# Sécurité et données privées dans ArcIA

Le socle est qualifié sur des données synthétiques. La [politique cloud](confidentialite-cloud.md) décrit le filtrage réellement déployé ; le [contrat de plateforme](plan-integration-hermes.md) décrit les contrôles à compléter avant données privées réelles et partage multi-utilisateur.

## Frontières actuelles

| Frontière | Contrôle | Limite |
|---|---|---|
| Administration SSH | Clés hôtes vérifiées hors bande, identité protégée, destinations désignées | Un administrateur root reste dans la frontière de confiance |
| Administration VMware | TLS contrôlé, compte technique et privilèges bornés | Permissions et inventaire privés |
| Secrets cluster | Chiffrement des Secrets K3s vérifié, montages distincts | Ne prouve pas le chiffrement de chaque disque/datastore |
| Entrée utilisateur | TLS, authentification locale scrypt, cookies sécurisés | Identité d’entreprise et révocation non intégrées |
| Runtime Hermes | Non-root, readonly, sans token SA ni socket d’administration | Un seul propriétaire de qualification |
| Réseau Hermes | Services internes autorisés, DNS sans forwarding, refus Internet et relais direct | Chaque nouveau connecteur exige sa recette |
| RAG | Scope serveur, FORCE RLS et rôle DB non propriétaire/non bypass | Deux scopes synthétiques ; agrégation selon identité à développer |
| Cloud | Presidio FR/EN, filtres techniques/secrets, enveloppe attestée, route gratuite ZDR | Faux négatifs possibles ; aucune garantie d’anonymat absolu |
| État Hermes | RWOP, replica unique, Recreate | Fencing sous panne brutale à qualifier |

## Secrets et preuves

Le contrôleur utilise DPAPI CurrentUser et ACL dans une racine privée hors Git/OneDrive. Get-ArcIAStateRoot retrouve aussi le LocalCache MSIX de Codex et refuse plusieurs états ambigus. Les wrappers déchiffrent dans leurs processus, transmettent les paramètres privés par stdin et rechiffrent les diagnostics. Le modèle ne reçoit que des codes, booléens et compteurs autorisés.

Ne pas afficher bundles, get secret, kubeconfigs, logs bruts, sessions, clés ou fichiers de credentials. La saisie se fait dans un programme local protégé. L’export portable convertit/chiffre l’état pour un autre compte ; il ne remplace pas les sauvegardes des bases et corpus.

## Autorité et données non fiables

Un document, un résultat MCP ou une réponse modèle peut contenir des instructions malveillantes. Les sources sont citées comme données, sans autorité sur les permissions. L’agent ne choisit pas son scope ni sa classification cloud. Un téléchargement autorisé n’autorise pas une exécution. Les schémas actifs, références distantes et formats opaques sont traités/refusés selon leur chemin.

Les futures actions externes exigeront permission serveur, plan immuable, approbation vérifiée et idempotence. Une perte de connexion impose réconciliation, jamais rejeu aveugle. Les intégrations d’instance ne peuvent pas ouvrir un accès fournisseur direct contournant la politique du socle.

## Partage, sauvegardes et production

Les connaissances communes doivent être accessibles uniquement aux personnes habilitées. Espaces restreints, historiques et connexions personnelles restent distincts. Le pilote actuel ne prouve pas encore ce modèle complet. [Contrat de partage](plateforme-arcia.md#partage-et-cloisonnement).

Code générique et exemples synthétiques dans le harness ; usages/configuration propres à l’organisation dans son dépôt d’instance ; données et sauvegardes sensibles chiffrées, clés externes. Un dépôt privé ne dispense pas du chiffrement. Réplication, stockage partagé et PV Retain ne sont pas des backups. [Reconstruction et limites](runbooks/sauvegarde-reconstruction.md).

La [sécurisation détaillée de la plateforme et des données](securisation-plateforme-donnees.md) relie chaque protection à sa frontière, sa recette et ses limites : sessions/révocation, corpus communs et personnels, outils, réseau, cloud, secrets, chiffrement et restauration.
