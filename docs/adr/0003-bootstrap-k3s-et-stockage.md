# ADR 0003 — Bootstrap K3s épinglé et stockage explicite

Date : 2026-10-11. Statut : proposé, scripts codés, non déployé.

Candidats : K3s v1.35.9+k3s1, CSI v3.7.3, CloudNativePG v1.30.1,
Hermes v0.21.6. Révisions et empreintes de K3s résolues sur les sources officielles.
Kubernetes 1.35 entre dans les plages documentées de CSI 3.7 et CNPG 1.30 ;
cela ne qualifie ni Debian/K3s avec CNPG, ni la version vCenter/ESXi inconnue.
Voir docs/guides/versions-officielles.md. Aucun digest applicatif inventé.

Installation K3s par binaire et bundle airgap vérifiés, script officiel par commit
et SHA256, sans curl|sh ni téléchargement de version flottante. Bootstrap série
du premier serveur puis des suivants via l'endpoint privé. Paramètres critiques
communs, token-file, kubeconfig 0600, secrets-encryption, Flannel VXLAN et moteur
NetworkPolicy K3s conservé. Désactiver traefik, servicelb et local-storage.

Préparer le cloud-provider externe et désactiver le cloud-controller embarqué :
le CPI vSphere compatible et ses provider IDs doivent ensuite être qualifiés
avec le CSI. Pas de retrait manuel de la taint uninitialized pour le contourner.
Les gates de compatibilité/endpoint/réseau/CPI empêchent l'application prématurée.
Une version source vérifiée peut servir au premier bootstrap synthétique après
ces gates ; elle ne devient qualifiée qu'après les essais sur cible. Exiger une
recette de cluster avant ce tout premier bootstrap créerait une dépendance circulaire.

Une réexécution n'adopte aucun K3s préexistant et ne modifie pas sa version ou sa
configuration. Toute dérive exige un runbook de migration distinct. Un marqueur
réservé permet la reprise d'une installation interrompue de ce même lot.

Hermes : un propriétaire actif, volume bloc filesystem Linux, RWOP si qualifié,
fencing avant reprise. Pas de NFS/SMB pour state.db. Ni quorum etcd, ni datastore
partagé, ni ReadWriteOnce ne prouvent la disponibilité métier.
