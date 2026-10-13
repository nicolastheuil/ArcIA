# État de reprise d’ArcIA — 13 octobre 2026

**Fin de session demandée par le propriétaire.** Reprendre avec le
[handoff de clôture](handoff-2026-10-13-fin-session.md). Révision fonctionnelle
`1361605` publiée sur main, CI terminée avec succès. Aucun travail ni reprise
automatique programmé pour ce soir ; services laissés en fonctionnement.

Mise à jour courante : sortie IPv4 publique TCP/443 Keycloak appliquée sur
instruction explicite, filtrage des destinations au pare-feu amont. Snapshot
`/32` retiré ; DNS courant, TLS Microsoft/Graph 4/4, HTTPS public et refus
HTTP/80 vérifiés. Admin local nommé récupéré (`realm-admin` effectif), mapper
tenant `ArcIA.User` appliqué sur exception limitée, rôle et espace d'un compte
fédéré constatés. Nettoyage de l'unique espace d'un compte supprimé et de ses
deux volumes autorisé par exception distincte ; deux comptes désactivés
conservés, pool privé porté à 32 places pour trente collaborateurs. Voir le
[handoff courant](handoff-2026-10-13-identity-public-https.md), qui remplace les
états réseau et habilitation intermédiaires ci-dessous. Bot Teams à recréer ;
identité administrative et cible Azure encore à enrôler localement.

Identité par défaut : comptes locaux permanents Keycloak, portail `/admin/users`,
SSO optionnel en parallèle. Lire le [handoff identité](handoff-2026-10-13-identite.md)
et [les procédures administrateur](identite-utilisateurs.md). Base dédiée et
portail déployés sur la cible existante ; qualification synthétique, sans
ouverture de données privées ni tenant Microsoft. Le lot remplace l'hypothèse
d'une identité locale seulement temporaire.

Complément : le point d'entrée `/portal/` crée automatiquement un espace
personnel vide pour chaque nouvelle identité habilitée (`ArcIA.User`), dans
un pool borné de huit places. Les anciens propriétaires synthétiques ont été
supprimés dans le realm par l'administrateur ; leurs volumes et UUID liés
restent conservés, sans transfert vers les nouveaux comptes. Voir
[le handoff du portail](handoff-2026-10-13-portail-personnel.md).

Complément documentaire et de configuration :
[handoff Microsoft 365](handoff-2026-10-13-microsoft365.md). Annexe admin et
contrat YAML/validation hors ligne livrés ; aucun service Microsoft 365 actif,
aucun tenant contacté. La qualification K3s précédente reste inchangée.

Authentification Microsoft : [diagnostic courant](handoff-2026-10-13-m365-auth-diagnostic.md).
Redirection vers Microsoft vérifiée (HTTP 303) ; callback en erreur réseau dans
les journaux récents, sans règle TCP/443 pour Keycloak. Correction non déployée,
connexion complète non qualifiée ; preuves brutes protégées localement.
Tests de routage exécutés : VM Microsoft IPv4/TLS 12/12, Pod Keycloak IPv4
refusé avec compteur REJECT +4, DNS/PG OK, contrôle de sortie Pod TLS 2/2.
IPv6 sans route sur les VM et Keycloak ; [preuves](qualification/2026-10-13-m365-routing.json).
Correction suivante : [réparation réseau appliquée](handoff-2026-10-13-m365-egress-repair.md)
sur exception administrative explicitement autorisée pour ce seul correctif.
Règle Keycloak TCP/443 sur 14 IPv4 `/32`, TLS Microsoft/Graph 4/4 et refus
hors liste vérifiés. Login Microsoft/MFA utilisateur encore à confirmer ;
pas de refresh automatique ni de qualification SSO complète revendiquée.
Suite : l'utilisateur confirme un login Microsoft fonctionnel sur le second PC.
Récupération de son nouvel admin et admission automatique du tenant préparées,
mais non appliquées avant l'exception d'élévation demandée ; capacité cinq places
libres sur huit. Bot Teams à créer entièrement après reprise de ces accès.
[État détaillé et demandes en attente](handoff-2026-10-13-tenant-admission-admin-recovery.md).

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
