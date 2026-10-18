"""Contrôle sans authentification d'utilisateur : uniquement les ressources statiques locales."""
import hashlib
import json
from pathlib import Path
import urllib.request


def verify(expected_revision, expected_hashes):
    try:
        mapping = json.loads(Path("/etc/arcia/models-branding.json").read_text())
        mapping_loaded = mapping.get("revision") == expected_revision
        for name, digest in expected_hashes.items():
            with urllib.request.urlopen("http://127.0.0.1:8080/static/" + name, timeout=5) as response:
                if "image/svg+xml" not in response.headers.get("Content-Type", "") or hashlib.sha256(response.read()).hexdigest() != digest:
                    raise ValueError("Ressource visuelle périmée ou type incorrect.")
        return {"runtime_loaded": mapping_loaded, "assets_served": True, "avatars_verified": False,
                "message": "Projection et fichiers chargés ; recette authentifiée du navigateur distincte."}
    except Exception:
        return {"runtime_loaded": False, "assets_served": False, "avatars_verified": False,
                "error": "Révision ou ressource visuelle indisponible dans Open-WebUI."}
