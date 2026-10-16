# Quickstart ArcIA v0.2

Ce guide vous accompagne pas-à-pas pour déployer, configurer et utiliser la plateforme souveraine d'entreprise **ArcIA v0.2** sur votre cluster Kubernetes K3s.

---

## 1. Prérequis

Pour déployer ArcIA, vous devez disposer de :
1. **Un cluster Kubernetes opérationnel** (K3s recommandé, Kubernetes 1.28+) :
   - Contrôleur d'Ingress Traefik installé.
   - Cert-Manager pour l'émission automatique des certificats SSL/TLS Let's Encrypt.
   - Une `StorageClass` provisionnant des volumes persistants (PVC).
2. **Outil CLI `kubectl`** configuré avec les droits d'administration sur le cluster.
3. **Python 3.8+** (utilisé par le moteur de déploiement universel, sans dépendance tierce requise).
4. **Une clé d'API LLM Cloud** (ex: [OpenRouter](https://openrouter.ai/) fournissant l'accès unifié à Claude 3.5 Sonnet, GPT-4o, DeepSeek-V3).

---

## 2. Déploiement en 3 Étapes

### Étape 1 : Cloner le dépôt

```bash
git clone https://github.com/nicolastheuil/ArcIA.git
cd ArcIA
```

### Étape 2 : Préparer la configuration `arcia.config.yaml`

Copiez le modèle d'exemple :
```powershell
# Sous Windows PowerShell
Copy-Item arcia.config.yaml.example arcia.config.yaml

# Sous Linux / macOS
cp arcia.config.yaml.example arcia.config.yaml
```

Ouvrez `arcia.config.yaml` et renseignez les paramètres obligatoires :
- `network.public_fqdn` : Le nom de domaine complet pour accéder à l'assistant (ex: `assistant.entreprise.com`).
- `network.acme_email` : Email de contact Let's Encrypt pour les certificats SSL.
- `llm_gateway.openrouter_api_key` : Votre clé API OpenRouter d'entreprise (`sk-or-v1-...`).
- `hermes.admin_password` : Mot de passe administrateur pour l'accès à Hermes Studio.

### Étape 3 : Lancer le Déploiement

Le moteur de déploiement universel valide la configuration, injecte les secrets nécessaires et applique les 10 manifests dans l'ordre strict de dépendance :

```powershell
# Déploiement sous Windows PowerShell
.\scripts\Deploy-ArcIA.ps1

# Déploiement sous Linux / Bash
bash scripts/deploy-arcia.sh

# Déploiement Python direct (multiplateforme)
python scripts/deploy.py --config arcia.config.yaml
```

---

## 3. Configuration de LiteLLM & Clés API d'Entreprise

### Où renseigner les clés d'entreprise ?

La passerelle d'inférence d'entreprise **LiteLLM Proxy** centralise les modèles et masque les clés d'API derrière des modèles virtuels sécurisés :

1. Les secrets d'entreprise sont stockés dans le fichier local `secrets/arcia.env` (généré automatiquement par le script de déploiement à partir de `secrets/arcia.env.template`).
2. Pour ajouter ou modifier des clés de fournisseurs (OpenRouter, OpenAI, Anthropic, DeepSeek, etc.), éditez `secrets/arcia.env` :
   ```env
   OPENROUTER_API_KEY=sk-or-v1-votre-cle-reelle
   OPENAI_API_KEY=sk-proj-votre-cle-openai-si-besoin
   ANTHROPIC_API_KEY=sk-ant-votre-cle-anthropic-si-besoin
   ```
3. Appliquez immédiatement la mise à jour des secrets dans le cluster :
   ```powershell
   # Sous Windows
   .\scripts\Apply-Secrets.ps1

   # Sous Linux
   bash scripts/apply-secrets.sh
   ```
4. Redémarrez la passerelle LiteLLM pour prise en compte immédiate :
   ```powershell
   .\scripts\Invoke-K3s.ps1 "rollout restart deployment litellm-proxy -n arcia"
   ```

### Modèles d'Entreprise Disponibles

Dès le premier déploiement, LiteLLM expose les modèles suivants dans le portail :
- `auto` : Routage intelligent par défaut (sélection automatique équilibrée).
- `claude-3.5-sonnet` : Modèle de pointe pour le raisonnement, le code et l'architecture.
- `gpt-4o` : Modèle multimodal rapide et polyvalent.
- `deepseek-chat` : Modèle hautement économique pour les requêtes volumineuses.
- `local-internal` : Route interne sans sortie cloud (Ollama/vLLM).

Toutes les requêtes sortant vers des modèles cloud sont **automatiquement caviardées par Presidio DLP** (`presidio-dlp.arcia.svc:8080`) avant transmission au fournisseur.

---

## 4. Portail Open-WebUI & Comptes Personnels (BYOK / OAuth)

### Accès au Portail Web

Ouvrez votre navigateur sur `https://<public_fqdn>/` (ex: `https://assistant.entreprise.com`).

- **Avec SSO Entra ID activé** (`entra_id_sso.enabled: true`) : L'authentification est déléguée à Microsoft 365. Le compte de l'utilisateur est automatiquement provisionné sans mot de passe à créer.
- **Sans SSO (Mode local)** : Le premier compte créé devient le compte administrateur d'Open-WebUI.

### Comment un utilisateur final peut inclure ses comptes personnels / clés perso (BYOK & OAuth) ?

Deux options sont offertes selon la politique de gouvernance de votre entreprise :

#### Option A : Connexions Directes dans Open-WebUI (Recommandé, Activé par Défaut)

Le harness configure nativement `ENABLE_DIRECT_CONNECTIONS: "true"` dans Open-WebUI :
1. Dans Open-WebUI, l'utilisateur clique sur son avatar (en bas à gauche) > **Paramètres (Settings)**.
2. Aller dans l'onglet **Connexions (Connections)** > section **Connexions directes (Direct connections)**.
3. L'utilisateur active le commutateur et renseigne son endpoint compatible OpenAI et sa clé d'API personnelle (ex: sa clé OpenAI, Anthropic ou OpenRouter personnelle).
4. **Garantie de Sécurité & Confidentialité** : La clé personnelle de l'utilisateur est stockée **exclusivement dans le stockage local de son navigateur (`localStorage`)**. Elle n'est jamais transmise ni persistée dans les bases de données d'ArcIA. Les requêtes de chat partent directement du navigateur du collaborateur vers son fournisseur.

#### Option B : Connexions Personnelles OmniRoute (Contrôle Serveur Souverain)

Si le routeur OmniRoute est activé (`omniroute.enabled: true`) :
1. L'administrateur attribue à l'utilisateur l'accès au portail LAN OmniRoute (`https://<VIP>:20129/`).
2. L'utilisateur y associe ses comptes de modèles personnels ou son OAuth tiers de façon étanche et chiffrée côté serveur.
3. Ses requêtes personnelles sont strictement isolées de celles des autres collaborateurs.

---

## 5. Hermes Studio (Port 9119) & Gateway (Port 8642)

Pour les ingénieurs IA et utilisateurs avancés souhaitant orchestrer des agents autonomes :

- **Hermes Studio (Kanban)** : Accessible à `https://<public_fqdn>/studio`. Connectez-vous avec `admin` et le mot de passe défini dans `hermes.admin_password`. Il permet de suivre l'exécution des missions longues, les réflexions (Chain of Thought), l'utilisation des outils et la collaboration multi-agents.
- **Hermes Gateway & Desktop** : L'application client lourd **Hermes Desktop** se connecte en WebSocket sur `https://<public_fqdn>/gateway` avec votre jeton PAT.
- **Tokenmaxing & Sobriété** : Le plugin ArcIA intégré ([services/hermes/plugin.py](../../services/hermes/plugin.py)) compresse automatiquement les sorties de terminaux et les gros fichiers JSON manipulés par les agents, réduisant drastiquement l'empreinte de tokens.

---

## 6. Intégration Microsoft Teams (Optionnel)

Pour permettre à vos collaborateurs d'échanger avec ArcIA directement dans Microsoft Teams :

1. Dans `arcia.config.yaml`, configurez la section `teams_bot` :
   ```yaml
   teams_bot:
     enabled: true
     app_id: "VOTRE-APP-ID-AZURE-BOT"
     app_password: "VOTRE-SECRET-AZURE-BOT"
   ```
2. Redéployez la plateforme avec `.\scripts\Deploy-ArcIA.ps1` ou `python scripts/deploy.py`.
3. Côté Azure Bot Service, définissez le Webhook de messagerie sur :
   `https://<public_fqdn>/api/teams/messages`
4. Les collaborateurs peuvent immédiatement discuter avec le bot en direct message (1:1) ou le mentionner dans les canaux d'équipe : `@ArcIA quelle est la procédure pour X ?`.

---

## 7. Vérification & Recette Automatisée

Pour valider l'intégrité opérationnelle de la plateforme déployée, exécutez la suite de recette complète (6/6 tests end-to-end) :

```powershell
# Exécution à distance sur le cluster via Invoke-K3s
Get-Content .\scripts\test-validation.sh -Raw | .\scripts\Invoke-K3s.ps1 -RawShell "bash -s"
```

Cette suite valide automatiquement :
1. Le statut opérationnel de tous les pods du namespace `arcia`.
2. Le caviardage DLP Presidio sur `/sanitize`.
3. La disponibilité LiteLLM sur `/health/readiness`.
4. La réactivité d'Hermes Studio (9119) et Gateway (8642).
5. La réponse de l'adaptateur Teams Bot sur `/health`.
6. La disponibilité du portail Open-WebUI sur `/health`.

---

## 8. Exploitation Quotidienne & Liens Utiles

- [Runbook d'Exploitation & Maintenance](exploitation.md) : Consultation des logs, redémarrage des services, injection de secrets.
- [Sauvegarde et Reconstruction](sauvegarde-reconstruction.md) : Sauvegarde d'etcd, persistance des PVC et reprise après incident.
- [Gouvernance Presidio DLP](../guides/confidentialite-presidio.md) : Détail des motifs de détection et politiques de caviardage.
- [Passerelle LiteLLM](../guides/inference-litellm.md) : Configuration avancée des quotas et des fournisseurs.
