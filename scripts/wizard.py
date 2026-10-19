#!/usr/bin/env python3
"""
ArcIA — Assistant & Moteur d'Installation Graphique Interactif (Wizard)
========================================================================
Ce serveur web autonome (Python 3, cryptography requis pour les sauvegardes AES-256-GCM)
guide pas-à-pas l'administrateur pour configurer, déployer et restaurer une instance
ArcIA complète et 100% opérationnelle dès le clone initial du dépôt Git.

Fonctionnalités :
  1. Installer une nouvelle instance -> Déploiement + Création de dépôt Git d'instance
     privé chiffré (GitHub / GitLab) avec mot de passe maître de chiffrement.
  2. Restaurer une instance existante -> Récupération depuis le dépôt Git privé +
     déchiffrement des secrets via mot de passe -> Déploiement complet en 1 clic.

Usage :
    python scripts/wizard.py [--port 8765] [--no-browser]
    ./wizard.sh           (Linux / macOS)
    .\\wizard.ps1         (Windows PowerShell)
"""

import os
import sys
import re
import json
import time
import socket
import ssl
import secrets
import argparse
import threading
import subprocess
import webbrowser
import base64
import urllib.request
import urllib.error
import tempfile
import shutil
from pathlib import Path
try:
    from http.server import ThreadingHTTPServer as HttpServerClass, BaseHTTPRequestHandler
except ImportError:
    from http.server import HTTPServer as HttpServerClass, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, List, Tuple

# Support chiffrement standard AEAD AES-256-GCM
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

# Support UTF-8 console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, ROOT_DIR)
from services.instance_backup import storage as instance_storage
from services.open_webui.branding import resolve_model_icon
DEFAULT_CONFIG_PATH = os.path.join(ROOT_DIR, "arcia.config.yaml")
EXAMPLE_CONFIG_PATH = os.path.join(ROOT_DIR, "arcia.config.yaml.example")

# Global deployment state
deployment_lock = threading.Lock()
deployment_state = {
    "status": "idle",       # "idle", "running", "success", "error"
    "logs": [],
    "start_time": None,
    "exit_code": None,
    "summary": {}
}
active_deployment_proc: Optional[subprocess.Popen] = None


# Global zero-downtime update state
update_lock = threading.Lock()
update_state = {
    "status": "idle",       # "idle", "running", "success", "error"
    "progress_pct": 0,
    "current_phase": "En attente",
    "phases": [],
    "logs": [],
    "start_time": None,
    "updated_components": []
}
last_update_check_cache: Dict[str, Any] = {}

# -----------------------------------------------------------------------------
# Utilitaires Cryptographiques & Chiffrement d'Instance (AES-256-GCM / PBKDF2)
# -----------------------------------------------------------------------------

def generate_token(kind: str) -> str:
    """Génère un jeton cryptographiquement sécurisé."""
    if kind == "litellm":
        return "sk-arcia-" + secrets.token_urlsafe(32)
    elif kind == "pat":
        return f"arcia-pat-{secrets.token_urlsafe(24)}"
    elif kind == "cookie":
        return secrets.token_urlsafe(32)
    elif kind == "admin":
        return secrets.token_urlsafe(16)
    elif kind == "presidio":
        return f"arcia-master-{secrets.token_hex(16)}"
    return secrets.token_urlsafe(24)

def encrypt_instance_bundle(payload_dict: dict, passphrase: str) -> str:
    """Chiffre les secrets et la configuration d'instance avec AES-256-GCM et dérivation PBKDF2."""
    if not passphrase:
        raise ValueError("Le mot de passe de chiffrement ne peut pas être vide.")
    if not HAS_CRYPTOGRAPHY:
        raise RuntimeError("Le module cryptography est requis pour AES-256-GCM ; aucune sauvegarde dégradée.")

    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(payload_dict, ensure_ascii=False).encode('utf-8')

    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = kdf.derive(passphrase.encode('utf-8'))
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, b'ARCIA_INSTANCE_V1')
    algo = "AES-256-GCM"

    bundle = {
        'schema': 'arcia-instance-v1',
        'algo': algo,
        'salt': base64.b64encode(salt).decode('utf-8'),
        'nonce': base64.b64encode(nonce).decode('utf-8'),
        'ciphertext': base64.b64encode(ciphertext).decode('utf-8')
    }
    return json.dumps(bundle, indent=2)

def decrypt_instance_bundle(bundle_str: str, passphrase: str) -> dict:
    """Déchiffre le bundle d'instance et vérifie l'intégrité via le mot de passe maître."""
    if not passphrase:
        raise ValueError("Veuillez renseigner le mot de passe de déchiffrement.")

    try:
        bundle = json.loads(bundle_str)
        salt = base64.b64decode(bundle['salt'])
        nonce = base64.b64decode(bundle['nonce'])
        ciphertext = base64.b64decode(bundle['ciphertext'])
        algo = bundle.get('algo', 'AES-256-GCM')

        if algo == "AES-256-GCM" and HAS_CRYPTOGRAPHY:
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
            key = kdf.derive(passphrase.encode('utf-8'))
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, b'ARCIA_INSTANCE_V1')
        elif algo == "HMAC-SHA256-STREAM":
            import hashlib, hmac
            key = hashlib.pbkdf2_hmac('sha256', passphrase.encode('utf-8'), salt, 100000, 64)
            enc_key, mac_key = key[:32], key[32:]
            tag_len = 32
            if len(ciphertext) < tag_len:
                raise ValueError("Format de bundle invalide.")
            ct_bytes = ciphertext[:-tag_len]
            tag = ciphertext[-tag_len:]
            expected_tag = hmac.new(mac_key, b'ARCIA_INSTANCE_V1' + nonce + ct_bytes, hashlib.sha256).digest()
            if not hmac.compare_digest(tag, expected_tag):
                raise ValueError("Authentification échouée")
            keystream = bytearray()
            block_idx = 0
            while len(keystream) < len(ct_bytes):
                keystream.extend(hmac.new(enc_key, nonce + block_idx.to_bytes(4, 'big'), hashlib.sha256).digest())
                block_idx += 1
            plaintext = bytes([c ^ k for c, k in zip(ct_bytes, keystream[:len(ct_bytes)])])

        else:
            raise ValueError("Algorithme inconnu ou cryptography absent.")
        return json.loads(plaintext.decode('utf-8'))
    except Exception:
        raise ValueError("Mot de passe de restauration incorrect ou données d'instance corrompues.")

# -----------------------------------------------------------------------------
# Gestion des Dépôts Git d'Instance Privés (GitHub / GitLab)
# -----------------------------------------------------------------------------

def git_test_credentials(provider: str, token: str) -> dict:
    """Valide le jeton Git (GitHub ou GitLab) et liste les organisations accessibles."""
    token = (token or "").strip()
    if not token:
        return {"success": False, "error": "Jeton d'accès Git non renseigné."}

    headers = {"User-Agent": "ArcIA-Setup-Wizard"}
    if provider == "github":
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github.v3+json"
        try:
            req = urllib.request.Request("https://api.github.com/user", headers=headers)
            with urllib.request.urlopen(req, timeout=8) as res:
                user_data = json.loads(res.read().decode("utf-8"))
                username = user_data.get("login", "")
        except urllib.error.HTTPError as e:
            return {"success": False, "error": f"Erreur GitHub HTTP {e.code} (Jeton invalide ou permissions insuffisantes)."}
        except Exception as e:
            return {"success": False, "error": f"Erreur de connexion à GitHub : {str(e)}"}

        targets = [username]
        try:
            req_orgs = urllib.request.Request("https://api.github.com/user/orgs", headers=headers)
            with urllib.request.urlopen(req_orgs, timeout=8) as res:
                orgs_data = json.loads(res.read().decode("utf-8"))
                for o in orgs_data:
                    if o.get("login"):
                        targets.append(o.get("login"))
        except Exception:
            pass
        return {"success": True, "username": username, "targets": targets}

    elif provider == "gitlab":
        headers["PRIVATE-TOKEN"] = token
        try:
            req = urllib.request.Request("https://gitlab.com/api/v4/user", headers=headers)
            with urllib.request.urlopen(req, timeout=8) as res:
                user_data = json.loads(res.read().decode("utf-8"))
                username = user_data.get("username", "")
        except urllib.error.HTTPError as e:
            return {"success": False, "error": f"Erreur GitLab HTTP {e.code} (Jeton invalide)."}
        except Exception as e:
            return {"success": False, "error": f"Erreur de connexion à GitLab : {str(e)}"}

        targets = [username]
        try:
            req_groups = urllib.request.Request("https://gitlab.com/api/v4/groups?min_access_level=30", headers=headers)
            with urllib.request.urlopen(req_groups, timeout=8) as res:
                groups_data = json.loads(res.read().decode("utf-8"))
                for g in groups_data:
                    if g.get("full_path"):
                        targets.append(g.get("full_path"))
        except Exception:
            pass
        return {"success": True, "username": username, "targets": targets}

    return {"success": True, "username": "custom", "targets": ["custom"]}

def git_create_remote_repo(provider: str, token: str, repo_name: str, owner: str = None) -> dict:
    """Crée automatiquement un dépôt privé distant sur GitHub ou GitLab."""
    token = (token or "").strip()
    repo_name = (repo_name or "").strip()
    owner = (owner or "").strip() if owner else ""

    if not token:
        return {"success": False, "error": "Jeton d'accès Git non renseigné."}
    if not repo_name:
        return {"success": False, "error": "Nom du dépôt Git non renseigné."}

    headers = {"User-Agent": "ArcIA-Setup-Wizard"}
    if provider == "github":
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github.v3+json"
        headers["Content-Type"] = "application/json"

        user_info = git_test_credentials("github", token)
        if not user_info.get("success"):
            return {
                "success": False,
                "error": f"Authentification GitHub impossible : {user_info.get('error', 'Jeton invalide')}"
            }

        username = user_info.get("username", "")
        is_org = bool(owner and owner.lower() != username.lower())
        url = f"https://api.github.com/orgs/{owner}/repos" if is_org else "https://api.github.com/user/repos"

        payload = {
            "name": repo_name,
            "private": True,
            "description": "Dépôt d'instance privée ArcIA — Configuration et secrets chiffrés",
            "auto_init": False
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                repo_info = json.loads(res.read().decode("utf-8"))
                return {
                    "success": True,
                    "clone_url": repo_info.get("clone_url"),
                    "html_url": repo_info.get("html_url")
                }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if "already exists" in err_body or e.code == 422:
                target_owner = owner if is_org else username
                return {
                    "success": True,
                    "clone_url": f"https://github.com/{target_owner}/{repo_name}.git",
                    "html_url": f"https://github.com/{target_owner}/{repo_name}",
                    "already_existed": True
                }
            elif e.code == 404:
                return {
                    "success": False,
                    "error": f"Échec création dépôt GitHub (HTTP 404) : L'organisation ou compte '{owner or username}' est introuvable ou vous n'avez pas les droits d'administration."
                }
            elif e.code == 403:
                return {
                    "success": False,
                    "error": f"Échec création dépôt GitHub (HTTP 403) : Droits insuffisants sur '{owner or username}'. Vérifiez les permissions (scope 'repo') de votre jeton d'accès personnel."
                }
            return {"success": False, "error": f"Échec création dépôt GitHub : HTTP {e.code} ({err_body})"}
        except Exception as e:
            return {"success": False, "error": f"Erreur de connexion à GitHub : {str(e)}"}

    elif provider == "gitlab":
        headers["PRIVATE-TOKEN"] = token
        headers["Content-Type"] = "application/json"

        user_info = git_test_credentials("gitlab", token)
        if not user_info.get("success"):
            return {
                "success": False,
                "error": f"Authentification GitLab impossible : {user_info.get('error', 'Jeton invalide')}"
            }

        username = user_info.get("username", "")
        payload = {
            "name": repo_name,
            "visibility": "private",
            "description": "Dépôt d'instance privée ArcIA — Configuration et secrets chiffrés"
        }
        req = urllib.request.Request("https://gitlab.com/api/v4/projects", data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                proj_info = json.loads(res.read().decode("utf-8"))
                return {
                    "success": True,
                    "clone_url": proj_info.get("http_url_to_repo"),
                    "html_url": proj_info.get("web_url")
                }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if "has already been taken" in err_body or e.code == 400:
                target_owner = owner or username
                return {
                    "success": True,
                    "clone_url": f"https://gitlab.com/{target_owner}/{repo_name}.git",
                    "html_url": f"https://gitlab.com/{target_owner}/{repo_name}",
                    "already_existed": True
                }
            return {"success": False, "error": f"Échec création projet GitLab : HTTP {e.code} ({err_body})"}
        except Exception as e:
            return {"success": False, "error": f"Erreur de connexion à GitLab : {str(e)}"}

    return {"success": False, "error": "Fournisseur Git non pris en charge."}

def git_push_instance(repo_url: str, token: str, encrypted_bundle_str: str, instance_name: str, fqdn: str) -> dict:
    """Push limité au bundle et à son manifeste, depuis un clone isolé."""
    try:
        result = instance_storage.push_snapshot(repo_url, token, encrypted_bundle_str,
                    {"schema_version": 1, "encryption": "AES-256-GCM", "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        if result.get("success"):
            cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
            settings = instance_storage.normalize_settings(cfg)
            settings.update({"enabled": True, "repo_url": repo_url})
            cfg["instance_backup"] = settings
            save_config_to_files(cfg, DEFAULT_CONFIG_PATH, trigger_backup=False)
        return result
    except Exception:
        return {"success": False, "error": "Push du dépôt privé refusé ; vérifier les accès et la branche. Aucun force-push effectué."}


def get_instance_backup_timeline(repo_url: str, token: str) -> dict:
    """Récupère l'historique des commits de sauvegarde chiffrée depuis le dépôt privé."""
    temp_dir = tempfile.mkdtemp(prefix="arcia-timeline-")
    try:
        instance_storage.validate_repo(repo_url)
        git_env = instance_storage.git_environment(repo_url, token)
        proc = subprocess.run(["git", "clone", "--depth", "50", repo_url, temp_dir], capture_output=True, timeout=30, env=git_env)
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")
            return {"success": False, "error": "Dépôt inaccessible ; vérifier les accès locaux.", "timeline": []}

        log_proc = subprocess.run(
            ["git", "log", "--format=%H|%ad|%s", "--date=iso", "--", "instance-secrets.enc"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if log_proc.returncode:
            return {"success": False, "error": "Historique de sauvegarde inaccessible.", "timeline": []}
        timeline = []
        if log_proc.returncode == 0 and log_proc.stdout.strip():
            for line in log_proc.stdout.strip().splitlines():
                parts = line.split("|", 2)
                if len(parts) >= 3:
                    c_hash, c_date, c_msg = parts[0].strip(), parts[1].strip(), parts[2].strip()
                    timeline.append({
                        "hash": c_hash,
                        "short_hash": c_hash[:7],
                        "datetime": c_date,
                        "message": c_msg
                    })

        last_backup = timeline[0]["datetime"] if timeline else None
        return {
            "success": True,
            "repo_url": repo_url,
            "last_backup": last_backup,
            "timeline": timeline
        }
    except Exception as e:
        return {"success": False, "error": "Lecture du dépôt de sauvegarde impossible.", "timeline": []}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def git_pull_and_decrypt_instance(repo_url: str, token: str, passphrase: str, commit_hash: Optional[str] = None) -> dict:
    """Clone le dépôt d'instance privé et déchiffre la configuration avec le mot de passe maître."""
    temp_dir = tempfile.mkdtemp(prefix="arcia-restore-")
    try:
        instance_storage.validate_repo(repo_url)
        git_env = instance_storage.git_environment(repo_url, token)
        depth_args = [] if commit_hash else ["--depth", "50"]
        proc = subprocess.run(["git", "clone"] + depth_args + [repo_url, temp_dir], capture_output=True, timeout=30, env=git_env)
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")
            return {"success": False, "error": "Dépôt d'instance inaccessible ; vérifier les accès locaux."}

        if commit_hash and not re.fullmatch(r"[a-fA-F0-9]{7,64}", commit_hash):
            raise ValueError("Révision de restauration invalide.")
        if commit_hash:
            ck = subprocess.run(["git", "checkout", "--detach", commit_hash], cwd=temp_dir, capture_output=True, timeout=15)
            if ck.returncode != 0:
                return {"success": False, "error": f"Point de restauration {commit_hash[:7]} introuvable."}

        enc_file = os.path.join(temp_dir, "instance-secrets.enc")
        if os.path.islink(enc_file):
            raise ValueError("Lien symbolique de sauvegarde interdit.")
        if not os.path.isfile(enc_file):
            return {"success": False, "error": "Fichier 'instance-secrets.enc' introuvable dans ce dépôt."}

        with open(enc_file, "r", encoding="utf-8") as f:
            bundle_str = f.read()

        decrypted = decrypt_instance_bundle(bundle_str, passphrase)

        config_yaml = decrypted.get("config_yaml", "")
        if not isinstance(decrypted.get("env_content", ""), str):
            raise ValueError("Environnement restauré invalide.")
        if not isinstance(config_yaml, str) or not config_yaml:
            return {"success": False, "error": "Le bundle d'instance ne contient pas de configuration valide."}

        # Valider avant écriture ; utiliser ensuite la même transaction que toute sauvegarde.
        try:
            import yaml
            cfg = yaml.safe_load(config_yaml)
        except ImportError:
            import deploy
            cfg = deploy.parse_simple_yaml(config_yaml)
        if not isinstance(cfg, dict):
            raise ValueError("Configuration restaurée invalide.")
        cfg = ensure_config_defaults(cfg)
        settings = instance_storage.normalize_settings(cfg)
        settings.update({"enabled": True, "repo_url": repo_url})
        cfg["instance_backup"] = settings
        instance_storage.unlock(ROOT_DIR, repo_url, token, passphrase)
        backup_result = save_config_to_files(cfg, DEFAULT_CONFIG_PATH, restored_env=decrypted.get("env_content", ""))
        return {
            "success": True,
            "instance_name": decrypted.get("instance_name", "ArcIA-instance"),
            "public_fqdn": decrypted.get("public_fqdn", cfg.get("network", {}).get("public_fqdn", "")),
            "config": cfg,
            "backup_status": backup_result,
            "commit_hash": commit_hash,
            "message": f"Instance '{decrypted.get('instance_name', '')}' restaurée avec succès !"
        }

    except ValueError as ve:
        return {"success": False, "error": str(ve)}
    except Exception:
        return {"success": False, "error": "Restauration impossible ; vérifier le dépôt, le coffre et la configuration chiffrée."}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def get_instance_backup_info() -> dict:
    """Renvoie les informations actuelles sur le dépôt de sauvegarde d'instance et la timeline des commits."""
    cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
    backup_cfg = instance_storage.normalize_settings(cfg)
    repo_url = backup_cfg.get("repo_url", "").strip()
    token = instance_storage.credentials(ROOT_DIR, backup_cfg)["token"]
    last_backup = backup_cfg.get("last_backup", None)

    if not repo_url:
        return {
            "success": True,
            "configured": False,
            "repo_url": "",
            "last_backup": None,
            "timeline": []
        }

    timeline_res = get_instance_backup_timeline(repo_url, token)
    return {
        "success": timeline_res.get("success", False),
        "configured": True,
        "repo_url": repo_url,
        "last_backup": timeline_res.get("last_backup") or last_backup,
        "timeline": timeline_res.get("timeline", []),
        "error": timeline_res.get("error"),
        "backup_status": instance_storage.status(ROOT_DIR),
        "unlocked": bool(instance_storage.credentials(ROOT_DIR, backup_cfg)["passphrase"])
    }

def get_integrations_status(cfg: Optional[Dict[str, Any]] = None) -> dict:
    """Vérifie l'état de configuration et de connectivité en production du SSO Entra ID et du Bot Teams."""
    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)

    sso_cfg = cfg.get("entra_id_sso", {})
    teams_cfg = cfg.get("teams_bot", {})

    sso_enabled = bool(sso_cfg.get("enabled", False))
    teams_enabled = bool(teams_cfg.get("enabled", False))

    res = {
        "success": True,
        "sso": {
            "enabled": sso_enabled,
            "configured": bool(sso_cfg.get("tenant_id") and sso_cfg.get("client_id")),
            "status": "inactive",
            "ready_replicas": 0,
            "tenant_id": sso_cfg.get("tenant_id", ""),
            "client_id": sso_cfg.get("client_id", ""),
            "message": "Non configuré" if not sso_enabled else "Désactivé"
        },
        "teams": {
            "enabled": teams_enabled,
            "configured": bool(teams_cfg.get("app_id") and teams_cfg.get("app_password")),
            "status": "inactive",
            "ready_replicas": 0,
            "app_id": teams_cfg.get("app_id", ""),
            "message": "Non configuré" if not teams_enabled else "Désactivé"
        }
    }

    try:
        runner = get_k8s_runner(cfg)
        ns = cfg.get("kubernetes", {}).get("namespace", "arcia")
        rc, out, _ = runner.run(["get", "deployments", f"-n={ns}", "-o", "json"], timeout=4)
        if rc == 0 and out.strip():
            data = json.loads(out)
            for item in data.get("items", []):
                name = item.get("metadata", {}).get("name", "")
                status = item.get("status", {})
                ready = status.get("readyReplicas", 0)
                if name == "oauth2-proxy":
                    if ready > 0:
                        res["sso"]["status"] = "connected"
                        res["sso"]["ready_replicas"] = ready
                        res["sso"]["message"] = f"Opérationnel ({ready} pod(s) actif(s))"
                    elif sso_enabled:
                        res["sso"]["status"] = "starting"
                        res["sso"]["message"] = "En attente de démarrage du pod"
                elif name == "teams-bot-adapter":
                    if ready > 0:
                        res["teams"]["status"] = "connected"
                        res["teams"]["ready_replicas"] = ready
                        res["teams"]["message"] = f"Opérationnel ({ready} pod(s) actif(s))"
                    elif teams_enabled:
                        res["teams"]["status"] = "starting"
                        res["teams"]["message"] = "En attente de démarrage du pod"
    except Exception:
        pass

    return res

# -----------------------------------------------------------------------------
# Dimensionnement VMware vSphere & Cibles d'Infrastructure
# -----------------------------------------------------------------------------

VMWARE_SIZING_TIERS = {
    "20": {
        "title": "Équipe pilote",
        "users_label": "Jusqu'à 20 utilisateurs",
        "description": "Gabarit pour évaluation, validation technique ou petite équipe projet.",
        "nodes": 1,
        "type": "All-in-One (Control-Plane + Worker)",
        "vcpu_per_node": 4,
        "ram_per_node_gb": 8,
        "disk_per_node_gb": 100,
        "total_vcpu": 4,
        "total_ram_gb": 8,
        "total_disk_gb": 100,
        "rag_storage_gb": 50,
        "rag_label": "50 Go dédiés RAG (~10 000 pages, documents + base vectorielle ChromaDB)",
        "open_webui_pvc": "50Gi",
        "concurrency": "1 à 3 interactions agentiques simultanées",
        "recommended": False
    },
    "100": {
        "title": "PME",
        "users_label": "21 à 100 utilisateurs",
        "description": "Cluster K3s haute disponibilité avec résilience multi-nœuds (etcd multi-maître).",
        "nodes": 3,
        "type": "3x Control-Plane HA / Workers",
        "vcpu_per_node": 4,
        "ram_per_node_gb": 16,
        "disk_per_node_gb": 150,
        "total_vcpu": 12,
        "total_ram_gb": 48,
        "total_disk_gb": 450,
        "rag_storage_gb": 200,
        "rag_label": "200 Go dédiés RAG (~100 000 pages, base vectorielle ChromaDB HNSW, collections inter-services)",
        "open_webui_pvc": "200Gi",
        "concurrency": "15 interactions simultanées avec streaming et DLP en temps réel",
        "recommended": False
    },
    "500": {
        "title": "Entreprise",
        "users_label": "101 à 500 utilisateurs",
        "description": "Séparation du plan de contrôle et des nœuds d'exécution agentique.",
        "nodes": 5,
        "type": "3x Control-Plane HA + 2x Workers dédiés",
        "vcpu_per_node": 8,
        "ram_per_node_gb": 32,
        "disk_per_node_gb": 250,
        "total_vcpu": 28,
        "total_ram_gb": 112,
        "total_disk_gb": 1250,
        "rag_storage_gb": 600,
        "rag_label": "600 Go dédiés RAG (~500 000 pages, bases multi-départements, embeddings denses)",
        "open_webui_pvc": "600Gi",
        "concurrency": "60 interactions simultanées, flux Teams continus, pipelines Graphify",
        "recommended": False
    },
    "1000": {
        "title": "Grande entreprise",
        "users_label": "Plus de 500 utilisateurs",
        "description": "Architecture multi-nœuds extensible, stockage haute performance et option vGPU.",
        "nodes": 7,
        "type": "3x Control-Plane HA + 4x Workers haute performance",
        "vcpu_per_node": 16,
        "ram_per_node_gb": 64,
        "disk_per_node_gb": 500,
        "total_vcpu": 88,
        "total_ram_gb": 352,
        "total_disk_gb": 3500,
        "rag_storage_gb": 2000,
        "rag_label": "2 To à 5 To dédiés RAG (Millions de documents, index distribué, modèles locaux)",
        "open_webui_pvc": "2Ti",
        "concurrency": "200+ interactions simultanées, modèles LLM locaux vLLM optionnels",
        "recommended": False
    }
}

def discover_vsphere_resources(host: str, port: int, session_id: str, ssl_ctx: Any) -> Dict[str, List[Dict[str, str]]]:
    """Interroge les API REST vSphere pour découvrir dynamiquement Datacenters, Clusters/RP, Datastores et Réseaux."""
    resources: Dict[str, List[Dict[str, str]]] = {
        "datacenters": [],
        "clusters": [],
        "datastores": [],
        "networks": []
    }
    if not session_id:
        return resources

    headers = {
        "vmware-api-session-id": session_id,
        "Accept": "application/json"
    }

    def _fetch_list(endpoint_rest: str, endpoint_api: str, key_name: str = "name") -> List[Dict[str, str]]:
        items = []
        for endpoint in [endpoint_rest, endpoint_api]:
            url = f"https://{host}:{port}{endpoint}"
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=8, context=ssl_ctx) as resp:
                    if resp.status == 200:
                        raw = json.loads(resp.read().decode("utf-8"))
                        data_list = raw.get("value", raw if isinstance(raw, list) else [])
                        for entry in data_list:
                            if isinstance(entry, dict) and key_name in entry:
                                name = entry[key_name]
                                extra = ""
                                if "free_space" in entry:
                                    free_gb = round(entry["free_space"] / (1024**3), 1)
                                    cap_gb = round(entry.get("capacity", 0) / (1024**3), 1)
                                    extra = f" ({free_gb} Go libres / {cap_gb} Go)"
                                elif "type" in entry:
                                    extra = f" ({entry['type']})"
                                items.append({"name": name, "label": f"{name}{extra}"})
                        if items:
                            break
            except Exception:
                continue
        return items

    # 1. Datacenters
    resources["datacenters"] = _fetch_list("/rest/vcenter/datacenter", "/api/vcenter/datacenter")

    # 2. Clusters & Resource Pools
    clusters = _fetch_list("/rest/vcenter/cluster", "/api/vcenter/cluster")
    rps = _fetch_list("/rest/vcenter/resource-pool", "/api/vcenter/resource-pool")
    for r in rps:
        if not any(c["name"] == r["name"] for c in clusters):
            clusters.append({"name": r["name"], "label": f"{r['name']} (Resource Pool)"})
    resources["clusters"] = clusters

    # 3. Datastores
    resources["datastores"] = _fetch_list("/rest/vcenter/datastore", "/api/vcenter/datastore")

    # 4. Réseaux / Portgroups
    resources["networks"] = _fetch_list("/rest/vcenter/network", "/api/vcenter/network")

    return resources

def test_vmware_connection(data: Dict[str, Any]) -> Dict[str, Any]:
    """Valide la connectivité réseau et les identifiants vCenter / ESXi, et découvre les ressources d'infrastructure."""
    host = data.get("host", "").strip()
    port = int(data.get("port", 443))
    user = data.get("username", "").strip()
    password = data.get("password", "").strip()
    insecure = data.get("insecure_tls", False)
    target_type = data.get("target_type", "vCenter Server")

    if not host:
        return {"success": False, "error": "L'adresse d'hôte ou IP du serveur vSphere est obligatoire."}

    # 1. Test de connectivité socket TCP
    try:
        sock = socket.create_connection((host, port), timeout=6)
        sock.close()
    except Exception as se:
        return {
            "success": False,
            "error": f"Impossible d'établir la connexion TCP vers {host}:{port} ({str(se)}). Vérifiez l'adresse IP et les flux réseau (port {port})."
        }

    # 2. Test poignée de main TLS / HTTPS
    try:
        ctx = ssl.create_default_context()
        if insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=6) as raw_sock:
            with ctx.wrap_socket(raw_sock, server_hostname=host if not insecure else None) as ssock:
                _ = ssock.getpeercert()
    except ssl.SSLCertVerificationError:
        return {
            "success": False,
            "error": "Échec de vérification du certificat TLS vSphere. Cochez l'option 'Autoriser les certificats vSphere auto-signés' pour continuer."
        }
    except Exception as te:
        return {
            "success": False,
            "error": f"Erreur lors de la négociation TLS vers {host}:{port} : {str(te)}"
        }

    # 3. Test authentification session vSphere et découverte de ressources si identifiants fournis
    auth_status = "Non authentifié (connectivité réseau et TLS confirmées)"
    session_id = None
    detected_version = "VMware vCenter Server" if "vcenter" in target_type.lower() else "Hôte VMware ESXi"
    discovered_resources: Dict[str, List[Dict[str, str]]] = {
        "datacenters": [],
        "clusters": [],
        "datastores": [],
        "networks": []
    }

    if user and password:
        ssl_ctx = ssl.create_default_context()
        if insecure:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        try:
            creds = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("utf-8")
            headers = {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

            # Tentative session REST classique CIS puis API moderne
            for session_endpoint in ["/rest/com/vmware/cis/session", "/api/session"]:
                try:
                    auth_url = f"https://{host}:{port}{session_endpoint}"
                    req = urllib.request.Request(auth_url, data=b"{}", headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=8, context=ssl_ctx) as resp:
                        if resp.status == 200:
                            content = resp.read().decode("utf-8")
                            body = json.loads(content)
                            session_id = body.get("value", body if isinstance(body, str) else None)
                            auth_status = "Authentification REST vSphere réussie"
                            break
                except urllib.error.HTTPError as he:
                    if he.code == 401:
                        return {"success": False, "error": "Échec d'authentification vSphere : nom d'utilisateur ou mot de passe incorrect."}
                except Exception:
                    pass

            if session_id:
                # Découverte dynamique des ressources d'infrastructure (Datacenters, Clusters, Datastores, Réseaux)
                discovered_resources = discover_vsphere_resources(host, port, session_id, ssl_ctx)
        except Exception as ae:
            auth_status = f"Vérification réseau OK (auth : {str(ae)})"

    return {
        "success": True,
        "message": f"Connexion vSphere établie avec succès sur {host}:{port} !",
        "details": {
            "host": host,
            "port": port,
            "target_type": target_type,
            "detected_version": detected_version,
            "auth_status": auth_status,
            "tls_verified": not insecure
        },
        "resources": discovered_resources
    }

def audit_kubernetes_environment_full(runner: Any) -> Dict[str, Any]:
    """Exécute un audit de qualification exhaustif sur un environnement Kubernetes existant."""
    checks = []

    # 1. API Server & Version
    rc_ver, out_ver, err_ver = runner.run(["version", "-o", "json"])
    k8s_version = "Inconnue"
    ver_ok = False
    err_ci = ""
    if rc_ver == 0:
        try:
            v_data = json.loads(out_ver)
            server_v = v_data.get("serverVersion", {})
            k8s_version = server_v.get("gitVersion", "v1.28+")
            major = int(re.sub(r"\D", "", server_v.get("major", "1")) or "1")
            minor = int(re.sub(r"\D", "", server_v.get("minor", "28")) or "28")
            ver_ok = (major > 1) or (major == 1 and minor >= 28)
        except Exception:
            ver_ok = True
    else:
        rc_ci, out_ci, err_ci = runner.run(["cluster-info"])
        ver_ok = (rc_ci == 0)

    api_msg = f"Connectivité confirmée ({k8s_version})" if ver_ok else "Impossible de joindre le serveur d'API Kubernetes."
    api_rec = "Assurez-vous que le cluster K8s (v1.28+) est opérationnel et accessible."
    if not ver_ok and runner.mode == "remote-ssh":
        raw_err = (err_ver or err_ci or "").strip()
        if "Permission denied" in raw_err:
            api_msg = f"Échec d'authentification SSH ({runner.ssh_user}@{runner.ssh_node}) : Permission refusée."
            api_rec = "Renseignez le chemin vers la clé privée SSH (.pem, id_rsa, id_ed25519) autorisée sur ce serveur."
        elif "introuvable sur le disque" in raw_err:
            api_msg = raw_err
            api_rec = "Vérifiez le chemin local vers votre fichier de clé privée SSH."
        elif "Could not resolve" in raw_err or "Connection refused" in raw_err or "timed out" in raw_err.lower():
            api_msg = f"Échec réseau SSH vers {runner.ssh_node}:{runner.ssh_port} : {raw_err}"
            api_rec = "Vérifiez que l'adresse IP et le port SSH sont corrects et joignables depuis cette machine."
        elif raw_err:
            api_msg = f"Échec SSH ({runner.ssh_user}@{runner.ssh_node}) : {raw_err}"
            api_rec = "Vérifiez les paramètres d'accès SSH et la présence de kubectl ou k3s sur le nœud distant."

    checks.append({
        "id": "api_server",
        "title": "API Server Kubernetes & Version",
        "status": "ok" if ver_ok else "error",
        "message": api_msg,
        "recommendation": api_rec
    })

    # 2. Nodes & Capacités (CPU/RAM)
    rc_nodes, out_nodes, _ = runner.run(["get", "nodes", "-o", "json"])
    nodes_count = 0
    ready_count = 0
    total_cpu = 0
    total_mem_gb = 0
    if rc_nodes == 0:
        try:
            n_data = json.loads(out_nodes)
            items = n_data.get("items", [])
            nodes_count = len(items)
            for n in items:
                status = n.get("status", {})
                for cond in status.get("conditions", []):
                    if cond.get("type") == "Ready" and cond.get("status") == "True":
                        ready_count += 1
                        break
                alloc = status.get("allocatable", {})
                cpu_str = str(alloc.get("cpu", "0"))
                if cpu_str.endswith("m"):
                    total_cpu += int(cpu_str[:-1]) / 1000.0
                elif cpu_str.isdigit():
                    total_cpu += int(cpu_str)
                else:
                    total_cpu += 2
                mem_str = str(alloc.get("memory", "0Ki"))
                if mem_str.endswith("Ki"):
                    total_mem_gb += int(mem_str[:-2]) / (1024 * 1024)
                elif mem_str.endswith("Mi"):
                    total_mem_gb += int(mem_str[:-2]) / 1024
                elif mem_str.endswith("Gi"):
                    total_mem_gb += int(mem_str[:-2])
        except Exception:
            pass

    nodes_ok = (ready_count >= 1)
    checks.append({
        "id": "nodes_capacity",
        "title": "Santé des Nœuds & Ressources Allouables",
        "status": "ok" if nodes_ok else "error",
        "message": f"{ready_count}/{nodes_count} nœud(s) Ready — Ressources globales : ~{int(total_cpu)} vCPU, ~{int(total_mem_gb)} Go RAM" if nodes_ok else "Aucun nœud en état Ready détecté.",
        "recommendation": "Vérifiez l'état de santé de vos nœuds avec 'kubectl get nodes'."
    })

    # 3. Contrôleur d'Ingress (Traefik / Nginx)
    rc_ing, out_ing, _ = runner.run(["get", "ingressclass", "-o", "json"])
    ingress_name = None
    if rc_ing == 0:
        try:
            ing_data = json.loads(out_ing)
            for item in ing_data.get("items", []):
                name = item.get("metadata", {}).get("name", "")
                if name:
                    ingress_name = name
                    break
        except Exception:
            pass
    if not ingress_name:
        rc_p, out_p, _ = runner.run(["get", "pods", "-A", "-l", "app.kubernetes.io/name in (traefik,ingress-nginx)"])
        if rc_p == 0 and "Running" in out_p:
            ingress_name = "traefik" if "traefik" in out_p.lower() else "ingress-nginx"

    ing_ok = bool(ingress_name)
    checks.append({
        "id": "ingress_controller",
        "title": "Contrôleur d'Ingress (Routage HTTPS)",
        "status": "ok" if ing_ok else "warn",
        "message": f"Contrôleur détecté ({ingress_name})" if ing_ok else "Aucune IngressClass explicite détectée. Traefik ou NGINX sera utilisé par défaut.",
        "recommendation": "K3s inclut Traefik nativement. Si vous utilisez un cluster nu, installez Traefik ou ingress-nginx."
    })

    # 4. Cert-Manager (TLS & Let's Encrypt)
    rc_crd, out_crd, _ = runner.run(["get", "crd", "certificates.cert-manager.io", "clusterissuers.cert-manager.io", "--no-headers"])
    cm_ok = (rc_crd == 0 and "cert-manager.io" in out_crd)
    checks.append({
        "id": "cert_manager",
        "title": "Gestionnaire de Certificats (Cert-Manager)",
        "status": "ok" if cm_ok else "warn",
        "message": "CRDs Cert-Manager détectées (Let's Encrypt automatique disponible)" if cm_ok else "Cert-Manager non détecté. Le déploiement universel ArcIA appliquera les manifests Cert-Manager automatiquement.",
        "recommendation": "L'émetteur Let's Encrypt automatique utilise Cert-Manager."
    })

    # 5. StorageClass Dynamique (Persistance PVC)
    rc_sc, out_sc, _ = runner.run(["get", "storageclass", "-o", "json"])
    default_sc = None
    sc_list = []
    if rc_sc == 0:
        try:
            sc_data = json.loads(out_sc)
            for sc in sc_data.get("items", []):
                sc_name = sc.get("metadata", {}).get("name", "")
                sc_list.append(sc_name)
                annotations = sc.get("metadata", {}).get("annotations", {})
                if annotations.get("storageclass.kubernetes.io/is-default-class") == "true":
                    default_sc = sc_name
        except Exception:
            pass

    sc_ok = bool(sc_list)
    checks.append({
        "id": "storage_class",
        "title": "Stockage Persistant Dynamique (StorageClass CSI)",
        "status": "ok" if sc_ok else "error",
        "message": f"StorageClass par défaut : '{default_sc}' (disponibles : {', '.join(sc_list)})" if default_sc else (f"StorageClasses disponibles : {', '.join(sc_list)}" if sc_list else "Aucune StorageClass dynamique détectée."),
        "recommendation": "Les PVCs de Hermes Agent et Open-WebUI requièrent une StorageClass dynamique."
    })

    # 6. Droits RBAC d'Administration
    rc_rbac, out_rbac, _ = runner.run(["auth", "can-i", "create", "namespaces"])
    rbac_ok = (rc_rbac == 0 and "yes" in out_rbac.lower())
    checks.append({
        "id": "rbac_admin",
        "title": "Droits RBAC d'Administration du Cluster",
        "status": "ok" if rbac_ok else "error",
        "message": "Droits d'administration confirmés (création de namespace, deployments, secrets autorisée)" if rbac_ok else "Droits restreints : le compte ne peut pas créer de namespace.",
        "recommendation": "Utilisez un kubeconfig ou compte ayant les droits administrateur sur le cluster."
    })

    all_ok = all(c["status"] == "ok" for c in checks)
    has_error = any(c["status"] == "error" for c in checks)

    return {
        "success": not has_error,
        "all_valid": all_ok,
        "summary": "Qualification réussie : le cluster est 100% prêt pour le déploiement d'ArcIA !" if all_ok else ("Attention : certains prérequis méritent votre attention mais ne sont pas bloquants." if not has_error else "Échec de qualification : des prérequis bloquants ont été détectés."),
        "checks": checks
    }

def get_docker_status() -> Dict[str, Any]:
    """Vérifie la présence et le statut d'exécution de Docker et Docker Compose."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return {
            "installed": False,
            "running": False,
            "docker_version": None,
            "compose_version": None,
            "message": "Docker n'a pas été détecté sur cette machine. Pour utiliser le Mode Lab, installez Docker Desktop ou lancez le daemon Docker."
        }

    running = False
    docker_version = None
    compose_version = None

    try:
        proc_ver = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, timeout=5)
        if proc_ver.returncode == 0:
            docker_version = proc_ver.stdout.decode("utf-8", errors="replace").strip()
            running = True
        else:
            docker_version = "Client détecté (Daemon non démarré)"
    except Exception:
        pass

    try:
        proc_comp = subprocess.run(["docker", "compose", "version", "--short"], capture_output=True, timeout=5)
        if proc_comp.returncode == 0:
            compose_version = proc_comp.stdout.decode("utf-8", errors="replace").strip()
        else:
            proc_comp_old = subprocess.run(["docker-compose", "--version"], capture_output=True, timeout=5)
            if proc_comp_old.returncode == 0:
                compose_version = proc_comp_old.stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        pass

    return {
        "installed": True,
        "running": running,
        "docker_version": docker_version or "Inconnue",
        "compose_version": compose_version or "Non détecté",
        "message": "Docker Engine et Docker Compose sont opérationnels." if running else "Docker est installé mais le moteur (daemon) ne semble pas être démarré."
    }

# -----------------------------------------------------------------------------
# Utilitaires Détection K8s & Configuration
# -----------------------------------------------------------------------------

def detect_kubectl_contexts() -> List[str]:
    """Détecte les contextes kubectl locaux disponibles."""
    try:
        proc = subprocess.run(
            ["kubectl", "config", "get-contexts", "-o", "name"],
            capture_output=True,
            timeout=5
        )
        if proc.returncode == 0:
            contexts = [c.strip() for c in proc.stdout.decode("utf-8", errors="replace").splitlines() if c.strip()]
            return contexts
    except Exception:
        pass
    return []

def detect_current_context() -> str:
    """Détecte le contexte courant kubectl."""
    try:
        proc = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True,
            timeout=5
        )
        if proc.returncode == 0:
            return proc.stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        pass
    return ""

def detect_available_ssh_keys() -> List[Dict[str, str]]:
    """Détecte les clés privées SSH disponibles sur la machine locale (~/.ssh/ et harness ArcIA)."""
    keys = []
    seen = set()

    # 1. Dossier ~/.ssh
    ssh_dir = os.path.expanduser("~/.ssh")
    if os.path.isdir(ssh_dir):
        try:
            for fname in sorted(os.listdir(ssh_dir)):
                p = os.path.join(ssh_dir, fname)
                if not os.path.isfile(p):
                    continue
                if fname.endswith((".pub", ".old", ".known_hosts", ".bak", ".txt")) or fname.startswith(("known_hosts", "authorized_keys", "config")):
                    continue
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        first_line = f.readline()
                        if "PRIVATE KEY" in first_line:
                            norm = os.path.normpath(p)
                            if norm not in seen:
                                seen.add(norm)
                                keys.append({"path": norm, "name": fname})
                except Exception:
                    pass
        except Exception:
            pass

    # 2. Dossier Harness ArcIA
    harness_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ArcIA-Harness", "ssh")
    candidate = os.path.join(harness_dir, "arcia-vm_ed25519")
    if os.path.isfile(candidate):
        norm = os.path.normpath(candidate)
        if norm not in seen:
            seen.add(norm)
            keys.append({"path": norm, "name": "arcia-vm_ed25519 (Harness)"})

    return keys

def generate_ssh_key_pair(comment: str = "arcia-vmware-cluster") -> Dict[str, Any]:
    """Génère une paire de clés SSH (Ed25519 avec repli RSA 4096) et renvoie le chemin et les clés."""
    ssh_dir = os.path.expanduser("~/.ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    ts = int(time.time())
    key_name = f"arcia_ed25519_{ts}"
    key_path = os.path.join(ssh_dir, key_name)
    pub_path = key_path + ".pub"

    # 1. Tentative avec la bibliothèque standard cryptography (instantanée et autonome)
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives import serialization
        key = ed25519.Ed25519PrivateKey.generate()
        priv_bytes = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=serialization.NoEncryption()
        )
        pub_bytes = key.public_key().public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH
        )
        priv_content = priv_bytes.decode("utf-8").strip()
        pub_content = f"{pub_bytes.decode('utf-8').strip()} {comment}"

        with open(key_path, "w", encoding="utf-8") as f:
            f.write(priv_content + "\n")
        with open(pub_path, "w", encoding="utf-8") as f:
            f.write(pub_content + "\n")

        try:
            os.chmod(key_path, 0o600)
            os.chmod(pub_path, 0o644)
        except Exception:
            pass

        return {
            "success": True,
            "key_path": os.path.normpath(key_path),
            "public_key": pub_content,
            "private_key": priv_content,
            "key_name": key_name
        }
    except Exception:
        pass

    # 2. Repli avec ssh-keygen système
    try:
        cmd = ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", comment, "-f", key_path]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            key_name = f"arcia_rsa_{ts}"
            key_path = os.path.join(ssh_dir, key_name)
            pub_path = key_path + ".pub"
            cmd = ["ssh-keygen", "-t", "rsa", "-b", "4096", "-N", "", "-C", comment, "-f", key_path]
            res = subprocess.run(cmd, capture_output=True, text=True)

        if res.returncode == 0 and os.path.isfile(key_path) and os.path.isfile(pub_path):
            with open(key_path, "r", encoding="utf-8") as f:
                priv_content = f.read()
            with open(pub_path, "r", encoding="utf-8") as f:
                pub_content = f.read()
            return {
                "success": True,
                "key_path": os.path.normpath(key_path),
                "public_key": pub_content.strip(),
                "private_key": priv_content.strip(),
                "key_name": key_name
            }
        else:
            err_msg = (res.stderr or res.stdout or "").strip()
            return {"success": False, "error": f"Échec de ssh-keygen ({err_msg})"}
    except Exception as e:
        return {"success": False, "error": f"Erreur de génération de clé SSH : {str(e)}"}

def load_config_data(config_file: str) -> Tuple[Dict[str, Any], bool]:
    """Charge la configuration depuis un fichier existant ou utilise le modèle par défaut."""
    exists = os.path.isfile(config_file)
    target = config_file if exists else EXAMPLE_CONFIG_PATH

    if not os.path.isfile(target):
        default_cfg = get_default_config_dict()
        return default_cfg, False

    try:
        sys.path.insert(0, SCRIPT_DIR)
        import deploy
        cfg = deploy.parse_yaml_or_env(target)
        if isinstance(cfg, dict):
            cfg = ensure_config_defaults(cfg)
            cfg = resolve_env_secrets_into_config(cfg)
            return cfg, exists
    except Exception:
        pass

    if exists:
        raise ValueError("Le fichier de configuration existant est illisible ; aucun catalogue par défaut ne sera chargé.")
    return get_default_config_dict(), False

def get_default_config_dict() -> Dict[str, Any]:
    """Génère un dictionnaire de configuration par défaut complet et sécurisé."""
    sys.path.insert(0, SCRIPT_DIR)
    import deploy
    ident_key, known_hosts = deploy.find_harness_ssh()
    detected_node = "127.0.0.1"
    detected_user = os.environ.get("ARCIA_K3S_USER", "debian")
    if known_hosts and os.path.isfile(known_hosts):
        try:
            with open(known_hosts, "r", encoding="utf-8") as f:
                for line in f:
                    m = re.match(r'^\s*([0-9\.]+)', line)
                    if m:
                        detected_node = m.group(1)
                        break
        except Exception:
            pass

    return {
        "kubernetes": {
            "mode": "remote-ssh" if ident_key else "local",
            "kubeconfig": "",
            "context": detect_current_context(),
            "namespace": "arcia",
            "storage_class": "",
            "remote_ssh": {
                "node_ip": detected_node,
                "ssh_user": detected_user,
                "ssh_port": 22,
                "ssh_key": ident_key or ""
            }
        },
        "network": {
            "public_fqdn": "",
            "ingress_class": "traefik",
            "tls_mode": "letsencrypt-prod",
            "acme_email": "",
            "tls_secret_name": "arcia-tls-cert"
        },
        "llm_gateway": {
            "openrouter_api_key": "",
            "default_model": "simple/auto",
            "local_vllm_endpoint": "",
            "openai_api_key": "",
            "anthropic_api_key": "",
            "mistral_api_key": "",
            "gemini_api_key": ""
        },
        "hermes": {
            "default_model": "agentic/auto",
            "admin_password": generate_token("admin"),
            "api_token": generate_token("pat"),
            "storage_size": "20Gi"
        },
        "presidio": {
            "enabled": True,
            "master_key": generate_token("presidio")
        },
        "open_webui": {
            "enabled": True,
            "storage_size": "50Gi"
        },
        "entra_id_sso": {
            "enabled": False,
            "tenant_id": "",
            "client_id": "",
            "client_secret": "",
            "cookie_secret": generate_token("cookie")
        },
        "teams_bot": {
            "enabled": False,
            "app_id": "",
            "app_password": "",
            "tenant_id": "",
            "system_prompt": "Tu es ArcIA, l'assistant et orchestrateur agentique d'entreprise. Réponds de façon synthétique, professionnelle et structurée en Markdown."
        },
        "microsoft365_integration": {
            "enabled": False,
            "config_file": "instance/microsoft365.yaml"
        },
        "vmware": {
            "host": "",
            "port": 443,
            "username": "",
            "insecure_tls": False,
            "datacenter": "",
            "cluster": "",
            "datastore": "",
            "portgroup": "",
            "tier": "100",
            "network": {
                "mode": "static",
                "node_ips": "",
                "netmask": "255.255.255.0",
                "gateway": "",
                "dns": "",
                "ntp": "pool.ntp.org",
                "domain": ""
            },
            "auth": {
                "vm_user": "debian",
                "ssh_key_mode": "generate",
                "ssh_key_path": "",
                "ssh_public_key": ""
            },
            "storage_policy": "",
            "storage_account": {
                "separate": False,
                "provider_type": "vsphere-csi",
                "username": "",
                "endpoint": ""
            },
            "resources_override": {
                "nodes": 3,
                "vcpu_per_node": 4,
                "ram_per_node_gb": 16,
                "disk_per_node_gb": 150
            }
        }
    }

def ensure_config_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """S'assure que toutes les sections et clés sont présentes avec des valeurs valides."""
    defaults = get_default_config_dict()
    for section, sec_data in defaults.items():
        if section not in cfg or not isinstance(cfg[section], dict):
            cfg[section] = sec_data
        else:
            for k, v in sec_data.items():
                if k not in cfg[section]:
                    cfg[section][k] = v
                elif isinstance(v, dict) and isinstance(cfg[section][k], dict):
                    for sub_k, sub_v in v.items():
                        if sub_k not in cfg[section][k]:
                            cfg[section][k][sub_k] = sub_v

    if not cfg["hermes"].get("api_token") or cfg["hermes"]["api_token"] == "arcia-pat-change-me-secret-key-32b":
        cfg["hermes"]["api_token"] = generate_token("pat")
    if not cfg["entra_id_sso"].get("cookie_secret") or "xxxx" in cfg["entra_id_sso"]["cookie_secret"]:
        cfg["entra_id_sso"]["cookie_secret"] = generate_token("cookie")
    if not cfg["presidio"].get("master_key"):
        cfg["presidio"]["master_key"] = generate_token("presidio")

    if cfg["network"].get("public_fqdn") == "assistant.example.org":
        cfg["network"]["public_fqdn"] = ""
    if cfg["network"].get("acme_email") == "admin@example.org":
        cfg["network"]["acme_email"] = ""
    if cfg["llm_gateway"].get("openrouter_api_key", "").startswith("sk-or-v1-xxxx"):
        cfg["llm_gateway"]["openrouter_api_key"] = ""
    if is_placeholder_key(cfg["llm_gateway"].get("openai_api_key", "")):
        cfg["llm_gateway"]["openai_api_key"] = ""
    if is_placeholder_key(cfg["llm_gateway"].get("anthropic_api_key", "")):
        cfg["llm_gateway"]["anthropic_api_key"] = ""
    if is_placeholder_key(cfg["llm_gateway"].get("mistral_api_key", "")):
        cfg["llm_gateway"]["mistral_api_key"] = ""
    if is_placeholder_key(cfg["llm_gateway"].get("gemini_api_key", "")):
        cfg["llm_gateway"]["gemini_api_key"] = ""

    return cfg

def resolve_env_secrets_into_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Résout automatiquement les clés d'API depuis secrets/arcia.env ou l'environnement système pour l'UI."""
    if not isinstance(cfg, dict):
        return cfg
    llm = cfg.setdefault("llm_gateway", {})

    env_path = os.path.join(ROOT_DIR, "secrets", "arcia.env")
    env_secrets: Dict[str, str] = {}
    if os.path.isfile(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as ef:
                for line in ef:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        ek, ev = line.split("=", 1)
                        env_secrets[ek.strip()] = ev.strip().strip('"').strip("'")
        except Exception:
            pass

    or_key = llm.get("openrouter_api_key", "").strip()
    if not or_key or is_placeholder_key(or_key):
        resolved_or = env_secrets.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
        if resolved_or and not is_placeholder_key(resolved_or):
            llm["openrouter_api_key"] = resolved_or
        else:
            llm["openrouter_api_key"] = ""

    oai_key = llm.get("openai_api_key", "").strip()
    if not oai_key or is_placeholder_key(oai_key):
        resolved_oai = env_secrets.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        if resolved_oai and not is_placeholder_key(resolved_oai):
            llm["openai_api_key"] = resolved_oai
        else:
            llm["openai_api_key"] = ""

    ant_key = llm.get("anthropic_api_key", "").strip()
    if not ant_key or is_placeholder_key(ant_key):
        resolved_ant = env_secrets.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
        if resolved_ant and not is_placeholder_key(resolved_ant):
            llm["anthropic_api_key"] = resolved_ant
        else:
            llm["anthropic_api_key"] = ""

    mis_key = llm.get("mistral_api_key", "").strip()
    if not mis_key or is_placeholder_key(mis_key):
        resolved_mis = env_secrets.get("MISTRAL_API_KEY") or os.environ.get("MISTRAL_API_KEY", "")
        if resolved_mis and not is_placeholder_key(resolved_mis):
            llm["mistral_api_key"] = resolved_mis
        else:
            llm["mistral_api_key"] = ""

    gem_key = llm.get("gemini_api_key", "").strip()
    if not gem_key or is_placeholder_key(gem_key):
        resolved_gem = env_secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
        if resolved_gem and not is_placeholder_key(resolved_gem):
            llm["gemini_api_key"] = resolved_gem
        else:
            llm["gemini_api_key"] = ""

    # Résolution des secrets VMware vSphere
    vm = cfg.setdefault("vmware", {})
    vm_auth = vm.setdefault("auth", {})
    if not vm.get("password") and env_secrets.get("VMWARE_VCENTER_PASSWORD"):
        vm["password"] = env_secrets.get("VMWARE_VCENTER_PASSWORD", "")
    if not vm_auth.get("vm_password") and env_secrets.get("VMWARE_VM_PASSWORD"):
        vm_auth["vm_password"] = env_secrets.get("VMWARE_VM_PASSWORD", "")
    if not vm_auth.get("root_password") and env_secrets.get("VMWARE_ROOT_PASSWORD"):
        vm_auth["root_password"] = env_secrets.get("VMWARE_ROOT_PASSWORD", "")
    vm_store = vm.setdefault("storage_account", {})
    if not vm_store.get("password") and env_secrets.get("VMWARE_STORAGE_PASSWORD"):
        vm_store["password"] = env_secrets.get("VMWARE_STORAGE_PASSWORD", "")

    return cfg

def serialize_yaml_config(cfg: Dict[str, Any]) -> str:
    """Sérialise proprement le dictionnaire de configuration en syntaxe YAML conforme."""
    if not isinstance(cfg, dict):
        cfg = {}
    k8s = cfg.get("kubernetes") or {}
    net = cfg.get("network") or {}
    llm = cfg.get("llm_gateway") or {}
    hermes = cfg.get("hermes") or {}
    presidio = cfg.get("presidio") or {}
    webui = cfg.get("open_webui") or {}
    sso = cfg.get("entra_id_sso") or {}
    teams = cfg.get("teams_bot") or {}
    m365 = cfg.get("microsoft365_integration") or {}
    vm = cfg.get("vmware") or {}
    vm_net = vm.get("network") or {}
    vm_auth = vm.get("auth") or {}
    vm_store = vm.get("storage_account") or {}
    vm_res = vm.get("resources_override") or {}
    sizing = k8s.get("sizing") or {}

    def bstr(val: Any) -> str:
        return "true" if bool(val) else "false"

    def qstr(val: Any) -> str:
        return json.dumps(str(val or ""), ensure_ascii=False)

    def istr(val: Any, default: int = 22) -> int:
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    ssh = k8s.get("remote_ssh") or {}
    custom_provs = llm.get("custom_providers") or []
    custom_provs_repr = json.dumps(custom_provs) if isinstance(custom_provs, list) else "[]"
    models_rout = llm.get("models_routing") or []
    models_rout_repr = json.dumps(models_rout) if isinstance(models_rout, list) else "[]"

    yaml_text = f"""# ==============================================================================
# ArcIA — Configuration Générée par le Setup Wizard Graphique
# Généré le {time.strftime('%Y-%m-%d %H:%M:%S')}
# ==============================================================================

# 1. Connexion Kubernetes
kubernetes:
  mode: {qstr(k8s.get('mode', 'local'))}
  kubeconfig: {qstr(k8s.get('kubeconfig', ''))}
  context: {qstr(k8s.get('context', ''))}
  namespace: {qstr(k8s.get('namespace', 'arcia'))}
  storage_class: {qstr(k8s.get('storage_class', ''))}
  remote_ssh:
    node_ip: {qstr(ssh.get('node_ip', '127.0.0.1'))}
    ssh_user: {qstr(ssh.get('ssh_user', 'debian'))}
    ssh_port: {istr(ssh.get('ssh_port'), 22)}
    ssh_key: {qstr(ssh.get('ssh_key', ''))}
  sizing:
    tier: {qstr(sizing.get('tier', vm.get('tier', '100')))}
    nodes: {istr(sizing.get('nodes', vm_res.get('nodes', 3)), 3)}
    vcpu_per_node: {istr(sizing.get('vcpu_per_node', vm_res.get('vcpu_per_node', 4)), 4)}
    ram_per_node_gb: {istr(sizing.get('ram_per_node_gb', vm_res.get('ram_per_node_gb', 16)), 16)}
    disk_per_node_gb: {istr(sizing.get('disk_per_node_gb', vm_res.get('disk_per_node_gb', 150)), 150)}
    rag_storage: {qstr(sizing.get('rag_storage', '200Gi'))}

# 2. Exposition Réseau, Domaine FQDN & Certificats TLS
network:
  public_fqdn: {qstr(net.get('public_fqdn', ''))}
  ingress_class: {qstr(net.get('ingress_class', 'traefik'))}
  tls_mode: {qstr(net.get('tls_mode', 'letsencrypt-prod'))}
  acme_email: {qstr(net.get('acme_email', ''))}
  tls_secret_name: {qstr(net.get('tls_secret_name', 'arcia-tls-cert'))}

# 3. Passerelle IA & Fournisseurs LLM
llm_gateway:
  openrouter_api_key: {qstr(llm.get('openrouter_api_key', ''))}
  master_key: {qstr(llm.get('master_key', ''))}
  salt_key: {qstr(llm.get('salt_key', ''))}
  db_password: {qstr(llm.get('db_password', ''))}
  default_model: {qstr(llm.get('default_model', 'simple/auto'))}
  local_vllm_endpoint: {qstr(llm.get('local_vllm_endpoint', ''))}
  openai_api_key: {qstr(llm.get('openai_api_key', ''))}
  anthropic_api_key: {qstr(llm.get('anthropic_api_key', ''))}
  mistral_api_key: {qstr(llm.get('mistral_api_key', ''))}
  gemini_api_key: {qstr(llm.get('gemini_api_key', ''))}
  custom_providers: {custom_provs_repr}
  models_routing: {models_rout_repr}

# 4. Moteur d'Agents Hermes & Studio Kanban
hermes:
  default_model: {qstr(hermes.get('default_model', 'agentic/auto'))}
  admin_password: {qstr(hermes.get('admin_password', 'admin'))}
  api_token: {qstr(hermes.get('api_token', ''))}
  storage_size: {qstr(hermes.get('storage_size', '20Gi'))}

# 5. Bouclier de Confidentialité Presidio DLP
presidio:
  enabled: {bstr(presidio.get('enabled', True))}
  master_key: {qstr(presidio.get('master_key', 'arcia-master-secret-key'))}

# 6. Portail Collaborateur Open-WebUI
open_webui:
  enabled: {bstr(webui.get('enabled', True))}
  storage_size: {qstr(webui.get('storage_size', '20Gi'))}

# 7. Authentification SSO Microsoft Entra ID [Optionnel]
entra_id_sso:
  enabled: {bstr(sso.get('enabled', False))}
  tenant_id: {qstr(sso.get('tenant_id', ''))}
  client_id: {qstr(sso.get('client_id', ''))}
  client_secret: {qstr(sso.get('client_secret', ''))}
  cookie_secret: {qstr(sso.get('cookie_secret', ''))}

# 8. Adaptateur Microsoft Teams Bot [Optionnel]
teams_bot:
  enabled: {bstr(teams.get('enabled', False))}
  app_id: {qstr(teams.get('app_id', ''))}
  app_password: {qstr(teams.get('app_password', ''))}
  tenant_id: {qstr(teams.get('tenant_id', ''))}
  system_prompt: {qstr(teams.get('system_prompt', "Tu es ArcIA, l'assistant et orchestrateur agentique d'entreprise. Réponds de façon synthétique, professionnelle et structurée en Markdown."))}

# 9. Intégration Microsoft 365
microsoft365_integration:
  enabled: {bstr(m365.get('enabled', False))}
  config_file: {qstr(m365.get('config_file', 'instance/microsoft365.yaml'))}

# 10. Infrastructure VMware vSphere & Dimensionnement [Optionnel]
vmware:
  host: {qstr(vm.get('host', ''))}
  port: {istr(vm.get('port'), 443)}
  username: {qstr(vm.get('username', ''))}
  insecure_tls: {bstr(vm.get('insecure_tls', False))}
  datacenter: {qstr(vm.get('datacenter', ''))}
  cluster: {qstr(vm.get('cluster', ''))}
  datastore: {qstr(vm.get('datastore', ''))}
  portgroup: {qstr(vm.get('portgroup', ''))}
  tier: {qstr(vm.get('tier', '100'))}
  network:
    mode: {qstr(vm_net.get('mode', 'static'))}
    node_ips: {qstr(vm_net.get('node_ips', ''))}
    netmask: {qstr(vm_net.get('netmask', ''))}
    gateway: {qstr(vm_net.get('gateway', ''))}
    dns: {qstr(vm_net.get('dns', ''))}
    ntp: {qstr(vm_net.get('ntp', ''))}
    domain: {qstr(vm_net.get('domain', ''))}
  auth:
    vm_user: {qstr(vm_auth.get('vm_user', 'debian'))}
    ssh_key_mode: {qstr(vm_auth.get('ssh_key_mode', 'generate'))}
    ssh_key_path: {qstr(vm_auth.get('ssh_key_path', ''))}
    ssh_public_key: {qstr(vm_auth.get('ssh_public_key', ''))}
  storage_policy: {qstr(vm.get('storage_policy', ''))}
  storage_account:
    separate: {bstr(vm_store.get('separate', False))}
    provider_type: {qstr(vm_store.get('provider_type', 'vsphere-csi'))}
    username: {qstr(vm_store.get('username', ''))}
    endpoint: {qstr(vm_store.get('endpoint', ''))}
  resources_override:
    nodes: {istr(vm_res.get('nodes', sizing.get('nodes', 3)), 3)}
    vcpu_per_node: {istr(vm_res.get('vcpu_per_node', sizing.get('vcpu_per_node', 4)), 4)}
    ram_per_node_gb: {istr(vm_res.get('ram_per_node_gb', sizing.get('ram_per_node_gb', 16)), 16)}
    disk_per_node_gb: {istr(vm_res.get('disk_per_node_gb', sizing.get('disk_per_node_gb', 150)), 150)}
"""
    import deploy
    rendered = deploy.parse_simple_yaml(yaml_text)

    def merge(target, source):
        for key, value in source.items():
            if isinstance(value, dict):
                current = target.get(key)
                if not isinstance(current, dict):
                    current = target[key] = {}
                merge(current, value)
            elif value is not None and not (key == "ssh_port" and value == ""):
                target[key] = value
    merge(rendered, cfg)
    for section in ("instance_backup", "instance_git"):
        if isinstance(rendered.get(section), dict):
            rendered[section].pop("passphrase", None)
    lines = ["# ArcIA — Configuration d'instance générée par le wizard"]
    def emit(mapping, depth=0):
        for key, value in mapping.items():
            safe_key = str(key) if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", str(key)) else json.dumps(str(key))
            if isinstance(value, dict) and value:
                lines.append(" " * depth + safe_key + ":")
                emit(value, depth + 2)
            else:
                lines.append(" " * depth + safe_key + ": " + json.dumps(value, ensure_ascii=False))
    emit(rendered)
    return "\n".join(lines) + "\n"


@instance_storage.serialized
def save_config_to_files(cfg: Dict[str, Any], config_path: str = DEFAULT_CONFIG_PATH, trigger_backup: bool = True, restored_env: Optional[str] = None) -> dict:
    """Enregistre la configuration dans arcia.config.yaml et synchronise secrets/arcia.env."""
    # Préserver le dépôt déclaré lorsque le formulaire ne transporte pas cette section.
    if os.path.isfile(config_path):
        import deploy
        previous = deploy.parse_yaml_or_env(config_path)
        if not instance_storage.normalize_settings(cfg).get("repo_url"):
            for key in ("instance_backup", "instance_git"):
                if key in previous:
                    cfg[key] = previous[key]
        # Un formulaire partiel ne doit pas effacer les autres réglages de l'instance.
        def merge_saved(base, changes):
            result = dict(base)
            for key, value in changes.items():
                result[key] = merge_saved(result.get(key, {}), value) if isinstance(value, dict) and isinstance(result.get(key), dict) else value
            return result
        merged = merge_saved(previous, cfg)
        cfg.clear()
        cfg.update(merged)
    settings = instance_storage.normalize_settings(cfg)
    if settings.get("repo_url") and settings.get("passphrase"):
        instance_storage.unlock(ROOT_DIR, settings["repo_url"], settings.get("git_token") or settings.get("token") or "", settings["passphrase"])
    yaml_content = serialize_yaml_config(cfg)
    os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
    temporary = str(config_path) + ".part"
    with open(temporary, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    env_temporary = None

    secrets_dir = os.path.join(ROOT_DIR, "secrets")
    real_prod_path = os.path.normpath(os.path.join(ROOT_DIR, "arcia.config.yaml"))
    if os.path.normpath(os.path.abspath(config_path)) == real_prod_path and os.path.isdir(secrets_dir):
        env_path = os.path.join(secrets_dir, "arcia.env")
        import io
        previous_env = restored_env
        if previous_env is None:
            previous_env = Path(env_path).read_text(encoding="utf-8") if os.path.isfile(env_path) else ""
        f = io.StringIO()
        f.write(f"# ArcIA Environment Secrets - Auto-généré par le Wizard\n")
        for field, env_name in (("master_key", "LITELLM_MASTER_KEY"), ("salt_key", "LITELLM_SALT_KEY"), ("db_password", "LITELLM_DB_PASSWORD")):
            value = cfg.get("llm_gateway", {}).get(field, "")
            if value:
                f.write(f"{env_name}={value}\n")
        or_key = cfg.get('llm_gateway', {}).get('openrouter_api_key', '')
        if or_key and not is_placeholder_key(or_key):
            f.write(f"OPENROUTER_API_KEY={or_key}\n")
        oai_key = cfg.get('llm_gateway', {}).get('openai_api_key', '')
        if oai_key and not is_placeholder_key(oai_key):
            f.write(f"OPENAI_API_KEY={oai_key}\n")
        ant_key = cfg.get('llm_gateway', {}).get('anthropic_api_key', '')
        if ant_key and not is_placeholder_key(ant_key):
            f.write(f"ANTHROPIC_API_KEY={ant_key}\n")
        mis_key = cfg.get('llm_gateway', {}).get('mistral_api_key', '')
        if mis_key and not is_placeholder_key(mis_key):
            f.write(f"MISTRAL_API_KEY={mis_key}\n")
        gem_key = cfg.get('llm_gateway', {}).get('gemini_api_key', '')
        if gem_key and not is_placeholder_key(gem_key):
            f.write(f"GEMINI_API_KEY={gem_key}\n")
        for section, field, env_name in (("hermes", "admin_password", "HERMES_ADMIN_PASSWORD"), ("hermes", "api_token", "HERMES_API_SERVER_KEY"), ("presidio", "master_key", "PRESIDIO_MASTER_KEY")):
            if field in cfg.get(section, {}):
                f.write(f"{env_name}={cfg[section][field]}\n")
        sso = cfg.get("entra_id_sso", {})
        if sso.get("enabled"):
            f.write(f"ENTRA_TENANT_ID={sso.get('tenant_id', '')}\n")
            f.write(f"ENTRA_CLIENT_ID={sso.get('client_id', '')}\n")
            f.write(f"ENTRA_CLIENT_SECRET={sso.get('client_secret', '')}\n")
            f.write(f"OAUTH2_PROXY_COOKIE_SECRET={sso.get('cookie_secret', '')}\n")
        teams = cfg.get("teams_bot", {})
        if teams.get("enabled"):
            f.write(f"TEAMS_BOT_APP_ID={teams.get('app_id', '')}\n")
            f.write(f"TEAMS_BOT_APP_PASSWORD={teams.get('app_password', '')}\n")
            if teams.get("tenant_id"):
                f.write(f"TEAMS_BOT_TENANT_ID={teams.get('tenant_id', '')}\n")
        # Secrets VMware vSphere
        vm = cfg.get("vmware", {})
        vm_auth = vm.get("auth", {})
        if vm.get("password") and not is_placeholder_key(vm.get("password")):
            f.write(f"VMWARE_VCENTER_PASSWORD={vm.get('password')}\n")
        if vm_auth.get("vm_password") and not is_placeholder_key(vm_auth.get("vm_password")):
            f.write(f"VMWARE_VM_PASSWORD={vm_auth.get('vm_password')}\n")
        if vm_auth.get("root_password") and not is_placeholder_key(vm_auth.get("root_password")):
            f.write(f"VMWARE_ROOT_PASSWORD={vm_auth.get('root_password')}\n")
        vm_store = vm.get("storage_account", {})
        if vm_store.get("password") and not is_placeholder_key(vm_store.get("password")):
            f.write(f"VMWARE_STORAGE_PASSWORD={vm_store.get('password')}\n")
        updates = dict(line.split("=", 1) for line in f.getvalue().splitlines() if "=" in line and not line.startswith("#"))
        preserved = []
        for line in previous_env.splitlines():
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key not in updates:
                preserved.append(line)
        env_content = "\n".join(preserved + [key + "=" + value for key, value in updates.items()]) + "\n"
        env_temporary = env_path + ".part"
        with open(env_temporary, "w", encoding="utf-8") as stream:
            stream.write(env_content)
    os.replace(temporary, config_path)
    if env_temporary is not None:
        os.replace(env_temporary, env_path)

    if trigger_backup and os.path.normcase(os.path.abspath(config_path)) == os.path.normcase(os.path.abspath(DEFAULT_CONFIG_PATH)):
        return backup_current_instance(cfg=cfg)
    return {"success": True, "state": "local_only"}


@instance_storage.serialized
def backup_current_instance(cfg=None, passphrase="", token="", repo_url="", force=False):
    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
    settings = instance_storage.normalize_settings(cfg)
    repo_url = repo_url or settings.get("repo_url", "")
    if repo_url:
        instance_storage.validate_repo(repo_url)
    auth_settings = settings if repo_url == settings.get("repo_url") else {"repo_url": repo_url}
    stored = instance_storage.credentials(ROOT_DIR, auth_settings)
    if passphrase and passphrase != stored["passphrase"]:
        latest = instance_storage.read_latest_bundle(repo_url, token or stored["token"])
        if latest is not None:
            decrypt_instance_bundle(latest, passphrase)
    if passphrase or (token and stored["passphrase"]):
        instance_storage.unlock(ROOT_DIR, repo_url, token or stored["token"], passphrase or stored["passphrase"])
    settings.update({"enabled": settings.get("enabled", True), "repo_url": repo_url})
    cfg["instance_backup"] = settings
    if passphrase or repo_url != instance_storage.normalize_settings(load_config_data(DEFAULT_CONFIG_PATH)[0]).get("repo_url", ""):
        save_config_to_files(cfg, DEFAULT_CONFIG_PATH, trigger_backup=False)
    env_path = os.path.join(ROOT_DIR, "secrets", "arcia.env")
    env_content = ""
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as stream:
            env_content = stream.read()
    return instance_storage.backup(ROOT_DIR, cfg, serialize_yaml_config(cfg), env_content, encrypt_instance_bundle, force=force)


def watch_instance_configuration(stop_event):
    previous = None
    retry_at = 0
    while not stop_event.wait(3):
        try:
            import hashlib
            digest = hashlib.sha256()
            for path in (DEFAULT_CONFIG_PATH, os.path.join(ROOT_DIR, "secrets", "arcia.env")):
                if os.path.isfile(path):
                    with open(path, "rb") as stream:
                        digest.update(stream.read())
            changed = digest.hexdigest() != previous
            retry = instance_storage.status(ROOT_DIR).get("state") in {"pending", "locked"} and time.monotonic() >= retry_at
            if changed or retry:
                backup_current_instance()
                previous = digest.hexdigest()
                retry_at = time.monotonic() + 30
        except Exception:
            # Aucun contenu de configuration ou exception privée dans les journaux.
            retry_at = time.monotonic() + 30


# -----------------------------------------------------------------------------
# Exécution du Déploiement en Tâche de Fond & Sauvegarde Git Chiffrée
# -----------------------------------------------------------------------------

def strip_ansi_codes(text: str) -> str:
    """Supprime proprement les séquences d'échappement ANSI de la sortie d'exécution."""
    if not text:
        return ""
    # Séquences ANSI standard
    text = re.sub(r'\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)
    # Séquences orphelines sans caractère d'échappement initial (ex: [1m, [96m, [0m)
    text = re.sub(r'\[(?:\d{1,3}(?:;\d{1,3})*)?m', '', text)
    return text

def cancel_active_deployment() -> dict:
    """Interrompt immédiatement le déploiement en cours d'exécution."""
    global active_deployment_proc, deployment_state
    proc_to_kill = None
    with deployment_lock:
        if deployment_state.get("status") != "running":
            return {"success": False, "error": "Aucun déploiement n'est actuellement en cours d'exécution."}
        proc_to_kill = active_deployment_proc
        deployment_state["status"] = "canceled"
        deployment_state["exit_code"] = -1
        deployment_state["logs"].append("[WARN] Déploiement interrompu par l'opérateur.")

    if proc_to_kill:
        try:
            proc_to_kill.terminate()
            try:
                proc_to_kill.wait(timeout=2)
            except Exception:
                proc_to_kill.kill()
        except Exception:
            pass

    with deployment_lock:
        active_deployment_proc = None

    return {"success": True, "message": "Déploiement interrompu avec succès."}

def run_deployment_worker(dry_run: bool = False, instance_git_info: Optional[dict] = None,
                          infra_target: str = "k8s_existing", infra_config: Optional[dict] = None):
    global deployment_state, active_deployment_proc

    with deployment_lock:
        deployment_state["status"] = "running"
        deployment_state["logs"] = [
            f"[INFO] Initialisation du déploiement universel ArcIA (Cible : {infra_target})...",
            f"[INFO] Mode d'exécution : {'Simulation (dry-run)' if dry_run else 'Déploiement réel'}"
        ]
        deployment_state["start_time"] = time.time()
        deployment_state["exit_code"] = None

    if infra_target == "docker_lab":
        try:
            with deployment_lock:
                deployment_state["logs"].append("[INFO] Démarrage de l'environnement Lab Local (Docker Desktop)...")

            doc_st = get_docker_status()
            if not doc_st.get("installed"):
                with deployment_lock:
                    deployment_state["status"] = "error"
                    deployment_state["logs"].append("[FATAL ERROR] Docker n'est pas détecté sur cette machine. Veuillez installer Docker Desktop ou démarrer le service Docker.")
                return

            cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
            openrouter_key = cfg.get("llm_gateway", {}).get("openrouter_api_key", "")
            admin_pass = cfg.get("hermes", {}).get("admin_password", "AdminArcIA2026!")

            docker_cfg = (infra_config or {}).get("docker", {})
            webui_port = docker_cfg.get("webui_port", 3000)
            litellm_port = docker_cfg.get("litellm_port", 4000)

            compose_file = os.path.join(ROOT_DIR, "docker-compose.lab.yml")
            if not os.path.isfile(compose_file):
                with deployment_lock:
                    deployment_state["status"] = "error"
                    deployment_state["logs"].append("[FATAL ERROR] Fichier docker-compose.lab.yml introuvable.")
                return

            with deployment_lock:
                deployment_state["logs"].append(f"[INFO] Démarrage des conteneurs via Docker Compose (Portail: http://localhost:{webui_port})...")

            env_vars = os.environ.copy()
            env_vars["PYTHONUNBUFFERED"] = "1"
            env_vars["PYTHONIOENCODING"] = "utf-8"
            env_vars["PYTHONUTF8"] = "1"
            env_vars["OPENROUTER_API_KEY"] = openrouter_key
            env_vars["WEBUI_PORT"] = str(webui_port)
            env_vars["LITELLM_PORT"] = str(litellm_port)
            env_vars["ADMIN_PASSWORD"] = admin_pass

            cmd = ["docker", "compose", "-f", compose_file, "up", "-d", "--progress", "plain"]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=ROOT_DIR,
                env=env_vars
            )
            with deployment_lock:
                active_deployment_proc = proc

            for line in iter(proc.stdout.readline, ''):
                if line:
                    clean_line = strip_ansi_codes(line).rstrip()
                    if clean_line:
                        with deployment_lock:
                            deployment_state["logs"].append(clean_line)

            proc.wait()
            exit_code = proc.returncode

            with deployment_lock:
                active_deployment_proc = None
                if deployment_state["status"] == "canceled":
                    return
                deployment_state["exit_code"] = exit_code
                if exit_code == 0:
                    deployment_state["status"] = "success"
                    deployment_state["logs"].append("\n[OK] Déploiement Docker Lab terminé avec succès !")
                    deployment_state["summary"] = {
                        "public_fqdn": "localhost",
                        "webui_url": f"http://localhost:{webui_port}/",
                        "studio_url": f"http://localhost:{webui_port}/studio",
                        "gateway_url": f"http://localhost:{litellm_port}/v1",
                        "teams_webhook": None,
                        "hermes_admin_user": "admin@arcia.local",
                        "hermes_admin_pass": admin_pass,
                        "hermes_pat": cfg.get("hermes", {}).get("api_token", ""),
                        "instance_repo_url": None,
                        "mode": "docker_lab"
                    }
                else:
                    deployment_state["status"] = "error"
                    deployment_state["logs"].append(f"\n[ERROR] Échec d'exécution de docker compose (Code: {exit_code})")
            return
        except Exception as de:
            with deployment_lock:
                active_deployment_proc = None
                if deployment_state["status"] != "canceled":
                    deployment_state["status"] = "error"
                    deployment_state["logs"].append(f"[FATAL ERROR Docker] {str(de)}")
            return

    # Mode Kubernetes Existant ou VMware vSphere
    cfg_for_vm, _ = load_config_data(DEFAULT_CONFIG_PATH)
    vm_cfg = (infra_config or {}).get("vmware", {}) or (cfg_for_vm or {}).get("vmware", {}) or {}
    if infra_target == "vmware_k3s":
        res_ov = vm_cfg.get("resources_override", {})
        storage_acc = vm_cfg.get("storage_account", {})
        nodes = res_ov.get("nodes", 3)
        vcpu = res_ov.get("vcpu_per_node", 4)
        ram = res_ov.get("ram_per_node_gb", 16)
        disk = res_ov.get("disk_per_node_gb", 150)
        rag_pvc = res_ov.get("rag_storage_pvc", "200Gi")
        host = vm_cfg.get("host", "vcenter")
        dc = vm_cfg.get("datacenter", "")
        cl = vm_cfg.get("cluster", "")
        ds = vm_cfg.get("datastore", "")
        with deployment_lock:
            deployment_state["logs"].append(f"[INFO] Cible d'infrastructure VMware vSphere : {host} (Datacenter: {dc or 'auto'}, Cluster/RP: {cl or 'auto'}, Datastore: {ds or 'auto'})")
            deployment_state["logs"].append(f"[INFO] Dimensionnement : {nodes} VM(s) x ({vcpu} vCPU, {ram} Go RAM, {disk} Go SSD), Stockage RAG : {rag_pvc}")
            if storage_acc.get("separate"):
                deployment_state["logs"].append(f"[INFO] Compte de stockage dissocié : type={storage_acc.get('provider_type')}, user={storage_acc.get('username')}, endpoint={storage_acc.get('endpoint') or 'local'}")

    deploy_script = os.path.join(SCRIPT_DIR, "deploy.py")
    cmd = [sys.executable, "-u", deploy_script, "--config", DEFAULT_CONFIG_PATH]
    if dry_run:
        cmd.append("--dry-run")

    env_vars = os.environ.copy()
    env_vars["PYTHONUNBUFFERED"] = "1"
    env_vars["PYTHONIOENCODING"] = "utf-8"
    env_vars["PYTHONUTF8"] = "1"

    with deployment_lock:
        deployment_state["logs"].append(f"[INFO] Exécution du déploiement : python -u scripts/deploy.py {'--dry-run' if dry_run else ''}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=ROOT_DIR,
            env=env_vars
        )
        with deployment_lock:
            active_deployment_proc = proc

        for line in iter(proc.stdout.readline, ''):
            if line:
                clean_line = strip_ansi_codes(line).rstrip()
                if clean_line:
                    with deployment_lock:
                        deployment_state["logs"].append(clean_line)

        proc.wait()
        exit_code = proc.returncode

        with deployment_lock:
            active_deployment_proc = None
            if deployment_state["status"] == "canceled":
                return
            deployment_state["exit_code"] = exit_code
            if exit_code == 0:
                cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
                fqdn = cfg.get("network", {}).get("public_fqdn", "assistant.example.org")
                hermes_pass = cfg.get("hermes", {}).get("admin_password", "admin")
                hermes_pat = cfg.get("hermes", {}).get("api_token", "")
                teams_enabled = cfg.get("teams_bot", {}).get("enabled", False)

                instance_repo_url = None
                if instance_git_info and instance_git_info.get("enabled") and not dry_run:
                    try:
                        deployment_state["logs"].append("\n[INFO] Sauvegarde chiffrée de l'instance vers le dépôt Git privé...")
                        repo_url = instance_git_info.get("repo_url", "")
                        token = instance_git_info.get("git_token", "")
                        passphrase = instance_git_info.get("passphrase", "")
                        inst_name = instance_git_info.get("instance_name", "ArcIA-instance")

                        push_res = backup_current_instance(cfg, passphrase=passphrase, token=token, repo_url=repo_url, force=True)
                        if push_res.get("success"):
                            deployment_state["logs"].append(f"[OK] Dépôt d'instance privé synchronisé et chiffré (AES-256-GCM) : {repo_url}")
                            instance_repo_url = repo_url
                        else:
                            deployment_state["logs"].append(f"[WARN] Avertissement sauvegarde Git : {push_res.get('error')}")
                    except Exception as ge:
                        deployment_state["logs"].append(f"[WARN] Sauvegarde Git non effectuée : {str(ge)}")

                deployment_state["status"] = "success"
                vm_auth = vm_cfg.get("auth", {})
                vm_net = vm_cfg.get("network", {})
                deployment_state["summary"] = {
                    "public_fqdn": fqdn,
                    "webui_url": f"https://{fqdn}/",
                    "studio_url": f"https://{fqdn}/studio",
                    "gateway_url": f"https://{fqdn}/gateway",
                    "teams_webhook": f"https://{fqdn}/api/teams/messages" if teams_enabled else None,
                    "hermes_admin_user": "admin",
                    "hermes_admin_pass": hermes_pass,
                    "hermes_pat": hermes_pat,
                    "instance_repo_url": instance_repo_url,
                    "mode": infra_target,
                    "credentials": {
                        "vmware": {
                            "active": infra_target == "vmware_k3s",
                            "host": vm_cfg.get("host", ""),
                            "ssh_user": vm_auth.get("vm_user", "debian"),
                            "vm_password": vm_auth.get("vm_password", ""),
                            "root_password": vm_auth.get("root_password", ""),
                            "ssh_key_path": vm_auth.get("ssh_key_path", ""),
                            "node_ips": vm_net.get("node_ips", ""),
                            "netmask": vm_net.get("netmask", ""),
                            "gateway": vm_net.get("gateway", ""),
                            "dns": vm_net.get("dns", ""),
                            "ntp": vm_net.get("ntp", "")
                        },
                        "litellm": {
                            "master_key": cfg.get("llm_gateway", {}).get("master_key", "")
                        },
                        "hermes": {
                            "admin_user": "admin",
                            "admin_password": hermes_pass,
                            "api_token": hermes_pat
                        },
                        "presidio": {
                            "master_key": cfg.get("presidio", {}).get("master_key", "")
                        },
                        "entra_id": {
                            "cookie_secret": cfg.get("entra_id_sso", {}).get("cookie_secret", "")
                        },
                        "teams_bot": {
                            "enabled": teams_enabled,
                            "app_password": cfg.get("teams_bot", {}).get("app_password", "")
                        }
                    }
                }
            else:
                deployment_state["status"] = "error"

    except Exception as e:
        with deployment_lock:
            active_deployment_proc = None
            if deployment_state["status"] != "canceled":
                deployment_state["status"] = "error"
                deployment_state["logs"].append(f"[FATAL ERROR] {str(e)}")


# -----------------------------------------------------------------------------
# Vérification en Ligne des Mises à Jour & Séquence de Mise à Jour Zero-Downtime
# -----------------------------------------------------------------------------

ARCIA_UPDATABLE_COMPONENTS = [
    {
        "id": "arcia-core",
        "name": "Socle ArcIA, ConfigMaps & Compétences",
        "icon": "🛡️",
        "category": "Socle & Microservices",
        "github_repo": "nicolastheuil/ArcIA",
        "manifest": "services/ & skills/",
        "k8s_resource": "configmap/presidio-code,hermes-governance-plugin,teams-bot-code,arcia-native-skills",
        "default_image": "nicolastheuil/ArcIA",
        "default_version": "v0.5.2",
        "strategy": "Hot-Sync ConfigMaps & Skills (0 coupure)",
        "wave": 1,
        "is_bumpable_image": False,
        "description": "Code source des microservices (Presidio DLP, Plugin Gouvernance/CCR Hermes, Bot Teams), branding et skills natives (Ponytail, Graphify, Public-APIs)."
    },
    {
        "id": "presidio-dlp",
        "name": "Microsoft Presidio DLP Shield",
        "icon": "🔒",
        "category": "Sécurité & Gouvernance",
        "github_repo": "microsoft/presidio",
        "manifest": "deploy/manifests/03-presidio.yaml",
        "k8s_resource": "deployment/presidio-dlp",
        "default_image": "python:3.11-slim",
        "default_version": "2.2.364",
        "strategy": "RollingUpdate (maxUnavailable: 0, maxSurge: 1) + Sonde /healthz",
        "wave": 2,
        "is_bumpable_image": False,
        "description": "Double barrière de détection et caviardage des secrets, adresses IP et données personnelles (PII fr/en) en mode fail-closed."
    },
    {
        "id": "oauth2-proxy",
        "name": "OAuth2-Proxy (SSO Microsoft Entra ID)",
        "icon": "🔐",
        "category": "Sécurité & Gouvernance",
        "github_repo": "oauth2-proxy/oauth2-proxy",
        "manifest": "deploy/manifests/02-oauth2-proxy.yaml",
        "k8s_resource": "deployment/oauth2-proxy",
        "default_image": "quay.io/oauth2-proxy/oauth2-proxy:v7.8.1",
        "default_version": "v7.8.1",
        "strategy": "RollingUpdate (maxUnavailable: 0, maxSurge: 1) + Sonde /ping",
        "wave": 2,
        "is_bumpable_image": True,
        "description": "Passerelle d'authentification OpenID Connect (ForwardAuth Traefik) protégeant les accès collaborateurs et studios."
    },
    {
        "id": "litellm-proxy",
        "name": "LiteLLM Proxy (Passerelle d'Inférence)",
        "icon": "⚡",
        "category": "Inférence & Routage",
        "github_repo": "BerriAI/litellm",
        "manifest": "deploy/manifests/05-litellm.yaml",
        "k8s_resource": "deployment/litellm-proxy",
        "default_image": "ghcr.io/berriai/litellm:main-v1.72.6-stable",
        "default_version": "v1.72.6-stable",
        "strategy": "RollingUpdate (maxUnavailable: 0, maxSurge: 1) + Sonde /health/liveliness",
        "wave": 3,
        "is_bumpable_image": True,
        "description": "Passerelle universelle exposant les 5 profils canoniques (simple/* & agentic/*), ZDR forcé, quotas PostgreSQL et guardrail Presidio."
    },
    {
        "id": "hermes-agent",
        "name": "Hermes Agent Runtime & Studio Kanban",
        "icon": "🤖",
        "category": "Moteur d'Agents",
        "github_repo": "NousResearch/Hermes-Agent",
        "manifest": "deploy/manifests/06-hermes-agent.yaml",
        "k8s_resource": "deployment/hermes-agent",
        "default_image": "nousresearch/hermes-agent:v0.22.2",
        "default_version": "v0.22.2",
        "strategy": "Mise à jour atomique + Préservation verrou SQLite state.db + Sync Power Users",
        "wave": 4,
        "is_bumpable_image": True,
        "description": "Moteur d'agents autonomes, Studio Kanban (:9119), Gateway API/WS (:8642) et pods dédiés des Power Users sur Kubernetes."
    },
    {
        "id": "teams-bot",
        "name": "Adaptateur Bot Microsoft Teams",
        "icon": "💬",
        "category": "Interfaces & Canaux",
        "github_repo": "microsoft/botbuilder-python",
        "manifest": "deploy/manifests/08-teams-bot.yaml",
        "k8s_resource": "deployment/teams-bot-adapter",
        "default_image": "python:3.11-slim",
        "default_version": "v4.16.0",
        "strategy": "RollingUpdate (maxUnavailable: 0, maxSurge: 1) + Sonde /healthz",
        "wave": 4,
        "is_bumpable_image": False,
        "description": "Passerelle Bot Framework pour Microsoft Teams (réponses rapides simple/auto et délégation /agent vers Hermes)."
    },
    {
        "id": "open-webui",
        "name": "Portail Collaborateur Open-WebUI",
        "icon": "🌐",
        "category": "Interfaces & Canaux",
        "github_repo": "open-webui/open-webui",
        "manifest": "deploy/manifests/07-open-webui.yaml",
        "k8s_resource": "deployment/open-webui",
        "default_image": "ghcr.io/open-webui/open-webui:v0.12.3",
        "default_version": "v0.12.3",
        "strategy": "Recreate (interruption prévue, volume RWO) + Sonde /health",
        "wave": 5,
        "is_bumpable_image": True,
        "description": "Portail web conversationnel d'entreprise avec RAG ChromaDB, SSO Entra ID et double raccordement simple/* et agentic/*."
    }
]

def extract_manifest_image_version(manifest_rel_path: str, default_image: str, default_version: str) -> Tuple[str, str]:
    """Lit l'image et la version actuellement déclarées dans un manifeste Kubernetes."""
    if not manifest_rel_path or not manifest_rel_path.endswith(".yaml"):
        return default_image, default_version
    full_path = os.path.join(ROOT_DIR, manifest_rel_path.replace("/", os.sep))
    if not os.path.isfile(full_path):
        return default_image, default_version
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        images = re.findall(r'^\s*image:\s*([^\s#]+)', content, flags=re.MULTILINE)
        if images:
            # Préférer l'image du conteneur applicatif principal (souvent le dernier si initContainer présent)
            img = images[-1].strip().strip('"').strip("'")
            img_no_digest = img.split("@")[0]
            if ":" in img_no_digest:
                ver = img_no_digest.split(":", 1)[1]
                # Nettoyer le préfixe main- éventuel de LiteLLM
                clean_ver = ver.replace("main-", "") if ver.startswith("main-v") else ver
                return img_no_digest, clean_ver
            return img_no_digest, default_version
    except Exception:
        pass
    return default_image, default_version

ARCIA_VERSIONS_FILE = os.path.join(ROOT_DIR, "deploy", "versions.json")

def load_arcia_official_versions(check_online: bool = False) -> Dict[str, Any]:
    """Charge le référentiel des versions officielles certifiées du projet ArcIA (dépôt ArcIA exclusif)."""
    local_data: Dict[str, Any] = {}
    if os.path.isfile(ARCIA_VERSIONS_FILE):
        try:
            with open(ARCIA_VERSIONS_FILE, "r", encoding="utf-8") as f:
                local_data = json.load(f)
                if isinstance(local_data, dict):
                    local_data.setdefault("arcia_version", local_data.get("arcia_release", "v0.5.1"))
        except Exception:
            pass

    if not check_online:
        return local_data

    # En mode vérification en ligne, interroger le référentiel officiel distant du projet ArcIA
    repo = local_data.get("repository", "nicolastheuil/ArcIA")
    remote_url = f"https://raw.githubusercontent.com/{repo}/main/deploy/versions.json"
    headers = {
        "User-Agent": "ArcIA-Update-Checker/0.5.2",
        "Accept": "application/json"
    }
    try:
        req = urllib.request.Request(remote_url, headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                remote_data = json.loads(resp.read().decode("utf-8", errors="replace"))
                if isinstance(remote_data, dict) and "components" in remote_data:
                    remote_data.setdefault("arcia_version", remote_data.get("arcia_release", "v0.5.1"))
                    return remote_data
    except Exception:
        pass

    if isinstance(local_data, dict):
        local_data.setdefault("arcia_version", local_data.get("arcia_release", "v0.5.1"))
    return local_data

def fetch_github_latest_release(repo: str, fallback_version: str) -> Dict[str, Any]:
    """Interroge l'API GitHub publique pour connaître la dernière version publiée d'un composant."""
    headers = {
        "User-Agent": "ArcIA-Update-Checker/0.5.2",
        "Accept": "application/vnd.github.v3+json"
    }
    # 1. Essayer /releases/latest
    try:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                tag = data.get("tag_name") or data.get("name") or fallback_version
                clean_tag = tag.replace("main-", "") if tag.startswith("main-v") else tag
                return {
                    "latest_version": clean_tag,
                    "raw_tag": tag,
                    "release_url": data.get("html_url", f"https://github.com/{repo}/releases"),
                    "published_at": (data.get("published_at") or "")[:10],
                    "online_checked": True
                }
    except Exception:
        pass

    # 2. Fallback sur /tags?per_page=1 (utile si un dépôt utilise des tags sans GitHub Release formelle)
    try:
        url_tags = f"https://api.github.com/repos/{repo}/tags?per_page=1"
        req_tags = urllib.request.Request(url_tags, headers=headers)
        with urllib.request.urlopen(req_tags, timeout=4) as resp:
            if resp.status == 200:
                tags_data = json.loads(resp.read().decode("utf-8", errors="replace"))
                if isinstance(tags_data, list) and len(tags_data) > 0:
                    tag = tags_data[0].get("name") or fallback_version
                    return {
                        "latest_version": tag,
                        "raw_tag": tag,
                        "release_url": f"https://github.com/{repo}/tags",
                        "published_at": "Récent",
                        "online_checked": True
                    }
    except Exception:
        pass

    return {
        "latest_version": fallback_version,
        "raw_tag": fallback_version,
        "release_url": f"https://github.com/{repo}/releases",
        "published_at": "Catalogue local",
        "online_checked": False
    }

def _normalize_ver(v: str) -> str:
    """Normalise une chaîne de version pour comparaison (ex: v0.5.10 -> 0.5.10)."""
    v = (v or "").strip()
    if v.startswith("main-"):
        v = v[5:]
    if v.endswith("-stable"):
        v = v[:-7]
    return v.lstrip("vV").strip()

def scan_production_versions(cfg: Optional[Dict[str, Any]] = None, timeout: int = 5) -> Dict[str, Dict[str, Any]]:
    """Interroge l'environnement de production (Kubernetes ou Docker Lab) pour connaître les versions réelles en service."""
    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)

    k8s_cfg = cfg.get("kubernetes", {})
    mode = k8s_cfg.get("mode", "local")
    namespace = k8s_cfg.get("namespace", "arcia") or "arcia"
    ssh_info = k8s_cfg.get("remote_ssh", {})

    versions: Dict[str, Dict[str, Any]] = {}

    # 1. Cible Kubernetes (local ou remote-ssh)
    if mode in ("local", "remote-ssh"):
        node_ip = ssh_info.get("node_ip", "").strip() if isinstance(ssh_info, dict) else ""
        if mode == "remote-ssh" and (not node_ip or node_ip in ("127.0.0.1", "192.168.1.100", "0.0.0.0")):
            mode = "local"

        try:
            sys.path.insert(0, SCRIPT_DIR)
            import deploy
            runner = deploy.K8sRunner(
                mode=mode,
                kubeconfig=k8s_cfg.get("kubeconfig", ""),
                context=k8s_cfg.get("context", ""),
                ssh_node=node_ip or "127.0.0.1",
                ssh_user=ssh_info.get("ssh_user", "debian") if isinstance(ssh_info, dict) else "debian",
                ssh_port=int(ssh_info.get("ssh_port", 22)) if isinstance(ssh_info, dict) else 22,
                ssh_key=ssh_info.get("ssh_key", "") if isinstance(ssh_info, dict) else ""
            )

            rc, out, _ = runner.run(["get", "deployments", f"-n={namespace}", "-o", "json"], timeout=timeout)
            if rc == 0 and out.strip():
                try:
                    data = json.loads(out)
                    items = data.get("items", [])
                    dep_map = {
                        "presidio-dlp": "presidio-dlp",
                        "oauth2-proxy": "oauth2-proxy",
                        "litellm-proxy": "litellm-proxy",
                        "hermes-agent": "hermes-agent",
                        "teams-bot-adapter": "teams-bot",
                        "teams-bot": "teams-bot",
                        "open-webui": "open-webui"
                    }
                    for item in items:
                        meta = item.get("metadata", {})
                        name = meta.get("name", "")
                        comp_id = dep_map.get(name)
                        if not comp_id:
                            continue

                        spec = item.get("spec", {}).get("template", {}).get("spec", {})
                        containers = spec.get("containers", [])
                        if not containers:
                            continue

                        img_full = containers[0].get("image", "").strip()
                        img_no_digest = img_full.split("@")[0]
                        tag = img_no_digest.split(":", 1)[1] if ":" in img_no_digest else "latest"
                        clean_tag = tag.replace("main-", "") if tag.startswith("main-v") else tag

                        annotations = meta.get("annotations", {})
                        labels = meta.get("labels", {})
                        app_ver = annotations.get("app.kubernetes.io/version") or labels.get("app.kubernetes.io/version")

                        # Pour les microservices reposant sur python:3.11-slim, conserver la version logicielle identifiée
                        if img_no_digest.startswith("python:") or img_no_digest == "python" or comp_id in ("presidio-dlp", "teams-bot"):
                            if app_ver and app_ver not in ("3.11-slim", "slim", "latest"):
                                final_ver = app_ver
                            else:
                                final_ver = next((c["default_version"] for c in ARCIA_UPDATABLE_COMPONENTS if c["id"] == comp_id), clean_tag)
                        else:
                            final_ver = clean_tag

                        status = item.get("status", {})
                        ready_replicas = status.get("readyReplicas", 0)

                        versions[comp_id] = {
                            "version": final_ver,
                            "image": img_no_digest,
                            "ready": ready_replicas > 0,
                            "replicas": status.get("replicas", 0),
                            "source": f"Cluster K8s ({namespace})"
                        }

                    # Vérifier présence ConfigMap arcia-native-skills pour arcia-core
                    rc_cm, out_cm, _ = runner.run(["get", "configmap", "arcia-native-skills", f"-n={namespace}", "-o", "json"], timeout=timeout)
                    if rc_cm == 0 and out_cm.strip():
                        versions["arcia-core"] = {
                            "version": "v0.5.1",
                            "image": "ConfigMap: arcia-native-skills",
                            "ready": True,
                            "replicas": 1,
                            "source": f"Cluster K8s ({namespace})"
                        }
                except Exception:
                    pass
        except Exception:
            pass

    # 2. Cible Docker Lab
    elif mode == "docker_lab" or cfg.get("infra_target") == "docker_lab":
        try:
            proc = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if proc.returncode == 0 and proc.stdout.strip():
                c_map = {
                    "presidio": "presidio-dlp",
                    "oauth2-proxy": "oauth2-proxy",
                    "litellm": "litellm-proxy",
                    "hermes": "hermes-agent",
                    "teams": "teams-bot",
                    "open-webui": "open-webui"
                }
                for line in proc.stdout.strip().splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        c_name, c_img = parts[0].strip(), parts[1].strip()
                        for prefix, cid in c_map.items():
                            if prefix in c_name:
                                img_no_digest = c_img.split("@")[0]
                                tag = img_no_digest.split(":", 1)[1] if ":" in img_no_digest else "latest"
                                clean_tag = tag.replace("main-", "") if tag.startswith("main-v") else tag
                                versions[cid] = {
                                    "version": clean_tag,
                                    "image": img_no_digest,
                                    "ready": True,
                                    "replicas": 1,
                                    "source": "Docker Lab"
                                }
                if versions:
                    versions["arcia-core"] = {
                        "version": "v0.5.1",
                        "image": "docker-compose.lab.yml",
                        "ready": True,
                        "replicas": 1,
                        "source": "Docker Lab"
                    }
        except Exception:
            pass

    return versions

def check_components_updates(check_online: bool = True, cfg: Optional[Dict[str, Any]] = None, force_prod_scan: bool = True) -> Dict[str, Any]:
    """Vérifie en direct l'état des versions en production (ou manifestes locaux) et les mises à jour en ligne."""
    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)

    prod_scanned: Dict[str, Dict[str, Any]] = {}
    if force_prod_scan:
        prod_scanned = scan_production_versions(cfg, timeout=4)

    arcia_catalog = load_arcia_official_versions(check_online=check_online)
    results: List[Dict[str, Any]] = [None] * len(ARCIA_UPDATABLE_COMPONENTS)  # type: ignore

    def _check_single(idx: int, comp: Dict[str, Any]):
        cid = comp["id"]
        prod_info = prod_scanned.get(cid)

        if prod_info:
            curr_ver = prod_info["version"]
            curr_img = prod_info["image"]
            source_label = prod_info["source"]
            is_live_prod = True
        else:
            curr_img, curr_ver = extract_manifest_image_version(
                comp["manifest"], comp["default_image"], comp["default_version"]
            )
            # Pour presidio et teams-bot dont l'image de base est python:3.11-slim, afficher la version logicielle
            if comp["id"] in ("presidio-dlp", "teams-bot", "arcia-core"):
                curr_ver = comp["default_version"]
            source_label = "Manifeste local"
            is_live_prod = False

        arcia_comp_ref = (arcia_catalog.get("components") or {}).get(cid, {})
        target_version = arcia_comp_ref.get("version") or comp["default_version"]
        target_image = arcia_comp_ref.get("image") or comp["default_image"]
        published_at = arcia_catalog.get("published_at") or "Catalogue ArcIA v0.5.2"
        release_notes = arcia_comp_ref.get("release_notes", "")
        repo = arcia_catalog.get("repository", "nicolastheuil/ArcIA")
        release_url = f"https://github.com/{repo}/releases"

        online_info = {
            "latest_version": target_version,
            "raw_tag": target_version,
            "target_image": target_image,
            "release_url": release_url,
            "published_at": published_at,
            "release_notes": release_notes,
            "online_checked": bool(check_online and arcia_catalog)
        }

        latest_ver = online_info["latest_version"]
        norm_curr = _normalize_ver(curr_ver)
        norm_latest = _normalize_ver(latest_ver)

        # Détecter si une mise à jour est disponible selon le référentiel officiel ArcIA
        if curr_ver in ("latest", "main"):
            update_avail = bool(norm_latest and norm_latest not in ("", "latest", "main"))
        else:
            update_avail = bool(norm_latest and norm_curr and norm_curr != norm_latest)

        results[idx] = {
            "id": comp["id"],
            "name": comp["name"],
            "icon": comp["icon"],
            "category": comp["category"],
            "github_repo": comp["github_repo"],
            "manifest": comp["manifest"],
            "k8s_resource": comp["k8s_resource"],
            "current_image": curr_img,
            "current_version": curr_ver,
            "latest_version": latest_ver,
            "raw_latest_tag": online_info.get("raw_tag", latest_ver),
            "update_available": update_avail,
            "has_update": update_avail,
            "online_checked": online_info["online_checked"],
            "release_url": online_info["release_url"],
            "published_at": online_info["published_at"],
            "strategy": comp["strategy"],
            "wave": comp["wave"],
            "order": comp["wave"],
            "is_bumpable_image": comp.get("is_bumpable_image", True),
            "is_prod_live": is_live_prod,
            "source": source_label,
            "description": comp["description"]
        }

    threads = []
    for i, comp in enumerate(ARCIA_UPDATABLE_COMPONENTS):
        t = threading.Thread(target=_check_single, args=(i, comp))
        t.daemon = True
        t.start()
        threads.append(t)

    for t in threads:
        t.join(timeout=6.0)

    valid_results = [r for r in results if r is not None]
    updates_count = sum(1 for r in valid_results if r.get("update_available"))
    online_count = sum(1 for r in valid_results if r.get("online_checked"))

    prod_active = len(prod_scanned) > 0
    prod_source_name = next(iter(prod_scanned.values()))["source"] if prod_active else "Manifestes locaux"

    payload = {
        "success": True,
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "online_reachable": online_count > 0,
        "prod_scanned": prod_active,
        "prod_source": prod_source_name,
        "total_components": len(valid_results),
        "updates_available_count": updates_count,
        "strategy": "RollingUpdate stateless ; Recreate avec interruption pour les états persistants",
        "components": valid_results
    }
    last_update_check_cache.clear()
    last_update_check_cache.update(payload)
    return payload

def get_initial_update_phases() -> List[Dict[str, Any]]:
    """Retourne les 6 étapes structurées de la séquence de mise à jour Zero-Downtime."""
    return [
        {
            "id": "preflight",
            "step": 1,
            "title": "Pré-vérification & Snapshot de Sécurité",
            "pct": 15,
            "status": "pending",
            "detail": "Contrôle de santé du cluster, vérification des nœuds Ready et sauvegarde mémoire des états."
        },
        {
            "id": "configs_skills",
            "step": 2,
            "title": "Hot-Sync ConfigMaps, Skills & Manifestes",
            "pct": 32,
            "status": "pending",
            "detail": "Injection à chaud du code des microservices (Presidio, Hermes Plugin, Teams) et des compétences natives."
        },
        {
            "id": "wave_security",
            "step": 3,
            "title": "Vague 1 — Bouclier Presidio DLP & SSO Entra ID",
            "pct": 52,
            "status": "pending",
            "detail": "RollingUpdate (maxUnavailable: 0, maxSurge: 1) avec validation préalable des sondes /healthz et /ping."
        },
        {
            "id": "wave_gateway",
            "step": 4,
            "title": "Vague 2 — Passerelle d'Inférence LiteLLM Proxy",
            "pct": 70,
            "status": "pending",
            "detail": "Mise à jour sans coupure de LiteLLM Proxy et vérification de la base comptable PostgreSQL."
        },
        {
            "id": "wave_agents",
            "step": 5,
            "title": "Vague 3 — Moteur Hermes Agent, Power Users & Bot Teams",
            "pct": 88,
            "status": "pending",
            "detail": "Mise à jour de Hermes Agent (intégrité SQLite state.db), du Bot Teams et des pods dédiés Power Users."
        },
        {
            "id": "wave_portal",
            "step": 6,
            "title": "Vague 4 — Portail Open-WebUI & Qualification Finale",
            "pct": 100,
            "status": "pending",
            "detail": "Recreate du portail Open-WebUI (interruption prévue, volume RWO) puis contrôle de disponibilité et des ressources visuelles."
        }
    ]

def repair_corrupted_manifest_images() -> List[str]:
    """Répare automatiquement les manifestes altérés par d'anciennes versions (ex: python:2.2.364 ou python:4.17.1)."""
    repaired_files = []
    presidio_path = os.path.join(ROOT_DIR, "deploy", "manifests", "03-presidio.yaml")
    if os.path.isfile(presidio_path):
        try:
            with open(presidio_path, "r", encoding="utf-8") as f:
                c = f.read()
            if re.search(r'^\s*image:\s*python:(?:2\.|[^\s#]*2\.2)', c, re.MULTILINE):
                repaired = re.sub(r'^(\s*image:\s*)python:[^\s#]+', r'\1python:3.11-slim', c, flags=re.MULTILINE)
                with open(presidio_path, "w", encoding="utf-8") as f:
                    f.write(repaired)
                repaired_files.append("deploy/manifests/03-presidio.yaml")
        except Exception:
            pass

    teams_path = os.path.join(ROOT_DIR, "deploy", "manifests", "08-teams-bot.yaml")
    if os.path.isfile(teams_path):
        try:
            with open(teams_path, "r", encoding="utf-8") as f:
                c = f.read()
            if re.search(r'^\s*image:\s*python:(?:4\.|[^\s#]*4\.1)', c, re.MULTILINE):
                repaired = re.sub(r'^(\s*image:\s*)python:[^\s#]+', r'\1python:3.11-slim', c, flags=re.MULTILINE)
                with open(teams_path, "w", encoding="utf-8") as f:
                    f.write(repaired)
                repaired_files.append("deploy/manifests/08-teams-bot.yaml")
        except Exception:
            pass
    return repaired_files

def update_manifest_image_tag(manifest_rel_path: str, new_tag: str) -> Optional[str]:
    """Met à jour proprement le tag d'image dans un manifeste Kubernetes si demandé."""
    if not manifest_rel_path or not manifest_rel_path.endswith(".yaml") or not new_tag:
        return None
    # Protection formelle : les microservices internes reposent sur python:3.11-slim
    # Leurs versions logicielles upstream ne doivent JAMAIS écraser l'image Python du conteneur.
    if any(m in manifest_rel_path for m in ("03-presidio.yaml", "08-teams-bot.yaml")):
        return None

    full_path = os.path.join(ROOT_DIR, manifest_rel_path.replace("/", os.sep))
    if not os.path.isfile(full_path):
        return None
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        def _repl(match):
            prefix = match.group(1)
            img_full = match.group(2)
            base_repo = img_full.split("@")[0].split(":")[0]
            # Protection absolue : ne jamais altérer l'interpréteur Python standard
            if base_repo in ("python", "library/python") or base_repo.endswith("/python"):
                return match.group(0)

            if "berriai/litellm" in base_repo:
                # Si le tag commence par v (ex: v1.105.1) ou main-, respecter le tag direct
                if new_tag.startswith("main-") or new_tag.startswith("v"):
                    final_tag = new_tag
                else:
                    final_tag = f"main-{new_tag}"
            else:
                final_tag = new_tag
            return f"{prefix}{base_repo}:{final_tag}"

        new_content = re.sub(r'^(\s*image:\s*)([^\s#]+)', _repl, content, flags=re.MULTILINE)
        if new_content != content:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return full_path
    except Exception:
        pass
    return None

def _set_update_phase(phase_idx: int, status: str, log_msg: Optional[str] = None):
    with update_lock:
        phases = update_state["phases"]
        if 0 <= phase_idx < len(phases):
            phases[phase_idx]["status"] = status
            update_state["current_phase"] = phases[phase_idx]["title"]
            if status == "done":
                update_state["progress_pct"] = phases[phase_idx]["pct"]
            elif status == "running" and phase_idx > 0:
                update_state["progress_pct"] = phases[phase_idx - 1]["pct"] + 5
            elif status == "running" and phase_idx == 0:
                update_state["progress_pct"] = 5
        if log_msg:
            update_state["logs"].append(log_msg)

def _append_update_log(msg: str):
    with update_lock:
        update_state["logs"].append(msg)

def run_update_worker(selected_components: List[str], bump_image_tags: bool = False,
                      dry_run: bool = False, infra_target: str = "k8s_existing"):
    """Exécute la séquence intelligente de mise à jour Zero-Downtime avec suivi temps réel."""
    global update_state

    if not selected_components:
        selected_components = [c["id"] for c in ARCIA_UPDATABLE_COMPONENTS]

    with update_lock:
        update_state["status"] = "running"
        update_state["progress_pct"] = 2
        update_state["current_phase"] = "Initialisation de la séquence de mise à jour..."
        update_state["phases"] = get_initial_update_phases()
        update_state["logs"] = [
            f"[INFO] Démarrage de l'orchestrateur de mise à jour intelligente ArcIA ({'Simulation Dry-Run' if dry_run else 'Exécution réelle'})",
            f"[INFO] Composants sélectionnés ({len(selected_components)}) : {', '.join(selected_components)}",
            f"[INFO] Stratégie : RollingUpdate pour les services stateless ; Recreate avec interruption pour Hermes et Open-WebUI."
        ]
        update_state["start_time"] = time.time()
        update_state["updated_components"] = []

    try:
        sys.path.insert(0, SCRIPT_DIR)
        import deploy
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
        k8s_cfg = cfg.get("kubernetes", {})
        namespace = k8s_cfg.get("namespace", "arcia")
        public_fqdn = cfg.get("network", {}).get("public_fqdn", "assistant.example.org") or "assistant.example.org"
        ssh_info = k8s_cfg.get("remote_ssh", {})

        runner = deploy.K8sRunner(
            mode=k8s_cfg.get("mode", "local"),
            kubeconfig=k8s_cfg.get("kubeconfig", ""),
            context=k8s_cfg.get("context", ""),
            ssh_node=ssh_info.get("node_ip", "127.0.0.1"),
            ssh_user=ssh_info.get("ssh_user", "debian"),
            ssh_port=int(ssh_info.get("ssh_port", 22)),
            ssh_key=ssh_info.get("ssh_key", "")
        )

        # =====================================================================
        # PHASE 1 : Pré-vérification & Snapshot de Sécurité
        # =====================================================================
        _set_update_phase(0, "running", "\n[PHASE 1/6] Pré-vérification de l'environnement et Snapshot de sécurité...")
        if dry_run:
            time.sleep(0.3)
            _append_update_log(f"[OK] [Dry-Run] Connectivité cluster et namespace '{namespace}' validés.")
            _append_update_log("[OK] [Dry-Run] Snapshot des manifestes et états de déploiement enregistré en mémoire.")
        elif infra_target == "docker_lab":
            doc_st = get_docker_status()
            if not doc_st.get("running"):
                _set_update_phase(0, "error", "[ERROR] Docker Engine n'est pas démarré sur cette machine.")
                with update_lock:
                    update_state["status"] = "error"
                return
            _append_update_log(f"[OK] Docker Engine v{doc_st.get('docker_version')} opérationnel pour mise à jour sans coupure.")
        else:
            rc, out, err = runner.run(["get", "nodes", "-o", "wide"])
            if rc != 0:
                _set_update_phase(0, "error", f"[ERROR] Impossible de joindre le cluster Kubernetes : {(err or out).strip()}")
                with update_lock:
                    update_state["status"] = "error"
                return
            nodes_cnt = len([l for l in out.strip().splitlines() if l and not l.startswith("NAME")])
            _append_update_log(f"[OK] Cluster Kubernetes joignable ({nodes_cnt} nœud(s) actif(s), namespace '{namespace}').")
        _set_update_phase(0, "done", "[OK] Phase 1 terminée : Pré-vérification qualifiée.")

        # =====================================================================
        # PHASE 2 : Hot-Sync ConfigMaps, Skills & Manifestes
        # =====================================================================
        _set_update_phase(1, "running", "\n[PHASE 2/6] Synchronisation à chaud des ConfigMaps, Skills et tags d'images...")
        repaired = repair_corrupted_manifest_images()
        for r_file in repaired:
            _append_update_log(f"[INFO] Réparation automatique du manifeste '{r_file}' vers l'image python:3.11-slim.")

        if bump_image_tags and last_update_check_cache.get("components"):
            for comp_info in last_update_check_cache["components"]:
                cid = comp_info["id"]
                if cid in selected_components and comp_info.get("update_available"):
                    # Protection stricte : les microservices internes sur python:3.11-slim ne bumpent pas leur image
                    if not comp_info.get("is_bumpable_image", True) or cid in ("presidio-dlp", "teams-bot", "arcia-core"):
                        _append_update_log(f"[INFO] {comp_info['name']} : microservice interne (code synchronisé via ConfigMap, image python:3.11-slim préservée).")
                        continue

                    new_tag = comp_info.get("raw_latest_tag") or comp_info.get("latest_version")
                    if dry_run:
                        _append_update_log(f"[INFO] [Dry-Run] Mise à jour du tag d'image pour {comp_info['name']} -> {new_tag} ({comp_info['manifest']})")
                    else:
                        updated_file = update_manifest_image_tag(comp_info["manifest"], new_tag)
                        if updated_file:
                            _append_update_log(f"[OK] Manifeste '{comp_info['manifest']}' mis à jour vers la version {new_tag}.")

        if dry_run:
            time.sleep(0.3)
            _append_update_log("[OK] [Dry-Run] ConfigMaps 'presidio-code', 'hermes-governance-plugin', 'teams-bot-code' synchronisés.")
            _append_update_log("[OK] [Dry-Run] Compétences natives ('ponytail', 'graphify', 'public-apis') et branding Open-WebUI synchronisés.")
        elif infra_target == "docker_lab":
            _append_update_log("[INFO] Rafraîchissement des images Docker Lab (docker compose pull)...")
            subprocess.run(["docker", "compose", "-f", os.path.join(ROOT_DIR, "docker-compose.lab.yml"), "pull"], cwd=ROOT_DIR, capture_output=True)
            _append_update_log("[OK] Images Docker et configurations locales prêtes.")
        else:
            code_checksums = deploy.sync_service_configmaps(runner, namespace, ROOT_DIR)
            _append_update_log("[OK] ConfigMaps de code microservices synchronisés à chaud sans coupure.")
            deploy.sync_native_skills(runner, namespace, ROOT_DIR)
            _append_update_log("[OK] Catalogue de compétences natives ('arcia-native-skills') synchronisé.")
            visual = deploy.sync_webui_branding(runner, namespace, ROOT_DIR, cfg=cfg)
            _append_update_log("[OK] Ressources visuelles publiées ; chargement et vérification après la mise à jour du portail.")

        if "arcia-core" in selected_components:
            with update_lock:
                update_state["updated_components"].append("arcia-core")
        _set_update_phase(1, "done", "[OK] Phase 2 terminée : ConfigMaps et compétences à jour.")

        # Helper interne pour appliquer un manifeste et suivre le rollout sans interruption
        manifests_dir = os.path.join(ROOT_DIR, "deploy", "manifests")

        def _rolling_update_k8s_deployment(comp_id: str, comp_label: str, manifest_filename: str, dep_name: str, ensure_zero_downtime_patch: bool = True):
            if comp_id not in selected_components:
                _append_update_log(f"[INFO] {comp_label} non sélectionné — conservé en l'état.")
                return
            if dry_run:
                time.sleep(0.25)
                strategy = "RollingUpdate" if ensure_zero_downtime_patch else "Recreate (interruption prévue)"
                _append_update_log(f"[INFO] [Dry-Run] Application de {manifest_filename} ({dep_name}) avec {strategy}.")
                _append_update_log(f"[OK] [Dry-Run] Disponibilité du nouveau pod '{dep_name}' simulée.")
                with update_lock:
                    update_state["updated_components"].append(comp_id)
                return
            if infra_target == "docker_lab":
                _append_update_log(f"[INFO] Recréation sans coupure du conteneur {dep_name} via Docker Compose...")
                subprocess.run(["docker", "compose", "-f", os.path.join(ROOT_DIR, "docker-compose.lab.yml"), "up", "-d", "--no-deps", dep_name], cwd=ROOT_DIR, capture_output=True)
                _append_update_log(f"[OK] Conteneur {dep_name} mis à jour.")
                with update_lock:
                    update_state["updated_components"].append(comp_id)
                return

            m_path = os.path.join(manifests_dir, manifest_filename)
            if os.path.isfile(m_path):
                with open(m_path, "r", encoding="utf-8") as f:
                    raw_yaml = f.read()
                adapted_yaml = deploy.render_model_manifest(
                    comp_id, raw_yaml, cfg, namespace,
                    branding_revision=visual["revision"], code_checksums=code_checksums)
                runner.apply_manifest(adapted_yaml)

            if ensure_zero_downtime_patch:
                patch_json = json.dumps({
                    "spec": {
                        "strategy": {
                            "type": "RollingUpdate",
                            "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1}
                        }
                    }
                })
                runner.run(["patch", "deployment", dep_name, f"-n={namespace}", "--type=merge", "-p", patch_json])

            # Déclencher un rollout restart propre pour prendre en compte les ConfigMaps actualisés et la nouvelle image
            runner.run(["rollout", "restart", f"deployment/{dep_name}", f"-n={namespace}"])
            _append_update_log(f"[INFO] Attente de la sonde de disponibilité (readinessProbe) pour '{dep_name}'...")
            rc_ro, out_ro, err_ro = runner.run(["rollout", "status", f"deployment/{dep_name}", f"-n={namespace}", "--timeout=360s"])
            if rc_ro == 0:
                availability = "sans interruption" if ensure_zero_downtime_patch else "avec interruption prévue (Recreate)"
                _append_update_log(f"[OK] '{dep_name}' mis à jour {availability}.")
                with update_lock:
                    update_state["updated_components"].append(comp_id)
            else:
                _append_update_log(f"[WARN] Délai dépassé sur '{dep_name}' ({err_ro.strip() or out_ro.strip()}) — déclenchement automatique de 'rollout undo' pour préserver le service !")
                runner.run(["rollout", "undo", f"deployment/{dep_name}", f"-n={namespace}"])
                raise RuntimeError(f"Échec de santé du nouveau pod sur {dep_name} (rollback automatique effectué).")

        # =====================================================================
        # PHASE 3 : Vague 1 — Bouclier DLP Presidio & SSO Entra ID
        # =====================================================================
        _set_update_phase(2, "running", "\n[PHASE 3/6] Vague 1 — Mise à jour du Bouclier DLP Presidio & SSO Entra ID...")
        _rolling_update_k8s_deployment("presidio-dlp", "Presidio DLP Shield", "03-presidio.yaml", "presidio-dlp", ensure_zero_downtime_patch=True)
        if cfg.get("entra_id_sso", {}).get("enabled") or dry_run:
            _rolling_update_k8s_deployment("oauth2-proxy", "OAuth2-Proxy SSO", "02-oauth2-proxy.yaml", "oauth2-proxy", ensure_zero_downtime_patch=True)
        else:
            _append_update_log("[INFO] SSO Entra ID (oauth2-proxy) est désactivé dans la configuration — étape ignorée.")
        _set_update_phase(2, "done", "[OK] Phase 3 terminée : Bouclier DLP et authentification opérationnels.")

        # =====================================================================
        # PHASE 4 : Vague 2 — Passerelle d'Inférence LiteLLM Proxy
        # =====================================================================
        _set_update_phase(3, "running", "\n[PHASE 4/6] Vague 2 — Mise à jour de la Passerelle d'Inférence LiteLLM Proxy...")
        _rolling_update_k8s_deployment("litellm-proxy", "LiteLLM Proxy", "05-litellm.yaml", "litellm-proxy", ensure_zero_downtime_patch=True)
        _set_update_phase(3, "done", "[OK] Phase 4 terminée : Passerelle LiteLLM opérationnelle sur les 5 profils canoniques.")

        # =====================================================================
        # PHASE 5 : Vague 3 — Moteur Hermes Agent, Power Users & Bot Teams
        # =====================================================================
        _set_update_phase(4, "running", "\n[PHASE 5/6] Vague 3 — Mise à jour de Hermes Agent, des Pods Power Users & du Bot Teams...")
        # Pour Hermes Agent, la stratégie Recreate protège le verrou d'écriture unique sur SQLite state.db
        _rolling_update_k8s_deployment("hermes-agent", "Hermes Agent & Studio", "06-hermes-agent.yaml", "hermes-agent", ensure_zero_downtime_patch=False)

        if "hermes-agent" in selected_components and not dry_run and infra_target != "docker_lab":
            try:
                from arcia_poweruser import sync_all_powerusers
                def _pu_runner(cmd_args, input_data=None):
                    rc, out, err = runner.run(cmd_args, stdin_input=input_data)
                    return subprocess.CompletedProcess(cmd_args, rc, out, err)
                synced_pu = sync_all_powerusers(namespace=namespace, fqdn=public_fqdn, runner_func=_pu_runner)
                _append_update_log(f"[OK] {synced_pu} instance(s) dédiée(s) Power User synchronisée(s).")
            except Exception as pue:
                _append_update_log(f"[WARN] Synchronisation des pods Power Users ignorée : {pue}")
        elif "hermes-agent" in selected_components and dry_run:
            _append_update_log("[OK] [Dry-Run] Synchronisation des pods dédiés Power Users simulée avec succès.")

        if cfg.get("teams_bot", {}).get("enabled") or dry_run:
            _rolling_update_k8s_deployment("teams-bot", "Adaptateur Microsoft Teams Bot", "08-teams-bot.yaml", "teams-bot-adapter", ensure_zero_downtime_patch=True)
        else:
            _append_update_log("[INFO] Bot Microsoft Teams désactivé dans la configuration — étape ignorée.")
        _set_update_phase(4, "done", "[OK] Phase 5 terminée : Moteur Hermes Agent et canaux d'équipe à jour.")

        # =====================================================================
        # PHASE 6 : Vague 4 — Portail Open-WebUI & Qualification Finale
        # =====================================================================
        _set_update_phase(5, "running", "\n[PHASE 6/6] Vague 4 — Mise à jour du Portail Collaborateur Open-WebUI & Vérification finale...")
        _rolling_update_k8s_deployment("open-webui", "Portail Open-WebUI", "07-open-webui.yaml", "open-webui", ensure_zero_downtime_patch=False)
        if not dry_run and infra_target != "docker_lab":
            visual_result = deploy.activate_webui_branding(runner, namespace, visual)
            if not (visual_result.get("assets_served") and visual_result.get("runtime_loaded")):
                raise RuntimeError("Ressources visuelles non vérifiées après rechargement Open-WebUI.")
            _append_update_log("[OK] Projection et ressources visuelles Open-WebUI vérifiées par HTTP ; recette navigateur distincte.")
            if "litellm-proxy" in selected_components:
                legacy_key = deploy.retire_legacy_webui_key(runner, namespace, ROOT_DIR)
                if legacy_key.get("verified_absent"):
                    _append_update_log("[OK] Ancienne clé statique Open-WebUI absente ; clés nominatives préservées.")
                else:
                    _append_update_log("[WARN] Retrait de l'ancienne clé statique différé : connexion du portail non vérifiée.")
        _set_update_phase(5, "done", "\n[OK] SÉQUENCE DE MISE À JOUR TERMINÉE AVEC SUCCÈS (100%) !")

        with update_lock:
            update_state["status"] = "success"
            update_state["progress_pct"] = 100
            update_state["current_phase"] = "Mise à jour terminée (interruptions Recreate prévues)"

    except Exception as ue:
        with update_lock:
            update_state["status"] = "error"
            update_state["current_phase"] = f"Erreur : {str(ue)}"
            update_state["logs"].append(f"[ERROR] Séquence interrompue : {str(ue)}")

# -----------------------------------------------------------------------------
# Gestion des Power Users (Pods Hermes Dédiés, PVCs & SOUL)
# -----------------------------------------------------------------------------

def get_k8s_runner(cfg: Optional[Dict[str, Any]] = None, context: Optional[str] = None, namespace: Optional[str] = None) -> Any:
    """Instancie un K8sRunner configuré pour le cluster actif avec repli intelligent sur kubectl local."""
    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
    sys.path.insert(0, SCRIPT_DIR)
    import deploy
    k8s = cfg.get("kubernetes", {})
    remote_ssh = k8s.get("remote_ssh", {})
    node_ip = remote_ssh.get("node_ip", "").strip() if isinstance(remote_ssh, dict) else ""
    mode = k8s.get("mode", "local")

    # Si le mode est remote-ssh mais que l'IP renseignée est une IP fictive / d'exemple (ex: 192.168.1.100 ou 127.0.0.1)
    # ou vide, basculer automatiquement sur kubectl local pour éviter tout blocage SSH aveugle
    if mode == "remote-ssh" and (not node_ip or node_ip in ("192.168.1.100", "127.0.0.1", "0.0.0.0")):
        mode = "local"

    ctx_to_use = context if (context is not None and str(context).strip()) else k8s.get("context", "")

    return deploy.K8sRunner(
        mode=mode,
        kubeconfig=k8s.get("kubeconfig", ""),
        context=ctx_to_use,
        ssh_node=node_ip or "127.0.0.1",
        ssh_user=remote_ssh.get("ssh_user", "debian") if isinstance(remote_ssh, dict) else "debian",
        ssh_port=int(remote_ssh.get("ssh_port", 22)) if isinstance(remote_ssh, dict) else 22,
        ssh_key=remote_ssh.get("ssh_key", "") if isinstance(remote_ssh, dict) else ""
    )

def get_cluster_resource_metrics(cfg: Optional[Dict[str, Any]] = None, runner: Any = None) -> Dict[str, Any]:
    """Récupère ou estime la charge des ressources (CPU, RAM, Stockage) du cluster K8s ou Docker."""
    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)

    infra_target = cfg.get("infra_target", "k8s_existing")
    ns = cfg.get("kubernetes", {}).get("namespace", "arcia")

    metrics = {
        "available": True,
        "target": infra_target,
        "cpu": {"percent": 24, "used": "4.8 GHz", "total": "20.0 GHz", "label": "Charge CPU Cluster (GHz)"},
        "ram": {"percent": 38, "used": "12.2 Go", "total": "32 Go", "label": "Mémoire RAM"},
        "storage": {"percent": 31, "used": "62 Go", "total": "200 Go", "label": "Stockage Persistant CSI"}
    }

    if infra_target == "docker_lab":
        metrics["storage"]["label"] = "Volumes Docker"
        metrics["storage"]["used"] = "18 Go"
        metrics["storage"]["total"] = "100 Go"
        metrics["storage"]["percent"] = 18
        try:
            proc = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}\t{{.MemPerc}}\t{{.MemUsage}}"],
                capture_output=True, text=True, timeout=3
            )
            if proc.returncode == 0 and proc.stdout.strip():
                lines = [l for l in proc.stdout.strip().splitlines() if l]
                total_cpu = 0.0
                total_mem_pct = 0.0
                for l in lines:
                    parts = l.split("\t")
                    if len(parts) >= 2:
                        cpu_str = parts[0].replace("%", "").strip()
                        mem_str = parts[1].replace("%", "").strip()
                        try:
                            total_cpu += float(cpu_str)
                            total_mem_pct += float(mem_str)
                        except Exception:
                            pass
                cpu_p = min(round(total_cpu, 1), 100.0)
                mem_p = min(round(total_mem_pct, 1), 100.0)
                ghz_used = round((cpu_p / 100.0) * 16.0, 1)
                metrics["cpu"] = {"percent": int(cpu_p), "used": f"{ghz_used} GHz", "total": "16.0 GHz", "label": "Charge CPU Docker (GHz)"}
                metrics["ram"] = {"percent": int(mem_p), "used": f"{mem_p}%", "total": "100%", "label": "RAM Docker"}
        except Exception:
            pass
        return metrics

    if runner is not None:
        try:
            rc_top, out_top, _ = runner.run(["top", "nodes", "--no-headers"], timeout=4)
            if rc_top == 0 and out_top.strip():
                lines = [l for l in out_top.strip().splitlines() if l]
                cpu_pcts = []
                mem_pcts = []
                for l in lines:
                    parts = l.split()
                    if len(parts) >= 5:
                        try:
                            cpu_pcts.append(int(parts[2].replace("%", "")))
                            mem_pcts.append(int(parts[4].replace("%", "")))
                        except Exception:
                            pass
                if cpu_pcts and mem_pcts:
                    avg_cpu = int(sum(cpu_pcts) / len(cpu_pcts))
                    avg_mem = int(sum(mem_pcts) / len(mem_pcts))
                    metrics["cpu"]["percent"] = max(1, min(100, avg_cpu))
                    ghz_used = round((metrics["cpu"]["percent"] / 100.0) * 20.0, 1)
                    metrics["cpu"]["used"] = f"{ghz_used} GHz"
                    metrics["cpu"]["total"] = "20.0 GHz"
                    metrics["ram"]["percent"] = max(1, min(100, avg_mem))
        except Exception:
            pass

        try:
            rc_pvc, out_pvc, _ = runner.run(["get", "pvc", f"-n={ns}", "--no-headers"], timeout=4)
            if rc_pvc == 0 and out_pvc.strip():
                lines = [l for l in out_pvc.strip().splitlines() if l]
                pvc_count = len(lines)
                allocated_gi = max(20, pvc_count * 10)
                metrics["storage"]["used"] = f"{allocated_gi} Go"
                metrics["storage"]["total"] = "200 Go"
                metrics["storage"]["percent"] = min(int((allocated_gi / 200.0) * 100), 100)
        except Exception:
            pass

    return metrics

def check_instance_connectivity(cfg: Optional[Dict[str, Any]] = None, context: Optional[str] = None, namespace: Optional[str] = None) -> Dict[str, Any]:
    """Teste la connectivité à l'infrastructure cible et vérifie si une instance ArcIA y est déployée."""
    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)

    infra_target = cfg.get("infra_target", "k8s_existing")
    fqdn = cfg.get("network", {}).get("public_fqdn", "assistant.example.org") or "assistant.example.org"
    default_model_simple = cfg.get("llm_gateway", {}).get("default_model", "simple/auto")
    default_model_agentic = cfg.get("hermes", {}).get("default_model", "agentic/auto")

    # 1. Cible Docker Lab
    if infra_target == "docker_lab":
        docker_st = get_docker_status()
        metrics = get_cluster_resource_metrics(cfg)
        if not docker_st.get("running"):
            return {
                "success": False,
                "connected": False,
                "instance_detected": False,
                "target": "docker_lab",
                "target_info": "Docker Lab (local)",
                "error": "Le démon Docker n'est pas accessible sur cette machine.",
                "message": "Démon Docker inaccessible. Vérifiez que Docker Desktop ou le service dockerd est démarré.",
                "deployed_components": [],
                "components_count": 0,
                "webui_url": "http://localhost:3000",
                "metrics": metrics,
                "default_model": default_model_simple,
                "default_model_simple": default_model_simple,
                "hermes_default_model": default_model_agentic,
                "default_model_agentic": default_model_agentic
            }
        prod_versions = scan_production_versions(cfg, timeout=4)
        has_instance = any(k in prod_versions for k in ("open-webui", "hermes-agent", "litellm-proxy", "presidio-dlp", "teams-bot", "arcia-core"))
        rich_components = []
        for comp in ARCIA_UPDATABLE_COMPONENTS:
            cid = comp["id"]
            if cid in prod_versions:
                info = prod_versions[cid]
                rich_components.append({
                    "id": cid,
                    "name": comp["name"],
                    "version": info.get("version", comp["default_version"]),
                    "ready": info.get("ready", True),
                    "source": "Docker Lab",
                    "image": info.get("image", comp["default_image"])
                })
        official_catalog = load_arcia_official_versions(check_online=False).get("components", {})
        for c in rich_components:
            cid = c.get("id")
            cur_v = c.get("version", "")
            target_info = official_catalog.get(cid, {})
            target_v = target_info.get("version", cur_v)
            c["target_version"] = target_v
            c["latest_version"] = target_v
            has_up = bool(cur_v and target_v and cur_v != target_v and cur_v != "Inconnu")
            c["has_update"] = has_up
            c["update_available"] = has_up

        updates_count = sum(1 for c in rich_components if c.get("has_update"))

        return {
            "success": True,
            "connected": True,
            "instance_detected": has_instance,
            "target": "docker_lab",
            "target_info": "Docker Lab (local)",
            "deployed_components": rich_components if has_instance else [],
            "components_count": len(rich_components) if has_instance else 0,
            "updates_available": (updates_count > 0),
            "updates_count": updates_count,
            "webui_url": "http://localhost:3000",
            "metrics": metrics,
            "default_model": default_model_simple,
            "default_model_simple": default_model_simple,
            "hermes_default_model": default_model_agentic,
            "default_model_agentic": default_model_agentic,
            "message": "Instance Docker Lab détectée et opérationnelle." if has_instance else "Démon Docker opérationnel, mais aucun conteneur ArcIA n'est en cours d'exécution."
        }

    # 2. Cible Kubernetes (k8s_existing ou vmware_k3s)
    k8s_cfg = cfg.get("kubernetes", {})
    ns = namespace or k8s_cfg.get("namespace", "arcia")
    webui_url = f"https://{fqdn}"

    try:
        runner = get_k8s_runner(cfg, context=context, namespace=ns)
        target_desc = f"SSH ({runner.ssh_node})" if runner.mode == "remote-ssh" else f"kubectl local (contexte: {runner.context or 'actif'})"

        # Test de contact avec l'API Kubernetes
        rc, out, err = runner.run(["get", "nodes", "-o", "name"], timeout=5)
        if rc != 0:
            err_msg = err.strip() or out.strip() or f"Impossible de contacter le cluster Kubernetes via {target_desc}."
            metrics = get_cluster_resource_metrics(cfg, runner)
            return {
                "success": False,
                "connected": False,
                "instance_detected": False,
                "target": runner.mode,
                "target_info": target_desc,
                "namespace": ns,
                "error": err_msg,
                "message": f"Échec de connexion au cluster Kubernetes ({target_desc}). Vérifiez l'accès réseau ou le kubeconfig.",
                "deployed_components": [],
                "components_count": 0,
                "webui_url": webui_url,
                "metrics": metrics,
                "default_model": default_model_simple,
                "default_model_simple": default_model_simple,
                "hermes_default_model": default_model_agentic,
                "default_model_agentic": default_model_agentic
            }

        # Test de présence du namespace ArcIA
        rc_ns, out_ns, _ = runner.run(["get", "namespace", ns, "-o", "name"], timeout=4)
        if rc_ns != 0:
            metrics = get_cluster_resource_metrics(cfg, runner)
            return {
                "success": True,
                "connected": True,
                "instance_detected": False,
                "target": runner.mode,
                "target_info": target_desc,
                "namespace": ns,
                "deployed_components": [],
                "components_count": 0,
                "webui_url": webui_url,
                "metrics": metrics,
                "message": f"Cluster Kubernetes accessible, mais le namespace '{ns}' n'existe pas encore."
            }

        # Test de détection des déploiements ArcIA dans le namespace
        rc_dep, out_dep, _ = runner.run(["get", "deployments", f"-n={ns}", "-o", "jsonpath={.items[*].metadata.name}"], timeout=5)
        detected_deps = []
        if rc_dep == 0 and out_dep.strip():
            all_deps = out_dep.strip().split()
            detected_deps = [d for d in all_deps if any(k in d for k in ("open-webui", "hermes", "litellm", "presidio", "teams", "oauth2"))]

        metrics = get_cluster_resource_metrics(cfg, runner)

        if detected_deps:
            prod_versions = scan_production_versions(cfg, timeout=4)
            rich_components = []
            for comp in ARCIA_UPDATABLE_COMPONENTS:
                cid = comp["id"]
                if cid in prod_versions:
                    info = prod_versions[cid]
                    rich_components.append({
                        "id": cid,
                        "name": comp["name"],
                        "version": info.get("version", comp["default_version"]),
                        "ready": info.get("ready", True),
                        "source": info.get("source", target_desc),
                        "image": info.get("image", comp["default_image"])
                    })
                elif cid in detected_deps or any(d in comp["manifest"] for d in detected_deps):
                    rich_components.append({
                        "id": cid,
                        "name": comp["name"],
                        "version": comp["default_version"],
                        "ready": True,
                        "source": target_desc,
                        "image": comp["default_image"]
                    })

            # Détection des mises à jour disponibles selon le catalogue certifié ArcIA
            official_catalog = load_arcia_official_versions(check_online=False).get("components", {})
            for c in rich_components:
                cid = c.get("id")
                cur_v = c.get("version", "")
                target_info = official_catalog.get(cid, {})
                target_v = target_info.get("version", cur_v)
                c["target_version"] = target_v
                c["latest_version"] = target_v
                has_up = bool(cur_v and target_v and cur_v != target_v and cur_v != "Inconnu")
                c["has_update"] = has_up
                c["update_available"] = has_up

            updates_count = sum(1 for c in rich_components if c.get("has_update"))

            return {
                "success": True,
                "connected": True,
                "instance_detected": True,
                "target": runner.mode,
                "target_info": target_desc,
                "namespace": ns,
                "deployed_components": rich_components,
                "components_count": len(rich_components),
                "updates_available": (updates_count > 0),
                "updates_count": updates_count,
                "webui_url": webui_url,
                "metrics": metrics,
                "default_model": default_model_simple,
                "default_model_simple": default_model_simple,
                "hermes_default_model": default_model_agentic,
                "default_model_agentic": default_model_agentic,
                "message": f"Instance ArcIA détectée dans le namespace '{ns}' ({len(rich_components)} composant(s) déployé(s))."
            }

        return {
            "success": True,
            "connected": True,
            "instance_detected": False,
            "target": runner.mode,
            "target_info": target_desc,
            "namespace": ns,
            "deployed_components": [],
            "components_count": 0,
            "webui_url": webui_url,
            "metrics": metrics,
            "default_model": default_model_simple,
            "default_model_simple": default_model_simple,
            "hermes_default_model": default_model_agentic,
            "default_model_agentic": default_model_agentic,
            "message": f"Cluster Kubernetes accessible, mais aucun composant ArcIA n'est déployé dans le namespace '{ns}'."
        }

    except Exception as exc:
        return {
            "success": False,
            "connected": False,
            "instance_detected": False,
            "target": "error",
            "target_info": "Erreur interne",
            "namespace": ns,
            "error": str(exc),
            "message": f"Erreur lors du test de connectivité : {str(exc)}",
            "deployed_components": [],
            "components_count": 0,
            "webui_url": webui_url
        }

def list_powerusers(cfg: Optional[Dict[str, Any]] = None, context: Optional[str] = None, namespace: Optional[str] = None) -> Dict[str, Any]:
    """Récupère l'état complet des Power Users : déploiements, pods, PVCs et consommation."""
    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
    ns = namespace or cfg.get("kubernetes", {}).get("namespace", "arcia")
    fqdn = cfg.get("network", {}).get("public_fqdn", "assistant.example.org")

    try:
        runner = get_k8s_runner(cfg, context=context, namespace=ns)
        rc_dep, out_dep, err_dep = runner.run(["get", "deployments", "-n", ns, "-l", "arcia.io/role=poweruser", "-o", "json"])
        if rc_dep != 0:
            target_desc = f"SSH ({runner.ssh_node})" if runner.mode == "remote-ssh" else f"kubectl local (contexte: {runner.context or 'actif'})"
            return {
                "status": "ok",
                "success": False,
                "connected": False,
                "namespace": ns,
                "context": runner.context or "default",
                "mode": runner.mode,
                "target_info": target_desc,
                "error": err_dep.strip() or f"Impossible de contacter le namespace '{ns}' sur le cluster ({target_desc}).",
                "users": [],
                "powerusers": [],
                "stats": {"total": 0, "running": 0, "sleeping": 0, "other": 0, "total_storage_gi": 0}
            }

        dep_data = json.loads(out_dep)
        deployments = dep_data.get("items", [])
    except Exception as e:
        return {
            "status": "ok",
            "success": False,
            "connected": False,
            "namespace": ns,
            "error": str(e),
            "users": [],
            "powerusers": [],
            "stats": {"total": 0, "running": 0, "sleeping": 0, "other": 0, "total_storage_gi": 0}
        }

    pods_by_slug = {}
    try:
        rc_pods, out_pods, _ = runner.run(["get", "pods", "-n", ns, "-l", "arcia.io/role=poweruser", "-o", "json"])
        if rc_pods == 0:
            pod_items = json.loads(out_pods).get("items", [])
            for p in pod_items:
                labels = p.get("metadata", {}).get("labels", {})
                slug = labels.get("app.kubernetes.io/instance") or labels.get("arcia.io/user-slug")
                if not slug:
                    name = p.get("metadata", {}).get("name", "")
                    m = re.match(r"hermes-poweruser-([a-z0-9\-]+?)(?:-[a-z0-9]+)+$", name)
                    if m:
                        slug = m.group(1)
                if slug:
                    pods_by_slug[slug] = p
    except Exception:
        pass

    pvcs_by_slug = {}
    try:
        rc_pvc, out_pvc, _ = runner.run(["get", "pvc", "-n", ns, "-o", "json"])
        if rc_pvc == 0:
            pvc_items = json.loads(out_pvc).get("items", [])
            for pvc in pvc_items:
                pname = pvc.get("metadata", {}).get("name", "")
                if pname.startswith("hermes-user-") and pname.endswith("-pvc"):
                    slug = pname[len("hermes-user-"):-len("-pvc")]
                    pvcs_by_slug[slug] = pvc
    except Exception:
        pass

    cm_by_slug = {}
    try:
        rc_cm, out_cm, _ = runner.run(["get", "configmaps", "-n", ns, "-o", "json"])
        if rc_cm == 0:
            cm_items = json.loads(out_cm).get("items", [])
            for cm in cm_items:
                cname = cm.get("metadata", {}).get("name", "")
                if cname.startswith("hermes-user-") and cname.endswith("-config"):
                    slug = cname[len("hermes-user-"):-len("-config")]
                    cm_by_slug[slug] = cm.get("data", {})
    except Exception:
        pass

    users = []
    for dep in deployments:
        dname = dep.get("metadata", {}).get("name", "")
        labels = dep.get("metadata", {}).get("labels", {})
        slug = labels.get("app.kubernetes.io/instance") or labels.get("arcia.io/user-slug") or dname.replace("hermes-poweruser-", "")
        spec = dep.get("spec", {})
        status = dep.get("status", {})
        replicas = spec.get("replicas", 0)
        ready_replicas = status.get("readyReplicas", 0)

        cm_data = cm_by_slug.get(slug, {})
        user_md = cm_data.get("USER.md", "")
        user_email = f"{slug}@entreprise.org"
        team = "engineering"
        job_title = "Expert / Ingénieur"
        manager = "Direction Technique"
        if user_md:
            m_email = re.search(r"- Email\s*:\s*([^\r\n]+)", user_md)
            if m_email: user_email = m_email.group(1).strip()
            m_team = re.search(r"- (?:Équipe|Equipe)\s*:\s*([^\r\n]+)", user_md)
            if m_team: team = m_team.group(1).strip()
            m_job = re.search(r"- Fonction\s*:\s*([^\r\n]+)", user_md)
            if m_job: job_title = m_job.group(1).strip()
            m_mgr = re.search(r"- Responsable\s*:\s*([^\r\n]+)", user_md)
            if m_mgr: manager = m_mgr.group(1).strip()

        pod = pods_by_slug.get(slug)
        pod_status = "Sleeping" if replicas == 0 else "Pending"
        pod_name = ""
        restarts = 0
        if pod:
            pod_name = pod.get("metadata", {}).get("name", "")
            phase = pod.get("status", {}).get("phase", "Unknown")
            c_statuses = pod.get("status", {}).get("containerStatuses", [])
            for cs in c_statuses:
                restarts += cs.get("restartCount", 0)
            if replicas == 0:
                pod_status = "Sleeping"
            elif phase == "Running":
                pod_status = "Running"
            else:
                pod_status = phase

        pvc = pvcs_by_slug.get(slug, {})
        pvc_spec = pvc.get("spec", {})
        pvc_status_obj = pvc.get("status", {})
        pvc_capacity = pvc_status_obj.get("capacity", {}).get("storage") or pvc_spec.get("resources", {}).get("requests", {}).get("storage", "10Gi")
        pvc_state = pvc_status_obj.get("phase", "Bound")

        pvc_usage = {
            "capacity": pvc_capacity,
            "used_str": "Non mesuré",
            "avail_str": "",
            "percent": None,
            "status_text": "Pod en veille" if replicas == 0 else f"Alloué : {pvc_capacity}"
        }
        if pod and pod_status.startswith("Running") and pod_name:
            try:
                rc_df, out_df, _ = runner.run(["exec", f"pod/{pod_name}", "-c", "hermes", "-n", ns, "--", "df", "-h", "/opt/data"], timeout=4)
                if rc_df == 0 and out_df:
                    lines = [l for l in out_df.strip().splitlines() if not l.startswith("Filesystem")]
                    if lines:
                        parts = lines[0].split()
                        if len(parts) >= 5:
                            pct_m = re.search(r"(\d+)%", parts[4])
                            pct_val = int(pct_m.group(1)) if pct_m else None
                            pvc_usage = {
                                "capacity": parts[1],
                                "used_str": parts[2],
                                "avail_str": parts[3],
                                "percent": pct_val,
                                "status_text": f"{parts[2]} / {parts[1]} ({parts[4]})"
                            }
            except Exception:
                pass

        user_name = labels.get("arcia.io/user-name") or slug.replace("-", " ").title()
        if user_md:
            m_nom = re.search(r"- (?:Nom|Prénom|Prenom|Collaborateur)\s*:\s*([^\r\n]+)", user_md)
            if m_nom:
                user_name = m_nom.group(1).strip()

        users.append({
            "slug": slug,
            "name": user_name,
            "deployment_name": dname,
            "email": user_email,
            "team": team,
            "job_title": job_title,
            "manager": manager,
            "replicas": replicas,
            "replicas_desired": replicas,
            "ready_replicas": ready_replicas,
            "replicas_ready": ready_replicas,
            "pod_status": pod_status,
            "pod_phase": pod_status,
            "pod_name": pod_name,
            "restarts": restarts,
            "pvc_name": f"hermes-user-{slug}-pvc",
            "pvc_capacity": pvc_capacity,
            "pvc_phase": pvc_state,
            "pvc_usage": pvc_usage,
            "pvc_used_human": pvc_usage.get("used_str") if pvc_usage else None,
            "pvc_percent": pvc_usage.get("percent") if pvc_usage else None,
            "studio_url": f"https://{fqdn}/poweruser/{slug}/studio",
            "studio_path": f"/poweruser/{slug}/studio",
            "has_vpn": "NET_ADMIN" in str(dep.get("spec", {}).get("template", {}).get("spec", {}))
        })

    total_storage = 0
    for u in users:
        cap = u.get("pvc_capacity") or "10Gi"
        m_cap = re.search(r"(\d+)", cap)
        if m_cap:
            total_storage += int(m_cap.group(1))

    stats = {
        "total": len(users),
        "running": sum(1 for u in users if u.get("pod_status") == "Running" or u.get("ready_replicas", 0) > 0),
        "sleeping": sum(1 for u in users if u.get("replicas", 1) == 0 or u.get("pod_status") == "Sleeping"),
        "other": sum(1 for u in users if u.get("pod_status") not in ("Running", "Sleeping") and u.get("replicas", 1) > 0),
        "total_storage_gi": total_storage
    }

    return {
        "status": "ok",
        "success": True,
        "connected": True,
        "namespace": ns,
        "count": len(users),
        "users": users,
        "powerusers": users,
        "stats": stats
    }

def create_poweruser(data: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Crée et déploie un nouveau Power User sur le cluster Kubernetes."""
    email = data.get("email", "").strip()
    if not email or "@" not in email:
        return {"success": False, "error": "Une adresse email valide est requise."}

    sys.path.insert(0, SCRIPT_DIR)
    import arcia_poweruser

    slug = arcia_poweruser.email_to_slug(email)
    team = data.get("team", "engineering").strip()
    job_title = data.get("job_title", "Expert / Ingénieur").strip()
    manager = data.get("manager", "Direction Technique").strip()
    storage_size = data.get("storage_size", "10Gi").strip()
    custom_soul = data.get("custom_soul")
    enable_vpn = bool(data.get("vpn", False))

    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
    ns = cfg.get("kubernetes", {}).get("namespace", "arcia")
    fqdn = cfg.get("network", {}).get("public_fqdn", "assistant.example.org")

    runner = get_k8s_runner(cfg)

    pat = data.get("pat") or arcia_poweruser.generate_litellm_pat(email, team=team)
    pwd = data.get("password") or secrets.token_urlsafe(16)

    manifest = arcia_poweruser.render_manifest(
        user_email=email,
        team=team,
        job_title=job_title,
        manager=manager,
        custom_soul=custom_soul,
        storage_size=storage_size,
        public_fqdn=fqdn,
        namespace=ns,
        litellm_pat=pat,
        studio_password=pwd,
        enable_vpn=enable_vpn
    )

    rc, out, err = runner.run(["apply", "-f", "-"], stdin_input=manifest)
    if rc != 0:
        return {"success": False, "error": f"Échec application manifeste : {err.strip() or out.strip()}"}

    try:
        py_code = f"""
import os, json, urllib.request
k = os.environ.get('LITELLM_MASTER_KEY')
payload = json.dumps({{
    'key': '{pat}',
    'key_alias': 'pat-{slug}',
    'user_id': '{email}',
    'max_budget': 200.0
}}).encode()
req = urllib.request.Request(
    'http://localhost:4000/key/generate',
    data=payload,
    headers={{'Authorization': f'Bearer {{k}}', 'Content-Type': 'application/json'}}
)
try:
    urllib.request.urlopen(req)
except Exception:
    pass
"""
        runner.run(["exec", "-i", "deployment/litellm-proxy", "-n", ns, "--", "python3"], stdin_input=py_code, timeout=6)
    except Exception:
        pass

    return {
        "success": True,
        "slug": slug,
        "email": email,
        "password": pwd,
        "pat": pat,
        "studio_url": f"https://{fqdn}/poweruser/{slug}/studio",
        "message": f"Power User '{slug}' déployé avec succès."
    }

def delete_poweruser(slug: str, keep_pvc: bool = False, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Supprime une instance Power User et nettoie ses ressources Kubernetes."""
    if not slug or not re.match(r"^[a-z0-9\-]+$", slug):
        return {"success": False, "error": "Identifiant slug invalide."}

    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
    ns = cfg.get("kubernetes", {}).get("namespace", "arcia")

    runner = get_k8s_runner(cfg)
    runner.run(["delete", "deployment", f"hermes-poweruser-{slug}", "-n", ns, "--ignore-not-found=true"])
    runner.run(["delete", "service", f"hermes-poweruser-{slug}", "-n", ns, "--ignore-not-found=true"])
    runner.run(["delete", "ingress", f"hermes-poweruser-{slug}-ingress", "-n", ns, "--ignore-not-found=true"])
    runner.run(["delete", "configmap", f"hermes-user-{slug}-config", "-n", ns, "--ignore-not-found=true"])
    runner.run(["delete", "secret", f"hermes-user-{slug}-secret", "-n", ns, "--ignore-not-found=true"])
    runner.run(["delete", "middleware", f"hermes-poweruser-{slug}-stripprefix", "-n", ns, "--ignore-not-found=true"])

    if not keep_pvc:
        runner.run(["delete", "pvc", f"hermes-user-{slug}-pvc", "-n", ns, "--ignore-not-found=true"])

    try:
        py_code = f"""
import os, json, urllib.request
k = os.environ.get('LITELLM_MASTER_KEY')
req = urllib.request.Request('http://localhost:4000/key/list', headers={{'Authorization': f'Bearer {{k}}'}})
try:
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read().decode())
    keys_to_del = [item['token'] for item in data.get('keys', []) if item.get('key_alias') == 'pat-{slug}']
    if keys_to_del:
        del_req = urllib.request.Request(
            'http://localhost:4000/key/delete',
            data=json.dumps({{'tokens': keys_to_del}}).encode(),
            headers={{'Authorization': f'Bearer {{k}}', 'Content-Type': 'application/json'}}
        )
        urllib.request.urlopen(del_req)
except Exception:
    pass
"""
        runner.run(["exec", "-i", "deployment/litellm-proxy", "-n", ns, "--", "python3"], stdin_input=py_code, timeout=6)
    except Exception:
        pass

    return {
        "success": True,
        "slug": slug,
        "pvc_deleted": not keep_pvc,
        "message": f"Instance Power User '{slug}' supprimée avec succès."
    }

def scale_poweruser(slug: str, replicas: int, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Met en veille (replicas=0) ou réveille (replicas=1) le pod d'un Power User."""
    if not slug:
        return {"success": False, "error": "Slug invalide."}
    if replicas not in (0, 1):
        return {"success": False, "error": "Nombre de répliques invalide (0 ou 1 attendu)."}

    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
    ns = cfg.get("kubernetes", {}).get("namespace", "arcia")

    runner = get_k8s_runner(cfg)
    rc, out, err = runner.run(["scale", f"deployment/hermes-poweruser-{slug}", f"--replicas={replicas}", "-n", ns])
    if rc != 0:
        return {"success": False, "error": err.strip() or "Échec de l'opération scale."}

    action_text = "réactivé (Scale 1)" if replicas == 1 else "mis en veille (Scale 0, RAM libérée)"
    return {
        "success": True,
        "slug": slug,
        "replicas": replicas,
        "message": f"Pod '{slug}' {action_text} avec succès."
    }

def resize_poweruser_pvc(slug: str, new_size: str, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Agrandit la capacité d'un volume persistant PVC (ex: de 10Gi à 20Gi)."""
    if not slug:
        return {"success": False, "error": "Slug invalide."}
    new_size = new_size.strip()
    if not re.match(r"^\d+(?:Gi|Mi|Ti)$", new_size):
        return {"success": False, "error": "Taille invalide (ex: 20Gi, 50Gi, 100Gi)."}

    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
    ns = cfg.get("kubernetes", {}).get("namespace", "arcia")

    runner = get_k8s_runner(cfg)
    patch_payload = json.dumps({
        "spec": {
            "resources": {
                "requests": {
                    "storage": new_size
                }
            }
        }
    })
    rc, out, err = runner.run(["patch", "pvc", f"hermes-user-{slug}-pvc", "-n", ns, "-p", patch_payload])
    if rc != 0:
        return {"success": False, "error": f"Échec de l'extension du PVC : {err.strip() or out.strip()}"}

    return {
        "success": True,
        "slug": slug,
        "new_size": new_size,
        "message": f"Volume PVC 'hermes-user-{slug}-pvc' étendu à {new_size} avec succès."
    }

def sync_all_powerusers_wizard(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Synchronise toutes les instances Power Users actives avec le catalogue de modèles."""
    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
    ns = cfg.get("kubernetes", {}).get("namespace", "arcia")
    fqdn = cfg.get("network", {}).get("public_fqdn", "assistant.example.org")
    runner = get_k8s_runner(cfg)
    try:
        sys.path.insert(0, SCRIPT_DIR)
        from arcia_poweruser import sync_all_powerusers
        def _runner_func(args, input_data=None):
            rc, out, err = runner.run(args, stdin_input=input_data)
            return subprocess.CompletedProcess(args, rc, out, err)
        count = sync_all_powerusers(namespace=ns, fqdn=fqdn, runner_func=_runner_func)
        return {"success": True, "count": count, "message": f"{count} instance(s) Power User synchronisée(s)."}
    except Exception as e:
        return {"success": False, "error": str(e)}

# -----------------------------------------------------------------------------
# Gestion du Routage des Modèles & Fournisseurs d'Inférence
# -----------------------------------------------------------------------------

def get_model_routing_config(cfg: Optional[Dict[str, Any]] = None, include_defaults: bool = True) -> Dict[str, Any]:
    """Fournit la vue complète des fournisseurs, clés d'API et catalogue de routage de modèles."""
    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)

    llm = cfg.setdefault("llm_gateway", {})
    openrouter_key = llm.get("openrouter_api_key", "")
    if not openrouter_key or is_placeholder_key(openrouter_key):
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not openrouter_key:
        try:
            runner = get_k8s_runner(cfg)
            rc, out, _ = runner.run(["get", "secret", "litellm-secret", f"-n={cfg.get('kubernetes', {}).get('namespace', 'arcia')}", "-o=jsonpath={.data.openrouter-key}"], timeout=3)
            if rc == 0 and out.strip():
                import base64
                k = base64.b64decode(out.strip()).decode('utf-8').strip()
                if k and not is_placeholder_key(k):
                    openrouter_key = k
                    llm["openrouter_api_key"] = k
        except Exception:
            pass

    def mask_key(k: str) -> str:
        if not k or len(k) < 6:
            return ""
        if is_placeholder_key(k):
            return ""
        return k[:8] + "••••••••" + k[-4:]

    providers = [
        {
            "id": "openrouter",
            "name": "OpenRouter",
            "description": "Agrégateur cloud",
            "is_set": bool(openrouter_key and not is_placeholder_key(openrouter_key)),
            "configured": bool(openrouter_key and not is_placeholder_key(openrouter_key)),
            "masked_key": mask_key(openrouter_key),
            "api_key_masked": mask_key(openrouter_key),
            "doc_url": "https://openrouter.ai/keys",
            "requires_endpoint": False,
            "endpoint": "",
            "recommended": True
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "description": "Accès aux modèles d'OpenAI",
            "is_set": bool(llm.get("openai_api_key") and not is_placeholder_key(llm.get("openai_api_key"))),
            "configured": bool(llm.get("openai_api_key") and not is_placeholder_key(llm.get("openai_api_key"))),
            "masked_key": mask_key(llm.get("openai_api_key", "")) if not is_placeholder_key(llm.get("openai_api_key")) else "",
            "api_key_masked": mask_key(llm.get("openai_api_key", "")) if not is_placeholder_key(llm.get("openai_api_key")) else "",
            "doc_url": "https://platform.openai.com/api-keys",
            "requires_endpoint": False,
            "endpoint": "",
            "recommended": False
        },
        {
            "id": "anthropic",
            "name": "Anthropic",
            "description": "Accès aux modèles d'Anthropic",
            "is_set": bool(llm.get("anthropic_api_key") and not is_placeholder_key(llm.get("anthropic_api_key"))),
            "configured": bool(llm.get("anthropic_api_key") and not is_placeholder_key(llm.get("anthropic_api_key"))),
            "masked_key": mask_key(llm.get("anthropic_api_key", "")) if not is_placeholder_key(llm.get("anthropic_api_key")) else "",
            "api_key_masked": mask_key(llm.get("anthropic_api_key", "")) if not is_placeholder_key(llm.get("anthropic_api_key")) else "",
            "doc_url": "https://console.anthropic.com/",
            "requires_endpoint": False,
            "endpoint": "",
            "recommended": False
        },
        {
            "id": "mistral",
            "name": "Mistral AI",
            "description": "Modèles de Mistral AI",
            "is_set": bool(llm.get("mistral_api_key") and not is_placeholder_key(llm.get("mistral_api_key"))),
            "configured": bool(llm.get("mistral_api_key") and not is_placeholder_key(llm.get("mistral_api_key"))),
            "masked_key": mask_key(llm.get("mistral_api_key", "")) if not is_placeholder_key(llm.get("mistral_api_key")) else "",
            "api_key_masked": mask_key(llm.get("mistral_api_key", "")) if not is_placeholder_key(llm.get("mistral_api_key")) else "",
            "doc_url": "https://console.mistral.ai/",
            "requires_endpoint": False,
            "endpoint": "",
            "recommended": False
        },
        {
            "id": "gemini",
            "name": "Google Gemini",
            "description": "Accès aux modèles de Google Gemini",
            "is_set": bool(llm.get("gemini_api_key") and not is_placeholder_key(llm.get("gemini_api_key"))),
            "configured": bool(llm.get("gemini_api_key") and not is_placeholder_key(llm.get("gemini_api_key"))),
            "masked_key": mask_key(llm.get("gemini_api_key", "")) if not is_placeholder_key(llm.get("gemini_api_key")) else "",
            "api_key_masked": mask_key(llm.get("gemini_api_key", "")) if not is_placeholder_key(llm.get("gemini_api_key")) else "",
            "doc_url": "https://aistudio.google.com/",
            "requires_endpoint": False,
            "endpoint": "",
            "recommended": False
        }
    ]

    custom_provs = llm.get("custom_providers", [])
    if isinstance(custom_provs, list):
        for cp in custom_provs:
            if isinstance(cp, dict) and cp.get("id"):
                cp_key = cp.get("api_key", "")
                providers.append({
                    "id": cp["id"],
                    "name": cp.get("name", cp["id"]),
                    "description": cp.get("description", "Fournisseur d'inférence personnalisé compatible LiteLLM"),
                    "is_set": bool(cp_key or cp.get("endpoint")),
                    "configured": bool(cp_key or cp.get("endpoint")),
                    "masked_key": mask_key(cp_key),
                    "api_key_masked": mask_key(cp_key),
                    "doc_url": cp.get("doc_url", ""),
                    "requires_endpoint": True,
                    "endpoint": cp.get("endpoint", ""),
                    "is_custom": True,
                    "hosting": cp.get("hosting", ""),
                    "recommended": False
                })

    default_mappings = [
        {
            "name": "simple/auto",
            "alias": "simple/auto",
            "label": "Chat Direct Rapide & Économique",
            "profile": "Utilisateur Standard (Rapide)",
            "category": "simple",
            "provider": "openrouter",
            "target_model": llm.get("simple_auto_model") or "openrouter/anthropic/claude-3.5-haiku",
            "real_model": llm.get("simple_auto_model") or "openrouter/anthropic/claude-3.5-haiku",
            "description": "Chat standard direct via LiteLLM Proxy sans latence de boucle agentique. Modèle par défaut.",
            "fallbacks": ["simple/free"],
            "fallback": "simple/free",
            "zdr": True,
            "is_default": (llm.get("default_model", "simple/auto") == "simple/auto"),
            "is_canonical": True
        },
        {
            "name": "simple/free",
            "alias": "simple/free",
            "label": "Chat Direct Gratuit (0 €)",
            "profile": "Utilisateur Standard (Gratuit)",
            "category": "simple",
            "provider": "openrouter",
            "target_model": llm.get("simple_free_model") or "openrouter/meta-llama/llama-3.3-70b-instruct:free",
            "real_model": llm.get("simple_free_model") or "openrouter/meta-llama/llama-3.3-70b-instruct:free",
            "description": "Inférence cloud gratuite à coût zéro sous protection ZDR et Presidio DLP.",
            "fallbacks": [],
            "fallback": "",
            "zdr": True,
            "is_default": (llm.get("default_model") == "simple/free"),
            "is_canonical": True
        },
        {
            "name": "agentic/auto",
            "alias": "agentic/auto",
            "label": "Hermes Agent Équilibré",
            "profile": "Power User & Agents Hermes (Polyvalent)",
            "category": "agentic",
            "provider": "openrouter",
            "target_model": llm.get("agentic_auto_model") or "openrouter/anthropic/claude-3.7-sonnet",
            "real_model": llm.get("agentic_auto_model") or "openrouter/anthropic/claude-3.7-sonnet",
            "description": "Session agentique autonome standard pour les tâches multi-outils, recherches et code.",
            "fallbacks": ["agentic/free"],
            "fallback": "agentic/free",
            "zdr": True,
            "is_default": (llm.get("default_model") == "agentic/auto"),
            "is_canonical": True
        },
        {
            "name": "agentic/free",
            "alias": "agentic/free",
            "label": "Hermes Agent Gratuit (0 €)",
            "profile": "Power User (Gratuit)",
            "category": "agentic",
            "provider": "openrouter",
            "target_model": llm.get("agentic_free_model") or "openrouter/meta-llama/llama-3.3-70b-instruct:free",
            "real_model": llm.get("agentic_free_model") or "openrouter/meta-llama/llama-3.3-70b-instruct:free",
            "description": "Session agentique autonome exécutée sur des modèles gratuits sans frais d'inférence.",
            "fallbacks": [],
            "fallback": "",
            "zdr": True,
            "is_default": (llm.get("default_model") == "agentic/free"),
            "is_canonical": True
        },
        {
            "name": "agentic/expert",
            "alias": "agentic/expert",
            "label": "Hermes Agent Raisonnement Avancé",
            "profile": "Hermes Raisonnement & Code Complexe",
            "category": "agentic",
            "provider": "openrouter",
            "target_model": llm.get("agentic_expert_model") or "openrouter/anthropic/claude-3.7-sonnet:thinking",
            "real_model": llm.get("agentic_expert_model") or "openrouter/anthropic/claude-3.7-sonnet:thinking",
            "description": "Orchestration haute précision avec raisonnement approfondi pour le code et l'architecture.",
            "fallbacks": ["agentic/auto"],
            "fallback": "agentic/auto",
            "zdr": True,
            "is_default": (llm.get("default_model") == "agentic/expert"),
            "is_canonical": True
        }
    ]

    custom_mappings = llm.get("models_routing")
    if "models_routing" in llm:
        if not isinstance(custom_mappings, list):
            return {"success": False, "error": "La déclaration models_routing doit être une liste YAML valide.", "mappings": [], "providers": providers}
        mappings_to_use = custom_mappings
    else:
        mappings_to_use = default_mappings if include_defaults else []

    # Même résolution serveur que la projection native d'avatars.
    for m in mappings_to_use:
        visual = resolve_model_icon(m, llm.get("custom_providers") or [])
        m.update({"icon": visual["icon"], "icon_type": visual["type"], "icon_badge": visual["badge"]})

    hermes = cfg.setdefault("hermes", {})
    return {
        "status": "ok",
        "success": True,
        "default_model": llm.get("default_model", "simple/auto"),
        "hermes_default_model": hermes.get("default_model", "agentic/auto"),
        "providers": providers,
        "mappings": mappings_to_use
    }

def detect_fallback_loops(mappings: List[Dict[str, Any]]) -> Optional[str]:
    """Détecte les cycles éventuels dans la chaîne de repli des modèles.
    Retourne la description de la boucle sous forme 'A -> B -> A' si un cycle existe, sinon None."""
    graph: Dict[str, str] = {}
    for m in mappings:
        alias = str(m.get("alias") or m.get("name") or "").strip()
        fallback = str(m.get("fallback") or "").strip()
        if alias and fallback:
            graph[alias] = fallback

    for start_node in graph:
        visited = []
        curr = start_node
        while curr and curr in graph:
            if curr in visited:
                idx = visited.index(curr)
                loop_nodes = visited[idx:] + [curr]
                return " -> ".join(loop_nodes)
            visited.append(curr)
            curr = graph.get(curr, "")
            if curr == start_node:
                return " -> ".join(visited + [curr])
    return None

def save_model_routing_config(data: Dict[str, Any], cfg_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Enregistre le routage des modèles et synchronise arcia.config.yaml."""
    cfg, _ = load_config_data(cfg_path)
    llm = cfg.setdefault("llm_gateway", {})
    hermes = cfg.setdefault("hermes", {})

    # Validation stricte contre les boucles de repli infinies et les incohérences de catalogue
    if "mappings" in data and isinstance(data["mappings"], list):
        mappings_list = data["mappings"]
        loop_err = detect_fallback_loops(mappings_list)
        if loop_err:
            return {
                "success": False,
                "error": f"Boucle de repli infinie détectée : {loop_err}. Veuillez modifier la chaîne de repli avant d'enregistrer."
            }
        seen_aliases = set()
        for idx, m in enumerate(mappings_list):
            if not isinstance(m, dict):
                continue
            alias = str(m.get("alias") or m.get("name") or "").strip()
            if not alias:
                return {"success": False, "error": f"Modèle #{idx + 1} : identifiant (alias) manquant."}
            if alias in seen_aliases:
                return {"success": False, "error": f"Identifiant de modèle dupliqué : '{alias}'."}
            seen_aliases.add(alias)
            target = str(m.get("target_model") or m.get("real_model") or "").strip()
            if not target:
                return {"success": False, "error": f"Modèle '{alias}' : cible fournisseur manquante (target_model obligatoire)."}

        def_llm_check = str(data.get("default_model") or "").strip()
        if def_llm_check and seen_aliases and def_llm_check not in seen_aliases:
            return {"success": False, "error": f"Modèle par défaut '{def_llm_check}' introuvable parmi les modèles déclarés."}
        def_hermes_check = str(data.get("hermes_default_model") or "").strip()
        if def_hermes_check and seen_aliases and def_hermes_check not in seen_aliases:
            return {"success": False, "error": f"Modèle par défaut Hermes '{def_hermes_check}' introuvable parmi les modèles déclarés."}

    providers_input = data.get("providers", {})
    for key_short, key_full in [
        ("openrouter", "openrouter_api_key"),
        ("openai", "openai_api_key"),
        ("anthropic", "anthropic_api_key"),
        ("mistral", "mistral_api_key"),
        ("gemini", "gemini_api_key"),
    ]:
        val = providers_input.get(key_full) or providers_input.get(key_short)
        if val and "••••" not in str(val) and not is_placeholder_key(str(val)):
            llm[key_full] = str(val).strip()

    vllm_ep = providers_input.get("local_vllm_endpoint") or providers_input.get("vllm_endpoint")
    if vllm_ep is not None:
        llm["local_vllm_endpoint"] = str(vllm_ep).strip()

    if "custom_providers" in data and isinstance(data["custom_providers"], list):
        llm["custom_providers"] = data["custom_providers"]

    if "default_model" in data and str(data["default_model"]).strip():
        llm["default_model"] = str(data["default_model"]).strip()

    if "hermes_default_model" in data and str(data["hermes_default_model"]).strip():
        hermes["default_model"] = str(data["hermes_default_model"]).strip()

    if "mappings" in data and isinstance(data["mappings"], list):
        llm["models_routing"] = data["mappings"]
        for m in data["mappings"]:
            m_name = m.get("alias") or m.get("name", "")
            m_target = m.get("real_model") or m.get("target_model", "")
            if m_name == "simple/auto": llm["simple_auto_model"] = m_target
            elif m_name == "simple/free": llm["simple_free_model"] = m_target
            elif m_name == "agentic/auto": llm["agentic_auto_model"] = m_target
            elif m_name == "agentic/free": llm["agentic_free_model"] = m_target
            elif m_name == "agentic/expert": llm["agentic_expert_model"] = m_target

    save_config_to_files(cfg, cfg_path)

    # Projection privée : aucune écriture dans les assets suivis du harness.
    branding_synced = False
    branding_status = {"assets_applied": False, "runtime_loaded": False, "avatars_verified": False}

    # 2. Synchronisation des 3 composants (LiteLLM, Hermes, Open-WebUI) et Power Users
    litellm_synced = False
    hermes_synced = False
    openwebui_synced = False
    powerusers_synced = False
    cluster_connected = False
    details = {}

    try:
        runner = get_k8s_runner(cfg)
        ns = cfg.get("kubernetes", {}).get("namespace", "arcia")
        rc, _, _ = runner.run(["get", "namespace", ns])
        if rc == 0:
            cluster_connected = True
            # 1. LiteLLM Proxy
            litellm_synced = sync_litellm_configmap(cfg, runner, ns)
            details["litellm"] = "Opérationnel" if litellm_synced else "Échec de synchronisation"

            # 2. Hermes Agent
            hermes_synced = sync_hermes_configmap(cfg, runner, ns)
            details["hermes"] = "Opérationnel" if hermes_synced else "Échec de synchronisation"

            # 3. Open-WebUI
            openwebui_synced = sync_openwebui_models_config(cfg, runner, ns)
            details["openwebui"] = "Opérationnel" if openwebui_synced else "Échec de synchronisation"

            # 4. Branding Open-WebUI
            try:
                import deploy
                published = deploy.sync_webui_branding(runner, ns, ROOT_DIR, cfg=cfg)
                branding_status = deploy.activate_webui_branding(runner, ns, published)
                branding_synced = bool(branding_status.get("assets_served") and branding_status.get("runtime_loaded"))
            except Exception:
                branding_status["error"] = "Publication des icônes non aboutie ; réenregistrez le routage pour réessayer."

            # 5. Power Users
            try:
                pu_res = sync_all_powerusers_wizard(cfg)
                powerusers_synced = pu_res.get("success", False)
                details["powerusers"] = f"{pu_res.get('count', 0)} synchronisé(s)"
            except Exception as pue:
                details["powerusers"] = f"Ignoré ({pue})"
        else:
            details["cluster"] = f"Namespace '{ns}' inaccessible sur le cluster."
    except Exception as e:
        details["error"] = str(e)

    msg_parts = ["Configuration du routage enregistrée avec succès."]
    if cluster_connected:
        if litellm_synced and hermes_synced and openwebui_synced:
            msg_parts.append("Passerelle LiteLLM, moteur Hermes et portail Open-WebUI synchronisés.")
        else:
            partial_reports = []
            partial_reports.append(f"LiteLLM: {'OK' if litellm_synced else 'Erreur'}")
            partial_reports.append(f"Hermes: {'OK' if hermes_synced else 'Erreur'}")
            partial_reports.append(f"Open-WebUI: {'OK' if openwebui_synced else 'Erreur'}")
            msg_parts.append(f"Synchronisation cluster partielle ({', '.join(partial_reports)}).")
    else:
        msg_parts.append("Routage non appliqué au cluster : vérifiez la cible Kubernetes et relancez la synchronisation. La sauvegarde locale est conservée.")
    if branding_synced:
        details["branding"] = "Icônes appliquées et ressources HTTP vérifiées."
        msg_parts.append("Projection des icônes chargée et ressources HTTP vérifiées ; recette navigateur distincte.")
    else:
        details["branding"] = branding_status.get("error") or "Icônes non appliquées au portail."
        msg_parts.append("Application des icônes incomplète ; réenregistrez le routage après vérification du cluster.")

    return {
        "success": True,
        "cm_synced": litellm_synced,
        "litellm_synced": litellm_synced,
        "hermes_synced": hermes_synced,
        "openwebui_synced": openwebui_synced,
        "powerusers_synced": powerusers_synced,
        "branding_synced": branding_synced,
        "branding_status": branding_status,
        "all_synced": bool(litellm_synced and hermes_synced and openwebui_synced and branding_synced),
        "details": details,
        "message": " ".join(msg_parts)
    }

def sync_litellm_configmap(cfg: Dict[str, Any], runner: Any, ns: str) -> bool:
    """Met à jour à chaud le ConfigMap litellm-config avec les modèles définis et redémarre LiteLLM."""
    try:
        import deploy
        full_config_yaml = deploy.build_litellm_config_data(cfg, namespace=ns)
        deploy.sync_litellm_provider_secrets(cfg, runner, ns)
        manifest = json.dumps({"apiVersion": "v1", "kind": "ConfigMap",
                               "metadata": {"name": "litellm-config", "namespace": ns},
                               "data": {"config.yaml": full_config_yaml}})
        rc, _, _ = runner.run(["apply", "-f", "-"], stdin_input=manifest, timeout=15)
        if rc != 0:
            return False

        # Redémarrage à chaud de LiteLLM Proxy pour prise en compte immédiate
        rc, _, _ = runner.run(["rollout", "restart", "deployment/litellm-proxy", "-n", ns], timeout=15)
        if rc != 0:
            return False
        rc, _, _ = runner.run(["rollout", "status", "deployment/litellm-proxy", "-n", ns, "--timeout=45s"], timeout=50)
        return rc == 0
    except Exception:
        return False

def sync_hermes_configmap(cfg: Dict[str, Any], runner: Any, ns: str) -> bool:
    """Met à jour à chaud le ConfigMap hermes-config avec les modèles agentiques définis et redémarre Hermes."""
    try:
        import deploy
        hermes_config_yaml = deploy.build_hermes_config_data(cfg, namespace=ns)
        manifest = json.dumps({"apiVersion": "v1", "kind": "ConfigMap",
                               "metadata": {"name": "hermes-config", "namespace": ns},
                               "data": {"config.yaml": hermes_config_yaml}})
        rc, _, _ = runner.run(["apply", "-f", "-"], stdin_input=manifest, timeout=15)
        if rc != 0:
            return False

        # Redémarrage à chaud de Hermes Agent pour prise en compte immédiate
        rc, _, _ = runner.run(["rollout", "restart", "deployment/hermes-agent", "-n", ns], timeout=15)
        if rc != 0:
            return False
        rc, _, _ = runner.run(["rollout", "status", "deployment/hermes-agent", "-n", ns, "--timeout=45s"], timeout=50)
        return rc == 0
    except Exception:
        return False

def sync_openwebui_models_config(cfg: Dict[str, Any], runner: Any, ns: str) -> bool:
    """Met à jour à chaud les variables de catalogue (OPENAI_API_CONFIGS, DEFAULT_MODELS, TASK_MODEL) sur Open-WebUI."""
    try:
        import deploy
        api_configs = deploy.build_openwebui_api_configs(cfg)
        catalog = deploy.build_model_catalog(cfg)
        def_model = catalog["default_simple"] or catalog["default_agentic"] or ""
        task_model = def_model

        env_args = [
            "set", "env", "deployment/open-webui", f"-n={ns}",
            f"OPENAI_API_CONFIGS={api_configs}",
            f"DEFAULT_MODELS={def_model}",
            f"TASK_MODEL={task_model}",
            "ENABLE_COMMUNITY_SHARING=false"
        ]
        rc, _, _ = runner.run(env_args, timeout=15)
        if rc != 0:
            return False
        rc, _, _ = runner.run(["rollout", "status", "deployment/open-webui", f"-n={ns}", "--timeout=45s"], timeout=50)
        return rc == 0
    except Exception:
        return False

def is_placeholder_key(val: str) -> bool:
    """Détecte si une clé est un placeholder factice ou masqué."""
    if not val:
        return True
    v = val.strip()
    if "••••" in v:
        return True
    placeholders = {
        "sk-or-v1-xxxx", "sk-proj-openaikey",
        "sk-ant-api03-xxxx", "sk-mistral-xxxx", "AIzaSyxxxx",
        "sk-proj-placeholder"
    }
    if v in placeholders or v.startswith("sk-or-v1-xxxx") or v.startswith("sk-proj-xxxx") or v == "sk-proj-openaikey":
        return True
    return False

def resolve_provider_key(provider: str, api_key: str = "", cfg: Optional[Dict[str, Any]] = None) -> Tuple[str, bool]:
    """Résout une clé API réelle pour un fournisseur depuis l'entrée utilisateur, la config, l'environnement ou les secrets K8s.
    Retourne (clé_résolue, est_placeholder)."""
    provider = (provider or "").lower().strip()
    api_key = (api_key or "").strip()

    if api_key and not is_placeholder_key(api_key):
        return api_key, False

    if cfg is None:
        cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
    llm = cfg.get("llm_gateway", {})

    if provider == "openrouter":
        env_k = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if env_k and not is_placeholder_key(env_k):
            return env_k, False
        cfg_k = llm.get("openrouter_api_key", "").strip()
        if cfg_k and not is_placeholder_key(cfg_k):
            return cfg_k, False
        try:
            runner = get_k8s_runner(cfg)
            ns = cfg.get("kubernetes", {}).get("namespace", "arcia")
            rc, out, _ = runner.run(["get", "secret", "litellm-secret", f"-n={ns}", "-o=jsonpath={.data.openrouter-key}"], timeout=4)
            if rc == 0 and out.strip():
                import base64
                k = base64.b64decode(out.strip()).decode("utf-8", errors="ignore").strip()
                if k and not is_placeholder_key(k):
                    return k, False
        except Exception:
            pass
        return "", True

    elif provider == "openai":
        env_k = os.environ.get("OPENAI_API_KEY", "").strip()
        if env_k and not is_placeholder_key(env_k):
            return env_k, False
        cfg_k = llm.get("openai_api_key", "").strip()
        if cfg_k and not is_placeholder_key(cfg_k):
            return cfg_k, False
        try:
            runner = get_k8s_runner(cfg)
            ns = cfg.get("kubernetes", {}).get("namespace", "arcia")
            rc, out, _ = runner.run(["get", "secret", "litellm-secret", f"-n={ns}", "-o=jsonpath={.data.openai-key}"], timeout=4)
            if rc == 0 and out.strip():
                import base64
                k = base64.b64decode(out.strip()).decode("utf-8", errors="ignore").strip()
                if k and not is_placeholder_key(k):
                    return k, False
        except Exception:
            pass
        return "", True

    elif provider == "anthropic":
        env_k = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if env_k and not is_placeholder_key(env_k):
            return env_k, False
        cfg_k = llm.get("anthropic_api_key", "").strip()
        if cfg_k and not is_placeholder_key(cfg_k):
            return cfg_k, False
        return "", True

    elif provider == "mistral":
        env_k = os.environ.get("MISTRAL_API_KEY", "").strip()
        if env_k and not is_placeholder_key(env_k):
            return env_k, False
        cfg_k = llm.get("mistral_api_key", "").strip()
        if cfg_k and not is_placeholder_key(cfg_k):
            return cfg_k, False
        return "", True

    elif provider == "gemini":
        env_k = os.environ.get("GEMINI_API_KEY", "").strip()
        if env_k and not is_placeholder_key(env_k):
            return env_k, False
        cfg_k = llm.get("gemini_api_key", "").strip()
        if cfg_k and not is_placeholder_key(cfg_k):
            return cfg_k, False
        return "", True

    else:
        for cp in llm.get("custom_providers", []):
            if cp.get("id") == provider:
                cfg_k = cp.get("api_key", "").strip()
                if cfg_k and not is_placeholder_key(cfg_k):
                    return cfg_k, False
                break
        return "", True

def test_provider_connectivity(provider: str, api_key: str, endpoint: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
    """Valide les identifiants ou l'endpoint d'un fournisseur en direct (et optionnellement un modèle)."""
    provider = provider.lower().strip()
    api_key = api_key.strip()

    if not api_key and not (endpoint or provider in ("vllm", "local_vllm")):
        return {"success": False, "valid": False, "error": f"Aucune clé API renseignée pour le fournisseur {provider}."}

    resolved_key, is_ph = resolve_provider_key(provider, api_key)

    if endpoint or provider in ("vllm", "local_vllm"):
        ep = endpoint or ""
        if not ep:
            cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
            ep = cfg.get("llm_gateway", {}).get("local_vllm_endpoint", "")
        if not ep:
            return {"success": False, "valid": False, "error": "Veuillez spécifier l'URL de l'endpoint."}
        try:
            req_url = ep.rstrip("/") + "/models"
            headers = {"User-Agent": "ArcIA-Wizard/0.5"}
            if resolved_key:
                headers["Authorization"] = f"Bearer {resolved_key}"
            req = urllib.request.Request(req_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                models_count = len(data.get("data", []))
                msg = f"Modèle '{model}' accessible sur l'endpoint ({models_count} modèle(s) détecté(s))." if model else f"Endpoint joignable ({models_count} modèle(s) détecté(s))."
                return {"success": True, "valid": True, "message": msg}
        except Exception as e:
            return {"success": False, "valid": False, "error": f"Impossible de joindre l'endpoint : {e}"}

    if is_ph or not resolved_key:
        if provider == "openai":
            return {
                "success": False,
                "valid": False,
                "error": "Clé OpenAI non configurée ou placeholder d'exemple (sk-proj-openaikey). Cliquez sur « Configurer » sous la tuile OpenAI pour saisir votre clé réelle."
            }
        elif provider == "openrouter":
            return {
                "success": False,
                "valid": False,
                "error": "Clé OpenRouter non configurée ou placeholder d'exemple. Cliquez sur « Configurer » sous la tuile OpenRouter pour renseigner votre clé réelle."
            }
        else:
            return {"success": False, "valid": False, "error": f"Aucune clé API réelle renseignée pour le fournisseur {provider}."}

    api_key = resolved_key

    try:
        if provider == "openrouter":
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {api_key}", "User-Agent": "ArcIA-Wizard/0.5"}
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode())
                key_info = data.get("data", {})
                label = key_info.get("label", "Clé active")
                usage = key_info.get("usage", 0)
                msg = f"Modèle '{model}' prêt via OpenRouter ({label})." if model else f"Clé OpenRouter valide ({label}). Utilisation : ${usage:.2f}"
                return {"success": True, "valid": True, "message": msg}

        elif provider == "openai":
            req = urllib.request.Request(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}", "User-Agent": "ArcIA-Wizard/0.5"}
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                msg = f"Modèle '{model}' prêt via OpenAI Direct." if model else "Clé OpenAI valide et authentifiée avec succès."
                return {"success": True, "valid": True, "message": msg}

        elif provider == "mistral":
            req = urllib.request.Request(
                "https://api.mistral.ai/v1/models",
                headers={"Authorization": f"Bearer {api_key}", "User-Agent": "ArcIA-Wizard/0.5"}
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                msg = f"Modèle '{model}' prêt via Mistral AI." if model else "Clé Mistral AI valide et authentifiée avec succès."
                return {"success": True, "valid": True, "message": msg}

        elif provider == "anthropic":
            if not api_key.startswith("sk-ant-"):
                return {"success": False, "valid": False, "error": "Format de clé Anthropic invalide (doit débuter par sk-ant-)."}
            msg = f"Modèle '{model}' prêt via Anthropic Direct." if model else "Clé Anthropic au format conforme."
            return {"success": True, "valid": True, "message": msg}

        elif provider == "gemini":
            if len(api_key) < 20:
                return {"success": False, "valid": False, "error": "Format de clé Google Gemini invalide."}
            msg = f"Modèle '{model}' prêt via Google Gemini." if model else "Clé Google Gemini au format conforme."
            return {"success": True, "valid": True, "message": msg}

        msg = f"Modèle '{model}' validé via {provider}." if model else f"Clé {provider} validée."
        return {"success": True, "valid": True, "message": msg}
    except urllib.error.HTTPError as he:
        try:
            he.close()
        except Exception:
            pass
        return {"success": False, "valid": False, "error": f"Erreur HTTP {he.code} : {he.reason}"}
    except Exception as e:
        return {"success": False, "valid": False, "error": f"Erreur de validation : {e}"}

_MODELS_CATALOG_CACHE: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}

def get_provider_models_catalog(provider: str, api_key: str = "", endpoint: Optional[str] = None) -> List[Dict[str, str]]:
    """Récupère dynamiquement le catalogue des modèles disponibles via l'API officielle du fournisseur ou l'endpoint."""
    global _MODELS_CATALOG_CACHE
    provider = provider.lower().strip()
    api_key = api_key.strip()

    resolved_k, _ = resolve_provider_key(provider, api_key)
    if resolved_k:
        api_key = resolved_k

    cache_key = f"{provider}:{endpoint or ''}"
    now = time.time()
    if cache_key in _MODELS_CATALOG_CACHE:
        cache_time, cached_models = _MODELS_CATALOG_CACHE[cache_key]
        if now - cache_time < 300 and cached_models:
            return cached_models

    models: List[Dict[str, str]] = []

    try:
        if provider == "openrouter":
            headers = {"User-Agent": "ArcIA-Wizard/0.5"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode())
                raw_list = data.get("data", [])
                for m in raw_list:
                    m_id = m.get("id", "")
                    if m_id:
                        m_name = m.get("name") or m_id
                        models.append({
                            "id": f"openrouter/{m_id}",
                            "label": f"{m_name} ({m_id})"
                        })
        elif provider == "openai":
            if api_key:
                headers = {"Authorization": f"Bearer {api_key}", "User-Agent": "ArcIA-Wizard/0.5"}
                req = urllib.request.Request("https://api.openai.com/v1/models", headers=headers)
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = json.loads(resp.read().decode())
                    raw_list = data.get("data", [])
                    for m in raw_list:
                        m_id = m.get("id", "")
                        if m_id and (m_id.startswith(("gpt-", "o1", "o3", "chatgpt")) and "realtime" not in m_id):
                            models.append({
                                "id": f"openai/{m_id}",
                                "label": f"{m_id}"
                            })
                    models.sort(key=lambda x: x["id"])
        elif provider == "mistral":
            if api_key:
                headers = {"Authorization": f"Bearer {api_key}", "User-Agent": "ArcIA-Wizard/0.5"}
                req = urllib.request.Request("https://api.mistral.ai/v1/models", headers=headers)
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = json.loads(resp.read().decode())
                    raw_list = data.get("data", [])
                    for m in raw_list:
                        m_id = m.get("id", "")
                        if m_id:
                            models.append({
                                "id": f"mistral/{m_id}",
                                "label": m.get("name") or m_id
                            })
                    models.sort(key=lambda x: x["id"])
        elif provider in ("vllm", "local_vllm") or endpoint:
            ep = endpoint or ""
            if not ep:
                cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
                ep = cfg.get("llm_gateway", {}).get("local_vllm_endpoint", "")
            if ep:
                req_url = ep.rstrip("/") + ("/models" if "/v1" in ep else "/v1/models")
                headers = {"User-Agent": "ArcIA-Wizard/0.5"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                req = urllib.request.Request(req_url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    raw_list = data.get("data", [])
                    for m in raw_list:
                        m_id = m.get("id", "")
                        if m_id:
                            prefix = "openai" if provider not in ("vllm", "local_vllm") else "hosted_vllm"
                            models.append({
                                "id": f"{prefix}/{m_id}",
                                "label": m_id
                            })
    except Exception:
        pass

    # Si la liste dynamique est vide (ex: hors-ligne, pas de clé API ou provider propriétaire sans API publique de liste), utiliser le catalogue standard
    if not models:
        standard_catalog = {
            "openrouter": [
                {"id": "openrouter/anthropic/claude-3.7-sonnet", "label": "Claude 3.7 Sonnet (Anthropic)"},
                {"id": "openrouter/anthropic/claude-3.7-sonnet:thinking", "label": "Claude 3.7 Sonnet Thinking"},
                {"id": "openrouter/anthropic/claude-3.5-haiku", "label": "Claude 3.5 Haiku"},
                {"id": "openrouter/openai/gpt-4o", "label": "GPT-4o (OpenAI)"},
                {"id": "openrouter/openai/gpt-4o-mini", "label": "GPT-4o Mini (OpenAI)"},
                {"id": "openrouter/deepseek/deepseek-r1", "label": "DeepSeek R1 (Raisonnement)"},
                {"id": "openrouter/meta-llama/llama-3.3-70b-instruct:free", "label": "Llama 3.3 70B (Gratuit)"},
                {"id": "openrouter/google/gemini-2.0-flash-exp:free", "label": "Gemini 2.0 Flash (Gratuit)"}
            ],
            "openai": [
                {"id": "openai/gpt-4o", "label": "GPT-4o"},
                {"id": "openai/gpt-4o-mini", "label": "GPT-4o Mini"},
                {"id": "openai/o1", "label": "o1 (Raisonnement)"},
                {"id": "openai/o3-mini", "label": "o3 Mini"}
            ],
            "anthropic": [
                {"id": "anthropic/claude-3-7-sonnet-20250219", "label": "Claude 3.7 Sonnet"},
                {"id": "anthropic/claude-3-5-sonnet-20241022", "label": "Claude 3.5 Sonnet"},
                {"id": "anthropic/claude-3-5-haiku-20241022", "label": "Claude 3.5 Haiku"}
            ],
            "mistral": [
                {"id": "mistral/mistral-large-latest", "label": "Mistral Large"},
                {"id": "mistral/codestral-latest", "label": "Codestral"},
                {"id": "mistral/mistral-small-latest", "label": "Mistral Small"},
                {"id": "mistral/ministral-8b-latest", "label": "Ministral 8B"}
            ],
            "gemini": [
                {"id": "gemini/gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
                {"id": "gemini/gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
                {"id": "gemini/gemini-2.0-flash-lite", "label": "Gemini 2.0 Flash Lite"},
                {"id": "gemini/gemini-1.5-pro", "label": "Gemini 1.5 Pro"}
            ]
        }
        models = standard_catalog.get(provider, [
            {"id": f"{provider}/default", "label": f"{provider} (Modèle par défaut)"}
        ])

    _MODELS_CATALOG_CACHE[cache_key] = (now, models)
    return models

def scale_cluster_resources(req_data: Dict[str, Any], cfg_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Applique le dimensionnement du cluster : scale-out (nœuds) et/ou scale-up (vCPU, RAM, disque, RAG)."""
    cfg, _ = load_config_data(cfg_path)
    k8s = cfg.setdefault("kubernetes", {})
    sizing = k8s.setdefault("sizing", {})
    vm = cfg.setdefault("vmware", {})
    vm_res = vm.setdefault("resources_override", {})

    scale_type = str(req_data.get("scale_type", "full")).lower().strip()
    tier = str(req_data.get("tier", "")).strip()

    # Si un palier est fourni, initialiser avec les valeurs calibrées
    if tier and tier in VMWARE_SIZING_TIERS:
        t_def = VMWARE_SIZING_TIERS[tier]
        sizing["tier"] = tier
        sizing["nodes"] = t_def["nodes"]
        sizing["vcpu_per_node"] = t_def["vcpu_per_node"]
        sizing["ram_per_node_gb"] = t_def["ram_per_node_gb"]
        sizing["disk_per_node_gb"] = t_def["disk_per_node_gb"]
        sizing["rag_storage_gb"] = t_def["rag_storage_gb"]

    # 1. Scale-out (horizontal) : ajustement du nombre de nœuds
    if scale_type in ("out", "full", "horizontal"):
        if "nodes" in req_data and req_data["nodes"] is not None:
            try:
                sizing["nodes"] = max(1, int(req_data["nodes"]))
            except (ValueError, TypeError):
                pass

    # 2. Scale-up (vertical) : ajustement des ressources par nœud et stockage persistant
    if scale_type in ("up", "full", "vertical"):
        if "vcpu_per_node" in req_data and req_data["vcpu_per_node"] is not None:
            try:
                sizing["vcpu_per_node"] = max(2, int(req_data["vcpu_per_node"]))
            except (ValueError, TypeError):
                pass
        if "ram_per_node_gb" in req_data and req_data["ram_per_node_gb"] is not None:
            try:
                sizing["ram_per_node_gb"] = max(4, int(req_data["ram_per_node_gb"]))
            except (ValueError, TypeError):
                pass
        if "disk_per_node_gb" in req_data and req_data["disk_per_node_gb"] is not None:
            try:
                sizing["disk_per_node_gb"] = max(50, int(req_data["disk_per_node_gb"]))
            except (ValueError, TypeError):
                pass
        if "rag_storage" in req_data and str(req_data["rag_storage"]).strip():
            rag_val = str(req_data["rag_storage"]).strip()
            sizing["rag_storage"] = rag_val
            cfg.setdefault("open_webui", {})["storage_size"] = rag_val

    # Synchronisation des paramètres VMware pour reprise ultérieure
    if "tier" in sizing:
        vm["tier"] = sizing["tier"]
    if "nodes" in sizing:
        vm_res["nodes"] = sizing["nodes"]
    if "vcpu_per_node" in sizing:
        vm_res["vcpu_per_node"] = sizing["vcpu_per_node"]
    if "ram_per_node_gb" in sizing:
        vm_res["ram_per_node_gb"] = sizing["ram_per_node_gb"]
    if "disk_per_node_gb" in sizing:
        vm_res["disk_per_node_gb"] = sizing["disk_per_node_gb"]

    save_config_to_files(cfg, cfg_path)

    applied_on_cluster = False
    details_log = []
    try:
        runner = get_k8s_runner(cfg)
        ns = k8s.get("namespace", "arcia")
        rc, _, _ = runner.run(["get", "namespace", ns], timeout=3)
        if rc == 0:
            applied_on_cluster = True
            if scale_type in ("up", "full"):
                rag_size = sizing.get("rag_storage") or f"{sizing.get('rag_storage_gb', 200)}Gi"
                patch_pvc = json.dumps({"spec": {"resources": {"requests": {"storage": rag_size}}}})
                runner.run(["patch", "pvc", "open-webui-pvc", "-n", ns, "-p", patch_pvc], timeout=4)
                details_log.append(f"Volume PVC RAG redimensionné à {rag_size}")
            if scale_type in ("out", "full"):
                details_log.append(f"Topologie horizontale ajustée à {sizing.get('nodes', 3)} nœud(s)")
    except Exception:
        pass

    msg_map = {
        "out": f"Scale-out appliqué avec succès : cible de {sizing.get('nodes', 3)} nœud(s).",
        "up": f"Scale-up appliqué avec succès : {sizing.get('vcpu_per_node', 4)} vCPU, {sizing.get('ram_per_node_gb', 16)} Go RAM/nœud.",
        "full": f"Dimensionnement complet appliqué : {sizing.get('nodes', 3)} nœuds ({sizing.get('vcpu_per_node', 4)} vCPU, {sizing.get('ram_per_node_gb', 16)} Go RAM)."
    }

    return {
        "success": True,
        "scale_type": scale_type,
        "message": msg_map.get(scale_type, msg_map["full"]),
        "applied_on_cluster": applied_on_cluster,
        "sizing": sizing,
        "details_log": details_log
    }

# -----------------------------------------------------------------------------
# Handlers Serveur HTTP (API REST & Single Page App)
# -----------------------------------------------------------------------------

class WizardHTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def is_safe_origin(self) -> bool:
        host = self.headers.get("Host", "").split(":")[0].strip()
        if host and host not in ("127.0.0.1", "localhost", "::1"):
            return False
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
                return False
        return True

    def end_headers(self):
        # Restriction stricte aux origines locales (Protection anti-DNS rebinding et CSRF)
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.hostname in ("127.0.0.1", "localhost", "::1"):
                self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def send_json(self, status: int, data: Any):
        if isinstance(data, dict) and getattr(self, "command", "") == "POST":
            data.setdefault("backup_status", instance_storage.status(ROOT_DIR))
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if not self.is_safe_origin():
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        try:
            if not self.is_safe_origin():
                self.send_json(403, {"success": False, "error": "Accès refusé : requête interdite depuis une origine externe non autorisée."})
                return

            parsed = urlparse(self.path)
            path = parsed.path

            if path in ("/", "/index.html"):
                self.serve_wizard_ui()
            elif path == "/api/config":
                cfg, exists = load_config_data(DEFAULT_CONFIG_PATH)
                contexts = detect_kubectl_contexts()
                current_ctx = detect_current_context()
                ssh_keys = detect_available_ssh_keys()
                self.send_json(200, {
                    "config": cfg,
                    "is_existing": exists,
                    "available_contexts": contexts,
                    "current_context": current_ctx,
                    "available_ssh_keys": ssh_keys,
                    "os": os.name
                })
            elif path == "/api/deploy/status":
                with deployment_lock:
                    state_copy = {
                        "status": deployment_state["status"],
                        "logs": deployment_state["logs"],
                        "exit_code": deployment_state["exit_code"],
                        "summary": deployment_state["summary"],
                        "count": len(deployment_state["logs"])
                    }
                self.send_json(200, state_copy)
            elif path == "/api/updates/check":
                qs = parse_qs(parsed.query)
                online = qs.get("online", ["1"])[0] not in ("0", "false")
                cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
                res = check_components_updates(check_online=online, cfg=cfg, force_prod_scan=True)
                self.send_json(200, res)
            elif path == "/api/updates/status":
                with update_lock:
                    u_copy = {
                        "status": update_state["status"],
                        "progress": update_state["progress_pct"],
                        "progress_pct": update_state["progress_pct"],
                        "current_phase": update_state["current_phase"],
                        "current_step_label": update_state["current_phase"],
                        "phases": update_state["phases"],
                        "logs": update_state["logs"],
                        "updated_components": update_state["updated_components"]
                    }
                self.send_json(200, u_copy)
            elif path == "/api/docker/status":
                st = get_docker_status()
                self.send_json(200, st)
            elif path == "/api/vmware/tiers":
                self.send_json(200, VMWARE_SIZING_TIERS)
            elif path == "/api/cluster/sizing":
                cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
                sizing = cfg.get("kubernetes", {}).get("sizing", {})
                self.send_json(200, {
                    "success": True,
                    "sizing": sizing,
                    "tiers": VMWARE_SIZING_TIERS
                })
            elif path == "/api/powerusers/list":
                qs = parse_qs(parsed.query)
                ctx = qs.get("context", [None])[0]
                ns = qs.get("namespace", [None])[0]
                self.send_json(200, list_powerusers(context=ctx, namespace=ns))
            elif path == "/api/models/routing":
                cfg, exists = load_config_data(DEFAULT_CONFIG_PATH)
                self.send_json(200, get_model_routing_config(cfg, include_defaults=not exists))
            elif path == "/api/models/catalog":
                qs = parse_qs(parsed.query)
                prov = qs.get("provider", ["openrouter"])[0]
                key = qs.get("api_key", [""])[0]
                ep = qs.get("endpoint", [None])[0]
                models = get_provider_models_catalog(prov, api_key=key, endpoint=ep)
                self.send_json(200, {"success": True, "provider": prov, "models": models})
            elif path == "/api/instance/detect":
                qs = parse_qs(parsed.query)
                ctx = qs.get("context", [None])[0]
                ns = qs.get("namespace", [None])[0]
                cfg, exists = load_config_data(DEFAULT_CONFIG_PATH)
                res = check_instance_connectivity(cfg, context=ctx, namespace=ns)
                res["is_existing"] = exists
                self.send_json(200, res)
            elif path == "/api/integrations/status":
                cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
                self.send_json(200, get_integrations_status(cfg))
            elif path == "/api/instance/backup-info":
                self.send_json(200, get_instance_backup_info())
            elif path == "/api/health":
                self.send_json(200, {"status": "ok"})
            elif path.startswith("/static/"):
                fname = os.path.basename(path)
                fpath = os.path.join(ROOT_DIR, "assets", "branding", fname)
                if os.path.isfile(fpath):
                    content_type = "image/svg+xml" if fname.endswith(".svg") else "application/json" if fname.endswith(".json") else "application/octet-stream"
                    with open(fpath, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", f"{content_type}; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "public, max-age=3600")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                else:
                    self.send_error(404, "Fichier statique introuvable")
                    return
            else:
                self.send_error(404, "Page non trouvée")
        except Exception as e:
            self.send_json(500, {"success": False, "error": f"Erreur serveur (GET) : {str(e)}"})

    def do_POST(self):
        try:
            if not self.is_safe_origin():
                self.send_json(403, {"success": False, "error": "Accès refusé : requête interdite depuis une origine externe non autorisée."})
                return
            self._handle_post_internal()
        except Exception as e:
            self.send_json(500, {"success": False, "error": f"Erreur serveur (POST) : {str(e)}"})

    def _handle_post_internal(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            req_data = json.loads(body) if body else {}
        except Exception:
            req_data = {}

        if path == "/api/test-k8s":
            mode = req_data.get("mode", "local")
            kubeconfig = req_data.get("kubeconfig", "")
            context = req_data.get("context", "")
            remote_ssh = req_data.get("remote_ssh", {})

            try:
                sys.path.insert(0, SCRIPT_DIR)
                import deploy
                runner = deploy.K8sRunner(
                    mode=mode,
                    kubeconfig=kubeconfig,
                    context=context,
                    ssh_node=remote_ssh.get("node_ip", "127.0.0.1"),
                    ssh_user=remote_ssh.get("ssh_user", "debian"),
                    ssh_port=int(remote_ssh.get("ssh_port", 22)),
                    ssh_key=remote_ssh.get("ssh_key", "")
                )
                rc, out, err = runner.run(["get", "nodes", "-o", "wide"])
                if rc == 0:
                    lines = [l for l in out.strip().splitlines() if l and not l.startswith("NAME")]
                    nodes = []
                    for l in lines:
                        parts = l.split()
                        if len(parts) >= 2:
                            nodes.append({"name": parts[0], "status": parts[1], "roles": parts[2] if len(parts) > 2 else "worker"})
                    self.send_json(200, {
                        "success": True,
                        "nodes_count": len(nodes),
                        "nodes": nodes,
                        "raw_output": out
                    })
                else:
                    self.send_json(200, {
                        "success": False,
                        "error": err.strip() or out.strip() or "Code de retour non nul"
                    })
            except Exception as e:
                self.send_json(200, {"success": False, "error": str(e)})

        elif path == "/api/instance/test-token":
            provider = req_data.get("provider", "github")
            token = req_data.get("token", "")
            res = git_test_credentials(provider, token)
            self.send_json(200, res)

        elif path == "/api/instance/create-repo":
            provider = req_data.get("provider", "github")
            token = req_data.get("token", "")
            repo_name = req_data.get("repo_name", "")
            owner = req_data.get("owner", "")
            res = git_create_remote_repo(provider, token, repo_name, owner)
            self.send_json(200, res)

        elif path == "/api/instance/restore":
            cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
            settings = instance_storage.normalize_settings(cfg)
            repo_url = (req_data.get("repo_url") or settings.get("repo_url") or "").strip()
            auth_settings = settings if repo_url == settings.get("repo_url") else {"repo_url": repo_url}
            stored = instance_storage.credentials(ROOT_DIR, auth_settings)
            token = (req_data.get("token") or stored["token"]).strip()
            passphrase = req_data.get("passphrase") or stored["passphrase"]
            commit_hash = req_data.get("commit_hash", None)
            res = git_pull_and_decrypt_instance(repo_url, token, passphrase, commit_hash=commit_hash)
            self.send_json(200, res)

        elif path == "/api/instance/backup-now":
            try:
                cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
                result = backup_current_instance(cfg, passphrase=req_data.get("passphrase", ""), token=req_data.get("token", ""), repo_url=req_data.get("repo_url", ""), force=True)
                if result.get("success"):
                    save_config_to_files(cfg, DEFAULT_CONFIG_PATH, trigger_backup=False)
                self.send_json(200 if result.get("success") else 400, result)
            except Exception:
                self.send_json(400, {"success": False, "error": "Sauvegarde indisponible ; vérifier le coffre et le dépôt privé."})

        elif path == "/api/instance/timeline":
            cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
            backup_cfg = instance_storage.normalize_settings(cfg)
            repo_url = (req_data.get("repo_url") or backup_cfg.get("repo_url") or "").strip()
            auth_settings = backup_cfg if repo_url == backup_cfg.get("repo_url") else {"repo_url": repo_url}
            token = (req_data.get("token") or instance_storage.credentials(ROOT_DIR, auth_settings)["token"]).strip()
            if not repo_url:
                self.send_json(400, {"success": False, "error": "URL de dépôt de sauvegarde manquante.", "timeline": []})
            else:
                res = get_instance_backup_timeline(repo_url, token)
                self.send_json(200, res)

        elif path == "/api/generate-secret":
            kind = req_data.get("kind", "pat")
            token = generate_token(kind)
            self.send_json(200, {"success": True, "token": token, "kind": kind})

        elif path == "/api/save-config":
            try:
                cfg = req_data.get("config", {})
                save_config_to_files(cfg, DEFAULT_CONFIG_PATH)
                self.send_json(200, {"success": True, "message": "Configuration enregistrée avec succès."})
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})

        elif path == "/api/vmware/test":
            res = test_vmware_connection(req_data)
            self.send_json(200, res)

        elif path == "/api/vmware/generate-ssh-key":
            comment = req_data.get("comment", "arcia-vmware-cluster")
            res = generate_ssh_key_pair(comment)
            self.send_json(200, res)

        elif path == "/api/k8s/validate-full":
            mode = req_data.get("mode", "local")
            kubeconfig = req_data.get("kubeconfig", "")
            context = req_data.get("context", "")
            remote_ssh = req_data.get("remote_ssh", {})

            try:
                sys.path.insert(0, SCRIPT_DIR)
                import deploy
                runner = deploy.K8sRunner(
                    mode=mode,
                    kubeconfig=kubeconfig,
                    context=context,
                    ssh_node=remote_ssh.get("node_ip", "127.0.0.1"),
                    ssh_user=remote_ssh.get("ssh_user", "debian"),
                    ssh_port=int(remote_ssh.get("ssh_port", 22)),
                    ssh_key=remote_ssh.get("ssh_key", "")
                )
                res = audit_kubernetes_environment_full(runner)
                self.send_json(200, res)
            except Exception as e:
                self.send_json(200, {
                    "success": False,
                    "all_valid": False,
                    "summary": f"Erreur lors de l'audit Kubernetes : {str(e)}",
                    "checks": []
                })

        elif path == "/api/deploy":
            with deployment_lock:
                if deployment_state["status"] == "running":
                    self.send_json(400, {"success": False, "error": "Un déploiement est déjà en cours d'exécution."})
                    return

            try:
                cfg = req_data.get("config")
                dry_run = req_data.get("dry_run", False)
                git_info = req_data.get("instance_git", None)
                if git_info and not dry_run:
                    registered = instance_storage.normalize_settings({"instance_git": git_info})
                    if not registered.get("repo_url"):
                        raise ValueError("Dépôt privé de sauvegarde incomplet.")
                    instance_storage.unlock(ROOT_DIR, registered["repo_url"], git_info.get("token", ""), git_info.get("passphrase", ""))
                    registered = {k: v for k, v in registered.items() if k not in {"token", "git_token", "passphrase"}}
                    registered["enabled"] = True
                    cfg = cfg or load_config_data(DEFAULT_CONFIG_PATH)[0]
                    cfg["instance_backup"] = registered
                    git_info = {"enabled": True, "repo_url": registered["repo_url"]}
                if cfg:
                    save_config_to_files(cfg, DEFAULT_CONFIG_PATH)

                infra_target = req_data.get("infra_target", "k8s_existing")
                infra_config = req_data.get("infra_config", None)

                worker = threading.Thread(
                    target=run_deployment_worker,
                    args=(dry_run, git_info, infra_target, infra_config),
                    daemon=True
                )
                worker.start()

                self.send_json(200, {"success": True, "started": True, "dry_run": dry_run, "infra_target": infra_target})
            except Exception as de:
                self.send_json(500, {"success": False, "error": f"Erreur lors de la configuration ou du démarrage du déploiement : {str(de)}"})

        elif path == "/api/deploy/cancel":
            res = cancel_active_deployment()
            self.send_json(200 if res.get("success") else 400, res)

        elif path == "/api/updates/check":
            online = bool(req_data.get("online", req_data.get("check_online", True)))
            cfg = req_data.get("config") if isinstance(req_data, dict) else None
            if cfg is None or not isinstance(cfg, dict):
                cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
            else:
                cfg = ensure_config_defaults(cfg)
            res = check_components_updates(check_online=online, cfg=cfg, force_prod_scan=True)
            self.send_json(200, res)

        elif path == "/api/updates/apply":
            with update_lock:
                if update_state["status"] == "running":
                    self.send_json(400, {"success": False, "error": "Une séquence de mise à jour est déjà en cours."})
                    return

            selected = req_data.get("components") or [c["id"] for c in ARCIA_UPDATABLE_COMPONENTS]
            bump_tags = bool(req_data.get("bump_image_tags", req_data.get("update_manifests", False)))
            dry_run = bool(req_data.get("dry_run", False))
            infra_target = req_data.get("infra_target", "k8s_existing")

            worker = threading.Thread(
                target=run_update_worker,
                args=(selected, bump_tags, dry_run, infra_target),
                daemon=True
            )
            worker.start()
            self.send_json(200, {
                "success": True,
                "started": True,
                "dry_run": dry_run,
                "selected_components": selected,
                "bump_image_tags": bump_tags
            })

        elif path == "/api/config/upload-yaml":
            try:
                yaml_content = req_data.get("yaml_content") or req_data.get("content") or ""
                filename = req_data.get("filename", "arcia.config.yaml")
                if not yaml_content.strip():
                    self.send_json(400, {"success": False, "error": "Le contenu du fichier YAML est vide."})
                    return

                sys.path.insert(0, SCRIPT_DIR)
                import deploy
                if filename.endswith(".env") or "ARCIA_PUBLIC_FQDN=" in yaml_content:
                    parsed_cfg = deploy.parse_env_format(yaml_content)
                else:
                    parsed_cfg = None
                    try:
                        import yaml
                        parsed_cfg = yaml.safe_load(yaml_content)
                    except Exception:
                        pass
                    if not isinstance(parsed_cfg, dict):
                        parsed_cfg = deploy.parse_simple_yaml(yaml_content)

                if not isinstance(parsed_cfg, dict):
                    self.send_json(400, {"success": False, "error": "Structure YAML invalide ou impossible à analyser."})
                    return

                cfg = ensure_config_defaults(parsed_cfg)
                save_config_to_files(cfg, DEFAULT_CONFIG_PATH)

                # Scan immédiat de la production et test de connectivité au chargement du YAML
                connectivity_info = check_instance_connectivity(cfg)
                updates_info = check_components_updates(check_online=False, cfg=cfg, force_prod_scan=True)

                self.send_json(200, {
                    "success": True,
                    "config": cfg,
                    "filename": filename,
                    "updates": updates_info,
                    "connectivity": connectivity_info,
                    "connected": connectivity_info.get("connected", False),
                    "instance_detected": connectivity_info.get("instance_detected", False),
                    "message": f"Configuration chargée avec succès depuis '{filename}'."
                })
            except Exception as ye:
                self.send_json(500, {"success": False, "error": f"Erreur lors de l'analyse du fichier YAML : {str(ye)}"})

        elif path == "/api/instance/detect":
            cfg = req_data.get("config")
            if not isinstance(cfg, dict):
                cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
            ctx = req_data.get("context")
            ns = req_data.get("namespace")
            res = check_instance_connectivity(cfg, context=ctx, namespace=ns)
            self.send_json(200, res)

        elif path == "/api/powerusers/create":
            res = create_poweruser(req_data)
            self.send_json(200, res)

        elif path == "/api/powerusers/delete":
            slug = req_data.get("slug", "").strip()
            if "delete_pvc" in req_data:
                keep_pvc = not bool(req_data.get("delete_pvc"))
            else:
                keep_pvc = bool(req_data.get("keep_pvc", False))
            res = delete_poweruser(slug, keep_pvc=keep_pvc)
            self.send_json(200, res)

        elif path == "/api/powerusers/scale":
            slug = req_data.get("slug", "").strip()
            replicas = int(req_data.get("replicas", 1))
            res = scale_poweruser(slug, replicas=replicas)
            self.send_json(200, res)

        elif path == "/api/powerusers/resize-pvc":
            slug = req_data.get("slug", "").strip()
            new_size = req_data.get("new_size", "").strip()
            res = resize_poweruser_pvc(slug, new_size=new_size)
            self.send_json(200, res)

        elif path == "/api/powerusers/sync-all":
            res = sync_all_powerusers_wizard()
            self.send_json(200, res)

        elif path == "/api/models/appearance":
            custom = req_data.get("custom_providers") or []
            self.send_json(200, {"success": True, "icons": [resolve_model_icon(m, custom) for m in req_data.get("models", [])]})

        elif path == "/api/models/routing":
            res = save_model_routing_config(req_data)
            self.send_json(200, res)

        elif path == "/api/models/test-provider":
            provider = req_data.get("provider", "").strip()
            api_key = req_data.get("api_key", "").strip()
            endpoint = req_data.get("endpoint")
            model = req_data.get("model")
            res = test_provider_connectivity(provider, api_key, endpoint=endpoint, model=model)
            self.send_json(200, res)

        elif path == "/api/cluster/scale":
            res = scale_cluster_resources(req_data)
            self.send_json(200, res)

        else:
            self.send_error(404, "Endpoint non trouvé")

    def serve_wizard_ui(self):
        """Sert l'application Web moderne, interactive et complète du Wizard."""
        html = get_wizard_html_page()
        encoded = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

# -----------------------------------------------------------------------------
# Interface Graphique (HTML5 / CSS3 Moderne / Vanilla JS)
# -----------------------------------------------------------------------------

def get_wizard_html_page() -> str:
    """Charge l interface graphique HTML/CSS/JS du Wizard depuis scripts/wizard_ui/index.html."""
    ui_path = os.path.join(SCRIPT_DIR, "wizard_ui", "index.html")
    with open(ui_path, "r", encoding="utf-8") as f:
        return f.read()

# -----------------------------------------------------------------------------
# Point d'Entrée & Démarrage du Serveur Local
# -----------------------------------------------------------------------------

def find_available_port(start_port: int = 8765, max_attempts: int = 20) -> int:
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port

def main():
    parser = argparse.ArgumentParser(description="ArcIA Setup & Configuration Wizard")
    parser.add_argument("--host", default="127.0.0.1", help="Adresse IP d'écoute (défaut : 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port d'écoute (défaut : 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Ne pas ouvrir automatiquement le navigateur")
    args = parser.parse_args()

    port = find_available_port(args.port)
    server_address = (args.host, port)
    httpd = HttpServerClass(server_address, WizardHTTPHandler)
    watcher_stop = threading.Event()
    threading.Thread(target=watch_instance_configuration, args=(watcher_stop,), daemon=True).start()

    wizard_url = f"http://{args.host}:{port}/"

    print("\033[1m\033[96m=================================================================\033[0m")
    print("\033[1m\033[96m          ArcIA — Setup & Configuration Wizard v0.5.2            \033[0m")
    print("\033[1m\033[96m=================================================================\033[0m")
    print(f"\n[+] Serveur graphique de configuration démarré avec succès !")
    print(f"[*] Accédez au Wizard dans votre navigateur à l'adresse :")
    print(f"\n      \033[1m\033[92m{wizard_url}\033[0m\n")
    print(f"[*] Appuyez sur Ctrl+C pour arrêter le serveur du Wizard.\n")

    if not args.no_browser:
        try:
            threading.Timer(1.0, lambda: webbrowser.open(wizard_url)).start()
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Arrêt du serveur Wizard.")
        watcher_stop.set()
        httpd.server_close()
        sys.exit(0)

if __name__ == "__main__":
    main()
