# ADR 0011 — Bootstrap exhaustif et évolutif d’ArcIA

Statut : retenu, codé et réconcilié sur la cible existante. Rebuild neuf non exécuté.

## Problème

Des opérations administratives individuelles ne suffisent pas à reconstruire le socle courant. L’installation neuve avait une dépendance circulaire entre Hermes, ses outils et son MCP documentaire ; le contrôleur Windows ne créait pas toujours son venv. Le répertoire protégé pouvait aussi être redirigé par MSIX.

## Décision

Point d’entrée PowerShell avec manifeste ordonné, profils Fresh/Reconcile/Verify/Audit, verrous et journal DPAPI. Succès récents contrôlés et arrêt sur erreur. Coverage CI exigée pour tout composant, outil, feature et service. Installer un Hermes minimal puis Knowledge/Privacy, les outils et le rendu complet. Les dépendances administratives Windows/Linux sont fixées par hashes, les applicatifs restent dans K3s. Le résolveur d’état retrouve une seule racine protégée valide.

## Conséquences

Toute évolution doit actualiser le bootstrap. Une preuve ancienne ne permet pas de sauter une étape. Les entrées protégées, confiance SSH, DNS et TLS sont des prérequis externes explicites. Le bootstrap logiciel ne remplace pas le restore des données. Une release complète demeure conditionnée à un rebuild neuf et aux autres gates de recette.
