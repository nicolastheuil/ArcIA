"""Provisionner des droits natifs explicites pour les comptes déclarés par l'admin.

Exécuté localement dans le backend par l'orchestrateur, jamais par un agent.
Les fiches et personnalisations de modèles existantes sont conservées.
"""
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import sys


async def reconcile(payload, users, models, form_class, grants):
    identities = payload.get("user_ids", [])
    if not identities:
        return {"granted": 0, "pending_admin": False}
    admin = await users.get_super_admin_user()
    if admin is None:
        return {"granted": 0, "pending_admin": True}
    for identity in identities:
        user = await users.get_user_by_id(identity)
        if user is None or user.role not in ("user", "admin"):
            raise ValueError("Compte WebUI déclaré absent ou non validé")
    count = 0
    for model_id in payload.get("model_ids", []):
        current = await models.get_model_by_id(model_id)
        if current is None:
            current = await models.insert_new_model(form_class(id=model_id, name=model_id,
                base_model_id=None, meta={}, params={}, access_grants=[]), user_id=admin.id)
            if current is None:
                raise RuntimeError("Fiche de modèle non créée")
        for identity in identities:
            result = await grants.grant_access("model", model_id, "user", identity, "read")
            if result is None:
                raise RuntimeError("Droit natif non appliqué")
            count += 1
    return {"granted": count, "pending_admin": False}


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    # Même clé de session que le lanceur, sans jamais afficher sa valeur.
    if not os.environ.get("WEBUI_SECRET_KEY"):
        key_file = Path(os.environ.get("WEBUI_SECRET_KEY_FILE", "/app/backend/data/.webui_secret_key"))
        os.environ["WEBUI_SECRET_KEY"] = key_file.read_text(encoding="utf-8").strip()
    with contextlib.redirect_stdout(io.StringIO()):
        from open_webui.models.users import Users
        from open_webui.models.models import Models, ModelForm
        from open_webui.models.access_grants import AccessGrants
    try:
        result = asyncio.run(reconcile(payload, Users, Models, ModelForm, AccessGrants))
        print("ARCIA_MODEL_ACCESS=" + json.dumps(result))
    except Exception:
        print("ARCIA_MODEL_ACCESS_FAILED", file=sys.stderr)
        sys.exit(1)
