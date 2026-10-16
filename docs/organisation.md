# Organisation et maintenance du harness

Le [README principal](../README.md) présente la plateforme et renvoie aux
références complètes. L’[index documentaire](README.md) inventorie les documents.
L’[état de reprise](etat-reprise.md) est l’unique handoff courant.

## Responsabilités des répertoires

| Ensemble | Contenu et règle |
|---|---|
| `services/` | Microservices applicatifs : Presidio DLP, Teams Bot, plugin Hermes Tokenmaxing |
| `scripts/` | Scripts de déploiement universel (`deploy.py`, `Deploy-ArcIA.ps1`), injection de secrets et validation |
| `deploy/manifests/` | Manifestes Kubernetes déclaratifs unifiés pour le namespace `arcia` |
| `skills/` | Compétences modulaires partagées : Graphify AST, Ponytail YAGNI, Public-APIs |
| `tests/` / `.github/` | Recettes unitaires, conformité des manifestes et barrière de confidentialité CI |
| Racine de `docs/` | Index, architecture, contrat, installation, schémas, état courant, backlog et règles d’organisation |
| `docs/guides/` | Fonctionnement détaillé des capacités, sécurité, outils et versions officielles |
| `docs/runbooks/` | Procédures exécutables de quickstart, exploitation quotidienne et reprise |
| `docs/annexes/` | Contrats d’intégration à remettre aux administrateurs externes (Microsoft 365) |
| `docs/adr/` | Décisions d'architecture numérotées et conséquences |
| `docs/archives/` | Instantanés historiques (recette fondatrice initiale) |

Les chemins `docs/installation-k3s-codex.md`, `docs/plan-integration-hermes.md`
et `docs/schemas-plateforme-hermes.md` restent stables pour AGENTS.md.
Les entrées de scripts et de services restent stables pour le déploiement,
les hashes et les consommateurs. La carte du code est dans
[l’architecture](architecture.md#carte-du-dépôt).

`secrets/`, `.personal/`, `artifacts/`, `.venv/`, `node_modules/` et caches sont locaux et
ignorés. Les fichiers non suivis ne sont pas ajoutés ou supprimés en masse.
Leur présence sur le poste ne signifie pas leur publication dans GitHub.

## Une information, une référence

Le README résume les capacités et leurs limites ; les guides les expliquent.
Le backlog indique les travaux et gates restants ; l’état de reprise désigne
les dernières preuves et le prochain point d’action. Les runbooks décrivent
la procédure réutilisable.

À chaque lot, **mettre à jour `docs/etat-reprise.md` au lieu de créer un nouveau
`handoff-*.md`**. Un changement de décision produit un ADR ; un changement de procédure met à jour le runbook concerné.
Git conserve l’historique ordinaire.

Toute évolution de composant, outil applicatif, secret requis ou migration
actualise manifestes, runbook et état de reprise dans le même
lot. Une réorganisation documentaire ne change pas les étapes runtime ni leurs
preuves. Livrer sur `main` selon la décision du propriétaire.

## Vérifier une modification

Depuis la racine du dépôt, avec les dépendances de validation préparées :

```powershell
python scripts/validate_docs.py
python -m unittest discover tests
```

Le contrôle documentaire lit uniquement les Markdown suivis par Git : chemins
locaux, ancres, index et absence de nouveaux handoffs hors archives. Ajouter
explicitement les nouveaux fichiers du lot à l’index avant le contrôle ; ne pas
utiliser `git add .` pour embarquer les diagnostics locaux. Les diagrammes sont
également validés sur les sources suivies. Les liens web ne sont pas sondés.

Pour une évolution fonctionnelle, exécuter les tests pertinents et les contrôles
PowerShell de la [CI](../.github/workflows/validate.yml). Les recettes cluster,
les accès privés et le rebuild restent des actions distinctes, réalisées sur
les seules cibles désignées et documentées comme exécutées lorsqu’elles le sont.
