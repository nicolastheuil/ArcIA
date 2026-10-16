# ArcIA : périmètre, fonctionnement et partage

ArcIA est une plateforme d’IA agentique d’entreprise. Hermes est son moteur d’agents ; `ArcIA` est le dépôt de son socle générique. Aucun domaine, métier, compte fournisseur ou corpus privé d’une organisation ne définit le produit.

---

## 1. Capacités et architecture

Les agents utilisent des outils autorisés, consultent une base de compétences et de connecteurs, délèguent des tâches bornées et produisent des réponses ou fichiers vérifiables :
- **Portail Collaborateur (Open-WebUI)** : Interface web moderne pour les requêtes quotidiennes, intégrée au SSO Microsoft Entra ID.
- **Studio Kanban & Gateway (Hermes Agent)** : Pilotage visuel des missions longues, multi-agents, et connexion native pour l'application de bureau Hermes Desktop.
- **Passerelle d'Inférence d'Entreprise (LiteLLM)** : Routage unifié des modèles souverains managés (`ArcIA-Agentic (auto)`, `ArcIA-Agentic (expert)`), résilience et suivi des quotas.
- **Gouvernance & Confidentialité (Presidio DLP)** : Caviardage automatique des PII et des secrets d'entreprise avant tout appel vers un LLM externe.
- **Canal Microsoft Teams** : Bot interactif pour les échanges directs et le travail en équipe.

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
| **Portail Web** | Accès collaborateurs avec SSO Entra ID ou comptes locaux | Open-WebUI sur port 8080 avec persistance PVC 20Gi |
| **Studio & Gateway** | Espace de pilotage Kanban et API pour Hermes Desktop | Hermes Studio sur port 9119 et Gateway sur port 8642 avec PVC 20Gi |
| **Sortie Cloud** | Anonymisation systématique des flux externes | Presidio DLP sur port 8080 devant LiteLLM |
| **Canaux Collaboratifs**| Bot Teams en direct message ou mention de canal | Teams Bot Adapter sur port 3978 |

Chaque instance Hermes conserve un propriétaire unique de son état SQLite persistant (`state.db`). Des profils ou sous-agents ne constituent pas une isolation de sécurité.

---

## 4. Parcours d’une demande

1. **Identification** : L'utilisateur s'identifie via SSO Entra ID sur le portail ou Teams.
2. **Consultation & Outils** : Hermes ou le portail consulte les compétences requises (skills locales, outils de code, analyse AST Graphify).
3. **Assainissement DLP** : Toute requête destinée à un modèle cloud externe passe préalablement par Presidio DLP pour caviardage des données sensibles.
4. **Inférence & Synthèse** : LiteLLM achemine la requête assainie vers le modèle approprié et restitue la réponse.
5. **Actions Externes** : Toute action sensible extérieure requiert validation explicite selon la politique de gouvernance.

Voir également : [Moteur d'Agents Hermes](hermes-agent.md) · [Inférence LiteLLM](inference-litellm.md) · [Confidentialité Presidio](confidentialite-presidio.md) · [Guide de Déploiement](deploiement-universel.md).
