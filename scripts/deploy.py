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
import base64
import secrets
import hashlib
import argparse
import subprocess
import textwrap
import tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.open_webui.branding import build_mapping
from typing import Dict, Any, Optional, List, Tuple

def make_secret_manifest(name: str, namespace: str, string_data: Dict[str, str], secret_type: str = "Opaque") -> str:
    """Génère un manifeste Kubernetes Secret déclaratif avec stringData pour transmission sécurisée par stdin."""
    lines = [
        "apiVersion: v1",
        "kind: Secret",
        "metadata:",
        f"  name: {name}",
        f"  namespace: {namespace}",
        f"type: {secret_type}",
        "stringData:",
    ]
    for k, v in string_data.items():
        str_val = str(v)
        if "\n" in str_val:
            lines.append(f"  {k}: |")
            for subline in str_val.splitlines():
                lines.append(f"    {subline}")
        else:
            escaped_v = str_val.replace("\\", "\\\\").replace('"', '\\"')
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
            "master_key": env.get("LITELLM_MASTER_KEY", ""),
            "salt_key": env.get("LITELLM_SALT_KEY", ""),
            "db_password": env.get("LITELLM_DB_PASSWORD", ""),
            **{f"{p}_api_key": env.get(f"{p.upper()}_API_KEY", "") for p in ("openai", "anthropic", "mistral", "gemini")},
            "default_model": env.get("ARCIA_DEFAULT_MODEL", "simple/auto"),
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
            "tenant_id": env.get("TEAMS_BOT_TENANT_ID", env.get("ENTRA_TENANT_ID", "")),
            "system_prompt": env.get("TEAMS_SYSTEM_PROMPT", "Tu es ArcIA, l'assistant et orchestrateur agentique d'entreprise. Réponds de façon synthétique, professionnelle et structurée en Markdown."),
        },
        "microsoft365_integration": {
            "enabled": env.get("M365_ENABLED", "false").lower() in ("true", "1", "yes"),
            "config_file": "instance/microsoft365.yaml",
        }
    }

def parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Lit les mappings, séquences YAML/JSON et blocs du fichier d'instance sans dépendance."""
    raw_lines = text.splitlines()

    def without_comment(line):
        quote = None
        escaped = False
        for index, char in enumerate(line):
            if escaped:
                escaped = False
            elif char == "\\" and quote == '"':
                escaped = True
            elif quote:
                if char == quote:
                    quote = None
            elif char in ("'", '"'):
                quote = char
            elif char == "#" and (index == 0 or line[index - 1].isspace()):
                return line[:index].rstrip()
        return line.rstrip()

    tokens = []
    for number, raw in enumerate(raw_lines):
        clean = without_comment(raw)
        if clean.strip():
            tokens.append((len(clean) - len(clean.lstrip()), clean.strip(), number))

    def sequence(content):
        return content == "-" or content.startswith("- ")

    def entry(content):
        match = re.match(r"^([^:]+):(?:[ \t]+(.*)|$)", content)
        if not match:
            raise ValueError("Structure YAML non prise en charge ; vérifier le fichier d'instance.")
        return str(cast_scalar(match[1].strip())), (match[2] or "").strip()

    def mapping(position, indent, first=None):
        result = {}
        while position < len(tokens):
            level, content, number = tokens[position]
            if first is None and (level != indent or sequence(content)):
                break
            content = first if first is not None else content
            first = None
            key, value = entry(content)
            position += 1
            if value in ("|", "|-", ">", ">-"):
                end = number + 1
                block_lines = []
                prefix = None
                while end < len(raw_lines):
                    raw = raw_lines[end]
                    depth = len(raw) - len(raw.lstrip())
                    if raw.strip() and depth <= indent:
                        break
                    if raw.strip() and prefix is None:
                        prefix = depth
                    block_lines.append(raw[prefix:] if raw.strip() else "")
                    end += 1
                while position < len(tokens) and tokens[position][2] < end:
                    position += 1
                result[key] = "\n".join(block_lines)
            elif value:
                # Les exporteurs YAML replient aussi les longues chaînes sans |.
                while position < len(tokens) and tokens[position][0] > indent:
                    value += " " + tokens[position][1]
                    position += 1
                result[key] = cast_scalar(value)
            elif position < len(tokens) and (tokens[position][0] > indent or
                    (tokens[position][0] == indent and sequence(tokens[position][1]))):
                result[key], position = block(position, tokens[position][0])
            else:
                result[key] = {}
        return result, position

    def block(position, indent):
        if not sequence(tokens[position][1]):
            return mapping(position, indent)
        values = []
        while position < len(tokens) and tokens[position][0] == indent and sequence(tokens[position][1]):
            content = tokens[position][1][1:].strip()
            if not content:
                position += 1
                if position < len(tokens) and tokens[position][0] > indent:
                    value, position = block(position, tokens[position][0])
                else:
                    value = None
            elif re.match(r"^[^:]+:(?:[ \t]+|$)", content):
                value, position = mapping(position, indent + 2, first=content)
            else:
                value = cast_scalar(content)
                position += 1
            values.append(value)
        return values, position

    if not tokens:
        return {}
    result, position = block(0, tokens[0][0])
    if position != len(tokens) or not isinstance(result, dict):
        raise ValueError("Structure YAML non prise en charge ; vérifier le fichier d'instance.")
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
        if val.startswith('"'):
            try:
                return json.loads(val)
            except ValueError:
                pass
        return val[1:-1]
    if (val.startswith("[") and val.endswith("]")) or (val.startswith("{") and val.endswith("}")):
        try:
            return json.loads(val)
        except Exception:
            pass
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
                 ssh_key: str = "", known_hosts: str = ""):
        self.mode = mode
        self.kubeconfig = kubeconfig
        self.context = context
        self.ssh_node = ssh_node
        self.ssh_user = ssh_user
        self.ssh_port = ssh_port
        self.ssh_key = ssh_key.strip() if ssh_key else ""

        self.ident_key, self.known_hosts = find_harness_ssh()
        self.known_hosts = known_hosts or self.known_hosts
        if not self.ssh_key and self.ident_key:
            self.ssh_key = self.ident_key

    def run(self, cmd_args: List[str], stdin_input: Optional[str] = None, timeout: Optional[int] = None) -> Tuple[int, str, str]:
        """Exécute une commande kubectl soit en local, soit via SSH."""
        if self.mode == "local":
            base_cmd = ["kubectl"]
            if self.kubeconfig:
                base_cmd.extend(["--kubeconfig", self.kubeconfig])
            if self.context:
                base_cmd.extend(["--context", self.context])
            full_cmd = base_cmd + cmd_args

            try:
                proc = subprocess.run(
                    full_cmd,
                    input=stdin_input.encode("utf-8") if stdin_input else None,
                    capture_output=True,
                    timeout=timeout
                )
                return proc.returncode, proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace")
            except subprocess.TimeoutExpired:
                return 255, "", f"Délai d'attente dépassé ({timeout}s) lors de l'exécution locale de kubectl."

        elif self.mode == "remote-ssh":
            quoted_args = " ".join([f"'{arg}'" if " " in arg or "|" in arg or ";" in arg else arg for arg in cmd_args])
            remote_shell = f"if command -v k3s >/dev/null 2>&1; then sudo k3s kubectl {quoted_args}; else sudo kubectl {quoted_args}; fi"

            ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
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

            try:
                proc = subprocess.run(
                    ssh_cmd,
                    input=stdin_input.encode("utf-8") if stdin_input else None,
                    capture_output=True,
                    timeout=timeout
                )
                return proc.returncode, proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace")
            except subprocess.TimeoutExpired:
                return 255, "", f"Délai d'attente dépassé ({timeout}s) lors de l'exécution SSH sur {self.ssh_node}."

        else:
            raise ValueError(f"Mode d'exécution inconnu : {self.mode}")

    def apply_manifest(self, manifest_yaml: str) -> None:
        """Applique un manifeste YAML via stdin (avec fallback replace en cas de conflit de schéma StrategicMerge)."""
        rc, out, err = self.run(["apply", "-f", "-"], stdin_input=manifest_yaml)
        if rc != 0:
            combined = (err or "") + "\n" + (out or "")
            if any(k in combined for k in ("may not be specified when", "field is immutable", "conflict")):
                # En cas de transition de type sur une clé env (ex: value <-> valueFrom) ou conflit de schéma,
                # kubectl replace remplace directement les spécifications sans fusion conflictuelle
                rc_rep, out_rep, err_rep = self.run(["replace", "-f", "-"], stdin_input=manifest_yaml)
                if rc_rep == 0:
                    return
            raise RuntimeError(f"Échec de l'application du manifeste :\n{err or out}")

# -----------------------------------------------------------------------------
# Validation des Prérequis & Données de Configuration
# -----------------------------------------------------------------------------
def validate_config(cfg: Dict[str, Any]) -> None:
    from hermes_files import declared_users
    declared_users(cfg)
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

    # Validation du catalogue et du routage des modèles
    llm = cfg.get("llm_gateway", {})
    if "models_routing" in llm:
        raw_mappings = llm["models_routing"]
        if isinstance(raw_mappings, list):
            seen_aliases = set()
            for idx, m in enumerate(raw_mappings):
                if not isinstance(m, dict):
                    continue
                alias = str(m.get("alias") or m.get("name") or "").strip()
                if not alias:
                    errors.append(f"llm_gateway.models_routing[{idx}] : identifiant (alias) manquant.")
                    continue
                if alias in seen_aliases:
                    errors.append(f"llm_gateway.models_routing : identifiant dupliqué '{alias}'.")
                seen_aliases.add(alias)
                target = str(m.get("target_model") or m.get("real_model") or "").strip()
                if not target:
                    errors.append(f"llm_gateway.models_routing[{idx}] ('{alias}') : cible fournisseur manquante (target_model obligatoire).")

            def_llm = str(llm.get("default_model") or "").strip()
            if def_llm and seen_aliases and def_llm not in seen_aliases:
                errors.append(f"llm_gateway.default_model '{def_llm}' est introuvable parmi les modèles déclarés ({', '.join(sorted(seen_aliases))}).")

            def_hermes = str(cfg.get("hermes", {}).get("default_model") or "").strip()
            if def_hermes and seen_aliases and def_hermes not in seen_aliases:
                errors.append(f"hermes.default_model '{def_hermes}' est introuvable parmi les modèles déclarés ({', '.join(sorted(seen_aliases))}).")

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

def build_model_catalog(cfg: Optional[Dict[str, Any]] = None, root_dir: Optional[str] = None) -> Dict[str, Any]:
    """Construit la représentation unifiée et normalisée du catalogue de modèles à partir des déclarations du Wizard.
    Garantit une source de vérité unique pour LiteLLM, Hermes et Open-WebUI."""
    cfg = cfg or {}
    llm_cfg = cfg.get("llm_gateway", {})
    hermes_cfg = cfg.get("hermes", {})

    raw_mappings = llm_cfg.get("models_routing")
    if raw_mappings is None and root_dir:
        cfg_path = os.path.join(root_dir, "arcia.config.yaml")
        if os.path.isfile(cfg_path):
            try:
                import yaml
                with open(cfg_path, "r", encoding="utf-8") as f:
                    c = yaml.safe_load(f)
                    if c and isinstance(c, dict):
                        raw_mappings = c.get("llm_gateway", {}).get("models_routing")
            except Exception:
                pass

    is_explicit_catalog = (raw_mappings is not None)

    # Si models_routing est absent (None et non configuré), on utilise le catalogue canonique par défaut
    if raw_mappings is None:
        raw_mappings = [
            {
                "alias": "simple/auto",
                "category": "simple",
                "provider": "openrouter",
                "target_model": "openrouter/anthropic/claude-3.5-haiku",
                "fallback": "simple/free",
                "zdr": True
            },
            {
                "alias": "simple/free",
                "category": "simple",
                "provider": "openrouter",
                "target_model": "openrouter/meta-llama/llama-3.3-70b-instruct:free",
                "fallback": "",
                "zdr": True
            },
            {
                "alias": "agentic/auto",
                "category": "agentic",
                "provider": "openrouter",
                "target_model": "openrouter/anthropic/claude-3.7-sonnet",
                "fallback": "agentic/free",
                "zdr": True
            },
            {
                "alias": "agentic/free",
                "category": "agentic",
                "provider": "openrouter",
                "target_model": "openrouter/meta-llama/llama-3.3-70b-instruct:free",
                "fallback": "",
                "zdr": True
            },
            {
                "alias": "agentic/expert",
                "category": "agentic",
                "provider": "openrouter",
                "target_model": "openrouter/anthropic/claude-3.7-sonnet:thinking",
                "fallback": "agentic/auto",
                "zdr": True
            }
        ]

    models: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    for item in raw_mappings:
        if not isinstance(item, dict):
            continue
        # L'alias prime sur le nom
        alias = str(item.get("alias") or item.get("name") or "").strip()
        if not alias:
            continue
        if alias in seen_ids:
            continue
        seen_ids.add(alias)

        target = str(item.get("target_model") or item.get("real_model") or "").strip()
        category = str(item.get("category") or "simple").strip().lower()
        if category not in ("simple", "agentic"):
            category = "simple"
        provider = str(item.get("provider") or "openrouter").strip().lower()
        zdr = bool(item.get("zdr", True))
        fallback = str(item.get("fallback") or "").strip()
        fallbacks = item.get("fallbacks") or ([fallback] if fallback else [])

        models.append({
            "id": alias,
            "alias": alias,
            "name": str(item.get("name") or alias).strip(),
            "target_model": target,
            "real_model": target,
            "category": category,
            "provider": provider,
            "zdr": zdr,
            "fallbacks": [f for f in fallbacks if f],
            "fallback": fallback,
            "label": item.get("label", alias),
            "profile": item.get("profile", ""),
            "description": item.get("description", "")
        })

    simple_models = [m["id"] for m in models if m["category"] == "simple"]
    agentic_models = [m["id"] for m in models if m["category"] == "agentic"]

    declared_def_simple = str(llm_cfg.get("default_model") or "").strip()
    if declared_def_simple in simple_models:
        default_simple = declared_def_simple
    elif simple_models:
        default_simple = simple_models[0]
    else:
        default_simple = declared_def_simple if declared_def_simple else ""

    declared_def_agentic = str(hermes_cfg.get("default_model") or "").strip()
    if declared_def_agentic in agentic_models:
        default_agentic = declared_def_agentic
    elif agentic_models:
        default_agentic = agentic_models[0]
    else:
        default_agentic = declared_def_agentic if declared_def_agentic else default_simple

    return {
        "all_models": models,
        "simple_models": simple_models,
        "agentic_models": agentic_models,
        "default_simple": default_simple,
        "default_agentic": default_agentic,
        "seen_ids": seen_ids,
        "is_explicit_catalog": is_explicit_catalog
    }

def build_openwebui_api_configs(cfg: Optional[Dict[str, Any]] = None) -> str:
    """Génère la configuration OPENAI_API_CONFIGS pour Open-WebUI v0.12.3.
    Index '0' (LiteLLM) : uniquement les modèles simple déclarés.
    Index '1' (Hermes) : uniquement les modèles agentic déclarés.
    Si une catégorie est vide, la connexion correspondante est désactivée avec enable: false."""
    catalog = build_model_catalog(cfg)
    simple_models = catalog["simple_models"]
    agentic_models = catalog["agentic_models"]

    configs = {
        "0": {
            "enable": bool(simple_models),
            "model_ids": simple_models
        },
        "1": {
            "enable": bool(agentic_models),
            "model_ids": agentic_models
        }
    }
    return json.dumps(configs, ensure_ascii=False)

def build_hermes_config_data(cfg: Optional[Dict[str, Any]] = None, namespace: str = "arcia") -> str:
    """Génère le contenu complet de config.yaml pour Hermes Agent (Studio & Pods dédiés Power Users).
    Projette dynamiquement les seuls modèles de catégorie agentic déclarés."""
    catalog = build_model_catalog(cfg)
    agentic_models = catalog["agentic_models"]
    default_agentic = catalog["default_agentic"] or (agentic_models[0] if agentic_models else "")

    if agentic_models:
        models_lines = "\n".join(f"          - {m}" for m in agentic_models)
        routes_lines = "\n".join(
            f"          {m}:\n            model: \"{m}\""
            for m in agentic_models
        )
    else:
        models_lines = "          []"
        routes_lines = "          {}"

    return f"""model:
  provider: custom
  base_url: http://litellm-proxy.{namespace}.svc:4000/v1
  default: {default_agentic}
  key_env: OPENAI_API_KEY
providers:
  custom:
    name: "ArcIA Agentic"
    base_url: http://litellm-proxy.{namespace}.svc:4000/v1
    key_env: OPENAI_API_KEY
    discover_models: false
    models:
{models_lines}
plugins:
  enabled:
    - arcia_governance
approvals:
  mode: smart
  unattended_mode: approve
skills:
  external_dirs:
    - /opt/data/skills
    - /opt/data/shared-skills/arcia
agent:
  max_turns: 30
platforms:
  api_server:
    direct_model_requests: true
    model_name: "{default_agentic}"
    model_routes:
{routes_lines}
"""

def compute_models_branding_dict(cfg: Optional[Dict[str, Any]] = None, root_dir: Optional[str] = None) -> Dict[str, Any]:
    """Projection visuelle des seules déclarations, sans décision de routage."""
    if cfg is None and root_dir:
        path = os.path.join(root_dir, "arcia.config.yaml")
        cfg = parse_yaml_or_env(path) if os.path.isfile(path) else {}
    return build_mapping(cfg or {})


def build_litellm_config_data(cfg: Optional[Dict[str, Any]] = None, namespace: str = "arcia") -> str:
    """Génère le contenu complet de config.yaml pour le ConfigMap litellm-config d'après arcia.config.yaml."""
    cfg = cfg or {}
    catalog = build_model_catalog(cfg)
    models = catalog["all_models"]
    defined_names = {m["id"] for m in models}

    model_list_entries = []
    fallbacks_map = {}

    for m in models:
        name = m["id"]
        target = m["target_model"]
        fallbacks = m["fallbacks"]
        zdr = m["zdr"]
        prov = m["provider"]

        if fallbacks:
            fallbacks_map[name] = [f for f in fallbacks if f]

        api_key_var = "os.environ/OPENROUTER_API_KEY"
        if prov == "openai":
            api_key_var = "os.environ/OPENAI_API_KEY"
        elif prov == "anthropic":
            api_key_var = "os.environ/ANTHROPIC_API_KEY"
        elif prov == "mistral":
            api_key_var = "os.environ/MISTRAL_API_KEY"
        elif prov == "gemini":
            api_key_var = "os.environ/GEMINI_API_KEY"
        elif prov in ("ollama", "vllm", "local"):
            api_key_var = "ollama"

        is_free_openrouter = (prov == "openrouter") and (":free" in target.lower() or "free" in target.lower())

        extra_body_lines = [
            "      extra_body:",
            "        provider:",
        ]
        if not is_free_openrouter:
            extra_body_lines.append('          data_collection: "deny"')
        extra_body_lines.extend([
            f'          zdr: {str(zdr).lower()}',
            '          allow_fallbacks: false'
        ])
        extra_body_str = "\n".join(extra_body_lines)

        entry = f"""  - model_name: "{name}"
    litellm_params:
      model: {target}
      api_key: {api_key_var}
{extra_body_str}"""
        model_list_entries.append(entry)

    fallbacks_lines = []
    for k, v in fallbacks_map.items():
        if v:
            fallbacks_lines.append(f'    - "{k}": {json.dumps(v)}')
    fallbacks_yaml = "\n".join(fallbacks_lines) if fallbacks_lines else "    []"

    alias_entries = []
    default_simple = catalog["default_simple"]
    if default_simple and "simple/auto" not in defined_names and default_simple in defined_names:
        alias_entries.append(f"""    "simple/auto":\n      model: "{default_simple}"\n      hidden: true""")

    free_simple = next((m["id"] for m in models if m["category"] == "simple" and m["zdr"]), default_simple)
    if free_simple and "simple/free" not in defined_names and free_simple in defined_names:
        alias_entries.append(f"""    "simple/free":\n      model: "{free_simple}"\n      hidden: true""")

    default_agentic = catalog["default_agentic"]
    if default_agentic and "agentic/auto" not in defined_names and default_agentic in defined_names:
        alias_entries.append(f"""    "agentic/auto":\n      model: "{default_agentic}"\n      hidden: true""")

    free_agentic = next((m["id"] for m in models if m["category"] == "agentic" and m["zdr"]), default_agentic)
    if free_agentic and "agentic/free" not in defined_names and free_agentic in defined_names:
        alias_entries.append(f"""    "agentic/free":\n      model: "{free_agentic}"\n      hidden: true""")

    if "simple/free" in defined_names and "agentic/free" not in defined_names:
        alias_entries.append("""    "agentic/free":\n      model: "simple/free"\n      hidden: true""")
    if "simple/auto" in defined_names and "agentic/auto" not in defined_names:
        alias_entries.append("""    "agentic/auto":\n      model: "simple/auto"\n      hidden: true""")

    aliases_yaml = "\n".join(alias_entries) if alias_entries else "    {}"
    models_yaml = "\n".join(model_list_entries) if model_list_entries else "  []"

    return f"""model_list:
{models_yaml}

router_settings:
  fallbacks:
{fallbacks_yaml}
  model_group_alias:
{aliases_yaml}

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  salt_key: os.environ/LITELLM_SALT_KEY
  database_url: os.environ/DATABASE_URL
  database_connection_pool_limit: 10
  user_header_name: "X-OpenWebUI-User-Email"
  store_model_in_db: false

litellm_settings:
  drop_params: true
  callbacks: error_handler.proxy_handler_instance
  request_timeout: 20
  num_retries: 1

guardrails:
  - guardrail_name: "presidio-guard"
    litellm_params:
      guardrail: presidio
      mode: "pre_call"
      default_on: true
      timeout: 5
      pii_entities_config:
        EMAIL_ADDRESS: MASK
      presidio_analyzer_api_base: "http://presidio-dlp.{namespace}.svc:8080"
      presidio_anonymizer_api_base: "http://presidio-dlp.{namespace}.svc:8080"
"""

def render_model_manifest(component, manifest, cfg, namespace="arcia", branding_revision=None, code_checksums=None):
    """Même projection d'instance à l'installation et lors des mises à jour."""
    rendered = adapt_manifest_namespace(manifest, namespace)
    checksums = code_checksums or {}
    if component in ("litellm-proxy", "hermes-agent"):
        if component == "litellm-proxy":
            name = "litellm-config"
            content = build_litellm_config_data(cfg, namespace)
        else:
            name = "hermes-config"
            content = build_hermes_config_data(cfg, namespace)
            fqdn = cfg.get("network", {}).get("public_fqdn") or "assistant.example.org"
            rendered = rendered.replace("https://assistant.example.org/studio", f"https://{fqdn}/studio")
        parts = re.split(r"\n---\s*\n", rendered, maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Manifeste {component} incomplet : Deployment absent.")
        cm = f"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: {name}\n  namespace: {namespace}\ndata:\n  config.yaml: |\n" + textwrap.indent(content, "    ")
        rendered = cm + "\n---\n" + parts[1]
        checksums = {**checksums, name: hashlib.sha256(content.encode("utf-8")).hexdigest()}
    elif component == "open-webui":
        catalog = build_model_catalog(cfg)
        default = catalog["default_simple"] or catalog["default_agentic"] or ""
        for name, value in {"OPENAI_API_CONFIGS": build_openwebui_api_configs(cfg),
                            "DEFAULT_MODELS": default, "TASK_MODEL": default}.items():
            pattern = rf'(- name: {name}\s*\n\s*value:\s*)(?:\'[^\']*\'|"(?:\\.|[^"\\])*")'
            rendered = re.sub(pattern, lambda match: match[1] + json.dumps(value, ensure_ascii=False), rendered)
        if branding_revision:
            checksums = {**checksums, "arcia-webui-branding": branding_revision}
        from hermes_files import declared_users
        declared_users(cfg)
        rendered = rendered.replace(f"http://hermes-studio.{namespace}.svc:8642/v1",
                                    "http://127.0.0.1:8080/api/v1/arcia/hermes/v1")
        rendered = rendered.replace("$(LITELLM_MASTER_KEY);$(HERMES_API_TOKEN)",
                                    "$(LITELLM_MASTER_KEY);__ARCIA_HERMES_FILES_KEY__")
    for name, revision in checksums.items():
        rendered = re.sub(rf'(checksum/{re.escape(name)}:\s*)"[^"]*"',
                          lambda match: match[1] + json.dumps(revision), rendered)
    return rendered


def sync_webui_branding(runner: K8sRunner, namespace: str, root_dir: str, cfg: Optional[Dict[str, Any]] = None):
    """Crée le ConfigMap arcia-webui-branding avec les logos SVG, custom.css, loader.js et les icônes de modèles ArcIA."""
    symbol_path = os.path.join(root_dir, "assets", "branding", "logo-arcia-symbol.svg")
    dark_path = os.path.join(root_dir, "assets", "branding", "logo-arcia-dark.svg")
    css_path = os.path.join(root_dir, "assets", "branding", "custom.css")
    loader_path = os.path.join(root_dir, "assets", "branding", "loader.js")
    icon_default_path = os.path.join(root_dir, "assets", "branding", "icon-model-default.svg")
    icon_local_path = os.path.join(root_dir, "assets", "branding", "icon-model-local.svg")
    icon_zdr_path = os.path.join(root_dir, "assets", "branding", "icon-model-zdr.svg")

    def read_file_safe(path: str) -> str:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    symbol_content = read_file_safe(symbol_path)
    dark_content = read_file_safe(dark_path)
    css_content = read_file_safe(css_path)
    loader_content = read_file_safe(loader_path)
    icon_default_content = read_file_safe(icon_default_path)
    icon_local_content = read_file_safe(icon_local_path)
    icon_zdr_content = read_file_safe(icon_zdr_path)

    # Le mapping privé est transmis en mémoire ; aucune écriture dans les assets suivis.
    branding_dict = compute_models_branding_dict(cfg=cfg, root_dir=root_dir)
    if not all((icon_default_content, icon_local_content, icon_zdr_content)):
        raise RuntimeError("Ressource d'icône requise absente ; publication interrompue.")
    # La route d'avatar doit invalider son URL même si seul le dessin SVG change.
    branding_dict["asset_revision"] = hashlib.sha256((icon_default_content + icon_local_content + icon_zdr_content).encode()).hexdigest()
    branding_dict["revision"] = hashlib.sha256(json.dumps(branding_dict, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    models_branding_json = json.dumps(branding_dict, indent=2, ensure_ascii=False)

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
    if css_content:
        cm_lines.append("  custom.css: |")
        for line in css_content.splitlines():
            cm_lines.append(f"    {line}")
    if loader_content:
        cm_lines.append("  loader.js: |")
        for line in loader_content.splitlines():
            cm_lines.append(f"    {line}")
    if icon_default_content:
        cm_lines.append("  icon-model-default.svg: |")
        for line in icon_default_content.splitlines():
            cm_lines.append(f"    {line}")
    if icon_local_content:
        cm_lines.append("  icon-model-local.svg: |")
        for line in icon_local_content.splitlines():
            cm_lines.append(f"    {line}")
    if icon_zdr_content:
        cm_lines.append("  icon-model-zdr.svg: |")
        for line in icon_zdr_content.splitlines():
            cm_lines.append(f"    {line}")
    if models_branding_json:
        cm_lines.append("  models-branding.json: |")
        for line in models_branding_json.splitlines():
            cm_lines.append(f"    {line}")

    manifest = "\n".join(cm_lines)
    runner.apply_manifest(manifest)
    code = {}
    for name in ("branding.py", "arcia_webui.py", "start.py", "arcia_hermes_files.py"):
        code[name] = read_file_safe(os.path.join(root_dir, "services", "open_webui", name))
    if not all(code.values()):
        raise RuntimeError("Adaptateur d'avatar Open-WebUI absent.")
    runner.apply_manifest(json.dumps({"apiVersion": "v1", "kind": "ConfigMap",
                                     "metadata": {"name": "arcia-webui-code", "namespace": namespace}, "data": code}))
    revision = hashlib.sha256((manifest + json.dumps(code, sort_keys=True)).encode("utf-8")).hexdigest()
    log_ok("Ressources visuelles appliquées ; validation HTTP distincte requise.")
    return {"assets_applied": True, "revision": revision, "mapping": branding_dict,
            "asset_hashes": {"icon-model-default.svg": hashlib.sha256(icon_default_content.encode()).hexdigest(),
                             "icon-model-local.svg": hashlib.sha256(icon_local_content.encode()).hexdigest(),
                             "icon-model-zdr.svg": hashlib.sha256(icon_zdr_content.encode()).hexdigest()}}


def activate_webui_branding(runner, namespace, state):
    """Recharge les subPath et installe le lanceur ; ne touche pas aux connexions modèles."""
    patch = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "open-webui", "namespace": namespace},
             "spec": {"strategy": {"type": "Recreate", "rollingUpdate": None},
                      "template": {"metadata": {"annotations": {"checksum/arcia-webui-branding": state["revision"]}},
                       "spec": {"containers": [{"name": "open-webui", "command": ["python3", "/opt/arcia-webui/start.py"],
                                 "volumeMounts": [{"mountPath": "/app/build/static/models-branding.json", "$patch": "delete"}, {"name": "arcia-branding-private", "mountPath": "/etc/arcia", "readOnly": True},
                                                  {"name": "arcia-webui-code", "mountPath": "/opt/arcia-webui", "readOnly": True}]}],
                                "volumes": [{"name": "arcia-branding-private", "configMap": {"name": "arcia-webui-branding", "items": [{"key": "models-branding.json", "path": "models-branding.json"}]}},
                                            {"name": "arcia-webui-code", "configMap": {"name": "arcia-webui-code"}}]}}}}
    # Fusion ciblée : préserver les connexions et retirer l'ancien mapping public.
    if getattr(runner, "mode", "remote-ssh") == "local":
        with tempfile.TemporaryDirectory(prefix="arcia-branding-") as directory:
            patch_file = os.path.join(directory, "patch.json")
            with open(patch_file, "w", encoding="utf-8") as stream:
                json.dump(patch, stream)
            rc, _, _ = runner.run(["patch", "deployment", "open-webui", "-n", namespace, "--type=strategic", "--patch-file=" + patch_file], timeout=20)
    else:
        rc, _, _ = runner.run(["patch", "deployment", "open-webui", "-n", namespace, "--type=strategic", "--patch-file=/dev/stdin"], stdin_input=json.dumps(patch), timeout=20)
    if rc:
        return {"assets_applied": True, "runtime_loaded": False, "avatars_verified": False, "error": "Activation du branding refusée."}
    rc, _, _ = runner.run(["rollout", "status", "deployment/open-webui", "-n", namespace, "--timeout=120s"], timeout=125)
    if rc:
        return {"assets_applied": True, "runtime_loaded": False, "avatars_verified": False, "error": "Rollout des ressources visuelles échoué."}
    probe_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "services", "open_webui", "verify.py")
    with open(probe_path, encoding="utf-8") as stream:
        source = stream.read()
    source += "\nprint('ARCIA_BRANDING_RESULT=' + json.dumps(verify(" + repr(state["mapping"]["revision"]) + ", " + repr(state["asset_hashes"]) + ")))\n"
    rc, out, _ = runner.run(["exec", "-i", "deployment/open-webui", "-n", namespace, "--", "python3", "-"], stdin_input=source, timeout=25)
    result = {"assets_applied": True, "runtime_loaded": False, "avatars_verified": False, "assets_served": False}
    for line in out.splitlines() if rc == 0 else []:
        if line.startswith("ARCIA_BRANDING_RESULT="):
            result.update(json.loads(line.split("=", 1)[1]))
    return result


def sync_service_configmaps(runner: K8sRunner, namespace: str, root_dir: str) -> Dict[str, str]:
    """Injecte le code source unique de services/ (Presidio DLP, Teams Bot, Hermes Governance Plugin, LiteLLM Error Handler) dans des ConfigMaps Kubernetes."""
    mappings = [
        ("presidio-code", "app.py", os.path.join(root_dir, "services", "presidio", "app.py")),
        ("teams-bot-code", "app.py", os.path.join(root_dir, "services", "teams", "app.py")),
        ("hermes-governance-plugin", "plugin.py", os.path.join(root_dir, "services", "hermes", "plugin.py")),
        ("hermes-files-code", "files.py", os.path.join(root_dir, "services", "hermes", "files.py")),
        ("litellm-error-handler", "error_handler.py", os.path.join(root_dir, "services", "litellm", "error_handler.py")),
    ]
    checksums: Dict[str, str] = {}
    for cm_name, key_name, file_path in mappings:
        if not os.path.isfile(file_path):
            log_warn(f"Fichier source introuvable pour ConfigMap '{cm_name}' : {file_path}")
            continue
        with open(file_path, "r", encoding="utf-8") as f:
            code_content = f.read()
        checksums[cm_name] = hashlib.sha256(code_content.encode("utf-8")).hexdigest()[:16]
        indented = "\n".join("    " + line for line in code_content.splitlines())
        cm_yaml = (
            "apiVersion: v1\n"
            "kind: ConfigMap\n"
            "metadata:\n"
            f"  name: {cm_name}\n"
            f"  namespace: {namespace}\n"
            "data:\n"
            f"  {key_name}: |\n"
            f"{indented}\n"
        )
        if cm_name in ("presidio-code", "teams-bot-code"):
            service = "presidio" if cm_name == "presidio-code" else "teams"
            with open(os.path.join(root_dir, "services", service, "requirements.txt"), encoding="utf-8") as source:
                requirements = source.read()
            if not requirements:
                raise RuntimeError("Dépendances du microservice épinglées absentes")
            cm_yaml += "  requirements.txt: |\n" + "\n".join("    " + line for line in requirements.splitlines()) + "\n"
            checksums[cm_name] = hashlib.sha256((code_content + requirements).encode()).hexdigest()[:16]
        runner.apply_manifest(cm_yaml)
    from hermes_files import governance_code, governance_revision
    runner.apply_manifest(json.dumps({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {
        "name": "hermes-runtime-guard", "namespace": namespace}, "data": governance_code(root_dir)}))
    checksums["hermes-runtime-guard"] = governance_revision(root_dir)
    log_ok("ConfigMaps des microservices et de l'admission DLP obligatoire synchronisés depuis services/.")
    return checksums

# -----------------------------------------------------------------------------
# Déploiement des Composants & Rendu des Manifestes
# -----------------------------------------------------------------------------
def retire_legacy_webui_key(runner, namespace: str, root_dir: str) -> Dict[str, Any]:
    """Retire uniquement l'identité statique historique après contrôle du portail."""
    source_path = os.path.join(root_dir, "services", "litellm", "retire_legacy_key.py")
    with open(source_path, encoding="utf-8") as stream:
        source = stream.read()
    rc, out, _ = runner.run(
        ["exec", "-i", "deployment/open-webui", "-n", namespace, "--", "python3", "-", "--check-consumer"],
        stdin_input=source, timeout=25)
    if rc != 0 or "ARCIA_LEGACY_CONSUMER_SAFE=true" not in out.splitlines():
        return {"retired": False, "verified_absent": False, "consumer_check_passed": False}
    rc, out, _ = runner.run(
        ["exec", "-i", "deployment/litellm-proxy", "-n", namespace, "--", "python3", "-"],
        stdin_input=source, timeout=55)
    for line in out.splitlines() if rc == 0 else []:
        if line.startswith("ARCIA_LEGACY_KEY_RESULT="):
            result = json.loads(line.split("=", 1)[1])
            if result.get("verified_absent") is True:
                return result
    raise RuntimeError("Retrait de la clé LiteLLM historique non vérifié.")


def sync_litellm_provider_secrets(cfg: Dict[str, Any], runner, namespace: str) -> None:
    """Met à jour les clés fournisseurs par stdin en préservant l'identité du proxy."""
    updates = {p.replace("_", "-") + "-key": str(cfg.get("llm_gateway", {}).get(p + "_api_key", "")).strip()
               for p in ("openrouter", "openai", "anthropic", "mistral", "gemini")}
    updates = {k: v for k, v in updates.items() if v}
    if not updates:
        return
    rc, out, _ = runner.run(["get", "secret", "litellm-secret", f"-n={namespace}", "-o", "json"], timeout=10)
    if rc != 0:
        raise RuntimeError("Secret LiteLLM inaccessible ; aucune identité remplacée.")
    data = json.loads(out).get("data", {})
    if not all(data.get(k) for k in ("master-key", "salt-key", "database-url")):
        raise RuntimeError("Secret LiteLLM incomplet ; réappliquez le déploiement.")
    data.update({k: base64.b64encode(v.encode("utf-8")).decode("ascii") for k, v in updates.items()})
    runner.apply_manifest(json.dumps({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                                     "metadata": {"name": "litellm-secret", "namespace": namespace}, "data": data}))


def get_existing_cluster_secret(runner, namespace: str, secret_name: str, key_name: str) -> Optional[str]:
    """Lit un champ de Secret en mémoire sans l'afficher."""
    try:
        rc, out, _ = runner.run(["get", "secret", secret_name, f"-n={namespace}", "-o", "json"], timeout=10)
        if rc == 0 and out.strip():
            value = json.loads(out).get("data", {}).get(key_name)
            if value:
                return base64.b64decode(value.strip()).decode("utf-8")
    except Exception:
        pass
    return None


def assert_database_upgrade_safe(runner, namespace: str, target_image: str) -> None:
    """Refuse avant mutation un changement majeur ou un volume sans propriétaire."""
    def major(image):
        match = re.search(r"(?:^|/)postgres:(\d+)(?:[.\-@]|$)", image)
        if not match:
            raise ValueError("Version PostgreSQL indéterminée ; migration et vérification du volume requises.")
        return int(match[1])

    target_major = major(target_image)
    objects = {}
    for kind, name in (("statefulset", "litellm-db"), ("pvc", "litellm-db-pvc")):
        rc, output, _ = runner.run(["get", kind, name, "-n", namespace,
                                    "--ignore-not-found=true", "-o", "json"])
        if rc:
            raise ValueError("Vérification PostgreSQL impossible ; aucune migration automatique autorisée.")
        try:
            objects[kind] = json.loads(output) if output.strip() else None
        except (ValueError, TypeError):
            raise ValueError("État PostgreSQL illisible ; aucune migration automatique autorisée.") from None
    existing = objects["statefulset"]
    if existing:
        containers = existing.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        images = [item.get("image", "") for item in containers if item.get("name") == "postgres"]
        if len(images) != 1 or major(images[0]) != target_major:
            raise ValueError("Changement majeur PostgreSQL : migration sauvegardée et restaurée requise avant réapplication.")
    elif objects["pvc"]:
        raise ValueError("Un volume PostgreSQL existe sans StatefulSet ; vérifier sa version et sa restauration avant réapplication.")


def deploy_arcia(cfg: Dict[str, Any], root_dir: str):
    if cfg.get("synthetic_validation"):
        raise ValueError("Une fixture synthétique ne peut pas être déployée ; utilisez --dry-run.")
    from hermes_files import declared_users, sync_private_runtimes
    declared_users(cfg)
    from services.instance_backup.storage import identity_recovery_pending
    if identity_recovery_pending(root_dir, cfg):
        raise ValueError("Identité LiteLLM signalée à récupérer localement avant déploiement ; aucune mutation effectuée.")
    from services.instance_backup.powerusers import declared_powerusers, reconcile_powerusers
    declared_powerusers(cfg)
    k8s_cfg = cfg.get("kubernetes", {})
    mode = k8s_cfg.get("mode", "local")
    kubeconfig = k8s_cfg.get("kubeconfig", "")
    context = k8s_cfg.get("context", "")
    namespace = k8s_cfg.get("namespace", "arcia")
    storage_class = k8s_cfg.get("storage_class", "")

    net_cfg = cfg.get("network", {})
    public_fqdn = net_cfg.get("public_fqdn", "assistant.example.org")
    tls_mode = net_cfg.get("tls_mode", "letsencrypt-prod")
    acme_email = net_cfg.get("acme_email", "admin@example.org")
    ingress_class = net_cfg.get("ingress_class", "traefik")
    tls_secret_name = net_cfg.get("tls_secret_name", "arcia-tls-cert")

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
        ssh_key=ssh_key,
        known_hosts=ssh_info.get("known_hosts_file", "")
    )

    registry_path = Path(root_dir) / "deploy" / "versions.json"
    with registry_path.open(encoding="utf-8") as registry_file:
        target_db_image = json.load(registry_file)["components"]["litellm-db"]["image"]
    assert_database_upgrade_safe(runner, namespace, target_db_image)

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

    def _get_existing_cluster_secret(secret_name: str, key_name: str) -> Optional[str]:
        return get_existing_cluster_secret(runner, namespace, secret_name, key_name)

    # 1. enterprise-llm-secret
    openrouter_key = llm_cfg.get("openrouter_api_key", "").strip()
    if not openrouter_key:
        openrouter_key = _get_existing_cluster_secret("litellm-secret", "openrouter-key") or ""
        if openrouter_key:
            log_info(" -> Préservation de la clé OpenRouter existante du cluster.")
    runner.apply_manifest(make_secret_manifest("enterprise-llm-secret", namespace, {
        "openrouter-key": openrouter_key
    }))

    # 2. litellm-secret (Master key, OpenRouter key, DB password & URL, Salt key)
    litellm_master = llm_cfg.get("master_key", "")
    if not litellm_master or litellm_master in KNOWN_INSECURE_SECRETS:
        litellm_master = _get_existing_cluster_secret("litellm-secret", "master-key") or f"sk-arcia-{secrets.token_urlsafe(32)}"
        log_info(" -> Génération ou préservation de la Master Key LiteLLM.")
        llm_cfg["master_key"] = litellm_master

    litellm_salt = llm_cfg.get("salt_key", "")
    if not litellm_salt or litellm_salt in KNOWN_INSECURE_SECRETS:
        litellm_salt = _get_existing_cluster_secret("litellm-secret", "salt-key") or secrets.token_hex(16)

    litellm_db_pass = llm_cfg.get("db_password", "")
    if not litellm_db_pass or litellm_db_pass in KNOWN_INSECURE_SECRETS:
        litellm_db_pass = _get_existing_cluster_secret("litellm-secret", "db-password") or f"ArcIA_DB_{secrets.token_urlsafe(24)}"

    litellm_db_url = f"postgresql://litellm:{litellm_db_pass}@litellm-db.{namespace}.svc:5432/litellm"

    litellm_secret_data = {
        "master-key": litellm_master,
        "salt-key": litellm_salt,
        "db-password": litellm_db_pass,
        "openrouter-key": openrouter_key,
        "database-url": litellm_db_url
    }
    for provider in ("openai", "anthropic", "mistral", "gemini"):
        litellm_secret_data[f"{provider}-key"] = llm_cfg.get(f"{provider}_api_key") or _get_existing_cluster_secret("litellm-secret", f"{provider}-key") or ""
    runner.apply_manifest(make_secret_manifest("litellm-secret", namespace, litellm_secret_data))

    # 3. hermes-gateway-secret
    hermes_key = hermes_cfg.get("api_token", "")
    if not hermes_key or hermes_key in KNOWN_INSECURE_SECRETS:
        hermes_key = _get_existing_cluster_secret("hermes-gateway-secret", "api-server-key") or f"arcia-pat-{secrets.token_urlsafe(24)}"
    hermes_pass = hermes_cfg.get("admin_password", "")
    if not hermes_pass or hermes_pass in KNOWN_INSECURE_SECRETS:
        hermes_pass = _get_existing_cluster_secret("hermes-gateway-secret", "admin-password") or secrets.token_urlsafe(16)

    runner.apply_manifest(make_secret_manifest("hermes-gateway-secret", namespace, {
        "api-server-key": hermes_key,
        "admin-password": hermes_pass
    }))

    # 4. presidio-secret
    presidio_key = presidio_cfg.get("master_key", "")
    if not presidio_key or presidio_key in KNOWN_INSECURE_SECRETS:
        presidio_key = _get_existing_cluster_secret("presidio-secret", "master-key") or f"arcia-presidio-{secrets.token_urlsafe(24)}"
    runner.apply_manifest(make_secret_manifest("presidio-secret", namespace, {
        "master-key": presidio_key
    }))

    # 5. entraid-secret (si SSO actif ou préservation du secret existant)
    existing_sso_tenant = _get_existing_cluster_secret("entraid-secret", "tenant-id")
    if existing_sso_tenant and not sso_cfg.get("enabled"):
        log_info(" -> Préservation de la configuration SSO Entra ID existante du cluster.")
        cfg.setdefault("entra_id_sso", {}).update({"tenant_id": existing_sso_tenant,
            "client_id": _get_existing_cluster_secret("entraid-secret", "client-id") or "",
            "client_secret": _get_existing_cluster_secret("entraid-secret", "client-secret") or "",
            "cookie_secret": _get_existing_cluster_secret("entraid-secret", "cookie-secret") or ""})
    else:
        sso_tenant = sso_cfg.get("tenant_id", "00000000-0000-0000-0000-000000000000") if sso_cfg.get("enabled") else "00000000-0000-0000-0000-000000000000"
        sso_client = sso_cfg.get("client_id", "placeholder-client-id") if sso_cfg.get("enabled") else "placeholder-client-id"
        sso_secret = sso_cfg.get("client_secret", "placeholder-client-secret") if sso_cfg.get("enabled") else "placeholder-client-secret"
        sso_cookie = sso_cfg.get("cookie_secret", "") if sso_cfg.get("enabled") else ""
        if not sso_cookie or sso_cookie in KNOWN_INSECURE_SECRETS:
            sso_cookie = _get_existing_cluster_secret("entraid-secret", "cookie-secret") or secrets.token_urlsafe(32)

        runner.apply_manifest(make_secret_manifest("entraid-secret", namespace, {
            "tenant-id": sso_tenant,
            "client-id": sso_client,
            "client-secret": sso_secret,
            "cookie-secret": sso_cookie
        }))
        cfg.setdefault("entra_id_sso", {}).update({"tenant_id": sso_tenant, "client_id": sso_client,
            "client_secret": sso_secret, "cookie_secret": sso_cookie})

    # 6. teams-bot-secret (si bot actif ou préservation du secret existant)
    existing_bot_app_id = _get_existing_cluster_secret("teams-bot-secret", "app-id")
    if teams_cfg.get("enabled") or existing_bot_app_id:
        bot_tenant_id = str(teams_cfg.get("tenant_id") or sso_cfg.get("tenant_id") or "").strip() or _get_existing_cluster_secret("teams-bot-secret", "tenant-id")
        app_id = str(teams_cfg.get("app_id") or existing_bot_app_id or "").strip()
        app_password = str(teams_cfg.get("app_password") or _get_existing_cluster_secret("teams-bot-secret", "app-password") or "").strip()
        if app_id and app_password:
            runner.apply_manifest(make_secret_manifest("teams-bot-secret", namespace, {
                "app-id": app_id,
                "app-password": app_password,
                "tenant-id": bot_tenant_id
            }))
            cfg.setdefault("teams_bot", {}).update({"app_id": app_id, "app_password": app_password, "tenant_id": bot_tenant_id or ""})
    elif _get_existing_cluster_secret("teams-bot-secret", "app-id"):
        log_info(" -> Préservation du secret Teams Bot existant du cluster.")

    # Sauvegarder les identités effectivement générées/préservées pour une reconstruction.
    cfg.setdefault("llm_gateway", {}).update({"master_key": litellm_master, "salt_key": litellm_salt,
        "db_password": litellm_db_pass, "openrouter_api_key": openrouter_key})
    for provider in ("openai", "anthropic", "mistral", "gemini"):
        cfg["llm_gateway"][provider + "_api_key"] = litellm_secret_data[provider + "-key"]
    cfg.setdefault("hermes", {}).update({"api_token": hermes_key, "admin_password": hermes_pass})
    cfg.setdefault("presidio", {})["master_key"] = presidio_key
    from services.instance_backup.configuration import persist_runtime_configuration
    persist_runtime_configuration(root_dir, cfg)
    log_ok("Secrets provisionnés et configuration effective conservée pour la sauvegarde.")

    # 4. Déploiement des Microservices Fondamentaux
    log_step(4, total_steps, "Déploiement des microservices du socle ArcIA")

    manifests_dir = os.path.join(root_dir, "deploy", "manifests")

    # A0. Synchronisation des ConfigMaps de code microservices depuis services/
    log_info(" -> Synchronisation des ConfigMaps de code microservices (services/)...")
    code_checksums = sync_service_configmaps(runner, namespace, root_dir)

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
    litellm_hash = code_checksums.get("litellm-error-handler", "v04")
    litellm_yaml = litellm_yaml.replace('checksum/litellm-error-handler: "default"', f'checksum/litellm-error-handler: "{litellm_hash}"')
    secret_hash = hashlib.sha256(json.dumps(litellm_secret_data, sort_keys=True).encode("utf-8")).hexdigest()
    runner.apply_manifest(render_model_manifest("litellm-proxy", litellm_yaml, cfg, namespace,
                                               code_checksums={**code_checksums, "litellm-secret": secret_hash}))
    log_ok("Catalogue de modèles et routage LiteLLM synchronisés avec succès.")

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

    runner.apply_manifest(render_model_manifest("hermes-agent", hermes_yaml, cfg, namespace))
    log_ok("Configuration agentique Hermes synchronisée avec succès.")


    # D. Open-WebUI Portal (avec espace persistant RAG, ChromaDB & corpus documentaire)
    log_info(" -> [Branding ArcIA] Injection de l'identité visuelle officielle (SVG & CSS)...")
    branding_state = sync_webui_branding(runner, namespace, root_dir, cfg=cfg)
    log_info(" -> Déploiement de Open-WebUI (07-open-webui.yaml)...")
    webui_path = os.path.join(manifests_dir, "07-open-webui.yaml")
    with open(webui_path, "r", encoding="utf-8") as f:
        webui_yaml = f.read()

    webui_storage = webui_cfg.get("storage_size", "50Gi")
    webui_yaml = re.sub(r'storage:\s*(?:20|50)Gi', f'storage: {webui_storage}', webui_yaml, count=1)
    if storage_class:
        webui_yaml = webui_yaml.replace("accessModes:\n  - ReadWriteOnce", f"accessModes:\n  - ReadWriteOnce\n  storageClassName: {storage_class}")
    runner.apply_manifest(render_model_manifest("open-webui", webui_yaml, cfg, namespace,
                                               branding_revision=branding_state["revision"]))
    log_ok("Portail Open-WebUI déployé avec catalogue restreint par connexion.")

    # E. Services Optionnels : Teams Bot et OAuth2-Proxy
    if teams_cfg.get("enabled") or existing_bot_app_id:
        log_info(" -> [Optionnel Activé] Déploiement de l'adaptateur Teams Bot (08-teams-bot.yaml)...")
        teams_path = os.path.join(manifests_dir, "08-teams-bot.yaml")
        with open(teams_path, "r", encoding="utf-8") as f:
            teams_yaml = f.read()
            prompt = teams_cfg.get("system_prompt", "Tu es ArcIA, l'assistant et orchestrateur agentique d'entreprise. Réponds de façon synthétique, professionnelle et structurée en Markdown.")
            teams_yaml = re.sub(r'value: "Tu es ArcIA.*?"', f'value: "{prompt}"', teams_yaml)
            teams_hash = code_checksums.get("teams-bot-code", "v04")
            teams_yaml = teams_yaml.replace('checksum/teams-bot-code: "default"', f'checksum/teams-bot-code: "{teams_hash}"')
            runner.apply_manifest(adapt_manifest_namespace(teams_yaml, namespace))
    else:
        log_info(" -> [Optionnel Ignoré] Adaptateur Microsoft Teams désactivé.")

    if sso_cfg.get("enabled") or existing_sso_tenant:
        log_info(" -> [Optionnel Activé] Déploiement du proxy SSO Entra ID (02-oauth2-proxy.yaml)...")
        oauth_path = os.path.join(manifests_dir, "02-oauth2-proxy.yaml")
        with open(oauth_path, "r", encoding="utf-8") as f:
            runner.apply_manifest(adapt_manifest_namespace(f.read(), namespace))
    else:
        log_info(" -> [Optionnel Ignoré] Authentification SSO Entra ID désactivée.")

    # F. Synchronisation Automatique des Compétences & Outils (Skills)
    log_info(" -> [Automatique] Synchronisation des compétences natives (Ponytail, Graphify, Public-APIs)...")
    sync_native_skills(runner, namespace, root_dir)

    # G. Politiques Réseau d'Isolation (NetworkPolicies)
    netpol_path = os.path.join(manifests_dir, "09-network-policy.yaml")
    if os.path.isfile(netpol_path):
        log_info(" -> [Sécurité Réseau] Déploiement des NetworkPolicies d'isolation (09-network-policy.yaml)...")
        with open(netpol_path, "r", encoding="utf-8") as f:
            runner.apply_manifest(adapt_manifest_namespace(f.read(), namespace))
        log_ok("NetworkPolicies d'isolation appliquées au namespace.")

    # 5. Gestion des Certificats TLS & Ingress
    log_step(5, total_steps, "Configuration du routage Ingress et des Certificats TLS")

    custom_cert = net_cfg.get("tls_cert", "").strip()
    custom_key = net_cfg.get("tls_key", "").strip()
    acme_account_key = net_cfg.get("acme_account_key", "").strip()
    acme_dns_txt = net_cfg.get("acme_dns_txt", "").strip()

    if custom_cert and custom_key:
        log_info(f" -> Injection du certificat TLS personnalisé déclaré pour '{public_fqdn}'...")
        runner.apply_manifest(make_secret_manifest(tls_secret_name, namespace, {
            "tls.crt": custom_cert,
            "tls.key": custom_key
        }, secret_type="kubernetes.io/tls"))
        log_ok(f"Secret TLS '{tls_secret_name}' provisionné avec le certificat configuré.")
    else:
        # Vérification si le secret TLS existe déjà sur le cluster
        rc_tls, _, _ = runner.run(["get", "secret", tls_secret_name, f"-n={namespace}"])
        if rc_tls == 0:
            log_ok(f"Secret TLS existant '{tls_secret_name}' préservé sur le cluster.")
        else:
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
        if acme_account_key:
            log_info(f" -> Injection de la clé de compte ACME pour Let's Encrypt ({tls_mode}-key)...")
            runner.apply_manifest(make_secret_manifest(f"{tls_mode}-key", namespace, {
                "tls.key": acme_account_key
            }))
        if acme_dns_txt:
            log_info(f" -> [Validation ACME DNS] Entrée TXT enregistrée pour '{public_fqdn}' : _acme-challenge.{public_fqdn} = {acme_dns_txt}")

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
    if teams_cfg.get("enabled") or existing_bot_app_id:
        teams_path_block = """      - path: /api/messages
        pathType: Prefix
        backend:
          service:
            name: teams-bot-adapter
            port:
              number: 3978
      - path: /api/teams/messages
        pathType: Prefix
        backend:
          service:
            name: teams-bot-adapter
            port:
              number: 3978"""

    oauth_path_block = ""
    studio_middlewares = f"{namespace}-studio-prefix@kubernetescrd,{namespace}-studio-stripprefix@kubernetescrd"
    if sso_cfg.get("enabled") or existing_sso_tenant:
        oauth_path_block = """      - path: /oauth2
        pathType: Prefix
        backend:
          service:
            name: oauth2-proxy
            port:
              number: 4180"""
        studio_middlewares = f"{namespace}-entra-id-auth@kubernetescrd,{studio_middlewares}"

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
# 3. Ingress Studio (Hermes Studio Dashboard)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: arcia-studio-ingress
  namespace: {namespace}
  annotations:
{ingress_annotations}
    traefik.ingress.kubernetes.io/router.middlewares: {studio_middlewares}
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
# 5. Middlewares Traefik (RateLimit, Studio Prefix/StripPrefix, Gateway StripPrefix)
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

    legacy_key = retire_legacy_webui_key(runner, namespace, root_dir)
    if legacy_key.get("verified_absent"):
        log_ok("Ancienne clé statique Open-WebUI absente ; clés nominatives préservées.")
    else:
        log_warn("Retrait de l'ancienne clé statique différé : connexion du portail non vérifiée.")

    # 6b. Réconciliation et synchronisation universelle des instances Power Users
    restored_powerusers = reconcile_powerusers(cfg, runner)
    sync_private_runtimes(cfg, runner, namespace, root_dir)
    if restored_powerusers:
        log_ok(f"{restored_powerusers} déclaration(s) Power User réappliquée(s) ; données PVC à restaurer séparément.")
    log_info(" -> [Power Users] Synchronisation du catalogue de modèles sur l'ensemble des instances...")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from arcia_poweruser import sync_all_powerusers
        def _deploy_runner(cmd_args, input_data=None):
            rc, out, err = runner.run(cmd_args, stdin_input=input_data)
            return subprocess.CompletedProcess(cmd_args, rc, out, err)
        protected_slugs = {user["poweruser_slug"] for user in declared_users(cfg) if user.get("poweruser_slug")}
        synced = sync_all_powerusers(namespace=namespace, fqdn=public_fqdn, runner_func=_deploy_runner, preserve_slugs=protected_slugs)
        if synced > 0:
            log_ok(f"{synced} instance(s) Power User synchronisée(s) avec le catalogue de modèles.")
    except Exception as exc:
        log_warn(f"Synchronisation automatique des Power Users ignorée : {exc}")

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
