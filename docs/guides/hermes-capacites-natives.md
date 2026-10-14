# Hermes : capacités natives et adéquation à ArcIA

Évaluation du **14 octobre 2026**, à partir du corpus officiel publié et des
sources de la révision verrouillée `818c13be1dc4fd28987e1e881a9408224afd4535`.
La documentation décrit des capacités ; leur présence dans les sources ne vaut
pas leur activation ni leur qualification sur le cluster ArcIA.

**Hermes convient comme moteur d'agents et interface personnelle. La plateforme
d'entreprise complète exige encore les frontières d'identité, de données et de
sortie d'ArcIA.** La priorité donnée par le propriétaire est de réutiliser le
natif, y compris son authentification et sa configuration des fournisseurs.
Le retrait annoncé des réglages natifs est suspendu pendant cette évaluation.

## Corpus et portée de la vérification

Le site fournit un [index officiel](https://hermes-agent.nousresearch.com/docs/llms.txt)
et le [corpus complet](https://hermes-agent.nousresearch.com/llms-full.txt).
Le corpus téléchargé contient **239 pages**, 5 630 844 octets : installation,
utilisation, fonctionnalités, messageries, intégrations, guides, développement
et référence. Toutes les pages ont été indexées par titre, sections et
occurrences des exigences ArcIA. Les contrats déterminants ci-dessous ont été
examinés dans leur texte et confrontés au dépôt de la version verrouillée.
Cela distingue une acquisition/indexation complète d'une lecture exhaustive
de chaque exemple et d'une recette fonctionnelle.

La [preuve de l'audit](../qualification/2026-10-14-hermes-native-docs.json)
conserve provenance, empreintes, inventaire et périmètre des contrôles. Les
copies complètes locales restent dans `artifacts/`, hors Git. Aucun installateur,
plugin ou exemple trouvé dans la documentation n'a été exécuté par cet audit.

## Ce qui existe nativement

| Besoin | Fonction Hermes | Conséquence pour ArcIA |
|---|---|---|
| Connexion au dashboard | Mot de passe partagé, OAuth Nous et OIDC self-hosted | Réutiliser OIDC avec Keycloak ; le mot de passe partagé ne crée pas un annuaire multi-utilisateur |
| Configuration personnelle | Profil avec son home, configuration, credentials, mémoire et état | Réutiliser ces mécanismes dans un runtime lié au propriétaire |
| Choix du fournisseur et du modèle | Écrans Models/API Keys, commandes de modèle et endpoints personnalisés | Une nouvelle interface de configuration complète n'est pas nécessaire par principe |
| Résilience des modèles | Replis entre fournisseurs, modèles auxiliaires, pools de credentials | Réutiliser les fonctions natives, en imposant le filtrage sur chaque destination |
| Clés et certains OAuth | Adaptateurs fournisseurs et gestion des credentials | Vérifier chaque méthode et les conditions du fournisseur, sans réécrire tous les adaptateurs |
| Coffres | Bitwarden, 1Password, helper et interface SecretSource | Un adaptateur de coffre ArcIA peut réutiliser l'orchestrateur natif |
| Réglages administrateur | Managed Scope | Imposer les seules valeurs nécessaires, plutôt que bloquer toute configuration |
| Extension | Plugins de modèle, auth, secrets, dashboard et middleware | Préférer une intégration ciblée aux modifications du cœur |

Les [profils](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)
séparent les configurations et états, mais ne constituent pas seuls une
frontière de sécurité entre personnes sur un même système. Le
[dashboard](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard)
gère normalement les profils de la machine : son sélecteur n'est pas une preuve
de contrôle d'accès par propriétaire. ArcIA conserve donc le binding d'identité
et l'isolation des runtimes/volumes.

Le [routage OpenRouter](https://hermes-agent.nousresearch.com/docs/user-guide/features/provider-routing)
concerne les préférences transmises à OpenRouter. Il ne constitue pas un routeur
universel administré pour tous les fournisseurs. Les
[replis](https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers)
et [pools](https://hermes-agent.nousresearch.com/docs/user-guide/features/credential-pools)
résolvent d'autres besoins : reprise après erreur et sélection de credentials.
Le routage automatique du pool d'entreprise reste la responsabilité d'OmniRoute.

## Authentification : conserver le mécanisme Hermes

Le provider OIDC self-hosted natif utilise discovery, PKCE, vérification de
l'identité et renouvellement. Notre
[provider ArcIA](../../services/identity/provider.py) **hérite déjà du provider
natif** ; il ajoute notamment propriétaire fixe, audience et vérification en
ligne. Il n'est donc pas une réécriture du login Hermes.

L'annuaire, l'attribution des rôles ArcIA et le provisioning Kubernetes restent
externes. Accepter un login OIDC ne suffit pas à établir que cette personne peut
administrer un autre profil ou ajouter un fournisseur.

**Keycloak reste le fournisseur d'identité avant la bascule.** Hermes
réutilise ses comptes et son login via OIDC ; il ne remplace pas l'annuaire.
Un branchement direct sur Entra ID est techniquement une autre option OIDC,
mais exige une migration des identités, clients, rôles et contrôles. Ce n'est
pas une suppression transparente avec les comptes locaux permanents actuels.
Le propriétaire a depuis choisi Entra direct et un seul `admin` local ; il
autorise le retrait de Keycloak après test humain. La
[recette préalable](../runbooks/entra-hermes-test.md) et l'
[ADR 0023](../adr/0023-entra-direct-et-admin-local.md) précisent cette évolution.

Hermes fournit aussi une séparation admin/utilisateur pour les commandes des
messageries via `allow_admin_from` et `user_allowed_commands`. Ce mécanisme
documenté n'est pas, à lui seul, un RBAC général du dashboard indexé sur nos rôles
Keycloak. [Référence des commandes](https://hermes-agent.nousresearch.com/docs/reference/slash-commands).

## Fournisseurs personnels : API et OAuth

La configuration peut être gérée par les surfaces natives du runtime personnel,
après contrôle serveur du rôle **ArcIA.ProviderSelfService**, en plus de
`ArcIA.User`. Ni le rôle admin seul ni un nouvel utilisateur n'obtiennent
automatiquement ce droit. L'affectation d'un profil et le droit de modifier ses
providers restent deux contrôles distincts.

| Exemple demandé | Capacité native | État ArcIA et condition |
|---|---|---|
| OpenRouter, clé API | Provider API, choix de modèle et préférences OpenRouter | Clé enregistrable dans Mes clés IA ; utilisation personnelle non raccordée/qualifiée |
| OpenAI, clé API | Provider API/endpoint compatible | Même limite ; la clé API est distincte d'un abonnement ChatGPT |
| Claude, OAuth | Parcours technique Anthropic OAuth/credentials Claude Code documenté par Hermes | Aucune activation ArcIA ; les conditions Anthropic ci-dessous empêchent de le présenter comme une connexion autorisée générique |

Hermes documente techniquement le parcours Claude OAuth avec des conditions de
plan/crédits. Cela corrige l'affirmation selon laquelle Hermes ne sait pas gérer
OAuth. Mais la documentation d'Anthropic interdit aux applications tierces de
proposer leur propre login Claude.ai et de collecter/intermédier les tokens de
session Claude.ai ; elle demande API Console ou fournisseur cloud supporté pour
ces applications. L'hébergement du binaire Claude Code non modifié est un cas
différent. **Le parcours OAuth Claude demandé ne doit donc pas être activé comme
provider Hermes/ArcIA sur cette seule base technique.**
[Capacités Hermes](https://hermes-agent.nousresearch.com/docs/integrations/providers)
et [conditions officielles Anthropic](https://code.claude.com/docs/en/legal-and-compliance).

### Sécurité des clés

Le natif accepte des fichiers `.env` et des credentials persistés dans
`auth.json` ; ce n'est pas une garantie de chiffrement applicatif par
propriétaire. Les credentials empruntés à une source externe sont référencés et
réhydratés ; une entrée manuelle peut au contraire contenir sa valeur dans le
store. La sauvegarde et les droits du home restent nécessaires.
[Stockage des pools](https://hermes-agent.nousresearch.com/docs/user-guide/features/credential-pools).

Les [sources de secrets](https://hermes-agent.nousresearch.com/docs/user-guide/secrets)
permettent d'éviter de conserver les clés fournisseurs dans `.env`. Elles
réutilisent les priorités, l'origine et le scope du profil ; les credentials
fournisseurs sont exclus du passthrough normal aux sous-processus d'outils.
Cela ne dispense pas de l'isolation système ni d'un contrôle du coffre.

Dans le lot ArcIA déjà livré, `/portal/keys` stocke les valeurs par AES-256-GCM,
liées au propriétaire, avec clé racine séparée. Cette page **n'alimente pas
encore Hermes**. Deux intégrations sont à comparer : source de secrets native
reliée au store ArcIA, ou références de routes vers un service qui conserve les
credentials hors du runtime. Aucun duplicata de clé dans Hermes n'est introduit
par cet audit. [Configuration livrée](omniroute.md#entreprise-et-fournisseurs-personnels).

Le dashboard OmniRoute ne détient pas ces stores personnels. Les administrateurs
d'infrastructure ou du service qui possèdent la clé de déchiffrement restent des
personnes de confiance ; le chiffrement au repos ne les exclut pas.

## Presidio obligatoire : la limite décisive

**Le filtrage doit s'appliquer à chaque appel modèle, quel que soit le fournisseur,
personnel ou d'entreprise, et à ses replis et tâches auxiliaires.** Cette exigence
du propriétaire remplace la cible antérieure qui laissait les routes internes
non filtrées. Le code et le bootstrap anciens ne sont pas encore migrés vers
cette nouvelle exigence dans ce lot d'audit documentaire.

Un modèle ou fournisseur visible dans Hermes n'est pas intrinsèquement un choix
d'activer Presidio. Le choix d'une route et l'obligation de filtrage sont deux
fonctions distinctes. L'interface native peut rester utile si **toutes** les
destinations qu'elle permet sont soumises à la même frontière obligatoire.
C'est une orientation d'intégration, pas une garantie actuelle.

Trois limites natives empêchent de déclarer cette garantie acquise :

1. Les middlewares peuvent transformer les requêtes, mais une exception du
   middleware laisse continuer le chemin normal. Un middleware Presidio seul
   ne bloque donc pas nécessairement une requête non filtrée.
   [Contrat middleware](https://hermes-agent.nousresearch.com/docs/developer-guide/middleware).
2. Managed Scope impose des valeurs administrateur, mais repose sur les droits
   des fichiers ; un fichier malformé est ignoré, et sa variable de localisation
   ne doit pas être contrôlée par l'utilisateur. Ce n'est pas un sandbox.
   [Limites de Managed Scope](https://hermes-agent.nousresearch.com/docs/user-guide/managed-scope).
3. Iron-proxy fournit allowlist et injection de credentials pour le sandbox,
   mais ne couvre pas les appels LLM faits par le processus hôte. Son activation
   seule ne suffit pas à notre frontière Presidio.
   [Périmètre iron-proxy](https://hermes-agent.nousresearch.com/docs/user-guide/egress/iron-proxy).

Une sortie contrôlée extérieure au processus Hermes doit donc refuser l'appel
en cas d'indisponibilité du filtrage et fermer les chemins directs. Elle peut
coexister avec les adaptateurs natifs, mais il faut qualifier les transports,
OAuth, streaming, outils, auxiliaires et replis réellement utilisés. Les sorties
de recherche web, vision, voix et autres outils cloud ont aussi leur propre
contrôle ; sécuriser le modèle principal ne prouve pas leur couverture.

## État réel observé et suites

Une inspection sans appel modèle a relu les **six runtimes actifs** :
`auto/smart`, transport custom, endpoint configuré et environnement cohérents
vers le Service OmniRoute. Ce résultat diffère du renderer Privacy versionné,
qui décrit le relais historique filtré. La référence du credential reste le
Secret interne nommé ; ni sa valeur ni une configuration privée n'ont été
restituées.

**Cette inspection ne prouve ni le passage par Presidio ni une sortie non
filtrée réussie.** Le chemin effectif, ses politiques réseau et l'origine de la
dérive doivent être audités avant toute déclaration de conformité ou migration.
Aucune connexion fournisseur, clé, configuration de modèle ou ressource du
cluster n'a été modifiée par cette évaluation.

La suite privilégie les fonctions natives : conserver login OIDC et état Hermes,
qualifier Managed Scope et les coffres, exposer la configuration personnelle
uniquement au rôle requis, puis établir la sortie Presidio obligatoire. ArcIA
porte le provisioning, les ACL d'entreprise, la sécurité réseau et les
approbations serveur. OmniRoute conserve le pool central administré.

Le [backlog](../backlog.md), l'[état courant](../etat-reprise.md) et les
[schémas](../schemas-plateforme-hermes.md) distinguent ces capacités du socle
effectivement déployé.
