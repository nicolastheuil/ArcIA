# ADR 0001 — Cible fondatrice et périmètre de préparation

Date : 2026-10-11. Statut : accepté par le cadrage.

Trois VM Debian 13 x86_64, K3s serveurs avec etcd embarqué ; 8 vCPU, 32 Gio
et 150 Gio système proposés par VM. CSI VMware partagé, endpoint API privé et
entrée HTTPS avec bascule à qualifier. Compose/Kilo facultatifs seulement.

Ce lot prépare le bootstrap et les gates ; il n'implémente pas les services métier
du lot 0. Les manifests livrés établissent un socle fermé sans runtime ni entrée
publique. Aucun accès périmètre et aucun déploiement distant dans cette préparation.

Destination confirmée par l'utilisateur : **nicolastheuil/ArcIA**.
Cette instruction remplace les noms proposés aux §4 et §26. Les VM sont à créer.
Identité GitHub connectée vérifiée comme nicolastheuil ; Git local initialisé
après confirmation. Aucun dépôt d'instance/périmètre/récupération créé dans ce lot.
