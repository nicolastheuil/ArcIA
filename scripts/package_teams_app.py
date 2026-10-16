#!/usr/bin/env python3
"""
ArcIA — Packageur d'Application Microsoft Teams
Génère et valide l'archive .zip prête à être importée dans le Portail Développeur Teams (dev.teams.microsoft.com).
"""

import argparse
import json
import os
import re
import struct
import sys
import uuid
import zipfile
from pathlib import Path

# Assure un affichage UTF-8 propre même sous Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GUID_REGEX = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
HEX_COLOR_REGEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def get_png_dimensions(filepath: Path) -> tuple[int, int]:
    """Extrait la largeur et la hauteur d'un fichier PNG depuis l'en-tête IHDR."""
    with open(filepath, "rb") as f:
        header = f.read(24)
        if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"'{filepath}' n'est pas un fichier PNG valide.")
        # Bytes 16 à 23 : largeur et hauteur (entiers 32-bit big-endian)
        width, height = struct.unpack(">II", header[16:24])
        return width, height


def validate_manifest(manifest: dict) -> list[str]:
    """Vérifie la conformité du manifeste Teams avec le schéma (v1.16 à v1.25+)."""
    errors = []

    required_keys = ["manifestVersion", "version", "id", "developer", "name", "description", "icons", "accentColor"]
    for key in required_keys:
        if key not in manifest:
            errors.append(f"Clé obligatoire manquante : '{key}'")

    # Validation GUID de l'application
    app_id = manifest.get("id", "")
    if not GUID_REGEX.match(str(app_id)):
        errors.append(f"'id' doit être un GUID valide au format xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (obtenu: '{app_id}')")

    # Validation de supportsChannelFeatures (requis en v1.25+)
    m_ver = str(manifest.get("manifestVersion", "1.16"))
    ch_feat = manifest.get("supportsChannelFeatures")
    if ch_feat is not None and ch_feat != "tier1":
        errors.append(f"'supportsChannelFeatures' doit valoir 'tier1' (obtenu: '{ch_feat}')")

    if "supportedChannelTypes" in manifest and m_ver >= "1.25":
        errors.append("'supportedChannelTypes' est obsolète et interdit en v1.25+ : utilisez 'supportsChannelFeatures': 'tier1'")

    # Validation du nom
    name = manifest.get("name", {})
    if not isinstance(name, dict):
        errors.append("'name' doit être un objet contenant 'short' et 'full'")
    else:
        short_name = name.get("short", "")
        if not short_name or len(short_name) > 30:
            errors.append(f"'name.short' obligatoire et <= 30 caractères (actuel: {len(short_name)})")
        full_name = name.get("full", "")
        if full_name and len(full_name) > 100:
            errors.append(f"'name.full' doit faire <= 100 caractères (actuel: {len(full_name)})")

    # Validation de la description
    desc = manifest.get("description", {})
    if not isinstance(desc, dict):
        errors.append("'description' doit être un objet contenant 'short' et 'full'")
    else:
        short_desc = desc.get("short", "")
        if not short_desc or len(short_desc) > 80:
            errors.append(f"'description.short' obligatoire et <= 80 caractères (actuel: {len(short_desc)})")
        full_desc = desc.get("full", "")
        if not full_desc or len(full_desc) > 4000:
            errors.append(f"'description.full' obligatoire et <= 4000 caractères (actuel: {len(full_desc)})")

    # Validation de l'accentColor
    accent = manifest.get("accentColor", "")
    if not HEX_COLOR_REGEX.match(str(accent)):
        errors.append(f"'accentColor' doit être une couleur hexadécimale (#RRGGBB) valide (obtenu: '{accent}')")

    # Validation des bots
    bots = manifest.get("bots", [])
    if bots:
        for idx, bot in enumerate(bots):
            bot_id = bot.get("botId", "")
            if not GUID_REGEX.match(str(bot_id)):
                errors.append(f"bots[{idx}].botId doit être un GUID valide (obtenu: '{bot_id}')")
            scopes = bot.get("scopes", [])
            allowed_scopes = {"team", "personal", "groupChat", "groupchat"}
            for s in scopes:
                if s not in allowed_scopes:
                    errors.append(f"Scope bot invalide : '{s}'. Autorisés : {allowed_scopes}")

    return errors


def build_teams_package(
    manifest_path: Path,
    icons_dir: Path,
    output_zip: Path,
    bot_id: str | None = None,
    app_id: str | None = None,
    short_name: str | None = None,
    domain: str | None = None,
    no_bot: bool = False,
) -> Path:
    """Construit et archive le package Teams .zip."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Fichier manifeste introuvable : {manifest_path}")

    color_png = icons_dir / "color.png"
    outline_png = icons_dir / "outline.png"

    if not color_png.is_file():
        raise FileNotFoundError(f"Icône 'color.png' introuvable dans : {icons_dir}")
    if not outline_png.is_file():
        raise FileNotFoundError(f"Icône 'outline.png' introuvable dans : {icons_dir}")

    # Vérification des dimensions des icônes
    c_w, c_h = get_png_dimensions(color_png)
    if (c_w, c_h) != (192, 192):
        raise ValueError(f"color.png doit mesurer exactement 192x192 px (actuel: {c_w}x{c_h})")

    o_w, o_h = get_png_dimensions(outline_png)
    if (o_w, o_h) != (32, 32):
        raise ValueError(f"outline.png doit mesurer exactement 32x32 px (actuel: {o_w}x{o_h})")

    # Chargement et personnalisation du manifeste
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    if app_id:
        manifest_data["id"] = app_id
    elif manifest_data.get("id") in ("", "00000000-0000-0000-0000-000000000000"):
        manifest_data["id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, "arcia.arcitek.fr"))

    if no_bot:
        manifest_data.pop("bots", None)
    elif bot_id:
        if "bots" in manifest_data and len(manifest_data["bots"]) > 0:
            manifest_data["bots"][0]["botId"] = bot_id
        else:
            manifest_data["bots"] = [{
                "botId": bot_id,
                "scopes": ["personal", "team", "groupchat"],
                "supportsFiles": False,
                "isNotificationOnly": False,
            }]
    elif "bots" in manifest_data and len(manifest_data["bots"]) > 0:
        curr_bot = manifest_data["bots"][0].get("botId", "")
        if curr_bot in ("", "00000000-0000-0000-0000-000000000000"):
            manifest_data["bots"][0]["botId"] = manifest_data["id"]

    if short_name:
        manifest_data["name"]["short"] = short_name

    if domain:
        domains = manifest_data.setdefault("validDomains", [])
        if domain not in domains:
            domains.append(domain)

    # Assure le support universel des canaux Teams (supportsChannelFeatures: tier1)
    if str(manifest_data.get("manifestVersion", "")) >= "1.25":
        manifest_data.setdefault("supportsChannelFeatures", "tier1")

    # Validation stricte
    errors = validate_manifest(manifest_data)
    if errors:
        raise ValueError("Erreurs de validation du manifeste Teams :\n - " + "\n - ".join(errors))

    # Création du zip avec les fichiers directement à la racine
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = json.dumps(manifest_data, indent=2, ensure_ascii=False).encode("utf-8")

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_bytes)
        zf.write(color_png, arcname="color.png")
        zf.write(outline_png, arcname="outline.png")

    return output_zip


def main():
    parser = argparse.ArgumentParser(description="Création et validation du package Microsoft Teams ArcIA (.zip)")
    parser.add_argument("--manifest", type=str, default="assets/teams/manifest.json", help="Chemin vers manifest.json")
    parser.add_argument("--icons-dir", type=str, default="assets/teams", help="Dossier contenant color.png et outline.png")
    parser.add_argument("--output", type=str, default="assets/teams/arcia-teams-app.zip", help="Chemin du package .zip généré")
    parser.add_argument("--bot-id", type=str, default=None, help="Microsoft App ID (GUID) du bot Azure / Entra ID")
    parser.add_argument("--app-id", type=str, default=None, help="GUID de l'application Teams (généré automatiquement si omis)")
    parser.add_argument("--name", type=str, default=None, help="Nom court personnalisé du bot (ex: ArcIA)")
    parser.add_argument("--domain", type=str, default=None, help="FQDN ou domaine valide supplémentaire")
    parser.add_argument("--no-bot", action="store_true", help="Génère un package sans bot pré-déclaré (import direct sans validation Bot Framework)")
    parser.add_argument("--check-only", action="store_true", help="Valide les fichiers sans générer le zip")

    args = parser.parse_args()

    manifest_p = Path(args.manifest)
    icons_p = Path(args.icons_dir)
    output_p = Path(args.output)

    try:
        if args.check_only:
            with open(manifest_p, "r", encoding="utf-8") as f:
                data = json.load(f)
            errs = validate_manifest(data)
            if errs:
                print("[ERROR] Erreurs de validation du manifeste :")
                for e in errs:
                    print(f"  - {e}")
                sys.exit(1)
            c_w, c_h = get_png_dimensions(icons_p / "color.png")
            o_w, o_h = get_png_dimensions(icons_p / "outline.png")
            print(f"[OK] Manifeste valide. Icônes valides (color: {c_w}x{c_h}, outline: {o_w}x{o_h}).")
            sys.exit(0)

        out = build_teams_package(
            manifest_path=manifest_p,
            icons_dir=icons_p,
            output_zip=output_p,
            bot_id=args.bot_id,
            app_id=args.app_id,
            short_name=args.name,
            domain=args.domain,
            no_bot=args.no_bot,
        )
        print(f"[OK] Package Microsoft Teams généré avec succès : {out.resolve()}")
        print(f"[INFO] Taille de l'archive : {out.stat().st_size} octets")
        print("\nPrêt pour l'importation directe dans le Portail Développeur Teams :")
        print("  1. Rendez-vous sur https://dev.teams.microsoft.com/apps")
        print("  2. Cliquez sur 'Importer une application' ('Import app')")
        print(f"  3. Sélectionnez le fichier : {out.resolve()}")
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
