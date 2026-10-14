# Microsoft 365 — parcours accompagné ArcIA

Session commencée le 13 octobre 2026. Ce guide complète
[l'annexe technique](integration-microsoft365.md), sans attester sa mise en œuvre.

## Point de départ et choix du login

La cible déployée utilise Keycloak pour les comptes locaux permanents.
Commencer par **ArcIA-Entra-Broker** pour ajouter la connexion Microsoft à
ces comptes. Le parcours direct **ArcIA-Web** est une autre architecture :
ne pas utiliser son callback pour configurer le broker.

| Application | Fonction | Callback ou restriction principale |
|---|---|---|
| ArcIA-Entra-Broker | Connexion Microsoft via Keycloak | Web : `https://<DOMAINE_INSTANCE>/identity/realms/arcia/broker/<ALIAS_FOURNISSEUR>/endpoint` |
| ArcIA-Teams | Conversation personnelle et SSO Teams | Azure Bot, canal Teams et API `access_as_user` ; annexe §6 |
| ArcIA-Meetings | Lire les transcriptions | Permissions Graph et policy limitée aux organisateurs pilotes ; annexe §7 |
| ArcIA-SharePoint | Collecte documentaire | `Sites.Selected` et grant `read` explicite par site ; annexe §8 |
| ArcIA-Outlook-User | Courriel et calendrier personnels | Délégué ; callback `/auth/microsoft365/callback` ; annexe §9.1 |
| ArcIA-Outlook-Service | Traitement Exchange sans utilisateur, optionnel | RBAC Exchange borné ; annexe §9.2 |

Les connecteurs Teams/Graph ne sont pas encore livrés par le harness.
Leur préparation Microsoft ne permet pas de les annoncer fonctionnels.
Les comptes locaux restent disponibles après ajout du broker.

## 1. Inscription du broker Entra

1. Vérifier localement que le tenant et l'environnement sont ceux autorisés.
   Aucun identifiant de tenant ou de compte n'est à coller dans le chat.
2. Dans **Entra ID → Inscriptions d'applications**, vérifier les inscriptions
   existantes, y compris **Toutes les applications**, avant de créer un doublon.
3. Si aucune inscription adaptée n'existe, ouvrir **Nouvelle inscription**.
4. Nom proposé : `ArcIA-Entra-Broker`, avec un suffixe d'environnement si requis.
5. Comptes pris en charge : **ce répertoire d'organisation uniquement**.
6. URI de redirection : plateforme **Web**, callback du broker ci-dessus,
   avec le domaine exact validé localement et l'alias réel du fournisseur
   Keycloak. Copier la **Redirect URI** affichée dans ce fournisseur : `entra`
   est l'alias proposé par la documentation, pas une constante imposée.
   L'erreur remontée pendant la session indique l'alias réel `microsoft`.
   Aucun wildcard.
7. Relire puis faire valider la création avant **Inscrire**.
8. Conserver tenant ID, client ID et Object IDs dans l'état privé protégé.
   Distinguer Object ID de l'inscription et du service principal.

Microsoft décrit l'inscription et la sélection mono-tenant dans sa
[procédure officielle](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app).

## 2. Credential et raccordement Keycloak

Faire la création du credential et sa sauvegarde par le parcours local
protégé. Aucune capture pendant l'affichage d'un secret, token, OTP ou clé.
Le Secret ID n'est pas la valeur du secret.

Dans le realm `arcia`, préparer le fournisseur OIDC d'alias `entra` si aucun
fournisseur n'existe ; préserver l'alias réel d'un fournisseur existant :
discovery du tenant explicite, client ID et credential protégé ; scopes
`openid profile`, éventuellement `email` pour l'affichage. Conserver
`Store tokens` désactivé pour le login seul, le formulaire local visible et
la liaison de comptes après preuve de possession. Ne pas fusionner sur le seul
email. Suivre [la procédure identité du projet](../identite-utilisateurs.md).

L'ajout d'un fournisseur, les credentials, consentements et affectations sont
des changements d'accès : préparer le détail, obtenir la validation requise,
puis vérifier l'état effectif. Le login ne requiert pas de permission Graph
de lecture des mails, des sites ou des réunions.

## 3. Qualification de la connexion

Avec une identité pilote et des contenus synthétiques autorisés :
vérifier connexion Microsoft, connexion locale conservée, identité stable
après liaison, refus d'un tenant étranger et d'un utilisateur non autorisé,
révocation et absence d'accès au runtime d'autrui. Ne pas déduire la réussite
de la seule présence de l'inscription Entra.

### Dépannage : AADSTS50011 et alias du callback

Erreur signalée : le callback envoyé se termine par
`/identity/realms/arcia/broker/microsoft/endpoint`, alors que le guide proposait
`/identity/realms/arcia/broker/entra/endpoint`. Le segment après `broker` est
l'alias du fournisseur Keycloak. Le conseil initial aurait dû être confirmé
sur la Redirect URI affichée par le fournisseur avant saisie dans Entra.

Dans **Entra → Inscriptions d'applications → ArcIA-Entra-Broker → Authentication**,
ajouter à la plateforme **Web** l'URI exacte affichée par le fournisseur et
rapportée dans l'erreur, avec l'alias `microsoft`. Préserver les autres URI tant
que leurs usages n'ont pas été vérifiés ; ne pas renommer le fournisseur pour
résoudre cette erreur. Enregistrer, attendre la propagation, puis recommencer
depuis ArcIA. Microsoft indique un délai de trois à cinq minutes.

[Procédure Microsoft AADSTS50011](https://learn.microsoft.com/en-us/troubleshoot/entra/entra-id/app-integration/error-code-aadsts50011-redirect-uri-mismatch).
Correction documentée ; modification du tenant et nouveau login non exécutés
par l'agent. Aucun identifiant réel de tenant ou d'application enregistré ici.

### Dépannage : AADSTS50194 et endpoint `/common`

Erreur signalée pendant le parcours : l'application mono-tenant reçoit une
demande via `/common`. Conserver le mono-tenant ; corriger l'autorité utilisée
par le fournisseur d'identité. Le client ID de l'application n'est pas le
tenant ID. Relever ce dernier localement dans la vue d'ensemble Entra.

Dans **Keycloak → realm arcia → Identity providers → fournisseur utilisé** :

- Si le type est **Microsoft**, renseigner **Tenant ID** avec l'ID du répertoire
  cible. Le code officiel Keycloak 26.8.1 utilise `common` si ce champ est vide.
- Si le type est **OpenID Connect v1.0**, utiliser la discovery spécifique :
  `https://login.microsoftonline.com/<TENANT_ID>/v2.0/.well-known/openid-configuration`.
  Vérifier que les endpoints d'autorisation, de token et l'issuer proviennent
  de cette discovery et désignent le tenant cible.

Après sauvegarde par l'administrateur, recommencer une connexion depuis ArcIA.
Vérifier localement que l'URL d'autorisation contient le tenant attendu à la
place de `common`. Ne pas éditer à la main une ancienne URL de connexion ni
partager ses paramètres `code`, `state`, tokens ou autres valeurs privées.
La disparition d'AADSTS50194 ne qualifie pas à elle seule la connexion complète.

Le fournisseur Microsoft prédéfini utilise Graph `/me` et le scope `User.read`,
alors que le parcours du projet privilégie OIDC avec `openid profile`. Ne pas
changer de type de fournisseur existant ou retirer ses permissions sans revoir
la liaison des comptes et préserver l'identité stable. Identifier d'abord le
type effectivement configuré ; aucune migration implicite n'est réalisée ici.

Sources officielles consultées le 13 octobre 2026 :
[autorités Microsoft OIDC](https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc),
[fournisseur Microsoft Keycloak 26.8.1](https://github.com/keycloak/keycloak/blob/26.8.1/services/src/main/java/org/keycloak/social/microsoft/MicrosoftIdentityProvider.java).
Diagnostic documenté ; correction sur la cible et nouveau login non exécutés
dans cette session.

### Dépannage : erreur générique Keycloak après le retour Microsoft

La page `Unexpected error when authenticating with identity provider` ne
permet pas de distinguer problème réseau, credential refusé ou profil Graph.
Ne pas modifier les permissions Entra au hasard. Lire les journaux par un
contrôleur protégé ; ne restituer que catégories et codes, et chiffrer les
preuves brutes avant stockage local.

Diagnostic exécuté le 13 octobre 2026 sur la cible possédée, en lecture seule :
Keycloak disponible (une réplique), deux événements d'erreur du broker sur les
trente dernières minutes, stack du callback OAuth, hôte Microsoft de login
présent et `java.net.SocketException: Network is unreachable`. Aucune règle
de sortie TCP/443 dans les deux NetworkPolicies sélectionnant Keycloak.
Aucun code AADSTS ni marqueur `invalid_client` dans cet échantillon : cela ne
prouve pas que le credential fonctionnera après correction réseau.

Le rendu du socle autorise DNS et PostgreSQL, sans sortie Microsoft. Préparer
une sortie contrôlée pour l'échange de tokens ; le fournisseur Microsoft
prédéfini nécessite aussi Graph pour `/me`. Ne pas ouvrir tout Internet à
Keycloak ou Hermes. Une NetworkPolicy Kubernetes standard ne fournit pas
une allowlist DNS ; choisir un mécanisme de contrôle de destination adapté.

Diagnostic et plan : [handoff du blocage réseau](../handoff-2026-10-13-m365-broker-reseau.md).
Correction réseau non codée/non déployée ; nouvelle connexion non vérifiée.

## 4. Préparation des connecteurs, dans cet ordre

Pour chaque application : vérifier l'existant, préparer les paramètres et le
périmètre pilote, valider les changements d'accès, appliquer, relire, puis
exécuter une recette positive et négative. Conserver les preuves brutes hors Git.

1. **Teams personnel** : inscription dédiée, Azure Bot mono-tenant, canal Teams,
   endpoint bot distinct du portail, SSO, puis package pilote. La publication et
   le test attendent le récepteur ArcIA et un package réellement disponibles.
2. **Réunions** : lecture des transcriptions, policy d'accès par organisateur,
   politique de transcription pilote, puis essai sur une réunion synthétique.
   Aucun droit audio ou accès global implicite.
3. **SharePoint** : inscription dédiée, `Sites.Selected`, consentement et grant
   `read` par site sélectionné. Tester un site autorisé et un site hors périmètre.
   Les copies indexées exigent aussi les ACL ArcIA.
4. **Outlook personnel** : inscription déléguée, `Mail.Read` et `Calendars.Read`
   selon besoins retenus ; connexion personnelle et tokens chiffrés. Aucun envoi.
5. **Outlook applicatif**, seulement si retenu : identité distincte et RBAC
   Exchange limité aux boîtes pilotes, sans permission Graph applicative globale
   additive. Tester un refus réel sur une boîte hors scope.
6. **Exploitation** : rotation, retrait des droits, kill switch, révocation,
   rétention et reprise sans double écriture. Webhooks seulement après livraison
   et qualification des handlers ; le contrat initial préfère le polling.

Les écrans, permissions exactes et commandes administratives de ces étapes
restent décrits dans les §6–13 de [l'annexe](integration-microsoft365.md).

## Captures et état de session

Les illustrations doivent être des captures réelles assainies **localement
avant transmission** : retirer compte connecté, tenant, domaines internes,
identifiants, inventaires et onglets étrangers au parcours. Utiliser des aplats
opaques et vérifier le fichier aplati. Ne jamais capturer un écran de secrets.
Une reproduction de formulaire n'est pas une preuve de configuration.

État constaté le 13 octobre 2026 : fenêtre Chrome ouverte sur **Inscriptions
d'applications**, onglet **Applications détenues**. Lecture limitée aux libellés
publics de navigation ; aucune valeur confidentielle importée volontairement.
Tentative d'ouverture de **Nouvelle inscription** refusée par l'outil Windows
(`coordinate input geometry is unavailable`) : ouverture non vérifiée.

**Aucune capture produite, aucune inscription créée, aucun consentement,
credential ou accès modifié.** L'outil Windows documenté affiche automatiquement
les captures brutes avant retouche ; il ne fournit pas ici un mode de capture
masquée préalable. Le contrôle navigateur disponible n'est pas connecté à Chrome.
Reprendre avec un canal permettant le masquage local avant transmission, ou
avec navigation manuelle accompagnée pour cette première étape.
