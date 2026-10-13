# Bootstrap exhaustif d’ArcIA

Le point d’entrée unique est `scripts/Bootstrap-Harness.ps1`. Son manifeste versionné `bootstrap/qualification.json` décrit toutes les étapes jusqu’au socle courant : VM, K3s, stockage, bases, moteur, outillage, RAG, confidentialité et recette. Toute évolution de composant/service/outillage exige une mise à jour du bootstrap et de sa couverture CI.

## Prérequis et saisies externes

Contrôleur Windows PowerShell 7.4+, Git, OpenSSH et WSL Debian existants. Windows PowerShell 5.1 est requis pour le client SSO .NET Framework. Qemu-img 10.2.1 sous WSL est nécessaire uniquement pour fabriquer l’image et provisionner les VM. Les dépendances du contrôleur sont installées dans des venv administratifs fixés par hashes ; aucun runtime applicatif ArcIA n’est installé sur le poste.

Avant Apply, enregistrer localement avec les formulaires protégés :

1. `Connect-VMware.ps1` puis `Select-VMwareTarget.ps1` : vCenter, cible et identité SSH personnelle. Les accès et destinations doivent être déjà désignés.
2. Enrôlement GitHub propre à l’ingénieur si nécessaire ; ne pas fournir de token au modèle.
3. Endpoints/IP réservés, CIDR et policy : `Configure-Foundation.ps1` les collecte si l’état n’existe pas, après découverte de l’infrastructure.
4. DNS API privé résolu depuis les trois nœuds avant qualification réseau. Le harness ne devine pas la gestion de votre DNS.
5. Certificat public valide avec clé : état protégé existant ou `Import-BootstrapTls.ps1 -CertificatePath ... -PrivateKeyPath ...`. L’émission DNS-01 manuelle est une dépendance externe : les TXT et leur publication ne peuvent pas être automatisés sans connecteur DNS autorisé.
6. Clé OpenRouter enregistrée via `Configure-Integrations.ps1`, utilisée exclusivement par le relais cloud. Seule la qualification gratuite est activée.

Les valeurs privées ne se mettent pas dans une ligne de commande affichée, un YAML Git ou le chat. Le manifeste énumère les entrées nécessaires ; un secret absent arrête la progression, il n’est pas remplacé par une fixture en production.

## Choisir le mode

```powershell
# Voir le parcours sans lire ni modifier l’état privé
./scripts/Bootstrap-Harness.ps1 -Mode Plan -Profile Fresh -ProvisionVMs

# Préparer une nouvelle opération et créer trois VM sur la cible désignée
./scripts/Bootstrap-Harness.ps1 -Mode Apply -Profile Fresh -ProvisionVMs

# Pour des VM vierges déjà provisionnées par cette opération, omettre -ProvisionVMs
./scripts/Bootstrap-Harness.ps1 -Mode Apply -Profile Fresh

# Réconcilier le cluster possédé avec l’état courant du dépôt
./scripts/Bootstrap-Harness.ps1 -Mode Apply -Profile Reconcile

# Recettes applicatives, RAG, outillage, confidentialité et accès
./scripts/Bootstrap-Harness.ps1 -Mode Verify

# Inspection sans install, switchover ni ingestion de fixture
./scripts/Bootstrap-Harness.ps1 -Mode Audit
```

Fresh refuse un nœud déjà K3s : ce mode n’est pas un reset. Les VM existantes doivent appartenir à l’opération protégée ; aucun inventaire arbitraire n’est adopté. Après installation K3s, reprendre avec Reconcile. Si K3s est interrompu mais les preuves préinstallation sont présentes et valides, Ensure-K3sBootstrap relance uniquement l’installation possédée, sans suppression d’état.

## Ordre effectif

| Groupe | Étapes |
|---|---|
| Contrôleur et enrôlement | Runtime administratif hashé, protection de la paire SSH, image/VM si demandées |
| Infrastructure | Placement, accès/confiance SSH, refus de nœuds non vierges, client SSO, compte et permissions VMware |
| Configuration et réseau | Instance, décisions conservées, DNS/ports, VIP, bascule synthétique, gates préinstallation |
| Fondations | K3s, inspect API/VIP/chiffrement, CPI/CSI et 5 essais de stockage |
| Applications | CNPG/PostgreSQL, TLS public, Hermes minimal, Knowledge, Privacy/DNS/relais |
| Assemblage | Outils sur PVC, MCP Knowledge readonly, configuration Hermes complète, second runtime de qualification avec volumes et identité propres |
| Recette | Persistance/switchover, VIP réels, inspections, Knowledge, outils, privacy/cloud, multi-utilisateur et HTTPS/auth |

Hermes minimal évite la dépendance circulaire avec les volumes et tokens encore absents. Une réconciliation d’une instance existante conserve ses outils et sa configuration au passage de cette étape. Les installations suivantes se terminent avant montage du volume RWOP readonly dans le runtime. Une ConfigMap immuable par hash assure que le Pod reçoit la configuration attendue.

## Journal, preuve et reprise

Le bootstrap verrouille l’opération ; chaque action cluster possède aussi son verrou. L’ordonnanceur exécute les étapes séquentiellement, avec timeout et arrêt immédiat au premier échec. Un code de succès doit provenir d’un statut écrit pendant l’exécution courante : un vieux fichier ne suffit pas.

`bootstrap-journal.dpapi` conserve commit, empreinte de manifeste et états. Les logs complets des sous-processus sont chiffrés. `bootstrap-status.json` ne restitue que phase/code. Le journal n’autorise jamais à sauter des étapes : une reprise revalide le profil sélectionné et la propriété des ressources. Les preuves et clés restent dans la racine protégée de l’ingénieur.

Si une VM vient de démarrer et n’est pas prête, attendre sa disponibilité puis reprendre Fresh avant installation K3s. Si un Job d’outils échoue, inspecter son statut protégé ; seuls les Jobs explicitement Failed et possédés peuvent être nettoyés. Ne pas supprimer un Job actif, PVC ou état pour « débloquer » l’installation. Une évolution des dépendances Knowledge/Privacy impose un démontage/upgrade contrôlé, pas une modification silencieuse du venv readonly.

## Couverture et limites vérifiées

La CI compare manifeste, components du lock, outils, features activées et dossiers services. Ajouter un service sans bootstrap fait échouer la validation. Les tests vérifient ordre, arrêt sur erreur, reprise et refus d’une instance étrangère. Les profils Plan n’exigent aucun secret.

Le manifeste compte 43 étapes. La dernière exécution Reconcile a réussi ses 25 étapes sélectionnées, avec les deux runtimes et leur recette ; un Audit précédent a également réussi sur le cluster existant ; les preuves sont précisées dans le handoff. **Aucun cluster neuf complet n’a encore été reconstruit.** Backup/restore cohérent des bases/corpus, fencing brutal, compatibilité/support de release, verrouillage de certains paquets système et renouvellement DNS automatisé restent des gates. Git + bootstrap reconstruisent le logiciel avec les entrées protégées requises ; ils ne restaurent pas les données perdues sans backup.

À chaque évolution : modifier locks/renderers/worker et manifeste, compléter recette/tests/docs, exécuter les vérifications pertinentes, livrer sur main puis conserver la référence du commit. Une instance spécifique fixe cette révision dans son propre dépôt et ajoute son bootstrap de customisations.

## Catalogue de skills et intégrations natives

Le contrat `catalogue_contract` du manifeste lie `builder/skills.lock.json` à
`install_hermes_tools_base`, `install_multiuser` et `verify_hermes_tools`. Le
Job reconstruit les 539 entrées depuis les archives immuables et vérifie l’index ;
le runtime monte les outils et le plugin natif `arcia-platform` en lecture seule.
La recette multi-utilisateur rejoue aussi les sondes d’outillage dans chaque
runtime. Les révisions existantes, identités, états et PVC sont conservés.
Le feature lock `tokenmaxing` et la configuration native portent aussi la
réduction automatique des résultats JSON de lecture et le cache d'originaux
privé, avec tests de restauration, bornes et exclusions.
Voir [skills](../skills.md), [tokenmaxing](../tokenmaxing.md) et
[crédits](../../THIRD_PARTY_NOTICES.md). Les résultats historiques à 43 étapes
restent datés ; les nouvelles preuves sont dans le handoff du 13 octobre.
