# Organisation et maintenance du harness

Le [README principal](../README.md) présente la plateforme et renvoie aux
références complètes. L’[index documentaire](README.md) inventorie les documents.
L’[état de reprise](etat-reprise.md) est l’unique handoff courant.

## Responsabilités des répertoires

| Ensemble | Contenu et règle |
|---|---|
| `services/` | Code applicatif, regroupé par frontière : identité, connaissance, confidentialité, isolation, skills |
| `scripts/` | Entrées administratives PowerShell, renderers Python et workers ; chemins publics stables, liés au bootstrap et aux locks |
| `bootstrap/` | Parcours exécutable et contrats verrouillés |
| `infra/` / `deploy/` | Préparation des machines et ressources Kubernetes, fournisseurs conservés avec provenance/licences |
| `builder/` | Rôle d’ingénierie et catalogue/dépendances d’outillage |
| `schemas/` / `examples/` | Contrats et fixtures, aucune configuration réelle en clair |
| `tests/` / `validation/` / `.github/` | Recettes synthétiques et contrôles CI |
| Racine de `docs/` | Index, architecture, contrat, installation, schémas, état courant, backlog et règles d’organisation |
| `docs/guides/` | Fonctionnement détaillé des capacités, sécurité, outils et versions |
| `docs/runbooks/` | Procédures exécutables d’installation, exploitation et récupération |
| `docs/annexes/` | Contrats d’intégration à remettre aux administrateurs externes |
| `docs/adr/` | Décisions numérotées et conséquences ; les décisions remplacées gardent leur contexte |
| `docs/qualification/` | Preuves assainies datées, distinctes des diagnostics privés |
| `docs/archives/` | Instantanés historiques ; aucune consigne courante ne dépend de leur lecture en chaîne |

Les chemins `docs/installation-k3s-codex.md`, `docs/plan-integration-hermes.md`
et `docs/schemas-plateforme-hermes.md` restent stables pour AGENTS.md.
Les entrées de scripts et de services restent stables pour le bootstrap,
les hashes et les consommateurs. La carte du code est dans
[l’architecture](architecture.md#carte-du-dépôt).

`secrets/`, `artifacts/`, `.venv/`, `node_modules/` et caches sont locaux et
ignorés. Les fichiers non suivis ne sont pas ajoutés ou supprimés en masse.
Leur présence sur le poste ne signifie pas leur publication dans GitHub.

## Une information, une référence

Le README résume les capacités et leurs limites ; les guides les expliquent.
Le backlog indique les travaux et gates restants ; l’état de reprise désigne
les dernières preuves et le prochain point d’action. Les runbooks décrivent
la procédure réutilisable. Les preuves datées n’affirment pas l’état réel actuel
sans une nouvelle vérification de la cible.

À chaque lot, **mettre à jour `docs/etat-reprise.md` au lieu de créer un nouveau
`handoff-*.md`**. Un événement qui nécessite une preuve durable produit un
rapport assaini dans `docs/qualification/`. Un changement de décision produit
un ADR ; un changement de procédure met à jour le runbook concerné.
Git conserve l’historique ordinaire. Les anciennes archives restent consultables
et leurs liens internes sont maintenus, sans faire évoluer leurs résultats.

Toute évolution de composant, outil applicatif, secret requis ou migration
actualise bootstrap, locks, couverture, runbook et état de reprise dans le même
lot. Une réorganisation documentaire ne change pas les étapes runtime ni leurs
preuves. Livrer sur `main` selon la décision du propriétaire.

## Vérifier une modification

Depuis la racine du dépôt, avec les dépendances de validation préparées :

```powershell
python scripts/validate_docs.py
python scripts/validate_sources.py
python scripts/validate_bootstrap.py
node validation/diagrams.mjs
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
