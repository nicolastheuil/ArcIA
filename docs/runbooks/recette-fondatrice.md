# Recette fondatrice — état au 12 octobre 2026

Les lignes « vérifié » correspondent aux scénarios exécutés sur les seules VM
de qualification. Les preuves détaillées restent chiffrées ; leurs statuts
assainis sont sous `%LOCALAPPDATA%\ArcIA-Harness`.
La [vérification locale](../verification-preparation.md) est distincte de cette recette.

## Matrice actuelle

| Gate | Résultat observé | État / limite |
|---|---|---|
| VM-01 | Trois Debian 13, identités uniques, ressources/NTP/cgroups/SSH et anti-affinité sur 3 ESXi | Vérifié ; inventaire privé |
| NET-01 | 54 contrôles de ports, transport VIP puis API/HTTPS réelles | Vérifié pour bascule contrôlée ; pas de panne brutale |
| NET-02 | CIDR comparés aux routes visibles ; refus Hermes DNS/DB | Partiel ; futurs VPN inconnus, isolation métier à construire |
| K3S-01 | 3 serveurs Ready/etcd, version épinglée, Secrets chiffrés et hashes cohérents | Vérifié |
| K3S-02 | Réutilisation d’identités, ressources annotées, refus d’objets étrangers | Partiel ; idempotence/rebuild complet non qualifiés, wrappers hérités à revoir |
| CSI-01 | Provisionnement/lecture, recréation, déplacement ordonné, suppression synthétique | Vérifié : 5 checks avec CSI-02 partiel |
| CSI-02 | Deuxième writer RWOP refusé | Vérifié ; panne brutale/fencing et RWX non qualifiés |
| PG-01 | 3 nœuds distincts, SQL vectoriel, réplique synchrone, canari réplique, switchover, canari conservé | Vérifié : 6 checks ; pas de queue métier ni crash primaire testé |
| HERMES-01 | SQLite natif présent, canari séparé persistant après recréation, propriétaire unique | Vérifié : 4 checks ; migration/sessions complètes non testées |
| HERMES-02 | DNS et connexion DB inter-namespace refusés | Vérifié : 2 checks ; politiques aux deux extrémités pour DB |
| TLS-01 | TLS/hostname/leaf épinglé, anonymat et mauvais login refusés, login, cookies, config authentifiée | Vérifié : 6 checks, certificat auto-signé |
| TLS-02 | Certbot DNS-01 et checkpoint protégé | Demande suspendue ; émission/collecte publiques non exécutées |
| ENTRY-01 | 3 phases × 3 nœuds × API + HTTPS durant bascule Keepalived | Vérifié : 18 sondes, propriétaire unique et retour sans préemption |
| ENTRY-02 | WebSocket/SSE, Desktop et callbacks Teams | Config proxy codée ; recette complète non exécutée, Teams absent |
| HA-01 | Arrêt brutal d’un nœud/ESXi, mesures interruption/perte | À exécuter ; aucun statut HA de production |
| SAFE-01 | Aucun credential LLM, aucun VPN/client ni notification métier activé | Vérifié pour périmètre synthétique ; safe-mode métier non implémenté |
| APP-01 | IAM/DESK/SEC/VPN/APR/DLP/KB/LLM/LOAD du plan | À développer/qualifier |
| REC-01 | Sauvegarde cohérente cluster et rebuild neuf par deuxième ingénieur | Non exécuté |
| POSTE-01 | Import portable sous nouveau compte, bundles/fichiers/ACL relus | Vérifié sur ancien snapshot ; nouvel export requis |

## Preuves disponibles

| Statut assaini | Scénario / code |
|---|---|
| `cluster-inspect_cluster-status.json` | `K3S_API_VIP_ENCRYPTION_VERIFIED` |
| `cluster-qualify_storage-status.json` | `CSI_RWOP_PERSISTENCE_VERIFIED`, 5 checks |
| `cluster-qualify_apps-status.json` | `APPLICATION_PERSISTENCE_SWITCHOVER_ISOLATION_VERIFIED`, 12 checks |
| `pilot-access-status.json` | `PILOT_HTTPS_AUTH_VERIFIED`, 6 checks |
| `cluster-qualify_live_vip-status.json` | `LIVE_API_HTTPS_VIP_FAILOVER_VERIFIED`, 18 sondes |
| `certificate-request-status.json` | `ACME_DNS_VALIDATION_DEFERRED` |

Les fichiers sont des instantanés datés dans l’état privé, pas une surveillance
continue. Les preuves DPAPI associées donnent le détail de l’opération.
Les canaris sont synthétiques et ont été retirés après succès.
Aucun test de fuite n’emploie de secret réel.

## Rejouer et compléter

Les commandes et leurs effets sont dans
[l’exploitation](exploitation-qualification.md). Les recettes stockage,
applications et VIP modifient temporairement le socle ; réserver une fenêtre.
Ne pas confondre switchover PostgreSQL et crash automatique du primaire.

Pour tout nouvel essai : consigner scénario, commit/lock, date, cible opaque,
résultat, nettoyage et référence privée. Les compteurs ne prouvent que les
assertions du scénario ; ne pas extrapoler à l’ensemble de la plateforme.
Une release exige les gates restants du [plan §19/25/26](../plan-integration-hermes.md)
et [la reconstruction](sauvegarde-reconstruction.md).
