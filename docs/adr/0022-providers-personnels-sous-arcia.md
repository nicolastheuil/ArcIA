# ADR 0022 — Fournisseurs personnels sous les contrôles ArcIA

Décision du propriétaire le 14 octobre 2026 : les providers personnels sont
des destinations supplémentaires d'ArcIA, en parallèle d'OmniRoute. Ils doivent
bénéficier de Presidio et des autres fonctionnalités et politiques de la
plateforme. La configuration personnelle ne crée pas une sortie libre depuis
Hermes. Ce contrat de raccordement reste à implémenter et qualifier.

Le chemin cible est `Hermes personnel → passerelle ArcIA → destination autorisée`.
La passerelle reçoit un contexte d'identité serveur, applique droits, classe de
route, quotas/budgets et filtrage cloud, puis choisit :

- la route d'entreprise vers OmniRoute mutualisé, selon la configuration admin ;
- une route personnelle vers un provider déclaré et lié au propriétaire dans
  ArcIA, avec clé API ou OAuth supporté, sans import dans OmniRoute central.

Presidio précède tout export cloud, quelle que soit la destination. Documents,
mémoire, outils et autres capacités restent celles de l'espace ArcIA/Hermes du
propriétaire. Un fournisseur personnel ne supprime aucun contrôle d'accès,
approbation métier applicable, restriction de sortie ou limite d'instance. Les
fonctions de plateforme encore absentes ne sont pas déclarées opérationnelles.

Le rôle `ArcIA.ProviderSelfService` demeure requis, avec `ArcIA.User` et
révalidation serveur. Les credentials restent dans le stockage chiffré du
service ArcIA et ne sont pas rendus au modèle. Aucun endpoint libre ni jeton
lisible par les outils de l'agent n'est placé dans la configuration Hermes.

L'administrateur du dashboard OmniRoute ne gère pas ces connexions personnelles
et n'y voit pas leurs secrets. Les administrateurs d'infrastructure et du
service détenant le chiffrement restent des personnes de confiance. Cette
séparation ne prétend pas garantir le secret contre un administrateur système.

Cette décision remplace la cible envisagée d'importer les providers personnels
dans OmniRoute et d'émettre une clé technique OmniRoute personnelle. Le lot
[ADR 0021](0021-cles-fournisseurs-personnelles.md) demeure valable pour la
configuration des clés : déployée/vérifiée, mais inactive pour l'inférence.
OAuth, adaptateurs de sortie personnelle, raccordement OmniRoute d'entreprise,
replis et révocation d'inférence demandent leur propre lot et recette. Aucun
fallback d'entreprise ne doit emprunter le compte personnel d'un autre sujet.

[Guide](../guides/omniroute.md) · [Backlog](../backlog.md) · [Reprise](../etat-reprise.md)
