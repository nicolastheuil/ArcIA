# Versions officielles — relevé du 11 octobre 2026

Les API GitHub publiques ont été interrogées et les tags résolus en commits.
Le lock est du JSON valide YAML 1.2, lisible sans dépendance Python.
Statut commun : **sources vérifiées ; aucune qualification sur cible**.

| Composant | Candidat | Condition restante |
|---|---|---|
| K3s | v1.35.9+k3s1 | Debian, réseau, CPI, essais et panne de nœud |
| vSphere CSI | v3.7.3 | Matrice vCenter/ESXi, compte minimum, sidecars et digests |
| CloudNativePG | v1.30.1 | Qualification sur K3s, image PG/pgvector, failover |
| Hermes | v0.21.6 | Digest, UID/GID, s6, wizard, Desktop/OIDC et SQLite |
| CPI, ingress, OmniRoute | Non résolus | Inventaire et qualification nécessaires |
| pyvmomi | 9.1.1.0 | Wheel SHA256 vérifiée ; inventaire vCenter en cours |
| Debian generic amd64 | 20261001-2618 | SHA512 vérifié, conversion VMDK exécutée ; tools et boot VMware restants |
| qemu-img | 10.2.1 | Conversion locale ; compatibilité import VMware à vérifier |

K3s 1.37 est disponible mais n'est pas retenu automatiquement : les notes CSI 3.7
indiquent Kubernetes 1.33 à 1.35. CNPG 1.30 documente 1.34 à 1.36 et ne garantit
pas les distributions autres que Kubernetes vanilla. L'intersection documentaire
1.35 est donc un candidat de travail, pas une certification de la combinaison.

Sources :

- [K3s release précise](https://github.com/k3s-io/k3s/releases/tag/v1.35.9%2Bk3s1)
- [SDK VMware](https://github.com/vmware/pyvmomi)
- [Debian image et SHA512SUMS](https://cloud.debian.org/images/cloud/trixie/20261001-2618/)
- [open-vm-tools Debian](https://packages.debian.org/trixie/open-vm-tools)
- [SHA256 officiels amd64](https://github.com/k3s-io/k3s/releases/download/v1.35.9%2Bk3s1/sha256sum-amd64.txt)
- [K3s HA](https://docs.k3s.io/datastore/ha-embedded)
- [K3s prérequis et ports](https://docs.k3s.io/installation/requirements)
- [K3s airgap](https://docs.k3s.io/installation/airgap)
- [CSI releases et matrice 3.7](https://github.com/kubernetes-sigs/vsphere-csi-driver/releases)
- [CNPG compatibilité](https://cloudnative-pg.io/docs/1.28/supported_releases/)
- [Hermes source épinglée](https://github.com/NousResearch/hermes-agent/tree/818c13be1dc4fd28987e1e881a9408224afd4535)
- [Hermes Docker](https://hermes-agent.nousresearch.com/docs/user-guide/docker)
- [Volumes et RWOP](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)

Le bootstrap bloque les composants non qualifiés. Les digests manquants restent
null. Relever les images et sidecars réellement déployés, conserver leurs artefacts
et SBOM, vérifier signatures/provenance avant une release. Les paquets Debian,
le contrôleur Ansible et les dépendances métier restent à verrouiller.
