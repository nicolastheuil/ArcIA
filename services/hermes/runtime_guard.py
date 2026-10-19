"""Admission DLP obligatoire au démarrage, aux écritures SQLite et au transport LLM.

Ces frontières ne sont pas des middlewares d'extension Hermes : leurs erreurs ne
peuvent pas déclencher la poursuite de la chaîne native en mode fail-open.
"""
import asyncio
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urlsplit

try:
    from . import plugin
except ImportError:
    import plugin

INSTALLED = False
_factories = {}
# Valeurs de contrôle SQLite/FTS publiques et constantes, sans donnée utilisateur.
SQL_CONTROLS = {"delete", "rebuild", "optimize", "integrity-check", "fts_rebuild_high_water"}


class DLPStop(BaseException):
    """Arrêt de sécurité ; ne pas l'absorber dans un fallback `except Exception`."""

    def __init__(self, message):
        super().__init__(message)
        # Seulement le nom statique de la frontière, jamais son payload ni l’erreur.
        reason = "media" if "multimédia" in message else "type" if "type de donnée" in message else "depth" if "profonde" in message else "admission"
        sys.stderr.write("ArcIA DLP : refus à la frontière " + sys._getframe(1).f_code.co_name + " (" + reason + ").\n")
        if os.environ.get("ARCIA_DLP_TRACE") == "true":
            import traceback
            for frame in traceback.extract_stack(limit=12):
                sys.stderr.write("ArcIA DLP frame: " + Path(frame.filename).name + ":" + str(frame.lineno) + ":" + frame.name + "\n")


def trace(stage):
    if os.environ.get("ARCIA_DLP_TRACE") == "true":
        sys.stderr.write("ArcIA DLP trace: " + stage + "\n")


def scope():
    key = os.environ.get("API_SERVER_KEY", "")
    if len(key) < 24:
        raise DLPStop("ArcIA DLP : identité privée absente.")
    return hmac.new(key.encode(), b"arcia-presidio-runtime-v1", hashlib.sha256).hexdigest()


def clean_text(text):
    # Aucun cache d'admission : même un texte déjà pseudonymisé exige un DLP prêt.
    try:
        plugin.PRESIDIO_FAIL_CLOSED = True
        return plugin.sanitize_via_presidio(text, session_id=scope())
    except Exception:
        raise DLPStop("ArcIA DLP : opération refusée avant persistance ou inférence.") from None


@dataclass
class TextSlot:
    index: int


@dataclass
class EncodedJSON:
    value: object
    prefix: str = ""


def clean_texts(texts):
    try:
        return plugin.sanitize_batch_via_presidio(texts, session_id=scope())
    except Exception:
        raise DLPStop("ArcIA DLP : lot refusé avant persistance ou inférence.") from None


def clean_structure(value, protocol=False):
    media = ("image_url", "input_image", "input_file", "input_audio", "audio", "image", "video_url")
    if protocol and isinstance(value, dict):
        nodes = [value, *(value.get("messages") or []), *(value.get("input") if isinstance(value.get("input"), list) else [])]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            parts = node.get("content") if isinstance(node.get("content"), list) else []
            if any(isinstance(part, dict) and part.get("type") in media for part in [node, *parts]):
                raise DLPStop("ArcIA DLP : contenu multimédia sans analyse qualifiée.")
    texts = []
    def prepare(item, depth=0):
        if depth > 64:
            raise DLPStop("ArcIA DLP : structure trop profonde.")
        if isinstance(item, str):
            prefix = "\x00json:" if item.startswith("\x00json:") else ""
            candidate = item[len(prefix):] if prefix else item
            if candidate.lstrip().startswith(("{", "[")):
                try:
                    parsed = json.loads(candidate)
                except ValueError:
                    parsed = None
                if isinstance(parsed, (dict, list)):
                    return EncodedJSON(prepare(parsed, depth + 1), prefix)
            texts.append(item)
            return TextSlot(len(texts) - 1)
        if isinstance(item, dict):
            return {key: child if protocol and depth == 0 and key == "model" and isinstance(child, str)
                    else prepare(child, depth + 1) for key, child in item.items()}
        if isinstance(item, (tuple, list)):
            return [prepare(child, depth + 1) for child in item]
        if item is None or isinstance(item, (bool, int, float)):
            return item
        trace("prepare.type." + ("bytes" if isinstance(item, bytes) else "memoryview" if isinstance(item, memoryview) else "other"))
        raise DLPStop("ArcIA DLP : type de donnée non qualifié.")
    prepared = prepare(value)
    cleaned = clean_texts(texts)
    def restore(item):
        if isinstance(item, TextSlot):
            return cleaned[item.index]
        if isinstance(item, EncodedJSON):
            return item.prefix + json.dumps(restore(item.value), ensure_ascii=False)
        if isinstance(item, dict):
            return {key: restore(child) for key, child in item.items()}
        if isinstance(item, list):
            return [restore(child) for child in item]
        return item
    return restore(prepared)


def transform(value, restore=False):
    """Parcourir les valeurs textuelles sans altérer les clés et types du protocole."""
    if not restore:
        return clean_structure(value, protocol=True)
    if isinstance(value, str):
        if restore:
            return plugin.deanonymize_via_presidio(value, session_id=scope()) if re.search(r"\[[A-Z][A-Z0-9_]*_\d+\]", value) else value
        return clean_text(value)
    if isinstance(value, dict):
        return {key: transform(item, restore) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [transform(item, restore) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise DLPStop("ArcIA DLP : type de donnée non qualifié.")


def digest_parameter_indexes(sql):
    """Le digest SHA-256 d’affichage natif est une identité binaire, pas du texte."""
    insert = re.match(r"\s*INSERT(?:\s+OR\s+\w+)?\s+INTO\s+messages\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)", sql, re.I)
    if insert:
        columns = [column.strip().lower() for column in insert[1].split(",")]
        values = [value.strip() for value in insert[2].split(",")]
        if len(columns) == len(values) and all(value == "?" for value in values):
            return {index for index, column in enumerate(columns) if column == "display_identity"}
    update = re.match(r"\s*UPDATE\s+messages\s+SET\s+(.+?)\s+WHERE\b", sql, re.I | re.S)
    if update:
        assignment = re.search(r"\bdisplay_identity\s*=\s*\?", update[1], re.I)
        if assignment:
            return {update[1][:assignment.start()].count("?")}
    return set()


def clean_parameters(parameters, sql=""):
    lease_table = bool(re.match(r"\s*(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|UPDATE)\s+(?:session_turn_leases|compression_locks)\b", sql, re.I))
    opaque_holder = r"pid=\d{1,10}(?::pidns=\d{1,20})?:turn=(?:api-)?[a-f0-9_-]{8,64}(?::(?:api-)?[a-f0-9_-]{8,64}){1,3}:platform=[a-z_]{1,32}"
    # Préserver les grammaires JSON/SQL et les identifiants structurels.
    try:
        prepared = dict(parameters) if isinstance(parameters, dict) else list(parameters)
        digests = {}
        for index in digest_parameter_indexes(sql) if not isinstance(parameters, dict) else ():
            if index < len(prepared) and isinstance(prepared[index], bytes) and len(prepared[index]) == 32:
                digests[index] = prepared[index]
                prepared[index] = None
        cleaned = clean_structure(prepared)
        for index, digest in digests.items():
            cleaned[index] = digest
        if type(cleaned) is not type(parameters) and not (isinstance(parameters, tuple) and isinstance(cleaned, list)):
            raise ValueError()
        if len(cleaned) != len(parameters):
            raise ValueError()
        if isinstance(parameters, dict) and cleaned.keys() != parameters.keys():
            raise ValueError()
        for key in parameters if isinstance(parameters, dict) else range(len(parameters)):
            before = parameters[key]
            if isinstance(before, str) and (before in SQL_CONTROLS or lease_table and re.fullmatch(opaque_holder, before)):
                # Identifiant de verrou généré par Hermes : les chiffres du PID
                # namespace ne sont pas un numéro de téléphone. Hors table de
                # verrous, le même texte reste intégralement assaini.
                cleaned[key] = before
        return cleaned
    except DLPStop:
        raise
    except Exception:
        raise DLPStop("ArcIA DLP : écriture SQLite non qualifiée.") from None


def mutates(sql):
    source = re.sub(r"/\*.*?\*/|--[^\n]*", "", str(sql), flags=re.S).lstrip()
    return bool(source) and source.split(None, 1)[0].upper() in ("INSERT", "UPDATE", "REPLACE", "WITH")


def admit_sql(sql):
    # Lexicaliser avant extraction : une apostrophe dans un commentaire ne
    # commence pas un littéral SQL. Ne pas retirer les commentaires dans les valeurs.
    tokens = re.finditer(r'--[^\n]*|/\*[\s\S]*?\*/|\'(?:\'\'|[^\'])*\'|"(?:""|[^"])*"', str(sql))
    literals = [match.group()[1:-1].replace("''", "'") for match in tokens if match.group().startswith("'")]
    # Les valeurs doivent être liées ; refuser les littéraux sensibles plutôt
    # que réécrire la grammaire SQL. Même sans paramètres, la disponibilité DLP
    # est contrôlée avant une écriture.
    cleaned = clean_texts(literals)
    # Commandes FTS5, jamais des données privées ; spaCy FR classe parfois
    # le mot anglais « delete » comme une personne. L’analyse reste obligatoire.
    if any(before != after and before not in SQL_CONTROLS for before, after in zip(literals, cleaned)):
        raise DLPStop("ArcIA DLP : littéral SQL sensible refusé.")


class GuardedCursor(sqlite3.Cursor):
    def executescript(self, sql):
        admit_sql(sql)
        return super().executescript(sql)

    def execute(self, sql, parameters=()):
        if mutates(sql):
            admit_sql(sql)
        return super().execute(sql, clean_parameters(parameters, sql) if parameters and mutates(sql) else parameters)

    def executemany(self, sql, parameters):
        if mutates(sql):
            admit_sql(sql)
        # Matérialiser et contrôler le lot avant sa première écriture.
        rows = [clean_parameters(row, sql) for row in parameters] if mutates(sql) else parameters
        return super().executemany(sql, rows)


def connection_factory(base):
    if base not in _factories:
        class GuardedConnection(base):
            def execute(self, sql, parameters=()):
                if mutates(sql):
                    admit_sql(sql)
                return super().execute(sql, clean_parameters(parameters, sql) if parameters and mutates(sql) else parameters)

            def executemany(self, sql, parameters):
                if mutates(sql):
                    admit_sql(sql)
                rows = [clean_parameters(row, sql) for row in parameters] if mutates(sql) else parameters
                return super().executemany(sql, rows)

            def executescript(self, sql):
                admit_sql(sql)
                return super().executescript(sql)

            def cursor(self, factory=None):
                if factory is not None and factory is not GuardedCursor:
                    raise DLPStop("ArcIA DLP : curseur SQLite non qualifié.")
                return super().cursor(factory=GuardedCursor)
        _factories[base] = GuardedConnection
    return _factories[base]


def install_sqlite():
    original = sqlite3.connect

    def connect(database, *args, **kwargs):
        # Couvrir aussi les URI file: et les profils Hermes sous le même pod.
        path = str(database).split("?", 1)[0].removeprefix("file:")
        if Path(path).name == "state.db":
            values = list(args)
            if len(values) > 4:
                values[4] = connection_factory(values[4])
            else:
                kwargs["factory"] = connection_factory(kwargs.get("factory", sqlite3.Connection))
            args = tuple(values)
        return original(database, *args, **kwargs)
    sqlite3.connect = connect


def llm_request(request):
    if request.method != "POST":
        return request
    approved = urlsplit(os.environ.get("OPENAI_BASE_URL", ""))
    actual = urlsplit(str(request.url))
    same_gateway = bool(approved.hostname) and (actual.scheme, actual.hostname, actual.port) == (approved.scheme, approved.hostname, approved.port)
    if not same_gateway:
        if re.search(r"/(?:chat/completions|responses|messages|completions|embeddings)(?:/|$)|:(?:streamGenerateContent|generateContent|predict)", request.url.path):
            raise DLPStop("ArcIA DLP : passerelle d'inférence non autorisée.")
        return request
    try:
        trace("llm.admission")
        trace("llm.path." + ("chat" if request.url.path.endswith("/chat/completions") else "responses" if "/responses" in request.url.path else "other"))
        # Les messages, résultats d'outils, instructions et schémas passent ensemble.
        payload = json.loads(request.read())
        cleaned = clean_structure(payload, protocol=True)
        trace("llm.sanitized")
        data = json.dumps(cleaned, ensure_ascii=False).encode()
        import httpx
        headers = dict(request.headers)
        headers.pop("content-length", None)
        return httpx.Request(request.method, request.url, headers=headers, content=data, extensions=request.extensions)
    except DLPStop:
        raise
    except Exception:
        raise DLPStop("ArcIA DLP : requête d'inférence non qualifiée.") from None


def install_httpx():
    import httpx
    sync_send, async_send = httpx.Client.send, httpx.AsyncClient.send

    def send(client, request, *args, **kwargs):
        result = sync_send(client, llm_request(request), *args, **kwargs)
        trace("llm.status." + str(result.status_code))
        return result

    async def asend(client, request, *args, **kwargs):
        result = await async_send(client, await asyncio.to_thread(llm_request, request), *args, **kwargs)
        trace("llm.status." + str(result.status_code))
        return result
    httpx.Client.send, httpx.AsyncClient.send = send, asend


def install_aiohttp():
    from aiohttp import web
    original = web.Application.__init__
    original_write = web.StreamResponse.write

    @web.middleware
    async def admission(request, handler):
        try:
            if request.path in ("/health", "/healthz"):
                await asyncio.to_thread(clean_text, "ArcIA readiness")
            if request.method in ("POST", "PUT", "PATCH") and request.content_type == "application/json":
                trace("input.received")
                payload = await request.json()
                # Remplacer le cache de lecture avant tout traitement Hermes.
                cleaned = await asyncio.to_thread(transform, payload)
                request._read_bytes = json.dumps(cleaned, ensure_ascii=False).encode()
                trace("input.sanitized")
            if request.method == "POST": trace("handler.enter")
            response = await handler(request)
            if request.method == "POST": trace("handler.return")
            if isinstance(response, web.Response) and response.content_type == "application/json" and response.body:
                payload = json.loads(response.body)
                hydrated = await asyncio.to_thread(transform, payload, True)
                response.body = json.dumps(hydrated, ensure_ascii=False).encode()
            return response
        except DLPStop:
            return web.json_response({"error": {"message": "ArcIA DLP : opération refusée par la protection de confidentialité."}}, status=422)

    def initialize(app, *args, **kwargs):
        kwargs["middlewares"] = [admission, *kwargs.get("middlewares", ())]
        original(app, *args, **kwargs)
    web.Application.__init__ = initialize

    async def write(response, data):
        if response.content_type != "text/event-stream":
            return await original_write(response, data)
        buffer = getattr(response, "_arcia_sse_buffer", b"") + bytes(data)
        buffer = buffer.replace(b"\r\n", b"\n")
        if len(buffer) > 1024 * 1024:
            raise DLPStop("ArcIA DLP : trame de streaming non qualifiée.")
        pending = getattr(response, "_arcia_sse_pending", {})
        while b"\n\n" in buffer:
            frame, buffer = buffer.split(b"\n\n", 1)
            content = b"\n".join(line[5:].strip() for line in frame.splitlines() if line.startswith(b"data:"))
            if content and content != b"[DONE]":
                try:
                    event = json.loads(content)
                    # Les événements Hermes nommés (dont approval.request)
                    # possèdent aussi un champ choices, contenant des chaînes.
                    # Ils ne sont pas des chunks OpenAI et gardent leur protocole.
                    named = any(line.startswith(b"event:") for line in frame.splitlines())
                    if not named and isinstance(event, dict) and event.get("choices"):
                        event = await asyncio.to_thread(hydrate_sse_event, event, pending)
                        frame = b"data: " + json.dumps(event, ensure_ascii=False).encode()
                except (ValueError, TypeError):
                    pass
            await original_write(response, frame + b"\n\n")
        response._arcia_sse_buffer = buffer
        response._arcia_sse_pending = pending
    web.StreamResponse.write = write


def hydrate_sse_event(event, pending):
    """Réhydrater après le runtime, même si un jeton arrive sur plusieurs deltas."""
    for choice in event.get("choices", []):
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            continue
        index = choice.get("index", 0)
        combined = pending.pop(index, "") + (delta.get("content") or "")
        if not combined:
            continue
        tail = re.search(r"\[[A-Z_0-9]{0,96}$", combined) if not choice.get("finish_reason") else None
        if tail:
            pending[index] = combined[tail.start():]
            combined = combined[:tail.start()]
        delta["content"] = transform(combined, True)
    return event


def install():
    global INSTALLED
    if INSTALLED:
        return
    scope()
    install_sqlite()
    install_httpx()
    install_aiohttp()
    INSTALLED = True
