# Skill : Public-APIs (Référentiel de Veille & Intégration Sécurisée d'APIs Ouvertes)

## Présentation

Le référentiel **Public-APIs** recense les sources de données ouvertes, les APIs publiques souveraines (Open Data, INSEE, Météo, Cadastre, géocodage, transports) et les services tiers documentés.

> [!WARNING]
> **Règle Fondatrice d'ArcIA : Hermétisme Réseau**
> `public-apis` est un **catalogue statique de référence et de veille**, et **en aucun cas un service ou une autorisation d'accès Internet libre**.
> Hermes et les runtimes de calcul n'ont pas de connectivité Internet ouverte non filtrée. Tout accès externe doit être formellement qualifié, approuvé au niveau de l'instance et borné par une `NetworkPolicy`.

---

## Protocole de Qualification d'une API Publique

Avant de concevoir ou d'invoquer un connecteur vers une API publique recensée :

1. **Vérification de la Source & de la Licence** :
   - Vérifier la gratuité, les quotas d'usage (rate limits), la présence d'une spécification OpenAPI/Swagger ou d'un schéma JSON strict.
   - Vérifier la compatibilité légale avec l'usage d'entreprise (licences ouvertes type Etalab, MIT, Apache).

2. **Gouvernance & Filtrage DLP** :
   - Tout appel vers une API tierce ne doit contenir **aucune Donnée à Caractère Personnel (PII)**, aucun secret d'entreprise, ni jeton interne.
   - Les requêtes sortantes doivent être préalablement assainies par la passerelle Presidio DLP.

3. **Déclaration du Connecteur (MCP d'Instance)** :
   - Le connecteur doit être implémenté sous forme d'outil MCP ou de micro-proxy dans le dépôt d'instance de l'organisation.
   - Les clés d'API (le cas échéant) sont stockées dans des secrets Kubernetes chiffrés et injectées par variable d'environnement, jamais écrites dans le code.

4. **Isolation Réseau Kubernetes (Egress NetworkPolicy)** :
   - Une règle d'egress stricte doit être déployée sur le namespace pour autoriser uniquement l'adresse IP / FQDN et le port de l'API ciblée, interdisant tout autre trafic sortant.
