# ArcIA : périmètre, fonctionnement et partage

ArcIA est une plateforme d’IA agentique d’entreprise. Hermes est son moteur d’agents ; `ArcIA` est le dépôt de son socle générique. Aucun domaine, métier, compte fournisseur ou corpus privé d’une organisation ne définit le produit.

---

## 1. Capacités et architecture

Les agents utilisent des outils autorisés, consultent une base de compétences et de connecteurs, délèguent des tâches bornées et produisent des réponses ou fichiers vérifiables :
- **Portail Collaborateur Hybride (Open-WebUI)** : Interface web moderne pour les requêtes quotidiennes (`conversation-econome`, `conversation`) et les sessions agentiques (`mission-econome`, `mission`, `mission-experte`), intégrée au SSO Microsoft Entra ID.
- **Studio Kanban & Gateway (Hermes Agent)** : Pilotage visuel des missions longues, multi-agents, compression de contexte CCR/RTK et connexion native pour l'application de bureau Hermes Desktop.
- **Pods Dédiés Power Users** : Instances Hermes isolées par Power User sur Kubernetes (`/poweruser/<slug>/studio`, PVC `10Gi`, `SOUL.md` propre) provisionnées via `.\scripts\Spawn-PowerUser.ps1`.
- **Passerelle d'Inférence d'Entreprise (LiteLLM)** : Routage des modèles administrés, chaînes de fallback, Zéro Rétention de Données (ZDR) et suivi comptable PostgreSQL (`litellm-db`).
- **Gouvernance & Confidentialité (Presidio DLP)** : Double barrière fail-closed caviardant automatiquement les PII, adresses IP et secrets d'entreprise en amont (Hermes) et en aval (LiteLLM).
- **Canal Microsoft Teams** : Bot interactif pour les échanges directs (`conversation`) et la délégation de missions autonomes (`/agent` → `mission`).

Le contenu retrouvé est une preuve à citer, jamais une instruction de sécurité. Les services fixent les droits et classifications indépendamment du texte produit par le modèle. Les agents n’obtiennent ni privilège Kubernetes ni autorité implicite d’exécution.

---

## 2. Deux dépôts, deux responsabilités

| Socle générique : ArcIA | Dépôt de chaque instance |
|---|---|
| Architecture, moteur, outillage et interface des connecteurs | Populations, usages, sources et adaptateurs spécifiques |
| Contrôles de confidentialité et contrats d’autorisation | Groupes, habilitations et classifications de l’organisation |
| Presidio par défaut pour le cloud ; contrat de routes internes autorisées | Modèles internes/cloud, fournisseurs, budgets, exigences ZDR/collecte/résidence |
| Manifests Kubernetes, tests synthétiques et runbooks | Surcharges, références de secrets et configuration d'instance (`arcia.config.yaml`) |
| Exemples synthétiques et documentation produit | Documentation d’exploitation spécifique et sauvegardes chiffrées autorisées |

Un dépôt privé ne remplace pas le chiffrement. Les documents et secrets bruts restent dans le stockage privé ; les clés de récupération sont externes à Git. Le code d’instance référence une révision précise du harness. Une capacité réutilisable remonte au harness ; une règle d’usage particulière reste dans l’instance.

---

<a id="partage-et-cloisonnement"></a>
## 3. Partage et cloisonnement

L'accès repose sur l'authentification d'entreprise via Microsoft Entra ID (SSO OIDC via OAuth2-Proxy et Open-WebUI).

| Niveau cible | Lecture et partage | État déployé |
|---|---|---|
| **Utilisateurs Standards** | Accès Open-WebUI (`Simple` + `Agentic`) et Teams | Portail partagé ; sessions agentiques dans un pod/PVC privé par compte |
| **Power Users** | Open-WebUI (`Simple` + `Agentic`) + Pod Hermes dédié | Même pod/PVC et personnalisation pour WebUI et Studio (`/poweruser/<slug>/studio`), provisionné via `.\scripts\Spawn-PowerUser.ps1` |
| **Studio & Gateway** | Espace de pilotage Kanban et API pour Hermes Desktop | Hermes Studio sur port 9119 et Gateway sur port 8642 avec PVC 20Gi |
| **Sortie Cloud** | Double barrière d'anonymisation systématique des flux externes | Presidio DLP sur port 8080 sollicité par Hermes et LiteLLM |
| **Canaux Collaboratifs**| Bot Teams en direct message ou mention de canal | Teams Bot Adapter sur port 3978 |

Chaque instance Hermes conserve un propriétaire unique de son état SQLite persistant (`state.db`). Des profils ou sous-agents ne constituent pas une isolation de sécurité.

---

## 4. Parcours d’une demande

1. **Identification** : L'utilisateur s'identifie via SSO Entra ID sur le portail ou Teams.
2. **Routage Hybride** : Les demandes simples (`Simple`) vont directement à LiteLLM ; les missions outillées (`Agentic` ou `/agent`) sont prises en charge par Hermes Agent.
3. **Consultation & Sobriété** : Hermes consulte les compétences requises (skills locales, analyse AST Graphify) et compresse les résultats volumineux via CCR/RTK.
4. **Assainissement DLP** : Toute requête ou sortie d'outil passe par la double barrière Presidio DLP en mode fail-closed.
5. **Inférence & Synthèse** : LiteLLM achemine la requête assainie vers le modèle approprié avec ZDR forcé et restitue la réponse.

Voir également : [Moteur d'Agents Hermes](hermes-agent.md) · [Inférence LiteLLM](inference-litellm.md) · [Confidentialité Presidio](confidentialite-presidio.md) · [Guide de Déploiement](deploiement-universel.md).
