# Handoff — blocage réseau du broker Microsoft

13 octobre 2026. Complément au
[parcours accompagné](annexes/microsoft365-parcours-accompagne.md).

## Preuves exécutées

Inspection en lecture seule via le transport SSH existant : identité nominative
protégée, clés d'hôte vérifiées et contrôle d'appartenance du Deployment Keycloak
à l'opération. Aucun secret, identifiant privé ou journal brut rendu au modèle.
Les journaux et politiques détaillés sont conservés dans
`m365-broker-diagnostic.dpapi` sous la racine privée hors dépôt.

- Keycloak : une réplique disponible.
- Échantillon : trente minutes, au plus 1 500 lignes.
- Deux événements d'erreur broker.
- Stack du callback OAuth, hôte Microsoft de login et
  `java.net.SocketException: Network is unreachable` présents.
- Deux NetworkPolicies sélectionnent Keycloak ; aucune règle de sortie TCP/443.
- Aucun code AADSTS ni marqueur `invalid_client` trouvé dans l'échantillon.

Le code `scripts/identity_deploy.py` prévoit DNS/PostgreSQL, sans sortie Microsoft.
Ces preuves établissent un échec réseau lors du callback et un manque dans les
règles de sortie. Elles ne qualifient ni le secret, ni Graph, ni la liaison de
comptes. Une cause réseau supplémentaire, notamment IPv6/routage, reste à
écarter lors de la recette de connectivité après correction.

## Plan proposé, non appliqué

1. Inventorier le fournisseur effectivement configuré sans exposer sa
   représentation privée : Microsoft prédéfini ou OIDC, tenant spécifique,
   alias et présence du credential. Préserver son identité et les liaisons.
2. Préparer une sortie HTTPS de Keycloak par un mécanisme bornant les noms de
   destination, de préférence le proxy de sortie administré de l'organisation
   s'il existe. Destinations proposées : `login.microsoftonline.com:443` pour
   les tokens et `graph.microsoft.com:443` si le fournisseur Microsoft appelle
   `/me`. Aucun wildcard ni désactivation de la validation TLS.
3. Garder le deny-all. N'autoriser le Pod Keycloak qu'à joindre le proxy
   sélectionné ; le proxy impose l'allowlist. Une simple ouverture TCP/443
   vers toutes les IP ne satisfait pas ce plan. Une NetworkPolicy standard
   n'accepte pas de noms DNS comme destinations.
4. Toute implémentation de proxy/service ou configuration effective doit
   actualiser le rendu, les versions/digests, les locks, la couverture, le
   bootstrap, le runbook et le handoff avant déploiement. Ne pas réappliquer
   aveuglément les autres changements de travail présents dans le checkout.
5. Préparer le diff/plan immuable et obtenir l'approbation vérifiée côté serveur
   requise pour l'ouverture réseau. Le service d'approbations Teams est décrit
   au backlog comme non livré ; aucune approbation valide n'est revendiquée.
6. Après approbation, appliquer uniquement les ressources possédées désignées.
   Vérifier TLS et connectivité depuis Keycloak, refus d'une destination hors
   liste, absence d'Internet direct, préservation des comptes/volumes et accès
   local. Puis faire retester la connexion Microsoft par l'utilisateur.
7. Requalifier issuer/tenant, liaison contrôlée, identité stable, utilisateur
   interdit et révocation avant toute ouverture de données réelles.

Le choix du proxy, ses adresses et ses éventuels credentials sont à collecter
par un programme local protégé. Aucun contournement de l'approbation serveur
par une simple réponse dans le chat.

## État de reprise

Diagnostic exécuté, preuve brute chiffrée, documentation mise à jour.
Plan proposé uniquement ; aucune règle réseau, application Entra, permission,
credential ou ressource runtime modifiée par ce diagnostic. Aucun nouveau test
de connexion Microsoft, aucune réapplication ni reconstruction exécutés.

La prochaine étape nécessite le mécanisme de sortie retenu et la validation
serveur. Ne pas demander à l'utilisateur de recréer l'application Entra pour
résoudre cet échec réseau.
