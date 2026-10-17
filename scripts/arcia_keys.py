#!/usr/bin/env python3
"""
ArcIA v0.4 — Gestionnaire des Clés Virtuelles et Budgets LiteLLM (PAT)
Permet d'émettre, renouveler, lister et révoquer les clés d'API nominatives
pour les Utilisateurs Standards et les Power Users.
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.error

DEFAULT_LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
DEFAULT_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")

ALL_CANONICAL_MODELS = ["simple/free", "simple/auto", "agentic/free", "agentic/auto", "agentic/expert"]

AUTONOMY_LEVELS = {
    "standard": {
        "models": ALL_CANONICAL_MODELS,
        "max_budget": 50.0,
        "description": "Utilisateur Standard (Open-WebUI Simple + Agentic)"
    },
    "poweruser": {
        "models": ALL_CANONICAL_MODELS,
        "max_budget": 200.0,
        "description": "Power User (Open-WebUI Simple + Agentic + Pod Hermes dédié)"
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


def create_key(user_email: str, autonomy_level: str = "poweruser", team: str = "engineering",
               duration: str = "90d", max_budget: float = None,
               base_url: str = DEFAULT_LITELLM_URL,
               master_key: str = DEFAULT_MASTER_KEY):
    """Génère une clé virtuelle nominative LiteLLM avec budget et modèles contraints."""
    level_info = AUTONOMY_LEVELS.get(autonomy_level, AUTONOMY_LEVELS["poweruser"])
    effective_budget = float(max_budget) if max_budget is not None else level_info["max_budget"]
    payload = {
        "user_id": user_email,
        "team_id": team,
        "models": level_info["models"],
        "max_budget": effective_budget,
        "budget_duration": "30d",
        "duration": duration,
        "metadata": {
            "profile": autonomy_level,
            "created_by": "arcia-keys-cli",
            "user_email": user_email
        }
    }
    print(f"[*] Génération de la clé virtuelle pour {user_email} (Profil: {autonomy_level}, Budget: {effective_budget} $ / 30j)...")
    res = _make_request(f"{base_url}/key/generate", master_key, method="POST", data=payload)
    key = res.get("key", "")
    print(f"\n[+] Clé nominative générée avec succès :")
    print(f"    Utilisateur : {user_email}")
    print(f"    Profil      : {autonomy_level} ({level_info['description']})")
    print(f"    Modèles     : {', '.join(level_info['models'])}")
    print(f"    Budget Max  : {effective_budget} $ / 30 jours (LiteLLM USD)")
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


def _add_create_arguments(subparser):
    subparser.add_argument("email", nargs="?", default=None, help="Adresse email professionnelle (ex: prenom.nom@example.org)")
    subparser.add_argument("--user", dest="user_opt", default=None, help="Adresse email professionnelle")
    subparser.add_argument("--profile", "--tier", "--level", dest="level", choices=["standard", "poweruser"], default="poweruser", help="Profil utilisateur (standard ou poweruser)")
    subparser.add_argument("--budget", type=float, default=None, help="Plafond budgétaire mensuel USD")
    subparser.add_argument("--team", default="engineering", help="Nom de l'équipe (ex: engineering, support, marketing)")
    subparser.add_argument("--duration", default="90d", help="Durée de validité de la clé (ex: 30d, 90d)")


def main():
    parser = argparse.ArgumentParser(description="Gestionnaire des Clés Virtuelles ArcIA v0.4")
    parser.add_argument("--url", default=DEFAULT_LITELLM_URL, help="URL de la passerelle LiteLLM")
    parser.add_argument("--master-key", default=DEFAULT_MASTER_KEY, help="Master Key LiteLLM")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # create & create-user
    p_create = subparsers.add_parser("create", help="Créer une clé virtuelle nominative pour un collaborateur")
    _add_create_arguments(p_create)

    p_create_user = subparsers.add_parser("create-user", help="Alias de 'create'")
    _add_create_arguments(p_create_user)

    # list
    subparsers.add_parser("list", help="Lister les clés virtuelles actives")

    # revoke
    p_revoke = subparsers.add_parser("revoke", help="Révoquer une clé d'API")
    p_revoke.add_argument("key", nargs="?", default=None, help="Clé ou alias de clé à révoquer")
    p_revoke.add_argument("--key", dest="key_opt", default=None, help="Clé ou alias de clé à révoquer")

    args = parser.parse_args()

    if args.command in ("create", "create-user"):
        target_email = args.user_opt or args.email
        if not target_email:
            parser.error("L'adresse email de l'utilisateur est requise (via --user <email> ou argument positionnel).")
        create_key(target_email, args.level, team=args.team, duration=args.duration,
                   max_budget=args.budget, base_url=args.url, master_key=args.master_key)
    elif args.command == "list":
        list_keys(base_url=args.url, master_key=args.master_key)
    elif args.command == "revoke":
        target_key = args.key_opt or args.key
        if not target_key:
            parser.error("La clé à révoquer est requise (via --key <cle> ou argument positionnel).")
        delete_key(target_key, base_url=args.url, master_key=args.master_key)


if __name__ == "__main__":
    main()

