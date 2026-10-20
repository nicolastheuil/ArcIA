# Capacités historiques LiteLLM et limites de migration

Ce document décrit uniquement le socle antérieur au [choix agentgateway](../v0.7/contrat-applicatif.md). La [matrice cible](gateway-capabilities.md) ne reprend aucune de ses qualifications.

## Preuves conservées

Les [preuves datées](../v0.7/verification.md) documentent LiteLLM v1.106.0 avec les images Hermes/WebUI et Presidio épinglées : 43 indicateurs API/fichiers/isolation, 23 canaris DLP natifs et 13 canaris aval. Ces résultats ne qualifient ni le pont A2A, ni MCP, ni les budgets ou l’annulation.

Le qualificateur livré reste disponible pour contrôler le retour arrière historique :

```bash
python scripts/qualify_hermes_workspaces.py --config arcia.config.yaml --real-gateway --report artifacts/legacy-stack-qualification.json
```

Les essais A2A spécifiques LiteLLM non livrés ont été écartés lors du changement de cible. Le témoin A2A générique conservé dans les fixtures n’est pas une attestation de compatibilité d’agentgateway ou de Hermes v1.0.

## Contraintes de migration

Conserver clés, identités, base, volumes, sauvegarde et anciens appels jusqu’à parité recettée. Le renderer LiteLLM et son API de clés ne sont pas réemployés comme contrat d’agentgateway. Aucun changement de fournisseur ou de gateway ne déclassifie l’historique, les données ou les droits.

L’ancien transformateur Chat/A2A inspecté au tag v1.106.0 regroupait l’historique dans une partie texte sans contexte nominatif démontré. Ce constat de source ne remplace aucune recette réseau et ne décrit pas la nouvelle gateway.
