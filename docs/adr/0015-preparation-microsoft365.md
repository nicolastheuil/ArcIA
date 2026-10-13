# ADR 0015 — Préparation Microsoft 365 et configuration d'instance

Statut : adopté pour la documentation et le contrat hors ligne, 13 octobre 2026.
Adaptateurs et tenant non déployés/non qualifiés.

## Décision

Une [annexe administrateur](../annexes/integration-microsoft365.md) décrit les
procédures Microsoft. L'instance conserve `instance/microsoft365.yaml`, sans
secrets ni inventaire confidentiel. Le harness porte schéma strict, gabarit
synthétique, validation/plan hors ligne, locks et gates de bootstrap.

Séparer login Web, bot personnel/SSO, collecte de transcriptions, collecte
SharePoint, Outlook délégué et éventuel Outlook app-only. Mono-tenant ; app
roles plutôt que lecture globale de l'annuaire. Meetings : permissions Graph
avec policy organisateurs ; SharePoint : Sites.Selected + grants read ;
Outlook applicatif : RBAC Exchange borné, sans permission Graph globale additive.
Le RSC par réunion et les écritures sont des extensions distinctes, exclues du
contrat v1. Les secrets sont des références opaques résolues hors modèle.

## Conséquences

L'administrateur peut préparer le tenant et remettre un dossier exploitable.
Le validateur refuse toute activation car les services correspondants ne sont
pas encore implémentés. Aucun faux service ou étape de déploiement Microsoft
n'est ajouté au bootstrap K3s. La prochaine évolution doit livrer importeur
protégé, adaptateurs, IAM/ACL, approbations, migrations, couverture bootstrap et
recette synthétique, avant ouverture des données. Une configuration valide
n'est ni un consentement effectivement vérifié ni une qualification du tenant.
