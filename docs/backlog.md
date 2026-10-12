# Backlog ArcIA — 12 octobre 2026

Référence : [handoff courant](handoff-2026-10-12-qualification-verifiee.md).
La [recette](runbooks/recette-fondatrice.md) définit la portée de « vérifié ».
Périmètre courant : socle/Hermes synthétiques, documentation et outillage builder
retenu au §25. Les services métier ne sont pas activés par cette demande.

| ID | Travail | État réel / suite |
|---|---|---|
| PREP-01 | Sources intégrales, inventaire, backlog/ADR | Réalisé ; documentation actualisée |
| PREP-02 | Versions et artefacts épinglés | Images/hashes fixés ; support et lock de release incomplets |
| PREP-03 | Wizard, DPAPI/ACL, configuration privée | Codé et utilisé ; export portable actuel à renouveler |
| PREP-04 | SSH hors bande et préflight | Vérifié 3/3 |
| PREP-05 | K3s trois serveurs | Déployé/vérifié ; wrappers et extraction au démarrage à revoir |
| PREP-06 | Namespaces, quotas, comptes et réseau | Appliqué pour apps ; refus Hermes observés, admission métier à compléter |
| PREP-07 | GitHub dédié privé | Créé ; privé et droits d’écriture revérifiés |
| PREP-08 | VM, identités et domaines ESXi | Vérifié 3/3 avec anti-affinité |
| PREP-09 | CPI/CSI, compte technique et stockage | Déployé ; 5 essais CSI réussis ; fencing brutal/RWX restants |
| PREP-10 | VIP API/HTTPS et réseau privé | Bascule réelle contrôlée vérifiée, 18 sondes ; panne brutale restante |
| L0-01 | CNPG/PostgreSQL/pgvector | Déployé 3/3 ; 6 checks SQL/réplication/switchover réussis |
| L0-02a | Hermes et HTTPS locaux | Déployé ; 6 checks Hermes, 6 HTTPS/auth ; Desktop/WS/SSE restants |
| L0-02b | TLS public pour les deux noms demandés | Certbot prêt, demande suspendue par utilisateur ; reprise après DNS |
| L0-02c | Entra/OIDC métier et bot Teams | À développer ; hors socle actuel |
| L0-03 | Policy/RBAC, sanitizer, sortie IA unique | À développer et tester avant client/appel cloud |
| L0-04 | Launcher typé, VPN personnel, reaper/kill switch | À développer ; pas de VPN actif |
| L0-05 | Backups cohérents, restore sûr, rebuild neuf | À développer/qualifier ; import poste seul déjà vérifié |
| L0-06 | Outils builder §25, provenance/licences | Context7/skills/LintLang installés ; 6 skills Superpowers/ECC, hashes/licences ; MCP/requête générique et scans vérifiés ; chargement au prochain tour |
| L0-07 | Routes à chaque connexion VPN et conflits | À développer avant activation VPN ; aucun inventaire futur exhaustif |
| L1 | Registre/RBAC, coffres individuels, collecte/rapports en lecture | Après frontières lot 0 |
| L2 | Plans immuables, approbations Teams, capacités uniques/réconciliation | Après L1 |
| L3 | Catalogue, Docling/OCR, embeddings locaux, recherche hybride/ACL/citations | Conception documentée ; aucun pipeline opérationnel |
| L4 | Fencing/panne de nœud, cinq missions, deuxième ingénieur/rebuild/SBOM | Gate de release |
| L5 | RTK/Graphify pilotes, compression/Headroom et autres options | Désactivés tant que qualification non conclue |

Aucun conteneur factice ne remplace un service métier manquant.
La réussite du socle n’atteste pas les contrôles IAM/DESK/SEC/VPN/APR/DLP/KB/LLM
du [plan complet](plan-integration-hermes.md). Le stockage et la réplication ne
constituent pas une sauvegarde. Ne pas publier de release avant recette/rebuild.
