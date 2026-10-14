# Standards d'Ingénierie — ArcIA

## 1. Organisation du Dépôt et Cycle de Livraison
- **Lecture préalable :** Consulter systématiquement `AGENTS.md` et `docs/organisation.md` avant d'éditer le code[cite: 1].
- **Branche cible :** Toutes les livraisons sont effectuées sur la branche `main`[cite: 1].
- **Cohérence des livrables :** Chaque évolution technique doit impérativement actualiser de concert le bootstrap (`bootstrap/`), les locks (`versions.lock.yaml`, `requirements*`), la couverture de tests (`tests/`, `validation/`), les runbooks (`docs/runbooks/`) et l'état de reprise (`docs/etat-reprise.md`)[cite: 1].
- **Respect de la carte du dépôt :**
  - `services/` : Services d'identité/portail, connaissance, confidentialité, isolation et skills[cite: 1].
  - `scripts/` : Contrôleur PowerShell protégé, CLI Python, renderers, workers et sondes[cite: 1].
  - `bootstrap/` : Parcours de qualification (`bootstrap/qualification.json`) et locks de contrats[cite: 1].
  - `infra/` : Rôles Ansible Debian/K3s, image et spécification VMware[cite: 1].
  - `deploy/` : Fondations statiques, manifests fournisseurs et skills embarquées[cite: 1].
  - `builder/` : Rôle d'ingénierie, catalogue, dépendances et licences d'outillage[cite: 1].
  - `schemas/` et `examples/` : Contrats de configuration et fixtures synthétiques[cite: 1].
  - `tests/`, `validation/` et `.github/workflows/` : Tests de frontières, validation des sources, liens, schémas et CI[cite: 1].

## 2. Ingénierie du Bootstrap et Déploiement
- **Point d'entrée unique :** Utiliser `scripts/Bootstrap-Harness.ps1`, qui est piloté par les 56 étapes de `bootstrap/qualification.json`[cite: 1].
- **Modes d'exécution :**
  - `Plan` : Découvrir le parcours sans déploiement (ex. `./scripts/Bootstrap-Harness.ps1 -Mode Plan -Profile Fresh -ProvisionVMs`)[cite: 1].
  - `Fresh` : Préparer une cible vierge désignée[cite: 1].
  - `Reconcile` : Réappliquer la cible possédée en préservant les identités et les volumes[cite: 1].
  - `Verify` : Exécuter les recettes de qualification[cite: 1].
  - `Audit` : Inspecter l'état de la cible[cite: 1].
- **Comportement d'exécution :** S'assurer que chaque étape vérifie les résultats de l'exécution courante, journalise sous protection et s'arrête immédiatement à la première erreur[cite: 1]. Avant un mode `Apply`, les accès, endpoints, DNS et secrets doivent être enregistrés dans les programmes locaux protégés[cite: 1].

## 3. Outillage, Skills, MCP et Tokenmaxing
- **Gestion des Skills :** Le catalogue local compte 539 entrées upstream (Hermes/ECC/Superpowers), 58 skills Hermes embarquées exposées au chargeur et sept adaptations/orientations ArcIA[cite: 1]. Les instructions doivent être chargées à la demande, analysées via LintLang, et conserver leurs dépendances et limites (Vercel skills servant à la découverte/import d'ingénierie)[cite: 1].
- **Optimisation de contexte (Tokenmaxing) :**
  - Utiliser RTK pour raccourcir automatiquement les commandes `git log` simples[cite: 1].
  - Utiliser Headroom pour réduire les gros résultats JSON des lectures déclarées, avec récupération de l'original dans un cache personnel borné[cite: 1].
  - Maintenir Context7 externe fermé tant que son adaptateur filtrant n'est pas qualifié, et conserver le routage automatique d'OmniRoute différé[cite: 1].
- **Nouveaux connecteurs MCP :** Chaque connecteur MCP doit fixer sa version, ses destinations, ses outils, son identité protégée et sa recette de qualification, et imposer les droits côté serveur avant toute recherche, téléchargement ou appel d'outil[cite: 1].