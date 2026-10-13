# Handoff de fin de session — 13 octobre 2026

Session arrêtée à la demande du propriétaire. Aucune opération
d'infrastructure, création Azure ou tâche automatique ne doit continuer
ce soir. La plateforme reste en service ; cet arrêt concerne le travail
d'ingénierie, pas les services déployés.

## Référence livrée et vérification

Dépôt `nicolastheuil/arcia-harness`, branche `main`, révision fonctionnelle
publiée `1361605df979324ceb7cdd433af50b189f474b90`.
[CI de cette révision terminée avec succès](https://github.com/nicolastheuil/arcia-harness/actions/runs/38449813937).
Ce handoff ajoute seulement une clôture documentaire à cette révision.

Validation locale exécutée : 222 tests Python, 220 réussis, deux ignorés ;
contrôles PowerShell du bootstrap et validation des sources réussis.
Le manifeste de qualification contient 56 étapes. Les réapplications ciblées
sur le cluster existant ont été vérifiées ; aucun rebuild VMware neuf,
restore complet ou test de charge de trente utilisateurs n'est revendiqué.

Lire le [handoff technique courant](handoff-2026-10-13-identity-public-https.md)
et sa [preuve assainie](qualification/2026-10-13-identity-public-https.json).
Les handoffs plus anciens conservent leurs résultats historiques ; leurs
mentions « correction en attente », snapshot IP ou capacité huit ne décrivent
plus la cible actuelle.

## État laissé en service

- Microsoft : connexion déclarée fonctionnelle par le propriétaire ; le
  compte fédéré observé possède `ArcIA.User` et un espace personnel.
- Admission : mapper du seul fournisseur Microsoft et du tenant vérifié,
  rôle `ArcIA.User`, synchronisation FORCE. Aucun rôle administrateur accordé
  automatiquement aux collaborateurs. Les comptes locaux restent disponibles.
- Administration : le compte local nommé `admin` a récupéré le rôle effectif
  `realm-management.realm-admin`, relu côté serveur. Aucun reset password/MFA.
- Réseau : Keycloak seul dispose d'une sortie IPv4 publique TCP/443, filtrage
  des destinations au pare-feu amont. L'ancienne liste Microsoft `/32` est
  retirée fonctionnellement. Les réseaux privés/cluster restent exclus de
  cette nouvelle règle ; Hermes n'obtient pas d'Internet arbitraire.
- Tests réseau : DNS courant, TLS Microsoft/Graph 4/4, REJECT Keycloak +0,
  HTTPS vers une autre destination publique réussi, HTTP/80 refusé,
  PostgreSQL accessible. IPv6 reste sans route et non qualifié.
- Portail : une réplique prête, pool de 32 places, trois liées et 29 libres.
  Une place liée à un compte actif ; deux liées à des comptes présents mais
  désactivés, volontairement conservées. Places supplémentaires dormantes.
- Nettoyage : l'unique espace d'un compte supprimé, ses deux PVC et ses deux
  PV ont été supprimés. La place a été recréée vide avec de nouveaux objets.
  Les bindings et volumes restants ont été contrôlés et préservés.

Les vérifications serveur ne remplacent pas une recette interactive de la
console admin, des invités, du refus d'un autre tenant ou de la concurrence.
Un ancien « OAuth state mismatch (CSRF check failed) » sur le premier PC
appelle un nouveau parcours depuis l'accueil, sans désactiver CSRF.

## Autorisations consommées et état protégé

Exceptions humaines limitées : réparation réseau initiale ; récupération du
compte admin nommé et admission utilisateur du tenant ; nettoyage de l'unique
espace du compte supprimé, données comprises. La sortie HTTPS publique a été
demandée explicitement. Ces décisions ne valent pas approbation générale des
futures élévations ou suppressions. Le mécanisme d'approbation Teams côté
serveur n'existe pas encore ; aucune vérification Teams n'est revendiquée.

Entrées privées sous DPAPI/ACL, à retrouver avec `Get-ArcIAStateRoot -Identity`
sans afficher les bundles : instance et opération VMware, confiance SSH,
identité et certificat, `identity-access-policy.dpapi`, résultats des actions
cluster et diagnostics. L'instance conserve `https_egress_mode=public_ipv4_443`
et `personal_slots=32`. Le harness générique garde ses défauts fermés et huit
places ; les personnalisations restent dans l'instance protégée.

Les anciens plans sont expirables et liés aux UID. **Ne pas rejouer le plan
de nettoyage** : l'ancien namespace et ses volumes ont disparu, la place
actuelle est neuve. Un nouvel effacement exige un nouveau plan et son
autorisation. Ne jamais forcer les finalizers CSI pour accélérer une reprise.

Des fichiers locaux non suivis existaient avant ce lot (diagnostics, wrappers
K3s et brouillons documentaires). Ils n'ont été ni supprimés ni inclus dans la
livraison. Les conserver et les examiner séparément avant tout ajout Git.

## Ordre de reprise à la prochaine session

1. Relire `AGENTS.md`, les trois documents d'architecture qu'il impose,
   ce handoff et l'état de reprise. Vérifier `main` et l'état Git sans intégrer
   automatiquement les fichiers non suivis.
2. Faire des lectures de contrôle via `inspect_identity_microsoft_egress`,
   `inspect_identity_access_policy` et `inspect_personal_portal` avec le
   transport protégé de la cible possédée. Aucun apply global nécessaire
   pour reprendre simplement l'inventaire.
3. Confirmer avec le propriétaire l'accès interactif de son compte local
   administrateur et l'accès utilisateur Microsoft. En cas de refus de la
   console pour un simple utilisateur Microsoft, ne pas lui attribuer
   automatiquement des privilèges administratifs.
4. Reprendre la création complète du bot Teams : le propriétaire a supprimé
   les anciens objets et demande de tout recréer. **Aucune ressource Azure
   Bot, aucun canal ni package Teams n'a été créé.** Les anciens credentials
   enregistrés ne prouvent pas l'existence ou la validité d'un bot.
5. Enrôler par programme local protégé l'identité administrative Azure
   nominative et la cible de souscription/groupe de ressources/région ; ne
   demander aucun secret dans le chat. Vérifier aussi l'exposition HTTPS du
   hostname bot distinct du portail avant de promettre sa disponibilité.
   Préparer un plan de création précis et le récepteur avant l'approbation
   des actions externes à risque. Garder les credentials du bot hors Hermes.
6. Compléter ensuite les recettes tenant/Teams et la capacité simultanée,
   puis les gates de release : rebuild neuf, sauvegarde/restauration et
   disponibilité. Ne pas confondre CI synthétique verte et recette VMware.

Aucune reprise programmée : attendre la demande du propriétaire.
