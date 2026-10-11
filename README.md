# ArcIA Harness

Préparation du harness de plateforme Hermes pour trois VM Debian 13 / K3s sur
VMware, avec stockage partagé. Dépôt : **nicolastheuil/arcia-harness**, privé.

**État : trois VM Debian 13 créées et allumées ; VMware, empreintes SSH hors bande
et préflight Linux vérifiés sur les trois nœuds ; DNS des endpoints vérifiés 3/3,
compte SSO dédié et droits effectifs bornés vérifiés ; VIP installée et bascule
du transport synthétique vérifiée (12/12), flux K3s vérifiés (54/54). Bootstrap K3s
tenté sur le premier nœud, échec de démarrage puis arrêt contrôlé ; aucun cluster
K3s opérationnel. Voir [le handoff](docs/handoff-2026-10-11.md). Les services métier Hermes/Entra/Teams/VPN/coffres/DLP restent à développer
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

Pour les sondes système Linux, JSON Schema, YAML et syntaxe Ansible, utiliser un environnement Python Linux
isolé avec requirements-validation.txt, puis `python scripts/validate_sources.py`.
Les tests n'accèdent à aucun environnement client. Les gates bloquent l'exemple
synthétique avant SSH et l'installation réelle tant que les prérequis manquent.

## Suite du déploiement

La cible confirmée est vCenter / cluster ESXi ; l'image Debian a été préparée et les trois VM déployées.
Le formulaire `scripts/Connect-VMware.ps1 -PromptFingerprint` permet une acceptation
locale du certificat et un inventaire chiffré. Voir [le runbook VMware](docs/runbooks/vcenter.md).

Pour l'instance actuelle, poursuivre par le réseau/endpoints
avec bascule et le stockage VMware. Saisir les paramètres complémentaires dans le wizard local,
qualifier CPI/CSI/versions, puis passer les gates avant le bootstrap. La recette
de panne d'un nœud et le rebuild sûr sur cluster neuf restent obligatoires.

L'état opérationnel privé est conservé hors Git/OneDrive. À la demande de l'utilisateur,
sa **sauvegarde portable chiffrée** est dans `secrets/local/arcia-private.arciap`,
exclue de Git et copiée avec le dossier de travail. Clé : **1Password personnel,
entrée « ArcIA Platform Encryption Key »**. Voir [sauvegarde et restauration sur
le second PC](docs/runbooks/transfert-second-pc.md). Les programmes protégés
rechiffrent les bundles pour le nouveau compte Windows ; aucun secret dans le chat.
La sauvegarde de fichiers ne remplace pas la recette de reprise d'un cluster actif.
