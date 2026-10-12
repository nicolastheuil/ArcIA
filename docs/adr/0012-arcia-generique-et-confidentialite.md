# ADR 0012 — ArcIA générique, instances distinctes et cloud filtré

Statut : retenu. Presidio et route gratuite déployés ; multi-utilisateur complet en cours de qualification.

## Périmètre

ArcIA est une plateforme IA agentique d’entreprise, sans usage métier imposé. arcia-harness porte le produit générique, son moteur Hermes, outils, RAG, contrôles et bootstrap. Les usages, corpus, comptes, domaines et connecteurs propres à une organisation vivent dans un dépôt d’instance distinct. Les références parlent de données privées/confidentielles et de périmètres, pas d’une catégorie particulière de métier.

## Sortie modèle

Presidio Analyzer/Anonymizer local, spaCy FR/EN, règles de secrets et d’infrastructure, pseudonymes HMAC par scope et payload complet. Un relais distinct reçoit une enveloppe attestée et porte seul la clé fournisseur. Hermes ne dispose ni d’Internet direct ni de DNS libre. Context7 externe est fermé tant que son adaptateur de sortie n’est pas qualifié.

## Budget et trajectoire

Qualification gratuite uniquement : OpenRouter free, ZDR, collecte interdite et prix maximal nul. Aucun fallback payant. La cible sera OmniRoute automatique puis OpenRouter free puis OpenRouter auto, sans affaiblir la politique ; automatisation et budget payant restent à autoriser/qualifier ultérieurement.

## Limites

Presidio ne garantit pas l’absence de faux négatifs ni la suppression de toute information confidentielle. Classification et IAM demeurent nécessaires. Les tokens synthétiques actuels ne doivent pas autoriser de données privées réelles. La résidence UE n’est pas établie par ZDR. Les espaces communs/restreints/personnels et le routage multi-utilisateur demandent une qualification end-to-end distincte.
