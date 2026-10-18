"""Adaptateur de la route native d'avatar ; ne crée ni fiche ni alias de modèle."""
import hashlib
import json
import os
from pathlib import Path

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRoute
from open_webui.main import app
from open_webui.internal.db import get_async_session
from open_webui.utils.auth import get_verified_user
from open_webui.utils.models import get_all_models, get_filtered_models
from branding import projected_icon

PATH = "/api/v1/models/model/profile/image"
native_route = next(route for route in app.router.routes if getattr(route, "path", None) == PATH)
native_image = native_route.endpoint


async def model_image(request: Request, id: str, user=Depends(get_verified_user), db=Depends(get_async_session)):
    try:
        source = Path(os.environ.get("ARCIA_MODEL_BRANDING_FILE", "/etc/arcia/models-branding.json")).read_bytes()
        mapping = json.loads(source)
    except (OSError, ValueError):
        return await native_image(request=request, id=id, user=user, db=db)
    if id in mapping.get("models", {}):
        # Même filtrage que le catalogue natif, avant toute résolution d'image.
        models = await get_all_models(request, user=user)
        visible = await get_filtered_models(models, user, db=db)
        icon = projected_icon(id, mapping, {model["id"] for model in visible})
        if icon:
            revision = hashlib.sha256(source).hexdigest()[:24]
            return RedirectResponse(icon + "?v=" + revision, headers={"Cache-Control": "no-store"})
    return await native_image(request=request, id=id, user=user, db=db)


# Conserve les autres routes, leurs dépendances et le lifespan officiel.
position = app.router.routes.index(native_route)
app.router.routes[position] = APIRoute(PATH, model_image, methods=["GET"], include_in_schema=False)
