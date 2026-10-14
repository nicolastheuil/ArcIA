# ADR 0020 — Périmètre générique et politiques de routage d’instance

Statut : décidé par le propriétaire le 14 octobre 2026 ; extraction des outils
personnels codée, intégration de routage en cours.

Le transfert personnel des secrets entre deux PC n’appartient pas au harness.
Scripts, test, lock, runbook et preuve sont conservés localement, hors Git/CI.
Le contrôleur de déploiement conserve DPAPI/ACL et son bootstrap générique.

OmniRoute est le premier routeur par défaut. Un utilisateur standard reçoit le
mode intelligent/automatique configuré par l’administrateur. Chaque instance
définit fournisseurs, souscriptions d’entreprise, budgets, modèles, ZDR,
collecte et résidence. Le rôle `ArcIA.ProviderSelfService` autorise la connexion
de providers personnels, isolés par sujet, sans droit d’administration globale.

Tous les appels modèles cloud passent par Presidio par défaut. Ollama/vLLM
internes autorisés n’y passent pas par défaut ; une bascule cloud reprend le
filtrage. Le portail OmniRoute est exclusivement privé sur le LAN et authentifié.
Aucune route publique, tunnel ou publication NAT n’est autorisée.

Teams est une entrée optionnelle par adaptateur authentifié appliquant les
mêmes droits que le navigateur. Le quickstart couvre identité, configuration
OmniRoute, premier usage et setup Teams.

Le code de qualification antérieur est spécialisé pour OpenRouter free/ZDR.
Cette limitation est distinguée du contrat générique ; aucun abonnement ou
fournisseur n’est activé implicitement. Toute activation effective actualise
bootstrap, locks, tests, runbooks et état de reprise. Rebuild neuf non exécuté.
