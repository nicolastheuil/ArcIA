#!/usr/bin/env python3
"""
ArcIA v0.3 — Gestionnaire des Clés Virtuelles et Budgets LiteLLM (PAT Power Users)
Permet d'émettre, renouveler, lister et révoquer les clés d'API nominatives
pour les collaborateurs et power users (N1, N2, N3).
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.error

DEFAULT_LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
DEFAULT_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")

AUTONOMY_LEVELS = {
    "N1": {
        "models": ["arcia/standard"],
        "max_budget": 10.0,
        "description": "Collaborateur standard (modèle standard)"
    },
    "N2": {
        "models": ["arcia/standard", "arcia/expert"],
        "max_budget": 50.0,
        "description": "Expert métier (standard + expert)"
    },
    "N3": {
        "models": ["arcia/standard", "arcia/expert", "arcia/reasoning"],
        "max_budget": 200.0,
        "description": "Power user / Ingénieur IA (tous modèles, accès /v1)"
    }
}


def _make_request(url: str, master_key: str, method: str = "GET", data: dict = None) -> dict:
    if not master_key:
        print("[ERREUR] Master Key LiteLLM non fournie. Définissez la variable LITELLM_MASTER_KEY ou le paramètre --master-key.", file=sys.stderr)
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {master_key}",
        "Content-Type": "application/json"
    }
    payload = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8") if e.fp else str(e)
        print(f"[ERREUR HTTP {e.code}] {err_msg}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERREUR CONNEXION] Impossible de contacter LiteLLM sur {url}: {e}", file=sys.stderr)
        sys.exit(1)


def create_key(user_email: str, autonomy_level: str, team: str = "engineering",
               duration: str = "90d", base_url: str = DEFAULT_LITELLM_URL,
               master_key: str = DEFAULT_MASTER_KEY):
    """Génère une clé virtuelle nominative LiteLLM avec budget et modèles contraints."""
    level_info = AUTONOMY_LEVELS.get(autonomy_level, AUTONOMY_LEVELS["N3"])
    payload = {
        "user_id": user_email,
        "team_id": team,
        "models": level_info["models"],
        "max_budget": level_info["max_budget"],
        "budget_duration": "30d",
        "duration": duration,
        "metadata": {
            "autonomy_level": autonomy_level,
            "created_by": "arcia-keys-cli",
            "user_email": user_email
        }
    }
    print(f"[*] Génération de la clé virtuelle pour {user_email} (Niveau: {autonomy_level}, Budget: {level_info['max_budget']} $ / 30j)...")
    res = _make_request(f"{base_url}/key/generate", master_key, method="POST", data=payload)
    key = res.get("key", "")
    print(f"\n[+] Clé nominative générée avec succès :")
    print(f"    Utilisateur : {user_email}")
    print(f"    Niveau      : {autonomy_level} ({level_info['description']})")
    print(f"    Modèles     : {', '.join(level_info['models'])}")
    print(f"    Budget Max  : {level_info['max_budget']} $ / 30 jours (LiteLLM USD)")
    print(f"    Clé d'API   : {key}\n")
    print(f"Conservez cette clé précieusement, elle ne sera plus affichée.")
    return key


def list_keys(base_url: str = DEFAULT_LITELLM_URL, master_key: str = DEFAULT_MASTER_KEY):
    """Liste les clés virtuelles actives sur la passerelle."""
    print(f"[*] Récupération des clés actives sur {base_url}...")
    res = _make_request(f"{base_url}/key/list?return_full_object=true", master_key, method="GET")
    keys = res.get("keys", [])
    print(f"[+] {len(keys)} clés enregistrées :")
    for k in keys:
        if isinstance(k, dict):
            alias = k.get("key_alias") or k.get("key_name") or k.get("token") or "N/A"
            user = k.get("user_id", "N/A")
            spend = k.get("spend", 0)
            budget = k.get("max_budget", "illimité")
            duration = k.get("budget_duration", "30d")
            print(f"  - Key: {alias} | User: {user} | Spend: {spend} $ / {budget} $ ({duration})")
        else:
            print(f"  - Key: {k}")
    return keys


def delete_key(key_alias: str, base_url: str = DEFAULT_LITELLM_URL, master_key: str = DEFAULT_MASTER_KEY):
    """Révoque une clé d'API nominative."""
    print(f"[*] Révocation de la clé '{key_alias}'...")
    payload = {"keys": [key_alias], "key_aliases": [key_alias]}
    res = _make_request(f"{base_url}/key/delete", master_key, method="POST", data=payload)
    print(f"[+] Clé révoquée avec succès : {res}")


def main():
    parser = argparse.ArgumentParser(description="Gestionnaire des Clés Virtuelles ArcIA v0.3")
    parser.add_argument("--url", default=DEFAULT_LITELLM_URL, help="URL de la passerelle LiteLLM")
    parser.add_argument("--master-key", default=DEFAULT_MASTER_KEY, help="Master Key LiteLLM")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = subparsers.add_parser("create-user", help="Créer une clé virtuelle nominative pour un collaborateur")
    p_create.add_argument("email", help="Adresse email professionnelle (ex: prenom.nom@entreprise.com)")
    p_create.add_argument("--level", choices=["N1", "N2", "N3"], default="N3", help="Niveau d'autonomie (N1, N2, N3)")
    p_create.add_argument("--team", default="engineering", help="Nom de l'équipe (ex: engineering, support, marketing)")
    p_create.add_argument("--duration", default="90d", help="Durée de validité de la clé (ex: 30d, 90d)")

    # list
    subparsers.add_parser("list", help="Lister les clés virtuelles actives")

    # revoke
    p_revoke = subparsers.add_parser("revoke", help="Révoquer une clé d'API")
    p_revoke.add_argument("key", help="Clé ou alias de clé à révoquer")

    args = parser.parse_args()

    if args.command == "create-user":
        create_key(args.email, args.level, team=args.team, duration=args.duration,
                   base_url=args.url, master_key=args.master_key)
    elif args.command == "list":
        list_keys(base_url=args.url, master_key=args.master_key)
    elif args.command == "revoke":
        delete_key(args.key, base_url=args.url, master_key=args.master_key)


if __name__ == "__main__":
    main()
