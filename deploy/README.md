# Ressources Kubernetes du harness

Le socle est déployé en qualification. Voir
[architecture](../docs/architecture.md), [recette](../docs/runbooks/recette-fondatrice.md)
et [exploitation](../docs/runbooks/exploitation-qualification.md).

## Sources et rendu

`foundation/` contient les namespaces/politiques/quotas statiques de préparation,
sans secrets réels. `vendor/vmware/` conserve CPI/CSI et licences ;
`vendor/cnpg/` conserve le manifeste opérateur et sa licence. Hashes et images
épinglées sont contrôlés contre `versions.lock.yaml`.

Les ressources applicatives réelles sont générées par
`scripts/kubernetes_apps.py` et celles VMware par `scripts/kubernetes_vmware.py`.
Le wrapper protégé fournit les paramètres sur stdin et le worker applique les
objets appartenant à l’opération. Ne pas enregistrer les manifests privés
rendus ni les Secrets dans ce dossier.

## Contrôles et exceptions

Hermes : non-root, racine readonly, pas de token Kubernetes, PVC RWOP/Recreate,
egress deny-all. NGINX : UID101 et même durcissement ; exception PSA du namespace
pour hostPort443, sans container privilégié ni capabilities. CNPG/PostgreSQL
a ses flux de réplication/opérateur bornés et des quotas applicatifs.

La ConfigMap safe-mode exprime une intention, pas une implémentation des futures
autorisations métier. Le namespace VPN et ses permissions restent à construire.

## Usage

L’inspection générique `kubectl kustomize deploy/foundation` ne déploie pas
les applications. Sur l’instance existante, utiliser les actions administratives
du runbook, avec contrôle de cible et verrou d’opération. Un apply direct non
journalisé ne remplace pas ce parcours.

Réplication, storage partagé et Pods Ready ne suffisent pas à qualifier panne
brutale/fencing, backup ou rebuild. La politique applicative `Retain` conserve
les données après suppression de claim ; aucune purge implicite autorisée.
