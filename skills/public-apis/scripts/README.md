<p align="left">
  <a href="../../../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.5.2-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <a href="../README.md"><img src="https://img.shields.io/badge/🏛️_Public--APIs-Compétence_Souveraine-0C2762?style=flat-square" alt="Public-APIs"></a>
  <img src="https://img.shields.io/badge/Runtime-Python_Stdlib_Only-6BE7DD?style=flat-square&logoColor=050712" alt="Python Stdlib">
</p>

# 🐍 Scripts utilitaires open data et public-APIs — ArcIA

> **[🏠 Accueil ArcIA](../../../README.md)** › **[🧠 Compétences](../../README.md)** › **[🏛️ Public-APIs](../README.md)** › **Scripts (`scripts/`)**

Ce dossier contient le moteur d'interrogation autonome associé à la compétence souveraine **[Public-APIs](../README.md)**.

---

## ⚡ Utilisation directe (`public_apis.py`)

Le script **[public_apis.py](public_apis.py)** fonctionne exclusivement avec la bibliothèque standard Python (`urllib.request`, `json`, `hashlib`) et met en cache les réponses pendant 24 heures :

```bash
# 1. Recherche d'entreprise (SIREN, SIRET ou Raison Sociale + calcul TVA intracommunautaire) :
python skills/public-apis/scripts/public_apis.py company "Exemple Entreprise"

# 2. Géocodage et normalisation d'adresse (Base Adresse Nationale - BAN) :
python skills/public-apis/scripts/public_apis.py address "20 avenue de segur paris"

# 3. Météo souveraine (Open-Meteo) :
python skills/public-apis/scripts/public_apis.py meteo "Paris"

# 4. Affichage du catalogue d'APIs certifiées :
python skills/public-apis/scripts/public_apis.py catalog
```

👉 Pour les règles d'invocation par Hermes Agent, consultez **[SKILL.md](../SKILL.md)**.
