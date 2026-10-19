# Correction des icônes et des sauvegardes du wizard

Date : 18 octobre 2026. Périmètre : icônes des modèles et sauvegarde/reprise d'instance. Le catalogue et l'authentification LiteLLM sont traités séparément.

## Icônes depuis les déclarations de l'administrateur

La résolution commune dans [branding.py](../services/open_webui/branding.py) s'applique à l'aperçu du wizard et à Open-WebUI. Priorité : hébergement local déclaré, puis ZDR explicitement actif, puis icône normale. Un alias contenant « local » ne change pas le type. La chaîne `"false"` n'active pas ZDR. Le champ facultatif `hosting`, configurable dans la ligne du wizard, accepte `local` ou `cloud` ; sans ce champ, le type de fournisseur est utilisé.

Les trois SVG existants restent les sources graphiques. Le HTML ne maintient plus de copies Data URI. Le mapping contient uniquement les identifiants exacts déclarés dans le wizard ; il reste privé dans `/etc/arcia/models-branding.json`, sans publication des identifiants dans les assets du harness.

La version Open-WebUI v0.12.3 charge les avatars par sa route d'image et retire l'image des réponses de certaines listes. Les fiches natives refusent aussi les identifiants avec espaces. Sources : [sélecteur officiel](https://github.com/open-webui/open-webui/blob/v0.12.3/src/lib/components/chat/ModelSelector/ModelItem.svelte), [route officielle](https://github.com/open-webui/open-webui/blob/v0.12.3/backend/open_webui/routers/models.py).

L'intégration retenue est une projection en lecture dans [arcia_webui.py](../services/open_webui/arcia_webui.py), appelée au même chemin d'avatar natif. Elle utilise la session vérifiée et le filtrage d'accès natifs avant de retourner une des trois ressources statiques autorisées. Elle conserve la route officielle comme repli. Elle ne crée aucune fiche, aucun alias, aucun utilisateur et ne modifie aucune route d'inférence. Cette solution évite une migration des identifiants de modèles pour porter une image.

Le backend officiel est lancé par [start.py](../services/open_webui/start.py), qui conserve la clé de session existante sur le volume. La projection, ses ressources et son mapping produisent une empreinte de déploiement. Le rechargement respecte la stratégie `Recreate` et le volume RWO existants : une interruption du portail est possible. La fusion ciblée préserve les connexions définies par le catalogue et retire l'ancien montage public du mapping.

[verify.py](../services/open_webui/verify.py) contrôle la révision chargée, le type MIME et les empreintes HTTP des SVG. `assets_applied`, `runtime_loaded`, `assets_served` et `avatars_verified` restent distincts. La vérification statique n'atteste pas une recette visuelle authentifiée. Les remplacements d'avatars par DOM et `window.fetch` ont été retirés de [loader.js](../assets/branding/loader.js).

Le packaging Kubernetes et le centre de mise à jour suivent cette publication. Le laboratoire Docker reste sur sa version historique et n'utilise pas cet adaptateur réservé à la version certifiée Kubernetes ; aucune mise à niveau de composant n'est introduite dans ce correctif.

## Sauvegarde et reprise

Le menu récupère le dépôt depuis `instance_backup` et les déclarations héritées `instance_git`, y compris `provider`, `owner` et `repo_name`. L'enregistrement YAML préserve ces paramètres et les champs additionnels. Un échec de lecture distante conserve le dépôt déclaré visible et affiche l'erreur.

Toute écriture de configuration par le wizard appelle le même mécanisme de sauvegarde. Une surveillance complète ce chemin pour les changements du YAML et de `secrets/arcia.env` pendant que le wizard fonctionne. Sans modification, aucune sauvegarde supplémentaire n'est poussée. Les écritures sont sérialisées ; les fichiers locaux sont remplacés atomiquement et les variables d'environnement inconnues sont préservées, y compris lors d'une restauration.

Les données complètes de configuration et d'environnement sont chiffrées en AES-256-GCM avant leur mise en attente locale ou leur synchronisation Git. L'absence de `cryptography` produit une erreur explicite ; aucun chiffrement dégradé n'est créé. La lecture des anciennes archives reste compatible avec l'ancien format identifié.

[storage.py](../services/instance_backup/storage.py) utilise un clone temporaire isolé de la branche réellement déclarée par le dépôt. Seuls `instance-secrets.enc` et `instance.json` sont ajoutés et poussés. Aucun `git add .`, force-push ou commit du harness. Les autres fichiers du dépôt privé sont préservés. La visibilité privée est vérifiée avant écriture distante. Une divergence refuse le push ; l'instantané chiffré reste en attente et sera réessayé après 30 secondes. Les changements successifs hors ligne sont conservés dans l'ordre, sans créer de doublons à chaque tentative.

Les identifiants Git passent par l'environnement du processus, jamais par l'URL ou les arguments. L'identité GitHub déjà connectée dans le programme local `gh` peut être réutilisée. Le mot de passe maître et, si nécessaire, le jeton sont saisis dans le formulaire local. Un nouveau déverrouillage vérifie le mot de passe sur l'archive distante existante avant de changer le coffre ; une faute de saisie ne remplace pas la clé des nouvelles sauvegardes. Sous Windows, le coffre est protégé par DPAPI et lié à l'utilisateur du poste. Sous Linux/macOS, les secrets restent en mémoire de session et doivent être déverrouillés après un redémarrage. Ils ne sont pas renvoyés dans les réponses d'état.

La restauration choisit le dernier instantané ou une révision de sauvegarde, valide et déchiffre avant d'écrire, puis utilise la même transaction d'enregistrement/sauvegarde. Elle restaure la configuration et l'environnement locaux ; la réapplication sur le cluster reste l'action de déploiement du wizard. Les sauvegardes de configuration ne remplacent pas les sauvegardes de bases, conversations, PVC ou etcd.

## Utilisation et validation

1. Installer les dépendances du coffre avec `python -m pip install -r requirements-wizard.txt` (Python 3.9+), puis lancer le wizard.
2. Dans **Sauvegarde et reprise**, vérifier le dépôt privé déclaré, saisir le mot de passe maître et, uniquement si nécessaire, l'accès Git local.
3. Déclencher une première sauvegarde. Contrôler l'état `pushed` et le commit distant ; un état `locked` ou `pending` ne constitue pas un succès de sauvegarde.
4. Les modifications suivantes déclenchent les sauvegardes tant que le wizard fonctionne. Les états sont aussi renvoyés avec les réponses de mutation et affichés par l'interface.
5. Pour une instance existante, cliquer sur **Enregistrer le routage** : la même action enregistre les déclarations et applique les icônes. Une application partielle est signalée dans le résultat et se reprend avec ce même bouton. Pour une nouvelle instance, les déclarations de modèles, leur hébergement et les fournisseurs personnalisés sont transmis au déploiement : les icônes sont installées automatiquement avec Open-WebUI. Aucun bouton d'application séparé n'est nécessaire. Contrôler les ressources, puis vérifier le sélecteur et les messages avec une session autorisée.

Les tests synthétiques couvrent la classification, les accès à la projection, la conservation de la clé de session, la publication déterministe, la reprise de queue chiffrée, la conservation du dépôt et des variables supplémentaires, ainsi qu'un push réel vers un dépôt Git local sur une branche différente de `main` avec contrôle des deux seuls fichiers modifiés.

Les contrôles de livraison comprennent la suite unitaire complète, la validation documentaire, les syntaxes PowerShell/Bash/JavaScript et le dry-run synthétique. Une qualification synthétique ne prouve ni le rendu navigateur de l'instance ni une reconstruction sur cluster neuf.
