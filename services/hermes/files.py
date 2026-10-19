"""Relais de fichiers d'un runtime Hermes exclusivement dédié à un utilisateur.

Ne monter ce service que dans les pods privés créés par hermes_files.py.
Il ne donne aucun accès à un chemin fourni par le navigateur.
"""
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import time
from urllib.parse import quote
import uuid

from aiohttp import ClientSession, ClientTimeout, web

MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 10
RETENTION = 7 * 86400
QUOTA = 200 * 1024 * 1024
ID = re.compile(r"[a-f0-9]{32}\Z")
HTTP = web.AppKey("http", ClientSession)


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def prune(self):
        for record in self.root.glob("*.json"):
            if not ID.fullmatch(record.stem):
                continue
            try:
                if time.time() - record.stat().st_mtime > RETENTION:
                    (self.root / (record.stem + ".blob")).unlink(missing_ok=True)
                    record.unlink()
            except OSError:
                continue

    def publish(self, directory):
        self.prune()
        total = sum(p.stat().st_size for p in self.root.glob("*.blob") if not p.is_symlink())
        links = []
        for source in sorted(Path(directory).iterdir()):
            if len(links) >= MAX_FILES:
                break
            if source.is_symlink() or not source.is_file() or source.name.startswith("."):
                continue
            try:
                # Refuser liens symboliques, liens physiques et fichiers spéciaux.
                before = source.lstat()
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_BYTES:
                    continue
                fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
                with os.fdopen(fd, "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                        continue
                    data = stream.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES or total + len(data) > QUOTA:
                    continue
                artifact = uuid.uuid4().hex
                # Les noms Markdown et Content-Disposition sont encodés à la restitution.
                name = source.name[:180]
                metadata = {"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                (self.root / (artifact + ".blob")).write_bytes(data)
                (self.root / (artifact + ".json")).write_text(json.dumps(metadata), encoding="utf-8")
                total += len(data)
                label = re.sub(r"[\[\]\\`<>\r\n]", "_", name)
                links.append(f"[{label}](/api/v1/arcia/hermes-files/{artifact})")
            except OSError:
                continue
        return "\n\nFichiers à télécharger :\n\n" + "\n\n".join(links) if links else ""

    def read(self, artifact):
        if not ID.fullmatch(artifact):
            raise web.HTTPNotFound()
        record = self.root / (artifact + ".json")
        blob = self.root / (artifact + ".blob")
        try:
            if record.is_symlink() or blob.is_symlink() or time.time() - record.stat().st_mtime > RETENTION:
                raise web.HTTPNotFound()
            meta = json.loads(record.read_text(encoding="utf-8"))
            if blob.stat().st_size > MAX_BYTES:
                raise web.HTTPNotFound()
            data = blob.read_bytes()
            if len(data) != meta["size"] or hashlib.sha256(data).hexdigest() != meta["sha256"]:
                raise web.HTTPNotFound()
            return meta["name"], data
        except (OSError, ValueError, KeyError):
            raise web.HTTPNotFound() from None


def frame(payload):
    return b"data: " + json.dumps(payload, ensure_ascii=False).encode() + b"\n\n"


async def relay_sse(content, publish):
    """Conserver le streaming ; publier avant la trame de fin, sans retraiter le texte LLM."""
    buffer = bytearray()
    held = []
    complete = False
    finished = False
    failed = False
    template = {}
    async for line in content:
        buffer.extend(line)
        if len(buffer) > 1024 * 1024:
            raise ValueError("Trame SSE trop volumineuse")
        if bytes(buffer).endswith((b"\n\n", b"\r\n\r\n")):
            raw = bytes(buffer)
            buffer.clear()
            fields = [p[5:].strip() for p in raw.splitlines() if p.startswith(b"data:")]
            data = b"\n".join(fields)
            if data == b"[DONE]":
                complete = True
                break
            try:
                event = json.loads(data) if data else {}
            except ValueError:
                failed = True
                yield raw
                continue
            if event is None:  # Certains flux natifs émettent un keepalive JSON null.
                yield raw
                continue
            if any(part.startswith(b"event:") for part in raw.splitlines()):
                # Les événements natifs d’approbation ont des choices textuels ;
                # seuls les chunks OpenAI déterminent la fin de l’inférence.
                yield raw
                continue
            if not isinstance(event, dict) or not isinstance(event.get("choices") or [], list) or any(not isinstance(choice, dict) for choice in event.get("choices") or []):
                failed = True
                yield raw
                continue
            if event.get("error"):
                failed = True
            choices = event.get("choices") or []
            if choices:
                template = {k: event[k] for k in ("id", "object", "created", "model") if k in event}
            finished |= any(c.get("finish_reason") == "stop" for c in choices)
            if held or any(c.get("finish_reason") for c in choices):
                held.append(raw)
            else:
                yield raw
    if not complete or not finished or failed:
        # Aucun lien de résultat après annulation, erreur ou flux tronqué.
        for raw in held:
            yield raw
        if complete:
            yield b"data: [DONE]\n\n"
        return
    links = await publish()
    if links:
        yield frame({**template, "choices": [{"index": 0, "delta": {"content": links}, "finish_reason": None}]})
    for raw in held:
        yield raw
    yield b"data: [DONE]\n\n"


def create_app(root, key, upstream="http://127.0.0.1:8642"):
    if not key or len(key) < 24:
        raise ValueError("Une clé privée dédiée est obligatoire")
    store = Store(Path(root) / "published")
    inbox = Path(root) / "inbox"
    inbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = asyncio.Lock()  # Un seul tour producteur par runtime privé.

    @web.middleware
    async def auth(request, handler):
        if request.path != "/health" and not hmac.compare_digest(
                request.headers.get("Authorization", ""), "Bearer " + key):
            raise web.HTTPUnauthorized()
        return await handler(request)

    app = web.Application(middlewares=[auth], client_max_size=10 * 1024 * 1024)

    async def session_context(app):
        app[HTTP] = ClientSession(timeout=ClientTimeout(total=1800, sock_connect=10))
        yield
        await app[HTTP].close()
    app.cleanup_ctx.append(session_context)

    async def health(request):
        async with app[HTTP].get(upstream + "/health", headers={"Authorization": "Bearer " + key}) as response:
            return web.json_response({"ready": response.status == 200}, status=200 if response.status == 200 else 503)

    async def download(request):
        name, data = await asyncio.to_thread(store.read, request.match_info["artifact"])
        return web.Response(body=data, content_type="application/octet-stream", headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name, safe=""),
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    async def chat(request):
        payload = await request.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            raise web.HTTPBadRequest()
        # Pas d'identité ou de session réutilisable fournie par le client.
        for field in ("user", "session_id", "previous_response_id"):
            payload.pop(field, None)
        async with lock:
            # Identité aléatoire de 128 bits, sans suites numériques que le DLP
            # pourrait confondre avec des téléphones dans les arguments d’outils.
            directory = inbox / uuid.uuid4().hex.translate(str.maketrans("0123456789", "ghijklmnop"))
            directory.mkdir(mode=0o700)
            payload["messages"] = [*payload["messages"], {"role": "system", "content": (
                "Pour remettre des fichiers à l'utilisateur, crée les fichiers finaux directement dans "
                + str(directory) + ". Pas de sous-dossiers. Limites : 10 fichiers, 20 Mio chacun. "
                "Le portail ajoutera les liens de téléchargement après ton exécution. "
                "Ne fabrique pas de liens sandbox: ou de liens de disque local.")}]
            headers = {"Authorization": "Bearer " + key}
            session_key = request.headers.get("X-Hermes-Session-Key")
            if session_key:
                headers["X-Hermes-Session-Key"] = session_key

            async def publish():
                return await asyncio.to_thread(store.publish, directory)

            try:
                async with app[HTTP].post(upstream + "/v1/chat/completions", json=payload, headers=headers) as upstream_response:
                    if upstream_response.status != 200:
                        return web.json_response({"error": {"message": "Échec de la session Hermes."}}, status=upstream_response.status)
                    if payload.get("stream"):
                        response = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-store"})
                        await response.prepare(request)
                        async for chunk in relay_sse(upstream_response.content, publish):
                            await response.write(chunk)
                        await response.write_eof()
                        return response
                    result = await upstream_response.json()
                    choices = result.get("choices") or []
                    if choices and not result.get("error"):
                        message = choices[0].get("message", {})
                        message["content"] = (message.get("content") or "") + await publish()
                    return web.json_response(result)
            finally:
                # Seulement ce répertoire de tour ; aucun rmtree sur des chemins d'agent.
                for child in directory.iterdir() if directory.is_dir() and not directory.is_symlink() else []:
                    if not child.is_dir() or child.is_symlink():
                        child.unlink(missing_ok=True)
                try:
                    directory.rmdir()
                except OSError:
                    pass

    app.router.add_get("/health", health)
    app.router.add_post("/v1/chat/completions", chat)
    app.router.add_get("/files/{artifact}", download)
    return app


if __name__ == "__main__":
    web.run_app(create_app(os.environ["ARCIA_FILES_ROOT"], os.environ["API_SERVER_KEY"]),
                host="0.0.0.0", port=8643, access_log=None)
