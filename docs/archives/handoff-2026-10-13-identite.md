# Handoff — identité locale permanente, 13 octobre 2026

> Archive historique. Pour la reprise actuelle, lire [l’état courant](../etat-reprise.md).

## Décision et livraison

Les comptes locaux sont une fonction permanente, par défaut, administrable sans
SSO. Keycloak fournit le portail de gestion ; Entra/autres SSO peuvent être
ajoutés en parallèle avec liaison explicite des identités. Pas de fusion sur email.
Référence : [Identité et portail utilisateurs](../guides/identite-utilisateurs.md), ADR 0016.

Déployé sur la cible K3s possédée : Keycloak 26.8.1 officiel amd64 par digest,
base CNPG dédiée, HTTPS privé `/admin/users` et `/account`. Aucun nouveau NAT
ni tenant Microsoft contacté. Credentials générés dans `identity.dpapi` ; le
compte bootstrap master est supprimé et son env retiré après initialisation.
L'admin initial doit changer son mot de passe et configurer TOTP dans le navigateur.

Les deux états Hermes existants sont rattachés à deux comptes synthétiques du
realm avec UUID/client propres. Le provider ArcIA vérifie JWT RS256, issuer,
audience, propriétaire, client, rôle et état en ligne UserInfo. PKCE S256/state/
nonce ; aucun secret client ou credential d'administration dans les runtimes.
Le provider basic historique est désactivé dans les processus rattachés.
Les volumes, historiques et credentials précédents restent préservés.

## Vérifications réellement exécutées

- 15 contrôles d'administration native Keycloak réussis : CRUD utilisateur,
  suspension, reset, affectation de rôle, révocation, issuer/PKCE et services.
- 12 contrôles HTTPS/OIDC réels réussis : portail accessible, master refusé,
  login A/B, propriétaires croisés refusés, compte désactivé refusé, sessions
  révoquées refusées et reconnexion après restauration sans reset.
- Recette multi-utilisateur complète : 200 contrôles réussis après migration,
  dont isolation des quatre volumes, corpus commun/personnels, outils, restart,
  sessions, exports et rejeu après logout.
- Recette HTTPS/auth du pilote : 7 contrôles réussis avec login Keycloak.
- Réapplication identité exécutée : realm ID, admin ID et reconciler ID
  conservés. Base/volumes et credentials ne sont pas recréés.
- 12 nouveaux tests unitaires identité/provider réussis ; tests bootstrap,
  parse PowerShell, coverage 48 étapes et validate_sources réussis.
- Suite locale Windows : 172 tests, 164 réussis, 7 ignorés, 1 erreur dans le
  test réseau Linux préexistant (`/etc/resolv.conf` absent sous Windows).
  Ce résultat n'est pas annoncé vert ; consulter la CI Linux du commit publié.

Les [preuves assainies](../qualification/2026-10-13-identite.json) ne contiennent
aucun domaine/IP, compte réel, token ou secret. Les preuves détaillées sont
dans l'état protégé de l'ingénieur. Le lot a corrigé deux erreurs de parcours
de qualification : attribut propriétaire explicitement déclaré dans le profil
Keycloak et port interne NGINX retiré des redirections externes. Une fixture
créée par le lot, jamais rattachée, a été nettoyée avant recréation ; aucun
ancien compte utilisateur n'a été supprimé ou réinitialisé.

## Bootstrap et reprise

Le lock des composants épingle Keycloak, celui d'identité épingle sources et
provider. Le manifeste ajoute install/verify/connect/verify_access/inspect.
Plan expose la solution par défaut et les comptes permanents. Reconcile conserve
les modifications administratives des comptes et les providers ; un rebinding
vers un autre UUID ou une dérive de credential est refusé. Le renderer monte
le plugin indépendamment des packs de skills et conserve les liaisons par
Secret propre au namespace. Les seeds sans liaison restent en qualification
jusqu'au rattachement, qui précède l'ouverture de l'accès.

Accès utilisateur à remettre :

```powershell
./scripts/Show-IdentityAccess.ps1 -OpenPortal
```

Les passwords ne passent ni dans le chat ni dans la ligne de commande.
L'administrateur doit créer les admins nominatifs et traiter son compte initial.

## Limites et lots suivants

### Correction de l'accès depuis un terminal Windows

Le retour utilisateur `MULTIPLE_PROTECTED_ARCIA_STATES_REFUSED` a montré que
le helper du portail utilisait la découverte générique des états VMware.
`Show-IdentityAccess` exige désormais un état d'identité complet, lié au même
identifiant d'opération que l'instance et VMware. Les alias physiques MSIX sont
dédupliqués sans sensibilité à la casse ; plusieurs états complets demandent
un choix dans le formulaire local. L'automatisation reste fermée en cas
d'ambiguïté. Aucun état privé, credential ni compte n'est modifié par ce correctif.
La régression Windows DPAPI couvre les anciens états, les scopes incompatibles,
les alias, le refus d'ambiguïté automatique et le choix explicite simulé. Le
lock et le contrat du bootstrap incluent les deux scripts d'accès.

### Fonctionnalités restant à qualifier

La gestion d'un nombre arbitraire de **comptes** est native dans le portail.
Le provisioning de nouveaux runtimes/PVC, ACL dynamiques de groupes, intégration
réelle Entra et connecteurs Microsoft, SMTP, passkeys et délégation fine des
administrateurs demandent leurs recettes propres. Seuls les deux espaces
Hermes existants sont provisionnés ; un nouveau compte ne partage pas leurs
états. HA identité, backup/restore, rebuild neuf et homologation de données
réelles restent non qualifiés. Le contrôle des flux longs est codé ; la matrice
complète de déconnexion SSE/WebSocket/Desktop reste à exercer séparément.
