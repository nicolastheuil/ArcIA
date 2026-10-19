"""Passage serveur vers les runtimes privés ; aucune identité acceptée du navigateur."""
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import re

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

MAX_BYTES = 20 * 1024 * 1024
LOCAL_BASE = "http://127.0.0.1:8080/api/v1/arcia/hermes/v1"


def binding_for(user_id, path):
    """Échec fermé, y compris pour un admin. Un runtime ne peut appartenir à deux comptes."""
    try:
        bindings = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(bindings, dict) or len({v["service"] for v in bindings.values()}) != len(bindings) or len({v["key"] for v in bindings.values()}) != len(bindings):
            raise ValueError()
        binding = bindings[user_id]
        runtime = binding["runtime"]
        namespace = binding["namespace"]
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", runtime) or not re.fullmatch(r"[a-z0-9-]{1,63}", namespace):
            raise ValueError()
        if runtime != "u-" + hashlib.sha256(user_id.encode()).hexdigest()[:24]:
            raise ValueError()
        service = binding["service"]
        slug = binding.get("poweruser_slug")
        if slug is not None:
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?", slug) or service != "hermes-poweruser-" + slug:
                raise ValueError()
        elif service != "hermes-files-" + runtime:
            raise ValueError()
        if len(binding["key"]) < 24:
            raise ValueError()
        return binding, f"http://{service}.{namespace}.svc:8643"
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(403, "Espace Hermes privé non provisionné pour ce compte.") from None


def install(app, get_verified_user):
    from open_webui.routers import openai
    native_headers = openai.get_headers_and_cookies

    async def trusted_headers(request, url, key=None, config=None, metadata=None, user=None):
        headers, cookies = await native_headers(request, url, key, config, metadata, user=user)
        if url.rstrip("/") == LOCAL_BASE:
            # Écraser les en-têtes issus de la configuration ou de la requête entrante.
            headers = {k: v for k, v in headers.items() if not k.lower().startswith("x-arcia-")}
            headers["X-ArcIA-User"] = str(user.id) if user else ""
            chat = str((metadata or {}).get("chat_id") or "")
            headers["X-ArcIA-Chat"] = hashlib.sha256(chat.encode()).hexdigest() if chat else ""
            headers["Authorization"] = "Bearer " + os.environ.get("ARCIA_HERMES_FILES_KEY", "")
            cookies = {}
        return headers, cookies

    openai.get_headers_and_cookies = trusted_headers
    router = APIRouter()

    def enabled():
        if os.environ.get("ARCIA_HERMES_FILES_ENABLED") != "true":
            raise HTTPException(404)

    def bindings_path():
        return os.environ.get("ARCIA_HERMES_FILES_BINDINGS", "/etc/arcia-hermes-files/bindings.json")

    def internal_user(request):
        enabled()
        key = os.environ.get("ARCIA_HERMES_FILES_KEY", "")
        if not key or not hmac.compare_digest(request.headers.get("Authorization", ""), "Bearer " + key):
            raise HTTPException(401)
        return request.headers.get("X-ArcIA-User", "")

    @router.get("/api/v1/arcia/hermes/v1/models")
    async def models(request: Request):
        internal_user(request)
        model_ids = json.loads(os.environ.get("OPENAI_API_CONFIGS", "{}"))["1"]["model_ids"]
        return {"object": "list", "data": [{"id": m, "object": "model", "owned_by": "arcia"} for m in model_ids]}

    @router.post("/api/v1/arcia/hermes/v1/chat/completions")
    async def chat(request: Request):
        user_id = internal_user(request)
        binding, base = binding_for(user_id, bindings_path())
        payload = await request.json()
        headers = {"Authorization": "Bearer " + binding["key"]}
        chat_id = request.headers.get("X-ArcIA-Chat", "")
        if chat_id:
            headers["X-Hermes-Session-Key"] = hmac.new(binding["key"].encode(), (user_id + ":" + chat_id).encode(), "sha256").hexdigest()
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1800, sock_connect=10), trust_env=False)
        try:
            response = await session.post(base + "/v1/chat/completions", json=payload, headers=headers, allow_redirects=False)
            if response.status != 200:
                status = response.status if response.status in (400, 401, 403, 422, 429) else 502
                response.release()
                await session.close()
                raise HTTPException(status, "Espace Hermes privé indisponible.")
            if payload.get("stream"):
                async def stream():
                    try:
                        async for chunk in response.content.iter_any():
                            yield chunk
                    finally:
                        response.close()
                        await session.close()
                return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})
            result = await response.json()
            response.release()
            await session.close()
            return result
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError):
            await session.close()
            raise HTTPException(502, "Espace Hermes privé indisponible.") from None

    @router.get("/api/v1/arcia/hermes-files/{artifact}")
    async def download(artifact: str, user=Depends(get_verified_user)):
        enabled()
        if not re.fullmatch(r"[a-f0-9]{32}", artifact):
            raise HTTPException(404)
        binding, base = binding_for(str(user.id), bindings_path())
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60), trust_env=False) as session:
                async with session.get(base + "/files/" + artifact, headers={"Authorization": "Bearer " + binding["key"]}, allow_redirects=False) as response:
                    if response.status != 200:
                        raise HTTPException(404 if response.status == 404 else 502)
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        data.extend(chunk)
                        if len(data) > MAX_BYTES:
                            raise HTTPException(502)
                    disposition = response.headers.get("Content-Disposition", "attachment")
                    if not disposition.startswith("attachment") or "\r" in disposition or "\n" in disposition:
                        disposition = "attachment"
                    return Response(bytes(data), media_type="application/octet-stream", headers={
                        "Content-Disposition": disposition, "Cache-Control": "private, no-store",
                        "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})
        except (aiohttp.ClientError, asyncio.TimeoutError):
            raise HTTPException(502, "Téléchargement momentanément indisponible.") from None

    # Le backend officiel monte son SPA sur / : les routes API doivent le précéder.
    position = next((i for i, route in enumerate(app.router.routes)
                     if getattr(route, "path", None) in ("", "/") and hasattr(route, "app")), len(app.router.routes))
    previous = len(app.router.routes)
    app.include_router(router)
    added = app.router.routes[previous:]
    del app.router.routes[previous:]
    app.router.routes[position:position] = added
