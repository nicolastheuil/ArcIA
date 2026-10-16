# Suite de Tests Automatisés — ArcIA

Ce dossier regroupe l'ensemble des tests unitaires, tests d'intégration et contrôles de frontière de sécurité de la plateforme ArcIA.

## Exécution des Tests

Pour exécuter l'ensemble de la suite de tests :
```bash
python -m unittest discover -s tests -v
```

## Cartographie des Modules de Test

| Fichier de Test | Périmètre Contrôlé |
|---|---|
| **[test_deploy.py](test_deploy.py)** | Valide le moteur de déploiement universel `scripts/deploy.py` : analyse des arguments CLI, parsing de `arcia.config.yaml`, vérification des prérequis et exécution en mode simulation (`--dry-run`). |
| **[test_manifests.py](test_manifests.py)** | Vérifie la syntaxe, la structure YAML, les labels, l'attribution au namespace unifié `arcia` et la cohérence des ports dans tous les manifests de [deploy/manifests/](../deploy/manifests/README.md). |
| **[test_privacy.py](test_privacy.py)** | Valide la frontière de confidentialité souveraine et le service Presidio DLP (`services/presidio/`) : détection des secrets, clés `sk-...`, jetons GitHub, tokens Bearer, adresses IP et PII. |
| **[test_wizard.py](test_wizard.py)** | Teste la logique de l'assistant interactif `scripts/wizard.py` : dimensionnement VMware/K3s (tiers 20, 100, 300, 1000 utilisateurs), validation des secrets et configuration. |
| **[test_skills.py](test_skills.py)** | Contrôle la conformité des compétences du catalogue (`skills/`) : présence des fichiers `SKILL.md`, limites de taille et absence de scripts exécutables non autorisés. |
| **[test_graphify.py](test_graphify.py)** | Teste l'analyseur AST Python `scripts/arcia_graphify.py` et la génération déterministe du rapport GraphRAG. |
| **[test_public_apis.py](test_public_apis.py)** | Vérifie le client `skills/public-apis/scripts/public_apis.py` : formatage SIREN/SIRET, calcul de clé TVA intracommunautaire et cache local. |

## Intégration Continue (CI)

Cette suite de tests est automatiquement exécutée à chaque commit et pull request via le workflow GitHub Actions [.github/workflows/validate.yml](../.github/WORKFLOWS.md).
