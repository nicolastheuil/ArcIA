#!/usr/bin/env python3
"""
ArcIA — Public APIs Helper & Sovereign Open Data Gateway
=========================================================
Ce script autonome (Python 3 standard library uniquement, 0 dépendance pip)
permet aux agents Hermes et aux utilisateurs d'interroger instantanément et
gratuitement les APIs publiques souveraines d'entreprise de l'État français
(SIRET/SIREN, Base Adresse Nationale, Météo Open Data, Cadastre IGN) avec mise
en cache locale sur disque (TTL 24h) et calcul automatique de la TVA intracommunautaire.

Usage :
    python public_apis.py company "entreprise"
    python public_apis.py company "789315306"
    python public_apis.py address "696 rue yves kermen boulogne"
    python public_apis.py meteo "Paris"
    python public_apis.py catalog
"""

import os
import sys
import json
import time
import hashlib
import argparse
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, Any, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

USER_AGENT = "ArcIA-Sovereign-Agent/0.2 (Sovereign Platform)"
CACHE_DIR = os.path.join(os.getenv("TEMP", os.getenv("TMPDIR", "/tmp")), "arcia_public_apis_cache")
CACHE_TTL = 86400  # 24 heures

# -----------------------------------------------------------------------------
# Gestion du Cache Disque Local
# -----------------------------------------------------------------------------

def _get_cache_path(key: str) -> str:
    if not os.path.isdir(CACHE_DIR):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
        except Exception:
            pass
    hashed = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{hashed}.json")

def read_cache(key: str, max_age: int = CACHE_TTL) -> Optional[Dict[str, Any]]:
    path = _get_cache_path(key)
    if not os.path.isfile(path):
        return None
    try:
        mtime = os.path.getmtime(path)
        if time.time() - mtime > max_age:
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def write_cache(key: str, data: Dict[str, Any]) -> None:
    path = _get_cache_path(key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass

# -----------------------------------------------------------------------------
# Requête HTTP Sécurisée avec Timeout
# -----------------------------------------------------------------------------

def fetch_json(url: str, use_cache: bool = True, timeout: int = 10) -> Dict[str, Any]:
    if use_cache:
        cached = read_cache(url)
        if cached is not None:
            return cached

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"Erreur HTTP {response.status} sur {url}")
            raw = response.read().decode("utf-8")
            data = json.loads(raw)
            if use_cache:
                write_cache(url, data)
            return data
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Erreur HTTP {e.code} : {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Erreur de connexion réseau : {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Erreur lors de l'appel API : {e}")

# -----------------------------------------------------------------------------
# Calcul Métier : Numéro de TVA Intracommunautaire Français
# -----------------------------------------------------------------------------

def compute_french_tva(siren: str) -> str:
    """Calcule la clé de TVA intracommunautaire pour un numéro SIREN français à 9 chiffres."""
    clean_siren = "".join(c for c in siren if c.isdigit())
    if len(clean_siren) != 9:
        return "N/A (SIREN non valide à 9 chiffres)"
    siren_int = int(clean_siren)
    key = (12 + 3 * (siren_int % 97)) % 97
    return f"FR{key:02d}{clean_siren}"

# -----------------------------------------------------------------------------
# 1. API Recherche d'Entreprises (INSEE / SIRENE / RNE)
# -----------------------------------------------------------------------------

def lookup_company(query: str, use_cache: bool = True) -> Dict[str, Any]:
    encoded = urllib.parse.quote(query.strip())
    url = f"https://recherche-entreprises.api.gouv.fr/search?q={encoded}&limite=1"
    data = fetch_json(url, use_cache=use_cache)
    results = data.get("results", [])
    if not results:
        return {"error": f"Aucune entreprise trouvée pour le terme : '{query}'"}
    return results[0]

def format_company_markdown(company: Dict[str, Any]) -> str:
    if "error" in company:
        return f"❌ {company['error']}"

    nom = company.get("nom_complet", "Inconnu")
    siren = company.get("siren", "Inconnu")
    siege = company.get("siege", {})
    siret_siege = siege.get("siret", "Inconnu")
    adresse = siege.get("adresse", "Non renseignée")
    activite = company.get("activite_principale", "Non renseignée")
    date_crea = company.get("date_creation", "Inconnue")
    etat = company.get("etat_administratif", "Inconnu")
    etat_label = "🟢 Actif (En activité)" if etat == "A" else ("🔴 Cessé / Radié" if etat == "C" else etat)

    # Calcul TVA
    tva = compute_french_tva(siren) if siren != "Inconnu" else "N/A"

    # Dirigeants
    dirigeants_list = []
    for d in company.get("dirigeants", []):
        qualite = d.get("qualite", "Dirigeant")
        if d.get("type_dirigeant") == "personne physique":
            dirigeants_list.append(f"{d.get('prenoms', '')} {d.get('nom', '')} ({qualite})".strip())
        else:
            dirigeants_list.append(f"{d.get('denomination', 'Société')} ({qualite})".strip())
    dirigeants_str = ", ".join(dirigeants_list[:3]) if dirigeants_list else "Non renseignés"

    md = [
        f"### 🏢 Fiche Entreprise Officielle : **{nom}**",
        "",
        f"- **SIREN** : `{siren}`",
        f"- **SIRET (Siège)** : `{siret_siege}`",
        f"- **TVA Intracommunautaire** : `{tva}`",
        f"- **État Administratif** : {etat_label}",
        f"- **Code NAF / Activité** : `{activite}`",
        f"- **Date de création** : {date_crea}",
        f"- **Adresse du siège** : {adresse}",
        f"- **Dirigeants principaux** : {dirigeants_str}",
        "",
        "> _Source : Répertoire National des Entreprises (RNE) & INSEE via recherche-entreprises.api.gouv.fr (100% Open Data officiel)_"
    ]
    return "\n".join(md)

# -----------------------------------------------------------------------------
# 2. API Base Adresse Nationale (BAN)
# -----------------------------------------------------------------------------

def lookup_address(query: str, use_cache: bool = True) -> Dict[str, Any]:
    encoded = urllib.parse.quote(query.strip())
    url = f"https://api-adresse.data.gouv.fr/search/?q={encoded}&limit=1"
    data = fetch_json(url, use_cache=use_cache)
    features = data.get("features", [])
    if not features:
        return {"error": f"Aucune adresse trouvée pour le terme : '{query}'"}
    return features[0]

def format_address_markdown(feat: Dict[str, Any]) -> str:
    if "error" in feat:
        return f"❌ {feat['error']}"

    props = feat.get("properties", {})
    geometry = feat.get("geometry", {})
    coords = geometry.get("coordinates", [None, None])

    label = props.get("label", "Inconnu")
    cp = props.get("postcode", "Inconnu")
    ville = props.get("city", "Inconnu")
    dep = props.get("context", "Inconnu")
    score = props.get("score", 0)
    score_pct = f"{int(score * 100)}%"

    md = [
        f"### 📍 Adresse Normalisée : **{label}**",
        "",
        f"- **Code Postal & Ville** : {cp} {ville}",
        f"- **Département / Région** : {dep}",
        f"- **Coordonnées GPS (WGS84)** : Latitude `{coords[1]}`, Longitude `{coords[0]}`",
        f"- **Indice de confiance (Score)** : {score_pct}",
        "",
        "> _Source : Base Adresse Nationale (BAN) via api-adresse.data.gouv.fr (Certifiée conforme)_"
    ]
    return "\n".join(md)

# -----------------------------------------------------------------------------
# 3. API Météo Ouverte (Open-Meteo & Météo-France)
# -----------------------------------------------------------------------------

WMO_WEATHER_CODES = {
    0: "☀️ Ciel dégagé / Ensoleillé",
    1: "🌤️ Principalement dégagé",
    2: "⛅ Partiellement nuageux",
    3: "☁️ Couvert",
    45: "🌫️ Brouillard",
    48: "🌫️ Brouillard givrant",
    51: "🌦️ Bruine légère",
    61: "🌧️ Pluie légère",
    63: "🌧️ Pluie modérée",
    65: "🌧️ Pluie forte",
    71: "🌨️ Chutes de neige légères",
    80: "🌦️ Averses de pluie",
    95: "⛈️ Orage modéré"
}

def lookup_weather(query: str, use_cache: bool = True) -> Dict[str, Any]:
    # Si la requête n'est pas déjà un couple lat,lon, on géocode via l'API adresse
    lat, lon, label = None, None, query
    if "," in query:
        parts = query.split(",")
        try:
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
        except ValueError:
            pass

    if lat is None or lon is None:
        addr = lookup_address(query, use_cache=use_cache)
        if "error" in addr:
            return {"error": f"Impossible de localiser la ville : '{query}'"}
        coords = addr.get("geometry", {}).get("coordinates", [None, None])
        lon, lat = coords[0], coords[1]
        label = addr.get("properties", {}).get("label", query)

    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    data = fetch_json(url, use_cache=use_cache)
    data["_target_label"] = label
    return data

def format_weather_markdown(weather: Dict[str, Any]) -> str:
    if "error" in weather:
        return f"❌ {weather['error']}"

    target = weather.get("_target_label", "Localisation demandée")
    curr = weather.get("current_weather", {})
    temp = curr.get("temperature", "N/A")
    wind = curr.get("windspeed", "N/A")
    code = curr.get("weathercode", -1)
    desc = WMO_WEATHER_CODES.get(code, f"Conditions normales (code {code})")
    time_obs = curr.get("time", "En direct")

    md = [
        f"### ⛅ Météo pour **{target}**",
        "",
        f"- **Conditions actuelles** : {desc}",
        f"- **Température** : **{temp} °C**",
        f"- **Vitesse du vent** : {wind} km/h",
        f"- **Horodatage d'observation** : `{time_obs}`",
        "",
        "> _Source : Open-Meteo & Données Ouvertes Météo-France (Sans frais)_"
    ]
    return "\n".join(md)

# -----------------------------------------------------------------------------
# CLI Entrypoint
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ArcIA Public APIs Gateway")
    parser.add_argument("command", choices=["company", "address", "meteo", "catalog"],
                        help="Commande : company (SIRET/SIREN), address (BAN), meteo (Météo-France), catalog")
    parser.add_argument("query", nargs="?", default="", help="Terme de recherche, identifiant ou adresse")
    parser.add_argument("--json", action="store_true", help="Retourne l'objet JSON brut au lieu du markdown")
    parser.add_argument("--no-cache", action="store_true", help="Ignore le cache local et force la requête en direct")
    args = parser.parse_args()

    use_cache = not args.no_cache

    if args.command == "catalog":
        script_dir = os.path.dirname(os.path.abspath(__file__))
        catalog_path = os.path.join(os.path.dirname(script_dir), "catalog.json")
        if os.path.isfile(catalog_path):
            with open(catalog_path, "r", encoding="utf-8") as f:
                cat = json.load(f)
            if args.json:
                print(json.dumps(cat, indent=2, ensure_ascii=False))
            else:
                print("### 📚 Catalogue des APIs Publiques Souveraines ArcIA\n")
                for api in cat.get("apis", []):
                    print(f"- **{api['name']}** ({api['domain']}) : {api['description']}")
                    print(f"  * _URL_ : `{api['base_url']}` | _Tarif_ : {api['pricing']}")
        else:
            print("Catalogue introuvable.")
        return

    if not args.query:
        print("Erreur : Veuillez spécifier un terme de recherche ou un identifiant.", file=sys.stderr)
        sys.exit(1)

    try:
        if args.command == "company":
            res = lookup_company(args.query, use_cache=use_cache)
            if args.json:
                print(json.dumps(res, indent=2, ensure_ascii=False))
            else:
                print(format_company_markdown(res))

        elif args.command == "address":
            res = lookup_address(args.query, use_cache=use_cache)
            if args.json:
                print(json.dumps(res, indent=2, ensure_ascii=False))
            else:
                print(format_address_markdown(res))

        elif args.command == "meteo":
            res = lookup_weather(args.query, use_cache=use_cache)
            if args.json:
                print(json.dumps(res, indent=2, ensure_ascii=False))
            else:
                print(format_weather_markdown(res))

    except Exception as e:
        print(f"❌ Erreur lors de l'exécution de la requête : {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
