# Sécurité et données privées

État du socle de qualification au 12 octobre 2026. Les exigences métier complètes
restent dans le [plan §5–10](plan-integration-hermes.md). La
[matrice de recette](runbooks/recette-fondatrice.md) distingue les preuves des intentions.

## Frontières actuelles

| Frontière | Contrôle présent | Portée prouvée / limite |
|---|---|---|
| Poste → SSH | Clés hôte validées hors bande, SSH strict, identité ingénieur | Trois VM désignées ; pas de confiance par réseau seul |
| Poste → VMware | Certificat accepté et contrôlé, compte technique borné | Accès et refus de droits dangereux testés ; inventaire protégé |
| Cluster → données | Secrets K3s chiffrés, PVC CSI, états séparés | Chiffrement Kubernetes vérifié ; pas de preuve du chiffrement complet du datastore |
| Entrée → Hermes | TLS épinglé, authentification scrypt locale, cookies Secure/HttpOnly | 6 checks réussis ; OIDC/Entra et révocation métier absents |
| Proxy → backend | NetworkPolicy par namespace et label, en-têtes reconstruits | Entrée privée contrôlée ; le CIDR de proxies de confiance reste borné |
| Hermes → réseau | Egress deny-all, aucune clé LLM | DNS et connexion DB inter-namespace refusés ; aucun appel IA |
| Hermes → hôte/Kubernetes | Non-root, racine readonly, sans token SA/socket runtime | Pas d’administration cluster depuis le runtime |
| Hermes → état | RWOP, un replica, Recreate | Second écrivain CSI refusé ; panne brutale/fencing restant |

Le refus Hermes → PostgreSQL est observé avec des politiques aux deux extrémités ;
il ne démontre pas à lui seul laquelle bloque le paquet. Une règle déclarée ou
une ConfigMap safe-mode n’est pas une preuve universelle d’isolation.

## État administratif et secrets

`%LOCALAPPDATA%\ArcIA-Harness` contient les bundles DPAPI, la clé SSH et les
références d’inventaire. Sa racine a des ACL restreintes. Les wrappers déchiffrent
dans leurs processus, transmettent les paramètres privés par stdin et capturent
les diagnostics avant rechiffrement. Le modèle reçoit des codes/compteurs.

Ne pas afficher bundles, kubeconfigs, sorties `get secret`, logs bruts, transits
Ansible, comptes ACME ou fichiers de credentials. Les scripts de diagnostic
non suivis préexistants ne sont pas des interfaces approuvées. Les mots de passe,
OTP et clés sont saisis uniquement dans un programme local protégé.

DPAPI protège l’état pour le compte Windows courant ; ce n’est pas une clé
portable. L’archive portable chiffre après conversion des bundles et se restaure
sous le nouveau compte. Son mot de passe reste dans le gestionnaire personnel,
hors dépôt et chat. Voir [transfert](runbooks/transfert-second-pc.md).

## Exception d’entrée

Le namespace `arcia-ingress` autorise le hostPort nécessaire au proxy. Son niveau
PSA est une exception technique documentée ; les conteneurs NGINX restent UID101,
non privilégiés, sans capabilities, sans élévation ni token Kubernetes.
Cette exception ne s’étend pas à Hermes ni aux futurs exécuteurs.

## Protections métier à construire

Entra identifie par tenant/object_id ; le serveur décide du client, de la mission
et des droits. Les coffres/VPN restent personnels. Une écriture cliente exige
plan immuable, approbation Teams vérifiée, capacité unique et recontrôle.
Une interruption impose réconciliation, jamais rejeu aveugle.

La future passerelle IA traite l’intégralité du payload, y compris extraits RAG,
historique et sorties d’outils. Données brutes, OCR et embeddings privés restent
locaux. Les caches respectent le même périmètre. Aucun client réel ne doit être
activé avant qualification de ces services et du kill switch VPN.

## GitHub et récupération

Le harness contient code générique, tests synthétiques et preuves assainies.
Configurations privées, données et sauvegardes sont chiffrées avant tout dépôt
privé. Les clés externes restent séparées. Le dépôt actuel reste privé ; une
publication publique nécessite la revue prévue au plan.
Un administrateur root appartient à la frontière de confiance et peut observer
les secrets utilisés sur sa machine. Réplication et stockage partagé ne sont
pas des sauvegardes ; voir [reconstruction](runbooks/sauvegarde-reconstruction.md).
