# Architecture d’ArcIA

Socle déployé sur une cible de qualification ; données synthétiques uniquement. [Vue produit](plateforme-arcia.md), [schémas](schemas-plateforme-hermes.md), [recette](runbooks/recette-fondatrice.md) et [état de reprise](etat-reprise.md) distinguent le présent des fonctions cibles.

## Hébergement et disponibilité

Trois VM Debian 13 amd64, paramètres initiaux 8 vCPU/32 Gio/150 Gio, réparties sur des ESXi distincts. K3s serveur/control-plane/etcd sur les trois nœuds, containerd et Flannel VXLAN. Keepalived porte des VIP API/HTTPS privées. L’administration reste privée ; NGINX termine TLS et transmet au dashboard Hermes.

La bascule contrôlée des VIP est vérifiée ; panne brutale de nœud, fencing et restauration complète restent à qualifier. Quorum etcd, réplication PostgreSQL et propriétaire SQLite unique sont des mécanismes distincts. Le datastore partagé demeure une dépendance commune.

## Services, données et états

L'identité locale permanente Keycloak est le choix par défaut. Le portail
utilisateurs est exposé en HTTPS privé sur `/admin/users`, avec un compte
personnel sur `/account`. Le namespace `arcia-identity` héberge Keycloak et sa
base CNPG dédiés. Les deux runtimes existants ont un client OIDC et un
propriétaire distincts ; les SSO s'ajoutent par brokering sans remplacer les
comptes locaux. [Administration et limites](identite-utilisateurs.md).

Le namespace `arcia-access` porte le portail `/portal/`, point d'entrée de la
racine du domaine. Un contrôleur unique attribue au premier login un emplacement
fixé `arcia-user-pNN` à la clé issuer/subject. Chaque namespace a ses deux PVC
RWOP, clients et tokens propres ; les runtimes arrêtés et Jobs suspendus sont
préparés par le bootstrap. Le contrôleur peut seulement modifier le binding,
reprendre le Job fixé et scaler deux déploiements précis. Les agents n'ont
aucun ServiceAccount. Un compte supprimé conserve son ancien espace réservé.
Le pool par défaut compte huit places ; HA et restore ne sont pas qualifiés.

| Namespace | Composants | État et stockage |
|---|---|---|
| kube-system / vmware-system-csi | K3s, CPI et CSI | Administration et stockage VMware |
| cnpg-system / arcia-data | CNPG, PostgreSQL/pgvector | 3 instances, PVC 20 Gi chacune, 1 réplica synchrone requis |
| arcia-hermes | Hermes, outils, relais Context7 fermé | État Hermes 10 Gi RWOP ; outils 10 Gi readonly |
| arcia-knowledge | Knowledge | Runtime/modèles 10 Gi readonly ; originaux/assets 20 Gi RWOP |
| arcia-privacy | Presidio, cloud-egress, DNS statique | Runtime/modèles spaCy 5 Gi readonly ; secrets séparés |
| arcia-ingress | NGINX sur les trois nœuds | Certificats protégés ; hostPort 443 vers 8443 non-root |

La StorageClass utilise ext4, WaitForFirstConsumer, Retain et RWOP. Un seul propriétaire écrit chaque état Hermes. Les outils partagent l’image Hermes fixée par digest mais disposent de dépendances isolées. Les nouveaux modèles/documents ne sont pas téléchargés librement par l’agent.

## Requête et réseau

Hermes appelle Knowledge par MCP en lecture seule. Knowledge applique scope et RLS, calcule la recherche localement et ne sort qu’à PostgreSQL/DNS. Les appels modèles passent à Presidio puis à un relais portant seul la clé OpenRouter. Le relais valide attestation, anti-rejeu et politique gratuite/ZDR avant TLS vers sa destination fixée. [Contrôles et limites](confidentialite-cloud.md).

Hermes utilise un DNS statique interne sans forwarding ; Internet direct, DNS général et accès direct au relais sont refusés. Context7 reste installé mais ne peut plus transmettre des requêtes externes non filtrées. Ajouter un MCP demande une autorisation réseau et une recette spécifiques. Les Jobs d’installation peuvent télécharger leurs artefacts HTTPS publics ; ils sont supprimés avant activation du volume runtime RWOP.

## Configuration et réconciliation

Les renderers combinent code/locks et état privé sur stdin. Chaque ressource porte un identifiant d’opération ; une ressource étrangère n’est pas adoptée. Les Secrets utilisent server-side apply, sans copie last-applied en clair. Les agents n’ont pas de token SA, socket d’administration ou PodSpec arbitraire.

Le rendu Hermes conserve configuration, outils, MCP, DNS et passerelle cloud lors d’une réapplication ou rotation TLS. Une ConfigMap immuable portant le hash du contenu sert au montage runtime : le nouveau Pod ne peut pas démarrer avec une ancienne projection mise en cache par le kubelet. La ConfigMap au nom stable reste l’interface des opérations administratives contrôlées.

## Carte du dépôt

| Chemin | Responsabilité |
|---|---|
| AGENTS.md / builder | Rôle de construction, locks et catalogue de skills |
| bootstrap/qualification.json | Ordre, profils et contrats de succès du bootstrap |
| scripts/Bootstrap-Harness.ps1 / BootstrapEngine.ps1 | Orchestration, verrous et journal protégé |
| scripts/*VMware* / infra/ansible | Provisionnement, préflight et K3s |
| scripts/kubernetes_apps.py / hermes_tools.py | Rendu canonique Hermes, outils et entrée |
| services/knowledge / scripts/knowledge_deploy.py | RAG local et intégration MCP |
| services/privacy / scripts/privacy_deploy.py | DLP, protocole attesté, sortie cloud et DNS |
| scripts/Invoke-ClusterFoundation.ps1 / cluster_foundation.py / node_*.py | Opérations administratives fixes sur la cible possédée |
| scripts/ProtectedState.ps1 / PortableState.ps1 | DPAPI/ACL, export/import protégé et résolution du répertoire MSIX |
| versions.lock.yaml / requirements* / builder/*lock* | Versions, dépendances, hashes et digests |
| tests / .github/workflows | Tests synthétiques, coverage bootstrap et CI |

## Extension d’instance

Les usages, corpus, sites, comptes, domaines, habilitations et connecteurs spécifiques sont externes au harness. Une instance fixe une révision d’ArcIA et fournit ses surcharges protégées. Le contrat multi-utilisateur, les espaces communs/restreints/personnels et leur limite actuelle sont détaillés dans [le modèle de partage](plateforme-arcia.md#partage-et-cloisonnement).

## Deux espaces locaux de qualification

Les deux runtimes historiques restent dans leurs namespaces avec état et outillage propres, exposés sur `/qualification-a/` et `/qualification-b/`. Le domaine racine ouvre désormais le portail personnel. Le préfixe est imposé par NGINX, tandis que chaque backend vérifie son propriétaire. La suppression des anciens comptes ne transfère pas ces états vers les nouveaux utilisateurs. La recette historique de connaissance commune + personnelle sous RLS reste dans [multi-utilisateur](multi-utilisateur.md).
