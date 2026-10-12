# État de reprise d’ArcIA — 12 octobre 2026

Lire le [handoff courant](handoff-2026-10-12-arcia-cloud-bootstrap.md). Travailler sur **main** ; ne pas créer de branche. `arcia-harness` contient la plateforme générique ArcIA ; les customisations d’organisation vivent dans leur dépôt d’instance distinct.

Socle K3s/VMware, PostgreSQL, Hermes, outils et Knowledge opérationnels en qualification synthétique. Presidio et le relais cloud gratuit filtré sont déployés ; une réponse réelle HTTP 200 avec ZDR/prix nul a été obtenue. DNS externe et Internet direct depuis Hermes sont refusés ; Context7 externe reste fermé. OmniRoute est installé, son automatisation reste différée. Aucune autorisation payante.

Le [bootstrap exhaustif](runbooks/bootstrap.md) porte les opérations jusqu’au point courant, avec couverture CI et journal protégé. La configuration runtime Hermes utilise une ConfigMap immuable par hash. Toute évolution doit être reportée dans bootstrap, locks, docs et tests avant livraison.

La qualification multi-utilisateur locale a réussi sur deux identités synthétiques : 90 contrôles de corpus commun/personnels, sessions/historiques/exports, états et outils distincts, accès concurrents, refus croisés, redémarrages et déconnexion sans rejeu du cookie. Le rejeu de cookie et bearer après déconnexion est refusé. Le SSO, les groupes, le provisioning général et les connexions déjà ouvertes restent à qualifier. Voir [la recette multi-utilisateur](multi-utilisateur.md) et [la sécurisation complète](securisation-plateforme-donnees.md).

Secrets, inventaires et diagnostics complets restent sous DPAPI/ACL. Ne pas afficher de bundle/get secret/log brut. L’archive portable doit être renouvelée avant transfert. Rebuild neuf, restore complet et panne brutale/fencing restent des gates de release.

[Historique](historique-qualification-2026-10-12.md) · [Backlog](backlog.md) · [Recette](runbooks/recette-fondatrice.md).

Code qualifié : `dcd06b4018633c676684d08868671d93698b02ef`, CI verte. Reconcile : 25 étapes ; Verify sur cette révision : 7 étapes. [Preuves assainies](qualification/2026-10-12-synthetique.json).
