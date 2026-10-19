#!/usr/bin/env python3
"""
ArcIA v0.5.2 — Spawner Kubernetes d'Instances Dédiées Power Users (Hermes Agent)

Permet de déployer, gérer, suspendre et supprimer des environnements Hermes Agent
dédiés par utilisateur directement dans le cluster Kubernetes.
Zéro agent local sur PC : chaque Power User dispose de son propre Pod, de son
propre volume persistant (PVC), de sa propre SOUL.md et de son état SQLite isolé.
"""

import sys
import os
import re
import json
import secrets
import argparse
import subprocess
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(ROOT_DIR, "deploy", "manifests", "templates", "hermes-poweruser.template.yaml")
CONFIG_PATH = os.path.join(ROOT_DIR, "arcia.config.yaml")


def load_arcia_config() -> Dict[str, Any]:
    """Charge la configuration globale arcia.config.yaml si présente."""
    if not os.path.isfile(CONFIG_PATH):
        return {}
    try:
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        # Fallback parsing regex si PyYAML n'est pas installé
        cfg = {}
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        fqdn = re.search(r'public_fqdn:\s*"([^"]+)"', content)
        if fqdn:
            cfg.setdefault("network", {})["public_fqdn"] = fqdn.group(1)
        ns = re.search(r'namespace:\s*"([^"]+)"', content)
        if ns:
            cfg.setdefault("kubernetes", {})["namespace"] = ns.group(1)
        vpn = re.search(r'enable_vpn:\s*(true|false)', content, re.IGNORECASE)
        if vpn:
            cfg.setdefault("powerusers", {})["enable_vpn"] = (vpn.group(1).lower() == "true")
        return cfg


def email_to_slug(email: str) -> str:
    """Convertit une adresse email en identifiant Kubernetes valide (DNS-1123)."""
    local_part = email.split("@")[0].lower()
    slug = re.sub(r"[^a-z0-9\-]", "-", local_part)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        slug = f"user-{secrets.token_hex(4)}"
    return slug[:40]


def run_kubectl(cmd_args: List[str], input_data: Optional[str] = None) -> subprocess.CompletedProcess:
    """Exécute une commande kubectl localement ou via scripts/Invoke-K3s.ps1 sous Windows."""
    # 1. Si kubectl est disponible directement
    try:
        res = subprocess.run(["kubectl", "version", "--client"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0:
            full_cmd = ["kubectl"] + cmd_args
            return subprocess.run(full_cmd, input=input_data, text=True, capture_output=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        pass

    # 2. Sous Windows, déléguer à Invoke-K3s.ps1 si présent
    invoke_k3s = os.path.join(ROOT_DIR, "scripts", "Invoke-K3s.ps1")
    if os.path.isfile(invoke_k3s) and sys.platform.startswith("win"):
        ps_cmd = " ".join(cmd_args)
        cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", invoke_k3s, "-Command", ps_cmd]
        return subprocess.run(cmd, input=input_data, text=True, capture_output=True, encoding="utf-8", errors="replace")

    raise RuntimeError("Ni kubectl direct ni scripts/Invoke-K3s.ps1 ne sont disponibles pour communiquer avec le cluster.")


def generate_litellm_pat(user_email: str, team: str = "engineering", max_budget: float = 200.0) -> str:
    """Génère un jeton PAT nominatif pour le Power User."""
    # Tente d'appeler l'API LiteLLM interne ou génère un token cryptographique de format conforme
    # En environnement de spawn K8s, génère un jeton conforme
    token_suffix = secrets.token_urlsafe(32)
    return f"sk-arcia-pat-{email_to_slug(user_email)}-{token_suffix}"


def render_manifest(user_email: str,
                    team: str = "engineering",
                    job_title: str = "Ingénieur / Expert",
                    manager: str = "Direction Technique",
                    custom_soul: Optional[str] = None,
                    storage_size: str = "10Gi",
                    public_fqdn: Optional[str] = None,
                    namespace: str = "arcia",
                    litellm_pat: Optional[str] = None,
                    studio_password: Optional[str] = None,
                    enable_vpn: Optional[bool] = None,
                    config: Optional[Dict[str, Any]] = None,
                    replicas: int = 1) -> str:
    """Génère le manifeste complet Kubernetes pour le Power User."""
    slug = email_to_slug(user_email)
    cfg = load_arcia_config() if config is None else config
    if type(replicas) is not int or replicas not in (0, 1):
        raise ValueError("Une instance Hermes doit avoir zéro ou un propriétaire actif.")
    fqdn = public_fqdn or cfg.get("network", {}).get("public_fqdn", "assistant.example.org")
    ns = namespace or cfg.get("kubernetes", {}).get("namespace", "arcia")
    pat = litellm_pat or generate_litellm_pat(user_email, team=team)
    pwd = studio_password or secrets.token_urlsafe(16)

    # Résolution du paramètre VPN (soit argument explicite, soit configuration d'instance arcia.config.yaml)
    if enable_vpn is None:
        enable_vpn = bool(cfg.get("powerusers", {}).get("enable_vpn", False))

    # 1. SOUL par défaut
    if not custom_soul:
        soul_text = f"""# Soul d'Entreprise — Profil Dédié Power User ({slug})
Tu es l'agent autonome personnel de {user_email}.
Tu disposes de ton propre environnement d'exécution persistant sur Kubernetes.

## Voice
- Style professionnel, rigoureux, direct et structuré.
- Priorité à la clarté technique, aux étapes vérifiables et au code opérationnel.

## Operations
- Planifie toujours les actions multi-étapes avant exécution.
- Respecte scrupuleusement la confidentialité des données et les quotas alloués.
"""
    else:
        soul_text = custom_soul.strip()

    # 2. USER.md par défaut
    user_text = f"""# Profil Power User
- Email : {user_email}
- Identifiant : {slug}
- Équipe : {team}
- Fonction : {job_title}
- Responsable : {manager}
- Statut : Instance Dédiée Kubernetes Active
"""

    def indent_lines(text: str, spaces: int = 4) -> str:
        prefix = " " * spaces
        return "\n".join(prefix + line if line.strip() else "" for line in text.strip().splitlines())

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    sys.path.insert(0, ROOT_DIR)
    sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))
    import deploy
    hermes_cfg_yaml = deploy.build_hermes_config_data(cfg, namespace=ns)

    rendered = template
    rendered = rendered.replace("{{USER_SLUG}}", slug)
    rendered = rendered.replace("{{NAMESPACE}}", ns)
    rendered = rendered.replace("{{STORAGE_SIZE}}", storage_size)
    rendered = rendered.replace("{{PUBLIC_FQDN}}", fqdn)
    # Les placeholders sont déjà entre guillemets YAML dans le template.
    rendered = rendered.replace("{{LITELLM_PAT}}", json.dumps(pat, ensure_ascii=False)[1:-1])
    rendered = rendered.replace("{{STUDIO_PASSWORD}}", json.dumps(pwd, ensure_ascii=False)[1:-1])
    rendered, count = re.subn(r"(?m)^  replicas: 1$", f"  replicas: {replicas}", rendered, count=1)
    if count != 1:
        raise ValueError("Le template Power User ne déclare pas sa réplique unique.")
    rendered = rendered.replace("{{HERMES_CONFIG_INDENTED}}", indent_lines(hermes_cfg_yaml, 4))
    rendered = rendered.replace("{{SOUL_CONTENT_INDENTED}}", indent_lines(soul_text, 4))
    rendered = rendered.replace("{{USER_CONTENT_INDENTED}}", indent_lines(user_text, 4))

    if enable_vpn:
        vpn_sec_ctx = """        securityContext:
          capabilities:
            add:
            - NET_ADMIN"""
        vpn_init_install = """          which openconnect >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq openconnect iproute2 iptables 2>/dev/null || true)"""
        vpn_vol_mounts = """        - name: dev-net-tun
          mountPath: /dev/net/tun"""
        vpn_volumes = """      - name: dev-net-tun
        hostPath:
          path: /dev/net/tun"""
    else:
        vpn_sec_ctx = ""
        vpn_init_install = ""
        vpn_vol_mounts = ""
        vpn_volumes = ""

    rendered = rendered.replace("{{VPN_CONTAINER_SECURITY_CONTEXT}}", vpn_sec_ctx)
    rendered = rendered.replace("{{VPN_INIT_INSTALL}}", vpn_init_install)
    rendered = rendered.replace("{{VPN_CONTAINER_VOLUME_MOUNTS}}", vpn_vol_mounts)
    rendered = rendered.replace("{{VPN_POD_VOLUMES}}", vpn_volumes)

    return rendered


def register_litellm_pat(pat: str, user_email: str, team: str = "engineering", max_budget: float = 200.0, ns: str = "arcia"):
    """Enregistre le jeton PAT dans LiteLLM pour autoriser l'inférence du Power User."""
    slug = email_to_slug(user_email)
    py_code = f"""
import os, json, urllib.request
k = os.environ.get('LITELLM_MASTER_KEY')
payload = json.dumps({{
    'key': '{pat}',
    'key_alias': 'pat-{slug}',
    'user_id': '{user_email}',
    'max_budget': {max_budget}
}}).encode()
req = urllib.request.Request(
    'http://localhost:4000/key/generate',
    data=payload,
    headers={{'Authorization': f'Bearer {{k}}', 'Content-Type': 'application/json'}}
)
try:
    resp = urllib.request.urlopen(req)
    print('[OK] LiteLLM PAT enregistré avec succès.')
except Exception as e:
    print(f'[WARN] LiteLLM PAT non enregistré: {{e}}')
"""
    cmd = ["exec", "-i", "deployment/litellm-proxy", "-n", ns, "--", "python3"]
    try:
        proc = run_kubectl(cmd, input_data=py_code)
        if proc.stdout:
            print(f"    {proc.stdout.strip()}")
    except Exception as e:
        print(f"    [WARN] Erreur enregistrement PAT LiteLLM: {e}")


def unregister_litellm_pat(user_email: str, ns: str = "arcia"):
    """Supprime le jeton PAT de LiteLLM lors de la destruction de l'instance."""
    slug = email_to_slug(user_email)
    py_code = f"""
import os, json, urllib.request
k = os.environ.get('LITELLM_MASTER_KEY')
req = urllib.request.Request(
    'http://localhost:4000/key/list',
    headers={{'Authorization': f'Bearer {{k}}'}}
)
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
        print('[OK] LiteLLM PAT révoqué avec succès.')
except Exception:
    pass
"""
    cmd = ["exec", "-i", "deployment/litellm-proxy", "-n", ns, "--", "python3"]
    try:
        run_kubectl(cmd, input_data=py_code)
    except Exception:
        pass


def cmd_spawn(args):
    """Déploie une instance dédiée pour un Power User sur Kubernetes."""
    slug = email_to_slug(args.email)
    cfg = load_arcia_config()
    fqdn = args.fqdn or cfg.get("network", {}).get("public_fqdn", "assistant.example.org")
    ns = args.namespace or cfg.get("kubernetes", {}).get("namespace", "arcia")

    soul_content = None
    if args.soul_file and os.path.isfile(args.soul_file):
        with open(args.soul_file, "r", encoding="utf-8") as f:
            soul_content = f.read()
    elif args.soul:
        soul_content = args.soul

    existing_pwd = None
    existing_pat = None
    try:
        proc_sec = run_kubectl(["get", "secret", f"hermes-user-{slug}-secret", "-n", ns, "-o", "json"])
        if proc_sec.returncode == 0:
            sec_data = json.loads(proc_sec.stdout).get("data", {})
            import base64
            if "studio-password" in sec_data:
                existing_pwd = base64.b64decode(sec_data["studio-password"]).decode("utf-8")
            if "litellm-pat" in sec_data:
                existing_pat = base64.b64decode(sec_data["litellm-pat"]).decode("utf-8")
    except Exception:
        pass

    pat = args.pat or existing_pat or generate_litellm_pat(args.email, team=args.team)
    pwd = args.password or existing_pwd or secrets.token_urlsafe(16)

    manifest = render_manifest(
        user_email=args.email,
        team=args.team,
        job_title=args.job_title,
        manager=args.manager,
        custom_soul=soul_content,
        storage_size=args.storage,
        public_fqdn=fqdn,
        namespace=ns,
        litellm_pat=pat,
        studio_password=pwd,
        enable_vpn=getattr(args, "vpn", None)
    )

    if args.dry_run:
        print(manifest)
        return

    print(f"[*] Déploiement de l'instance Hermes Power User pour {args.email}...")
    print(f"    Slug Kubernetes  : {slug}")
    print(f"    Namespace        : {ns}")
    print(f"    Volume persistant: {args.storage}")
    print(f"    URL Studio       : https://{fqdn}/poweruser/{slug}/studio")

    proc = run_kubectl(["apply", "-f", "-"], input_data=manifest)
    if proc.returncode != 0:
        print(f"[ERREUR] Échec du déploiement Kubernetes :", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        sys.exit(proc.returncode)

    print("[*] Enregistrement du jeton PAT dans LiteLLM Proxy...")
    register_litellm_pat(pat, args.email, team=args.team, ns=ns)

    print("\n[OK] Instance Power User déployée avec succès !")
    print(f"  - Dashboard Studio : https://{fqdn}/poweruser/{slug}/studio")
    print(f"  - Identifiant      : {slug}")
    print(f"  - Mot de passe     : {pwd}")
    print(f"  - PAT d'inférence  : {pat}")
    print("\nL'agent démarre dans son propre Pod avec son PVC isolé et sa SOUL dédiée.")


def cmd_list(args):
    """Liste l'ensemble des instances Power Users actives dans le cluster."""
    cfg = load_arcia_config()
    ns = args.namespace or cfg.get("kubernetes", {}).get("namespace", "arcia")

    print(f"[*] Recherche des instances Hermes Power Users dans le namespace '{ns}'...")
    proc = run_kubectl(["get", "deployments", "-n", ns, "-l", "arcia.io/role=poweruser", "-o", "json"])
    if proc.returncode != 0:
        print(f"[ERREUR] Impossible de lister les déploiements : {proc.stderr}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(proc.stdout)
        items = data.get("items", [])
    except Exception as e:
        print(f"[ERREUR] Sortie non JSON reçue : {e}", file=sys.stderr)
        sys.exit(1)

    if not items:
        print(f"[-] Aucune instance Power User active trouvée dans '{ns}'.")
        return

    print(f"\n[+] {len(items)} instance(s) Power User déployée(s) :")
    print(f"{'DÉPLOIEMENT':<32} {'RÉPLIQUES':<12} {'DISPONIBLE':<12} {'STATUT'}")
    print("-" * 70)
    for it in items:
        name = it["metadata"]["name"]
        replicas = it["spec"].get("replicas", 0)
        available = it.get("status", {}).get("availableReplicas", 0)
        status = "ACTIF (Running)" if available > 0 else ("EN VEILLE (Scale=0)" if replicas == 0 else "DÉMARRAGE")
        print(f"{name:<32} {replicas:<12} {available:<12} {status}")


def sync_single_user(slug: str, ns: str = "arcia", fqdn: Optional[str] = None, runner_func=run_kubectl) -> bool:
    """Synchronise une instance Power User existante avec les derniers modèles et templates."""
    cfg = load_arcia_config()
    fqdn = fqdn or cfg.get("network", {}).get("public_fqdn", "assistant.example.org")

    # 1. Secret existant (préserver mot de passe et PAT)
    pwd, pat = None, None
    proc_sec = runner_func(["get", "secret", f"hermes-user-{slug}-secret", "-n", ns, "-o", "json"])
    if proc_sec.returncode == 0:
        sec_data = json.loads(proc_sec.stdout).get("data", {})
        import base64
        if "studio-password" in sec_data:
            pwd = base64.b64decode(sec_data["studio-password"]).decode("utf-8")
        if "litellm-pat" in sec_data:
            pat = base64.b64decode(sec_data["litellm-pat"]).decode("utf-8")

    # 2. ConfigMap existant (préserver SOUL.md et USER.md)
    custom_soul = None
    user_email = f"{slug}@example.org"
    team = "engineering"
    job_title = "Expert / Ingénieur"
    manager = "Direction Technique"
    proc_cm = runner_func(["get", "configmap", f"hermes-user-{slug}-config", "-n", ns, "-o", "json"])
    if proc_cm.returncode == 0:
        cm_data = json.loads(proc_cm.stdout).get("data", {})
        if "SOUL.md" in cm_data:
            custom_soul = cm_data["SOUL.md"]
        if "USER.md" in cm_data:
            user_md = cm_data["USER.md"]
            m_email = re.search(r"- Email\s*:\s*([^\r\n]+)", user_md)
            if m_email:
                user_email = m_email.group(1).strip()
            m_team = re.search(r"- (?:Équipe|Equipe)\s*:\s*([^\r\n]+)", user_md)
            if m_team:
                team = m_team.group(1).strip()
            m_job = re.search(r"- Fonction\s*:\s*([^\r\n]+)", user_md)
            if m_job:
                job_title = m_job.group(1).strip()
            m_mgr = re.search(r"- Responsable\s*:\s*([^\r\n]+)", user_md)
            if m_mgr:
                manager = m_mgr.group(1).strip()

    # 3. Détecter si le VPN était activé dans le déploiement
    vpn_enabled = False
    proc_dep = runner_func(["get", "deployment", f"hermes-poweruser-{slug}", "-n", ns, "-o", "json"])
    if proc_dep.returncode == 0:
        dep_json = json.loads(proc_dep.stdout)
        containers = dep_json.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        for c in containers:
            if c.get("name") == "hermes":
                caps = c.get("securityContext", {}).get("capabilities", {}).get("add", [])
                if "NET_ADMIN" in caps:
                    vpn_enabled = True

    # 4. Rendu et application du manifeste mis à jour
    manifest = render_manifest(
        user_email=user_email,
        team=team,
        job_title=job_title,
        manager=manager,
        custom_soul=custom_soul,
        public_fqdn=fqdn,
        namespace=ns,
        litellm_pat=pat,
        studio_password=pwd,
        enable_vpn=vpn_enabled
    )

    proc_apply = runner_func(["apply", "-f", "-"], input_data=manifest)
    if proc_apply.returncode != 0:
        print(f"    [WARN] Échec apply : {proc_apply.stderr}")
        return False

    # 5. Enregistrement PAT LiteLLM
    if pat:
        register_litellm_pat(pat, user_email, team=team, ns=ns)

    # 6. Synchronisation à chaud du pod en cours d'exécution
    cfg = load_arcia_config()
    sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))
    import deploy
    catalog = deploy.build_model_catalog(cfg)
    agentic_models = catalog["agentic_models"]
    default_agentic = catalog["default_agentic"] or (agentic_models[0] if agentic_models else "")
    models_repr = json.dumps(agentic_models)
    def_repr = json.dumps(default_agentic)
    routes_dict = {m: {"model": m} for m in agentic_models}
    routes_repr = json.dumps(routes_dict)

    sync_code = f"""
import sys; sys.path.insert(0, '/opt/hermes'); import hermes_yaml
cfg_p = '/opt/data/.hermes/config.yaml'
try:
    with open(cfg_p) as f: c = hermes_yaml.safe_load(f) or {{}}
    c.setdefault('providers', {{}})['custom'] = {{
        'name': 'ArcIA Agentic',
        'base_url': 'http://litellm-proxy.{ns}.svc:4000/v1',
        'key_env': 'OPENAI_API_KEY',
        'discover_models': False,
        'models': {models_repr}
    }}
    c.setdefault('platforms', {{}}).setdefault('api_server', {{}})['model_name'] = {def_repr}
    c.setdefault('platforms', {{}}).setdefault('api_server', {{}})['model_routes'] = {routes_repr}
    with open(cfg_p, 'w') as f: hermes_yaml.safe_dump(c, f)
    with open('/opt/data/config.yaml', 'w') as f: hermes_yaml.safe_dump(c, f)
except Exception: pass
"""
    runner_func(["exec", "-i", f"deployment/hermes-poweruser-{slug}", "-c", "hermes", "-n", ns, "--", "/opt/hermes/.venv/bin/python"], input_data=sync_code)
    return True


def sync_all_powerusers(namespace: str = "arcia", fqdn: Optional[str] = None, runner_func=run_kubectl) -> int:
    """Fonction universelle pour réconcilier toutes les instances Power Users."""
    cfg = load_arcia_config()
    fqdn = fqdn or cfg.get("network", {}).get("public_fqdn", "assistant.example.org")
    ns = namespace

    print(f"[*] Détection des instances Power Users à réconcilier dans '{ns}'...")
    proc = runner_func(["get", "deployments", "-n", ns, "-l", "arcia.io/role=poweruser", "-o", "json"])
    if proc.returncode != 0:
        return 0

    try:
        data = json.loads(proc.stdout)
        items = data.get("items", [])
    except Exception:
        return 0

    if not items:
        print(f"[-] Aucune instance Power User à synchroniser.")
        return 0

    synced_count = 0
    print(f"[+] Synchronisation de {len(items)} instance(s) Power User avec le catalogue de modèles...")
    for it in items:
        dep_name = it["metadata"]["name"]
        slug = it["metadata"].get("labels", {}).get("app.kubernetes.io/instance") or dep_name.replace("hermes-poweruser-", "")
        print(f"  -> Synchronisation de '{slug}'...")
        if sync_single_user(slug=slug, ns=ns, fqdn=fqdn, runner_func=runner_func):
            synced_count += 1
            print(f"     [OK] '{slug}' à jour.")
    return synced_count


def cmd_sync_all(args):
    """Commande CLI pour synchroniser toutes les instances Power Users existantes."""
    cfg = load_arcia_config()
    ns = args.namespace or cfg.get("kubernetes", {}).get("namespace", "arcia")
    fqdn = args.fqdn or cfg.get("network", {}).get("public_fqdn", "assistant.example.org")
    sync_all_powerusers(namespace=ns, fqdn=fqdn)


def cmd_stop(args):
    """Met en veille le Pod de l'utilisateur (replicas=0) pour libérer la RAM."""
    slug = email_to_slug(args.email)
    cfg = load_arcia_config()
    ns = args.namespace or cfg.get("kubernetes", {}).get("namespace", "arcia")
    dep_name = f"hermes-poweruser-{slug}"

    print(f"[*] Mise en veille de l'instance '{dep_name}' dans '{ns}' (libération de la RAM)...")
    proc = run_kubectl(["scale", f"deployment/{dep_name}", "--replicas=0", "-n", ns])
    if proc.returncode != 0:
        print(f"[ERREUR] {proc.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"[OK] Instance '{dep_name}' mise en veille. Le volume PVC et state.db restent intacts.")


def cmd_start(args):
    """Réveille le Pod de l'utilisateur (replicas=1)."""
    slug = email_to_slug(args.email)
    cfg = load_arcia_config()
    ns = args.namespace or cfg.get("kubernetes", {}).get("namespace", "arcia")
    dep_name = f"hermes-poweruser-{slug}"

    print(f"[*] Réveil de l'instance '{dep_name}' dans '{ns}'...")
    proc = run_kubectl(["scale", f"deployment/{dep_name}", "--replicas=1", "-n", ns])
    if proc.returncode != 0:
        print(f"[ERREUR] {proc.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"[OK] Instance '{dep_name}' réactivée.")


def cmd_destroy(args):
    """Supprime l'instance Power User."""
    slug = email_to_slug(args.email)
    cfg = load_arcia_config()
    ns = args.namespace or cfg.get("kubernetes", {}).get("namespace", "arcia")

    print(f"[!] Suppression de l'instance '{slug}' dans '{ns}'...")
    run_kubectl(["delete", "deployment", f"hermes-poweruser-{slug}", "-n", ns, "--ignore-not-found=true"])
    run_kubectl(["delete", "service", f"hermes-poweruser-{slug}", "-n", ns, "--ignore-not-found=true"])
    run_kubectl(["delete", "ingress", f"hermes-poweruser-{slug}-ingress", "-n", ns, "--ignore-not-found=true"])
    run_kubectl(["delete", "configmap", f"hermes-user-{slug}-config", "-n", ns, "--ignore-not-found=true"])
    run_kubectl(["delete", "secret", f"hermes-user-{slug}-secret", "-n", ns, "--ignore-not-found=true"])
    run_kubectl(["delete", "middleware", f"hermes-poweruser-{slug}-stripprefix", "-n", ns, "--ignore-not-found=true"])

    if not args.keep_pvc:
        run_kubectl(["delete", "pvc", f"hermes-user-{slug}-pvc", "-n", ns, "--ignore-not-found=true"])
        print(f"[+] Volume persistant PVC hermes-user-{slug}-pvc supprimé.")
    else:
        print(f"[*] Le volume persistant PVC hermes-user-{slug}-pvc a été conservé.")

    unregister_litellm_pat(args.email, ns=ns)
    print(f"[OK] Instance '{slug}' supprimée.")


def main():
    parser = argparse.ArgumentParser(description="ArcIA v0.5.2 — Gestionnaire de Pods Hermes Power Users sur Kubernetes")
    parser.add_argument("--namespace", default="arcia", help="Namespace Kubernetes cible")
    parser.add_argument("--fqdn", default=None, help="FQDN public de la plateforme (ex: assistant.entreprise.com)")

    sub = parser.add_subparsers(dest="action", required=True)

    # spawn
    p_spawn = sub.add_parser("spawn", help="Déployer un Pod Hermes dédié pour un Power User")
    p_spawn.add_argument("email", help="Email du collaborateur (ex: claire.dubois@entreprise.com)")
    p_spawn.add_argument("--team", default="engineering", help="Nom de l'équipe")
    p_spawn.add_argument("--job-title", default="Expert / Ingénieur", help="Intitulé du poste")
    p_spawn.add_argument("--manager", default="Direction Technique", help="Nom du responsable")
    p_spawn.add_argument("--soul", default=None, help="Texte direct pour la SOUL.md")
    p_spawn.add_argument("--soul-file", default=None, help="Fichier Markdown contenant la SOUL.md")
    p_spawn.add_argument("--storage", default="10Gi", help="Taille du volume PVC (défaut: 10Gi)")
    p_spawn.add_argument("--pat", default=None, help="Clé virtuelle LiteLLM (générée auto si omise)")
    p_spawn.add_argument("--password", default=None, help="Mot de passe Studio (généré auto si omis)")
    p_spawn.add_argument("--vpn", dest="vpn", action="store_true", default=None, help="Activer le support VPN (NET_ADMIN et /dev/net/tun)")
    p_spawn.add_argument("--no-vpn", dest="vpn", action="store_false", help="Désactiver le support VPN")
    p_spawn.add_argument("--dry-run", action="store_true", help="Afficher le YAML sans l'appliquer")
    p_spawn.set_defaults(func=cmd_spawn)

    # list
    p_list = sub.add_parser("list", help="Lister les instances Power Users")
    p_list.set_defaults(func=cmd_list)

    # sync-all
    p_sync = sub.add_parser("sync-all", help="Synchroniser toutes les instances Power Users avec les derniers modèles et templates")
    p_sync.set_defaults(func=cmd_sync_all)

    # stop
    p_stop = sub.add_parser("stop", help="Mettre en veille le Pod (scale=0)")
    p_stop.add_argument("email", help="Email du collaborateur")
    p_stop.set_defaults(func=cmd_stop)

    # start
    p_start = sub.add_parser("start", help="Réveiller le Pod (scale=1)")
    p_start.add_argument("email", help="Email du collaborateur")
    p_start.set_defaults(func=cmd_start)

    # destroy
    p_destroy = sub.add_parser("destroy", help="Supprimer une instance Power User")
    p_destroy.add_argument("email", help="Email du collaborateur")
    p_destroy.add_argument("--keep-pvc", action="store_true", help="Conserver le PVC persistant")
    p_destroy.set_defaults(func=cmd_destroy)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
