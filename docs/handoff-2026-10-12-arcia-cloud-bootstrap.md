# Reprise ArcIA — bootstrap, confidentialité et périmètre générique

## Décisions à conserver

Plateforme **ArcIA**, dépôt **arcia-harness**, moteur d’agents **Hermes**. Socle générique uniquement : usages, corpus, domaines, comptes, connecteurs et surcharges propres à une organisation dans son dépôt d’instance. Ce dépôt existe désormais, privé et initialisé sur main ; il ne contient aucun secret ou corpus privé importé.

Livrer directement sur main, sans branche. Tous les outils applicatifs tournent dans K3s, jamais sur le poste. Secrets et diagnostics complets restent dans les programmes/états protégés ; ne pas lire les scripts de debug privés non suivis.

## Codé et déployé

Bootstrap ordonné avec profils Plan/Fresh/Reconcile/Verify/Audit, coverage CI, runtime administratif hashé, résolution de la racine DPAPI/MSIX, protection SSH et gate TLS. Hermes minimal évite le cycle de dépendance des outils et MCP ; la réconciliation ne rétrograde pas une instance existante.

Presidio 2.2.364 et spaCy 3.8.16 avec modèles FR/EN 3.8.0 installés dans le cluster. Gateway privée, relais distinct avec clé OpenRouter, attestation HMAC/anti-rejeu, politique gratuite seule et DNS statique sans forwarding dans Hermes. Context7 externe est fermé. La configuration Hermes est montée depuis une ConfigMap immuable par hash pour éviter une projection obsolète pendant le rollout.

Documentation produit refondue : README capacités/outils/RAG/MCP/partage, périmètre d’instance, schémas génériques, confidentialité, bootstrap et guides. Les anciens documents de cadrage propres à l’usage initial sont archivés dans le dépôt d’instance.

## Vérifié réellement

Un Audit et un Reconcile complet ont réussi sur le cluster existant. Le dernier Reconcile inclut Privacy : 23 étapes sélectionnées réussies avant ajout des deux étapes multi-utilisateur. Knowledge : 25 contrôles synthétiques ; outils : 21 sondes ; HTTPS/auth : 7 contrôles. Les nouveaux contrôles Privacy vérifient payload complet, secrets retirés, images/options/payants/anonymes refusés, DNS interne, DNS externe/Internet/relais direct refusés, absence de clé fournisseur dans Hermes et configuration de la passerelle. Une réponse cloud gratuite HTTP 200 a été obtenue avec ZDR et prix nul sur fixture synthétique. La disponibilité gratuite peut varier d’une requête à l’autre.

Les tests unitaires Privacy adverses ne nécessitent aucune installation applicative sur le contrôleur. Le dernier résultat et les preuves cloud sans contenu sont conservés dans les statuts protégés et une ConfigMap de preuve publique assainie. Ne jamais annoncer la disponibilité d’un modèle à partir du seul healthcheck.

## Qualification multi-utilisateur locale

Deux identités et runtimes synthétiques déployés, quatre PVC d’état/outillage distincts, authentification locale et corpus commun + personnels sous FORCE RLS. La recette exécutée a réussi 90 contrôles : recherches/downloads/écritures, scopes imposés, sessions/messages/exports/modifications, refus de cookies croisés, en-têtes usurpés, accès concurrents, HTML/assets du dashboard, états après restart, outils readonly, absence de clés fournisseur/ServiceAccount, refus réseau et pseudonymes séparés. Le rejeu de cookie et de bearer après logout est refusé.

Le test a révélé le rejeu possible après déconnexion native ; une frontière ASGI du harness conserve les empreintes révoquées dans un registre durable propre à chaque runtime. Code Hermes épinglé inchangé. Voir [ADR 0013](adr/0013-qualification-multi-utilisateur.md), [recette locale](multi-utilisateur.md) et [sécurisation expliquée](securisation-plateforme-donnees.md). Les 129 tests unitaires Linux sont passés, ainsi que les gardes bootstrap PowerShell et la validation des sources.

Le bootstrap compte 43 étapes, dont installation et vérification multi-utilisateur. La réconciliation finale a réussi ses 25 étapes sur le cluster existant. Le code est livré directement sur main dans `dcd06b4018633c676684d08868671d93698b02ef` ; [CI verte, tests et schémas](https://github.com/nicolastheuil/arcia-harness/actions/runs/38312788196). Le journal Apply a été commencé sur la copie de travail avant ce commit ; un Verify à la révision publiée a réussi ses 7 étapes et reproduit les 90 contrôles multi-utilisateur. Ne pas confondre cette recette locale avec l’IAM d’entreprise : SSO/groupes/provisioning, connexions déjà ouvertes et données confidentielles réelles restent hors qualification.

## Gates restant indépendantes

Rebuild sur cluster neuf, sauvegarde/restauration cohérente des bases et corpus, perte brutale/fencing, compatibilité/support des versions, paquets système incomplets, renouvellement DNS automatique et migration du compte ACME. Pas de release de production déclarée. Le bootstrap reconstruit le logiciel avec ses entrées protégées ; il ne ressuscite pas des données sans backup.

La cible de routage future est OmniRoute automatique → OpenRouter free → OpenRouter auto. Seul le gratuit est autorisé pour la qualification ; aucun recours payant ne doit être introduit implicitement. Les connecteurs HubSpot/SharePoint du README sont des exemples documentés, pas des intégrations déjà installées.

## Preuves et accès

Les [preuves assainies datées](qualification/2026-10-12-synthetique.json) récapitulent les contrôles sans identifiants privés ni contenu de requêtes. Le [README](../README.md) renvoie aux documents complets. `Show-PilotAccess.ps1 -User A` et `-User B` affichent localement les accès, sans secret dans le chat ; le second espace utilise le chemin `/qualification-b/` du même domaine. Le dépôt d’instance privé existe sur main et fixe une révision du harness ; les customisations restent à démarrer.
