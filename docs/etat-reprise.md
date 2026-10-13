# État de reprise d’ArcIA — 13 octobre 2026

Complément documentaire et de configuration :
[handoff Microsoft 365](handoff-2026-10-13-microsoft365.md). Annexe admin et
contrat YAML/validation hors ligne livrés ; aucun service Microsoft 365 actif,
aucun tenant contacté. La qualification K3s précédente reste inchangée.

Lire le [handoff courant](handoff-2026-10-13-skills-catalogue.md), puis le [socle précédent](handoff-2026-10-12-arcia-cloud-bootstrap.md). Travailler sur **main** ; ne pas créer de branche. `arcia-harness` contient la plateforme générique ArcIA ; les customisations d’organisation vivent dans leur dépôt d’instance distinct.

Socle K3s/VMware, PostgreSQL, Hermes, outils et Knowledge opérationnels en qualification synthétique. Presidio et le relais cloud gratuit filtré sont déployés ; une réponse réelle HTTP 200 avec ZDR/prix nul a été obtenue. DNS externe et Internet direct depuis Hermes sont refusés ; Context7 externe reste fermé. OmniRoute est installé, son automatisation reste différée. Aucune autorisation payante.

Le [bootstrap exhaustif](runbooks/bootstrap.md) porte les opérations jusqu’au point courant, avec couverture CI et journal protégé. La configuration runtime Hermes utilise une ConfigMap immuable par hash. Toute évolution doit être reportée dans bootstrap, locks, docs et tests avant livraison.

La qualification multi-utilisateur locale a réussi sur deux identités synthétiques : 90 contrôles de corpus commun/personnels, sessions/historiques/exports, états et outils distincts, accès concurrents, refus croisés, redémarrages et déconnexion sans rejeu du cookie. Le rejeu de cookie et bearer après déconnexion est refusé. Le SSO, les groupes, le provisioning général et les connexions déjà ouvertes restent à qualifier. Voir [la recette multi-utilisateur](multi-utilisateur.md) et [la sécurisation complète](securisation-plateforme-donnees.md).

Secrets, inventaires et diagnostics complets restent sous DPAPI/ACL. Ne pas afficher de bundle/get secret/log brut. L’archive portable doit être renouvelée avant transfert. Rebuild neuf, restore complet et panne brutale/fencing restent des gates de release.

[Historique](historique-qualification-2026-10-12.md) · [Backlog](backlog.md) · [Recette](runbooks/recette-fondatrice.md).

Code courant qualifié : `ae07bd0a109a29b6c6a96df882e07b9c7965f8eb`, CI verte et Verify complet de 7 étapes réussi. 151 tests Linux, 55 contrôles d'outillage par runtime et 200 contrôles multi-utilisateur incluant les sondes des deux runtimes. [Preuves courantes](qualification/2026-10-13-skills.json). La réconciliation fondatrice à 25 étapes reste une preuve historique du 12 octobre ; aucun rebuild neuf n'est annoncé.

Catalogue complet local : 539 entrées upstream, sept adaptations/orientations
ArcIA, 58 skills Hermes embarquées exposées nativement. Découverte locale MCP et
orientation par plugin natif ; aucun téléchargement depuis les conversations.
Mémoire/délégation Hermes, pas d'apprentissage/mémoire ECC ni de proxy/mémoire
Headroom. RTK automatique sur git log simple et borné ; Headroom automatique sur
gros résultats JSON de lectures déclarées, avec originaux exacts dans un cache
RAM privé borné, TTL de référence 5 minutes et exclusions RAG/skills/écritures.
Voir [skills](skills.md), [tokenmaxing](tokenmaxing.md) et
[crédits/licences](../THIRD_PARTY_NOTICES.md). Les MCP métiers restent à ajouter
dans le dépôt d'instance avec leur propre recette.
