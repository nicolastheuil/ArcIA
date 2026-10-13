# Backlog ArcIA — 13 octobre 2026

Référence : [handoff courant](handoff-2026-10-13-skills-catalogue.md).
Complément : [préparation Microsoft 365](handoff-2026-10-13-microsoft365.md).
La [recette](runbooks/recette-fondatrice.md) définit la portée de « vérifié ».
Périmètre courant : socle/Hermes synthétiques, documentation, outils dans Hermes/K3s et recherche documentaire locale. Les adaptations d’usage appartiennent aux dépôts d’instance ; qualification multi-utilisateur locale exécutée sur fixtures synthétiques.

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
| L0-02b | TLS public pour les deux noms demandés | Certificat Let’s Encrypt émis/collecté/déployé ; renouvellement DNS manuel et migration du compte ACME restants |
| L0-02c | Entra/OIDC métier et bot Teams | À développer ; hors socle actuel |
| M365-01 | Annexe administrateur, YAML d'instance, schéma strict et plan hors ligne | Codés ; aucun accès/configuration tenant ; [annexe](annexes/integration-microsoft365.md) |
| M365-02 | Wizard/importeur protégé, adaptateurs OIDC/Bot/Graph et export assaini | À développer ; contrat v1 interdit toute activation |
| M365-03 | IAM/ACL, approbations Teams, collecte/synthèse, scopes et révocation | À développer puis recette synthétique ; aucune donnée réelle autorisée |
| M365-AUTH-01 | Sortie HTTPS du broker Microsoft Keycloak | IPv4 publique TCP/443 déployée sur instruction explicite, destinations au pare-feu amont ; snapshot retiré, TLS Microsoft/Graph 4/4 et refus HTTP/80 vérifiés ; [reprise](handoff-2026-10-13-identity-public-https.md) |
| IAM-LOCAL-01 | Annuaire local permanent par défaut et portail admins | Keycloak 26.8.1, PostgreSQL dédié, `/admin/users` ; administration native déployée, 15 contrôles exécutés |
| IAM-LOCAL-02 | Raccordement des espaces, sessions et identité stable | Provider OIDC public PKCE, validation UserInfo/propriétaire ; 12 contrôles HTTPS et 200 d'isolation réussis ; [handoff](handoff-2026-10-13-identite.md) |
| IAM-LOCAL-03 | Coexistence local/SSO, nouveaux runtimes et ACL de groupes | Brokering documenté ; tenant réel, launcher général, ACL dynamiques et restore/HA à qualifier |
| IAM-LOCAL-04 | Espace personnel vide au premier login | Portail PKCE, pool borné, binding issuer/subject et contrôle administratif limité ; [handoff](handoff-2026-10-13-portail-personnel.md) |
| IAM-LOCAL-05 | Cycle de vie et capacité des espaces | Transfert explicite, purge, récupération d'emplacements, migration d'outils actifs et sauvegarde/restore restent à qualifier ; aucun recyclage automatique |
| IAM-LOCAL-06 | Récupération admin nommé et admission automatique du tenant Microsoft | Appliquées sur exception limitée ; realm-admin et ArcIA.User fédéré relus ; pool privé 32 places, nettoyage explicite d'un compte supprimé ; recette interactive et charge simultanée à compléter ; [reprise](handoff-2026-10-13-identity-public-https.md) |
| L0-03 | Policy/RBAC, sanitizer, sortie IA unique | Presidio/gateway/DNS déployés et réponse gratuite vérifiée ; deux espaces locaux qualifiés ; IAM central restant |
| L0-04 | Launcher typé, VPN personnel, reaper/kill switch | À développer ; pas de VPN actif |
| L0-05 | Backups cohérents, restore sûr, rebuild neuf | À développer/qualifier ; import poste seul déjà vérifié |
| L0-06 | Outils, catalogue, provenance/licences | Dans K3s ; 539 entrées upstream, 7 adaptations/orientations natives ; 55 sondes par runtime. RTK git log et Headroom JSON intégrés ; OmniRoute automatique différé |
| L0-07 | Routes à chaque connexion VPN et conflits | À développer avant activation VPN ; aucun inventaire futur exhaustif |
| L1 | Registre/RBAC, coffres individuels, collecte/rapports en lecture | Après frontières lot 0 |
| L2 | Plans immuables, approbations Teams, capacités uniques/réconciliation | Après L1 |
| L3 | Catalogue, Docling/OCR, embeddings locaux, recherche hybride/ACL/citations | Hybride + multi-vecteur, PDF textuels/API/schémas, RLS/citations et MCP déployés/vérifiés synthétiquement ; OCR, ColPali, collecte/import dédié, file durable et benchmark corpus large restants |
| L4 | Fencing/panne de nœud, cinq missions, deuxième ingénieur/rebuild/SBOM | Gate de release |
| L5 | Réduction du contexte et autres options | RTK borné et Headroom sur lectures JSON qualifiés ; proxy/mémoire Headroom écartés. OmniRoute automatique, Graphify/Ponytail différés |

| BOOT-01 | Bootstrap exhaustif et coverage CI | Codé, Audit/Reconcile existants vérifiés ; rebuild neuf restant |
| MU-01 | Identités, états personnels, connaissance commune et refus croisés | Deux identités locales : 200 contrôles réussis, dont 90 d'isolation/corpus et 55 sondes d'outillage par runtime ; SSO, groupes et provisioning général restants |

Aucun conteneur factice ne remplace un service métier manquant.
La réussite du socle n’atteste pas les contrôles IAM/DESK/SEC/VPN/APR/DLP/KB/LLM
du [plan complet](plan-integration-hermes.md). Le stockage et la réplication ne
constituent pas une sauvegarde. Ne pas publier de release avant recette/rebuild.

## Évolution du 13 octobre — skills et réduction du contexte

Catalogue complet des sources retenues : 539 entrées, découverte locale MCP,
58 skills Hermes embarquées exposées nativement, sept adaptations/orientations.
Mémoire/délégation Hermes ; pas de mémoire/apprentissage ECC ni d’orchestrateur
supplémentaire. RTK automatique borné à git log ; Headroom réduit les gros
résultats JSON de lectures déclarées avant contexte, avec original récupérable,
sans proxy ni mémoire partagée. Sources, crédits et licences
verrouillés ; vérification upstream par script/workflow manuel. Voir le
[handoff du 13 octobre](handoff-2026-10-13-skills-catalogue.md) pour les résultats
exécutés. Qualification individuelle des centaines de procédures et comparaison
de qualité sur des missions représentatives restent à faire.
