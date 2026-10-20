# Intégration agentgateway OSS

Passerelle cible v0.7 : [contrat applicatif](../../docs/v0.7/contrat-applicatif.md). Ce module porte la sélection explicite du profil et empêche un déploiement historique involontaire.

- Configuration native canonique : [bootstrap fermé](../../deploy/agentgateway/config.yaml).
- Image, Service et DenyAll : [manifeste Kubernetes](../../deploy/manifests/05-agentgateway.yaml).
- Version/digest : [registre](../../deploy/versions.json).
- [Matrice et recette](../../docs/reference/gateway-capabilities.md) : qualification distincte de l'activation métier.

`gateway.implementation: agentgateway` exige actuellement `mode: qualification_only`. Le déploiement complet est bloqué avant toute mutation ; utiliser le qualificateur synthétique. Un fichier historique sans `gateway` conserve son interprétation de migration, sans conversion silencieuse.

Les futurs adaptateurs utilisent JWT/CEL et les API natives qualifiées. Ne pas porter les callbacks, clés virtuelles ou tables LiteLLM sous un nouveau nom. Aucun service agentgateway n'est déclaré prêt pour des données réelles à ce stade.
