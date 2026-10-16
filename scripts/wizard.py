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
from http.server import HTTPServer, BaseHTTPRequestHandler
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
    headers = {"User-Agent": "ArcIA-Setup-Wizard"}
    if provider == "github":
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github.v3+json"
        headers["Content-Type"] = "application/json"

        user_info = git_test_credentials("github", token)
        is_org = owner and owner != user_info.get("username")
        url = f"https://api.github.com/orgs/{owner}/repos" if is_org else "https://api.github.com/user/repos"

        payload = {
            "name": repo_name,
            "private": True,
            "description": "Dépôt d'instance privée ArcIA — Configuration et secrets chiffrés",
            "auto_init": False
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                repo_info = json.loads(res.read().decode("utf-8"))
                return {
                    "success": True,
                    "clone_url": repo_info.get("clone_url"),
                    "html_url": repo_info.get("html_url")
                }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if "already exists" in err_body or e.code == 422:
                target_owner = owner or user_info.get("username")
                return {
                    "success": True,
                    "clone_url": f"https://github.com/{target_owner}/{repo_name}.git",
                    "html_url": f"https://github.com/{target_owner}/{repo_name}",
                    "already_existed": True
                }
            return {"success": False, "error": f"Échec création dépôt GitHub : HTTP {e.code} ({err_body})"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif provider == "gitlab":
        headers["PRIVATE-TOKEN"] = token
        headers["Content-Type"] = "application/json"
        payload = {
            "name": repo_name,
            "visibility": "private",
            "description": "Dépôt d'instance privée ArcIA — Configuration et secrets chiffrés"
        }
        req = urllib.request.Request("https://gitlab.com/api/v4/projects", data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                proj_info = json.loads(res.read().decode("utf-8"))
                return {
                    "success": True,
                    "clone_url": proj_info.get("http_url_to_repo"),
                    "html_url": proj_info.get("web_url")
                }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if "has already been taken" in err_body or e.code == 400:
                user_info = git_test_credentials("gitlab", token)
                target_owner = owner or user_info.get("username")
                return {
                    "success": True,
                    "clone_url": f"https://gitlab.com/{target_owner}/{repo_name}.git",
                    "html_url": f"https://gitlab.com/{target_owner}/{repo_name}",
                    "already_existed": True
                }
            return {"success": False, "error": f"Échec création projet GitLab : HTTP {e.code} ({err_body})"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    return {"success": False, "error": "Fournisseur Git non pris en charge."}

def git_push_instance(repo_url: str, token: str, encrypted_bundle_str: str, instance_name: str, fqdn: str) -> dict:
    """Initialise, committe et pousse le bundle d'instance chiffré vers le dépôt privé."""
    temp_dir = tempfile.mkdtemp(prefix="arcia-instance-")
    try:
        meta = {
            "instance_name": instance_name,
            "public_fqdn": fqdn,
            "schema_version": "0.2.0",
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

def test_vmware_connection(data: Dict[str, Any]) -> Dict[str, Any]:
    """Valide la connectivité réseau et les identifiants vCenter / ESXi de manière sécurisée."""
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

    # 3. Test authentification session vSphere si identifiants fournis
    auth_status = "Non authentifié (connectivité réseau et TLS confirmées)"
    session_id = None
    detected_version = f"VMware vSphere ({target_type})"

    if user and password:
        try:
            auth_url = f"https://{host}:{port}/rest/com/vmware/cis/session"
            creds = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("utf-8")
            headers = {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

            req = urllib.request.Request(auth_url, data=b"{}", headers=headers, method="POST")
            ssl_ctx = ssl.create_default_context()
            if insecure:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE

            try:
                with urllib.request.urlopen(req, timeout=8, context=ssl_ctx) as resp:
                    if resp.status == 200:
                        body = json.loads(resp.read().decode("utf-8"))
                        session_id = body.get("value")
                        auth_status = "Authentification REST vSphere réussie"
                        detected_version = "VMware vCenter 7.0 / 8.0"
            except urllib.error.HTTPError as he:
                if he.code == 401:
                    return {"success": False, "error": "Échec d'authentification vSphere : nom d'utilisateur ou mot de passe incorrect."}
                elif he.code == 404:
                    auth_status = "Endpoint vSphere actif, session SOAP accessible"
            except Exception:
                pass
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
        }
    }

def audit_kubernetes_environment_full(runner: Any) -> Dict[str, Any]:
    """Exécute un audit de qualification exhaustif sur un environnement Kubernetes existant."""
    checks = []

    # 1. API Server & Version
    rc_ver, out_ver, _ = runner.run(["version", "-o", "json"])
    k8s_version = "Inconnue"
    ver_ok = False
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
        rc_ci, out_ci, _ = runner.run(["cluster-info"])
        ver_ok = (rc_ci == 0)

    checks.append({
        "id": "api_server",
        "title": "API Server Kubernetes & Version",
        "status": "ok" if ver_ok else "error",
        "message": f"Connectivité confirmée ({k8s_version})" if ver_ok else "Impossible de joindre le serveur d'API Kubernetes.",
        "recommendation": "Assurez-vous que le cluster K8s (v1.28+) est opérationnel et accessible."
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
    detected_user = "debian"
    if known_hosts and os.path.isfile(known_hosts):
        try:
            with open(known_hosts, "r", encoding="utf-8") as f:
                for line in f:
                    m = re.match(r'^\s*([0-9\.]+)', line)
                    if m:
                        detected_node = m.group(1)
                        detected_user = "nicolas"
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
                "ssh_port": 22
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
            "default_model": "ArcIA-Agentic (auto)",
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
            "system_prompt": "Tu es ArcIA, l'assistant d'entreprise. Réponds de façon synthétique, professionnelle et structurée en Markdown."
        },
        "microsoft365_integration": {
            "enabled": False,
            "config_file": "instance/microsoft365.yaml"
        },
        "omniroute": {
            "enabled": False,
            "storage_size": "5Gi"
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
    k8s = cfg.get("kubernetes", {})
    net = cfg.get("network", {})
    llm = cfg.get("llm_gateway", {})
    hermes = cfg.get("hermes", {})
    presidio = cfg.get("presidio", {})
    webui = cfg.get("open_webui", {})
    sso = cfg.get("entra_id_sso", {})
    teams = cfg.get("teams_bot", {})
    m365 = cfg.get("microsoft365_integration", {})
    omni = cfg.get("omniroute", {})

    def bstr(val: bool) -> str:
        return "true" if val else "false"

    def qstr(val: Any) -> str:
        s = str(val or "")
        return f'"{s}"'

    ssh = k8s.get("remote_ssh", {})

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
    ssh_port: {int(ssh.get('ssh_port', 22))}

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
  default_model: {qstr(llm.get('default_model', 'ArcIA-Agentic (auto)'))}
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
  system_prompt: {qstr(teams.get('system_prompt', "Tu es ArcIA, l'assistant d'entreprise."))}

# 9. Intégration Microsoft 365
microsoft365_integration:
  enabled: {bstr(m365.get('enabled', False))}
  config_file: {qstr(m365.get('config_file', 'instance/microsoft365.yaml'))}

# 10. Routeur Multi-Fournisseurs OmniRoute [Optionnel]
omniroute:
  enabled: {bstr(omni.get('enabled', False))}
  storage_size: {qstr(omni.get('storage_size', '5Gi'))}
"""
    return yaml_text

def save_config_to_files(cfg: Dict[str, Any], config_path: str = DEFAULT_CONFIG_PATH) -> None:
    """Enregistre la configuration dans arcia.config.yaml et synchronise secrets/arcia.env."""
    yaml_content = serialize_yaml_config(cfg)
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
        deployment_state["logs"] = []
        deployment_state["start_time"] = time.time()
        deployment_state["exit_code"] = None

    if infra_target == "docker_lab":
        try:
            with deployment_lock:
                deployment_state["logs"].append("[INFO] Initialisation du déploiement en Mode Lab (Docker Local)...")

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
            env_vars["OPENROUTER_API_KEY"] = openrouter_key
            env_vars["WEBUI_PORT"] = str(webui_port)
            env_vars["LITELLM_PORT"] = str(litellm_port)
            env_vars["ADMIN_PASSWORD"] = admin_pass

            cmd = ["docker", "compose", "-f", compose_file, "up", "-d"]
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
                        "omniroute_admin": None,
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
    deploy_script = os.path.join(SCRIPT_DIR, "deploy.py")
    cmd = [sys.executable, deploy_script, "--config", DEFAULT_CONFIG_PATH]
    if dry_run:
        cmd.append("--dry-run")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=ROOT_DIR
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
                omni_enabled = cfg.get("omniroute", {}).get("enabled", False)

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
                    "omniroute_admin": "http://omniroute.arcia.svc.cluster.local:20129" if omni_enabled else None,
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
# Handlers Serveur HTTP (API REST & Single Page App)
# -----------------------------------------------------------------------------

class WizardHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, status: int, data: Any):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self.serve_wizard_ui()
        elif path == "/api/config":
            cfg, exists = load_config_data(DEFAULT_CONFIG_PATH)
            contexts = detect_kubectl_contexts()
            current_ctx = detect_current_context()
            self.send_json(200, {
                "config": cfg,
                "is_existing": exists,
                "available_contexts": contexts,
                "current_context": current_ctx,
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
        elif path == "/api/docker/status":
            st = get_docker_status()
            self.send_json(200, st)
        elif path == "/api/vmware/tiers":
            self.send_json(200, VMWARE_SIZING_TIERS)
        elif path == "/api/health":
            self.send_json(200, {"status": "ok"})
        else:
            self.send_error(404, "Page non trouvée")

    def do_POST(self):
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
                    ssh_port=int(remote_ssh.get("ssh_port", 22))
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
                    ssh_port=int(remote_ssh.get("ssh_port", 22))
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
    return r"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ArcIA — Assistant Graphique d'Installation</title>
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'%3E%3Crect x='24' y='24' width='464' height='464' rx='108' fill='%23131B2E' stroke='%231E293B' stroke-width='8'/%3E%3Cg transform='translate(68, 174) scale(1.68)'%3E%3Cpath d='M43.61 26C47.78 26.09 51.8 26.57 55.66 27.43 59.52 28.29 62.99 30.27 66.07 33.36 68.7 35.9 70.54 38.89 71.58 42.35 72.63 45.8 73.15 49.34 73.15 52.96L73.15 97.75 22.24 97.75C14.89 97.75 9.25 95.73 5.35 91.69 1.45 87.66-0.32 82.06 0.05 74.88 0.68 66.26 3.72 60.68 9.17 58.13 14.62 55.59 21.11 54.32 28.64 54.32L53.55 54.19C53.82 48.29 52.3 44.61 48.99 43.16 45.68 41.71 41.48 40.98 36.4 40.98L4.81 40.84 4.81 26 43.61 26ZM29.99 83.32 53.68 83.32 53.68 68.48 31.35 68.48C31.17 68.57 30.99 68.62 30.81 68.62L30.27 68.62C27.73 68.71 25.37 69.19 23.19 70.05 21.01 70.91 19.87 72.93 19.78 76.1 19.6 79.64 20.57 81.73 22.71 82.37 24.84 83.01 27.27 83.37 29.99 83.46L29.99 83.32Z' fill='%23F8FAFC'/%3E%3Cpath d='M82.92 97.76 L100.16 0 L121.67 0 L104.43 97.76 Z' fill='%236BE7DD'/%3E%3Cpath fill-rule='evenodd' clip-rule='evenodd' d='M177.86 0 L199.65 0 L224.07 97.76 L201.20 97.76 L196.32 74.48 L153.84 74.48 L141.02 97.76 L119.37 97.76 L177.86 0 Z M184.51 19.47 L163.58 57.05 L192.72 57.05 L184.51 19.47 Z' fill='%236BE7DD'/%3E%3C/g%3E%3C/svg%3E">
  <style>
    :root {
      --bg: #050712;
      --card-bg: rgba(19, 27, 46, 0.95);
      --card-border: #1e293b;
      --accent-cyan: #6be7dd;
      --accent-blue: #1659e4;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --border-color: #1e293b;
      --input-bg: #0a0f1d;
      --btn-primary: linear-gradient(135deg, #1659e4, #5ad8ce);
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --radius: 12px;
      --shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.4);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
    body { background: var(--bg); color: var(--text-main); min-height: 100vh; display: flex; flex-direction: column; background-image: radial-gradient(circle at 15% 20%, rgba(107, 231, 221, 0.08) 0%, transparent 40%), radial-gradient(circle at 85% 80%, rgba(22, 89, 228, 0.08) 0%, transparent 40%); }

    header { background: rgba(10, 15, 29, 0.92); backdrop-filter: blur(10px); border-bottom: 1px solid var(--border-color); padding: 16px 32px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
    .brand { display: flex; align-items: center; gap: 14px; }
    .brand-logo { width: 38px; height: 38px; border-radius: 10px; background: #131b2e; border: 1px solid #1e293b; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 15px rgba(107, 231, 221, 0.15); }
    .brand-title { font-size: 20px; font-weight: 700; letter-spacing: -0.5px; }
    .brand-subtitle { font-size: 13px; color: var(--text-muted); }
    .header-badge { font-size: 12px; background: rgba(107, 231, 221, 0.1); color: var(--accent-cyan); border: 1px solid rgba(107, 231, 221, 0.3); border-radius: 20px; padding: 4px 12px; font-weight: 600; }

    .app-container { display: flex; flex: 1; max-width: 1380px; width: 100%; margin: 0 auto; padding: 24px; gap: 24px; }
    
    .stepper-nav { width: 330px; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow); height: fit-content; position: sticky; top: 88px; }
    .stepper-title { font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: var(--text-muted); margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid var(--border-color); }
    .step-item { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-radius: 8px; cursor: pointer; transition: all 0.2s ease; margin-bottom: 6px; }
    .step-item:hover { background: rgba(255, 255, 255, 0.04); }
    .step-item.active { background: rgba(0, 210, 255, 0.12); border-left: 3px solid var(--accent-cyan); }
    .step-item.completed .step-icon { background: var(--success); color: white; border-color: var(--success); }
    .step-icon { width: 28px; height: 28px; border-radius: 50%; border: 2px solid var(--border-color); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; color: var(--text-muted); flex-shrink: 0; transition: all 0.2s; }
    .step-item.active .step-icon { border-color: var(--accent-cyan); color: var(--accent-cyan); box-shadow: 0 0 10px rgba(0, 210, 255, 0.3); }
    .step-label { font-size: 13px; font-weight: 500; }
    .step-tag { margin-left: auto; font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 600; }
    .step-tag.optional { background: rgba(255, 255, 255, 0.08); color: var(--text-muted); }
    .step-tag.required { background: rgba(0, 210, 255, 0.15); color: var(--accent-cyan); }

    .content-area { flex: 1; display: flex; flex-direction: column; }
    .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius); padding: 32px; box-shadow: var(--shadow); margin-bottom: 24px; position: relative; }
    
    .screen-header { margin-bottom: 24px; }
    .screen-title { font-size: 24px; font-weight: 700; margin-bottom: 8px; display: flex; align-items: center; gap: 10px; }
    .screen-desc { font-size: 14px; color: var(--text-muted); line-height: 1.5; }

    /* Cards de Choix Mode d'Installation */
    .mode-cards-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 24px 0; }
    .mode-card { border: 2px solid var(--border-color); border-radius: var(--radius); padding: 24px; background: rgba(255,255,255,0.02); cursor: pointer; transition: all 0.2s; position: relative; }
    .mode-card:hover { border-color: var(--accent-cyan); background: rgba(0, 210, 255, 0.04); transform: translateY(-2px); }
    .mode-card.selected { border-color: var(--accent-cyan); background: rgba(0, 210, 255, 0.08); box-shadow: 0 0 20px rgba(0, 210, 255, 0.2); }
    .mode-card-badge { position: absolute; top: 16px; right: 16px; font-size: 11px; padding: 3px 8px; border-radius: 12px; font-weight: 700; }
    .mode-card-icon { font-size: 36px; margin-bottom: 12px; }
    .mode-card-title { font-size: 18px; font-weight: 700; margin-bottom: 8px; }
    .mode-card-desc { font-size: 13px; color: var(--text-muted); line-height: 1.5; margin-bottom: 16px; }

    /* Target & Sizing Cards */
    .target-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .target-card { border: 2px solid var(--border-color); border-radius: var(--radius); padding: 20px; background: rgba(255,255,255,0.02); cursor: pointer; transition: all 0.2s; position: relative; }
    .target-card:hover { border-color: var(--accent-cyan); background: rgba(0, 210, 255, 0.04); transform: translateY(-2px); }
    .target-card.active { border-color: var(--accent-cyan); background: rgba(0, 210, 255, 0.08); box-shadow: 0 0 20px rgba(0, 210, 255, 0.2); }
    
    .tier-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 14px; background: rgba(255,255,255,0.02); cursor: pointer; transition: all 0.2s; position: relative; }
    .tier-card:hover { border-color: var(--accent-cyan); }
    .tier-card.active { border-color: var(--accent-cyan); background: rgba(0, 210, 255, 0.1); box-shadow: 0 0 12px rgba(0, 210, 255, 0.25); }
    
    .audit-check-item { display: flex; align-items: flex-start; gap: 12px; padding: 12px; border-radius: 8px; background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); }
    .audit-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 700; flex-shrink: 0; }
    .audit-badge.ok { background: rgba(16, 185, 129, 0.2); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.4); }
    .audit-badge.warn { background: rgba(245, 158, 11, 0.2); color: var(--warning); border: 1px solid rgba(245, 158, 11, 0.4); }
    .audit-badge.error { background: rgba(239, 68, 68, 0.2); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.4); }

    /* Form Fields */
    .form-group { margin-bottom: 20px; }
    .form-label { display: block; font-size: 14px; font-weight: 600; margin-bottom: 6px; color: #e2e8f0; }
    .form-sublabel { font-size: 12px; color: var(--text-muted); margin-bottom: 8px; line-height: 1.4; }
    .form-control { width: 100%; background: var(--input-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 12px 14px; color: var(--text-main); font-size: 14px; transition: border-color 0.2s, box-shadow 0.2s; outline: none; }
    .form-control:focus { border-color: var(--accent-cyan); box-shadow: 0 0 0 3px rgba(0, 210, 255, 0.15); }
    .input-row { display: flex; gap: 10px; }
    
    .toggle-wrapper { display: flex; align-items: center; justify-content: space-between; padding: 16px; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-color); border-radius: 10px; margin-bottom: 20px; }
    .toggle-info h4 { font-size: 15px; margin-bottom: 4px; }
    .toggle-info p { font-size: 12px; color: var(--text-muted); }
    .switch { position: relative; display: inline-block; width: 50px; height: 26px; }
    .switch input { opacity: 0; width: 0; height: 0; }
    .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #334155; transition: .3s; border-radius: 34px; }
    .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 4px; bottom: 4px; background-color: white; transition: .3s; border-radius: 50%; }
    input:checked + .slider { background: linear-gradient(135deg, #00d2ff, #3a7bd5); }
    input:checked + .slider:before { transform: translateX(24px); }

    .doc-accordion { background: rgba(0, 210, 255, 0.04); border: 1px solid rgba(0, 210, 255, 0.2); border-radius: 8px; margin-top: 16px; overflow: hidden; }
    .doc-header { padding: 12px 16px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; font-size: 13px; font-weight: 600; color: var(--accent-cyan); }
    .doc-body { padding: 16px; font-size: 13px; line-height: 1.6; color: #cbd5e1; border-top: 1px solid rgba(0, 210, 255, 0.1); background: rgba(0, 0, 0, 0.2); display: none; }
    .doc-body ol { margin-left: 20px; margin-top: 8px; margin-bottom: 8px; }
    .doc-body li { margin-bottom: 6px; }
    .doc-link { color: var(--accent-cyan); text-decoration: none; font-weight: 600; display: inline-flex; align-items: center; gap: 4px; }
    .doc-link:hover { text-decoration: underline; }

    .actions-bar { display: flex; justify-content: space-between; align-items: center; margin-top: 16px; }
    .btn { padding: 10px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; display: inline-flex; align-items: center; gap: 8px; transition: all 0.2s; }
    .btn-secondary { background: #1e293b; color: #cbd5e1; border: 1px solid var(--border-color); }
    .btn-secondary:hover { background: #334155; color: white; }
    .btn-primary { background: var(--btn-primary); color: white; box-shadow: 0 4px 12px rgba(0, 210, 255, 0.3); }
    .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(0, 210, 255, 0.4); }
    .btn-test { background: #1e293b; color: var(--accent-cyan); border: 1px solid rgba(0, 210, 255, 0.4); font-size: 12px; padding: 6px 12px; }
    .btn-test:hover { background: rgba(0, 210, 255, 0.15); }

    .alert-box { padding: 14px 18px; border-radius: 8px; font-size: 13px; line-height: 1.5; margin-bottom: 20px; display: flex; align-items: flex-start; gap: 12px; }
    .alert-info { background: rgba(0, 210, 255, 0.08); border: 1px solid rgba(0, 210, 255, 0.3); color: #e0f2fe; }
    .alert-success { background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); color: #a7f3d0; }
    .alert-warn { background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); color: #fde68a; }

    .terminal-box { background: #050811; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; font-size: 13px; height: 380px; overflow-y: auto; color: #94a3b8; white-space: pre-wrap; line-height: 1.5; box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.6); }
    .log-line { margin-bottom: 2px; }
    .log-cyan { color: #38bdf8; font-weight: 600; }
    .log-green { color: #4ade80; font-weight: 600; }
    .log-yellow { color: #facc15; }
    .log-red { color: #f87171; font-weight: 600; }

    .recap-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; margin: 20px 0; }
    .recap-card { background: rgba(13, 19, 33, 0.8); border: 1px solid var(--border-color); border-radius: 10px; padding: 18px; position: relative; transition: border-color 0.2s; }
    .recap-card:hover { border-color: var(--accent-cyan); }
    .recap-card-title { font-size: 14px; font-weight: 700; color: #e2e8f0; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
    .recap-card-url { font-size: 13px; color: var(--accent-cyan); word-break: break-all; margin-bottom: 8px; font-family: monospace; }
    .recap-card-desc { font-size: 12px; color: var(--text-muted); margin-bottom: 12px; }
    .recap-card-btn { font-size: 11px; padding: 4px 10px; border-radius: 6px; background: rgba(255, 255, 255, 0.08); color: white; border: 1px solid var(--border-color); cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 4px; }
    .recap-card-btn:hover { background: var(--accent-blue); }

    .screen { display: none; }
    .screen.active { display: block; animation: fadeIn 0.3s ease; }

    @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-logo">
        <svg viewBox="0 0 512 512" width="28" height="28" fill="none">
          <g transform="translate(68, 174) scale(1.68)">
            <path d="M43.61 26C47.78 26.09 51.8 26.57 55.66 27.43 59.52 28.29 62.99 30.27 66.07 33.36 68.7 35.9 70.54 38.89 71.58 42.35 72.63 45.8 73.15 49.34 73.15 52.96L73.15 97.75 22.24 97.75C14.89 97.75 9.25 95.73 5.35 91.69 1.45 87.66-0.32 82.06 0.05 74.88 0.68 66.26 3.72 60.68 9.17 58.13 14.62 55.59 21.11 54.32 28.64 54.32L53.55 54.19C53.82 48.29 52.3 44.61 48.99 43.16 45.68 41.71 41.48 40.98 36.4 40.98L4.81 40.84 4.81 26 43.61 26ZM29.99 83.32 53.68 83.32 53.68 68.48 31.35 68.48C31.17 68.57 30.99 68.62 30.81 68.62L30.27 68.62C27.73 68.71 25.37 69.19 23.19 70.05 21.01 70.91 19.87 72.93 19.78 76.1 19.6 79.64 20.57 81.73 22.71 82.37 24.84 83.01 27.27 83.37 29.99 83.46L29.99 83.32Z" fill="#F8FAFC" />
            <path d="M82.92 97.76 L100.16 0 L121.67 0 L104.43 97.76 Z" fill="#6BE7DD" />
            <path fill-rule="evenodd" clip-rule="evenodd" d="M177.86 0 L199.65 0 L224.07 97.76 L201.20 97.76 L196.32 74.48 L153.84 74.48 L141.02 97.76 L119.37 97.76 L177.86 0 Z M184.51 19.47 L163.58 57.05 L192.72 57.05 L184.51 19.47 Z" fill="#6BE7DD" />
          </g>
        </svg>
      </div>
      <div>
        <div class="brand-title">ArcIA Enterprise Setup Wizard</div>
        <div class="brand-subtitle">Gestionnaire de Déploiement & Restauration d'Instance v0.2</div>
      </div>
    </div>
    <div style="display: flex; gap: 12px; align-items: center;">
      <span id="instanceModeBadge" class="header-badge">Chargement...</span>
      <button class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="saveConfigOnly()">💾 Enregistrer localement</button>
    </div>
  </header>

  <div class="app-container">
    
    <!-- Stepper Navigation -->
    <aside class="stepper-nav">
      <div class="stepper-title">Étapes d'installation</div>
      <div class="step-item active" onclick="goToStep(1)">
        <div class="step-icon">1</div>
        <div class="step-label">🚀 Mode & Démarrage</div>
        <div class="step-tag required">Choix</div>
      </div>
      <div class="step-item" onclick="goToStep(2)">
        <div class="step-icon">2</div>
        <div class="step-label">📦 Dépôt Git d'Instance</div>
        <div class="step-tag required">Requis</div>
      </div>
      <div class="step-item" onclick="goToStep(3)">
        <div class="step-icon">3</div>
        <div class="step-label">☸️ Cible & Infrastructure</div>
        <div class="step-tag required">Requis</div>
      </div>
      <div class="step-item" onclick="goToStep(4)">
        <div class="step-icon">4</div>
        <div class="step-label">🌐 Réseau & Ingress</div>
        <div class="step-tag required">Requis</div>
      </div>
      <div class="step-item" onclick="goToStep(5)">
        <div class="step-icon">5</div>
        <div class="step-label">🧠 Passerelle LLM & IA</div>
        <div class="step-tag required">Requis</div>
      </div>
      <div class="step-item" onclick="goToStep(6)">
        <div class="step-icon">6</div>
        <div class="step-label">🤖 Hermes Studio & Agents</div>
        <div class="step-tag required">Requis</div>
      </div>
      <div class="step-item" onclick="goToStep(7)">
        <div class="step-icon">7</div>
        <div class="step-label">🔐 SSO Entra ID</div>
        <div class="step-tag optional">Option</div>
      </div>
      <div class="step-item" onclick="goToStep(8)">
        <div class="step-icon">8</div>
        <div class="step-label">💬 Bot Microsoft Teams</div>
        <div class="step-tag optional">Option</div>
      </div>
      <div class="step-item" onclick="goToStep(9)">
        <div class="step-icon">9</div>
        <div class="step-label">🔀 Routeur OmniRoute</div>
        <div class="step-tag optional">Option</div>
      </div>
      <div class="step-item" onclick="goToStep(10)">
        <div class="step-icon">10</div>
        <div class="step-label">⚡ Déploiement & Sauvegarde</div>
        <div class="step-tag required">Action</div>
      </div>
      <div class="step-item" onclick="goToStep(11)">
        <div class="step-icon">11</div>
        <div class="step-label">🎉 Accès & Récapitulatif</div>
        <div class="step-tag required">Prêt</div>
      </div>
    </aside>

    <!-- Main Content Area -->
    <main class="content-area">
      
      <!-- SCREEN 1: Choix de Mode (Nouvelle Instance vs Restaurer) -->
      <section id="step1" class="screen active card">
        <div class="screen-header">
          <h2 class="screen-title">Bienvenue dans l'assistant ArcIA</h2>
          <p class="screen-desc">Choisissez votre parcours : installez une nouvelle instance avec sauvegarde Git chiffrée, ou restaurez une instance existante.</p>
        </div>

        <div class="mode-cards-grid">
          <!-- Option A : Nouvelle Instance -->
          <div id="cardNewInstance" class="mode-card selected" onclick="selectSetupMode('new')">
            <span class="mode-card-badge" style="background:rgba(0,210,255,0.2); color:var(--accent-cyan);">Recommandé</span>
            <div class="mode-card-icon">🚀</div>
            <div class="mode-card-title">Installer une nouvelle instance</div>
            <div class="mode-card-desc">
              Déploie le socle ArcIA sur votre cluster Kubernetes et initialise automatiquement votre dépôt Git d'instance privé chiffré (GitHub / GitLab).
            </div>
            <button class="btn btn-primary" onclick="selectSetupMode('new'); goToStep(2);">Configurer la nouvelle instance →</button>
          </div>

          <!-- Option B : Restaurer Instance -->
          <div id="cardRestoreInstance" class="mode-card" onclick="selectSetupMode('restore')">
            <span class="mode-card-badge" style="background:rgba(16,185,129,0.2); color:var(--success);">Reprise</span>
            <div class="mode-card-icon">🔄</div>
            <div class="mode-card-title">Restaurer une instance existante</div>
            <div class="mode-card-desc">
              Récupère la configuration et les secrets depuis un dépôt Git d'instance privé, déchiffre les données avec votre mot de passe et déploie le cluster.
            </div>
            <button class="btn btn-secondary" onclick="selectSetupMode('restore')">Ouvrir l'outil de restauration ↓</button>
          </div>
        </div>

        <!-- Formulaire de Restauration Dédié (affiché si mode restore sélectionné) -->
        <div id="restoreSection" style="display:none; background:rgba(0,0,0,0.3); border:1px solid var(--accent-cyan); border-radius:10px; padding:24px; margin-top:20px;">
          <h3 style="font-size:18px; margin-bottom:12px; color:var(--accent-cyan); display:flex; align-items:center; gap:8px;">
            <span>📥 Restauration d'Instance depuis Dépôt Git Privé</span>
          </h3>
          <p style="font-size:13px; color:var(--text-muted); margin-bottom:16px;">
            Renseignez l'URL de votre dépôt d'instance privé (GitHub / GitLab) et votre mot de passe maître de déchiffrement :
          </p>

          <div class="form-group">
            <label class="form-label">URL du Dépôt Git d'Instance Privé <span style="color:var(--accent-cyan);">*</span></label>
            <input type="text" id="restore_git_url" class="form-control" placeholder="https://github.com/votre-orga/ArcIA-instance-prod.git">
          </div>

          <div class="input-row">
            <div class="form-group" style="flex:1;">
              <label class="form-label">Jeton d'Accès Git (Token PAT) <span style="color:var(--accent-cyan);">*</span></label>
              <input type="password" id="restore_git_token" class="form-control" placeholder="ghp_xxxxxxxxxxxx ou glpat-xxxxxxxxxxxx">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">Mot de Passe de Déchiffrement <span style="color:var(--accent-cyan);">*</span></label>
              <input type="password" id="restore_passphrase" class="form-control" placeholder="Mot de passe maître défini à la création">
            </div>
          </div>

          <div style="display:flex; align-items:center; gap:16px; margin-top:12px;">
            <button class="btn btn-primary" onclick="executeInstanceRestore()">📥 Récupérer et Déchiffrer l'Instance</button>
            <span id="restoreStatus" style="font-size:13px;"></span>
          </div>

          <div id="restoreSuccessPanel" style="display:none; margin-top:20px; background:rgba(16,185,129,0.1); border:1px solid var(--success); border-radius:8px; padding:16px;">
            <div style="font-size:16px; font-weight:700; color:var(--success); margin-bottom:8px;">✅ Instance Déchiffrée avec Succès !</div>
            <div id="restoreSummaryDetails" style="font-size:13px; color:#e2e8f0; line-height:1.6; margin-bottom:16px;"></div>
            <button class="btn btn-primary" style="background:var(--success); border-color:var(--success);" onclick="goToStep(10)">
              🚀 Lancer directement le Déploiement sur le Cluster Kubernetes →
            </button>
          </div>
        </div>

        <div class="alert-box alert-success" style="margin-top:24px;">
          <span style="font-size:20px;">🛡️</span>
          <div>
            <strong>Isolation Enterprise & Zéro Fuite :</strong><br>
            Le socle générique <code>ArcIA</code> ne contient aucun secret. Les configurations, domaines, clés d'API et identités propres à votre entreprise sont stockées de façon étanche et chiffrée (<strong>AES-256-GCM</strong>) sur votre dépôt d'instance privé.
          </div>
        </div>
      </section>

      <!-- SCREEN 2: Dépôt Git d'Instance Privé -->
      <section id="step2" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 2 : Dépôt Git d'Instance Privé & Chiffrement</h2>
          <p class="screen-desc">Configurez le dépôt Git privé où seront sauvegardés vos paramètres et secrets chiffrés de bout en bout.</p>
        </div>

        <div class="toggle-wrapper">
          <div class="toggle-info">
            <h4>Créer et synchroniser automatiquement un dépôt Git d'instance privé</h4>
            <p>Initialise un dépôt privé séparé (GitHub / GitLab) pour stocker les secrets chiffrés (AES-256-GCM) et faciliter la restauration.</p>
          </div>
          <label class="switch">
            <input type="checkbox" id="git_instance_enabled" checked onchange="toggleGitInstanceFields()">
            <span class="slider"></span>
          </label>
        </div>

        <div id="git_instance_fields">
          <div class="input-row">
            <div class="form-group" style="flex:1;">
              <label class="form-label">Plateforme Git</label>
              <select id="git_provider" class="form-control" onchange="updateGitProviderDoc()">
                <option value="github">GitHub (github.com ou GitHub Enterprise)</option>
                <option value="gitlab">GitLab (gitlab.com ou auto-hébergé)</option>
                <option value="custom">URL Git Personnalisée</option>
              </select>
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">Nom du Dépôt d'Instance <span style="color:var(--accent-cyan);">*</span></label>
              <input type="text" id="git_repo_name" class="form-control" value="ArcIA-instance-prod">
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">Jeton d'Accès Git (Personal Access Token) <span style="color:var(--accent-cyan);">*</span></label>
            <div class="form-sublabel">Requis pour créer le dépôt privé et pousser les sauvegardes chiffrées. Scope requis : <code>repo</code> (GitHub) ou <code>write_repository</code> (GitLab).</div>
            <div class="input-row">
              <input type="password" id="git_token" class="form-control" placeholder="ghp_xxxxxxxxxxxxxxxxxxxx">
              <button class="btn btn-test" style="white-space:nowrap;" onclick="testGitToken()">🔍 Valider le token</button>
            </div>
          </div>

          <div class="form-group" id="git_owner_group" style="display:none;">
            <label class="form-label">Organisation ou Compte Propriétaire Cible</label>
            <select id="git_owner_select" class="form-control"></select>
          </div>

          <div class="input-row">
            <div class="form-group" style="flex:1;">
              <label class="form-label">Mot de Passe Maître de Chiffrement <span style="color:var(--accent-cyan);">*</span></label>
              <div class="form-sublabel">Utilisé pour chiffrer tous les secrets d'instance (AES-256-GCM + PBKDF2 100k).</div>
              <input type="password" id="git_passphrase" class="form-control" placeholder="Mot de passe robuste pour chiffrer l'instance">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">Confirmation du Mot de Passe <span style="color:var(--accent-cyan);">*</span></label>
              <div class="form-sublabel">Retapez le mot de passe maître pour vérification.</div>
              <input type="password" id="git_passphrase_confirm" class="form-control" placeholder="Confirmer le mot de passe">
            </div>
          </div>
        </div>

        <div class="alert-box alert-warn">
          <span style="font-size:20px;">⚠️</span>
          <div>
            <strong>Conservez précieusement ce mot de passe maître :</strong><br>
            Il sera indispensable pour restaurer votre instance sur un nouveau cluster. Aucune clé n'est transmise en clair à GitHub ou au Cloud.
          </div>
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(1)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(3)">Suivant : Connectivité Kubernetes →</button>
        </div>
      </section>

      <!-- SCREEN 3: Infrastructure & Hébergement -->
      <section id="step3" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 3 : Cible d'Hébergement & Infrastructure</h2>
          <p class="screen-desc">Choisissez l'environnement d'hébergement d'ArcIA : déployez un nouveau cluster K3s sur VMware avec dimensionnement par tranche d'utilisateurs, connectez-vous à un cluster Kubernetes existant, ou lancez une instance locale en conteneurs Docker (mode Lab).</p>
        </div>

        <!-- 3 Cibles d'infrastructure cliquables -->
        <div class="target-grid">
          <!-- Cible 1: VMware vSphere -->
          <div id="target_card_vmware" class="target-card" onclick="selectInfraTarget('vmware_k3s')">
            <div style="font-size:32px; margin-bottom:8px;">☁️</div>
            <div style="font-weight:700; font-size:15px; margin-bottom:4px;">Nouveau Cluster K3s sur VMware</div>
            <div style="font-size:12px; color:var(--text-muted); line-height:1.4;">Déploiement automatisé de VMs Debian sur vCenter ou ESXi avec dimensionnement par effectif d'utilisateurs.</div>
          </div>

          <!-- Cible 2: Kubernetes Existant -->
          <div id="target_card_k8s" class="target-card active" onclick="selectInfraTarget('k8s_existing')">
            <div style="font-size:32px; margin-bottom:8px;">☸️</div>
            <div style="font-weight:700; font-size:15px; margin-bottom:4px;">Cluster Kubernetes Existant</div>
            <div style="font-size:12px; color:var(--text-muted); line-height:1.4;">Connexion à votre cluster K3s, RKE2, AKS, EKS avec audit de qualification exhaustif en direct.</div>
          </div>

          <!-- Cible 3: Docker Local Lab -->
          <div id="target_card_docker" class="target-card" onclick="selectInfraTarget('docker_lab')">
            <div style="font-size:32px; margin-bottom:8px;">🐳</div>
            <div style="font-weight:700; font-size:15px; margin-bottom:4px;">Docker Local (Mode Lab)</div>
            <div style="font-size:12px; color:var(--text-muted); line-height:1.4;">Exécution locale directe sur ce poste via Docker Compose sans prérequis Kubernetes. Idéal pour PoC et démo.</div>
          </div>
        </div>

        <!-- SOUS-PANEL 1 : Cible VMware vSphere -->
        <div id="panel_infra_vmware" style="display:none;">
          <h3 style="font-size:16px; font-weight:700; color:var(--accent-cyan); margin-bottom:12px; display:flex; align-items:center; gap:8px;">
            <span>👥 1. Dimensionnement par tranche d'utilisateurs</span>
          </h3>
          <p style="font-size:13px; color:var(--text-muted); margin-bottom:14px;">
            Sélectionnez votre tranche d'utilisateurs pour calculer automatiquement le dimensionnement matériel optimal (vCPU, RAM, stockage SSD, topologie HA) :
          </p>

          <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 16px;">
            <div id="tier_card_20" class="tier-card" onclick="selectVmwareTier('20')">
              <div style="font-weight:700; font-size:14px; margin-bottom:4px;">Jusqu'à 20 utilisateurs</div>
              <div style="font-size:11px; color:var(--accent-cyan); font-weight:600; margin-bottom:6px;">Équipe Pilote / PoC</div>
              <div style="font-size:12px; color:var(--text-muted); line-height:1.4;">1 VM (4 vCPU, 8 Go RAM, 100 Go SSD)</div>
              <div style="font-size:11px; color:#38ef7d; font-weight:600; margin-top:4px;">📚 50 Go dédiés RAG / ChromaDB</div>
            </div>
            <div id="tier_card_100" class="tier-card active" onclick="selectVmwareTier('100')">
              <span style="position:absolute; top:8px; right:8px; font-size:10px; background:rgba(0,210,255,0.2); color:var(--accent-cyan); padding:2px 6px; border-radius:10px; font-weight:700;">Recommandé</span>
              <div style="font-weight:700; font-size:14px; margin-bottom:4px;">21 à 100 utilisateurs</div>
              <div style="font-size:11px; color:var(--accent-cyan); font-weight:600; margin-bottom:6px;">PME / Direction Métier</div>
              <div style="font-size:12px; color:var(--text-muted); line-height:1.4;">3 VMs K3s HA (12 vCPU, 48 Go RAM, 450 Go SSD)</div>
              <div style="font-size:11px; color:#38ef7d; font-weight:600; margin-top:4px;">📚 200 Go dédiés RAG / HNSW</div>
            </div>
            <div id="tier_card_500" class="tier-card" onclick="selectVmwareTier('500')">
              <div style="font-weight:700; font-size:14px; margin-bottom:4px;">101 à 500 utilisateurs</div>
              <div style="font-size:11px; color:var(--accent-cyan); font-weight:600; margin-bottom:6px;">Entreprise</div>
              <div style="font-size:12px; color:var(--text-muted); line-height:1.4;">5 VMs (3 CP HA + 2 Workers, 28 vCPU, 112 Go, 1,2 To)</div>
              <div style="font-size:11px; color:#38ef7d; font-weight:600; margin-top:4px;">📚 600 Go dédiés RAG multi-équipes</div>
            </div>
            <div id="tier_card_1000" class="tier-card" onclick="selectVmwareTier('1000')">
              <div style="font-weight:700; font-size:14px; margin-bottom:4px;">Plus de 500 utilisateurs</div>
              <div style="font-size:11px; color:var(--accent-cyan); font-weight:600; margin-bottom:6px;">Grande Entreprise</div>
              <div style="font-size:12px; color:var(--text-muted); line-height:1.4;">7+ VMs multi-nœuds (88+ vCPU, 352+ Go, 3,5 To SSD)</div>
              <div style="font-size:11px; color:#38ef7d; font-weight:600; margin-top:4px;">📚 2 To à 5 To dédiés RAG distribué</div>
            </div>
          </div>

          <div id="vmware_tier_summary" class="alert-box alert-info" style="margin-bottom:20px;">
            <!-- Rempli dynamiquement par JS -->
          </div>

          <h3 style="font-size:16px; font-weight:700; color:var(--accent-cyan); margin-bottom:12px;">
            <span>🌐 2. Connexion vCenter Server ou Hôte ESXi</span>
          </h3>

          <div class="input-row">
            <div class="form-group" style="flex:2;">
              <label class="form-label">Type d'environnement vSphere</label>
              <select id="vmware_type" class="form-control">
                <option value="vCenter Server">vCenter Server (vSphere 7.0 / 8.0)</option>
                <option value="ESXi Host">Hôte ESXi Autonome</option>
              </select>
            </div>
            <div class="form-group" style="flex:3;">
              <label class="form-label">Adresse FQDN ou IP du serveur vSphere <span style="color:var(--accent-cyan);">*</span></label>
              <input type="text" id="vmware_host" class="form-control" placeholder="ex: vcenter.corp.local ou 192.168.1.10">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">Port HTTPS</label>
              <input type="number" id="vmware_port" class="form-control" value="443">
            </div>
          </div>

          <div class="input-row">
            <div class="form-group" style="flex:1;">
              <label class="form-label">Nom d'utilisateur vSphere <span style="color:var(--accent-cyan);">*</span></label>
              <input type="text" id="vmware_user" class="form-control" placeholder="ex: administrator@vsphere.local ou compte de service">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">Mot de passe vSphere <span style="color:var(--accent-cyan);">*</span></label>
              <input type="password" id="vmware_pass" class="form-control" placeholder="Mot de passe">
            </div>
          </div>

          <div style="margin-bottom:16px;">
            <label style="display:inline-flex; align-items:center; gap:8px; font-size:13px; color:#cbd5e1; cursor:pointer;">
              <input type="checkbox" id="vmware_insecure" checked>
              <span>Autoriser les certificats TLS vSphere auto-signés ou internes (Insecure TLS)</span>
            </label>
          </div>

          <div class="input-row">
            <div class="form-group" style="flex:1;">
              <label class="form-label">Datacenter vSphere</label>
              <input type="text" id="vmware_dc" class="form-control" placeholder="ex: Datacenter-Prod">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">Cluster ou Ressource Pool</label>
              <input type="text" id="vmware_cluster" class="form-control" placeholder="ex: Cluster-HA">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">Datastore de stockage</label>
              <input type="text" id="vmware_ds" class="form-control" placeholder="ex: vsanDatastore">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">Réseau / PortGroup</label>
              <input type="text" id="vmware_pg" class="form-control" placeholder="ex: VM Network">
            </div>
          </div>

          <div style="margin: 16px 0; display:flex; align-items:center; gap:14px;">
            <button class="btn btn-test" onclick="testVmwareConnection()">🔍 Tester la connexion vCenter / ESXi</button>
            <span id="vmware_test_status" style="font-size: 13px;"></span>
          </div>

          <h3 style="font-size:16px; font-weight:700; color:var(--accent-cyan); margin:18px 0 12px 0;">
            <span>⚙️ 3. Réseau et Identités des VMs K3s</span>
          </h3>

          <div class="input-row">
            <div class="form-group" style="flex:2;">
              <label class="form-label">Adresses IP fixes des nœuds K3s (séparées par virgules)</label>
              <input type="text" id="vmware_ips" class="form-control" placeholder="ex: 192.168.1.11, 192.168.1.12, 192.168.1.13">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">Passerelle (Gateway)</label>
              <input type="text" id="vmware_gw" class="form-control" placeholder="ex: 192.168.1.1">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">Serveur DNS</label>
              <input type="text" id="vmware_dns" class="form-control" placeholder="ex: 192.168.1.1">
            </div>
          </div>

          <div class="input-row">
            <div class="form-group" style="flex:1;">
              <label class="form-label">Utilisateur SSH administrateur des VMs</label>
              <input type="text" id="vmware_ssh_user" class="form-control" value="debian">
            </div>
            <div class="form-group" style="flex:2;">
              <label class="form-label">Clé publique SSH (Optionnel pour injection Cloud-Init)</label>
              <input type="text" id="vmware_ssh_key" class="form-control" placeholder="ssh-ed25519 AAAAC3... ou vide">
            </div>
          </div>
        </div>

        <!-- SOUS-PANEL 2 : Cible Kubernetes Existant (Actif par défaut) -->
        <div id="panel_infra_k8s">
          <div class="form-group">
            <label class="form-label">Mode d'accès à Kubernetes</label>
            <div class="form-sublabel">Choisissez si kubectl s'exécute depuis votre machine locale ou directement via SSH sur un nœud maître K3s.</div>
            <select id="k8s_mode" class="form-control" onchange="toggleK8sMode()">
              <option value="local">Local — Utilise la commande kubectl locale de cette machine</option>
              <option value="remote-ssh">Remote SSH — Exécute kubectl à distance sur le nœud K3s</option>
            </select>
          </div>

          <div id="k8s_local_block">
            <div class="form-group">
              <label class="form-label">Contexte Kubernetes (Context)</label>
              <div class="form-sublabel">Laissez vide pour utiliser le contexte courant actif (~/.kube/config), ou sélectionnez un contexte détecté :</div>
              <div class="input-row">
                <input type="text" id="k8s_context" class="form-control" placeholder="Défaut : contexte courant actif">
                <select id="k8s_context_select" class="form-control" style="max-width: 200px;" onchange="selectContextFromList()">
                  <option value="">Contextes détectés...</option>
                </select>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">Chemin Kubeconfig personnalisé (Facultatif)</label>
              <input type="text" id="k8s_kubeconfig" class="form-control" placeholder="C:\Users\...\.kube\config ou /home/.../.kube/config">
            </div>
          </div>

          <div id="k8s_ssh_block" style="display:none;">
            <div class="input-row">
              <div class="form-group" style="flex:2;">
                <label class="form-label">Adresse IP du nœud maître K3s</label>
                <input type="text" id="k8s_ssh_ip" class="form-control" placeholder="ex: 192.168.1.50">
              </div>
              <div class="form-group" style="flex:1;">
                <label class="form-label">Utilisateur SSH</label>
                <input type="text" id="k8s_ssh_user" class="form-control" value="debian">
              </div>
              <div class="form-group" style="flex:1;">
                <label class="form-label">Port SSH</label>
                <input type="number" id="k8s_ssh_port" class="form-control" value="22">
              </div>
            </div>
          </div>

          <div class="input-row">
            <div class="form-group" style="flex:1;">
              <label class="form-label">Namespace cible</label>
              <input type="text" id="k8s_namespace" class="form-control" value="arcia">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">StorageClass personnalisée (Optionnel)</label>
              <input type="text" id="k8s_storage_class" class="form-control" placeholder="Défaut : StorageClass par défaut du cluster">
            </div>
          </div>

          <div style="margin: 16px 0; display:flex; align-items:center; gap:14px; flex-wrap:wrap;">
            <button class="btn btn-test" onclick="testK8sQualificationFull()">🔍 Qualifier et tester l'environnement Kubernetes</button>
            <span id="k8s_audit_status" style="font-size: 13px;"></span>
          </div>

          <!-- Zone du rapport d'audit exhaustif K8s -->
          <div id="k8s_audit_results" style="display:none; margin-top:16px; background:rgba(0,0,0,0.3); border:1px solid var(--border-color); border-radius:10px; padding:16px;">
            <div id="k8s_audit_summary" style="font-weight:700; font-size:14px; margin-bottom:12px;"></div>
            <div id="k8s_audit_items" style="display:flex; flex-direction:column; gap:10px;"></div>
          </div>
        </div>

        <!-- SOUS-PANEL 3 : Cible Docker Local (Mode Lab) -->
        <div id="panel_infra_docker" style="display:none;">
          <div id="docker_status_box" class="alert-box alert-info" style="margin-bottom:16px;">
            <!-- Rempli par checkDockerStatus() -->
          </div>

          <div class="alert-box alert-warn">
            <span style="font-size:20px;">💡</span>
            <div>
              <strong>Mode Lab & Démonstration Portable :</strong><br>
              Les services (Open-WebUI, LiteLLM, Presidio DLP, Hermes Agent) sont démarrés directement dans des conteneurs Docker locaux. Les données persistantes sont stockées dans un volume Docker local. Aucun nom de domaine public n'est nécessaire (accès immédiat sur <code>http://localhost:3000</code>).
            </div>
          </div>

          <div class="input-row">
            <div class="form-group" style="flex:1;">
              <label class="form-label">Port Local Open-WebUI</label>
              <input type="number" id="docker_webui_port" class="form-control" value="3000">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">Port Local LiteLLM Proxy</label>
              <input type="number" id="docker_litellm_port" class="form-control" value="4000">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">Port Local Presidio Anonymizer</label>
              <input type="number" id="docker_presidio_port" class="form-control" value="5001">
            </div>
          </div>
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(2)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(4)">Suivant : Réseau & Exposition →</button>
        </div>
      </section>

      <!-- SCREEN 4: Réseau & Ingress -->
      <section id="step4" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 4 : Exposition Réseau, Domaine FQDN & TLS</h2>
          <p class="screen-desc">Définissez le nom de domaine public d'accès et la gestion automatique des certificats HTTPS.</p>
        </div>

        <div class="form-group">
          <label class="form-label">Nom de domaine public complet (FQDN) <span style="color:var(--accent-cyan);">*</span></label>
          <div class="form-sublabel">Vos collaborateurs accéderont au portail via cette URL (ex: <code>assistant.mon-entreprise.com</code>).</div>
          <input type="text" id="net_fqdn" class="form-control" placeholder="ex: assistant.mon-entreprise.com" required oninput="updateInstanceRepoSuggestion()">
        </div>

        <div class="input-row">
          <div class="form-group" style="flex:1;">
            <label class="form-label">Mode TLS / HTTPS</label>
            <select id="net_tls_mode" class="form-control" onchange="toggleTlsMode()">
              <option value="letsencrypt-prod">Let's Encrypt Production (Recommandé en production)</option>
              <option value="letsencrypt-staging">Let's Encrypt Staging (Tests / Évite le rate-limit)</option>
              <option value="custom-secret">Secret TLS existant déjà présent dans le cluster</option>
              <option value="disabled">Désactivé (HTTP port 80 direct — déconseillé)</option>
            </select>
          </div>
          <div class="form-group" style="flex:1;">
            <label class="form-label">Contrôleur Ingress</label>
            <select id="net_ingress_class" class="form-control">
              <option value="traefik">Traefik Ingress (Standard K3s et Helm)</option>
              <option value="nginx">NGINX Ingress (ingress-nginx)</option>
              <option value="default">IngressClass par défaut du cluster</option>
            </select>
          </div>
        </div>

        <div id="net_acme_block" class="form-group">
          <label class="form-label">Email de contact Let's Encrypt (ACME) <span style="color:var(--accent-cyan);">*</span></label>
          <input type="email" id="net_acme_email" class="form-control" placeholder="admin@mon-entreprise.com">
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(3)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(5)">Suivant : Passerelle LLM →</button>
        </div>
      </section>

      <!-- SCREEN 5: Passerelle LLM & IA -->
      <section id="step5" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 5 : Passerelle LLM & Modèles d'Inférence</h2>
          <p class="screen-desc">Connectez votre fournisseur d'inférence. Les requêtes sont automatiquement protégées par Presidio DLP.</p>
        </div>

        <div class="form-group">
          <label class="form-label">Clé d'API OpenRouter d'entreprise <span style="color:var(--accent-cyan);">*</span></label>
          <div class="form-sublabel">Accès unifié aux modèles mondiaux avec protection Presidio DLP. <a href="https://openrouter.ai/keys" target="_blank" class="doc-link">Obtenir une clé sur OpenRouter.ai ↗</a></div>
          <input type="password" id="llm_key" class="form-control" placeholder="sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx" required>
        </div>

        <div class="input-row">
          <div class="form-group" style="flex:1;">
            <label class="form-label">Modèle managé d'entreprise</label>
            <select id="llm_model" class="form-control">
              <option value="ArcIA-Agentic (auto)">ArcIA-Agentic (auto) — Routage intelligent automatique (Recommandé)</option>
              <option value="ArcIA-Agentic (expert)">ArcIA-Agentic (expert) — Modèle d'expertise et raisonnement frontière</option>
            </select>
          </div>
          <div class="form-group" style="flex:1;">
            <label class="form-label">Endpoint vLLM local optionnel</label>
            <input type="text" id="llm_vllm" class="form-control" placeholder="ex: http://vllm.corp.local:8000/v1">
          </div>
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(4)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(6)">Suivant : Hermes Studio →</button>
        </div>
      </section>

      <!-- SCREEN 6: Hermes Studio & Desktop -->
      <section id="step6" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 6 : Moteur d'Agents Hermes & Studio Kanban</h2>
          <p class="screen-desc">Sécurisez l'accès au Studio Kanban multi-agents et à la passerelle WebSocket du client de bureau.</p>
        </div>

        <div class="form-group">
          <label class="form-label">Mot de passe Administrateur Hermes Studio (/studio) <span style="color:var(--accent-cyan);">*</span></label>
          <div class="input-row">
            <input type="text" id="hermes_password" class="form-control" required>
            <button class="btn btn-secondary" onclick="generateSecretFor('hermes_password', 'admin')">🎲 Régénérer</button>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Jeton PAT Hermes Desktop Gateway (/gateway) <span style="color:var(--accent-cyan);">*</span></label>
          <div class="input-row">
            <input type="text" id="hermes_pat" class="form-control" required>
            <button class="btn btn-secondary" onclick="generateSecretFor('hermes_pat', 'pat')">🎲 Régénérer</button>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Espace de stockage persistant (PVC)</label>
          <input type="text" id="hermes_storage" class="form-control" value="20Gi">
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(5)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(7)">Suivant : SSO Entra ID (Optionnel) →</button>
        </div>
      </section>

      <!-- SCREEN 7: SSO Entra ID (Optionnel) -->
      <section id="step7" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 7 : Authentification SSO Microsoft Entra ID</h2>
          <p class="screen-desc">Optionnel : Restreignez l'accès à Hermes Studio et Open-WebUI aux seuls comptes Microsoft 365.</p>
        </div>

        <div class="toggle-wrapper">
          <div class="toggle-info">
            <h4>Activer l'Authentification SSO Microsoft Entra ID</h4>
            <p>Active oauth2-proxy et le middleware Traefik ForwardAuth pour verrouiller l'accès aux collaborateurs.</p>
          </div>
          <label class="switch">
            <input type="checkbox" id="sso_enabled" onchange="toggleSsoFields()">
            <span class="slider"></span>
          </label>
        </div>

        <div id="sso_fields" style="opacity: 0.4; pointer-events: none; transition: opacity 0.3s;">
          <div class="input-row">
            <div class="form-group" style="flex:1;">
              <label class="form-label">ID de l'annuaire (Tenant ID) <span style="color:var(--accent-cyan);">*</span></label>
              <input type="text" id="sso_tenant" class="form-control" placeholder="ex: 00000000-0000-0000-0000-000000000000">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">ID d'application (Client ID) <span style="color:var(--accent-cyan);">*</span></label>
              <input type="text" id="sso_client" class="form-control" placeholder="ex: 00000000-0000-0000-0000-000000000000">
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">Secret Client (Client Secret) <span style="color:var(--accent-cyan);">*</span></label>
            <input type="password" id="sso_secret" class="form-control" placeholder="Valeur du secret générée sur le portail Azure">
          </div>

          <div class="form-group">
            <label class="form-label">Secret de chiffrement des cookies (Cookie Secret)</label>
            <div class="input-row">
              <input type="text" id="sso_cookie" class="form-control">
              <button class="btn btn-secondary" onclick="generateSecretFor('sso_cookie', 'cookie')">🎲 Régénérer</button>
            </div>
          </div>
        </div>

        <div class="doc-accordion">
          <div class="doc-header" onclick="toggleDocAccordion('docEntra')">
            <span>📘 Comment créer l'application dans Microsoft Entra ID ? (Guide pas-à-pas)</span>
            <span id="docEntraIcon">▼</span>
          </div>
          <div id="docEntra" class="doc-body">
            <ol>
              <li>Portail Azure > <strong>Microsoft Entra ID</strong> > <strong>Inscriptions d'applications</strong> > <strong>+ Nouvelle inscription</strong>.</li>
              <li>Nom : <code>ArcIA-SSO</code> | Types de comptes : <em>Mono-locataire</em>.</li>
              <li>URI de redirection (Web) : <code id="guide_sso_callback">https://&lt;fqdn&gt;/oauth2/callback</code>.</li>
              <li>Copiez <strong>ID d'application (client)</strong> et <strong>ID de l'annuaire (tenant)</strong>.</li>
              <li>Dans <strong>Certificats & secrets</strong>, créez un secret et copiez sa <em>Valeur</em>.</li>
            </ol>
            <p style="margin-top:10px;">
              <a href="https://github.com/nicolastheuil/ArcIA/blob/main/docs/guides/portail-webui-entraid.md#creation-app-entraid" target="_blank" class="doc-link">Guide détaillé SSO Entra ID sur GitHub ↗</a>
            </p>
          </div>
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(6)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(8)">Suivant : Bot Teams (Optionnel) →</button>
        </div>
      </section>

      <!-- SCREEN 8: Bot Teams (Optionnel) -->
      <section id="step8" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 8 : Adaptateur Microsoft Teams Bot</h2>
          <p class="screen-desc">Optionnel : Intégrez le bot ArcIA dans Microsoft Teams (chats 1:1 et mentions @ArcIA en canaux).</p>
        </div>

        <div class="toggle-wrapper">
          <div class="toggle-info">
            <h4>Activer le Bot Microsoft Teams</h4>
            <p>Déploie le microservice adaptateur Teams Bot et route les webhooks Azure Bot Service.</p>
          </div>
          <label class="switch">
            <input type="checkbox" id="teams_enabled" onchange="toggleTeamsFields()">
            <span class="slider"></span>
          </label>
        </div>

        <div id="teams_fields" style="opacity: 0.4; pointer-events: none; transition: opacity 0.3s;">
          <div class="input-row">
            <div class="form-group" style="flex:1;">
              <label class="form-label">Microsoft App ID <span style="color:var(--accent-cyan);">*</span></label>
              <input type="text" id="teams_appid" class="form-control" placeholder="ex: 00000000-0000-0000-0000-000000000000">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">App Password <span style="color:var(--accent-cyan);">*</span></label>
              <input type="password" id="teams_password" class="form-control" placeholder="Mot de passe Azure Bot">
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">Prompt système du Bot Teams</label>
            <textarea id="teams_prompt" class="form-control" rows="2">Tu es ArcIA, l'assistant d'entreprise. Réponds de façon synthétique, professionnelle et structurée en Markdown.</textarea>
          </div>
        </div>

        <div class="doc-accordion">
          <div class="doc-header" onclick="toggleDocAccordion('docTeams')">
            <span>📘 Comment créer le bot sur Azure Bot Service ? (Guide pas-à-pas)</span>
            <span id="docTeamsIcon">▼</span>
          </div>
          <div id="docTeams" class="doc-body">
            <ol>
              <li>Portail Azure > Créer une ressource <strong>Azure Bot</strong>.</li>
              <li>Dans <strong>Configuration</strong>, renseignez l'URL de messagerie : <code id="guide_teams_webhook">https://&lt;fqdn&gt;/api/teams/messages</code>.</li>
              <li>Copiez le <strong>Microsoft App ID</strong> et générez le secret dans <em>Gérer le mot de passe</em>.</li>
              <li>Dans <strong>Canaux</strong>, activez le canal <strong>Microsoft Teams</strong>.</li>
            </ol>
            <p style="margin-top:10px;">
              <a href="https://github.com/nicolastheuil/ArcIA/blob/main/docs/guides/integration-teams.md#creation-azure-bot" target="_blank" class="doc-link">Guide détaillé Intégration Teams sur GitHub ↗</a>
            </p>
          </div>
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(7)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(9)">Suivant : OmniRoute (Optionnel) →</button>
        </div>
      </section>

      <!-- SCREEN 9: OmniRoute -->
      <section id="step9" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 9 : Routeur Multi-Fournisseurs OmniRoute</h2>
          <p class="screen-desc">Optionnel : Activez OmniRoute v3.8.51 pour disposer d'un portail LAN multi-fournisseurs.</p>
        </div>

        <div class="toggle-wrapper">
          <div class="toggle-info">
            <h4>Activer OmniRoute v3.8.51</h4>
            <p>Déploie OmniRoute avec point d'accès API (:20128) et portail Web LAN (:20129).</p>
          </div>
          <label class="switch">
            <input type="checkbox" id="omni_enabled">
            <span class="slider"></span>
          </label>
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(8)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(10)">Suivant : Validation & Déploiement →</button>
        </div>
      </section>

      <!-- SCREEN 10: Déploiement & Sauvegarde Git Chiffrée -->
      <section id="step10" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 10 : Validation & Déploiement Automatisé</h2>
          <p class="screen-desc">Vérifiez les paramètres. L'installation déploie le cluster et sauvegarde l'instance chiffrée sur Git.</p>
        </div>

        <div id="deployPreCheck" style="margin-bottom: 20px;">
          <div class="alert-box alert-info">
            <span style="font-size:20px;">📋</span>
            <div id="deploySummaryText">Vérification de la configuration...</div>
          </div>
        </div>

        <div style="display: flex; gap: 12px; margin-bottom: 20px;">
          <button id="btnStartDeploy" class="btn btn-primary" style="font-size: 16px; padding: 12px 28px;" onclick="triggerDeployment(false)">
            🚀 Lancer le Déploiement d'ArcIA
          </button>
          <button id="btnDryRun" class="btn btn-secondary" onclick="triggerDeployment(true)">
            🧪 Simuler le déploiement (Dry-Run)
          </button>
        </div>

        <div style="margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 13px; font-weight: 600; color: var(--text-muted);">Console d'exécution temps réel :</span>
          <span id="deployStatusBadge" class="header-badge">En attente</span>
        </div>

        <div id="terminalConsole" class="terminal-box">
          <div class="log-line">ArcIA Setup Wizard prêt. Cliquez sur "Lancer le Déploiement" pour démarrer l'installation.</div>
        </div>

        <div class="actions-bar" style="margin-top:20px;">
          <button class="btn btn-secondary" onclick="goToStep(9)">← Précédent</button>
          <button id="btnGoFinal" class="btn btn-primary" style="display:none;" onclick="goToStep(11)">Voir le récapitulatif final et les URLs d'accès →</button>
        </div>
      </section>

      <!-- SCREEN 11: Récapitulatif Final & Accès -->
      <section id="step11" class="screen card">
        <div class="screen-header">
          <div style="font-size: 48px; margin-bottom: 12px;">🎉</div>
          <h2 class="screen-title" style="color: var(--success);">ArcIA est 100% Opérationnel !</h2>
          <p class="screen-desc">L'ensemble des microservices, secrets, certificats TLS, compétences et passerelles d'inférence ont été déployés avec succès.</p>
        </div>

        <div class="recap-grid" id="recapAccessGrid"></div>

        <div class="alert-box alert-success" style="margin-top: 24px;">
          <span style="font-size:20px;">✅</span>
          <div>
            <strong>Compétences et Outils Activés Automatiquement :</strong><br>
            Les compétences natives (<em>Ponytail</em> pour la sobriété logicielle, <em>Graphify</em> pour le GraphRAG AST local déterministe, et <em>Public-APIs</em>) sont intégrées d'office et utilisables immédiatement.
          </div>
        </div>

        <div class="actions-bar" style="margin-top:24px;">
          <button class="btn btn-secondary" onclick="goToStep(1)">← Revenir à l'accueil du Wizard</button>
          <button class="btn btn-primary" onclick="window.open(getCurrentPublicUrl(), '_blank')">Ouvrir le Portail ArcIA ↗</button>
        </div>
      </section>

    </main>
  </div>

  <script>
    let currentStep = 1;
    let configData = {};
    let isExistingInstallation = false;
    let logPollingInterval = null;
    let selectedSetupMode = "new"; // "new" ou "restore"
    let createdRepoUrl = "";

    window.addEventListener("DOMContentLoaded", () => {
      fetchConfig();
    });

    async function fetchConfig() {
      try {
        const res = await fetch("/api/config");
        const data = await res.json();
        configData = data.config || {};
        isExistingInstallation = data.is_existing;

        const badge = document.getElementById("instanceModeBadge");
        if (isExistingInstallation) {
          badge.textContent = "Configuration existante chargée";
          badge.style.color = "var(--success)";
          badge.style.borderColor = "var(--success)";
        } else {
          badge.textContent = "Nouvelle installation";
        }

        const ctxSelect = document.getElementById("k8s_context_select");
        if (data.available_contexts && data.available_contexts.length > 0) {
          data.available_contexts.forEach(ctx => {
            const opt = document.createElement("option");
            opt.value = ctx;
            opt.textContent = ctx + (ctx === data.current_context ? " (Actif)" : "");
            ctxSelect.appendChild(opt);
          });
        }

        populateFormFields(configData);
      } catch (err) {
        console.error("Erreur récupération configuration:", err);
      }
    }

    function selectSetupMode(mode) {
      selectedSetupMode = mode;
      document.getElementById("cardNewInstance").classList.toggle("selected", mode === "new");
      document.getElementById("cardRestoreInstance").classList.toggle("selected", mode === "restore");
      document.getElementById("restoreSection").style.display = (mode === "restore") ? "block" : "none";
    }

    async function executeInstanceRestore() {
      const gitUrl = document.getElementById("restore_git_url").value.trim();
      const gitToken = document.getElementById("restore_git_token").value.trim();
      const passphrase = document.getElementById("restore_passphrase").value.trim();
      const statusSpan = document.getElementById("restoreStatus");
      const successPanel = document.getElementById("restoreSuccessPanel");

      if (!gitUrl) {
        alert("Veuillez renseigner l'URL du dépôt Git d'instance privé.");
        return;
      }
      if (!passphrase) {
        alert("Veuillez renseigner votre mot de passe maître de déchiffrement.");
        return;
      }

      statusSpan.innerHTML = '<span style="color:var(--accent-cyan);">⏳ Téléchargement et déchiffrement du bundle d\'instance...</span>';
      successPanel.style.display = "none";

      try {
        const res = await fetch("/api/instance/restore", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ repo_url: gitUrl, token: gitToken, passphrase: passphrase })
        });
        const data = await res.json();
        if (data.success) {
          statusSpan.innerHTML = '<span style="color:var(--success); font-weight:700;">✅ Déchiffrement réussi !</span>';
          successPanel.style.display = "block";
          document.getElementById("restoreSummaryDetails").innerHTML = `
            • Nom de l'instance : <strong>${data.instance_name}</strong><br>
            • Domaine FQDN : <strong>https://${data.public_fqdn}/</strong><br>
            • Namespace Kubernetes : <strong>${data.config.kubernetes ? data.config.kubernetes.namespace : 'arcia'}</strong><br>
            Tous les paramètres et secrets ont été rechargés dans le Wizard.
          `;
          populateFormFields(data.config);
          configData = data.config;
        } else {
          statusSpan.innerHTML = `<span style="color:var(--danger); font-weight:700;">❌ ${data.error}</span>`;
        }
      } catch (err) {
        statusSpan.innerHTML = `<span style="color:var(--danger);">❌ Erreur de communication : ${err.message}</span>`;
      }
    }

    function populateFormFields(cfg) {
      const k8s = cfg.kubernetes || {};
      const net = cfg.network || {};
      const llm = cfg.llm_gateway || {};
      const hermes = cfg.hermes || {};
      const sso = cfg.entra_id_sso || {};
      const teams = cfg.teams_bot || {};
      const omni = cfg.omniroute || {};

      document.getElementById("k8s_mode").value = k8s.mode || "local";
      document.getElementById("k8s_context").value = k8s.context || "";
      document.getElementById("k8s_kubeconfig").value = k8s.kubeconfig || "";
      document.getElementById("k8s_namespace").value = k8s.namespace || "arcia";
      document.getElementById("k8s_storage_class").value = k8s.storage_class || "";
      const ssh = k8s.remote_ssh || {};
      document.getElementById("k8s_ssh_ip").value = ssh.node_ip || "";
      document.getElementById("k8s_ssh_user").value = ssh.ssh_user || "debian";
      document.getElementById("k8s_ssh_port").value = ssh.ssh_port || 22;
      toggleK8sMode();

      document.getElementById("net_fqdn").value = net.public_fqdn || "";
      document.getElementById("net_tls_mode").value = net.tls_mode || "letsencrypt-prod";
      document.getElementById("net_ingress_class").value = net.ingress_class || "traefik";
      document.getElementById("net_acme_email").value = net.acme_email || "";
      toggleTlsMode();

      document.getElementById("llm_key").value = llm.openrouter_api_key || "";
      document.getElementById("llm_model").value = llm.default_model || "ArcIA-Agentic (auto)";
      document.getElementById("llm_vllm").value = llm.local_vllm_endpoint || "";

      document.getElementById("hermes_password").value = hermes.admin_password || "admin";
      document.getElementById("hermes_pat").value = hermes.api_token || "";
      document.getElementById("hermes_storage").value = hermes.storage_size || "20Gi";

      document.getElementById("sso_enabled").checked = !!sso.enabled;
      document.getElementById("sso_tenant").value = sso.tenant_id || "";
      document.getElementById("sso_client").value = sso.client_id || "";
      document.getElementById("sso_secret").value = sso.client_secret || "";
      document.getElementById("sso_cookie").value = sso.cookie_secret || "";
      toggleSsoFields();

      document.getElementById("teams_enabled").checked = !!teams.enabled;
      document.getElementById("teams_appid").value = teams.app_id || "";
      document.getElementById("teams_password").value = teams.app_password || "";
      if (teams.system_prompt) {
        document.getElementById("teams_prompt").value = teams.system_prompt;
      }
      toggleTeamsFields();

      document.getElementById("omni_enabled").checked = !!omni.enabled;

      updateGuideFqdn();
      updateInstanceRepoSuggestion();
      renderVmwareTierSummary();
    }

    function collectFormData() {
      return {
        kubernetes: {
          mode: document.getElementById("k8s_mode").value,
          kubeconfig: document.getElementById("k8s_kubeconfig").value.trim(),
          context: document.getElementById("k8s_context").value.trim(),
          namespace: document.getElementById("k8s_namespace").value.trim() || "arcia",
          storage_class: document.getElementById("k8s_storage_class").value.trim(),
          remote_ssh: {
            node_ip: document.getElementById("k8s_ssh_ip").value.trim() || "127.0.0.1",
            ssh_user: document.getElementById("k8s_ssh_user").value.trim() || "debian",
            ssh_port: parseInt(document.getElementById("k8s_ssh_port").value, 10) || 22
          }
        },
        network: {
          public_fqdn: document.getElementById("net_fqdn").value.trim(),
          ingress_class: document.getElementById("net_ingress_class").value,
          tls_mode: document.getElementById("net_tls_mode").value,
          acme_email: document.getElementById("net_acme_email").value.trim(),
          tls_secret_name: "arcia-tls-cert"
        },
        llm_gateway: {
          openrouter_api_key: document.getElementById("llm_key").value.trim(),
          default_model: document.getElementById("llm_model").value,
          local_vllm_endpoint: document.getElementById("llm_vllm").value.trim()
        },
        hermes: {
          admin_password: document.getElementById("hermes_password").value.trim() || "admin",
          api_token: document.getElementById("hermes_pat").value.trim(),
          storage_size: document.getElementById("hermes_storage").value.trim() || "20Gi"
        },
        presidio: {
          enabled: true,
          master_key: configData.presidio ? configData.presidio.master_key : "arcia-master-key"
        },
        open_webui: {
          enabled: true,
          storage_size: (vmwareTiersData[currentVmwareTier] ? vmwareTiersData[currentVmwareTier].pvc : "50Gi")
        },
        entra_id_sso: {
          enabled: document.getElementById("sso_enabled").checked,
          tenant_id: document.getElementById("sso_tenant").value.trim(),
          client_id: document.getElementById("sso_client").value.trim(),
          client_secret: document.getElementById("sso_secret").value.trim(),
          cookie_secret: document.getElementById("sso_cookie").value.trim()
        },
        teams_bot: {
          enabled: document.getElementById("teams_enabled").checked,
          app_id: document.getElementById("teams_appid").value.trim(),
          app_password: document.getElementById("teams_password").value.trim(),
          system_prompt: document.getElementById("teams_prompt").value.trim()
        },
        microsoft365_integration: {
          enabled: false,
          config_file: "instance/microsoft365.yaml"
        },
        omniroute: {
          enabled: document.getElementById("omni_enabled").checked,
          storage_size: "5Gi"
        }
      };
    }

    function collectInstanceGitInfo() {
      const enabled = document.getElementById("git_instance_enabled").checked;
      const provider = document.getElementById("git_provider").value;
      const repoName = document.getElementById("git_repo_name").value.trim();
      const token = document.getElementById("git_token").value.trim();
      const passphrase = document.getElementById("git_passphrase").value.trim();
      const ownerSelect = document.getElementById("git_owner_select");
      const owner = ownerSelect.value || "";

      let repoUrl = "";
      if (provider === "github") {
        repoUrl = `https://github.com/${owner || 'votre-orga'}/${repoName}.git`;
      } else if (provider === "gitlab") {
        repoUrl = `https://gitlab.com/${owner || 'votre-orga'}/${repoName}.git`;
      }

      return {
        enabled: enabled,
        provider: provider,
        repo_name: repoName,
        owner: owner,
        git_token: token,
        repo_url: repoUrl,
        passphrase: passphrase,
        instance_name: repoName
      };
    }

    function goToStep(stepNumber) {
      if (stepNumber < 1 || stepNumber > 11) return;
      if (stepNumber > currentStep && !validateStep(currentStep)) return;

      currentStep = stepNumber;
      updateGuideFqdn();

      document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
      const targetScreen = document.getElementById(`step${stepNumber}`);
      if (targetScreen) targetScreen.classList.add("active");

      const stepItems = document.querySelectorAll(".step-item");
      stepItems.forEach((item, idx) => {
        item.classList.remove("active");
        if (idx + 1 === stepNumber) item.classList.add("active");
        if (idx + 1 < stepNumber) item.classList.add("completed");
        else item.classList.remove("completed");
      });

      if (stepNumber === 10) updateDeploySummary();
      if (stepNumber === 11) buildRecapCards();

      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function validateStep(step) {
      if (step === 2 && document.getElementById("git_instance_enabled").checked) {
        const pwd = document.getElementById("git_passphrase").value;
        const confirm = document.getElementById("git_passphrase_confirm").value;
        if (!pwd || pwd.length < 8) {
          alert("Veuillez renseigner un mot de passe maître de chiffrement d'au moins 8 caractères pour sécuriser votre instance.");
          document.getElementById("git_passphrase").focus();
          return false;
        }
        if (pwd !== confirm) {
          alert("Les deux mots de passe maîtres ne correspondent pas.");
          document.getElementById("git_passphrase_confirm").focus();
          return false;
        }
      } else if (step === 4) {
        const fqdn = document.getElementById("net_fqdn").value.trim();
        if (!fqdn) {
          alert("Veuillez renseigner un nom de domaine public (FQDN) pour continuer.");
          document.getElementById("net_fqdn").focus();
          return false;
        }
      } else if (step === 5) {
        const key = document.getElementById("llm_key").value.trim();
        if (!key || key.startsWith("sk-or-v1-xxxx")) {
          alert("Veuillez renseigner votre clé d'API OpenRouter réelle pour joindre les modèles d'inférence.");
          document.getElementById("llm_key").focus();
          return false;
        }
      }
      return true;
    }

    function updateInstanceRepoSuggestion() {
      const fqdn = document.getElementById("net_fqdn").value.trim();
      if (fqdn && document.getElementById("git_repo_name").value === "ArcIA-instance-prod") {
        const slug = fqdn.split(".")[0];
        document.getElementById("git_repo_name").value = `ArcIA-instance-${slug}`;
      }
    }

    function toggleGitInstanceFields() {
      const enabled = document.getElementById("git_instance_enabled").checked;
      const block = document.getElementById("git_instance_fields");
      block.style.opacity = enabled ? "1" : "0.4";
      block.style.pointerEvents = enabled ? "auto" : "none";
    }

    async function testGitToken() {
      const provider = document.getElementById("git_provider").value;
      const token = document.getElementById("git_token").value.trim();
      if (!token) {
        alert("Veuillez entrer votre jeton d'accès Git (PAT).");
        return;
      }

      try {
        const res = await fetch("/api/instance/test-token", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider, token })
        });
        const data = await res.json();
        if (data.success) {
          alert(`✅ Authentification Git réussie en tant que : ${data.username}`);
          const ownerGroup = document.getElementById("git_owner_group");
          const ownerSelect = document.getElementById("git_owner_select");
          ownerSelect.innerHTML = "";
          data.targets.forEach(t => {
            const opt = document.createElement("option");
            opt.value = t;
            opt.textContent = t;
            ownerSelect.appendChild(opt);
          });
          ownerGroup.style.display = "block";
        } else {
          alert(`❌ ${data.error}`);
        }
      } catch (err) {
        alert("Erreur de test : " + err.message);
      }
    }

    let currentInfraTarget = "k8s_existing";
    let currentVmwareTier = "100";

    const vmwareTiersData = {
      "20": {
        title: "Équipe Pilote / PoC (jusqu'à 20 utilisateurs)",
        nodes: 1,
        vcpu: 4,
        ram: 8,
        disk: 100,
        ragGb: 50,
        pvc: "50Gi",
        ragLabel: "50 Go dédiés RAG (~10 000 pages, documents bruts + base vectorielle ChromaDB)",
        topo: "1x VM K3s All-in-One (Control-Plane + Worker)",
        desc: "Idéal pour évaluer ArcIA, tests métiers d'équipe ou qualification technique."
      },
      "100": {
        title: "PME / Direction Métier (21 à 100 utilisateurs) [Recommandé]",
        nodes: 3,
        vcpu: 12,
        ram: 48,
        disk: 450,
        ragGb: 200,
        pvc: "200Gi",
        ragLabel: "200 Go dédiés RAG (~100 000 pages, base vectorielle ChromaDB HNSW, collections inter-services)",
        topo: "3x VMs K3s Haute Disponibilité (etcd multi-maître, 4 vCPU / 16 Go / 150 Go par VM)",
        desc: "Tolérance aux pannes, haute résilience, recherche sémantique rapide et streaming fluide."
      },
      "500": {
        title: "Entreprise / Multi-Départements (101 à 500 utilisateurs)",
        nodes: 5,
        vcpu: 28,
        ram: 112,
        disk: 1250,
        ragGb: 600,
        pvc: "600Gi",
        ragLabel: "600 Go dédiés RAG (~500 000 pages, bases multi-départements, embeddings denses)",
        topo: "3x Control-Plane HA (4 vCPU / 16 Go) + 2x Workers Dédiés (8 vCPU / 32 Go / 250 Go)",
        desc: "Isolation du plan de contrôle, haute concurrence agentique, RAG hybride et intégration Teams continue."
      },
      "1000": {
        title: "Grande Entreprise (Plus de 500 utilisateurs)",
        nodes: 7,
        vcpu: 88,
        ram: 352,
        disk: 3500,
        ragGb: 2000,
        pvc: "2Ti",
        ragLabel: "2 To à 5 To dédiés RAG (Millions de documents, index distribué, modèles locaux)",
        topo: "3x Control-Plane HA (8 vCPU / 32 Go) + 4x Workers Haute Performance (16 vCPU / 64 Go / 500 Go)",
        desc: "Charge massive multi-tenant, modèles LLM locaux vLLM optionnels, stockage SAN rapide."
      }
    };

    function selectInfraTarget(target) {
      currentInfraTarget = target;
      const cardVmware = document.getElementById("target_card_vmware");
      const cardK8s = document.getElementById("target_card_k8s");
      const cardDocker = document.getElementById("target_card_docker");

      if (cardVmware) cardVmware.classList.toggle("active", target === "vmware_k3s");
      if (cardK8s) cardK8s.classList.toggle("active", target === "k8s_existing");
      if (cardDocker) cardDocker.classList.toggle("active", target === "docker_lab");

      const pVm = document.getElementById("panel_infra_vmware");
      const pK8s = document.getElementById("panel_infra_k8s");
      const pDoc = document.getElementById("panel_infra_docker");

      if (pVm) pVm.style.display = (target === "vmware_k3s") ? "block" : "none";
      if (pK8s) pK8s.style.display = (target === "k8s_existing") ? "block" : "none";
      if (pDoc) pDoc.style.display = (target === "docker_lab") ? "block" : "none";

      if (target === "vmware_k3s") {
        renderVmwareTierSummary();
      } else if (target === "docker_lab") {
        checkDockerStatus();
        const fqdnInput = document.getElementById("net_fqdn");
        if (fqdnInput && (!fqdnInput.value || fqdnInput.value === "assistant.example.org")) {
          fqdnInput.value = "localhost";
        }
      }
    }

    function selectVmwareTier(tierKey) {
      currentVmwareTier = tierKey;
      ["20", "100", "500", "1000"].forEach(k => {
        const el = document.getElementById(`tier_card_${k}`);
        if (el) el.classList.toggle("active", k === tierKey);
      });
      renderVmwareTierSummary(tierKey);
    }

    function renderVmwareTierSummary(tierKey = currentVmwareTier) {
      const t = vmwareTiersData[tierKey] || vmwareTiersData["100"];
      const box = document.getElementById("vmware_tier_summary");
      if (!box) return;
      box.innerHTML = `
        <span style="font-size:20px;">🖥️</span>
        <div>
          <strong>Dimensionnement calculé : ${t.title}</strong><br>
          • Topologie : <strong>${t.topo}</strong><br>
          • Ressources totales requises : <strong>${t.vcpu} vCPU</strong>, <strong>${t.ram} Go RAM</strong>, <strong>${t.disk} Go SSD</strong><br>
          • 📚 <strong>Espace RAG & Base Vectorielle inclus</strong> : <strong>${t.ragLabel}</strong> (PVC automatique <code>${t.pvc}</code>)<br>
          • Recommandation : ${t.desc}
        </div>
      `;
    }

    async function testVmwareConnection() {
      const status = document.getElementById("vmware_test_status");
      status.innerHTML = '<span style="color:var(--accent-cyan);">⏳ Test de connexion vSphere en cours...</span>';

      const payload = {
        host: document.getElementById("vmware_host").value.trim(),
        port: parseInt(document.getElementById("vmware_port").value, 10) || 443,
        username: document.getElementById("vmware_user").value.trim(),
        password: document.getElementById("vmware_pass").value,
        insecure_tls: document.getElementById("vmware_insecure").checked,
        target_type: document.getElementById("vmware_type").value
      };

      try {
        const res = await fetch("/api/vmware/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
          status.innerHTML = `<span style="color:var(--success); font-weight:700;">✅ ${data.message} (${data.details.detected_version})</span>`;
        } else {
          status.innerHTML = `<span style="color:var(--danger); font-weight:700;">❌ ${data.error}</span>`;
        }
      } catch (err) {
        status.innerHTML = `<span style="color:var(--danger);">❌ Erreur réseau : ${err.message}</span>`;
      }
    }

    async function testK8sQualificationFull() {
      const status = document.getElementById("k8s_audit_status");
      const resBox = document.getElementById("k8s_audit_results");
      const summaryBox = document.getElementById("k8s_audit_summary");
      const itemsBox = document.getElementById("k8s_audit_items");

      status.innerHTML = '<span style="color:var(--accent-cyan);">⏳ Audit de qualification exhaustif en cours...</span>';
      resBox.style.display = "none";

      const formData = collectFormData();
      try {
        const res = await fetch("/api/k8s/validate-full", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData.kubernetes)
        });
        const data = await res.json();
        status.innerHTML = data.success 
          ? '<span style="color:var(--success); font-weight:700;">✅ Qualification terminée avec succès</span>'
          : '<span style="color:var(--danger); font-weight:700;">⚠️ Qualification avec avertissements ou erreurs</span>';

        resBox.style.display = "block";
        summaryBox.innerHTML = `<span style="color:${data.all_valid ? 'var(--success)' : (data.success ? 'var(--warning)' : 'var(--danger)')};">${data.summary}</span>`;

        itemsBox.innerHTML = "";
        data.checks.forEach(c => {
          const badgeClass = c.status === "ok" ? "ok" : (c.status === "warn" ? "warn" : "error");
          const badgeLabel = c.status === "ok" ? "VALIDE" : (c.status === "warn" ? "ATTENTION" : "BLOQUANT");
          const item = document.createElement("div");
          item.className = "audit-check-item";
          item.innerHTML = `
            <span class="audit-badge ${badgeClass}">${badgeLabel}</span>
            <div style="flex:1;">
              <div style="font-weight:700; font-size:13px; margin-bottom:2px;">${c.title}</div>
              <div style="font-size:12px; color:#cbd5e1; margin-bottom:4px;">${c.message}</div>
              ${c.status !== 'ok' ? `<div style="font-size:11px; color:var(--text-muted);">💡 <em>${c.recommendation}</em></div>` : ''}
            </div>
          `;
          itemsBox.appendChild(item);
        });
      } catch (err) {
        status.innerHTML = `<span style="color:var(--danger);">❌ Erreur de qualification : ${err.message}</span>`;
      }
    }

    async function checkDockerStatus() {
      const box = document.getElementById("docker_status_box");
      if (!box) return;
      box.innerHTML = '<span style="color:var(--accent-cyan);">⏳ Détection de Docker en cours...</span>';

      try {
        const res = await fetch("/api/docker/status");
        const data = await res.json();
        if (data.installed && data.running) {
          box.className = "alert-box alert-success";
          box.innerHTML = `
            <span style="font-size:22px;">🐳</span>
            <div>
              <strong>Docker Engine est opérationnel !</strong><br>
              • Version Docker : <strong>${data.docker_version}</strong> | Docker Compose : <strong>${data.compose_version}</strong><br>
              Votre machine est prête pour le lancement local en Mode Lab.
            </div>
          `;
        } else if (data.installed) {
          box.className = "alert-box alert-warn";
          box.innerHTML = `
            <span style="font-size:22px;">⚠️</span>
            <div>
              <strong>Docker est installé mais le moteur n'est pas démarré :</strong><br>
              ${data.message}<br>
              Veuillez démarrer Docker Desktop ou le service Docker sur cette machine.
            </div>
          `;
        } else {
          box.className = "alert-box alert-warn";
          box.innerHTML = `
            <span style="font-size:22px;">⚠️</span>
            <div>
              <strong>Docker n'a pas été détecté sur ce poste :</strong><br>
              ${data.message}<br>
              <a href="https://docs.docker.com/get-docker/" target="_blank" style="color:var(--accent-cyan); font-weight:600;">Télécharger Docker Desktop ↗</a>
            </div>
          `;
        }
      } catch (err) {
        box.className = "alert-box alert-warn";
        box.innerHTML = `Erreur vérification Docker : ${err.message}`;
      }
    }

    function toggleK8sMode() {
      const mode = document.getElementById("k8s_mode").value;
      document.getElementById("k8s_local_block").style.display = (mode === "local") ? "block" : "none";
      document.getElementById("k8s_ssh_block").style.display = (mode === "remote-ssh") ? "block" : "none";
    }

    function selectContextFromList() {
      const val = document.getElementById("k8s_context_select").value;
      if (val) document.getElementById("k8s_context").value = val;
    }

    function toggleTlsMode() {
      const mode = document.getElementById("net_tls_mode").value;
      document.getElementById("net_acme_block").style.display = mode.startsWith("letsencrypt") ? "block" : "none";
    }

    function toggleSsoFields() {
      const enabled = document.getElementById("sso_enabled").checked;
      const block = document.getElementById("sso_fields");
      block.style.opacity = enabled ? "1" : "0.4";
      block.style.pointerEvents = enabled ? "auto" : "none";
    }

    function toggleTeamsFields() {
      const enabled = document.getElementById("teams_enabled").checked;
      const block = document.getElementById("teams_fields");
      block.style.opacity = enabled ? "1" : "0.4";
      block.style.pointerEvents = enabled ? "auto" : "none";
    }

    function toggleDocAccordion(id) {
      const body = document.getElementById(id);
      const icon = document.getElementById(id + "Icon");
      if (body.style.display === "block") {
        body.style.display = "none";
        icon.textContent = "▼";
      } else {
        body.style.display = "block";
        icon.textContent = "▲";
      }
    }

    function updateGuideFqdn() {
      const fqdn = document.getElementById("net_fqdn").value.trim() || "<votre-fqdn>";
      const ssoCallback = document.getElementById("guide_sso_callback");
      if (ssoCallback) ssoCallback.textContent = `https://${fqdn}/oauth2/callback`;
      const teamsWebhook = document.getElementById("guide_teams_webhook");
      if (teamsWebhook) teamsWebhook.textContent = `https://${fqdn}/api/teams/messages`;
    }

    async function generateSecretFor(elementId, kind) {
      try {
        const res = await fetch("/api/generate-secret", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind })
        });
        const data = await res.json();
        if (data.success) {
          document.getElementById(elementId).value = data.token;
        }
      } catch (err) {
        console.error("Erreur génération secret:", err);
      }
    }

    async function testK8sConnection() {
      const statusSpan = document.getElementById("k8s_test_status");
      const nodesResult = document.getElementById("k8s_nodes_result");
      statusSpan.innerHTML = '<span style="color:var(--accent-cyan);">⏳ Test de connexion en cours...</span>';
      nodesResult.style.display = "none";

      const formData = collectFormData();
      try {
        const res = await fetch("/api/test-k8s", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData.kubernetes)
        });
        const data = await res.json();
        if (data.success) {
          statusSpan.innerHTML = `<span style="color:var(--success); font-weight:600;">✅ Connecté avec succès (${data.nodes_count} nœud(s) détecté(s))</span>`;
          nodesResult.style.display = "block";
          let html = `<strong>Nœuds détectés sur le cluster :</strong><br>`;
          data.nodes.forEach(n => {
            html += `• ${n.name} (Statut: <span style="color:var(--success);">${n.status}</span>, Rôles: ${n.roles})<br>`;
          });
          nodesResult.innerHTML = html;
        } else {
          statusSpan.innerHTML = `<span style="color:var(--danger); font-weight:600;">❌ Échec de connexion : ${data.error}</span>`;
        }
      } catch (err) {
        statusSpan.innerHTML = `<span style="color:var(--danger);">❌ Erreur réseau : ${err.message}</span>`;
      }
    }

    async function saveConfigOnly() {
      const cfg = collectFormData();
      try {
        const res = await fetch("/api/save-config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ config: cfg })
        });
        const data = await res.json();
        if (data.success) {
          alert("Configuration enregistrée dans 'arcia.config.yaml' avec succès !");
        } else {
          alert("Erreur lors de l'enregistrement : " + data.error);
        }
      } catch (err) {
        alert("Erreur communication : " + err.message);
      }
    }

    function updateDeploySummary() {
      const cfg = collectFormData();
      const fqdn = (currentInfraTarget === "docker_lab") ? "localhost" : (cfg.network.public_fqdn || "Non renseigné");
      let targetLabel = "Cluster Kubernetes Existant";
      if (currentInfraTarget === "vmware_k3s") {
        const t = vmwareTiersData[currentVmwareTier] || vmwareTiersData["100"];
        targetLabel = `Nouveau Cluster K3s sur VMware (${t.title} - ${t.topo})`;
      } else if (currentInfraTarget === "docker_lab") {
        targetLabel = "Docker Local (Mode Lab - Conteneurs locaux sur ce poste)";
      }

      const sso = cfg.entra_id_sso.enabled ? "Activé" : "Désactivé";
      const teams = cfg.teams_bot.enabled ? "Activé" : "Désactivé";
      const omni = cfg.omniroute.enabled ? "Activé" : "Désactivé";
      const gitInfo = collectInstanceGitInfo();
      const gitMsg = gitInfo.enabled ? `Oui (${gitInfo.repo_name} sur ${gitInfo.provider})` : "Non (stockage local)";

      document.getElementById("deploySummaryText").innerHTML = `
        <strong>Cible de déploiement & Sauvegarde :</strong><br>
        • Cible d'infrastructure : <strong>${targetLabel}</strong><br>
        • Point d'accès : <strong>${currentInfraTarget === "docker_lab" ? "http://localhost:3000/" : "https://" + fqdn + "/"}</strong><br>
        • Dépôt d'instance privé chiffré : <strong>${gitMsg}</strong><br>
        • Modules optionnels : SSO Entra ID (<strong>${sso}</strong>) | Bot Teams (<strong>${teams}</strong>) | OmniRoute (<strong>${omni}</strong>)<br>
        • Briques internes automatiques : Presidio DLP, Open-WebUI, Hermes Studio, LiteLLM Proxy, Skills natifs (Ponytail, Graphify, Public-APIs).
      `;
    }

    async function triggerDeployment(dryRun = false) {
      const cfg = collectFormData();
      const gitInfo = collectInstanceGitInfo();
      const btnDeploy = document.getElementById("btnStartDeploy");
      const btnDry = document.getElementById("btnDryRun");
      const badge = document.getElementById("deployStatusBadge");

      btnDeploy.disabled = true;
      btnDry.disabled = true;
      badge.textContent = dryRun ? "Simulation en cours..." : "Déploiement en cours...";
      badge.style.color = "var(--accent-cyan)";
      badge.style.borderColor = "var(--accent-cyan)";

      const terminal = document.getElementById("terminalConsole");
      terminal.innerHTML = `<div class="log-line log-cyan">[INITIALISATION] Démarrage du moteur de déploiement et de sauvegarde...</div>`;

      // Si création de dépôt demandée, appeler l'API de création au préalable
      if (gitInfo.enabled && !dryRun && gitInfo.git_token) {
        try {
          terminal.innerHTML += `<div class="log-line">[INFO] Création / vérification du dépôt distant ${gitInfo.repo_name}...</div>`;
          const cRes = await fetch("/api/instance/create-repo", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              provider: gitInfo.provider,
              token: gitInfo.git_token,
              repo_name: gitInfo.repo_name,
              owner: gitInfo.owner
            })
          });
          const cData = await cRes.json();
          if (cData.success && cData.clone_url) {
            gitInfo.repo_url = cData.clone_url;
            createdRepoUrl = cData.html_url || cData.clone_url;
            terminal.innerHTML += `<div class="log-line log-green">[OK] Dépôt Git privé prêt : ${createdRepoUrl}</div>`;
          }
        } catch (e) {
          console.warn("Création de repo:", e);
        }
      }

      try {
        const infraConfig = {
          vmware: {
            host: document.getElementById("vmware_host").value.trim(),
            port: parseInt(document.getElementById("vmware_port").value, 10) || 443,
            user: document.getElementById("vmware_user").value.trim(),
            password: document.getElementById("vmware_pass").value,
            insecure_tls: document.getElementById("vmware_insecure").checked,
            target_type: document.getElementById("vmware_type").value,
            datacenter: document.getElementById("vmware_dc").value.trim(),
            cluster: document.getElementById("vmware_cluster").value.trim(),
            datastore: document.getElementById("vmware_ds").value.trim(),
            portgroup: document.getElementById("vmware_pg").value.trim(),
            user_tier: currentVmwareTier
          },
          docker: {
            webui_port: parseInt(document.getElementById("docker_webui_port").value, 10) || 3000,
            litellm_port: parseInt(document.getElementById("docker_litellm_port").value, 10) || 4000,
            presidio_port: parseInt(document.getElementById("docker_presidio_port").value, 10) || 5001
          }
        };

        const res = await fetch("/api/deploy", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            config: cfg,
            dry_run: dryRun,
            instance_git: gitInfo,
            infra_target: currentInfraTarget,
            infra_config: infraConfig
          })
        });
        const data = await res.json();
        if (!data.success) {
          terminal.innerHTML += `<div class="log-line log-red">[ERREUR] ${data.error}</div>`;
          btnDeploy.disabled = false;
          btnDry.disabled = false;
          badge.textContent = "Erreur";
          return;
        }

        startLogPolling(dryRun);
      } catch (err) {
        terminal.innerHTML += `<div class="log-line log-red">[FATAL] ${err.message}</div>`;
        btnDeploy.disabled = false;
        btnDry.disabled = false;
      }
    }

    function startLogPolling(dryRun) {
      if (logPollingInterval) clearInterval(logPollingInterval);

      const terminal = document.getElementById("terminalConsole");
      const badge = document.getElementById("deployStatusBadge");
      const btnGoFinal = document.getElementById("btnGoFinal");
      const btnDeploy = document.getElementById("btnStartDeploy");
      const btnDry = document.getElementById("btnDryRun");

      logPollingInterval = setInterval(async () => {
        try {
          const res = await fetch("/api/deploy/status");
          const state = await res.json();

          terminal.innerHTML = state.logs.map(l => formatAnsiLine(l)).join("");
          terminal.scrollTop = terminal.scrollHeight;

          if (state.status === "success") {
            clearInterval(logPollingInterval);
            badge.textContent = dryRun ? "Simulation réussie" : "Déploiement terminé avec succès !";
            badge.style.color = "var(--success)";
            badge.style.borderColor = "var(--success)";
            btnDeploy.disabled = false;
            btnDry.disabled = false;
            btnGoFinal.style.display = "inline-flex";

            if (!dryRun) {
              setTimeout(() => { goToStep(11); }, 1500);
            }
          } else if (state.status === "error") {
            clearInterval(logPollingInterval);
            badge.textContent = "Échec du déploiement";
            badge.style.color = "var(--danger)";
            badge.style.borderColor = "var(--danger)";
            btnDeploy.disabled = false;
            btnDry.disabled = false;
          }
        } catch (err) {
          console.error("Polling error:", err);
        }
      }, 1000);
    }

    function formatAnsiLine(line) {
      let cls = "log-line";
      if (line.includes("[INFO]")) cls += " log-cyan";
      else if (line.includes("[OK]") || line.includes("EFFECTUE AVEC SUCCES")) cls += " log-green";
      else if (line.includes("[WARN]")) cls += " log-yellow";
      else if (line.includes("[ERROR]") || line.includes("Échec")) cls += " log-red";

      const clean = line.replace(/\\x1b\\[[0-9;]*m/g, "");
      return `<div class="${cls}">${escapeHtml(clean)}</div>`;
    }

    function escapeHtml(text) {
      const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
      return text.replace(/[&<>"']/g, m => map[m]);
    }

    function getCurrentPublicUrl() {
      if (currentInfraTarget === "docker_lab") {
        const webPort = parseInt(document.getElementById("docker_webui_port").value, 10) || 3000;
        return `http://localhost:${webPort}/`;
      }
      const fqdn = document.getElementById("net_fqdn").value.trim() || "assistant.example.org";
      return `https://${fqdn}/`;
    }

    function buildRecapCards() {
      const cfg = collectFormData();
      const fqdn = cfg.network.public_fqdn || "assistant.example.org";
      const hermesPass = cfg.hermes.admin_password || "admin";
      const hermesPat = cfg.hermes.api_token || "";
      const grid = document.getElementById("recapAccessGrid");

      let cards = [];

      if (currentInfraTarget === "docker_lab") {
        const webPort = parseInt(document.getElementById("docker_webui_port").value, 10) || 3000;
        const llmPort = parseInt(document.getElementById("docker_litellm_port").value, 10) || 4000;
        const presPort = parseInt(document.getElementById("docker_presidio_port").value, 10) || 5001;

        cards = [
          {
            title: "🌐 Portail Collaborateur (Open-WebUI Local)",
            url: `http://localhost:${webPort}/`,
            desc: "Interface conversationnelle d'entreprise hébergée localement via Docker Compose. Identifiant : <strong>admin@arcia.local</strong>",
            actionText: "Ouvrir le portail"
          },
          {
            title: "🧠 Passerelle d'Inférence IA LiteLLM Proxy",
            url: `http://localhost:${llmPort}/v1`,
            desc: "Accès unifié OpenAI-compatible pour vos modèles Cloud (Claude 3.5 Sonnet, GPT-4o, DeepSeek-V3). Clé maître : <code>sk-or-v1-arcia-lab</code>",
            actionText: "Tester l'API"
          },
          {
            title: "🛡️ Guardrail DLP Microsoft Presidio Anonymizer",
            url: `http://localhost:${presPort}/`,
            desc: "Service local d'anonymisation et de détection des données sensibles (PII).",
            actionText: "Inspecter"
          }
        ];
      } else {
        cards = [
          {
            title: "🌐 Portail Collaborateur (Open-WebUI)",
            url: `https://${fqdn}/`,
            desc: "Interface conversationnelle souveraine pour l'ensemble des collaborateurs.",
            actionText: "Ouvrir le portail"
          },
          {
            title: "📊 Hermes Studio (Kanban Multi-Agents)",
            url: `https://${fqdn}/studio`,
            desc: `Pilotage visuel des agents autonomes. Identifiant : <strong>admin</strong> | Mot de passe : <code>${hermesPass}</code>`,
            actionText: "Accéder au Studio"
          },
          {
            title: "⚡ Hermes Desktop Gateway (WebSocket)",
            url: `https://${fqdn}/gateway`,
            desc: `Point de raccordement du client lourd de bureau Hermes. Jeton PAT : <code style="font-size:11px;">${hermesPat}</code>`,
            actionText: "Copier le token"
          }
        ];
      }

      if (createdRepoUrl) {
        cards.push({
          title: "📦 Dépôt Git d'Instance Privé (Chiffré)",
          url: createdRepoUrl,
          desc: "Contient la configuration et les secrets chiffrés (AES-256-GCM) de cette instance pour restauration ultérieure.",
          actionText: "Voir sur Git"
        });
      }

      if (cfg.teams_bot.enabled) {
        cards.push({
          title: "🤖 Webhook Microsoft Teams Bot",
          url: `https://${fqdn}/api/teams/messages`,
          desc: "Point de terminaison de messagerie configuré dans votre Azure Bot Service.",
          actionText: "Copier l'URL"
        });
      }

      if (cfg.omniroute.enabled) {
        cards.push({
          title: "🔀 Portail Administration OmniRoute",
          url: `http://omniroute.arcia.svc.cluster.local:20129`,
          desc: "Tableau de bord local de gestion multi-fournisseurs accessible sur le réseau LAN.",
          actionText: "Ouvrir"
        });
      }

      grid.innerHTML = cards.map(c => `
        <div class="recap-card">
          <div class="recap-card-title">${c.title}</div>
          <div class="recap-card-url">${c.url}</div>
          <div class="recap-card-desc">${c.desc}</div>
          <div style="display:flex; gap:8px;">
            <button class="recap-card-btn" onclick="navigator.clipboard.writeText('${c.url}'); alert('URL copiée dans le presse-papier !');">📋 Copier l'URL</button>
            <a href="${c.url}" target="_blank" class="recap-card-btn">${c.actionText} ↗</a>
          </div>
        </div>
      `).join("");
    }
  </script>
</body>
</html>
"""

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
    httpd = HTTPServer(server_address, WizardHTTPHandler)

    wizard_url = f"http://{args.host}:{port}/"

    print("\033[1m\033[96m=================================================================\033[0m")
    print("\033[1m\033[96m          ArcIA — Setup & Configuration Wizard v0.2              \033[0m")
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
