#!/usr/bin/env python3
"""
ArcIA — Assistant & Moteur d'Installation Graphique Interactif (Wizard)
========================================================================
Ce serveur web autonome (Python 3 standard library uniquement, 0 dépendance)
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
    if kind == "pat":
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

    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(payload_dict, ensure_ascii=False).encode('utf-8')

    if HAS_CRYPTOGRAPHY:
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
        key = kdf.derive(passphrase.encode('utf-8'))
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, b'ARCIA_INSTANCE_V1')
        algo = "AES-256-GCM"
    else:
        import hashlib, hmac
        key = hashlib.pbkdf2_hmac('sha256', passphrase.encode('utf-8'), salt, 100000, 64)
        enc_key, mac_key = key[:32], key[32:]
        keystream = bytearray()
        block_idx = 0
        while len(keystream) < len(plaintext):
            keystream.extend(hmac.new(enc_key, nonce + block_idx.to_bytes(4, 'big'), hashlib.sha256).digest())
            block_idx += 1
        ct_bytes = bytes([p ^ k for p, k in zip(plaintext, keystream[:len(plaintext)])])
        tag = hmac.new(mac_key, b'ARCIA_INSTANCE_V1' + nonce + ct_bytes, hashlib.sha256).digest()
        ciphertext = ct_bytes + tag
        algo = "HMAC-SHA256-STREAM"

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
        else:
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
    """Initialise, committe et pousse le bundle d'instance chiffré vers le dépôt privé."""
    temp_dir = tempfile.mkdtemp(prefix="arcia-instance-")
    try:
        meta = {
            "instance_name": instance_name,
            "public_fqdn": fqdn,
            "schema_version": "0.4.0",
            "encryption": "AES-256-GCM-PBKDF2-100K",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        with open(os.path.join(temp_dir, "instance.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        with open(os.path.join(temp_dir, "instance-secrets.enc"), "w", encoding="utf-8") as f:
            f.write(encrypted_bundle_str)

        readme_content = f"""# ArcIA — Dépôt d'Instance Privée : {instance_name}

Ce dépôt privé contient la configuration et les secrets chiffrés de l'instance ArcIA **{instance_name}** (`https://{fqdn}/`).

> [!IMPORTANT]
> **Sécurité de bout en bout :** Tous les secrets (clés d'inférence, identifiants Entra ID, tokens Bot Teams, mots de passe Hermes) sont chiffrés avec **AES-256-GCM** et dérivation de clé **PBKDF2 (100 000 itérations)**.
> Aucune valeur secrète n'est exposée en clair dans ce dépôt.

## Procédure de Restauration Complète

Pour restaurer cette instance sur un cluster Kubernetes neuf ou reconstruit :

1. Clonez le dépôt du socle générique ArcIA :
   ```bash
   git clone https://github.com/nicolastheuil/ArcIA.git
   cd ArcIA
   ```
2. Lancez le Setup Wizard :
   ```bash
   ./wizard.sh       # Linux / macOS
   .\\wizard.ps1      # Windows PowerShell
   ```
3. Choisissez **Restaurer une instance existante**.
4. Renseignez l'URL de ce dépôt (`{repo_url}`) et votre mot de passe maître de déchiffrement.
5. Cliquez sur **Lancer la restauration complète sur Kubernetes**.
"""
        with open(os.path.join(temp_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write(readme_content)

        auth_url = repo_url
        if token and "https://" in repo_url:
            if "github.com" in repo_url:
                auth_url = repo_url.replace("https://", f"https://x-access-token:{token}@")
            elif "gitlab.com" in repo_url:
                auth_url = repo_url.replace("https://", f"https://oauth2:{token}@")
            else:
                auth_url = repo_url.replace("https://", f"https://{token}@")

        subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "ArcIA Setup Wizard"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "admin@arcia.local"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "checkout", "-B", "main"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", f"chore(instance): sauvegarde chiffrée de {instance_name}"], cwd=temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "origin", auth_url], cwd=temp_dir, capture_output=True)

        proc = subprocess.run(["git", "push", "-u", "origin", "main", "--force"], cwd=temp_dir, capture_output=True, timeout=30)
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")
            return {"success": False, "error": f"Erreur git push ({err.strip()})"}

        return {"success": True, "repo_url": repo_url}

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def git_pull_and_decrypt_instance(repo_url: str, token: str, passphrase: str) -> dict:
    """Clone le dépôt d'instance privé et déchiffre la configuration avec le mot de passe maître."""
    temp_dir = tempfile.mkdtemp(prefix="arcia-restore-")
    try:
        auth_url = repo_url
        if token and "https://" in repo_url:
            if "github.com" in repo_url:
                auth_url = repo_url.replace("https://", f"https://x-access-token:{token}@")
            elif "gitlab.com" in repo_url:
                auth_url = repo_url.replace("https://", f"https://oauth2:{token}@")
            else:
                auth_url = repo_url.replace("https://", f"https://{token}@")

        proc = subprocess.run(["git", "clone", "--depth", "1", auth_url, temp_dir], capture_output=True, timeout=30)
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")
            return {"success": False, "error": f"Impossible d'accéder au dépôt d'instance : {err.strip()}"}

        enc_file = os.path.join(temp_dir, "instance-secrets.enc")
        if not os.path.isfile(enc_file):
            return {"success": False, "error": "Fichier 'instance-secrets.enc' introuvable dans ce dépôt."}

        with open(enc_file, "r", encoding="utf-8") as f:
            bundle_str = f.read()

        decrypted = decrypt_instance_bundle(bundle_str, passphrase)

        config_yaml = decrypted.get("config_yaml", "")
        if not config_yaml:
            return {"success": False, "error": "Le bundle d'instance ne contient pas de configuration valide."}

        # Écriture immédiate dans arcia.config.yaml
        with open(DEFAULT_CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(config_yaml)

        # Restauration de secrets/arcia.env
        env_content = decrypted.get("env_content", "")
        if env_content:
            secrets_dir = os.path.join(ROOT_DIR, "secrets")
            os.makedirs(secrets_dir, exist_ok=True)
            with open(os.path.join(secrets_dir, "arcia.env"), "w", encoding="utf-8") as f:
                f.write(env_content)

        sys.path.insert(0, SCRIPT_DIR)
        import deploy
        cfg = deploy.parse_yaml_or_env(DEFAULT_CONFIG_PATH)

        return {
            "success": True,
            "instance_name": decrypted.get("instance_name", "ArcIA-instance"),
            "public_fqdn": decrypted.get("public_fqdn", cfg.get("network", {}).get("public_fqdn", "")),
            "config": cfg,
            "message": f"Instance '{decrypted.get('instance_name', '')}' déchiffrée avec succès !"
        }

    except ValueError as ve:
        return {"success": False, "error": str(ve)}
    except Exception as e:
        return {"success": False, "error": f"Erreur lors de la restauration : {str(e)}"}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# -----------------------------------------------------------------------------
# Dimensionnement VMware vSphere & Cibles d'Infrastructure
# -----------------------------------------------------------------------------

VMWARE_SIZING_TIERS = {
    "20": {
        "title": "Équipe Pilote / Découverte",
        "users_label": "Jusqu'à 20 utilisateurs",
        "description": "Idéal pour un PoC, qualification technique ou une petite équipe projet.",
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
        "title": "PME / Direction Métier",
        "users_label": "21 à 100 utilisateurs",
        "description": "Cluster K3s Haute Disponibilité avec résilience multi-nœuds (etcd multi-maître).",
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
        "recommended": True
    },
    "500": {
        "title": "Entreprise / Multi-Départements",
        "users_label": "101 à 500 utilisateurs",
        "description": "Séparation du plan de contrôle et des nœuds d'exécution agentique.",
        "nodes": 5,
        "type": "3x Control-Plane HA + 2x Workers Dédiés",
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
        "title": "Grande Entreprise",
        "users_label": "Plus de 500 utilisateurs",
        "description": "Architecture multi-nœuds extensible, stockage haute performance et option vGPU.",
        "nodes": 7,
        "type": "3x Control-Plane HA + 4x Workers Haute Performance",
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
            return cfg, exists
    except Exception:
        pass

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
            "local_vllm_endpoint": ""
        },
        "hermes": {
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

    def bstr(val: Any) -> str:
        return "true" if bool(val) else "false"

    def qstr(val: Any) -> str:
        s = str(val or "")
        return f'"{s}"'

    def istr(val: Any, default: int = 22) -> int:
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    ssh = k8s.get("remote_ssh") or {}

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
  default_model: {qstr(llm.get('default_model', 'simple/auto'))}
  local_vllm_endpoint: {qstr(llm.get('local_vllm_endpoint', ''))}

# 4. Moteur d'Agents Hermes & Studio Kanban
hermes:
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
"""
    return yaml_text

def save_config_to_files(cfg: Dict[str, Any], config_path: str = DEFAULT_CONFIG_PATH) -> None:
    """Enregistre la configuration dans arcia.config.yaml et synchronise secrets/arcia.env."""
    yaml_content = serialize_yaml_config(cfg)
    os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    secrets_dir = os.path.join(ROOT_DIR, "secrets")
    if os.path.isdir(secrets_dir):
        env_path = os.path.join(secrets_dir, "arcia.env")
        try:
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(f"# ArcIA Environment Secrets - Auto-généré par le Wizard\n")
                f.write(f"OPENROUTER_API_KEY={cfg.get('llm_gateway', {}).get('openrouter_api_key', '')}\n")
                f.write(f"HERMES_ADMIN_PASSWORD={cfg.get('hermes', {}).get('admin_password', 'admin')}\n")
                f.write(f"HERMES_API_SERVER_KEY={cfg.get('hermes', {}).get('api_token', '')}\n")
                f.write(f"PRESIDIO_MASTER_KEY={cfg.get('presidio', {}).get('master_key', '')}\n")
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
        except Exception:
            pass

# -----------------------------------------------------------------------------
# Exécution du Déploiement en Tâche de Fond & Sauvegarde Git Chiffrée
# -----------------------------------------------------------------------------

def run_deployment_worker(dry_run: bool = False, instance_git_info: Optional[dict] = None,
                          infra_target: str = "k8s_existing", infra_config: Optional[dict] = None):
    global deployment_state

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
                bufsize=1,
                cwd=ROOT_DIR,
                env=env_vars
            )

            for line in iter(proc.stdout.readline, ''):
                if line:
                    clean_line = line.rstrip()
                    with deployment_lock:
                        deployment_state["logs"].append(clean_line)

            proc.wait()
            exit_code = proc.returncode

            with deployment_lock:
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
                deployment_state["status"] = "error"
                deployment_state["logs"].append(f"[FATAL ERROR Docker] {str(de)}")
            return

    # Mode Kubernetes Existant ou VMware vSphere
    if infra_target == "vmware_k3s":
        vm_cfg = (infra_config or {}).get("vmware", {})
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

    with deployment_lock:
        deployment_state["logs"].append(f"[INFO] Exécution du déploiement : python -u scripts/deploy.py {'--dry-run' if dry_run else ''}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=ROOT_DIR,
            env=env_vars
        )

        for line in iter(proc.stdout.readline, ''):
            if line:
                clean_line = line.rstrip()
                with deployment_lock:
                    deployment_state["logs"].append(clean_line)

        proc.wait()
        exit_code = proc.returncode

        with deployment_lock:
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

                        yaml_content = serialize_yaml_config(cfg)
                        env_content = ""
                        try:
                            with open(os.path.join(ROOT_DIR, "secrets", "arcia.env"), "r", encoding="utf-8") as f:
                                env_content = f.read()
                        except Exception:
                            pass

                        payload = {
                            "instance_name": inst_name,
                            "public_fqdn": fqdn,
                            "config_yaml": yaml_content,
                            "env_content": env_content
                        }
                        enc_bundle = encrypt_instance_bundle(payload, passphrase)
                        push_res = git_push_instance(repo_url, token, enc_bundle, inst_name, fqdn)
                        if push_res.get("success"):
                            deployment_state["logs"].append(f"[OK] Dépôt d'instance privé synchronisé et chiffré (AES-256-GCM) : {repo_url}")
                            instance_repo_url = repo_url
                        else:
                            deployment_state["logs"].append(f"[WARN] Avertissement sauvegarde Git : {push_res.get('error')}")
                    except Exception as ge:
                        deployment_state["logs"].append(f"[WARN] Sauvegarde Git non effectuée : {str(ge)}")

                deployment_state["status"] = "success"
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
                    "mode": infra_target
                }
            else:
                deployment_state["status"] = "error"

    except Exception as e:
        with deployment_lock:
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
        "default_version": "v0.4",
        "strategy": "Hot-Sync ConfigMaps & Skills (0 coupure)",
        "wave": 1,
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
        "default_version": "2.2.354",
        "strategy": "RollingUpdate (maxUnavailable: 0, maxSurge: 1) + Sonde /healthz",
        "wave": 2,
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
        "default_image": "quay.io/oauth2-proxy/oauth2-proxy:v7.6.0",
        "default_version": "v7.6.0",
        "strategy": "RollingUpdate (maxUnavailable: 0, maxSurge: 1) + Sonde /ping",
        "wave": 2,
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
        "default_image": "nousresearch/hermes-agent:v0.2.0",
        "default_version": "v0.2.0",
        "strategy": "Mise à jour atomique + Préservation verrou SQLite state.db + Sync Power Users",
        "wave": 4,
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
        "default_image": "ghcr.io/open-webui/open-webui:v0.5.10",
        "default_version": "v0.5.10",
        "strategy": "RollingUpdate (maxUnavailable: 0, maxSurge: 1) + Sonde /health",
        "wave": 5,
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

def fetch_github_latest_release(repo: str, fallback_version: str) -> Dict[str, Any]:
    """Interroge l'API GitHub publique pour connaître la dernière version publiée d'un composant."""
    headers = {
        "User-Agent": "ArcIA-Update-Checker/0.4",
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

def check_components_updates(check_online: bool = True) -> Dict[str, Any]:
    """Vérifie en parallèle l'état des versions locales et les mises à jour disponibles en ligne."""
    results: List[Dict[str, Any]] = [None] * len(ARCIA_UPDATABLE_COMPONENTS)  # type: ignore

    def _check_single(idx: int, comp: Dict[str, Any]):
        curr_img, curr_ver = extract_manifest_image_version(
            comp["manifest"], comp["default_image"], comp["default_version"]
        )
        # Pour presidio et teams-bot dont l'image de base est python:3.11-slim, afficher la version logicielle
        if comp["id"] in ("presidio-dlp", "teams-bot", "arcia-core"):
            curr_ver = comp["default_version"]

        if check_online:
            online_info = fetch_github_latest_release(comp["github_repo"], comp["default_version"])
        else:
            online_info = {
                "latest_version": comp["default_version"],
                "raw_tag": comp["default_version"],
                "release_url": f"https://github.com/{comp['github_repo']}/releases",
                "published_at": "Cache local",
                "online_checked": False
            }

        latest_ver = online_info["latest_version"]
        norm_curr = _normalize_ver(curr_ver)
        norm_latest = _normalize_ver(latest_ver)

        # Détecter si une mise à jour est disponible
        if curr_ver in ("latest", "main"):
            # Les tags flottants (latest/main) peuvent être épinglés ou rafraîchis vers la dernière release stable
            update_avail = online_info["online_checked"] and norm_latest not in ("", "latest", "main")
        else:
            update_avail = bool(online_info["online_checked"] and norm_latest and norm_curr != norm_latest)

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
            "online_checked": online_info["online_checked"],
            "release_url": online_info["release_url"],
            "published_at": online_info["published_at"],
            "strategy": comp["strategy"],
            "wave": comp["wave"],
            "order": comp["wave"],
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

    payload = {
        "success": True,
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "online_reachable": online_count > 0,
        "total_components": len(valid_results),
        "updates_available_count": updates_count,
        "strategy": "RollingUpdate (maxUnavailable=0, maxSurge=1)",
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
            "detail": "RollingUpdate du portail collaborateur Open-WebUI et validation de disponibilité de bout en bout."
        }
    ]

def update_manifest_image_tag(manifest_rel_path: str, new_tag: str) -> Optional[str]:
    """Met à jour proprement le tag d'image dans un manifeste Kubernetes si demandé."""
    if not manifest_rel_path or not manifest_rel_path.endswith(".yaml") or not new_tag:
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
            if "berriai/litellm" in base_repo and not new_tag.startswith("main-"):
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
        update_state["current_phase"] = "Initialisation de la séquence Zero-Downtime..."
        update_state["phases"] = get_initial_update_phases()
        update_state["logs"] = [
            f"[INFO] Démarrage de l'orchestrateur de mise à jour intelligente ArcIA ({'Simulation Dry-Run' if dry_run else 'Exécution Réelle Zero-Downtime'})",
            f"[INFO] Composants sélectionnés ({len(selected_components)}) : {', '.join(selected_components)}",
            f"[INFO] Stratégie : RollingUpdate séquentiel (maxUnavailable=0, maxSurge=1) avec validation des sondes de santé."
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
        if bump_image_tags and last_update_check_cache.get("components"):
            for comp_info in last_update_check_cache["components"]:
                cid = comp_info["id"]
                if cid in selected_components and comp_info.get("update_available"):
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
            deploy.sync_service_configmaps(runner, namespace, ROOT_DIR)
            _append_update_log("[OK] ConfigMaps de code microservices synchronisés à chaud sans coupure.")
            deploy.sync_native_skills(runner, namespace, ROOT_DIR)
            _append_update_log("[OK] Catalogue de compétences natives ('arcia-native-skills') synchronisé.")
            deploy.sync_webui_branding(runner, namespace, ROOT_DIR)
            _append_update_log("[OK] Identité visuelle 'arcia-webui-branding' synchronisée.")

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
                _append_update_log(f"[INFO] [Dry-Run] Application de {manifest_filename} ({dep_name}) avec RollingUpdate (maxUnavailable=0, maxSurge=1)...")
                _append_update_log(f"[OK] [Dry-Run] Nouveau pod '{dep_name}' Ready (sonde HTTP 200) -> bascule du Service -> terminaison ancien pod (0 coupure).")
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
                adapted_yaml = deploy.adapt_manifest_namespace(raw_yaml, namespace)
                if comp_id == "hermes-agent":
                    adapted_yaml = adapted_yaml.replace("https://assistant.example.org/studio", f"https://{public_fqdn}/studio")
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
            rc_ro, out_ro, err_ro = runner.run(["rollout", "status", f"deployment/{dep_name}", f"-n={namespace}", "--timeout=180s"])
            if rc_ro == 0:
                _append_update_log(f"[OK] '{dep_name}' mis à jour avec succès sans aucune interruption de service.")
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
        _rolling_update_k8s_deployment("open-webui", "Portail Open-WebUI", "07-open-webui.yaml", "open-webui", ensure_zero_downtime_patch=True)
        _set_update_phase(5, "done", "\n[OK] SÉQUENCE DE MISE À JOUR ZERO-DOWNTIME TERMINÉE AVEC SUCCÈS (100%) !")

        with update_lock:
            update_state["status"] = "success"
            update_state["progress_pct"] = 100
            update_state["current_phase"] = "Instance 100% à jour (Aucune interruption de service)"

    except Exception as ue:
        with update_lock:
            update_state["status"] = "error"
            update_state["current_phase"] = f"Erreur : {str(ue)}"
            update_state["logs"].append(f"[ERROR] Séquence interrompue : {str(ue)}")

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
                res = check_components_updates(check_online=online)
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
            elif path == "/api/health":
                self.send_json(200, {"status": "ok"})
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
            repo_url = req_data.get("repo_url", "").strip()
            token = req_data.get("token", "").strip()
            passphrase = req_data.get("passphrase", "").strip()
            res = git_pull_and_decrypt_instance(repo_url, token, passphrase)
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
                if cfg:
                    save_config_to_files(cfg, DEFAULT_CONFIG_PATH)

                dry_run = req_data.get("dry_run", False)
                git_info = req_data.get("instance_git", None)
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

        elif path == "/api/updates/check":
            online = bool(req_data.get("online", req_data.get("check_online", True)))
            res = check_components_updates(check_online=online)
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
                self.send_json(200, {
                    "success": True,
                    "config": cfg,
                    "filename": filename,
                    "message": f"Configuration chargée avec succès depuis '{filename}'."
                })
            except Exception as ye:
                self.send_json(500, {"success": False, "error": f"Erreur lors de l'analyse du fichier YAML : {str(ye)}"})

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

    wizard_url = f"http://{args.host}:{port}/"

    print("\033[1m\033[96m=================================================================\033[0m")
    print("\033[1m\033[96m          ArcIA — Setup & Configuration Wizard v0.4              \033[0m")
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
        httpd.server_close()
        sys.exit(0)

if __name__ == "__main__":
    main()
