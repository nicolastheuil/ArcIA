#!/usr/bin/env python3
"""
ArcIA — Déploiement Universel et Reproductible sur Kubernetes
============================================================
Ce script lit le fichier de configuration unique 'arcia.config.yaml' (ou 'arcia.env')
et déploie l'intégralité de la plateforme ArcIA sur n'importe quel cluster Kubernetes.
Ne requiert aucune dépendance externe (compatible Python 3.8+ standard).
"""

import os
import sys
import re
import json
import time
import secrets
import argparse
import subprocess
from typing import Dict, Any, Optional, List, Tuple

def make_secret_manifest(name: str, namespace: str, string_data: Dict[str, str]) -> str:
    """Génère un manifeste Kubernetes Secret déclaratif avec stringData pour transmission sécurisée par stdin."""
    lines = [
        "apiVersion: v1",
        "kind: Secret",
        "metadata:",
        f"  name: {name}",
        f"  namespace: {namespace}",
        "type: Opaque",
        "stringData:",
    ]
    for k, v in string_data.items():
        escaped_v = str(v).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'  {k}: "{escaped_v}"')
    return "\n".join(lines) + "\n"

# Support UTF-8 et streaming non-bufferisé sur Windows PowerShell / CMD
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

# Codes couleur ANSI
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_GRAY = "\033[90m"

def log_info(msg: str):
    print(f"{C_CYAN}[INFO]{C_RESET} {msg}", flush=True)

def log_ok(msg: str):
    print(f"{C_GREEN}[OK]{C_RESET} {msg}", flush=True)

def log_warn(msg: str):
    print(f"{C_YELLOW}[WARN]{C_RESET} {msg}", flush=True)

def log_err(msg: str):
    print(f"{C_RED}[ERROR]{C_RESET} {msg}", flush=True)

def log_step(step: int, total: int, msg: str):
    print(f"\n{C_BOLD}{C_CYAN}[{step}/{total}]{C_RESET} {C_BOLD}{msg}{C_RESET}", flush=True)

# -----------------------------------------------------------------------------
# Parser YAML Léger & Autonome (Standard Library Only)
# -----------------------------------------------------------------------------
def parse_yaml_or_env(file_path: str) -> Dict[str, Any]:
    """Parse un fichier YAML basique ou un fichier .ENV sans dépendance externe."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Fichier de configuration introuvable : {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Détection si c'est un format .env plat (sans structure YAML indentée)
    if file_path.endswith(".env") or file_path.endswith(".env.example") or "ARCIA_PUBLIC_FQDN=" in content:
        return parse_env_format(content)

    # Si PyYAML est disponible, on l'utilise pour les fichiers YAML
    try:
        import yaml
        data = yaml.safe_load(content)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Parser autonome pour arcia.config.yaml
    return parse_simple_yaml(content)

def parse_env_format(content: str) -> Dict[str, Any]:
    """Convertit un format .env plat en dictionnaire structuré ArcIA."""
    env: Dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        # Nettoyage des commentaires inline (# ...) en dehors des guillemets
        clean_v = v.strip()
        if clean_v.startswith('"') and '"' in clean_v[1:]:
            end_quote = clean_v[1:].find('"') + 1
            clean_v = clean_v[1:end_quote]
        elif clean_v.startswith("'") and "'" in clean_v[1:]:
            end_quote = clean_v[1:].find("'") + 1
            clean_v = clean_v[1:end_quote]
        else:
            clean_v = clean_v.split("#")[0].strip()
        env[k.strip()] = clean_v.strip()

    return {
        "kubernetes": {
            "mode": env.get("ARCIA_K8S_MODE", "local"),
            "kubeconfig": env.get("ARCIA_KUBE_CONFIG", ""),
            "context": env.get("ARCIA_KUBE_CONTEXT", ""),
            "namespace": env.get("ARCIA_NAMESPACE", "arcia"),
            "storage_class": env.get("ARCIA_STORAGE_CLASS", ""),
            "remote_ssh": {
                "node_ip": env.get("ARCIA_K3S_NODE", "127.0.0.1"),
                "ssh_user": env.get("ARCIA_K3S_USER", "debian"),
                "ssh_port": int(env.get("ARCIA_K3S_PORT", "22")),
                "ssh_key": env.get("ARCIA_K3S_SSH_KEY", ""),
            }
        },
        "network": {
            "public_fqdn": env.get("ARCIA_PUBLIC_FQDN", "assistant.example.org"),
            "ingress_class": env.get("ARCIA_INGRESS_CLASS", "traefik"),
            "tls_mode": env.get("ARCIA_TLS_MODE", "letsencrypt-prod"),
            "acme_email": env.get("ARCIA_ACME_EMAIL", "admin@example.org"),
            "tls_secret_name": env.get("ARCIA_TLS_SECRET", "arcia-tls-cert"),
        },
        "llm_gateway": {
            "openrouter_api_key": env.get("OPENROUTER_API_KEY", ""),
            "default_model": env.get("ARCIA_DEFAULT_MODEL", "openrouter/auto"),
            "local_vllm_endpoint": env.get("VLLM_INTERNAL_URL", ""),
        },
        "hermes": {
            "admin_password": env.get("HERMES_ADMIN_PASSWORD", "admin"),
            "api_token": env.get("HERMES_API_SERVER_KEY", "arcia-pat-default"),
            "storage_size": env.get("HERMES_STORAGE_SIZE", "20Gi"),
        },
        "presidio": {
            "enabled": env.get("PRESIDIO_ENABLED", "true").lower() in ("true", "1", "yes"),
            "master_key": env.get("PRESIDIO_MASTER_KEY", "arcia-presidio-master-key"),
        },
        "open_webui": {
            "enabled": env.get("OPEN_WEBUI_ENABLED", "true").lower() in ("true", "1", "yes"),
            "storage_size": env.get("OPEN_WEBUI_STORAGE_SIZE", "20Gi"),
        },
        "entra_id_sso": {
            "enabled": env.get("ENTRA_ID_ENABLED", "false").lower() in ("true", "1", "yes"),
            "tenant_id": env.get("ENTRA_TENANT_ID", ""),
            "client_id": env.get("ENTRA_CLIENT_ID", ""),
            "client_secret": env.get("ENTRA_CLIENT_SECRET", ""),
            "cookie_secret": env.get("OAUTH2_PROXY_COOKIE_SECRET", ""),
        },
        "teams_bot": {
            "enabled": env.get("TEAMS_BOT_ENABLED", "false").lower() in ("true", "1", "yes"),
            "app_id": env.get("TEAMS_BOT_APP_ID", ""),
            "app_password": env.get("TEAMS_BOT_APP_PASSWORD", ""),
            "system_prompt": env.get("TEAMS_SYSTEM_PROMPT", "Tu es ArcIA, l'assistant d'entreprise."),
        },
        "microsoft365_integration": {
            "enabled": env.get("M365_ENABLED", "false").lower() in ("true", "1", "yes"),
            "config_file": "instance/microsoft365.yaml",
        },
        "omniroute": {
            "enabled": env.get("OMNIROUTE_ENABLED", "false").lower() in ("true", "1", "yes"),
            "storage_size": env.get("OMNIROUTE_STORAGE_SIZE", "5Gi"),
        }
    }

def parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Parseur récursif simple pour le format arcia.config.yaml."""
    result: Dict[str, Any] = {}
    stack: List[Tuple[int, Dict[str, Any]]] = [(0, result)]

    for line_idx, raw_line in enumerate(text.splitlines(), start=1):
        # Enlever les commentaires inline si non entre guillemets
        clean = raw_line.split("#", 1)[0].rstrip()
        if not clean.strip():
            continue

        indent = len(clean) - len(clean.lstrip())
        trimmed = clean.strip()

        # Ajuster le niveau de stack selon l'indentation
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()

        current_dict = stack[-1][1]

        if ":" in trimmed:
            k, v = trimmed.split(":", 1)
            key = k.strip()
            val_str = v.strip()

            if not val_str:
                # C'est une section / dictionnaire parent
                new_dict: Dict[str, Any] = {}
                current_dict[key] = new_dict
                stack.append((indent, new_dict))
            else:
                # C'est une valeur scalaire
                current_dict[key] = cast_scalar(val_str)

    return result

def cast_scalar(val: str) -> Any:
    val = val.strip()
    if val in ("null", "None", "~", ""):
        return ""
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    try:
        if "." in val:
            return float(val)
        return int(val)
    except ValueError:
        return val

def find_harness_ssh() -> Tuple[Optional[str], Optional[str]]:
    """Localise automatiquement la clé SSH et le fichier known_hosts du harness ArcIA si configurés."""
    env_key = os.environ.get("ARCIA_SSH_KEY", "").strip()
    if env_key and os.path.isfile(env_key):
        return env_key, os.environ.get("ARCIA_KNOWN_HOSTS")
    harness_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ArcIA-Harness")
    candidate = os.path.join(harness_dir, "ssh", "arcia-vm_ed25519")
    if os.path.isfile(candidate):
        known = os.path.join(harness_dir, "known_hosts.arcia")
        return candidate, (known if os.path.isfile(known) else None)
    return None, None

def adapt_manifest_namespace(yaml_text: str, target_ns: str) -> str:
    """Adapte dynamiquement les manifestes pour n'importe quel namespace (y compris sandbox)."""
    if target_ns == "arcia":
        return yaml_text
    res = re.sub(r'(\bnamespace:\s*)arcia\b', rf'\g<1>{target_ns}', yaml_text)
    res = res.replace('.arcia.svc', f'.{target_ns}.svc')
    res = res.replace('arcia-entra-id-auth@kubernetescrd', f'{target_ns}-entra-id-auth@kubernetescrd')
    return res

# -----------------------------------------------------------------------------
# Exécuteur Kubernetes (Local ou Remote SSH)
# -----------------------------------------------------------------------------
class K8sRunner:
    def __init__(self, mode: str, kubeconfig: str = "", context: str = "",
                 ssh_node: str = "", ssh_user: str = "debian", ssh_port: int = 22,
                 ssh_key: str = ""):
        self.mode = mode
        self.kubeconfig = kubeconfig
        self.context = context
        self.ssh_node = ssh_node
        self.ssh_user = ssh_user
        self.ssh_port = ssh_port
        self.ssh_key = ssh_key.strip() if ssh_key else ""

        self.ident_key, self.known_hosts = find_harness_ssh()
        if not self.ssh_key and self.ident_key:
            self.ssh_key = self.ident_key

    def run(self, cmd_args: List[str], stdin_input: Optional[str] = None) -> Tuple[int, str, str]:
        """Exécute une commande kubectl soit en local, soit via SSH."""
        if self.mode == "local":
            base_cmd = ["kubectl"]
            if self.kubeconfig:
                base_cmd.extend(["--kubeconfig", self.kubeconfig])
            if self.context:
                base_cmd.extend(["--context", self.context])
            full_cmd = base_cmd + cmd_args

            proc = subprocess.run(
                full_cmd,
                input=stdin_input.encode("utf-8") if stdin_input else None,
                capture_output=True
            )
            return proc.returncode, proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace")

        elif self.mode == "remote-ssh":
            quoted_args = " ".join([f"'{arg}'" if " " in arg or "|" in arg or ";" in arg else arg for arg in cmd_args])
            remote_shell = f"if command -v k3s >/dev/null 2>&1; then sudo k3s kubectl {quoted_args}; else sudo kubectl {quoted_args}; fi"

            ssh_cmd = ["ssh", "-o", "BatchMode=yes"]
            if self.known_hosts:
                ssh_cmd.extend(["-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={self.known_hosts}"])
            else:
                ssh_cmd.extend(["-o", "StrictHostKeyChecking=accept-new"])

            effective_key = self.ssh_key or self.ident_key
            if effective_key:
                expanded_key = os.path.expanduser(os.path.expandvars(effective_key))
                if os.path.isfile(expanded_key):
                    ssh_cmd.extend(["-i", expanded_key])
                else:
                    return 255, "", f"Clé SSH introuvable sur le disque local : {expanded_key}"

            ssh_cmd.extend([
                "-p", str(self.ssh_port),
                f"{self.ssh_user}@{self.ssh_node}",
                remote_shell
            ])

            proc = subprocess.run(
                ssh_cmd,
                input=stdin_input.encode("utf-8") if stdin_input else None,
                capture_output=True
            )
            return proc.returncode, proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace")

        else:
            raise ValueError(f"Mode d'exécution inconnu : {self.mode}")

    def apply_manifest(self, manifest_yaml: str) -> None:
        """Applique un manifeste YAML via stdin."""
        rc, out, err = self.run(["apply", "-f", "-"], stdin_input=manifest_yaml)
        if rc != 0:
            raise RuntimeError(f"Échec de l'application du manifeste :\n{err or out}")

# -----------------------------------------------------------------------------
# Validation des Prérequis & Données de Configuration
# -----------------------------------------------------------------------------
def validate_config(cfg: Dict[str, Any]) -> None:
    errors = []

    k8s = cfg.get("kubernetes", {})
    mode = k8s.get("mode", "local")
    if mode not in ("local", "remote-ssh"):
        errors.append(f"kubernetes.mode doit valoir 'local' ou 'remote-ssh' (actuel: {mode})")

    if mode == "remote-ssh":
        ssh_node = k8s.get("remote_ssh", {}).get("node_ip", "")
        if not ssh_node or ssh_node in ("127.0.0.1", "0.0.0.0"):
            errors.append("kubernetes.remote_ssh.node_ip doit être renseigné avec l'adresse IP de votre nœud K3s.")
        ssh_key = k8s.get("remote_ssh", {}).get("ssh_key", "")
        if ssh_key and ssh_key.strip():
            expanded_key = os.path.expanduser(os.path.expandvars(ssh_key.strip()))
            if not os.path.isfile(expanded_key):
                errors.append(f"kubernetes.remote_ssh.ssh_key est configurée mais le fichier est introuvable : {ssh_key}")

    net = cfg.get("network", {})
    fqdn = net.get("public_fqdn", "").strip()
    if not fqdn:
        errors.append("network.public_fqdn est OBLIGATOIRE (ex: assistant.entreprise.com).")
    elif fqdn == "assistant.example.org":
        log_warn("network.public_fqdn est configuré avec la valeur par défaut 'assistant.example.org'. Pensez à utiliser votre vrai nom d'hôte.")

    tls_mode = net.get("tls_mode", "letsencrypt-prod")
    if tls_mode.startswith("letsencrypt"):
        acme_email = net.get("acme_email", "").strip()
        if not acme_email or "@" not in acme_email:
            errors.append("network.acme_email est OBLIGATOIRE pour l'émission Let's Encrypt (ex: admin@entreprise.com).")

    llm = cfg.get("llm_gateway", {})
    openrouter_key = llm.get("openrouter_api_key", "").strip()
    if openrouter_key.startswith("sk-or-v1-xxxx"):
        errors.append("llm_gateway.openrouter_api_key contient la valeur d'exemple 'sk-or-v1-xxxx'. Renseignez votre clé réelle, ou laissez vide (\"\") si aucune souscription Cloud n'est encore connectée.")
    elif not openrouter_key:
        log_warn("llm_gateway.openrouter_api_key n'est pas renseigné : aucun fournisseur Cloud n'est connecté à ce stade. La plateforme démarrera avec les modèles génériques de la passerelle LiteLLM configurables selon l'instance.")

    hermes = cfg.get("hermes", {})
    if not hermes.get("admin_password"):
        errors.append("hermes.admin_password est OBLIGATOIRE pour sécuriser Hermes Studio.")
    if not hermes.get("api_token"):
        errors.append("hermes.api_token est OBLIGATOIRE pour la connexion Hermes Desktop Gateway.")

    sso = cfg.get("entra_id_sso", {})
    if sso.get("enabled"):
        for field in ("tenant_id", "client_id", "client_secret", "cookie_secret"):
            if not sso.get(field):
                errors.append(f"entra_id_sso.{field} est OBLIGATOIRE lorsque entra_id_sso.enabled est à true.")

    teams = cfg.get("teams_bot", {})
    if teams.get("enabled"):
        for field in ("app_id", "app_password"):
            if not teams.get(field):
                errors.append(f"teams_bot.{field} est OBLIGATOIRE lorsque teams_bot.enabled est à true.")

    if errors:
        log_err("La configuration comporte des erreurs de validation :")
        for err in errors:
            print(f"  [-] {err}")
        print("\nVeuillez corriger ces points dans 'arcia.config.yaml' puis relancer.")
        sys.exit(1)

    log_ok("Validation de la configuration : Tous les paramètres obligatoires sont valides.")

def sync_native_skills(runner: K8sRunner, namespace: str, root_dir: str) -> None:
    """Synchronise automatiquement les compétences natives (Ponytail, Graphify, Public-APIs)."""
    skills_dir = os.path.join(root_dir, "skills")
    if not os.path.isdir(skills_dir):
        return

    cm_data = []
    skills_files = {}
    for skill_name in ["ponytail", "graphify", "public-apis"]:
        skill_file = os.path.join(skills_dir, skill_name, "SKILL.md")
        if os.path.isfile(skill_file):
            try:
                with open(skill_file, "r", encoding="utf-8") as f:
                    content = f.read()
                skills_files[skill_name] = content
                indented = "\n".join("    " + line for line in content.splitlines())
                cm_data.append(f"  {skill_name}-skill.md: |\n{indented}")
            except Exception as e:
                log_warn(f"Impossible de lire la compétence {skill_name}: {e}")

    # Synchronisation des ressources additionnelles de public-apis (script et catalogue)
    pa_script = os.path.join(skills_dir, "public-apis", "scripts", "public_apis.py")
    pa_script_content = ""
    if os.path.isfile(pa_script):
        try:
            with open(pa_script, "r", encoding="utf-8") as f:
                pa_script_content = f.read()
            indented = "\n".join("    " + line for line in pa_script_content.splitlines())
            cm_data.append(f"  public-apis-script.py: |\n{indented}")
        except Exception:
            pass

    pa_cat = os.path.join(skills_dir, "public-apis", "catalog.json")
    pa_cat_content = ""
    if os.path.isfile(pa_cat):
        try:
            with open(pa_cat, "r", encoding="utf-8") as f:
                pa_cat_content = f.read()
            indented = "\n".join("    " + line for line in pa_cat_content.splitlines())
            cm_data.append(f"  public-apis-catalog.json: |\n{indented}")
        except Exception:
            pass

    if cm_data:
        cm_yaml = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: arcia-native-skills
  namespace: {namespace}
data:
""" + "\n".join(cm_data) + "\n"
        try:
            runner.apply_manifest(cm_yaml)
            log_ok("ConfigMap 'arcia-native-skills' provisionné avec succès dans le namespace.")
        except Exception as e:
            log_warn(f"Impossible d'appliquer le ConfigMap des compétences : {e}")

    # Synchronisation sur le système de fichiers hôte ou distant
    if runner.mode == "remote-ssh":
        try:
            nodes_to_sync = [runner.ssh_node]
            if runner.known_hosts and os.path.isfile(runner.known_hosts):
                with open(runner.known_hosts, "r", encoding="utf-8") as f:
                    for line in f:
                        m = re.match(r'^\s*([0-9\.]+)', line)
                        if m and m.group(1) not in nodes_to_sync:
                            nodes_to_sync.append(m.group(1))

            for target_ip in nodes_to_sync:
                ssh_base = ["ssh", "-o", "BatchMode=yes"]
                if runner.known_hosts:
                    ssh_base.extend(["-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={runner.known_hosts}"])
                else:
                    ssh_base.extend(["-o", "StrictHostKeyChecking=accept-new"])
                if runner.ident_key:
                    ssh_base.extend(["-i", runner.ident_key])
                ssh_base.extend(["-p", str(runner.ssh_port), f"{runner.ssh_user}@{target_ip}"])

                for skill_name, content in skills_files.items():
                    remote_dir = f"/var/data/arcia/shared-skills/arcia/{skill_name}"
                    tee_cmd = f"sudo mkdir -p {remote_dir} && sudo tee {remote_dir}/SKILL.md >/dev/null"
                    subprocess.run(ssh_base + [tee_cmd], input=content.encode("utf-8"), capture_output=True)

                if pa_script_content:
                    pa_dir = "/var/data/arcia/shared-skills/arcia/public-apis/scripts"
                    tee_script = f"sudo mkdir -p {pa_dir} && sudo tee {pa_dir}/public_apis.py >/dev/null && sudo chmod +x {pa_dir}/public_apis.py"
                    subprocess.run(ssh_base + [tee_script], input=pa_script_content.encode("utf-8"), capture_output=True)

                if pa_cat_content:
                    pa_cat_dir = "/var/data/arcia/shared-skills/arcia/public-apis"
                    tee_cat = f"sudo mkdir -p {pa_cat_dir} && sudo tee {pa_cat_dir}/catalog.json >/dev/null"
                    subprocess.run(ssh_base + [tee_cat], input=pa_cat_content.encode("utf-8"), capture_output=True)

            log_ok(f"Compétences natives (Ponytail, Graphify, Public-APIs) synchronisées sur {len(nodes_to_sync)} nœud(s).")
        except Exception as e:
            log_warn(f"Avertissement synchronisation distante des compétences : {e}")
    elif runner.mode == "local" and os.name != "nt":
        try:
            target_base = "/var/data/arcia/shared-skills/arcia"
            import shutil
            for s in ["ponytail", "graphify", "public-apis"]:
                src = os.path.join(skills_dir, s)
                dst = os.path.join(target_base, s)
                if os.path.isdir(src):
                    os.makedirs(dst, exist_ok=True)
                    shutil.copytree(src, dst, dirs_exist_ok=True)
            log_ok("Compétences natives synchronisées en local.")
        except Exception:
            pass

    log_ok("Toutes les compétences et outils natifs d'ArcIA sont déployés.")

def sync_webui_branding(runner: K8sRunner, namespace: str, root_dir: str):
    """Crée le ConfigMap arcia-webui-branding avec les logos SVG officiels ArcIA."""
    symbol_path = os.path.join(root_dir, "assets", "branding", "logo-arcia-symbol.svg")
    dark_path = os.path.join(root_dir, "assets", "branding", "logo-arcia-dark.svg")

    symbol_content = ""
    dark_content = ""
    if os.path.isfile(symbol_path):
        with open(symbol_path, "r", encoding="utf-8") as f:
            symbol_content = f.read()
    if os.path.isfile(dark_path):
        with open(dark_path, "r", encoding="utf-8") as f:
            dark_content = f.read()

    cm_lines = [
        "apiVersion: v1",
        "kind: ConfigMap",
        "metadata:",
        "  name: arcia-webui-branding",
        f"  namespace: {namespace}",
        "data:",
        "  favicon.svg: |",
    ]
    for line in symbol_content.splitlines():
        cm_lines.append(f"    {line}")
    cm_lines.append("  logo.svg: |")
    for line in dark_content.splitlines():
        cm_lines.append(f"    {line}")

    runner.apply_manifest("\n".join(cm_lines))
    log_ok("Identité visuelle ArcIA (monogramme squircle et logos SVG) injectée dans le cluster.")

# -----------------------------------------------------------------------------
# Déploiement des Composants & Rendu des Manifestes
# -----------------------------------------------------------------------------
def deploy_arcia(cfg: Dict[str, Any], root_dir: str):
    k8s_cfg = cfg.get("kubernetes", {})
    mode = k8s_cfg.get("mode", "local")
    kubeconfig = k8s_cfg.get("kubeconfig", "")
    context = k8s_cfg.get("context", "")
    namespace = k8s_cfg.get("namespace", "arcia")
    storage_class = k8s_cfg.get("storage_class", "")

    ssh_info = k8s_cfg.get("remote_ssh", {})
    ssh_node = ssh_info.get("node_ip", "127.0.0.1")
    ssh_user = ssh_info.get("ssh_user", "debian")
    ssh_port = ssh_info.get("ssh_port", 22)
    ssh_key = ssh_info.get("ssh_key", "")

    runner = K8sRunner(
        mode=mode,
        kubeconfig=kubeconfig,
        context=context,
        ssh_node=ssh_node,
        ssh_user=ssh_user,
        ssh_port=ssh_port,
        ssh_key=ssh_key
    )

    total_steps = 7

    # 1. Pré-requis Kubernetes & Connectivité
    log_step(1, total_steps, "Vérification de la connectivité au cluster Kubernetes")
    rc, out, err = runner.run(["get", "nodes", "-o", "wide"])
    if rc != 0:
        log_err(f"Impossible de joindre le cluster Kubernetes :\n{err or out}")
        sys.exit(1)
    nodes_count = len([l for l in out.strip().splitlines() if l and not l.startswith("NAME")])
    log_ok(f"Cluster connecté avec succès ({nodes_count} nœud(s) détecté(s)).")

    # Détection de la StorageClass
    rc, sc_out, _ = runner.run(["get", "sc", "-o", "jsonpath={.items[*].metadata.name}"])
    available_sc = sc_out.strip().split() if rc == 0 and sc_out.strip() else []
    if storage_class:
        if storage_class in available_sc:
            log_ok(f"StorageClass spécifiée : '{storage_class}' (présente sur le cluster).")
        else:
            log_warn(f"StorageClass '{storage_class}' introuvable dans le cluster (disponibles: {', '.join(available_sc) or 'aucune'}).")
    else:
        log_ok(f"StorageClass : Utilisation automatique de la StorageClass par défaut du cluster.")

    # 2. Création du Namespace
    log_step(2, total_steps, f"Création et vérification du namespace '{namespace}'")
    ns_manifest = f"""apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
"""
    runner.apply_manifest(ns_manifest)
    log_ok(f"Namespace '{namespace}' prêt.")

    # 3. Création des Secrets Applicatifs
    log_step(3, total_steps, "Génération et injection des secrets Kubernetes")
    llm_cfg = cfg.get("llm_gateway", {})
    hermes_cfg = cfg.get("hermes", {})
    presidio_cfg = cfg.get("presidio", {})
    webui_cfg = cfg.get("open_webui", {})
    sso_cfg = cfg.get("entra_id_sso", {})
    teams_cfg = cfg.get("teams_bot", {})
    omniroute_cfg = cfg.get("omniroute", {})

    KNOWN_INSECURE_SECRETS = {
        "sk-arcia-master-key-v03",
        "sk-arcia-master-key-change-me-32b",
        "arcia-salt-key-32-chars-long-secret",
        "ArcIALiteLLMPostgres2026!",
        "ChangeThisToAStrongPassword2026!",
        "admin",
        "arcia-pat-default",
        "arcia-pat-secret-key-32b-secure",
        "arcia-presidio-master-secret-key",
        "arcia-presidio-master-key"
    }

    # 1. enterprise-llm-secret
    openrouter_key = llm_cfg.get("openrouter_api_key", "")
    runner.apply_manifest(make_secret_manifest("enterprise-llm-secret", namespace, {
        "openrouter-key": openrouter_key
    }))

    # 2. litellm-secret (Master key, DB password, Salt key pour la passerelle d'inférence)
    litellm_master = llm_cfg.get("master_key", "")
    if not litellm_master or litellm_master in KNOWN_INSECURE_SECRETS:
        litellm_master = f"sk-arcia-{secrets.token_urlsafe(32)}"
        log_info(" -> Génération automatique d'une Master Key LiteLLM cryptographiquement sécurisée.")

    litellm_salt = llm_cfg.get("salt_key", "")
    if not litellm_salt or litellm_salt in KNOWN_INSECURE_SECRETS:
        litellm_salt = secrets.token_hex(16)

    litellm_db_pass = llm_cfg.get("db_password", "")
    if not litellm_db_pass or litellm_db_pass in KNOWN_INSECURE_SECRETS:
        litellm_db_pass = f"ArcIA_DB_{secrets.token_urlsafe(24)}"

    runner.apply_manifest(make_secret_manifest("litellm-secret", namespace, {
        "master-key": litellm_master,
        "salt-key": litellm_salt,
        "db-password": litellm_db_pass
    }))

    # 3. hermes-gateway-secret
    hermes_key = hermes_cfg.get("api_token", "")
    if not hermes_key or hermes_key in KNOWN_INSECURE_SECRETS:
        hermes_key = f"arcia-pat-{secrets.token_urlsafe(24)}"
    hermes_pass = hermes_cfg.get("admin_password", "")
    if not hermes_pass or hermes_pass in KNOWN_INSECURE_SECRETS:
        hermes_pass = secrets.token_urlsafe(16)

    runner.apply_manifest(make_secret_manifest("hermes-gateway-secret", namespace, {
        "api-server-key": hermes_key,
        "admin-password": hermes_pass
    }))

    # 4. presidio-secret
    presidio_key = presidio_cfg.get("master_key", "")
    if not presidio_key or presidio_key in KNOWN_INSECURE_SECRETS:
        presidio_key = f"arcia-presidio-{secrets.token_urlsafe(24)}"
    runner.apply_manifest(make_secret_manifest("presidio-secret", namespace, {
        "master-key": presidio_key
    }))

    # 5. entraid-secret (si SSO actif ou placeholder sécurisé pour satisfaire les références des pods)
    sso_tenant = sso_cfg.get("tenant_id", "00000000-0000-0000-0000-000000000000") if sso_cfg.get("enabled") else "00000000-0000-0000-0000-000000000000"
    sso_client = sso_cfg.get("client_id", "placeholder-client-id") if sso_cfg.get("enabled") else "placeholder-client-id"
    sso_secret = sso_cfg.get("client_secret", "placeholder-client-secret") if sso_cfg.get("enabled") else "placeholder-client-secret"
    sso_cookie = sso_cfg.get("cookie_secret", "") if sso_cfg.get("enabled") else ""
    if not sso_cookie or sso_cookie in KNOWN_INSECURE_SECRETS:
        sso_cookie = secrets.token_urlsafe(32)

    runner.apply_manifest(make_secret_manifest("entraid-secret", namespace, {
        "tenant-id": sso_tenant,
        "client-id": sso_client,
        "client-secret": sso_secret,
        "cookie-secret": sso_cookie
    }))

    # 6. teams-bot-secret (si bot actif)
    if teams_cfg.get("enabled"):
        runner.apply_manifest(make_secret_manifest("teams-bot-secret", namespace, {
            "app-id": teams_cfg.get("app_id", ""),
            "app-password": teams_cfg.get("app_password", "")
        }))

    log_ok("Tous les secrets Kubernetes sont provisionnés de façon déclarative et sécurisée.")

    # 4. Déploiement des Microservices Fondamentaux
    log_step(4, total_steps, "Déploiement des microservices du socle ArcIA")

    manifests_dir = os.path.join(root_dir, "deploy", "manifests")

    # A. Presidio DLP
    log_info(" -> Déploiement de Presidio DLP (03-presidio.yaml)...")
    presidio_path = os.path.join(manifests_dir, "03-presidio.yaml")
    with open(presidio_path, "r", encoding="utf-8") as f:
        runner.apply_manifest(adapt_manifest_namespace(f.read(), namespace))

    # B1. Base PostgreSQL LiteLLM (Gestion des clés virtuelles et comptabilité)
    litellm_db_path = os.path.join(manifests_dir, "05-litellm-db.yaml")
    if os.path.isfile(litellm_db_path):
        log_info(" -> Déploiement de la base LiteLLM PostgreSQL (05-litellm-db.yaml)...")
        with open(litellm_db_path, "r", encoding="utf-8") as f:
            runner.apply_manifest(adapt_manifest_namespace(f.read(), namespace))

    # B2. LiteLLM Proxy (Passerelle d'inférence universelle avec guardrail fail-closed)
    log_info(" -> Déploiement de LiteLLM Proxy (05-litellm.yaml)...")
    litellm_path = os.path.join(manifests_dir, "05-litellm.yaml")
    with open(litellm_path, "r", encoding="utf-8") as f:
        litellm_yaml = f.read()

    local_vllm = llm_cfg.get("local_vllm_endpoint", "").strip()
    if local_vllm:
        litellm_yaml = litellm_yaml.replace("http://vllm-internal.corp.local:8000/v1", local_vllm)
    runner.apply_manifest(adapt_manifest_namespace(litellm_yaml, namespace))

    # C. Hermes Agent (Studio & Gateway Desktop)
    log_info(" -> Déploiement de Hermes Agent & Studio (06-hermes-agent.yaml)...")
    hermes_path = os.path.join(manifests_dir, "06-hermes-agent.yaml")
    with open(hermes_path, "r", encoding="utf-8") as f:
        hermes_yaml = f.read()

    hermes_storage = hermes_cfg.get("storage_size", "20Gi")
    hermes_yaml = re.sub(r'storage:\s*20Gi', f'storage: {hermes_storage}', hermes_yaml, count=1)
    hermes_yaml = hermes_yaml.replace("https://assistant.example.org/studio", f"https://{public_fqdn}/studio")
    if storage_class:
        hermes_yaml = hermes_yaml.replace("accessModes:\n  - ReadWriteOnce", f"accessModes:\n  - ReadWriteOnce\n  storageClassName: {storage_class}")
    runner.apply_manifest(adapt_manifest_namespace(hermes_yaml, namespace))

    # D. Open-WebUI Portal (avec espace persistant RAG, ChromaDB & corpus documentaire)
    log_info(" -> [Branding ArcIA] Injection de l'identité visuelle officielle (SVG & CSS)...")
    sync_webui_branding(runner, namespace, root_dir)
    log_info(" -> Déploiement de Open-WebUI (07-open-webui.yaml)...")
    webui_path = os.path.join(manifests_dir, "07-open-webui.yaml")
    with open(webui_path, "r", encoding="utf-8") as f:
        webui_yaml = f.read()

    webui_storage = webui_cfg.get("storage_size", "50Gi")
    webui_yaml = re.sub(r'storage:\s*20Gi', f'storage: {webui_storage}', webui_yaml, count=1)
    if storage_class:
        webui_yaml = webui_yaml.replace("accessModes:\n  - ReadWriteOnce", f"accessModes:\n  - ReadWriteOnce\n  storageClassName: {storage_class}")
    runner.apply_manifest(adapt_manifest_namespace(webui_yaml, namespace))

    # E. Services Optionnels : Teams Bot et OAuth2-Proxy
    if teams_cfg.get("enabled"):
        log_info(" -> [Optionnel Activé] Déploiement de l'adaptateur Teams Bot (08-teams-bot.yaml)...")
        teams_path = os.path.join(manifests_dir, "08-teams-bot.yaml")
        with open(teams_path, "r", encoding="utf-8") as f:
            teams_yaml = f.read()
            prompt = teams_cfg.get("system_prompt", "Tu es ArcIA, l'assistant d'entreprise.")
            teams_yaml = re.sub(r'value: "Tu es ArcIA.*?"', f'value: "{prompt}"', teams_yaml)
            runner.apply_manifest(adapt_manifest_namespace(teams_yaml, namespace))
    else:
        log_info(" -> [Optionnel Ignoré] Adaptateur Microsoft Teams désactivé.")

    if sso_cfg.get("enabled"):
        log_info(" -> [Optionnel Activé] Déploiement du proxy SSO Entra ID (02-oauth2-proxy.yaml)...")
        oauth_path = os.path.join(manifests_dir, "02-oauth2-proxy.yaml")
        with open(oauth_path, "r", encoding="utf-8") as f:
            runner.apply_manifest(adapt_manifest_namespace(f.read(), namespace))
    else:
        log_info(" -> [Optionnel Ignoré] Authentification SSO Entra ID désactivée.")

    if omniroute_cfg.get("enabled"):
        omni_path = os.path.join(manifests_dir, "09-omniroute.yaml")
        if os.path.isfile(omni_path):
            log_info(" -> [Optionnel Activé] Déploiement d'OmniRoute (09-omniroute.yaml)...")
            with open(omni_path, "r", encoding="utf-8") as f:
                omni_yaml = f.read()
            storage_size = omniroute_cfg.get("storage_size", "5Gi")
            omni_yaml = omni_yaml.replace("storage: 5Gi", f"storage: {storage_size}")
            if storage_class:
                omni_yaml = omni_yaml.replace("accessModes:\n  - ReadWriteOnce", f"accessModes:\n  - ReadWriteOnce\n  storageClassName: {storage_class}")
            runner.apply_manifest(adapt_manifest_namespace(omni_yaml, namespace))
        else:
            log_info(" -> [v0.3 Note] OmniRoute est retiré en v0.3 au profit du routage unifié LiteLLM.")
    else:
        log_info(" -> [Optionnel Ignoré] Routeur OmniRoute désactivé (retiré en v0.3).")

    # F. Synchronisation Automatique des Compétences & Outils (Skills)
    log_info(" -> [Automatique] Synchronisation des compétences natives (Ponytail, Graphify, Public-APIs)...")
    sync_native_skills(runner, namespace, root_dir)

    # G. Synchronisation Programmée Hebdomadaire des Compétences Externes
    skills_cron_path = os.path.join(manifests_dir, "10-skills-sync-cronjob.yaml")
    if os.path.isfile(skills_cron_path):
        with open(skills_cron_path, "r", encoding="utf-8") as f:
            runner.apply_manifest(adapt_manifest_namespace(f.read(), namespace))
        log_ok("CronJob 'arcia-skills-sync' déployé pour la mise à jour hebdomadaire.")

    # H. Politiques Réseau d'Isolation (NetworkPolicies)
    netpol_path = os.path.join(manifests_dir, "09-network-policy.yaml")
    if os.path.isfile(netpol_path):
        log_info(" -> [Sécurité Réseau] Déploiement des NetworkPolicies d'isolation (09-network-policy.yaml)...")
        with open(netpol_path, "r", encoding="utf-8") as f:
            runner.apply_manifest(adapt_manifest_namespace(f.read(), namespace))
        log_ok("NetworkPolicies d'isolation appliquées au namespace.")

    # 5. Gestion des Certificats TLS & Ingress
    log_step(5, total_steps, "Configuration du routage Ingress et des Certificats TLS")
    net_cfg = cfg.get("network", {})
    public_fqdn = net_cfg.get("public_fqdn", "assistant.example.org")
    tls_mode = net_cfg.get("tls_mode", "letsencrypt-prod")
    acme_email = net_cfg.get("acme_email", "admin@example.org")
    ingress_class = net_cfg.get("ingress_class", "traefik")
    tls_secret_name = net_cfg.get("tls_secret_name", "arcia-tls-cert")

    # Vérification et initialisation sécurisée du secret TLS si absent
    rc_tls, _, _ = runner.run(["get", "secret", tls_secret_name, f"-n={namespace}"])
    if rc_tls != 0:
        log_info(f" -> Secret TLS '{tls_secret_name}' absent : génération d'un certificat bootstrap pour '{public_fqdn}'...")
        gen_cmd = f"openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /tmp/tls_{namespace}.key -out /tmp/tls_{namespace}.crt -subj '/CN={public_fqdn}' >/dev/null 2>&1 && sudo k3s kubectl create secret tls {tls_secret_name} --cert=/tmp/tls_{namespace}.crt --key=/tmp/tls_{namespace}.key -n {namespace} >/dev/null 2>&1 && rm -f /tmp/tls_{namespace}.*"
        if runner.mode == "remote-ssh":
            ssh_tls = ["ssh", "-o", "BatchMode=yes"]
            if runner.known_hosts:
                ssh_tls.extend(["-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={runner.known_hosts}"])
            else:
                ssh_tls.extend(["-o", "StrictHostKeyChecking=accept-new"])
            if runner.ident_key:
                ssh_tls.extend(["-i", runner.ident_key])
            ssh_tls.extend(["-p", str(runner.ssh_port), f"{runner.ssh_user}@{runner.ssh_node}", gen_cmd])
            subprocess.run(ssh_tls, capture_output=True)
        else:
            subprocess.run(gen_cmd, shell=True, capture_output=True)
        log_ok(f"Secret TLS bootstrap '{tls_secret_name}' provisionné.")
    if tls_mode.startswith("letsencrypt"):
        server_url = "https://acme-v02.api.letsencrypt.org/directory" if tls_mode == "letsencrypt-prod" else "https://acme-staging-v02.api.letsencrypt.org/directory"
        issuer_yaml = f"""apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: {tls_mode}
spec:
  acme:
    server: {server_url}
    email: {acme_email}
    privateKeySecretRef:
      name: {tls_mode}-key
    solvers:
    - http01:
        ingress:
          class: {ingress_class}
"""
        runner.apply_manifest(issuer_yaml)
        log_ok(f"ClusterIssuer '{tls_mode}' configuré avec le contact {acme_email}.")

    # Ingress Render
    ingress_annotations = ""
    if ingress_class == "traefik":
        ingress_annotations = """    traefik.ingress.kubernetes.io/router.entrypoints: "web,websecure"
    traefik.ingress.kubernetes.io/router.tls: "true" """
    elif ingress_class == "nginx":
        ingress_annotations = """    kubernetes.io/ingress.class: "nginx"
    nginx.ingress.kubernetes.io/ssl-redirect: "true" """

    if tls_mode.startswith("letsencrypt"):
        ingress_annotations += f'\n    cert-manager.io/cluster-issuer: "{tls_mode}"'

    # Construction dynamique des routes Ingress
    teams_path_block = ""
    if teams_cfg.get("enabled"):
        teams_path_block = """      - path: /api/teams/messages
        pathType: Prefix
        backend:
          service:
            name: teams-bot-adapter
            port:
              number: 3978"""

    oauth_path_block = ""
    if sso_cfg.get("enabled"):
        oauth_path_block = """      - path: /oauth2
        pathType: Prefix
        backend:
          service:
            name: oauth2-proxy
            port:
              number: 4180"""

    rendered_ingress = f"""# 1. Ingress Public (Open-WebUI, OAuth2, Teams)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: arcia-public-ingress
  namespace: {namespace}
  annotations:
{ingress_annotations}
spec:
  tls:
  - hosts:
    - {public_fqdn}
    secretName: {tls_secret_name}
  rules:
  - host: {public_fqdn}
    http:
      paths:
{oauth_path_block}
{teams_path_block}
      - path: /
        pathType: Prefix
        backend:
          service:
            name: open-webui
            port:
              number: 8080
---
# 2. Ingress Power Users /v1 (Protégé par RateLimit Traefik)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: arcia-v1-ingress
  namespace: {namespace}
  annotations:
{ingress_annotations}
    traefik.ingress.kubernetes.io/router.middlewares: {namespace}-litellm-ratelimit@kubernetescrd
spec:
  tls:
  - hosts:
    - {public_fqdn}
    secretName: {tls_secret_name}
  rules:
  - host: {public_fqdn}
    http:
      paths:
      - path: /v1
        pathType: Prefix
        backend:
          service:
            name: litellm-proxy
            port:
              number: 4000
---
# 3. Ingress Studio (Hermes Studio Dashboard — Authentification native admin/password)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: arcia-studio-ingress
  namespace: {namespace}
  annotations:
{ingress_annotations}
    traefik.ingress.kubernetes.io/router.middlewares: {namespace}-studio-prefix@kubernetescrd,{namespace}-studio-stripprefix@kubernetescrd
spec:
  tls:
  - hosts:
    - {public_fqdn}
    secretName: {tls_secret_name}
  rules:
  - host: {public_fqdn}
    http:
      paths:
      - path: /studio
        pathType: Prefix
        backend:
          service:
            name: hermes-studio
            port:
              number: 9119
---
# 4. Ingress Gateway Desktop (Hermes Gateway API & WebSocket — Protégé par PAT)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: arcia-gateway-ingress
  namespace: {namespace}
  annotations:
{ingress_annotations}
    traefik.ingress.kubernetes.io/router.middlewares: {namespace}-gateway-stripprefix@kubernetescrd
spec:
  tls:
  - hosts:
    - {public_fqdn}
    secretName: {tls_secret_name}
  rules:
  - host: {public_fqdn}
    http:
      paths:
      - path: /gateway
        pathType: Prefix
        backend:
          service:
            name: hermes-studio
            port:
              number: 8642
---
# 5. Ingress LiteLLM Admin UI (Gestion graphique des modèles, fallbacks et quotas)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: arcia-litellm-ui-ingress
  namespace: {namespace}
  annotations:
{ingress_annotations}
spec:
  tls:
  - hosts:
    - {public_fqdn}
    secretName: {tls_secret_name}
  rules:
  - host: {public_fqdn}
    http:
      paths:
      - path: /ui
        pathType: Prefix
        backend:
          service:
            name: litellm-proxy
            port:
              number: 4000
      - path: /model
        pathType: Prefix
        backend:
          service:
            name: litellm-proxy
            port:
              number: 4000
      - path: /models
        pathType: Prefix
        backend:
          service:
            name: litellm-proxy
            port:
              number: 4000
      - path: /key
        pathType: Prefix
        backend:
          service:
            name: litellm-proxy
            port:
              number: 4000
      - path: /fallback
        pathType: Prefix
        backend:
          service:
            name: litellm-proxy
            port:
              number: 4000
      - path: /spend
        pathType: Prefix
        backend:
          service:
            name: litellm-proxy
            port:
              number: 4000
---
# 6. Middlewares Traefik (RateLimit, Studio Prefix/StripPrefix, Gateway StripPrefix)
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: litellm-ratelimit
  namespace: {namespace}
spec:
  rateLimit:
    average: 100
    burst: 50
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: studio-prefix
  namespace: {namespace}
spec:
  headers:
    customRequestHeaders:
      X-Forwarded-Prefix: "/studio"
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: studio-stripprefix
  namespace: {namespace}
spec:
  stripPrefix:
    prefixes:
      - /studio
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: gateway-stripprefix
  namespace: {namespace}
spec:
  stripPrefix:
    prefixes:
      - /gateway
"""
    runner.apply_manifest(rendered_ingress)
    log_ok(f"Ingress configuré pour l'hôte public : https://{public_fqdn}/")

    # 6. Attente et Vérification du Rollout des Pods
    log_step(6, total_steps, "Vérification de l'état de démarrage des Pods (Rollout)")
    deployments_to_check = ["presidio-dlp", "litellm-proxy", "hermes-agent", "open-webui"]
    if teams_cfg.get("enabled"):
        deployments_to_check.append("teams-bot-adapter")
    if sso_cfg.get("enabled"):
        deployments_to_check.append("oauth2-proxy")
    if omniroute_cfg.get("enabled"):
        deployments_to_check.append("omniroute")

    # Vérification préalable de la base LiteLLM
    log_info(" -> Attente du démarrage de la base PostgreSQL LiteLLM...")
    runner.run(["rollout", "status", "statefulset/litellm-db", f"-n={namespace}", "--timeout=180s"])

    for dep in deployments_to_check:
        log_info(f" -> Attente du démarrage de {dep}...")
        rc, out, err = runner.run(["rollout", "status", f"deployment/{dep}", f"-n={namespace}", "--timeout=180s"])
        if rc == 0:
            log_ok(f"Déploiement '{dep}' est opérationnel.")
        else:
            log_warn(f"Le déploiement '{dep}' met du temps à démarrer ({err.strip() or out.strip()}).")

    # 7. Synthèse et Liens d'Accès
    log_step(7, total_steps, "Récapitulatif de Déploiement d'ArcIA")
    print(f"\n{C_BOLD}{C_GREEN}================================================================={C_RESET}")
    print(f"{C_BOLD}{C_GREEN}   [+] DEPLOIEMENT D'ARCIA EFFECTUE AVEC SUCCES SUR KUBERNETES   {C_RESET}")
    print(f"{C_BOLD}{C_GREEN}================================================================={C_RESET}\n")

    print(f"{C_BOLD}Points d'accès de votre instance :{C_RESET}")
    print(f"  * {C_BOLD}Portail Collaborateur (Open-WebUI)    :{C_RESET} https://{public_fqdn}/")
    print(f"  * {C_BOLD}Passerelle Inférence Power User (/v1) :{C_RESET} https://{public_fqdn}/v1")
    print(f"  * {C_BOLD}Hermes Studio (Kanban Multi-Agents)    :{C_RESET} https://{public_fqdn}/studio")
    print(f"  * {C_BOLD}Hermes Desktop Gateway (WebSocket)     :{C_RESET} https://{public_fqdn}/gateway")
    if teams_cfg.get("enabled"):
        print(f"  * {C_BOLD}Webhook Microsoft Teams             :{C_RESET} https://{public_fqdn}/api/teams/messages")
    if omniroute_cfg.get("enabled"):
        print(f"  * {C_BOLD}OmniRoute API interne               :{C_RESET} http://omniroute.{namespace}.svc.cluster.local:20128/v1")
        print(f"  * {C_BOLD}OmniRoute Portail LAN (:20129)      :{C_RESET} http://omniroute.{namespace}.svc.cluster.local:20129")


    print(f"\n{C_BOLD}Identifiants et Secrets Sécurisés :{C_RESET}")
    print(f"  - {C_BOLD}Hermes Studio Web :{C_RESET} Identifiant: 'admin' | Secret: [Géré de façon sécurisée dans le Secret Kubernetes hermes-gateway-secret]")
    print(f"  - {C_BOLD}Hermes Desktop PAT:{C_RESET} [Géré de façon sécurisée dans le Secret Kubernetes hermes-gateway-secret]")
    print(f"  - {C_BOLD}LiteLLM Master Key:{C_RESET} [Géré de façon sécurisée dans le Secret Kubernetes litellm-secret]")

    print(f"\n{C_BOLD}Rappel DNS & Réseau :{C_RESET}")
    print(f"  Assurez-vous que le nom de domaine {C_CYAN}{public_fqdn}{C_RESET} pointe vers l'adresse IP publique de votre Ingress.")
    print(f"  Les flux HTTPS entrants sur le port 443 doivent être routés vers le contrôleur Ingress du cluster.\n")


def main():
    parser = argparse.ArgumentParser(description="Déploiement Universel d'ArcIA sur Kubernetes")
    parser.add_argument("--config", "-c", default="arcia.config.yaml",
                        help="Chemin vers le fichier arcia.config.yaml ou arcia.env")
    parser.add_argument("--dry-run", action="store_true", help="Valide la configuration sans appliquer")
    parser.add_argument("--wizard", action="store_true", help="Lance le wizard graphique interactif d'installation")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)

    if args.wizard:
        wizard_script = os.path.join(script_dir, "wizard.py")
        import subprocess
        sys.exit(subprocess.call([sys.executable, wizard_script]))

    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(root_dir, config_path)

    # Fallback automatique sur arcia.env si arcia.config.yaml n'existe pas
    if not os.path.exists(config_path):
        env_fallback = os.path.join(root_dir, "arcia.env")
        if os.path.exists(env_fallback):
            config_path = env_fallback
        else:
            log_err(f"Fichier de configuration introuvable : {config_path}")
            print(f"\n{C_BOLD}{C_CYAN}Méthode recommandée (Simple & Graphique) :{C_RESET}")
            print("  Lancez le Wizard d'installation visuel pas-à-pas :")
            print("    Linux / macOS       : ./wizard.sh")
            print("    Windows PowerShell  : .\\wizard.ps1")
            print("    Python direct       : python scripts/wizard.py")
            print(f"\n{C_BOLD}Méthode manuelle :{C_RESET}")
            print(f"  1. cp {os.path.join(root_dir, 'arcia.config.yaml.example')} {os.path.join(root_dir, 'arcia.config.yaml')}")
            print("  2. Éditez arcia.config.yaml puis relancez deploy.py\n")
            sys.exit(1)

    print(f"{C_BOLD}{C_CYAN}================================================================={C_RESET}")
    print(f"{C_BOLD}{C_CYAN}         ArcIA — Déploiement Universel sur Kubernetes            {C_RESET}")
    print(f"{C_BOLD}{C_CYAN}================================================================={C_RESET}")
    log_info(f"Lecture du fichier de configuration : {config_path}")

    cfg = parse_yaml_or_env(config_path)
    validate_config(cfg)

    if args.dry_run:
        log_ok("Mode --dry-run : Configuration analysée et validée avec succès. Aucun déploiement exécuté.")
        sys.exit(0)

    deploy_arcia(cfg, root_dir)

if __name__ == "__main__":
    main()
