# Conception de la plateforme ArcIA v0.7

Statut : **proposé**, sur la branche `v0.7`, depuis le socle `09dd2a5`. Ce dossier prépare l'évolution ; il ne décrit pas des services déjà installés. Le registre [versions.json](../../deploy/versions.json) reste celui du socle réellement livré.

## Décisions du cadrage

- Open-WebUI est conservé. Une connexion de chat vers LiteLLM doit couvrir inférence directe et agents A2A, après qualification de bout en bout.
- `category: simple|agentic` reste une métadonnée explicite, avec des noms libres ; la catégorie ne crée pas deux backends dans Open-WebUI.
- Le wizard local conserve installation et restauration. Les autres fonctions passent progressivement dans la console, sans suppression avant parité vérifiée.
- Console unique : `/provider/` et `/tenant/<slug>/`. Le slug est une présentation, jamais une identité d'autorisation.
- Deux niveaux d'administration : opérateur du provider et administrateur de tenant. Les profils Standard et Power User sont conservés.
- Cluster partagé avec isolation renforcée comme référence ; cluster dédié en option. Admission de code outillé interdite si les prérequis d'isolation ne sont pas qualifiés.
- Désactivation complète de la DLP et/ou de la contrainte ZDR possible par modèle, selon une exception explicite et auditée. Elle n'accorde aucun droit supplémentaire et ne rend jamais les secrets du coffre accessibles au modèle.
- Réutiliser les API des composants avant d'écrire un remplacement ; une fonction annoncée n'est pas une fonction qualifiée sur la version fixée.

## Parcours de lecture

1. [Audit critique de l'existant](audit.md) : preuves, limites et incohérences.
2. [Conception et flux](conception.md) : topologie, responsabilités, isolation et parcours.
3. [Plan par lots](lots.md) : ordre, interfaces, recette, déploiement progressif et retour arrière.
4. [Sources et capacités à qualifier](sources.md) : références officielles et dépendances.
5. [Vérifications de cette étude](verification.md) : commandes exécutées et limites.

## Réorganisation documentaire prévue

La documentation sera structurée par besoins, en reprenant la séparation opérateur / organisation / applications mise en avant par Galene. Aucun contenu privé ni schéma propriétaire de Galene n'est repris.

| Entrée | Contenu à constituer dans les lots |
|---|---|
| Comprendre | Produit, profils, limites, architecture et glossaire |
| Installer et restaurer | Wizard local, headless, prérequis et reconstruction |
| Administrer le provider | Tenants, capacités, versions, incidents et supervision infra |
| Administrer un tenant | Modèles, confidentialité, groupes, agents, connexions, Power Users et sauvegardes |
| Utiliser | Chat, missions, fichiers, applications et partage |
| Construire | Contrat d'agent, compétences, MCP, builder et publication |
| Exploiter et qualifier | SLO, PRA, migrations, recettes et preuves datées |
| Référence | API, schémas, permissions, versions et contrats de compatibilité |

Pendant la migration, les pages actuelles restent valides. Chaque déplacement conserve un point d'entrée compatible ou actualise tous les liens et ancres dans le même lot. La documentation d'exploitation ne présente une cible comme disponible qu'après livraison de son lot.

## Règle de progression

Chaque lot produit un résultat utilisable, une recette positive et négative, un état de sauvegarde, un retour arrière et une preuve. Un lot dont la recette échoue n'est pas ouvert aux utilisateurs suivants. Les critères détaillés et les cinq risques transverses sont dans le [plan](lots.md).
