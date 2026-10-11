# Sources VMware épinglées — non déployées

Ces manifests proviennent des projets Kubernetes vSphere CPI et CSI sous licence
Apache 2.0, conservée dans les deux fichiers LICENSE. Seules les références
d'images ont été remplacées par les digests OCI résolus auprès de registry.k8s.io.
URLs, commits, SHA256 amont et rendus sont dans `versions.lock.yaml` ; la CI
vérifie les rendus et toutes les références d'images.

Régénération explicite : `python scripts/pin_vmware_images.py`. Aucun apply,
aucune création de secret ni changement de VM par ce programme. Il ne doit pas
être exécuté implicitement lors du déploiement : utiliser les artefacts versionnés.

Ces fichiers ne constituent pas encore un overlay installable. Revoir les labels
K3s, le namespace privilégié CSI limité aux composants techniques, les affinités,
les snapshots/CRD, les certificats et le compte technique vCenter de moindre droit.
Ne pas y insérer les identifiants de l'ingénieur. Les credentials/configurations
réelles seront rendus uniquement par le programme local protégé. Compatibilité
vSphere 9.1.1 et tests PVC/fencing restent à qualifier sur les cibles désignées.
