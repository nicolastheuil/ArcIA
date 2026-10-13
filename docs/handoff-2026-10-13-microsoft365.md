# Handoff — préparation Microsoft 365, 13 octobre 2026

## Livraison et limites

Demande : une annexe à remettre à l'administrateur Microsoft, et une
configuration YAML non confidentielle dans le dépôt arcia-arcitek.

Annexe : `docs/annexes/integration-microsoft365.md`, titre **Intégration
Microsoft365**. Sources Microsoft officielles consultées le 13 octobre 2026 ;
Entra/OIDC, rôles administratifs, bot personnel/SSO, artefacts de réunions,
SharePoint Sites.Selected et Outlook délégué/RBAC Exchange, recettes et retrait.
ADR 0015, index, runbook et backlog actualisés.

Contrat v1 : gabarit YAML, JSON Schema strict, validate/plan hors ligne et
9 tests de frontières. Le YAML d'instance reprend le gabarit inactif ; aucune
valeur réelle du tenant, secret ou donnée privée importée. Le bootstrap
d'instance exige le checkout à la révision du harness fixée dans son dépôt.

Bootstrap harness : `configuration_contracts.microsoft365` et lock d'artefacts
normalisés UTF-8/LF ; `versions.lock.yaml` indique `enabled=false` et
`runtime_implemented=false`. Couverture/Plan exposent ce statut. Aucun nouveau
service, credential runtime obligatoire ou contact Microsoft n'est ajouté.
Les identités, données et volumes existants ne sont pas modifiés.

## Vérifications exécutées localement

- 9 tests Microsoft 365 réussis : configuration inactive, champs secrets/droits
  globaux/écritures refusés, identité bot liée, IDs de ressources obligatoires,
  YAML hostile/ambigu/trop grand refusé, aucune valeur d'entrée en sortie.
- 5 tests bootstrap Python réussis ; couverture de 43 étapes vérifiée avec
  contrôle des hashes et validation du gabarit.
- Test Bootstrap PowerShell réussi, incluant le refus d'un contrat M365 activé.
- Bootstrap-Harness Plan Fresh exécuté, sans accès cible ; contrat M365 visible.
- validate_sources exécuté sous Windows : YAML/schémas, manifests et locks OK.
- Plan du YAML arcia-arcitek exécuté : 54 éléments administratifs manquants,
  runtime et tenant_contacted faux, aucun secret résolu.
- Suite Windows générale avant ajout du neuvième test : 159 tests, 151 réussis,
  7 ignorés (SDK VMware/ISO/OpenSSL absents de cet interpréteur), 1 erreur dans
  `test_failed_peer_connection_is_not_qualified` : lecture Linux
  `/etc/resolv.conf` sous Windows. Les deux fichiers concernés sont inchangés
  par ce lot. Cette exécution n'est pas annoncée verte ; la CI Linux reste
  l'autorité pour la suite complète. Consulter les checks GitHub du commit publié.

## À reprendre

L'admin doit remplir la fiche du tenant, créer les objets/consentements/grants
et remettre ses preuves privées. Le validateur ne vérifie pas ces faits sur
Microsoft. Wizard/importeur protégé, adaptateurs OIDC/Bot/Graph, IAM/ACL,
approbations, renouvellement et réconciliation restent à implémenter et
qualifier synthétiquement. Toute activation est refusée par le contrat v1.
L'ancien Configure-Integrations ne consomme pas le YAML et suggère encore
l'endpoint bot sur le domaine portail : le corriger lors de l'intégration,
sans écraser les valeurs protégées existantes. Aucun déploiement tenant,
réapplication K3s ou rebuild neuf n'est revendiqué ici.
