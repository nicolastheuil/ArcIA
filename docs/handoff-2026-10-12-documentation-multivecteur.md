# Handoff — outils K3s, TLS et connaissance documentaire

## Décisions utilisateur effectives

Livrer directement sur **main** du dépôt privé nicolastheuil/arcia-harness, sans nouvelle branche ni PR. Tous les outils applicatifs résident dans le cluster K3s, à disposition d’Hermes. Le poste conserve uniquement le contrôleur administratif existant et, provisoirement, le compte/runtime ACME à migrer. Qualification synthétique uniquement ; services métier et appels IA désactivés.

## Réalisé et vérifié

- Main a reçu le précédent lot par avance rapide et push ; les changements de ce lot sont à identifier par le commit de livraison.
- Certificat Let’s Encrypt DNS-01 émis pour arcia.arcitek.io et arcia-teams.arcitek.io, collecté sous protection et appliqué à NGINX ; 7 contrôles HTTPS/auth réussis, dont chaîne CA publique et hostname. Teams et NAT public absents.
- Anciennes installations Context7/skills/LintLang ArcIA-Builder du poste et MCP Codex supprimés, avec sauvegarde protégée ; six skills déplacés dans le catalogue runtime Hermes.
- PVC Hermes tools 10 Gi RWOP, montage lecture seule : Context7 4.3.0, skills 1.7.2, LintLang 0.8.2, RTK 0.51.0, Headroom 0.40.0, OmniRoute 3.8.51 et Certbot 5.8.0. CLI/imports, 6 skills natifs, Context7 réel générique, refus Internet direct et MCP Knowledge vérifiés. Hooks, compression automatique et fournisseurs IA désactivés.
- Service Knowledge privé dans arcia-knowledge : modèles E5 et mLateOn locaux, FTS/pgvector/HNSW, RRF puis MaxSim, RLS avec rôle non propriétaire, versions, sources/empreintes et fichiers éditables. Deux PVC : runtime 10 Gi, données 20 Gi, RWOP. Modèles et dépendances fixés par révision/hash.
- Recette synthétique : 25 contrôles Knowledge réussis, dont PDF textuel/page illustrée, OpenAPI, déduplication, version, schéma dérivé, recherche/citations, refus A/B recherche/asset, lecture seule/anonyme/scope, XML actif/référence distante, RLS, refus réseau et modèles lecture seule. Recherche de fixture environ 0,13–0,14 s, sans extrapolation au corpus réel.
- Accès dashboard corrigé : découverte du répertoire protégé Codex/MSIX depuis un terminal Windows, formulaire de credentials local et ouverture Edge avec résolution privée sans modification DNS/hosts. Fenêtre locale effectivement ouverte ; login HTTP vérifié par programme, interaction navigateur restant à confirmer par l’utilisateur.
- Les manifests canoniques conservent les outils et les deux MCP lors de la réapplication Hermes ; rotation de configuration déclenche le rollout.

## Validation des sources

107 tests Python réussis sous Linux/WSL. Validation JSON/YAML, empreintes vendor/skills, images par digest, syntaxe Ansible et gate synthétique avant SSH réussis. Tests Windows DPAPI/ACL/résolution physique, archive portable, DNS et SSO exécutés séparément avec leur runtime approprié. 146 liens de fichiers documentaires contrôlés sans cible manquante. La validation Mermaid est ajoutée à la CI avec dépendances fixées, sans installation de runtime sur le poste.

## Commandes de reprise

```powershell
./scripts/Invoke-ClusterFoundation.ps1 -Action inspect_knowledge
./scripts/Invoke-ClusterFoundation.ps1 -Action verify_knowledge
./scripts/Invoke-ClusterFoundation.ps1 -Action verify_hermes_tools
./scripts/Verify-PilotAccess.ps1
```

L’état d’administration, les inventaires, credentials et résultats détaillés sont protégés sous LOCALAPPDATA/ArcIA-Harness. Ne pas afficher de bundle ou de log privé brut. Les statuts assainis distinguent échec et vérification réussie. Ne pas ajouter les anciens scripts de debug et handoffs privés non suivis à Git.

## Limites et prochaines gates

1. Migrer le compte ACME et le parcours DNS-01 vers K3s ; supprimer ensuite le runtime Certbot WSL. Aucun renouvellement autonome en DNS manuel ; prévoir nouveau TXT et recette avant expiration.
2. Ajouter interface d’import opérateur, collecte catalogue/licences, file durable et publication/réindexation par génération ; réconcilier les assets orphelins après échec. L’API d’ingestion privée est réservée aux tokens opérateur.
3. Qualifier Docling/OCR et ColPali sélectif. Les PDF scannés sont actuellement refusés ; les schémas PDF sont recherchés par leur texte associé, sans compréhension visuelle autonome. Draw.io compressé préservé sans extraction complète des libellés.
4. Benchmark représentatif des manuels/API/schémas : pertinence, extraction, versions, droits, p50/p95, CPU/RAM, WAL/disque. Les limites actuelles de stockage ne garantissent pas un corpus de centaines de PDF.
5. Modèles/dépendances Knowledge : mise à jour nécessitant démontage contrôlé, refusée à chaud. Les changements de code seuls redéploient via Recreate. Ne pas partager l’écriture des volumes.
6. IAM Entra/Teams, policy/approbations, VPN/coffres, sanitizer cloud restent hors socle. Ne pas activer OmniRoute/fournisseurs sans qualifier cette frontière.
7. Panne brutale/fencing, sauvegarde cohérente et reconstruction sur cluster neuf restent non qualifiés. Renouveler l’archive portable privée avant transfert ; elle ne sauvegarde pas les volumes actifs.

Documentation d’usage : [README](../README.md), [Knowledge](connaissance-documentaire.md), [outillage](outillage-builder.md), [certificats](runbooks/certificats-dns.md), [backlog](backlog.md).
