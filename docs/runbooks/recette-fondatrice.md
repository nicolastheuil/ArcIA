# Recette à exécuter sur les cibles futures

Statut : plan de tests, aucun scénario distant exécuté.

| Gate | Scénario / preuve attendue |
|---|---|
| VM-01 | Trois identités uniques ; Debian, CPU/RAM/disque, NTP/cgroups ; preuve assainie |
| NET-01 | API stable sous arrêt d'un backend ; TLS-SAN et sondes vérifiés |
| NET-02 | Recouvrement CIDR et flux interdits ; isolation de Pods inter-nœuds |
| K3S-01 | Trois serveurs etcd Ready, version verrouillée, secrets-encrypt Enabled |
| K3S-02 | Deuxième apply sans reset, identité/token stables ; drift refusé |
| CSI-01 | PVC bloc filesystem, lecture après remplacement, déplacement inter-nœuds |
| CSI-02 | Double propriétaire refusé ; panne brutale puis fencing réel avant reprise |
| PG-01 | Réplication, bascule et cohérence de queue sans rejouer une écriture client |
| HA-01 | Perte d'un nœud : entrée, contrôle et données mesurés, domaines de panne relevés |
| SAFE-01 | Aucun VPN/accès client/notification prod en qualification et restore |
| APP-01 | Toute recette métier §19, compléments §25 et scaling §26 exécutés |
| REC-01 | Rebuild neuf avec deuxième ingénieur et récupération externe |

Conserver scénario, commit/lock, dates, cible opaque, résultat mesuré et référence
de preuve locale. Les inventaires, captures réseau et journaux bruts restent
protégés ; aucun test de fuite utilisant des secrets réels. Une ligne proposée
ou un test unitaire réussi ne valide pas ces gates.
