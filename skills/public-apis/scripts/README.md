# Scripts Utilitaires Open Data & Public-APIs — ArcIA

Ce dossier contient les scripts autonomes associés à la compétence souveraine [Public-APIs](../README.md).

## Contenu

* **[public_apis.py](public_apis.py)** : Script autonome sans dépendance externe (`urllib` Python standard uniquement) permettant aux agents et développeurs d'interroger directement les APIs ouvertes officielles françaises avec mise en cache disque automatique (TTL 24h) :
  * Recherche d'entreprises (API Recherche d'Entreprises / INSEE SIREN/SIRET et calcul de TVA intracommunautaire) :
    ```bash
    python public_apis.py company "Exemple Entreprise"
    ```
  * Géocodage et normalisation d'adresses (Base Adresse Nationale - BAN) :
    ```bash
    python public_apis.py address "20 avenue de segur paris"
    ```
  * Données météo souveraines (Open-Meteo) :
    ```bash
    python public_apis.py meteo "Paris"
    ```
  * Consultation du catalogue d'APIs certifiées :
    ```bash
    python public_apis.py catalog
    ```

Pour plus de détails, consulter la documentation de la compétence : [SKILL.md](../SKILL.md).
