# CI/CD & Workflows GitHub — ArcIA

Ce dossier contient les workflows d'intégration continue (CI) et d'automatisation GitHub Actions pour la plateforme ArcIA.

## Contenu

| Composant | Fichier | Description |
|---|---|---|
| **Pipeline de Validation Multi-OS** | [workflows/validate.yml](workflows/validate.yml) | Matrice de tests automatisés (Ubuntu 24.04 et Windows Server 2025) exécutée à chaque push et pull request sur `main`. |

## Rôle et Contrôles Automatisés

Le workflow `validate.yml` garantit l'intégrité et la reproductibilité du socle générique avant tout déploiement :

1. **Suite de tests unitaires** : Exécution de `tests/` (validation des manifests Kubernetes, moteur de déploiement, règles Presidio DLP, analyseurs Graphify et catalogue de skills).
2. **Qualification du moteur de déploiement (Dry-Run)** : Exécution de `scripts/deploy.py --dry-run` sur une configuration synthétique pour vérifier la génération des ressources.
3. **Contrôle syntaxique des scripts Shell & PowerShell** : Vérification de syntaxe (`bash -n` et `Get-Command / Test-Path`) sur tous les scripts de déploiement.
4. **Validation de documentation** : Vérification de tous les liens internes et ancres via `scripts/validate_docs.py`.

## Fixture de validation

La CI utilise [tests/fixtures/deploy.synthetic.yaml](../tests/fixtures/deploy.synthetic.yaml), sans réécrire un fichier de configuration à la racine. Les valeurs sont inventées, sans modèle réel ni secret d’instance. Son marqueur `synthetic_validation` interdit un déploiement effectif ; seul `--dry-run` l’accepte. Cette validation ne prouve pas un déploiement Kubernetes ni une recette navigateur.
