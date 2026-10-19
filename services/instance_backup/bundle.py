"""Fichiers de configuration portables, exclusivement à l'intérieur du bundle chiffré."""
import base64
import copy
import hashlib
import os
import re
from pathlib import Path

MAX_FILES = 128
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
FILE_FIELDS = {"config_file", "cert_file", "key_file", "ca_file", "deny_list_file", "known_hosts_file"}
KNOWN_FIELDS = {("kubernetes", "kubeconfig"), ("kubernetes", "remote_ssh", "ssh_key"),
                ("vmware", "auth", "ssh_key_path")}


def references(cfg):
    """Ignorer les modules désactivés et les chemins de volumes distants."""
    found = []
    def walk(value, binding=()):
        if isinstance(value, dict):
            if value.get("enabled") is False:
                return
            for key, child in value.items():
                path = binding + (key,)
                if isinstance(child, str) and child.strip() and (path in KNOWN_FIELDS or key in FILE_FIELDS):
                    found.append((path, child))
                elif path == ("instance_backup", "additional_files") and isinstance(child, list):
                    for index, item in enumerate(child):
                        if not isinstance(item, str) or not item.strip():
                            raise ValueError("Déclaration des fichiers de configuration supplémentaires invalide.")
                        found.append((path + (index,), item))
                else:
                    walk(child, path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, binding + (index,))
    walk(cfg)
    return found


def source_path(root, value):
    path = Path(os.path.expandvars(os.path.expanduser(value)))
    return path if path.is_absolute() else Path(root) / path


def _regular(path):
    return not any(p.is_symlink() for p in (path, *path.parents)) and path.is_file()


def _portable_kubeconfig(path, content):
    """Embarquer CA/certificat/clé référencés, sans exécuter de plugin d'identité."""
    import json
    try:
        try:
            import yaml
        except ImportError:
            from scripts.deploy import parse_simple_yaml
            config = parse_simple_yaml(content.decode("utf-8-sig"))
        else:
            config = yaml.safe_load(content.decode("utf-8-sig"))
    except Exception:
        raise ValueError("Kubeconfig illisible pour la sauvegarde portable.") from None
    if not isinstance(config, dict):
        raise ValueError("Kubeconfig invalide pour la sauvegarde portable.")
    changed = False
    def inline(value):
        nonlocal changed
        if isinstance(value, dict):
            for field in ("certificate-authority", "client-certificate", "client-key"):
                if field in value:
                    reference = value[field]
                    if not isinstance(reference, str):
                        raise ValueError("Référence de certificat Kubernetes invalide.")
                    if field + "-data" not in value:
                        target = source_path(path.parent, reference)
                        if not _regular(target) or target.stat().st_size > MAX_FILE_BYTES:
                            raise ValueError("Certificat Kubernetes référencé inaccessible.")
                        value[field + "-data"] = base64.b64encode(target.read_bytes()).decode("ascii")
                    del value[field]
                    changed = True
            for child in value.values():
                inline(child)
        elif isinstance(value, list):
            for child in value:
                inline(child)
    inline(config)
    return json.dumps(config, ensure_ascii=False, indent=2).encode() if changed else content


def collect(root, cfg):
    """Ne jamais parcourir aveuglément le dépôt, le home, les volumes ou le coffre."""
    assets, missing, total = [], [], 0
    for binding, value in references(cfg):
        path = source_path(root, value)
        if path.name in {"instance-backup.dpapi", "instance-backup-status.json"} or "backup-pending" in path.parts or path.name.startswith("pre-restore-"):
            raise ValueError("Le coffre de sauvegarde et les archives ne sont pas des fichiers de configuration exportables.")
        if not _regular(path):
            missing.append(".".join(map(str, binding)))
            continue
        if path.stat().st_size > MAX_FILE_BYTES or len(assets) >= MAX_FILES:
            raise ValueError("Limite des fichiers de configuration dépassée ; sauvegarde incomplète refusée.")
        content = path.read_bytes()
        if binding == ("kubernetes", "kubeconfig"):
            content = _portable_kubeconfig(path, content)
        if len(content) > MAX_FILE_BYTES:
            raise ValueError("Limite de taille d'un fichier de configuration dépassée.")
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Volume des fichiers de configuration trop important ; sauvegarde incomplète refusée.")
        assets.append({"binding": list(binding), "sha256": hashlib.sha256(content).hexdigest(),
                       "suffix": path.suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,12}", path.suffix) else "",
                       "content": base64.b64encode(content).decode("ascii")})
    return assets, {"managed_files": 2, "referenced_files": len(assets), "total_bytes": total,
                    "missing_references": missing, "complete": not missing}


def prepare_restore(cfg, assets):
    """Valider tout le bundle avant la moindre écriture. Aucun chemin d'archive accepté."""
    if not isinstance(assets, list) or len(assets) > MAX_FILES:
        raise ValueError("Fichiers de configuration restaurés invalides.")
    restored = copy.deepcopy(cfg)
    allowed = {tuple(binding) for binding, _ in references(cfg)}
    files, used, total = {}, set(), 0
    for asset in assets:
        try:
            binding = tuple(asset["binding"])
            if binding not in allowed or binding in used:
                raise ValueError()
            if not isinstance(asset["content"], str) or len(asset["content"]) > 4 * ((MAX_FILE_BYTES + 2) // 3):
                raise ValueError()
            content = base64.b64decode(asset["content"], validate=True)
            digest = hashlib.sha256(content).hexdigest()
            if digest != asset["sha256"] or len(content) > MAX_FILE_BYTES:
                raise ValueError()
            total += len(content)
            if total > MAX_TOTAL_BYTES:
                raise ValueError()
            # Nom déterministe, sans réutiliser un chemin contrôlé par l'archive.
            suffix = asset.get("suffix", "")
            if not isinstance(suffix, str) or (suffix and not re.fullmatch(r"\.[A-Za-z0-9]{1,12}", suffix)):
                raise ValueError()
            relative = "secrets/restored-assets/" + digest + suffix
            target = restored
            for part in binding[:-1]:
                target = target[part]
            target[binding[-1]] = relative
            files[relative] = content
            used.add(binding)
        except (KeyError, TypeError, ValueError, IndexError):
            raise ValueError("Intégrité ou référence d'un fichier de configuration restauré invalide.") from None
    if used != allowed:
        raise ValueError("Archive incomplète : des fichiers de configuration référencés sont absents.")
    return restored, files


def install_assets(root, files):
    root = Path(root).resolve()
    for relative, content in files.items():
        path = root / relative
        if path.parent != root / "secrets" / "restored-assets" or not re.fullmatch(r"[a-f0-9]{64}(?:\.[A-Za-z0-9]{1,12})?", path.name):
            raise ValueError("Destination de restauration interdite.")
        if any(p.is_symlink() for p in (path, path.parent, path.parent.parent)):
            raise ValueError("Lien symbolique interdit pour la restauration.")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != content:
            raise ValueError("Collision de fichier de configuration restauré.")
        path.write_bytes(content)
        path.chmod(0o600)
