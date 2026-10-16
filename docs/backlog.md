# Backlog ArcIA — 16 octobre 2026 (v0.2)

Référence courante : [état de reprise](etat-reprise.md).
L'[architecture](architecture.md) définit le périmètre technique et les exigences du socle déployé.
Périmètre courant : socle unifié ArcIA v0.2 (Open-WebUI, Hermes Agent, LiteLLM, Presidio DLP, Teams Bot, OmniRoute) déployé sur le namespace `arcia` avec persistance VMware vSphere CSI.

| ID | Travail | État réel / suite |
|---|---|---|
| PREP-01 | Sources intégrales, inventaire, architecture/backlog | Réalisé ; documentation actualisée |
| PREP-02 | Versions officielles et manifestes épinglés | Images et digests fixés dans [versions officielles](guides/versions-officielles.md) |
| PREP-04 | SSH hors bande et préflight | Vérifié 3/3 sur les VM K3s |
| PREP-05 | K3s trois serveurs haute disponibilité | Déployé et vérifié sur `node-01`, `node-02`, `node-03` |
| PREP-08 | VM, identités et domaines ESXi | Vérifié 3/3 avec anti-affinité |
| PREP-09 | CPI/CSI VMware vSphere et stockage | Déployé ; StorageClass `arcia-vsphere` validée avec PVC RWO |
| L0-01 | Namespace unifié `arcia` | Déployé ; abandon des 43 micro-namespaces au profit du namespace unique |
| L0-02a | Hermes Agent Studio (9119) & Gateway (8642) | Déployé et qualifié sur PVC `hermes-user-pvc` (20Gi) avec Tokenmaxing |
| L0-02b | Ingress Traefik et Cert-Manager TLS | Déployé ; ClusterIssuer `letsencrypt-prod` et terminaison HTTPS |
| L0-02c | Authentification SSO Microsoft Entra ID | Middleware ForwardAuth OAuth2-Proxy préparé, Open-WebUI SSO OIDC natif |
| L0-03 | Passerelle DLP Presidio (port 8080) | Déployé et qualifié (`/sanitize` vérifié, PII/secrets caviardés) |
| L0-04 | Passerelle d'inférence LiteLLM Proxy (port 4000) | Déployé et qualifié (`/health/readiness` HTTP 200, modèle `auto`, fallbacks) |
| L0-05 | Portail Collaborateur Open-WebUI (port 8080) | Déployé et qualifié (PVC 20Gi, BYOK, raccordements LiteLLM et Hermes) |
| L0-06 | Adaptateur Microsoft Teams Bot (port 3978) | Déployé et qualifié (`/health` HTTP 200, DM et canaux @ArcIA) |
| L0-07 | Routeur OmniRoute v3.8.51 LAN | Déployé et qualifié sur ports 20128/20129 avec PVC 5Gi |
| L5 | Outillage agentique et Tokenmaxing | RTK, Headroom AI, LintLang, Ponytail v1.0, ArcIA Graphify AST v0.2 et Public-APIs qualifiés ([Guide outillage](guides/outillage-builder.md)) |
| M365-01 | Spécifications intégration Microsoft 365 | Codé ; [annexe d'intégration](annexes/integration-microsoft365.md) pour les administrateurs tenant |
| DOC-03 | Purge documentaire intégrale & validation auto | Réalisé : guides v0.2 alignés, handoffs historiques purgés, `scripts/validate_docs.py` vérifié (0 erreur) |

Aucun conteneur factice ne remplace un service métier manquant.
La réussite du socle synthétique est consignée dans [l'état de reprise](etat-reprise.md).

## Lots documentaires

DOC-01 — Réalisé : README synthétique, guides regroupés, état de reprise unique, index exhaustif et validation des liens en CI. [Règles](organisation.md).

DOC-02 — Réalisé : Périmètre générique et politiques d'instance clarifiées ; [quickstart](runbooks/quickstart.md) et [guide OmniRoute](guides/omniroute.md). [Architecture](architecture.md).

DOC-03 — Réalisé : Purge intégrale de la dette documentaire v0.1 (guides obsolètes, handoffs caducs, json de qualification obsolètes), alignement strict sur le harness v0.2 déployé, et automatisation du contrôle d'intégrité par `scripts/validate_docs.py`.

## Évolution skills et réduction du contexte

Catalogue complet des sources retenues : découverte locale MCP, skills Hermes embarquées exposées nativement. RTK automatique borné à git log ; Headroom réduit les gros résultats JSON de lectures déclarées avant contexte, sans mémoire partagée. Ponytail applique l'échelle de décision sobre YAGNI et ArcIA Graphify extrait les AST en local avec 0 token dépensé. Voir [l'état de reprise](etat-reprise.md) pour les détails.
