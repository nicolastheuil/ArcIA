# Tokenmaxing v0.5.1 : CCR, RTK et sobriété de contexte dans Hermes

> [!NOTE]
> **Statut en v0.5.1 : Implémenté et Actif.**
> Le plugin natif de gouvernance et d'économie de tokens ([services/hermes/plugin.py](../../services/hermes/plugin.py)) est synchronisé automatiquement par `scripts/deploy.py` dans le ConfigMap `hermes-governance-plugin` et monté dans [deploy/manifests/06-hermes-agent.yaml](../../deploy/manifests/06-hermes-agent.yaml) ainsi que dans les pods Power Users ([deploy/manifests/templates/hermes-poweruser.template.yaml](../../deploy/manifests/templates/hermes-poweruser.template.yaml)).

Le socle **ArcIA v0.5.1** articule quatre leviers complémentaires d'économie de tokens et de sobriété :
1. **CCR (Compress-Cache-Retrieve)** : Compression réversible des fichiers et résultats JSON volumineux (> 8 Ko) avant leur injection dans la fenêtre de contexte du LLM, avec mise en cache mémoire SHA-256 et récupération paginée de l'original à la demande.
2. **RTK (Rust Token Killer)** : Réécriture bornée des commandes `git log` verbeuses pour réduire le bruit des historiques Git.
3. **Graphify** : Cartographie structurelle AST locale de bases de code ([scripts/arcia_graphify.py](../../scripts/arcia_graphify.py)) sans consommer un seul token LLM.
4. **Ponytail** : Échelle de décision YAGNI ([skills/ponytail/SKILL.md](../../skills/ponytail/SKILL.md)) prévenant le sur-développement agentique.

Ces mécanismes opèrent conjointement avec la **Barrière 1 DLP Presidio** intégrée au plugin, garantissant que toute sortie d'outil (compressée ou restituée) est assainie en mode *fail-closed* avant persistance SQLite et avant envoi au modèle.

---

## 1. Mesures de référence sur fixtures synthétiques

Mesures exécutées sur fixtures synthétiques sans appel modèle externe :

| Scénario | Original | Résultat | Observation |
|---|---:|---:|---|
| RTK, `git status` avec 120 fichiers non suivis | 2 474 octets | 2 475 octets | Aucun gain sur cette fixture |
| RTK, journal de 15 commits (`git log`) | 3 169 octets | 1 670 octets | **Réduction de 47,3 %**, sujet du dernier commit conservé |
| CCR, charge JSON structurée (150 événements) | 14 252 octets | 7 402 octets | **Réduction de 48,1 %**, marqueurs critiques et clés de schéma préservés |

---

## 2. RTK : compaction bornée des journaux Git

Le hook `transform_command` de [services/hermes/plugin.py](../../services/hermes/plugin.py) intercepte les commandes shell simples `git log ...` :
- Lorsque le binaire `rtk` est disponible dans le conteneur, la commande est réécrite vers `rtk git log ...`.
- En repli sans binaire `rtk`, le plugin ajoute automatiquement `--oneline -n 30` aux appels `git log` dépourvus d'options de formatage.
- Les commandes composées (`|`, `;`, `&&`), diffs, formats explicites (`--format`, `--pretty`, `--stat`) ou redirections sont laissés strictement intacts.

---

## 3. CCR (Compress-Cache-Retrieve) : compression JSON réversible

### 3.1 Interception automatique (`transform_tool_result`)
Avant qu'un résultat d'outil de lecture (`read_file`, `fetch_url`, `terminal`, `bash`, `mcp_call`) n'entre dans le contexte du modèle :
1. **Assainissement DLP préalable** : La sortie passe par `http://presidio-dlp.arcia.svc:8080/sanitize` en mode *fail-closed*.
2. **Détection et Compression (> 8 Kio)** : Si la charge est un JSON valide de plus de 8 Kio, le moteur CCR construit un résumé structurel préservant :
   - Les clés de premier niveau et la cardinalité des listes.
   - Un échantillon des premiers et derniers éléments.
   - Tout élément contenant un marqueur critique (`error`, `fatal`, `exception`, `warning`, `failed`, `status`).
3. **Cache Privé SHA-256 (`_CCR_CACHE`)** :
   - Le contenu original exact (assaini par DLP) est stocké en RAM sous une clé `ccr_<sha256[:16]>`.
   - Le cache est borné à **32 entrées** ou **4 Mio** maximum par processus avec expiration TTL automatique à **300 secondes (5 minutes)**.
   - Aucun cache n'est partagé entre différents pods Power Users.

### 3.2 Outils natifs exposés à l'agent (`register(ctx)`)
Le plugin enregistre deux outils directement invocables par Hermes Agent :
- **`arcia_compress_json_file(file_path)`** : Lit et compresse un fichier JSON situé dans `/opt/data/workspace` (jusqu'à 512 Kio, protection stricte contre toute traversée de répertoire) avant que l'agent ne charge le fichier brut en contexte. Retourne la vue CCR et son `ccr_hash`.
- **`arcia_restore_tool_result(ccr_hash, offset=0, limit=4000)`** : Permet à l'agent de récupérer à la demande une tranche paginée de l'original exact à partir de son `ccr_hash` lorsqu'un détail spécifique lui est nécessaire.

---

## 4. Architecture de sécurité et non-recouvrement

| Fonction | Implémentation ArcIA v0.5.1 | Principe de Sobriété |
|---|---|---|
| **Mémoire de session** | Hermes natif (`state.db` sur PVC RWO dédié) | Un seul propriétaire SQLite par pod ; pas de mémoire globale inter-utilisateurs |
| **Compression de contexte** | Plugin natif `services/hermes/plugin.py` (CCR + RTK) | Zéro proxy externe ; cache RAM éphémère isolé par runtime |
| **Analyse de code** | `scripts/arcia_graphify.py` (AST Python local) | 0 token consommé, 0 envoi cloud |
| **Routage d'inférence** | LiteLLM Proxy (`05-litellm.yaml`) | Point de sortie unique avec ZDR et double barrière DLP (OmniRoute supprimé) |

Voir également :
- [Code source du plugin Hermes](../../services/hermes/plugin.py)
- [Outillage Builder & Graphify](outillage-builder.md)
- [Guide des Skills](skills.md)
- [Confidentialité Presidio DLP](confidentialite-presidio.md)
