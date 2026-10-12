> Instantané historique de qualification. Voir l’état de reprise pour le statut courant ; les noms d’exemple sont synthétiques.

# Handoff — socle vérifié et documentation — 12 octobre 2026

Référence courante. Périmètre autorisé : socle et Hermes de qualification, puis
documentation complète et installation des outils retenus au §25 du plan.
Ce handoff remplace le point d’arrêt HTTPS du handoff précédent.

## Vérifié sur les cibles désignées

- K3s trois serveurs Ready/control-plane/etcd, API privée/VIP et chiffrement.
- CPI 1.37.0, CSI 3.7.3 ; cinq contrôles RWOP/persistance réussis et volume de
  recette supprimé. StorageClass applicative ext4/WFFC/Retain.
- CNPG 1.30.1 opérateur 2/2 ; PostgreSQL 18.6, trois instances distinctes ;
  pgvector, réplication synchrone, canari réplique, switchover et canari conservé.
- Hermes 0.21.6 1/1, SQLite natif exclusif, canari SQLite conservé après
  recréation ; refus DNS et connexion base inter-namespace observés.
- NGINX 1.31.6 3/3 ; correction des chemins temporaires appliquée ; TLS,
  anonymat/mauvais mot de passe refusés, login et cookies Secure/HttpOnly vérifiés.
- Bascule contrôlée Keepalived avec vrais services : 9 sondes API + 9 HTTPS,
  propriétaire unique, retour sans préemption ; service arrêté rétabli.

Canaris SQL/SQLite retirés. Aucun appel IA ni environnement privé. Le Pod fondation
non Ready examiné était un Job Succeeded, sans Pending/Failed correspondant.

## DNS, TLS et reprise

Hermes utilise `assistant.example.org`. `assistant-teams.example.org` est réservé au futur
bot, absent. Identifiants/session et clé pilote préservés pendant migration du
hostname ; certificat auto-signé renouvelé pour le nom Hermes.

L’utilisateur a demandé de différer la vérification DNS : Certbot est suspendu,
statut `ACME_DNS_VALIDATION_DEFERRED`, compte/challenges checkpointés dans DPAPI.
Ne pas reprendre les contrôles en arrière-plan. Les valeurs TXT déjà communiquées
peuvent devoir changer avec un nouvel ordre. Voir [runbook TLS](runbooks/certificats-dns.md).

La collecte d’un certificat public est codée, non exécutée. NAT public désactivé.
La publication attend les contrôles métier, indépendamment de TLS.

## Preuves privées et validations locales

Sous `%LOCALAPPDATA%\ArcIA-Harness` : `cluster-qualify_storage-status.json`
(5 checks), `cluster-qualify_apps-status.json` (12),
`cluster-qualify_live_vip-status.json` (18 sondes), `pilot-access-status.json`
(6), et `certificate-request-status.json` (deferred). Preuves détaillées DPAPI,
credentials pilote et compte ACME protégés. Ne pas afficher les bundles/logs.

98 tests Python WSL réussis ; schéma/JSON/YAML, hashes VMware/CNPG, digests
applicatifs, syntaxe Ansible et refus synthétique avant SSH vérifiés.
Voir [rapport de vérification](verification-preparation.md).

L’archive portable actuelle est antérieure à ces lots : renouveler localement
avant transfert. Ne pas importer l’ancienne archive sur l’état courant.

## Restant et précautions

WebSocket/SSE et Desktop complet ; perte brutale de nœud/fencing ; kill switch
VPN ; sauvegardes cohérentes et rebuild neuf ; revue des wrappers K3s hérités
et du nettoyage d’extraction au démarrage ; paquets/locks/SBOM/support.
CNPG/CSI sur Kubernetes 1.37 ont des limites de support non levées par les tests.
Les services métier et l’ingestion restent absents.

La documentation opérationnelle est désormais accessible depuis
[l’index](README.md) et le [README principal](../README.md). Le statut précis de
l’installation builder est suivi dans [l’outillage](outillage-builder.md).
Context7/skills/LintLang installés, MCP/requête publique et scans vérifiés ;
six skills Superpowers/ECC ciblés dans `.agents/skills`, invocation explicite,
sans hooks ni apprentissage. 19 schémas Mermaid parsés, 128 liens locaux vérifiés,
50 scripts PowerShell parsés. Le scan LintLang n’atteste pas la sécurité.
Aucune déclaration HA de production ni release installable.

## Livraison GitHub

Les commits de réalisation sont publiés sur `codex/socle-qualification-handoff`.
La [PR nº1](https://github.com/nicolastheuil/arcia-harness/pull/1) reste en
brouillon, sans fusion dans `main`. La [CI Linux et Windows
nº12](https://github.com/nicolastheuil/arcia-harness/actions/runs/38287969991)
a réussi sur `21647b838d6893d98b32eb7581e09e3f6724fed5` : tests Python,
validation des sources, scan LintLang, parsing PowerShell et tests protégés
Windows. Cette mention de livraison est un ajout documentaire ultérieur.
