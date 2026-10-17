---
name: public-apis
description: Consultation et vérification automatique d'entreprises françaises (SIRET, SIREN, TVA intracommunautaire, dirigeants), d'adresses postales (BAN) et de météo ouverte via les APIs souveraines officielles de l'État français.
author: ArcIA Platform Team
version: 1.1.0
triggers:
  - SIRET
  - SIREN
  - TVA intracommunautaire
  - vérification entreprise
  - dirigeants société
  - adresse postale
  - géocodage
  - météo locale
---

# Skill : Public-APIs (Passerelle Souveraine Open Data & Entreprises)

## 1. Présentation & Périmètre

La skill **public-apis** fournit un accès **instantané, 100% gratuit, sans clé d'API et mis en cache localement** aux référentiels publics officiels de l'État français et aux données ouvertes européennes :

1. **Vérification d'Entreprises (INSEE / SIRENE / RNE)** :
   - Recherche par SIREN (9 chiffres), SIRET (14 chiffres) ou raison sociale.
   - Restitution officielle : Nom complet, SIRET du siège, Code NAF/APE, état d'activité (actif/fermé), adresse légale, date d'immatriculation et dirigeants.
   - **Calcul automatique du numéro de TVA Intracommunautaire** français.
2. **Base Adresse Nationale (BAN)** :
   - Normalisation d'adresses postales, code postal, commune, département et coordonnées GPS (WGS84).
3. **Météo Ouverte (Open-Meteo & Météo-France Open Data)** :
   - Conditions en direct et prévisions par ville ou coordonnées.

> [!NOTE]
> **Performance & Souveraineté :**
> - **Coût** : 0 € (Open Data officiel sous licence ouverte Etalab).
> - **Cache disque local** : Expiration automatique à 24h (`/tmp/arcia_public_apis_cache`). Les requêtes récurrentes répondent en moins de 50 ms sans solliciter le réseau.
> - **Confidentialité** : Aucune donnée privée ou secrète ne doit être envoyée en paramètre d'URL. Les flux sortants sont assainis par Presidio DLP.

---

## 2. Quand Déclencher cette Skill ? (Règles pour l'Agent)

L'agent doit exécuter le helper `public_apis.py` dès que l'utilisateur pose une question relative à :
- **Un numéro SIRET ou SIREN** : *"Vérifie le SIRET 13002526500013"*, *"Qui dirige l'entité au SIREN 130025265 ?"*.
- **Le numéro de TVA d'une entreprise** : *"Quel est le numéro de TVA de la société X ?"*.
- **La vérification d'une société française** : *"Donne-moi les infos officielles sur l'entreprise X"*, *"Est-ce que cette société est toujours active ?"*.
- **Une adresse ou un code postal** : *"Valide l'adresse 20 avenue de Ségur à Paris"*, *"Quelles sont les coordonnées GPS de cette adresse ?"*.
- **La météo locale** : *"Quel temps fait-il à Lyon aujourd'hui ?"*.

---

## 3. Commandes d'Exécution Autonome

L'agent exécute le script en ligne de commande via l'interpréteur Python :

```bash
# Chemin standard dans le pod Hermes Agent :
PYTHON_SCRIPT="/opt/data/skills/public-apis/scripts/public_apis.py"

# En environnement local de développement :
# python skills/public-apis/scripts/public_apis.py ...
```

### A. Recherche & Vérification d'Entreprise
```bash
python3 $PYTHON_SCRIPT company "<nom_ou_siren_ou_siret>"
```
*Exemple :* `python3 $PYTHON_SCRIPT company "DINUM"` ou `python3 $PYTHON_SCRIPT company "130025265"`

### B. Validation & Géocodage d'Adresse (BAN)
```bash
python $PYTHON_SCRIPT address "<adresse_complete>"
```
*Exemple :* `python $PYTHON_SCRIPT address "20 avenue de segur paris"`

### C. Météo Ouverte
```bash
python $PYTHON_SCRIPT meteo "<ville_ou_coordonnees>"
```
*Exemple :* `python $PYTHON_SCRIPT meteo "Paris"`

### D. Consultation du Catalogue des APIs
```bash
python $PYTHON_SCRIPT catalog
```

---

## 4. Protocole de Réponse de l'Agent

1. **Exécution transparente** : L'agent lance le helper avec la commande adéquate.
2. **Restitution directe** : L'agent intègre directement la fiche Markdown générée dans sa réponse conversationnelle à l'utilisateur, sans reformuler inutilement ni tronquer les numéros légaux (SIREN, SIRET, TVA).
3. **Cas d'erreur** : Si l'entreprise ou l'adresse n'est pas trouvée, proposer à l'utilisateur d'affiner l'orthographe ou de fournir le numéro SIREN à 9 chiffres.

---

## 5. Gouvernance, Filtrage Presidio DLP & Réseau (NetworkPolicy)

- **Protection DLP Presidio** : Aucun secret d'entreprise, mot de passe ou PII confidentielle ne doit être envoyé en paramètre d'URL vers une API externe. Le filtre Presidio DLP valide les requêtes sortantes.
- **Hermétisme Réseau & NetworkPolicy** : L'accès aux domaines publics homologués (`*.api.gouv.fr`, `api.open-meteo.com`, `apicarto.ign.fr`) est strictement délimité au niveau du cluster Kubernetes par `NetworkPolicy` d'egress pour interdire tout flux non maîtrisé.
