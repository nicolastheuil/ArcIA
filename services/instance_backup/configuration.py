"""Sérialisation commune et persistance privée des réglages effectifs."""
import copy
import json
import os
from pathlib import Path
import re


def dump_mapping(cfg):
    rendered = copy.deepcopy(cfg)
    for section in ("instance_git", "instance_backup"):
        if isinstance(rendered.get(section), dict):
            rendered[section].pop("passphrase", None)
    lines = ["# ArcIA — Configuration d'instance"]
    def emit(mapping, depth=0):
        for key, value in mapping.items():
            name = str(key) if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", str(key)) else json.dumps(str(key))
            if isinstance(value, dict) and value:
                lines.append(" " * depth + name + ":")
                emit(value, depth + 2)
            else:
                lines.append(" " * depth + name + ": " + json.dumps(value, ensure_ascii=False))
    emit(rendered)
    return "\n".join(lines) + "\n"


def persist_runtime_configuration(root, cfg):
    path = Path(root) / "arcia.config.yaml"
    temporary = path.with_suffix(".yaml.part")
    if path.is_symlink() or temporary.is_symlink():
        raise ValueError("Destination de configuration symbolique interdite.")
    try:
        temporary.write_text(dump_mapping(cfg), encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, path)
    except OSError:
        raise RuntimeError("Persistance de la configuration effective impossible ; conserver les identités du cluster avant reprise.") from None
