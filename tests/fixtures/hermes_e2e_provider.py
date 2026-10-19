"""Fournisseur déterministe de recette : aucun appel cloud, uniquement des fichiers synthétiques."""
import json
from pathlib import Path
import re
import shlex
import time
from aiohttp import web

MARKER = "ARCIA_SYNTHETIC_POWERUSER_PERSONALIZATION"
seen = {"llm_requests": 0, "personalization_seen": False, "tool_execution_requested": False,
        "raw_tool_pii_seen": False, "sanitized_tool_token_seen": False, "tool_result_token_seen": False}


async def completions(request):
    body = await request.json()
    seen["llm_requests"] += 1
    messages = body.get("messages", [])
    serialized = json.dumps(messages)
    seen["raw_tool_pii_seen"] |= "tool.synthetic+dlp@example.org" in serialized
    seen["sanitized_tool_token_seen"] |= "[EMAIL_" in serialized
    seen["tool_result_token_seen"] |= any(m.get("role") == "tool" and "[EMAIL_" in str(m.get("content")) for m in messages)
    owner_match = re.findall(r"ARCIA_SYNTHETIC_OWNER_(111|222|333)", serialized)
    owner = {"111": "alice", "222": "charlie", "333": "bob"}[owner_match[-1]] if owner_match else "unknown"
    seen["personalization_seen"] |= MARKER in serialized
    text = "\n".join(str(m.get("content") or "") for m in messages if m.get("role") in ("system", "developer"))
    match = re.search(r"directement dans (.+?)\. Pas de sous-dossiers", text)
    tools = [t["function"] for t in body.get("tools", []) if t.get("type") == "function"]
    terminal = next((t for t in tools if t["name"] == "terminal"), None)
    if match and terminal and not any(m.get("role") == "tool" for m in messages):
        # Exécution par le vrai outil terminal de Hermes, jamais par ce serveur.
        directory = match[1]
        filename = str(Path(directory) / "rapport-synthetique.csv")
        # Une écriture CSV locale suffit ; un interpréteur -c déclencherait
        # légitimement l’approbation d’exécution de code natif de Hermes.
        command = "printf %s " + shlex.quote("proprietaire,valeur\n" + owner + ",42\n") + " > " + shlex.quote(filename)
        # Assembler la PII dans l’outil : le canari doit éprouver l’assainissement
        # de son résultat brut, pas seulement celui des arguments avant exécution.
        command += "; printf '%s%s%s' 'tool.synthetic+dlp' '@' 'example.org'"
        args = {"command": command}
        seen["tool_execution_requested"] = True
        message = {"role": "assistant", "content": None, "tool_calls": [{"id": "synthetic_tool_call", "type": "function",
                   "function": {"name": "terminal", "arguments": json.dumps(args)}}]}
        reason = "tool_calls"
    else:
        message = {"role": "assistant", "content": "Fichier synthétique généré."}
        reason = "stop"
    choice = {"index": 0, "message": message, "finish_reason": reason}
    result = {"id": "chatcmpl-synthetic", "object": "chat.completion", "created": int(time.time()),
              "model": body.get("model", "mission-synthetique"), "choices": [choice],
              "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
    if body.get("stream"):
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        result["object"] = "chat.completion.chunk"
        delta = dict(message)
        if message.get("tool_calls"):
            delta["tool_calls"] = [dict(call, index=index) for index, call in enumerate(message["tool_calls"])]
        result["choices"] = [{"index": 0, "delta": delta, "finish_reason": None}]
        await response.write(b"data: " + json.dumps(result).encode() + b"\n\n")
        result["choices"] = [{"index": 0, "delta": {}, "finish_reason": reason}]
        await response.write(b"data: " + json.dumps(result).encode() + b"\n\ndata: [DONE]\n\n")
        await response.write_eof()
        return response
    return web.json_response(result)


async def models(request):
    return web.json_response({"object": "list", "data": [{"id": "mission-synthetique", "object": "model"}]})


async def status(request):
    return web.json_response(seen)


app = web.Application()
app.router.add_post("/v1/chat/completions", completions)
app.router.add_get("/v1/models", models)
app.router.add_get("/health", status)
web.run_app(app, host="0.0.0.0", port=4000, access_log=None)
