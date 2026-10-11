# ArcIA Harness

Préparation du harness de plateforme Hermes pour trois VM Debian 13 / K3s sur
VMware, avec stockage partagé. Dépôt : **nicolastheuil/arcia-harness**, privé.

**État : trois VM Debian 13 créées, allumées et vérifiées via VMware ; aucun cluster
K3s déployé. Les services métier Hermes/Entra/Teams/VPN/coffres/DLP restent à développer
et qualifier. Ce dépôt n'est pas encore une release installable.**

Le socle contient : spécification des VM, wizard Windows DPAPI à ACL restreinte,
validation stricte des paramètres, préflight SSH en lecture, rendu Ansible privé,
bootstrap K3s épinglé et bloqué par prérequis, manifests Kubernetes fermés,
tests synthétiques et CI, ADR, backlog et état de reprise.

Commencer par [le runbook](docs/runbooks/preparer-deploiement.md), puis
[l'état de reprise](docs/etat-reprise.md). Les sources de cadrage intégrales restent
dans docs/installation-k3s-codex.md, docs/plan-integration-hermes.md et
docs/schemas-plateforme-hermes.md. Les instructions prioritaires sont dans AGENTS.md.

## Contrôles locaux sans accès aux VM

```powershell
python -m unittest discover -s tests -v
python scripts/harness.py doctor
python scripts/harness.py plan --config examples/synthetic/instance.json
powershell -NoProfile -File tests/Test-ProtectedState.ps1
```

Pour JSON Schema, YAML et syntaxe Ansible, utiliser un environnement Python Linux
isolé avec requirements-validation.txt, puis `python scripts/validate_sources.py`.
Les tests n'accèdent à aucun environnement client. Les gates bloquent l'exemple
synthétique avant SSH et l'installation réelle tant que les prérequis manquent.

## Suite du déploiement

La cible confirmée est vCenter / cluster ESXi ; l'image Debian est à préparer.
Le formulaire `scripts/Connect-VMware.ps1 -PromptFingerprint` permet une acceptation
locale du certificat et un inventaire chiffré. Voir [le runbook VMware](docs/runbooks/vcenter.md).

Créer les trois VM selon infra/vmware/vm-spec.yaml, identifier réseau/endpoints
avec bascule et stockage VMware. Saisir les paramètres dans le wizard local,
qualifier CPI/CSI/versions, puis passer les gates avant le bootstrap. La recette
de panne d'un nœud et le rebuild sûr sur cluster neuf restent obligatoires.

Les valeurs privées sont conservées hors Git et hors OneDrive. Les secrets passent
par les programmes locaux protégés ; aucun collage dans le chat. DPAPI protège le
bootstrap Windows, sans remplacer SOPS/age et la récupération externe à construire.
