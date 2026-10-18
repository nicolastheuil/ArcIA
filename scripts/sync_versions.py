#!/usr/bin/env python3
"""Synchronise et audite la cohérence des versions de la plateforme ArcIA sur tout le dépôt.

Source de vérité déclarative : deploy/versions.json (arcia_version).
Usage:
    python scripts/sync_versions.py --check
    python scripts/sync_versions.py --apply
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS_JSON_PATH = ROOT / "deploy" / "versions.json"


def load_target_version() -> str:
    if not VERSIONS_JSON_PATH.exists():
        raise FileNotFoundError(f"Référentiel introuvable : {VERSIONS_JSON_PATH}")
    with open(VERSIONS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    version = data.get("arcia_version") or data.get("arcia_release") or "v0.5.1"
    return version if version.startswith("v") else f"v{version}"


def load_tracked_files() -> list:
    """Charge la liste des fichiers audités depuis le registre deploy/versions.json."""
    if VERSIONS_JSON_PATH.exists():
        try:
            with open(VERSIONS_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                files = data.get("version_registry", {}).get("tracked_files")
                if files and isinstance(files, list):
                    return files
        except Exception:
            pass
    return DEFAULT_TARGET_FILES


# Registre canonique des motifs de version ArcIA suivis sur le dépôt
VERSION_TARGET_PATTERNS = [
    # 1. Badges Shields.io dans README.md et sous-dossiers
    (
        r"https://img\.shields\.io/badge/ArcIA-v[0-9.]+-1659E4(?:\.svg)?(?:\?[^\s\"'\)]*)?",
        lambda v: f"https://img.shields.io/badge/ArcIA-{v}-1659E4.svg",
    ),
    (
        r"https://img\.shields\.io/badge/[^\"'\s\)]*Accueil-ArcIA_v[0-9.]+[^\s\"'\)]*",
        lambda v: f"https://img.shields.io/badge/🏠_Accueil-ArcIA_{v}-1659E4?style=flat-square",
    ),
    # 2. Mentions textuelles explicites "ArcIA v0.X" ou "ArcIA v0.X.Y"
    (
        r"\bArcIA v0\.[0-9]+(?:\.[0-9]+)?\b",
        lambda v: f"ArcIA {v}",
    ),
    (
        r"\bTokenmaxing v0\.[0-9]+(?:\.[0-9]+)?\b",
        lambda v: f"Tokenmaxing {v}",
    ),
    (
        r"\bSetup & Configuration Wizard v0\.[0-9]+(?:\.[0-9]+)?\b",
        lambda v: f"Setup & Configuration Wizard {v}",
    ),
    (
        r"\bStatut(?:\s+en)?\s*:\s*(?:Implémenté|Actif)?\s*\(?v0\.[0-9]+(?:\.[0-9]+)?\)?",
        lambda v: f"Statut : Implémenté ({v})",
    ),
    (
        r"\barcia_version\s*=\s*['\"]v?[0-9.]+['\"]",
        lambda v: f'arcia_version = "{v}"',
    ),
    (
        r"ArcIA-Update-Checker/[0-9.]+",
        lambda v: f"ArcIA-Update-Checker/{v.lstrip('v')}",
    ),
    (
        r"ArcIA\s+v[0-9.]+\s*·\s*Production",
        lambda v: f"ArcIA {v} · Production",
    ),
    (
        r"versions de référence ArcIA\s+v[0-9.]+",
        lambda v: f"versions de référence ArcIA {v}",
    ),
    (
        r"Catalogue ArcIA\s+v[0-9.]+",
        lambda v: f"Catalogue ArcIA {v}",
    ),
    (
        r"ArcIA v0\.[0-9.]+\s*—",
        lambda v: f"ArcIA {v} —",
    ),
    (
        r"ArcIA v0\.[0-9.]+\s+Platform Validation Tests",
        lambda v: f"ArcIA {v} Platform Validation Tests",
    ),
    (
        r"Passerelle d'inférence LiteLLM v0\.[0-9.]+",
        lambda v: f"Passerelle d'inférence LiteLLM {v}",
    ),
    (
        r"Tableau de bord de traçabilité v0\.[0-9.]+",
        lambda v: f"Tableau de bord de traçabilité {v}",
    ),
    (
        r"## 1\. Principes fondateurs v0\.[0-9.]+",
        lambda v: f"## 1. Principes fondateurs {v}",
    ),
    (
        r"## 3\. Cartographie des composants et ports \(v0\.[0-9.]+\)",
        lambda v: f"## 3. Cartographie des composants et ports ({v})",
    ),
    (
        r"dans la version \*\*v0\.[0-9.]+\*\*",
        lambda v: f"dans la version **{v}**",
    ),
    (
        r"Cible \(v0\.[0-9.]+\)",
        lambda v: f"Cible ({v})",
    ),
    (
        r"## Profils utilisateurs v0\.[0-9.]+",
        lambda v: f"## Profils utilisateurs {v}",
    ),
    (
        r"## Synthèse des durcissements de sécurité \(v0\.[0-9.]+\)",
        lambda v: f"## Synthèse des durcissements de sécurité ({v})",
    ),
    (
        r"## 1\. Fonctionnalités clés v0\.[0-9.]+",
        lambda v: f"## 1. Fonctionnalités clés {v}",
    ),
    (
        r"## 1\. Rôles et architecture v0\.[0-9.]+",
        lambda v: f"## 1. Rôles et architecture {v}",
    ),
    (
        r"## 3\. Configuration du routage v0\.[0-9.]+",
        lambda v: f"## 3. Configuration du routage {v}",
    ),
    (
        r"## 1\. Caractéristiques principales et verrouillage d'accès v0\.[0-9.]+",
        lambda v: f"## 1. Caractéristiques principales et verrouillage d'accès {v}",
    ),
    (
        r"# Presidio DLP — gouvernance et double barrière de confidentialité \(v0\.[0-9.]+\)",
        lambda v: f"# Presidio DLP — gouvernance et double barrière de confidentialité ({v})",
    ),
    (
        r"# Hermes Agent — moteur d'agents, Studio et pods dédiés Power Users \(v0\.[0-9.]+\)",
        lambda v: f"# Hermes Agent — moteur d'agents, Studio et pods dédiés Power Users ({v})",
    ),
    (
        r"# LiteLLM Proxy — passerelle d'inférence d'entreprise \(v0\.[0-9.]+\)",
        lambda v: f"# LiteLLM Proxy — passerelle d'inférence d'entreprise ({v})",
    ),
    (
        r"# Intégration Microsoft Teams — bot ArcIA \(v0\.[0-9.]+\)",
        lambda v: f"# Intégration Microsoft Teams — bot ArcIA ({v})",
    ),
    (
        r"# Portail collaborateur Open-WebUI et SSO Microsoft Entra ID \(v0\.[0-9.]+\)",
        lambda v: f"# Portail collaborateur Open-WebUI et SSO Microsoft Entra ID ({v})",
    ),
    (
        r"\[État des fonctionnalités v0\.[0-9.]+\]",
        lambda v: f"[État des fonctionnalités {v}]",
    ),
    (
        r"flux d'inférence en v0\.[0-9.]+\.",
        lambda v: f"flux d'inférence en {v}.",
    ),
    (
        r">\s*\*\*Statut en v0\.[0-9.]+\s*:\s*Implémenté et Actif\.\*\*",
        lambda v: f"> **Statut en {v} : Implémenté et Actif.**",
    ),
    (
        r"arcia-governance-tokenmaxing\s*v0\.[0-9.]+",
        lambda v: f"arcia-governance-tokenmaxing {v}",
    ),
    (
        r"Guide Tokenmaxing & CCR v0\.[0-9.]+",
        lambda v: f"Guide Tokenmaxing & CCR {v}",
    ),
    (
        r"Governance & Tokenmaxing Plugin \(v0\.[0-9.]+\)",
        lambda v: f"Governance & Tokenmaxing Plugin ({v})",
    ),
    (
        r"Adaptateur Teams Bot\s*:\s*🟢\s*Opérationnel\s*\(v0\.[0-9.]+\)",
        lambda v: f"Adaptateur Teams Bot : 🟢 Opérationnel ({v})",
    ),
    (
        r"tokens typés v0\.[0-9.]+",
        lambda v: f"tokens typés {v}",
    ),
    (
        r"security constraints for v0\.[0-9.]+",
        lambda v: f"security constraints for {v}",
    ),
    (
        r"profils canoniques v0\.[0-9.]+",
        lambda v: f"profils canoniques {v}",
    ),
]

# Fichiers de secours si deploy/versions.json n'est pas accessible
DEFAULT_TARGET_FILES = [
    "README.md",
    "AGENTS.md",
    "docs/README.md",
    "docs/architecture.md",
    "docs/etat-des-fonctionnalites.md",
    "docs/runbooks/README.md",
    "docs/runbooks/quickstart.md",
    "docs/runbooks/exploitation.md",
    "docs/runbooks/sauvegarde-reconstruction.md",
    "docs/guides/README.md",
    "docs/guides/versions-officielles.md",
    "docs/guides/deploiement-universel.md",
    "docs/guides/hermes-agent.md",
    "docs/guides/inference-litellm.md",
    "docs/guides/integration-teams.md",
    "docs/guides/portail-webui-entraid.md",
    "docs/guides/securite.md",
    "docs/guides/tokenmaxing.md",
    "docs/guides/outillage-builder.md",
    "docs/guides/skills.md",
    "docs/guides/confidentialite-presidio.md",
    "docs/guides/chaine-de-routage.md",
    "scripts/README.md",
    "scripts/wizard_ui/index.html",
    "scripts/wizard.py",
    "services/README.md",
    "services/hermes/README.md",
    "services/litellm/README.md",
    "services/presidio/README.md",
    "services/teams/README.md",
    "skills/README.md",
    "skills/graphify/README.md",
    "skills/ponytail/README.md",
    "skills/public-apis/README.md",
    "tests/README.md",
]


def sync_file_versions(filepath: Path, target_version: str, apply_changes: bool = False) -> int:
    """Vérifie ou applique la synchronisation de version sur un fichier. Retourne le nombre d'occurrences modifiées."""
    if not filepath.exists():
        return 0

    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return 0

    new_content = content
    changes_count = 0

    for pattern_re, replacer in VERSION_TARGET_PATTERNS:
        replacement = replacer(target_version)
        matches = re.findall(pattern_re, new_content)
        if matches:
            for m in set(matches):
                if m != replacement:
                    new_content = new_content.replace(m, replacement)
                    changes_count += 1

    if apply_changes and changes_count > 0:
        filepath.write_text(new_content, encoding="utf-8")

    return changes_count


def audit_version_consistency(apply_changes: bool = False) -> int:
    target_version = load_target_version()
    print(f"[*] Version cible certifiée ArcIA : {target_version} (source : deploy/versions.json)")

    total_changes = 0
    mismatched_files = []

    for rel_path in load_tracked_files():
        fp = ROOT / rel_path
        if not fp.exists():
            continue
        c = sync_file_versions(fp, target_version, apply_changes=apply_changes)
        if c > 0:
            total_changes += c
            mismatched_files.append((rel_path, c))

    if apply_changes:
        print(f"[OK] {total_changes} référence(s) de version synchronisée(s) vers {target_version} dans {len(mismatched_files)} fichier(s).")
        for f, cnt in mismatched_files:
            print(f"   -> Mis à jour : {f} ({cnt} occurrence(s))")
        return 0
    else:
        if total_changes > 0:
            print(f"[WARN] {total_changes} incohérence(s) de version détectée(s) :")
            for f, cnt in mismatched_files:
                print(f"   - {f} ({cnt} référence(s) obsolètes)")
            print("\nExécutez `python scripts/sync_versions.py --apply` pour régulariser automatiquement.")
            return 1
        else:
            print(f"[OK] Toutes les références documentaires et applicatives sont parfaitement alignées sur {target_version}.")
            return 0


def main():
    parser = argparse.ArgumentParser(description="Synchronisation des versions officielles d'ArcIA.")
    parser.add_argument("--apply", action="store_true", help="Applique automatiquement les corrections sur les fichiers.")
    parser.add_argument("--check", action="store_true", help="Vérifie la cohérence sans modifier les fichiers.")
    args = parser.parse_args()

    mode_apply = args.apply or (not args.check)
    sys.exit(audit_version_consistency(apply_changes=mode_apply))


if __name__ == "__main__":
    main()
