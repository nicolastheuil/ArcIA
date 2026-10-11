# Socle de qualification

`foundation/` contient seulement cinq namespaces, PSA restricted version 1.35,
deny-all ingress/egress, DNS vers CoreDNS, ServiceAccounts sans token automatique,
quotas et LimitRanges. Pas de workload applicatif, Ingress, secret ou permission
de création de Pods. Le namespace d'exécution VPN exige une admission spécifique
encore à développer ; il n'est pas créé avec des permissions trop larges.

La ConfigMap safe-mode exprime l'intention de qualification. Elle ne constitue pas
un mécanisme d'autorisation : les futurs services doivent l'appliquer, et les
politiques réseau doivent être testées sur cible. Aucun accès client n'est possible
via ce socle seul. Ajouter les flux internes un à un avec tests négatifs.

Après bootstrap autorisé sur cibles désignées et contrôle du contexte kubectl :

```bash
kubectl kustomize deploy/foundation
kubectl apply --dry-run=server -k deploy/foundation
kubectl apply -k deploy/foundation
```

Ces commandes ne sont pas exécutées pendant la préparation. Le dry-run serveur
requiert un cluster. Les quotas par namespace ne sont pas une réservation globale
de capacité : mesurer et ajuster le budget deux nœuds et les cinq missions.

Hermes, ingress, CPI/CSI et PostgreSQL restent à ajouter après qualification des
images par digest. Le UID/GID et le superviseur s6 de l'image Hermes officielle
doivent être testés avant de décider son SecurityContext ; ne pas inventer un
Deployment Running en désactivant les contrôles du namespace.
