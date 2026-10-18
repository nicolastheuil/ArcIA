#!/usr/bin/env python3
"""
ArcIA Governance & Tokenmaxing Plugin (v0.4) for Hermes Agent
=============================================================
Assure deux fonctions critiques en amont dans le moteur Hermes :
1. Barrière DLP Presidio Fail-Closed (avant persistance SQLite et envoi LiteLLM).
2. Économie de tokens (Tokenmaxing v0.4) :
   - CCR (Compress-Cache-Retrieve) réversible inspiré de Headroom : sauvegarde
     systématique de l'original par hash SHA-256 dans le cache privé borné et
     préservation stricte de la structure JSON/AST.
   - RTK (Rust Token Killer) pour compresser les sorties shell bruyantes (git,
     kubectl, pytest, docker, npm, cargo).
   - Orientation Ponytail (échelle YAGNI) et Graphify (AST local 0 token).

Usage CLI (pour récupération CCR par l'agent) :
    python3 plugin.py retrieve <ccr_hash> [--offset 0] [--limit 100] [--key <json_key>]
"""

import os
import sys
import json
import time
import shutil
import hashlib
import argparse
import subprocess
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

MAX_JSON_BYTES = int(os.environ.get("ARCIA_MAX_JSON_BYTES", "8192"))
MAX_SHELL_LINES = int(os.environ.get("ARCIA_MAX_SHELL_LINES", "80"))
MAX_CCR_FILES = int(os.environ.get("ARCIA_MAX_CCR_FILES", "200"))

PRESIDIO_DLP_URL = os.environ.get(
    "PRESIDIO_DLP_URL",
    "http://presidio-dlp.arcia.svc:8080/sanitize"
)
PRESIDIO_FAIL_CLOSED = os.environ.get("PRESIDIO_FAIL_CLOSED", "true").lower() in ("true", "1", "yes")


def get_ccr_cache_dir() -> str:
    """Retourne le répertoire de cache CCR privé du pod Hermes."""
    custom = os.environ.get("ARCIA_CCR_CACHE_DIR")
    if custom:
        return custom
    hermes_home = os.environ.get("HERMES_HOME", "/data/hermes")
    if os.path.isdir(hermes_home) and os.access(hermes_home, os.W_OK):
        return os.path.join(hermes_home, ".ccr_cache")
    return os.path.join(os.environ.get("TEMP", "/tmp"), "arcia_ccr_cache")


# -----------------------------------------------------------------------------
# 1. Cache CCR (Compress-Cache-Retrieve) Réversible et Borné
# -----------------------------------------------------------------------------

def ccr_store(raw_content: str, kind: str = "text", metadata: Optional[Dict[str, Any]] = None) -> str:
    """
    Sauvegarde le contenu original dans le cache CCR par hash SHA-256 (12 caractères)
    et applique une rotation LRU bornée à MAX_CCR_FILES entrées.
    """
    content_bytes = raw_content.encode("utf-8", errors="replace")
    ccr_hash = hashlib.sha256(content_bytes).hexdigest()[:12]
    cache_dir = get_ccr_cache_dir()
    os.makedirs(cache_dir, exist_ok=True)

    entry_path = os.path.join(cache_dir, f"{ccr_hash}.json")
    payload = {
        "hash": ccr_hash,
        "kind": kind,
        "created_at": time.time(),
        "size_bytes": len(content_bytes),
        "metadata": metadata or {},
        "content": raw_content,
    }
    with open(entry_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    # Rotation LRU si le nombre de fichiers dépasse MAX_CCR_FILES
    try:
        files = [
            os.path.join(cache_dir, fn)
            for fn in os.listdir(cache_dir)
            if fn.endswith(".json")
        ]
        if len(files) > MAX_CCR_FILES:
            files.sort(key=lambda p: os.path.getmtime(p))
            for old_file in files[: len(files) - MAX_CCR_FILES]:
                try:
                    os.remove(old_file)
                except OSError:
                    pass
    except OSError:
        pass

    return ccr_hash


def ccr_retrieve(
    ccr_hash: str,
    offset: int = 0,
    limit: int = 100,
    json_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Récupère le contenu original exact depuis le cache CCR à partir de son hash.
    Permet la pagination par lignes ou l'extraction d'une clé JSON spécifique.
    """
    clean_hash = "".join(c for c in ccr_hash if c.isalnum())[:12]
    cache_dir = get_ccr_cache_dir()
    entry_path = os.path.join(cache_dir, f"{clean_hash}.json")
    if not os.path.isfile(entry_path):
        return {
            "found": False,
            "hash": clean_hash,
            "error": f"Entrée CCR '{clean_hash}' introuvable ou expirée dans {cache_dir}."
        }

    with open(entry_path, "r", encoding="utf-8") as f:
        entry = json.load(f)

    raw_content = entry.get("content", "")
    if json_key:
        try:
            parsed = json.loads(raw_content)
            if isinstance(parsed, dict) and json_key in parsed:
                return {
                    "found": True,
                    "hash": clean_hash,
                    "key": json_key,
                    "value": parsed[json_key]
                }
            return {
                "found": False,
                "hash": clean_hash,
                "error": f"Clé '{json_key}' absente de l'objet JSON."
            }
        except Exception as e:
            return {"found": False, "hash": clean_hash, "error": f"Contenu non-JSON: {e}"}

    lines = raw_content.splitlines()
    sliced = lines[offset: offset + limit] if limit > 0 else lines[offset:]
    return {
        "found": True,
        "hash": clean_hash,
        "kind": entry.get("kind", "text"),
        "total_lines": len(lines),
        "offset": offset,
        "returned_lines": len(sliced),
        "content": "\n".join(sliced),
    }


# -----------------------------------------------------------------------------
# 2. Compression RTK (Shell) & Headroom CCR (JSON / Logs)
# -----------------------------------------------------------------------------

def compress_shell_output(command: str, output: str) -> str:
    """
    Compresse les sorties de commandes shell bruyantes via RTK (si présent)
    ou par réduction structurelle avec sauvegarde CCR intégrale.
    """
    if not output:
        return output

    rtk_bin = shutil.which("rtk") or ("/usr/local/bin/rtk" if os.path.exists("/usr/local/bin/rtk") else None)
    if rtk_bin and os.access(rtk_bin, os.X_OK):
        try:
            proc = subprocess.run(
                [rtk_bin, "compress"],
                input=output.encode("utf-8"),
                capture_output=True,
                timeout=5
            )
            if proc.returncode == 0 and proc.stdout:
                compressed = proc.stdout.decode("utf-8", errors="replace")
                if len(compressed) < len(output):
                    ccr_hash = ccr_store(output, kind="shell", metadata={"command": command, "compressor": "rtk"})
                    return f"{compressed}\n[CCR_HASH: {ccr_hash} | retrieve: python3 /opt/hermes/plugins/plugin.py retrieve {ccr_hash}]"
        except Exception:
            pass

    lines = output.splitlines()
    if len(lines) > MAX_SHELL_LINES:
        ccr_hash = ccr_store(output, kind="shell", metadata={"command": command, "total_lines": len(lines)})
        head_count = int(MAX_SHELL_LINES * 0.65)
        tail_count = MAX_SHELL_LINES - head_count
        head = "\n".join(lines[:head_count])
        tail = "\n".join(lines[-tail_count:])
        omitted = len(lines) - head_count - tail_count
        return (
            f"{head}\n\n"
            f"... [Tokenmaxing CCR: {omitted} lignes compressées | Hash: {ccr_hash} | "
            f"Récupérer l'original: python3 /opt/hermes/plugins/plugin.py retrieve {ccr_hash} --offset {head_count} --limit 100] ...\n\n"
            f"{tail}"
        )

    return output


def compress_large_json(raw_text: str) -> str:
    """
    Compresse les payloads JSON dépassant MAX_JSON_BYTES tout en garantissant
    une sortie 100% JSON valide et la récupération exacte via le cache CCR.
    """
    if not raw_text or len(raw_text.encode("utf-8", errors="replace")) <= MAX_JSON_BYTES:
        return raw_text

    # Essayer headroom-ai si disponible et configuré
    try:
        import headroom  # type: ignore
        if hasattr(headroom, "compress"):
            ccr_hash = ccr_store(raw_text, kind="json")
            res = headroom.compress(raw_text)
            if isinstance(res, str) and len(res) < len(raw_text):
                return res
    except Exception:
        pass

    try:
        data = json.loads(raw_text)
    except Exception:
        # Si ce n'est pas du JSON valide, compresser comme texte long avec CCR
        return compress_shell_output("read_text", raw_text)

    ccr_hash = ccr_store(raw_text, kind="json")
    retrieve_hint = f"python3 /opt/hermes/plugins/plugin.py retrieve {ccr_hash}"

    if isinstance(data, list) and len(data) > 15:
        summary = {
            "_arcia_ccr": {
                "hash": ccr_hash,
                "status": "compressed_list",
                "total_items": len(data),
                "shown_items": 10,
                "retrieve_cmd": retrieve_hint,
            },
            "items_sample": data[:10],
        }
        return json.dumps(summary, indent=2, ensure_ascii=False)

    if isinstance(data, dict):
        compressed_dict: Dict[str, Any] = {
            "_arcia_ccr": {
                "hash": ccr_hash,
                "status": "compressed_object",
                "total_keys": len(data),
                "retrieve_cmd": f"{retrieve_hint} --key <nom_cle>",
            }
        }
        for k, v in data.items():
            serialized_v = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
            if isinstance(v, list) and len(serialized_v) > 1024:
                compressed_dict[k] = {
                    "_ccr_summary": f"list({len(v)} items)",
                    "sample": v[:3],
                    "retrieve_key_cmd": f"{retrieve_hint} --key {k}",
                }
            elif isinstance(v, dict) and len(serialized_v) > 1024:
                compressed_dict[k] = {
                    "_ccr_summary": f"dict({len(v)} keys)",
                    "keys": list(v.keys())[:15],
                    "retrieve_key_cmd": f"{retrieve_hint} --key {k}",
                }
            elif isinstance(v, str) and len(v) > 1024:
                compressed_dict[k] = v[:512] + f"... [CCR {ccr_hash}: --key {k}]"
            else:
                compressed_dict[k] = v
        return json.dumps(compressed_dict, indent=2, ensure_ascii=False)

    return raw_text


# -----------------------------------------------------------------------------
# 3. Barrière DLP Presidio en Amont (Fail-Closed & Pseudonymisation Réversible)
# -----------------------------------------------------------------------------

class ArcIAPresidioBlockedException(RuntimeError):
    """Exception levée en mode Fail-Closed lorsqu'un secret d'infrastructure est bloqué."""
    pass


class ArcIAPresidioUnavailableException(RuntimeError):
    """Exception levée en mode Fail-Closed lorsque Presidio DLP est inaccessible."""
    pass


def format_hermes_error(error_content: Any) -> str:
    """
    Formate les erreurs d'exécution, d'appels LLM ou d'outils pour les Power Users
    dans Hermes Studio et Hermes CLI, avec des alertes Markdown claires.
    """
    raw_str = str(error_content)
    lower = raw_str.lower()

    if "rejet-fail-closed" in lower or "rejet de secret brut" in lower or "fail_closed_secret_rejected" in lower or "blocage sécurité" in lower:
        return (
            "> [!CAUTION]\n"
            "> ### 🛡️ ArcIA Presidio DLP — Rejet Fail-Closed\n"
            "> Votre requête ou la sortie d'un outil a été bloquée par mesure de sécurité souveraine "
            "car elle contient des secrets d'infrastructure sensibles (clé privée SSH/PEM, kubeconfig ou jeton d'authentification).\n"
            "> L'exécution a été immédiatement interrompue pour protéger l'infrastructure."
        )

    if "service injoignable" in lower or "inaccessible" in lower or "unreachable" in lower:
        return (
            "> [!WARNING]\n"
            "> ### 🛡️ ArcIA Presidio DLP — Service Indisponible\n"
            "> Le service de confidentialité Presidio DLP est momentanément inaccessible (Fail-Closed).\n"
            "> L'exécution a été suspendue pour éviter toute fuite de données vers l'extérieur."
        )

    if any(k in lower for k in ["key limit exceeded", "daily limit", "spend_usd", "insufficient_quota"]):
        return (
            "> [!WARNING]\n"
            "> ### ⚠️ Quota d'inférence atteint\n"
            "> La limite d'utilisation quotidienne ou le solde de la clé d'API fournisseur a été atteint.\n"
            "> Veuillez contacter l'administrateur ArcIA ou vérifier le quota configuré."
        )

    if any(k in lower for k in ["zero data retention", "filter by data policy", "zdr"]):
        return (
            "> [!IMPORTANT]\n"
            "> ### 🔒 Politique de confidentialité (ZDR)\n"
            "> Aucun modèle public gratuit ne respecte le Zéro Rétention de Données (ZDR) imposé par ArcIA.\n"
            "> Veuillez basculer sur un profil d'inférence qualifié (ex: `agentic/auto` ou `agentic/expert`)."
        )

    return f"> [!WARNING]\n> ### ⚠️ Incident technique\n> {raw_str}"


PRESIDIO_DEANONYMIZE_URL = os.environ.get(
    "PRESIDIO_DEANONYMIZE_URL",
    PRESIDIO_DLP_URL.replace("/sanitize", "/deanonymize")
)


def sanitize_via_presidio(text: str, language: str = "fr", session_id: Optional[str] = None) -> str:
    """
    Appelle le microservice interne Presidio DLP pour assainir un texte
    avant persistance SQLite ou appel au modèle.
    En mode PRESIDIO_FAIL_CLOSED=true, lève une exception explicite si Presidio est injoignable
    ou rejette un dump de secret brut (HTTP 422).
    """
    if not text or not text.strip():
        return text

    payload = {"text": text, "language": language}
    if session_id:
        payload["session_id"] = session_id

    req_body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        PRESIDIO_DLP_URL,
        data=req_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return resp_data.get("sanitized_text", resp_data.get("text", text))
            if PRESIDIO_FAIL_CLOSED:
                raise ArcIAPresidioUnavailableException(f"Presidio DLP returned HTTP {resp.status} (Fail-Closed)")
    except urllib.error.HTTPError as http_err:
        err_msg = http_err.read().decode("utf-8", errors="replace")
        if http_err.code == 422:
            friendly_msg = (
                "🛡️ [ArcIA Presidio DLP - Rejet Fail-Closed] "
                "Votre message ou document a été bloqué par mesure de sécurité souveraine "
                "car il contient des secrets d'infrastructure sensibles (clé privée SSH/PEM, kubeconfig ou token). "
                f"Détail : {err_msg}"
            )
            raise ArcIAPresidioBlockedException(friendly_msg)
        if PRESIDIO_FAIL_CLOSED:
            friendly_msg = (
                f"🛡️ [ArcIA Presidio DLP - Erreur HTTP {http_err.code} Fail-Closed] "
                f"Erreur du service Presidio : {err_msg}"
            )
            raise ArcIAPresidioUnavailableException(friendly_msg)
    except Exception as exc:
        if isinstance(exc, (ArcIAPresidioBlockedException, ArcIAPresidioUnavailableException)):
            raise
        if PRESIDIO_FAIL_CLOSED:
            friendly_msg = (
                f"🛡️ [ArcIA Presidio DLP - Service Injoignable Fail-Closed] "
                f"Impossible de contacter Presidio DLP ({exc}). "
                "L'opération a été interrompue pour éviter toute fuite de données vers l'extérieur."
            )
            raise ArcIAPresidioUnavailableException(friendly_msg) from exc
    return text


def deanonymize_via_presidio(text: str, session_id: Optional[str] = None) -> str:
    """
    Ré-hydrate la réponse générée par le LLM en remplaçant les jetons [TYPE_01]
    par leurs valeurs originales depuis le Vault éphémère de session.
    """
    if not text or not text.strip():
        return text

    payload = {"text": text}
    if session_id:
        payload["session_id"] = session_id

    req_body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        PRESIDIO_DEANONYMIZE_URL,
        data=req_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return resp_data.get("text", text)
    except Exception:
        pass
    return text


# -----------------------------------------------------------------------------
# 4. Hooks Hermes Agent & CLI
# -----------------------------------------------------------------------------

def on_pre_llm_call(messages: List[Dict[str, Any]], session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Hook Hermes appelé avant l'envoi des messages au LLM (Barrière DLP amont)."""
    sanitized_messages = []
    for msg in messages:
        new_msg = dict(msg)
        content = new_msg.get("content")
        if isinstance(content, str) and content.strip():
            new_msg["content"] = sanitize_via_presidio(content, session_id=session_id)
        sanitized_messages.append(new_msg)
    return sanitized_messages


def on_post_llm_response(response_text: str, session_id: Optional[str] = None) -> str:
    """Hook Hermes appelé sur la réponse du LLM pour ré-hydrater les jetons réversibles."""
    return deanonymize_via_presidio(response_text, session_id=session_id)


def on_tool_result(tool_name: str, command: str, result: str) -> str:
    """Hook Hermes appelé sur les résultats d'outils (Tokenmaxing RTK + CCR)."""
    if not result:
        return result
    if tool_name in ("terminal", "bash", "exec", "shell"):
        return compress_shell_output(command, result)
    if tool_name in ("read_file", "fetch_url", "http", "mcp_call"):
        return compress_large_json(result)
    return result


def get_system_governance_prompt() -> str:
    """Orientation injectée dans la session Hermes pour activer Ponytail, Graphify et CCR."""
    return (
        "[ArcIA Tokenmaxing v0.4 Actif] "
        "1) Applique l'échelle de sobriété Ponytail (YAGNI, réutilisation de l'existant). "
        "2) Pour cartographier un dépôt de code sans consommer de tokens, utilise Graphify (`python3 /opt/arcia/scripts/arcia_graphify.py`). "
        "3) Lorsqu'une sortie d'outil affiche `[CCR_HASH: <hash>]` ou `_arcia_ccr`, récupère les détails exacts à la demande via `python3 /opt/hermes/plugins/plugin.py retrieve <hash>`."
    )


def main():
    parser = argparse.ArgumentParser(description="ArcIA Governance & Tokenmaxing CCR CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ret = sub.add_parser("retrieve", help="Récupérer une entrée originale depuis le cache CCR")
    p_ret.add_argument("hash", help="Hash CCR à 12 caractères")
    p_ret.add_argument("--offset", type=int, default=0, help="Ligne de départ (défaut: 0)")
    p_ret.add_argument("--limit", type=int, default=100, help="Nombre maximum de lignes (défaut: 100)")
    p_ret.add_argument("--key", type=str, default=None, help="Clé JSON spécifique à extraire")

    p_dean = sub.add_parser("deanonymize", help="Ré-hydrater un texte avec jetons depuis le Vault Presidio")
    p_dean.add_argument("text", help="Texte contenant des jetons [TYPE_01]")
    p_dean.add_argument("--session-id", required=True, help="Identifiant de session du Vault")

    p_err = sub.add_parser("format-error", help="Formater un message d'erreur pour l'utilisateur Hermes")
    p_err.add_argument("error", help="Texte ou traceback de l'erreur brute")

    args = parser.parse_args()
    if args.cmd == "retrieve":
        res = ccr_retrieve(args.hash, offset=args.offset, limit=args.limit, json_key=args.key)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        sys.exit(0 if res.get("found") else 1)
    elif args.cmd == "deanonymize":
        res = deanonymize_via_presidio(args.text, session_id=args.session_id)
        print(res)
        sys.exit(0)
    elif args.cmd == "format-error":
        print(format_hermes_error(args.error))
        sys.exit(0)


if __name__ == "__main__":
    main()
