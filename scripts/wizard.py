#!/usr/bin/env python3
"""
ArcIA — Assistant & Moteur d'Installation Graphique Interactif (Wizard)
========================================================================
Ce serveur web autonome (Python 3 standard library uniquement, 0 dépendance)
guide pas-à-pas l'administrateur pour configurer et déployer une instance ArcIA
complète et 100% opérationnelle dès le clone initial du dépôt Git.

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
import secrets
import argparse
import threading
import subprocess
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, List, Tuple

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
# Utilitaires de Configuration & Secrets
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

    # Si aucun fichier n'existe, on génère un dictionnaire propre
    if not os.path.isfile(target):
        default_cfg = get_default_config_dict()
        return default_cfg, False

    try:
        # Tenter d'utiliser deploy.py parser
        sys.path.insert(0, SCRIPT_DIR)
        import deploy
        cfg = deploy.parse_yaml_or_env(target)
        if isinstance(cfg, dict):
            # Normalisation et valeurs par défaut
            cfg = ensure_config_defaults(cfg)
            return cfg, exists
    except Exception:
        pass

    return get_default_config_dict(), False

def get_default_config_dict() -> Dict[str, Any]:
    """Génère un dictionnaire de configuration par défaut complet et sécurisé."""
    return {
        "kubernetes": {
            "mode": "local",
            "kubeconfig": "",
            "context": detect_current_context(),
            "namespace": "arcia",
            "storage_class": "",
            "remote_ssh": {
                "node_ip": "127.0.0.1",
                "ssh_user": "debian",
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
            "default_model": "openrouter/auto",
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
            "storage_size": "20Gi"
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

    # Si certains secrets requis sont vides, les générer proprement
    if not cfg["hermes"].get("api_token") or cfg["hermes"]["api_token"] == "arcia-pat-change-me-secret-key-32b":
        cfg["hermes"]["api_token"] = generate_token("pat")
    if not cfg["entra_id_sso"].get("cookie_secret") or "xxxx" in cfg["entra_id_sso"]["cookie_secret"]:
        cfg["entra_id_sso"]["cookie_secret"] = generate_token("cookie")
    if not cfg["presidio"].get("master_key"):
        cfg["presidio"]["master_key"] = generate_token("presidio")

    # Si public_fqdn ou acme_email ont la valeur par défaut d'exemple, on laisse vide pour inviter à la saisie
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
  default_model: {qstr(llm.get('default_model', 'openrouter/auto'))}
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

    # Mise à jour synchronisée du fichier secrets/arcia.env si le dossier secrets existe
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
# Exécution du Déploiement en Tâche de Fond & Streaming Logs
# -----------------------------------------------------------------------------

def run_deployment_worker(dry_run: bool = False):
    global deployment_state
    deploy_script = os.path.join(SCRIPT_DIR, "deploy.py")
    cmd = [sys.executable, deploy_script, "--config", DEFAULT_CONFIG_PATH]
    if dry_run:
        cmd.append("--dry-run")

    with deployment_lock:
        deployment_state["status"] = "running"
        deployment_state["logs"] = []
        deployment_state["start_time"] = time.time()
        deployment_state["exit_code"] = None

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
                deployment_state["status"] = "success"
                # Extraction du FQDN pour le récapitulatif
                cfg, _ = load_config_data(DEFAULT_CONFIG_PATH)
                fqdn = cfg.get("network", {}).get("public_fqdn", "assistant.example.org")
                hermes_pass = cfg.get("hermes", {}).get("admin_password", "admin")
                hermes_pat = cfg.get("hermes", {}).get("api_token", "")
                teams_enabled = cfg.get("teams_bot", {}).get("enabled", False)
                omni_enabled = cfg.get("omniroute", {}).get("enabled", False)

                deployment_state["summary"] = {
                    "public_fqdn": fqdn,
                    "webui_url": f"https://{fqdn}/",
                    "studio_url": f"https://{fqdn}/studio",
                    "gateway_url": f"https://{fqdn}/gateway",
                    "teams_webhook": f"https://{fqdn}/api/teams/messages" if teams_enabled else None,
                    "omniroute_admin": "http://omniroute.arcia.svc.cluster.local:20129" if omni_enabled else None,
                    "hermes_admin_user": "admin",
                    "hermes_admin_pass": hermes_pass,
                    "hermes_pat": hermes_pat
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
        # Silence standard HTTP logs pour ne pas polluer le terminal
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

        elif path == "/api/deploy":
            with deployment_lock:
                if deployment_state["status"] == "running":
                    self.send_json(400, {"success": False, "error": "Un déploiement est déjà en cours d'exécution."})
                    return

            cfg = req_data.get("config")
            if cfg:
                save_config_to_files(cfg, DEFAULT_CONFIG_PATH)

            dry_run = req_data.get("dry_run", False)
            worker = threading.Thread(target=run_deployment_worker, args=(dry_run,), daemon=True)
            worker.start()

            self.send_json(200, {"success": True, "started": True, "dry_run": dry_run})

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
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(18, 24, 38, 0.95);
      --card-border: #1e293b;
      --accent-cyan: #00d2ff;
      --accent-blue: #3a7bd5;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --border-color: #2a374d;
      --input-bg: #0d1321;
      --btn-primary: linear-gradient(135deg, #00d2ff, #3a7bd5);
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --radius: 12px;
      --shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.4);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
    body { background: var(--bg); color: var(--text-main); min-height: 100vh; display: flex; flex-direction: column; background-image: radial-gradient(circle at 15% 20%, rgba(0, 210, 255, 0.08) 0%, transparent 40%), radial-gradient(circle at 85% 80%, rgba(58, 123, 213, 0.08) 0%, transparent 40%); }

    /* Header */
    header { background: rgba(13, 19, 33, 0.9); backdrop-filter: blur(10px); border-bottom: 1px solid var(--border-color); padding: 16px 32px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
    .brand { display: flex; align-items: center; gap: 14px; }
    .brand-logo { width: 36px; height: 36px; border-radius: 10px; background: var(--btn-primary); display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 18px; color: #fff; box-shadow: 0 0 15px rgba(0, 210, 255, 0.4); }
    .brand-title { font-size: 20px; font-weight: 700; letter-spacing: -0.5px; }
    .brand-subtitle { font-size: 13px; color: var(--text-muted); }
    .header-badge { font-size: 12px; background: rgba(0, 210, 255, 0.1); color: var(--accent-cyan); border: 1px solid rgba(0, 210, 255, 0.3); border-radius: 20px; padding: 4px 12px; font-weight: 600; }

    /* Layout */
    .app-container { display: flex; flex: 1; max-width: 1360px; width: 100%; margin: 0 auto; padding: 24px; gap: 24px; }
    
    /* Stepper Sidebar */
    .stepper-nav { width: 320px; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow); height: fit-content; position: sticky; top: 88px; }
    .stepper-title { font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: var(--text-muted); margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid var(--border-color); }
    .step-item { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-radius: 8px; cursor: pointer; transition: all 0.2s ease; margin-bottom: 6px; }
    .step-item:hover { background: rgba(255, 255, 255, 0.04); }
    .step-item.active { background: rgba(0, 210, 255, 0.12); border-left: 3px solid var(--accent-cyan); }
    .step-item.completed .step-icon { background: var(--success); color: white; border-color: var(--success); }
    .step-icon { width: 28px; height: 28px; border-radius: 50%; border: 2px solid var(--border-color); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; color: var(--text-muted); flex-shrink: 0; transition: all 0.2s; }
    .step-item.active .step-icon { border-color: var(--accent-cyan); color: var(--accent-cyan); box-shadow: 0 0 10px rgba(0, 210, 255, 0.3); }
    .step-label { font-size: 14px; font-weight: 500; }
    .step-tag { margin-left: auto; font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 600; }
    .step-tag.optional { background: rgba(255, 255, 255, 0.08); color: var(--text-muted); }
    .step-tag.required { background: rgba(0, 210, 255, 0.15); color: var(--accent-cyan); }

    /* Main Content Area */
    .content-area { flex: 1; display: flex; flex-direction: column; }
    .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius); padding: 32px; box-shadow: var(--shadow); margin-bottom: 24px; position: relative; }
    
    .screen-header { margin-bottom: 24px; }
    .screen-title { font-size: 24px; font-weight: 700; margin-bottom: 8px; display: flex; align-items: center; gap: 10px; }
    .screen-desc { font-size: 14px; color: var(--text-muted); line-height: 1.5; }

    /* Form Fields */
    .form-group { margin-bottom: 20px; }
    .form-label { display: block; font-size: 14px; font-weight: 600; margin-bottom: 6px; color: #e2e8f0; }
    .form-sublabel { font-size: 12px; color: var(--text-muted); margin-bottom: 8px; line-height: 1.4; }
    .form-control { width: 100%; background: var(--input-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 12px 14px; color: var(--text-main); font-size: 14px; transition: border-color 0.2s, box-shadow 0.2s; outline: none; }
    .form-control:focus { border-color: var(--accent-cyan); box-shadow: 0 0 0 3px rgba(0, 210, 255, 0.15); }
    .input-row { display: flex; gap: 10px; }
    
    /* Toggle Switch */
    .toggle-wrapper { display: flex; align-items: center; justify-content: space-between; padding: 16px; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-color); border-radius: 10px; margin-bottom: 20px; }
    .toggle-info h4 { font-size: 15px; margin-bottom: 4px; }
    .toggle-info p { font-size: 12px; color: var(--text-muted); }
    .switch { position: relative; display: inline-block; width: 50px; height: 26px; }
    .switch input { opacity: 0; width: 0; height: 0; }
    .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #334155; transition: .3s; border-radius: 34px; }
    .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 4px; bottom: 4px; background-color: white; transition: .3s; border-radius: 50%; }
    input:checked + .slider { background: linear-gradient(135deg, #00d2ff, #3a7bd5); }
    input:checked + .slider:before { transform: translateX(24px); }

    /* Collapsible / Doc Guides */
    .doc-accordion { background: rgba(0, 210, 255, 0.04); border: 1px solid rgba(0, 210, 255, 0.2); border-radius: 8px; margin-top: 16px; overflow: hidden; }
    .doc-header { padding: 12px 16px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; font-size: 13px; font-weight: 600; color: var(--accent-cyan); }
    .doc-body { padding: 16px; font-size: 13px; line-height: 1.6; color: #cbd5e1; border-top: 1px solid rgba(0, 210, 255, 0.1); background: rgba(0, 0, 0, 0.2); display: none; }
    .doc-body ol { margin-left: 20px; margin-top: 8px; margin-bottom: 8px; }
    .doc-body li { margin-bottom: 6px; }
    .doc-link { color: var(--accent-cyan); text-decoration: none; font-weight: 600; display: inline-flex; align-items: center; gap: 4px; }
    .doc-link:hover { text-decoration: underline; }

    /* Action Buttons */
    .actions-bar { display: flex; justify-content: space-between; align-items: center; margin-top: 16px; }
    .btn { padding: 10px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; display: inline-flex; align-items: center; gap: 8px; transition: all 0.2s; }
    .btn-secondary { background: #1e293b; color: #cbd5e1; border: 1px solid var(--border-color); }
    .btn-secondary:hover { background: #334155; color: white; }
    .btn-primary { background: var(--btn-primary); color: white; box-shadow: 0 4px 12px rgba(0, 210, 255, 0.3); }
    .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(0, 210, 255, 0.4); }
    .btn-test { background: #1e293b; color: var(--accent-cyan); border: 1px solid rgba(0, 210, 255, 0.4); font-size: 12px; padding: 6px 12px; }
    .btn-test:hover { background: rgba(0, 210, 255, 0.15); }

    /* Badges & Alerts */
    .alert-box { padding: 14px 18px; border-radius: 8px; font-size: 13px; line-height: 1.5; margin-bottom: 20px; display: flex; align-items: flex-start; gap: 12px; }
    .alert-info { background: rgba(0, 210, 255, 0.08); border: 1px solid rgba(0, 210, 255, 0.3); color: #e0f2fe; }
    .alert-success { background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); color: #a7f3d0; }
    .alert-warn { background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); color: #fde68a; }

    /* Live Terminal Console */
    .terminal-box { background: #050811; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; font-size: 13px; height: 380px; overflow-y: auto; color: #94a3b8; white-space: pre-wrap; line-height: 1.5; box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.6); }
    .log-line { margin-bottom: 2px; }
    .log-cyan { color: #38bdf8; font-weight: 600; }
    .log-green { color: #4ade80; font-weight: 600; }
    .log-yellow { color: #facc15; }
    .log-red { color: #f87171; font-weight: 600; }

    /* Success Cards Grid */
    .recap-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; margin: 20px 0; }
    .recap-card { background: rgba(13, 19, 33, 0.8); border: 1px solid var(--border-color); border-radius: 10px; padding: 18px; position: relative; transition: border-color 0.2s; }
    .recap-card:hover { border-color: var(--accent-cyan); }
    .recap-card-title { font-size: 14px; font-weight: 700; color: #e2e8f0; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
    .recap-card-url { font-size: 13px; color: var(--accent-cyan); word-break: break-all; margin-bottom: 8px; font-family: monospace; }
    .recap-card-desc { font-size: 12px; color: var(--text-muted); margin-bottom: 12px; }
    .recap-card-btn { font-size: 11px; padding: 4px 10px; border-radius: 6px; background: rgba(255, 255, 255, 0.08); color: white; border: 1px solid var(--border-color); cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 4px; }
    .recap-card-btn:hover { background: var(--accent-blue); }

    /* Hidden step screens */
    .screen { display: none; }
    .screen.active { display: block; animation: fadeIn 0.3s ease; }

    @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-logo">A</div>
      <div>
        <div class="brand-title">ArcIA Enterprise Setup Wizard</div>
        <div class="brand-subtitle">Assistant de Déploiement & Configuration Universelle v0.2</div>
      </div>
    </div>
    <div style="display: flex; gap: 12px; align-items: center;">
      <span id="instanceModeBadge" class="header-badge">Chargement...</span>
      <button class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="saveConfigOnly()">💾 Enregistrer sans déployer</button>
    </div>
  </header>

  <div class="app-container">
    
    <!-- Stepper Navigation -->
    <aside class="stepper-nav">
      <div class="stepper-title">Étapes d'installation</div>
      <div class="step-item active" onclick="goToStep(1)">
        <div class="step-icon">1</div>
        <div class="step-label">🚀 Bienvenue</div>
        <div class="step-tag required">Info</div>
      </div>
      <div class="step-item" onclick="goToStep(2)">
        <div class="step-icon">2</div>
        <div class="step-label">☸️ Cluster Kubernetes</div>
        <div class="step-tag required">Requis</div>
      </div>
      <div class="step-item" onclick="goToStep(3)">
        <div class="step-icon">3</div>
        <div class="step-label">🌐 Réseau & Ingress</div>
        <div class="step-tag required">Requis</div>
      </div>
      <div class="step-item" onclick="goToStep(4)">
        <div class="step-icon">4</div>
        <div class="step-label">🧠 Passerelle LLM & IA</div>
        <div class="step-tag required">Requis</div>
      </div>
      <div class="step-item" onclick="goToStep(5)">
        <div class="step-icon">5</div>
        <div class="step-label">🤖 Hermes Studio & Agents</div>
        <div class="step-tag required">Requis</div>
      </div>
      <div class="step-item" onclick="goToStep(6)">
        <div class="step-icon">6</div>
        <div class="step-label">🔐 SSO Entra ID</div>
        <div class="step-tag optional">Option</div>
      </div>
      <div class="step-item" onclick="goToStep(7)">
        <div class="step-icon">7</div>
        <div class="step-label">💬 Bot Microsoft Teams</div>
        <div class="step-tag optional">Option</div>
      </div>
      <div class="step-item" onclick="goToStep(8)">
        <div class="step-icon">8</div>
        <div class="step-label">🔀 Routeur OmniRoute</div>
        <div class="step-tag optional">Option</div>
      </div>
      <div class="step-item" onclick="goToStep(9)">
        <div class="step-icon">9</div>
        <div class="step-label">⚡ Déploiement Automatisé</div>
        <div class="step-tag required">Action</div>
      </div>
      <div class="step-item" onclick="goToStep(10)">
        <div class="step-icon">10</div>
        <div class="step-label">🎉 Accès & Récapitulatif</div>
        <div class="step-tag required">Prêt</div>
      </div>
    </aside>

    <!-- Main Content Area -->
    <main class="content-area">
      
      <!-- SCREEN 1: Bienvenue -->
      <section id="step1" class="screen active card">
        <div class="screen-header">
          <h2 class="screen-title">Bienvenue dans l'assistant d'installation d'ArcIA</h2>
          <p class="screen-desc">Ce wizard configure et déploie l'intégralité de la plateforme d'agents souverains ArcIA en quelques minutes sur votre infrastructure Kubernetes.</p>
        </div>

        <div id="existingConfigAlert" class="alert-box alert-info" style="display:none;">
          <span style="font-size:20px;">ℹ️</span>
          <div>
            <strong>Instance existante détectée !</strong><br>
            Le fichier <code>arcia.config.yaml</code> a été chargé. Vous pouvez modifier n'importe quel paramètre ou activer des modules optionnels (SSO Entra ID, Bot Teams) et relancer le déploiement en toute sécurité sans perte de données.
          </div>
        </div>

        <div class="alert-box alert-success">
          <span style="font-size:20px;">✨</span>
          <div>
            <strong>Prise en charge intégrale automatique par défaut :</strong><br>
            Tous les composants internes (Presidio DLP pour le masquage des données sensibles, portail Open-WebUI, moteur d'agents Hermes, LiteLLM Proxy, compétences et outils natifs Graphify, Ponytail et Public-APIs) sont provisionnés <strong>automatiquement</strong> sans intervention manuelle requise.
          </div>
        </div>

        <div style="margin: 24px 0; background: rgba(255,255,255,0.02); padding: 20px; border-radius: 8px; border: 1px solid var(--border-color);">
          <h4 style="margin-bottom: 12px; font-size: 15px;">Ce dont vous avez besoin pour démarrer :</h4>
          <ul style="margin-left: 20px; font-size: 13px; line-height: 1.8; color: #cbd5e1;">
            <li><strong>Un cluster Kubernetes</strong> accessible via <code>kubectl</code> en local (EKS, AKS, GKE, K3s, Minikube) ou via SSH sur un nœud K3s.</li>
            <li><strong>Un nom de domaine public (FQDN)</strong> pointant vers l'adresse IP publique de votre Ingress (ex: <code>assistant.mon-entreprise.com</code>).</li>
            <li><strong>Une clé d'API LLM Cloud</strong> (ex: <a href="https://openrouter.ai/keys" target="_blank" style="color:var(--accent-cyan);">OpenRouter</a>) donnant accès à Claude 3.5 Sonnet, GPT-4o, DeepSeek-V3.</li>
          </ul>
        </div>

        <div class="actions-bar">
          <div></div>
          <button class="btn btn-primary" onclick="goToStep(2)">Commencer la configuration →</button>
        </div>
      </section>

      <!-- SCREEN 2: Kubernetes -->
      <section id="step2" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 2 : Connectivité au Cluster Kubernetes</h2>
          <p class="screen-desc">Renseignez la méthode de connexion au cluster où sera déployée la plateforme ArcIA.</p>
        </div>

        <div class="form-group">
          <label class="form-label">Mode d'exécution de kubectl</label>
          <div class="form-sublabel">Choisissez si kubectl s'exécute depuis votre machine locale ou directement via SSH sur un nœud maître K3s.</div>
          <select id="k8s_mode" class="form-control" onchange="toggleK8sMode()">
            <option value="local">Local — Utilise la commande kubectl locale de cette machine</option>
            <option value="remote-ssh">Remote SSH — Exécute kubectl à distance sur le nœud K3s</option>
          </select>
        </div>

        <!-- Mode Local -->
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
            <div class="form-sublabel">Laisser vide pour utiliser le fichier standard ~/.kube/config.</div>
            <input type="text" id="k8s_kubeconfig" class="form-control" placeholder="C:\Users\...\.kube\config ou /home/.../.kube/config">
          </div>
        </div>

        <!-- Mode Remote SSH -->
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

        <div style="margin: 16px 0; display:flex; align-items:center; gap:14px;">
          <button class="btn btn-test" onclick="testK8sConnection()">🔍 Tester la connexion au cluster</button>
          <span id="k8s_test_status" style="font-size: 13px;"></span>
        </div>

        <div id="k8s_nodes_result" style="display:none; margin-top:12px; background:rgba(0,0,0,0.3); border:1px solid var(--border-color); border-radius:8px; padding:12px; font-family:monospace; font-size:12px;"></div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(1)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(3)">Suivant : Réseau & Ingress →</button>
        </div>
      </section>

      <!-- SCREEN 3: Réseau & Ingress -->
      <section id="step3" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 3 : Exposition Réseau, Domaine FQDN & TLS</h2>
          <p class="screen-desc">Définissez le nom de domaine public d'accès et la gestion automatique des certificats HTTPS.</p>
        </div>

        <div class="form-group">
          <label class="form-label">Nom de domaine public complet (FQDN) <span style="color:var(--accent-cyan);">*</span></label>
          <div class="form-sublabel">Vos collaborateurs accéderont au portail via cette URL (ex: <code>assistant.mon-entreprise.com</code>).</div>
          <input type="text" id="net_fqdn" class="form-control" placeholder="ex: assistant.mon-entreprise.com" required>
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
          <div class="form-sublabel">Utilisé par l'autorité de certification Let's Encrypt pour les alertes d'expiration de certificat.</div>
          <input type="email" id="net_acme_email" class="form-control" placeholder="admin@mon-entreprise.com">
        </div>

        <div class="alert-box alert-info">
          <span style="font-size:20px;">💡</span>
          <div>
            <strong>Rappel DNS d'Entreprise :</strong><br>
            N'oubliez pas de créer un enregistrement DNS de type <code>A</code> ou <code>CNAME</code> pointant votre nom de domaine vers l'adresse IP publique de votre Ingress ou pare-feu.
          </div>
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(2)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(4)">Suivant : Passerelle LLM →</button>
        </div>
      </section>

      <!-- SCREEN 4: Passerelle LLM & IA -->
      <section id="step4" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 4 : Passerelle LLM & Modèles d'Inférence</h2>
          <p class="screen-desc">Connectez votre fournisseur d'inférence d'entreprise. Les requêtes sont automatiquement protégées par le bouclier DLP Presidio.</p>
        </div>

        <div class="form-group">
          <label class="form-label">Clé d'API OpenRouter d'entreprise <span style="color:var(--accent-cyan);">*</span></label>
          <div class="form-sublabel">Fournit un accès unifié et optimisé à Claude 3.5 Sonnet, GPT-4o, DeepSeek-V3 et Mistral Large. <a href="https://openrouter.ai/keys" target="_blank" class="doc-link">Obtenir une clé sur OpenRouter.ai ↗</a></div>
          <input type="password" id="llm_key" class="form-control" placeholder="sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx" required>
        </div>

        <div class="input-row">
          <div class="form-group" style="flex:1;">
            <label class="form-label">Modèle d'entreprise par défaut</label>
            <select id="llm_model" class="form-control">
              <option value="openrouter/auto">openrouter/auto (Routage automatique optimisé)</option>
              <option value="openrouter/anthropic/claude-3.5-sonnet">openrouter/anthropic/claude-3.5-sonnet (Raisonnement de pointe)</option>
              <option value="openrouter/openai/gpt-4o">openrouter/openai/gpt-4o (Polyvalent et multimodal)</option>
              <option value="openrouter/deepseek/deepseek-chat">openrouter/deepseek/deepseek-chat (Ultra-économique)</option>
            </select>
          </div>
          <div class="form-group" style="flex:1;">
            <label class="form-label">Serveur vLLM local souverain (Optionnel)</label>
            <input type="text" id="llm_vllm" class="form-control" placeholder="ex: http://vllm.corp.local:8000/v1">
          </div>
        </div>

        <div class="alert-box alert-success">
          <span style="font-size:20px;">🛡️</span>
          <div>
            <strong>Bouclier de Confidentialité Presidio DLP activé d'office :</strong><br>
            Toutes les requêtes sortantes passent automatiquement par le service de caviardage DLP en coupure avant transmission aux modèles Cloud (masquage déterministe des adresses emails, numéros de téléphone, numéros de cartes bancaires et clés d'API).
          </div>
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(3)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(5)">Suivant : Hermes Studio →</button>
        </div>
      </section>

      <!-- SCREEN 5: Hermes Studio & Desktop -->
      <section id="step5" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 5 : Moteur d'Agents Hermes & Studio Kanban</h2>
          <p class="screen-desc">Sécurisez l'accès au Studio Kanban multi-agents et à la passerelle WebSocket du client de bureau Hermes Desktop.</p>
        </div>

        <div class="form-group">
          <label class="form-label">Mot de passe Administrateur Hermes Studio (/studio) <span style="color:var(--accent-cyan);">*</span></label>
          <div class="form-sublabel">Identifiant de connexion par défaut : <code>admin</code>. Utilisé pour administrer les agents sur le portail Kanban visuel.</div>
          <div class="input-row">
            <input type="text" id="hermes_password" class="form-control" required>
            <button class="btn btn-secondary" style="white-space:nowrap;" onclick="generateSecretFor('hermes_password', 'admin')">🎲 Régénérer</button>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Jeton PAT Hermes Desktop Gateway (/gateway) <span style="color:var(--accent-cyan);">*</span></label>
          <div class="form-sublabel">Jeton d'authentification (Personal Access Token) pour connecter l'application de bureau Hermes (Mac/Win/Linux).</div>
          <div class="input-row">
            <input type="text" id="hermes_pat" class="form-control" required>
            <button class="btn btn-secondary" style="white-space:nowrap;" onclick="generateSecretFor('hermes_pat', 'pat')">🎲 Régénérer</button>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Espace de stockage persistant de l'agent (PVC)</label>
          <input type="text" id="hermes_storage" class="form-control" value="20Gi">
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(4)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(6)">Suivant : SSO Entra ID (Optionnel) →</button>
        </div>
      </section>

      <!-- SCREEN 6: SSO Entra ID (Optionnel) -->
      <section id="step6" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 6 : Authentification SSO Microsoft Entra ID (Zero-Trust)</h2>
          <p class="screen-desc">Optionnel : Restreignez l'accès à Hermes Studio et Open-WebUI aux seuls comptes Microsoft 365 de votre entreprise.</p>
        </div>

        <div class="toggle-wrapper">
          <div class="toggle-info">
            <h4>Activer l'Authentification SSO Microsoft Entra ID</h4>
            <p>Active oauth2-proxy et le middleware Traefik ForwardAuth pour verrouiller l'accès aux collaborateurs de votre tenant.</p>
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

        <!-- Guide interactif Entra ID -->
        <div class="doc-accordion">
          <div class="doc-header" onclick="toggleDocAccordion('docEntra')">
            <span>📘 Comment créer l'application dans Microsoft Entra ID ? (Guide pas-à-pas)</span>
            <span id="docEntraIcon">▼</span>
          </div>
          <div id="docEntra" class="doc-body">
            <p>Suivez ces 5 étapes rapides sur le <strong>Portail Azure</strong> :</p>
            <ol>
              <li>Allez sur <a href="https://portal.azure.com" target="_blank" class="doc-link">portal.azure.com</a> > <strong>Microsoft Entra ID</strong> > <strong>Inscriptions d'applications</strong> > <strong>+ Nouvelle inscription</strong>.</li>
              <li>Nommez l'application (ex: <code>ArcIA-SSO</code>), choisissez <em>Comptes dans cet annuaire uniquement (Mono-locataire)</em>.</li>
              <li>Dans <strong>URI de redirection (Web)</strong>, saisissez : <code id="guide_sso_callback">https://&lt;votre-fqdn&gt;/oauth2/callback</code>.</li>
              <li>Dans <strong>Vue d'ensemble</strong>, copiez l'<strong>ID d'application (client)</strong> et l'<strong>ID de l'annuaire (tenant)</strong>.</li>
              <li>Dans <strong>Certificats & secrets</strong>, créez un <strong>Nouveau secret client</strong> et copiez sa <em>Valeur</em>.</li>
            </ol>
            <p style="margin-top:10px;">
              Consultez le guide officiel complet : <a href="https://github.com/nicolastheuil/ArcIA/blob/main/docs/guides/portail-webui-entraid.md#creation-app-entraid" target="_blank" class="doc-link">Guide détaillé SSO Entra ID sur GitHub ↗</a>
            </p>
          </div>
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(5)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(7)">Suivant : Bot Teams (Optionnel) →</button>
        </div>
      </section>

      <!-- SCREEN 7: Bot Microsoft Teams (Optionnel) -->
      <section id="step7" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 7 : Adaptateur Microsoft Teams Bot</h2>
          <p class="screen-desc">Optionnel : Intégrez le bot ArcIA directement dans Microsoft Teams (chats 1:1 et mentions @ArcIA dans les canaux).</p>
        </div>

        <div class="toggle-wrapper">
          <div class="toggle-info">
            <h4>Activer le Bot Microsoft Teams</h4>
            <p>Déploie le microservice adaptateur Teams Bot et route les requêtes du webhook Azure Bot Service.</p>
          </div>
          <label class="switch">
            <input type="checkbox" id="teams_enabled" onchange="toggleTeamsFields()">
            <span class="slider"></span>
          </label>
        </div>

        <div id="teams_fields" style="opacity: 0.4; pointer-events: none; transition: opacity 0.3s;">
          <div class="input-row">
            <div class="form-group" style="flex:1;">
              <label class="form-label">Microsoft App ID (Bot ID) <span style="color:var(--accent-cyan);">*</span></label>
              <input type="text" id="teams_appid" class="form-control" placeholder="ex: 00000000-0000-0000-0000-000000000000">
            </div>
            <div class="form-group" style="flex:1;">
              <label class="form-label">App Password (Secret Bot) <span style="color:var(--accent-cyan);">*</span></label>
              <input type="password" id="teams_password" class="form-control" placeholder="Mot de passe généré dans Azure Bot">
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">Prompt système du Bot Teams</label>
            <textarea id="teams_prompt" class="form-control" rows="2">Tu es ArcIA, l'assistant d'entreprise. Réponds de façon synthétique, professionnelle et structurée en Markdown.</textarea>
          </div>
        </div>

        <!-- Guide interactif Teams Bot -->
        <div class="doc-accordion">
          <div class="doc-header" onclick="toggleDocAccordion('docTeams')">
            <span>📘 Comment créer le bot sur Azure Bot Service ? (Guide pas-à-pas)</span>
            <span id="docTeamsIcon">▼</span>
          </div>
          <div id="docTeams" class="doc-body">
            <p>Suivez ces 4 étapes simples sur le <strong>Portail Azure</strong> :</p>
            <ol>
              <li>Créez une ressource <strong>Azure Bot</strong> (type d'application : <em>Mono-locataire</em> ou <em>Multi-locataire</em>).</li>
              <li>Dans <strong>Configuration</strong>, renseignez l'URL de messagerie (Messaging endpoint) : <code id="guide_teams_webhook">https://&lt;votre-fqdn&gt;/api/teams/messages</code>.</li>
              <li>Copiez le <strong>Microsoft App ID</strong> et cliquez sur <em>Gérer le mot de passe</em> pour générer un nouveau secret client (App Password).</li>
              <li>Dans le menu <strong>Canaux</strong>, activez le canal <strong>Microsoft Teams</strong> en un clic.</li>
            </ol>
            <p style="margin-top:10px;">
              Consultez le guide officiel complet : <a href="https://github.com/nicolastheuil/ArcIA/blob/main/docs/guides/integration-teams.md#creation-azure-bot" target="_blank" class="doc-link">Guide détaillé Intégration Teams sur GitHub ↗</a>
            </p>
          </div>
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(6)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(8)">Suivant : OmniRoute (Optionnel) →</button>
        </div>
      </section>

      <!-- SCREEN 8: OmniRoute & Avancé -->
      <section id="step8" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 8 : Routeur Multi-Fournisseurs OmniRoute</h2>
          <p class="screen-desc">Optionnel : Activez OmniRoute v3.8.51 pour disposer d'un portail LAN d'administration multi-fournisseurs.</p>
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

        <div class="alert-box alert-info">
          <span style="font-size:20px;">ℹ️</span>
          <div>
            Par défaut, <strong>LiteLLM Proxy</strong> (:4000) gère déjà le routage d'entreprise unifié avec Presidio DLP. N'activez OmniRoute que si vous avez un besoin spécifique de gestion multi-fournisseurs avancée en amont.
          </div>
        </div>

        <div class="actions-bar">
          <button class="btn btn-secondary" onclick="goToStep(7)">← Précédent</button>
          <button class="btn btn-primary" onclick="goToStep(9)">Suivant : Récapitulatif & Déploiement →</button>
        </div>
      </section>

      <!-- SCREEN 9: Déploiement Automatique -->
      <section id="step9" class="screen card">
        <div class="screen-header">
          <h2 class="screen-title">Étape 9 : Validation & Lancement du Déploiement</h2>
          <p class="screen-desc">Vérifiez les paramètres avant l'application sur le cluster. Les compétences et outils natifs seront déployés automatiquement.</p>
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
          <button class="btn btn-secondary" onclick="goToStep(8)">← Précédent</button>
          <button id="btnGoFinal" class="btn btn-primary" style="display:none;" onclick="goToStep(10)">Voir le récapitulatif final et les URLs d'accès →</button>
        </div>
      </section>

      <!-- SCREEN 10: Récapitulatif Final & Accès -->
      <section id="step10" class="screen card">
        <div class="screen-header">
          <div style="font-size: 48px; margin-bottom: 12px;">🎉</div>
          <h2 class="screen-title" style="color: var(--success);">ArcIA est 100% Opérationnel !</h2>
          <p class="screen-desc">L'ensemble des microservices, secrets, certificats TLS, compétences et passerelles d'inférence ont été déployés avec succès.</p>
        </div>

        <div class="recap-grid" id="recapAccessGrid">
          <!-- Injecté dynamiquement par JavaScript -->
        </div>

        <div class="alert-box alert-success" style="margin-top: 24px;">
          <span style="font-size:20px;">✅</span>
          <div>
            <strong>Compétences et Outils Activés Automatiquement :</strong><br>
            Les compétences natives (<em>Ponytail</em> pour la sobriété logicielle, <em>Graphify</em> pour le GraphRAG AST local déterministe, et <em>Public-APIs</em>) sont intégrées d'office et utilisables immédiatement par les agents sans aucune manipulation.
          </div>
        </div>

        <div class="alert-box alert-info">
          <span style="font-size:20px;">🔄</span>
          <div>
            <strong>Installation évolutive et ré-exécutable :</strong><br>
            Vous pouvez à tout moment relancer ce Wizard (<code>./wizard.sh</code> ou <code>.\\wizard.ps1</code>) pour modifier un paramètre, changer une clé API ou activer a posteriori l'authentification Entra ID ou le bot Teams par-dessus cette même installation.
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
    // État global de l'application
    let currentStep = 1;
    let configData = {};
    let isExistingInstallation = false;
    let logPollingInterval = null;

    // Initialisation au chargement de la page
    window.addEventListener("DOMContentLoaded", () => {
      fetchConfig();
    });

    async function fetchConfig() {
      try {
        const res = await fetch("/api/config");
        const data = await res.json();
        configData = data.config || {};
        isExistingInstallation = data.is_existing;

        // Mise à jour de l'indicateur d'instance
        const badge = document.getElementById("instanceModeBadge");
        if (isExistingInstallation) {
          badge.textContent = "Instance existante chargée (Mode Mise à Jour)";
          badge.style.color = "var(--success)";
          badge.style.borderColor = "var(--success)";
          document.getElementById("existingConfigAlert").style.display = "flex";
        } else {
          badge.textContent = "Nouvelle installation";
        }

        // Remplissage des contextes K8s disponibles
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
        console.error("Erreur lors de la récupération de la configuration:", err);
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

      // Step 2
      document.getElementById("k8s_mode").value = k8s.mode || "local";
      document.getElementById("k8s_context").value = k8s.context || "";
      document.getElementById("k8s_kubeconfig").value = k8s.kubeconfig || "";
      document.getElementById("k8s_namespace").value = k8s.namespace || "arcia";
      document.getElementById("k8s_storage_class").value = k8s.storage_class || "";
      const ssh = k8s.remote_ssh || {};
      document.getElementById("k8s_ssh_ip").value = ssh.node_ip || "127.0.0.1";
      document.getElementById("k8s_ssh_user").value = ssh.ssh_user || "debian";
      document.getElementById("k8s_ssh_port").value = ssh.ssh_port || 22;
      toggleK8sMode();

      // Step 3
      document.getElementById("net_fqdn").value = net.public_fqdn || "";
      document.getElementById("net_tls_mode").value = net.tls_mode || "letsencrypt-prod";
      document.getElementById("net_ingress_class").value = net.ingress_class || "traefik";
      document.getElementById("net_acme_email").value = net.acme_email || "";
      toggleTlsMode();

      // Step 4
      document.getElementById("llm_key").value = llm.openrouter_api_key || "";
      document.getElementById("llm_model").value = llm.default_model || "openrouter/auto";
      document.getElementById("llm_vllm").value = llm.local_vllm_endpoint || "";

      // Step 5
      document.getElementById("hermes_password").value = hermes.admin_password || "admin";
      document.getElementById("hermes_pat").value = hermes.api_token || "";
      document.getElementById("hermes_storage").value = hermes.storage_size || "20Gi";

      // Step 6
      document.getElementById("sso_enabled").checked = !!sso.enabled;
      document.getElementById("sso_tenant").value = sso.tenant_id || "";
      document.getElementById("sso_client").value = sso.client_id || "";
      document.getElementById("sso_secret").value = sso.client_secret || "";
      document.getElementById("sso_cookie").value = sso.cookie_secret || "";
      toggleSsoFields();

      // Step 7
      document.getElementById("teams_enabled").checked = !!teams.enabled;
      document.getElementById("teams_appid").value = teams.app_id || "";
      document.getElementById("teams_password").value = teams.app_password || "";
      if (teams.system_prompt) {
        document.getElementById("teams_prompt").value = teams.system_prompt;
      }
      toggleTeamsFields();

      // Step 8
      document.getElementById("omni_enabled").checked = !!omni.enabled;

      updateGuideFqdn();
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
          storage_size: "20Gi"
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

    // Navigation entre étapes
    function goToStep(stepNumber) {
      if (stepNumber < 1 || stepNumber > 10) return;
      
      // Validation légère avant passage à l'étape suivante
      if (stepNumber > currentStep && !validateStep(currentStep)) {
        return;
      }

      currentStep = stepNumber;
      updateGuideFqdn();

      // Mise à jour de l'affichage des écrans
      document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
      const targetScreen = document.getElementById(`step${stepNumber}`);
      if (targetScreen) targetScreen.classList.add("active");

      // Mise à jour du stepper
      const stepItems = document.querySelectorAll(".step-item");
      stepItems.forEach((item, idx) => {
        item.classList.remove("active");
        if (idx + 1 === stepNumber) {
          item.classList.add("active");
        }
        if (idx + 1 < stepNumber) {
          item.classList.add("completed");
        } else {
          item.classList.remove("completed");
        }
      });

      // Si on arrive sur l'étape 9 (Déploiement), mettre à jour le résumé
      if (stepNumber === 9) {
        updateDeploySummary();
      }

      // Si on arrive sur l'étape 10 (Récapitulatif)
      if (stepNumber === 10) {
        buildRecapCards();
      }

      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function validateStep(step) {
      if (step === 3) {
        const fqdn = document.getElementById("net_fqdn").value.trim();
        if (!fqdn) {
          alert("Veuillez renseigner un nom de domaine public (FQDN) pour continuer.");
          document.getElementById("net_fqdn").focus();
          return false;
        }
        const tlsMode = document.getElementById("net_tls_mode").value;
        const email = document.getElementById("net_acme_email").value.trim();
        if (tlsMode.startsWith("letsencrypt") && (!email || !email.includes("@"))) {
          alert("Veuillez renseigner une adresse email ACME valide pour Let's Encrypt.");
          document.getElementById("net_acme_email").focus();
          return false;
        }
      } else if (step === 4) {
        const key = document.getElementById("llm_key").value.trim();
        if (!key || key.startsWith("sk-or-v1-xxxx")) {
          alert("Veuillez renseigner votre clé d'API OpenRouter réelle pour joindre les modèles d'inférence.");
          document.getElementById("llm_key").focus();
          return false;
        }
      }
      return true;
    }

    function toggleK8sMode() {
      const mode = document.getElementById("k8s_mode").value;
      document.getElementById("k8s_local_block").style.display = (mode === "local") ? "block" : "none";
      document.getElementById("k8s_ssh_block").style.display = (mode === "remote-ssh") ? "block" : "none";
    }

    function selectContextFromList() {
      const val = document.getElementById("k8s_context_select").value;
      if (val) {
        document.getElementById("k8s_context").value = val;
      }
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
        console.error("Erreur génération de secret:", err);
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
        alert("Erreur de communication : " + err.message);
      }
    }

    function updateDeploySummary() {
      const cfg = collectFormData();
      const fqdn = cfg.network.public_fqdn || "Non renseigné";
      const mode = cfg.kubernetes.mode;
      const sso = cfg.entra_id_sso.enabled ? "Activé" : "Désactivé";
      const teams = cfg.teams_bot.enabled ? "Activé" : "Désactivé";
      const omni = cfg.omniroute.enabled ? "Activé" : "Désactivé";

      document.getElementById("deploySummaryText").innerHTML = `
        <strong>Récapitulatif de la cible de déploiement :</strong><br>
        • Domaine FQDN : <strong>https://${fqdn}/</strong><br>
        • Kubernetes : Mode <strong>${mode}</strong> | Namespace : <strong>${cfg.kubernetes.namespace}</strong><br>
        • Modules optionnels : SSO Entra ID (<strong>${sso}</strong>) | Bot Teams (<strong>${teams}</strong>) | OmniRoute (<strong>${omni}</strong>)<br>
        • Briques internes automatiques : Presidio DLP, Open-WebUI, Hermes Studio, LiteLLM Proxy, Skills natifs (Ponytail, Graphify, Public-APIs).
      `;
    }

    async function triggerDeployment(dryRun = false) {
      const cfg = collectFormData();
      const btnDeploy = document.getElementById("btnStartDeploy");
      const btnDry = document.getElementById("btnDryRun");
      const badge = document.getElementById("deployStatusBadge");
      const btnGoFinal = document.getElementById("btnGoFinal");

      btnDeploy.disabled = true;
      btnDry.disabled = true;
      badge.textContent = dryRun ? "Simulation en cours..." : "Déploiement en cours...";
      badge.style.color = "var(--accent-cyan)";
      badge.style.borderColor = "var(--accent-cyan)";

      const terminal = document.getElementById("terminalConsole");
      terminal.innerHTML = `<div class="log-line log-cyan">[INITIALISATION] Démarrage du moteur de déploiement universel...</div>`;

      try {
        const res = await fetch("/api/deploy", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ config: cfg, dry_run: dryRun })
        });
        const data = await res.json();
        if (!data.success) {
          terminal.innerHTML += `<div class="log-line log-red">[ERREUR] ${data.error}</div>`;
          btnDeploy.disabled = false;
          btnDry.disabled = false;
          badge.textContent = "Erreur";
          return;
        }

        // Démarrage du polling des logs
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

          // Rendu des logs colorés
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
              setTimeout(() => { goToStep(10); }, 1500);
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
      const fqdn = document.getElementById("net_fqdn").value.trim() || "assistant.example.org";
      return `https://${fqdn}/`;
    }

    function buildRecapCards() {
      const cfg = collectFormData();
      const fqdn = cfg.network.public_fqdn || "assistant.example.org";
      const hermesPass = cfg.hermes.admin_password || "admin";
      const hermesPat = cfg.hermes.api_token || "";
      const grid = document.getElementById("recapAccessGrid");

      let cards = [
        {
          title: "🌐 Portail Collaborateur (Open-WebUI)",
          url: `https://${fqdn}/`,
          desc: "Interface conversationnelle principale d'ArcIA pour l'ensemble des collaborateurs de l'entreprise.",
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

      if (cfg.teams_bot.enabled) {
        cards.push({
          title: "🤖 Webhook Microsoft Teams Bot",
          url: `https://${fqdn}/api/teams/messages`,
          desc: "Point de terminaison de messagerie (Messaging endpoint) configuré dans votre ressource Azure Bot Service.",
          actionText: "Copier l'URL"
        });
      }

      if (cfg.omniroute.enabled) {
        cards.push({
          title: "🔀 Portail Administration OmniRoute",
          url: `http://omniroute.arcia.svc.cluster.local:20129`,
          desc: "Tableau de bord local de gestion multi-fournisseurs accessible au sein du réseau d'entreprise.",
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
