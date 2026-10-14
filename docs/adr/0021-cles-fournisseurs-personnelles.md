# ADR 0021 — Configuration des clés personnelles dans ArcIA

Décision du 14 octobre 2026 : sur demande du propriétaire, seuls les comptes
explicitement habilités `ArcIA.ProviderSelfService`, avec `ArcIA.User`, peuvent
enregistrer leurs clés. Aucun octroi automatique aux utilisateurs actuels ou
futurs ; le rôle admin seul ne suffit pas.

Le propriétaire autorise explicitement l'application du lot. Il précise que
l'exigence d'approbation Teams vise les futures actions des utilisateurs et
de leurs agents en exploitation, pas l'intervention de l'IA Platform Engineer.
Cette clarification est reportée dans [AGENTS.md](../../AGENTS.md) ; la cible
désignée et les protections des secrets restent obligatoires.

La page `/portal/keys` et son API `/portal/api/keys` utilisent la session OIDC
du portail. Chaque requête relit les rôles courants via UserInfo. Le subject et
l'issuer viennent de l'identité vérifiée ; aucun propriétaire, endpoint ou
modèle n'est accepté dans le corps client. Origin et CSRF sont exigés en écriture.

Une clé par fournisseur peut être ajoutée/remplacée/supprimée. Les valeurs
sont chiffrées par AES-256-GCM, avec authentification de l'opération et du
propriétaire, dans un Secret nommé de son emplacement fixe. La clé de
chiffrement séparée reste dans `portal-key-encryption`, uniquement montée dans
le portail. Les runtimes et le navigateur ne reçoivent pas les valeurs stockées.
Les droits Kubernetes restent bornés à `get/patch` de ce Secret, sans list/create.

Réapplication : conserver les Secrets, la clé de chiffrement, les identités et
les volumes. Une clé racine manquante avec des données déjà chiffrées bloque
l'installation et exige une récupération ; aucune rotation silencieuse.

L'enregistrement reste **inactif pour l'inférence**. Il ne crée pas de provider
global OmniRoute ni de test automatique vers un fournisseur. L'API native
OmniRoute de création déclenche un test de connexion ; le raccordement personnel
doit donc être qualifié séparément avec politique d'instance, droits et filtrage.
Le retrait du rôle interdit immédiatement la gestion des clés ; les données
inactives restent chiffrées et conservées pour l'administrateur.

[Guide et procédure](../guides/omniroute.md) · [Bootstrap](../runbooks/bootstrap.md)
