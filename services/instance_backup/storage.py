"""Git isolé, fichiers autorisés et secrets locaux protégés. Aucun force-push."""
import base64
import ctypes
import hashlib
import functools
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit
import urllib.request

LOCK = threading.RLock()
SESSIONS = {}
ALLOWED_FILES = ("instance-secrets.enc", "instance.json")


def serialized(function):
    @functools.wraps(function)
    def execute(*args, **kwargs):
        with LOCK:
            return function(*args, **kwargs)
    return execute


def normalize_settings(cfg):
    settings = dict(cfg.get("instance_git") or {})
    current = cfg.get("instance_backup") or {}
    settings.update({k: v for k, v in current.items() if v not in ("", None) or k not in {"repo_url", "owner", "repo_name"}})
    if not settings.get("repo_url") and settings.get("owner") and settings.get("repo_name"):
        host = "gitlab.com" if settings.get("provider") == "gitlab" else "github.com"
        settings["repo_url"] = "https://" + host + "/" + settings["owner"] + "/" + settings["repo_name"] + ".git"
    return settings


def validate_repo(repo_url, allow_local=False):
    if allow_local and Path(repo_url).is_absolute():
        return
    parsed = urlsplit(repo_url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "gitlab.com"} or parsed.port not in {None, 443} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("URL de dépôt HTTPS GitHub/GitLab sans identifiant requise.")
    if not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", parsed.path):
        raise ValueError("Chemin de dépôt invalide.")


def git_environment(repo_url, token):
    env = os.environ.copy()
    env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never", "GIT_TRACE": "0", "GIT_TRACE_CURL": "0", "GIT_CURL_VERBOSE": "0"})
    if token:
        username = "oauth2" if "gitlab.com" in repo_url else "x-access-token"
        credential = base64.b64encode((username + ":" + token).encode()).decode()
        # Secret transmis uniquement par l'environnement, jamais en URL/argv/config Git.
        env.update({"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "http.extraHeader", "GIT_CONFIG_VALUE_0": "Authorization: Basic " + credential,
                    "GIT_CONFIG_KEY_1": "credential.helper", "GIT_CONFIG_VALUE_1": ""})
    return env


def assert_private(repo_url, token):
    parsed = urlsplit(repo_url)
    project = parsed.path.strip("/")
    if project.endswith(".git"):
        project = project[:-4]
    if parsed.hostname == "github.com":
        request = urllib.request.Request("https://api.github.com/repos/" + project,
                                         headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "User-Agent": "ArcIA"})
        with urllib.request.urlopen(request, timeout=10) as response:
            private = json.load(response).get("private") is True
    else:
        from urllib.parse import quote
        request = urllib.request.Request("https://gitlab.com/api/v4/projects/" + quote(project, safe=""), headers={"PRIVATE-TOKEN": token})
        with urllib.request.urlopen(request, timeout=10) as response:
            private = json.load(response).get("visibility") == "private"
    if not private:
        raise ValueError("La destination de sauvegarde doit être un dépôt privé.")


def push_snapshot(repo_url, token, encrypted_bundle, metadata, *, allow_local=False):
    """Le clone isolé contient uniquement des modifications de fichiers autorisés."""
    validate_repo(repo_url, allow_local)
    if not allow_local:
        assert_private(repo_url, token)
    env = git_environment(repo_url, token)
    with tempfile.TemporaryDirectory(prefix="arcia-backup-") as directory:
        root = Path(directory)
        checkout = root / "checkout"
        hooks = root / "no-hooks"
        hooks.mkdir()

        def git(args, cwd=None, check=True):
            proc = subprocess.run(["git", "-c", "core.hooksPath=" + str(hooks), *args], cwd=cwd, env=env, capture_output=True, timeout=30)
            if check and proc.returncode:
                raise RuntimeError("Opération Git refusée : " + args[0] + ". Aucun force-push effectué.")
            return proc

        git(["clone", "--single-branch", "--", repo_url, str(checkout)])
        # Branche réellement sélectionnée par le dépôt, y compris un dépôt encore vide.
        branch = git(["symbolic-ref", "--short", "HEAD"], cwd=checkout).stdout.decode().strip()
        if not branch or branch.startswith("-"):
            raise RuntimeError("Branche de sauvegarde invalide.")
        if any((checkout / name).is_symlink() for name in ALLOWED_FILES):
            raise RuntimeError("Cible de sauvegarde symbolique interdite.")
        (checkout / "instance-secrets.enc").write_text(encrypted_bundle, encoding="utf-8")
        (checkout / "instance.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        git(["add", "--", *ALLOWED_FILES], cwd=checkout)
        staged = git(["diff", "--cached", "--name-only", "-z"], cwd=checkout).stdout.decode().split("\0")
        if any(name and name not in ALLOWED_FILES for name in staged):
            raise RuntimeError("Fichier étranger à la configuration détecté ; push interdit.")
        if not any(staged):
            return {"success": True, "unchanged": True}
        git(["commit", "-m", "chore(instance): sauvegarde chiffrée de la configuration"], cwd=checkout)
        commit = git(["rev-parse", "HEAD"], cwd=checkout).stdout.decode().strip()
        git(["push", "origin", "HEAD:refs/heads/" + branch], cwd=checkout)
        return {"success": True, "commit": commit, "branch": branch, "repo_url": repo_url}


def read_latest_bundle(repo_url, token):
    """Vérifier un déverrouillage sur l'archive distante, sans checkout ni restauration."""
    validate_repo(repo_url)
    env = git_environment(repo_url, token)
    with tempfile.TemporaryDirectory(prefix="arcia-unlock-") as directory:
        checkout = Path(directory) / "checkout"
        hooks = Path(directory) / "no-hooks"
        hooks.mkdir()

        def git(args):
            return subprocess.run(["git", "-c", "core.hooksPath=" + str(hooks), *args], env=env, capture_output=True, timeout=30)

        if git(["clone", "--depth", "1", "--no-checkout", "--", repo_url, str(checkout)]).returncode:
            raise RuntimeError("Impossible de vérifier le mot de passe sur le dépôt privé.")
        head = git(["-C", str(checkout), "rev-parse", "--verify", "HEAD"])
        if head.returncode:
            return None  # Dépôt vide : première sauvegarde.
        files = git(["-C", str(checkout), "ls-tree", "HEAD", "--", "instance-secrets.enc"])
        if files.returncode:
            raise RuntimeError("Archive distante inaccessible.")
        if not files.stdout:
            return None
        if not files.stdout.startswith(b"100644 "):
            raise ValueError("Format de fichier de sauvegarde distant interdit.")
        bundle = git(["-C", str(checkout), "show", "HEAD:instance-secrets.enc"])
        if bundle.returncode:
            raise RuntimeError("Archive distante inaccessible.")
        return bundle.stdout.decode("utf-8")


def _dpapi(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Coffre persistant indisponible ; déverrouillage en mémoire pour cette session.")
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RuntimeError("Coffre local inaccessible.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def unlock(root, repo_url, token, passphrase):
    validate_repo(repo_url)
    if not passphrase:
        raise ValueError("Mot de passe maître requis dans le formulaire local.")
    key = (str(Path(root).resolve()), repo_url)
    SESSIONS[key] = {"token": token, "passphrase": passphrase}
    persisted = False
    try:
        path = Path(root) / "secrets" / "instance-backup.dpapi"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".part")
        temporary.write_bytes(_dpapi(json.dumps({"repo_url": repo_url, "token": token, "passphrase": passphrase}).encode()))
        os.replace(temporary, path)
        persisted = True
    except (OSError, RuntimeError):
        pass
    return {"unlocked": True, "credentials_persisted": persisted}


def credentials(root, settings):
    repo = settings.get("repo_url", "")
    key = (str(Path(root).resolve()), repo)
    if key not in SESSIONS:
        try:
            data = json.loads(_dpapi((Path(root) / "secrets" / "instance-backup.dpapi").read_bytes(), decrypt=True))
            if data.get("repo_url") == repo:
                SESSIONS[key] = {"token": data["token"], "passphrase": data["passphrase"]}
        except (OSError, ValueError, RuntimeError):
            pass
    found = SESSIONS.get(key, {})
    token = found.get("token") or settings.get("git_token") or settings.get("token") or ""
    if not token and urlsplit(repo).hostname == "github.com":
        # Réutiliser l'identité du programme local gh ; aucune valeur vers le navigateur.
        try:
            proc = subprocess.run(["gh", "auth", "token", "--hostname", "github.com"], capture_output=True, timeout=5)
            if proc.returncode == 0:
                token = proc.stdout.decode().strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {"token": token,
            "passphrase": found.get("passphrase") or ""}


def save_status(root, status):
    path = Path(root) / "secrets" / "instance-backup-status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def status(root):
    try:
        return json.loads((Path(root) / "secrets" / "instance-backup-status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def backup(root, cfg, config_yaml, env_content, encrypt, *, force=False, extra_payload=None, coverage=None):
    settings = normalize_settings(cfg)
    if not settings.get("repo_url") or settings.get("enabled") is False:
        result = {"success": False, "state": "not_configured", "error": "Dépôt privé de sauvegarde non configuré."}
        save_status(root, result)
        return result
    with LOCK:
        auth = credentials(root, settings)
        if not auth["passphrase"]:
            result = {"success": False, "state": "locked", "error": "Sauvegarde en attente : déverrouillez le coffre dans Sauvegarde et reprise."}
            save_status(root, result)
            return result
        clean = json.loads(json.dumps(cfg))
        for section in ("instance_backup", "instance_git"):
            for field in ("last_backup", "last_commit", "last_digest", "passphrase"):
                clean.get(section, {}).pop(field, None)
        if coverage and not coverage.get("complete"):
            result = {"success": False, "state": "incomplete", "error": "Sauvegarde incomplète refusée : un fichier de configuration référencé est absent ou inaccessible.", "coverage": coverage}
            save_status(root, result)
            return result
        digest = hashlib.sha256((json.dumps(clean, sort_keys=True, ensure_ascii=False) + env_content + json.dumps(extra_payload or {}, sort_keys=True)).encode()).hexdigest()
        previous = status(root)
        if not force and previous.get("success") and previous.get("digest") == digest and previous.get("repo_url") == settings["repo_url"]:
            return previous
        payload = {"config_yaml": config_yaml, "env_content": env_content, "schema": "arcia-instance-v1"}
        if extra_payload:
            payload.update(extra_payload)
            payload["schema"] = "arcia-instance-v2"
        try:
            queue = Path(root) / "secrets" / "backup-pending"
            queue.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            snapshots = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(queue.glob("*.json"))]
            if not any(s.get("repo_url") == settings["repo_url"] and s.get("digest") == digest for s in snapshots):
                bundle = encrypt(payload, auth["passphrase"])
                pending = queue / (str(time.time_ns()) + ".json")
                temporary = pending.with_suffix(".part")
                temporary.write_text(json.dumps({"repo_url": settings["repo_url"], "bundle": bundle, "digest": digest,
                                              "metadata": {"schema_version": 2 if extra_payload else 1, "encryption": "AES-256-GCM", "updated_at": timestamp}}, ensure_ascii=False), encoding="utf-8")
                os.replace(temporary, pending)
            result = {}
            for candidate in sorted(queue.glob("*.json")):
                snapshot = json.loads(candidate.read_text(encoding="utf-8"))
                if snapshot["repo_url"] != settings["repo_url"]:
                    continue
                result = push_snapshot(settings["repo_url"], auth["token"], snapshot["bundle"], snapshot["metadata"])
                candidate.unlink()
            result.update({"state": "pushed", "timestamp": timestamp, "digest": digest, "repo_url": settings["repo_url"]})
        except Exception:
            result = {"success": False, "state": "pending", "error": "Sauvegarde non poussée : vérifier le coffre, les droits Git, la visibilité privée et la divergence du dépôt. Aucune écriture forcée."}
        if coverage:
            result["coverage"] = coverage
        save_status(root, result)
        return result
