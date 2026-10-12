# ADR 0008 — Qualification applicative, état exclusif et TLS différé

Date : 12 octobre 2026. Statut : adopté pour le socle synthétique.

## Décision

Déployer CNPG/PostgreSQL/pgvector à trois instances avec réplication synchrone,
et un unique Hermes avec SQLite natif sur PVC RWOP/Recreate. Aucune migration
implicite de l’état Hermes vers PostgreSQL. NGINX répliqué expose l’entrée privée
avec TLS et authentification locale ; il reconstruit les en-têtes proxy.

Deux noms publics demandés : Hermes et futur bot Teams. Le bot reste absent.
Le DNS-01 Certbot est suspendu à la demande de l’utilisateur ; conserver le TLS
auto-signé privé et le compte ACME chiffré jusqu’à reprise explicite.
Les trois réplicas proxy ne créent pas un troisième endpoint public.

## Preuves et conséquences

CSI : cinq checks, dont second writer refusé et déplacement ordonné. Applications :
douze checks, dont switchover PostgreSQL et canari conservé, canari SQLite après
recréation Hermes et refus réseau. HTTPS/auth : six checks. VIP réelles : neuf
sondes API et neuf HTTPS durant bascule contrôlée.

Ces résultats ne qualifient ni perte brutale/fencing, ni sauvegarde/rebuild,
ni Desktop/WebSocket/SSE complet, ni Entra/Teams/RBAC/DLP/VPN/ingestion.
Les incompatibilités de matrice de support demeurent visibles.

La publication publique reste désactivée, même après émission éventuelle d’un
certificat public. Voir [recette](../runbooks/recette-fondatrice.md),
[TLS](../runbooks/certificats-dns.md) et [sécurité](../securite.md).
