# Backlog — préparation ArcIA

Mis à jour : 2026-10-11. Codé ne signifie pas déployé ou qualifié.

| ID | Lot | Travail | État / gate |
|---|---|---|---|
| PREP-01 | Préparation | Lire intégralement les sources, inventorier poste et fichiers | Vérifié localement |
| PREP-02 | Préparation | ADR, versions officielles, rôle et reprise | Codé/documenté |
| PREP-03 | Préparation | Wizard DPAPI, validation stricte, rendu privé | Codé ; tests synthétiques locaux |
| PREP-04 | Préparation | Préflight SSH sans mutation et sans sorties brutes | Vérifié sur les trois VM via SSH strict et sudo ; preuves détaillées protégées |
| PREP-05 | Préparation | Ansible K3s épinglé et idempotence bornée | Codé ; exécution distante non testée |
| PREP-06 | Préparation | Namespaces restreints, deny-all, quotas, identités | Codé ; API/admission non testées |
| PREP-07 | Préparation | Compte/dépôt privé, identité et droits | Créé : nicolastheuil/arcia-harness ; privé et ADMIN vérifiés |
| PREP-08 | Préparation | Trois VM, empreintes SSH, DNS/NTP et ressources | Vérifié : trois Debian 13, clés SSH hors bande conservées, sudo, identités Linux uniques, DNS/NTP, ressources, tools, cgroups, swap absent et TUN ; K3s non installé |
| PREP-09 | Préparation | ESXi/domaines de panne, CPI/CSI, policy, comptes minimum | Connexion/inventaire validés ; trois ESXi distincts et anti-affinité vérifiés ; CSI/CPI non qualifiés |
| PREP-10 | Préparation | API/HTTPS avec bascule, CIDR sans recouvrement, firewall | Qualification attendue |
| L0-01 | 0 | Digests/artefacts, CPI/CSI/ingress et PG/pgvector | À coder/qualifier après inventaire |
| L0-02 | 0 | Hermes synthétique, Desktop, OIDC, Entra et Teams | À développer et tester |
| L0-03 | 0 | Policy serveur, sanitizer complet, sortie unique mock | À développer et tester |
| L0-04 | 0 | Launcher typé, VPN personnel synthétique, kill switch/reaper | À développer et tester |
| L0-05 | 0 | Backup chiffré cohérent, restore safe-mode et rebuild | À développer et tester |
| L0-06 | 0 | Qualification skills/hooks §25, licences/provenance | Pilotes désactivés |
| L1 | 1 | Registre/RBAC, coffres individuels, lecture, rapports, docs réduites | Après gates lot 0 |
| L2 | 2 | Plans immuables, Teams, capacités uniques, verrou et réconciliation | Après lot 1 |
| L3 | 3 | Brigade, collecte documentaire, ACL/recherche, promotion REX | Après fondations |
| L4 | 4 | Rebuild deuxième ingénieur, revue confidentialité, release/SBOM | Aucun statut release avant recette |
| L5 | 5 | Benchmarks compression et connecteurs supplémentaires | Facultatif, désactivé au bootstrap |

Les services métier sont absents. Ne pas remplacer leur développement par des
conteneurs vides ou des réponses fictives. La recette complète reste celle du §19,
complétée par §25 et §26 : IAM/DESK/SEC/VPN/APR/DLP/KB/LLM/GIT/CRY/REC/LOAD,
perte de nœud, failover PG, fencing Hermes et bascule endpoints.
