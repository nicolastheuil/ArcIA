# Tester Entra ID directement dans Hermes

Le propriétaire a retenu Entra ID pour les utilisateurs et un seul compte local
de secours `admin`. **Configurer et faire tester le login avant de supprimer
Keycloak.** Ce lot fournit un espace d'authentification isolé ; il ne remplace pas
encore le provisioning des espaces personnels.
[Décision](../adr/0023-entra-direct-et-admin-local.md).

## Enrôlement protégé

Exécuter le formulaire local ; ne copier aucune valeur dans le chat :

```powershell
./scripts/Configure-EntraTest.ps1
```

Enregistrer tenant, client d'application Web mono-tenant, secret applicatif et
Object ID Entra du compte de test. Ajouter l'URI affichée au type **Web** de
l'application : `https://<nom-HTTPS-instance>/entra-test/auth/callback`.
Les paramètres sont conservés dans `entra-test.dpapi`, liés à l'opération ; le
mot de passe Microsoft ne doit pas être fourni à ArcIA.

Les clés de connexion du compte local `admin` sont générées par le programme
protégé à la première installation, puis conservées dans `entra-test-admin.dpapi`.
La réapplication refuse un écart entre ce credential et le Secret installé.

## Déploiement et vérifications techniques

```powershell
./scripts/Invoke-ClusterFoundation.ps1 -Action install_entra_test
./scripts/Invoke-ClusterFoundation.ps1 -Action verify_entra_test
```

Le renderer crée uniquement le namespace `arcia-entra-test` : runtime Hermes,
état et outils propres, plugin d'authentification, Secret OIDC et relais TLS.
Le worker ajoute le chemin fixe dans l'ingress HTTPS existant après validation
Nginx ; il conserve les autres chemins, le certificat et les espaces existants.
Aucun utilisateur ni Secret Keycloak n'est modifié.

Les contrôles techniques vérifient l'annonce des providers `entra` et `basic`,
le refus de configuration anonyme, le login local `admin`, le propriétaire
unique du runtime, l'absence de service account, la politique réseau et le
maintien de Keycloak. Un succès ne prouve pas encore le login Entra interactif.
La classe ArcIA hérite du provider self-hosted Hermes ; elle conserve son
discovery, PKCE, vérification JWT et refresh, puis refuse un autre tenant/OID.
Elle ne remplace pas le serveur d'authentification Microsoft.

Le canary est **réservé au test de login**. Les appels IA y sont désactivés et
les destinations d'inférence sont refusées par le réseau/relais. Le relais
transporte TLS sans journaliser les corps et ne reçoit pas le secret pour
décrypter les sessions ; il autorise seulement l'autorité Microsoft exacte.

## Test humain

```powershell
./scripts/Open-EntraTest.ps1
```

Le helper lit la cible protégée et ouvre un profil navigateur dédié, après
`ENTRA_TEST_VERIFIED`, directement sur le login Entra du runtime de test.
L'utilisateur réalise lui-même la connexion et le MFA chez Microsoft.

1. Vérifier que la connexion se déroule chez Microsoft, sans écran Keycloak.
2. Vérifier le retour dans Hermes, sur l'espace de test attendu.
3. Tester logout et reconnexion. Le retour après expiration/refresh et les
   refus croisés restent à qualifier avant généralisation.
4. Confirmer le résultat au responsable de l'installation ; en cas d'échec,
   communiquer seulement le code d'erreur, sans code OAuth, cookie ni token.

Une erreur de callback indique notamment que l'URI n'est pas enregistrée sur
la bonne application. Un mauvais tenant/OID est refusé même après un login
Microsoft réussi. En cas d'erreur, Keycloak reste utilisable : sa suppression
n'est pas lancée par cette procédure.

## Bootstrap et suite

Les deux étapes sont optionnelles et sélectionnées avec `-TestEntra` :

```powershell
./scripts/Bootstrap-Harness.ps1 -Mode Plan -Profile Reconcile -TestEntra
```

Les scripts, provider et relais sont couverts par `bootstrap/identity.lock.json`.
Les ressources du canary et son compte local sont conservés à la réapplication.
Le renderer ingress connaît le chemin fixe, même si le canary n'est pas actif.
Une demande de test ne déclenche pas le bootstrap complet du cluster.

Après validation humaine, préparer la bascule du portail/provisioning vers
Entra, les rôles applicatifs et l'administration locale unique. Microsoft
UserInfo ne restitue pas nos rôles personnalisés : la lecture des rôles
Keycloak actuelle ne peut pas simplement être remplacée par cette URL.
[UserInfo Microsoft](https://learn.microsoft.com/en-us/entra/identity-platform/userinfo).
Supprimer ensuite les seules ressources Keycloak dédiées conformément à la
décision, sans supprimer les composants partagés d'ArcIA.

L'[état courant](../etat-reprise.md) porte le dernier résultat exécuté ; les
[capacités natives](../guides/hermes-capacites-natives.md) expliquent les limites.
