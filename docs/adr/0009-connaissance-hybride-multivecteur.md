# ADR 0009 — Recherche hybride et multi-vecteur locale

Date : 12 octobre 2026. Statut : accepté et déployé en qualification synthétique.

## Contexte

Le corpus visé contient des centaines de manuels éditeurs PDF, des guides API complets, des spécifications OpenAPI/JSON Schema et des schémas à réutiliser ou adapter. Le français/anglais, les références exactes et la coexistence de versions imposent plusieurs modes de recherche. Le socle dispose de PostgreSQL/pgvector et de CPU ; un modèle visuel lourd uniforme n’est pas encore dimensionné.

## Décision

Conserver PostgreSQL pour catalogue, droits, versions, FTS, vecteurs et tokens. Rechercher par texte, vecteur E5 du passage et vecteur du titre, fusionner par RRF, puis appliquer MaxSim mLateOn sur 30 candidats. Les modèles multilingues sont locaux, fixés par révision/hash et exécutés hors ligne. Les assets et originaux restent séparés sur PVC RWOP avec hash et filiation des adaptations.

Les API sont indexées par méthode/chemin/opération, avec leurs paramètres/réponses et source complète. Les PDF gardent page, tableaux et images ; les fichiers Mermaid/SVG/draw.io restent éditables. La compréhension visuelle, les scans/OCR avancés et les fichiers draw.io compressés exigent une qualification supplémentaire. Un PDF inexploitable est refusé avant publication.

## Conséquences et preuve

Un seul service CPU séquentiel borne charge et écritures dans le pilote. Les matrices de tokens FP16 augmentent le stockage ; le reclassement borné évite un MaxSim exhaustif. Les ACL sont imposées par le token serveur et RLS avec rôle non propriétaire. La recette réelle couvre sources, versions, schémas dérivés, citations, refus A/B et réseau ; aucun benchmark de centaines de PDF n’est revendiqué.

La sélection d’extraction actuelle utilise PyMuPDF sous sa licence duale AGPL/commerciale ; le statut de licence doit être traité lors de la décision de distribution/exploitation élargie. L’usage privé de qualification ne constitue pas une validation de licence pour une future offre. Les modèles E5 et mLateOn sont respectivement MIT et Apache-2.0. [Pipeline complet, formats, coûts et sources](../guides/connaissance-documentaire.md).
