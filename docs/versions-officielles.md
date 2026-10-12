# Versions et compatibilités — 12 octobre 2026

Le [lock](../versions.lock.yaml) contient les références exactes, commits et
digests. Les statuts conservateurs de préparation dans ce lock ne constituent
pas une preuve de déploiement ; celle-ci est dans
[la recette](runbooks/recette-fondatrice.md). Aucun statut de release qualifiée.

| Composant | Version déployée | Preuve / limite |
|---|---|---|
| Debian amd64 | 13, image generic 20261001-2618 | SHA512, conversion/import/boot et préflight 3 VM vérifiés |
| K3s | v1.37.1+k3s1 | 3 serveurs Ready, API/VIP/chiffrement ; rebuild non qualifié |
| vSphere CPI | v1.37.0 | Rollout et providerID/taints vérifiés 3/3 |
| vSphere CSI | v3.7.3 | 5 checks RWOP/persistance ; panne brutale/fencing restants |
| CloudNativePG | v1.30.1 | Opérateur 2/2, réconciliation et switchover vérifiés |
| PostgreSQL/pgvector | 18.6-202610120828-standard-trixie | 3 instances, SQL vectoriel/réplication/switchover vérifiés |
| Hermes | v0.21.6 | 1 instance, UID/GID, SQLite/persistance/isolation/HTTPS local vérifiés |
| NGINX | 1.31.6 | 3 réplicas prêts, TLS/auth/bascule contrôlée vérifiés |
| Certbot | 5.8.0, runtime poste WSL | Dépendances hashées, DNS-01 suspendu ; aucun certificat public émis |
| Python de validation poste | 3.14.7 | Tests/contrôleurs Windows et WSL utilisés |
| pyvmomi | 9.1.1.0 | Wheel hashée, inventaire VMware exécuté |
| qemu-img | 10.2.1 | Conversion de l’image exécutée |
| OmniRoute | Non retenu par version à ce stade | Non installé, aucune sortie IA |
| Outils builder §25 | Voir lock builder dédié | [Installation et preuves](outillage-builder.md) |

## Support : limites conservées

Le relevé officiel initial indiquait CSI 3.7 avec Kubernetes 1.33–1.35,
CNPG 1.30 avec 1.34–1.36 et une garantie portant sur Kubernetes vanilla.
Le cluster testé est K3s/Kubernetes 1.37. Les scénarios réussis ne prolongent
pas une matrice de support éditeur et ne certifient pas vSphere 9.1.1.
La matrice Broadcom détaillée n’avait pas pu être lue (HTTP403).
Traiter ces écarts avant release : combinaison documentée supportée, ou décision
d’exploitation explicite avec qualification renforcée et limites assumées.

## Verrouillage et reproductibilité

Images VMware/applicatives par digest ; manifests amont CNPG/CPI/CSI conservés
avec licences et hashes. Le tag PostgreSQL doit rester présent en plus du digest :
CNPG y lit la version majeure.
`scripts/validate_sources.py` vérifie ces artefacts sans SSH.

Restent à compléter : paquets Debian/snapshots, dépendances transitives de tout
le build, signatures/provenance, SBOM et kit de reconstruction. La sélection
des versions est une activité de build ; aucune utilisation de `latest` au
déploiement. Les wrappers K3s hérités doivent être réconciliés avant rebuild.

## Sources officielles du relevé

- [K3s release épinglée](https://github.com/k3s-io/k3s/releases/tag/v1.37.1%2Bk3s1)
- [K3s HA](https://docs.k3s.io/datastore/ha-embedded)
- [CPI 1.37.0](https://github.com/kubernetes/cloud-provider-vsphere/releases/tag/v1.37.0)
- [vSphere CSI releases](https://github.com/kubernetes-sigs/vsphere-csi-driver/releases)
- [CNPG 1.30 support](https://cloudnative-pg.io/docs/1.30/supported_releases/)
- [Hermes source épinglée](https://github.com/NousResearch/hermes-agent/tree/818c13be1dc4fd28987e1e881a9408224afd4535)
- [NGINX 1.31.6](https://github.com/nginx/nginx/releases/tag/release-1.31.6)
- [Debian image](https://cloud.debian.org/images/cloud/trixie/20261001-2618/)
- [Volumes et RWOP](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Certbot](https://eff-certbot.readthedocs.io/en/stable/using.html)

Les versions installées sont celles des artefacts du lot, pas une affirmation
qu’elles seront toujours les releases courantes.
