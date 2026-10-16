# ADR 0010 — Outils dans Hermes/K3s et livraison main

Date : 12 octobre 2026. Statut : décision utilisateur appliquée.

Les outils applicatifs sont installés dans K3s et exposés à l’instance Hermes : PVC d’outils RWOP en lecture seule, catalogue natif de skills, Context7 par relais privé et MCP Knowledge en lecture seule. Les anciennes installations ArcIA-Builder du poste sont supprimées et leurs installateurs désactivés. Le contrôleur administratif reste sur le poste ; le compte ACME WSL doit encore être migré et son runtime supprimé.

Les changements génériques sont committés et poussés directement sur **main**, sans nouvelle branche ni PR, conformément à la demande explicite. Les locks, manifestes, tests, ADR et handoffs font partie du dépôt ; les inventaires, credentials, bundles et scripts de debug privés en sont exclus.

Les certificats Let’s Encrypt sont émis pour les deux seuls noms publics demandés et appliqués à NGINX. NAT et Teams restent absents. Le dashboard utilise l’authentification locale et la résolution privée ; le formulaire d’accès retrouve le stockage protégé Codex/MSIX depuis un terminal Windows classique. Aucune valeur secrète ne passe par le chat.

Cette décision remplace les recommandations historiques de placement builder sur le poste et de livraison par branche/PR, ainsi que le statut TLS différé de l’ADR 0008. [Outillage](../guides/outillage-builder.md), [infrastructure](../guides/infrastructure-k3s.md), [reprise](../etat-reprise.md).
