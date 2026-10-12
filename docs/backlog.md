# Backlog — préparation ArcIA

Mis à jour : 2026-10-12. Codé ne signifie pas déployé ou qualifié.

État courant prioritaire : [handoff socle de qualification](handoff-2026-10-12-socle-qualification.md).
PREP-05 : K3s trois serveurs Ready ; PREP-09/L0-01 : CPI 1.37.0 et CSI 3.7.3
déployés, cinq essais RWOP vérifiés, PostgreSQL prêt 3/3. L0-02 : Hermes prêt
1/1 en isolation sans appels IA ; HTTPS non prêt, correction NGINX codée à appliquer.
Failover PG, fencing/perte de nœud, sauvegardes et rebuild non exécutés.
La table historique ci-dessous conserve le contexte initial ; le handoff prévaut.

| ID | Lot | Travail | État / gate |
|---|---|---|---|
| PREP-01 | Préparation | Lire intégralement les sources, inventorier poste et fichiers | Vérifié localement |
| PREP-02 | Préparation | ADR, versions officielles, rôle et reprise | Codé/documenté |
| PREP-03 | Préparation | Wizard DPAPI, validation stricte, rendu privé | Codé ; tests synthétiques locaux |
| PREP-04 | Préparation | Préflight SSH sans mutation et sans sorties brutes | Vérifié sur les trois VM via SSH strict et sudo ; preuves détaillées protégées |
| PREP-05 | Préparation | Ansible K3s épinglé et idempotence bornée | Exécuté ; premier serveur préparé puis échec k3s-server/PATH ; arrêt contrôlé pour handoff, cause à corriger avant reprise |
| PREP-06 | Préparation | Namespaces restreints, deny-all, quotas, identités | Codé ; API/admission non testées |
| PREP-07 | Préparation | Compte/dépôt privé, identité et droits | Créé : nicolastheuil/arcia-harness ; privé et ADMIN vérifiés |
| PREP-08 | Préparation | Trois VM, empreintes SSH, DNS/NTP et ressources | Vérifié : trois Debian 13, clés SSH hors bande conservées, sudo, identités Linux uniques, DNS/NTP, ressources, tools, cgroups, swap absent et TUN ; K3s non installé |
| PREP-09 | Préparation | ESXi/domaines de panne, CPI/CSI, policy, comptes minimum | vCenter/ESXi 9.1.1 ; vSAN partagé, dix policies compatibles PBM ; compte SSO créé ; quatre rôles, dix objets, droits effectifs positifs/négatifs vérifiés ; CPI/CSI non qualifiés |
| PREP-10 | Préparation | API/HTTPS avec bascule, CIDR sans recouvrement, firewall | DNS vérifiés 3/3 ; 54/54 ports et 12/12 contrôles transport VIP avec bascule/retrait qualifiés ; API K3s réelle à tester ; réseaux futurs inconnus |
| L0-01 | 0 | Digests/artefacts, CPI/CSI/ingress et PG/pgvector | CPI 1.35.1 et CSI 3.7.3 : quatre manifests et neuf images épinglés ; non déployés ; autres composants à préparer |
| L0-07 | 0 | Contrôle de routes à chaque connexion VPN, refus des conflits, isolation et kill switch | À développer avant activation d'un VPN client ; aucun inventaire futur réputé exhaustif |
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
