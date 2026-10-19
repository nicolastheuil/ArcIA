"""Canaris synthétiques : exécution uniquement dans un namespace jetable contrôlé."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import urllib.error
import urllib.request
import uuid

import runtime_guard as guard

mode = sys.argv[1]
model = "mission-synthetique"
base = os.environ["OPENAI_BASE_URL"].removesuffix("/v1")


def provider_count():
    return json.load(urllib.request.urlopen(base + "/health", timeout=10))["llm_requests"]


def turn(text):
    body = json.dumps({"model": model, "stream": False, "messages": [{"role": "user", "content": text}]}).encode()
    request = urllib.request.Request("http://127.0.0.1:8642/v1/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + os.environ["API_SERVER_KEY"],
        "X-Hermes-Session-Key": uuid.uuid4().hex})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


results = {"guard_loaded": guard.INSTALLED}
connection = sqlite3.connect("/opt/data/state.db")
if mode == "online":
    connection.execute("CREATE TABLE IF NOT EXISTS arcia_qualification_canary (content TEXT)")
    connection.execute("INSERT INTO arcia_qualification_canary VALUES (?)", ("contact.synthetic+sql@example.org",))
    connection.commit()
    stored = connection.execute("SELECT content FROM arcia_qualification_canary").fetchone()[0]
    results["sqlite_redacted_before_write"] = "contact.synthetic+sql@example.org" not in stored and "[EMAIL_" in stored
    before = provider_count()
    code = turn("ARCIA_SYNTHETIC_BLOCKED_INPUT\n-----BEGIN PRIVATE KEY-----\nSYNTHETIC_ONLY\n-----END PRIVATE KEY-----")
    results["secret_input_http_422"] = code == 422
    results["blocked_input_no_llm_call"] = provider_count() == before
    results["blocked_input_not_persisted"] = "ARCIA_SYNTHETIC_BLOCKED_INPUT" not in "\n".join(connection.iterdump())
    for name, value in (("cidr", "10.240.0.0/16"), ("mac", "00:1A:2B:3C:4D:5E"), ("hostname", "synthetic.internal")):
        before = provider_count()
        marker = "ARCIA_SYNTHETIC_BLOCKED_" + name.upper()
        results[name + "_input_http_422"] = turn(marker + " " + value) == 422
        results[name + "_no_provider_or_persistence"] = provider_count() == before and marker not in "\n".join(connection.iterdump())
    persisted = "\n".join(connection.iterdump())
    results["tool_pii_not_persisted"] = "tool.synthetic+dlp@example.org" not in persisted
    results["input_pii_not_persisted"] = "contact.synthetic+input@example.org" not in persisted
    original = "alice.synthetic+vault@example.org"
    token = guard.plugin.sanitize_via_presidio(original, session_id=guard.scope())
    results["own_scope_rehydrates"] = guard.plugin.deanonymize_via_presidio(token, session_id=guard.scope()) == original
    results["other_scope_never_rehydrates"] = guard.plugin.deanonymize_via_presidio(token, session_id="synthetic-unknown-" + uuid.uuid4().hex) == token
    from hermes_cli.plugins import discover_plugins, get_plugin_manager
    discover_plugins()
    results["native_plugin_discovered"] = any(item.get("name") == "arcia_governance" and item.get("enabled") for item in get_plugin_manager().list_plugins())
elif mode == "outage":
    before = provider_count()
    results["outage_input_http_422"] = turn("ARCIA_SYNTHETIC_OUTAGE_INPUT") == 422
    try:
        connection.execute("INSERT INTO arcia_qualification_canary VALUES (?)", ("ARCIA_SYNTHETIC_OUTAGE_SQL",))
        results["outage_sqlite_denied"] = False
    except guard.DLPStop:
        results["outage_sqlite_denied"] = True
    import httpx
    try:
        with httpx.Client(timeout=15) as client:
            client.post(os.environ["OPENAI_BASE_URL"] + "/chat/completions", json={"model": model, "messages": [{"role": "user", "content": "ARCIA_SYNTHETIC_OUTAGE_LLM"}]})
        results["outage_llm_transport_denied"] = False
    except guard.DLPStop:
        results["outage_llm_transport_denied"] = True
    results["outage_no_provider_call"] = provider_count() == before
    data = "\n".join(connection.iterdump())
    results["outage_no_persistence"] = "ARCIA_SYNTHETIC_OUTAGE_" not in data
elif mode == "recovery":
    results["dlp_recovered"] = turn("ARCIA_SYNTHETIC_RECOVERY") == 200
print("ARCIA_GOVERNANCE=" + json.dumps(results))
