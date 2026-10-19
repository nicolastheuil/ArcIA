"""Client de recette exécuté exclusivement dans un portail de qualification jetable.

Les credentials générés ne sont jamais affichés. Aucun compte existant n'est lu.
"""
import json
import re
import secrets
import sys
import urllib.error
import urllib.request


def request(path, payload=None, token=None, cookie=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if cookie:
        headers["Cookie"] = "token=" + cookie
    req = urllib.request.Request("http://127.0.0.1:8080" + path,
                                 data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        # Classifier localement ; ne jamais restituer un corps d'erreur arbitraire.
        body = error.read().decode("utf-8", errors="replace")
        reason = "workspace_binding" if "Espace Hermes privé non provisionné" in body else (
            "model_access" if any(word in body.lower() for word in ("model not found", "access denied", "not authorized", "permission")) else "http_error")
        return error.code, json.dumps({"reason_code": reason}).encode()


if sys.argv[1] == "create":
    accounts = {}
    for name in ("admin", "alice", "charlie", "bob"):
        payload = {"name": name, "email": "synthetic." + name + "@example.org", "password": "Q!a9" + secrets.token_urlsafe(32)}
        if name == "admin":
            status, body = request("/api/v1/auths/signup", payload)
        else:
            payload["role"] = "user"
            status, body = request("/api/v1/auths/add", payload, accounts["admin"]["token"])
        if status != 200:
            raise SystemExit("Création des comptes de qualification refusée : HTTP " + str(status))
        user = json.loads(body)
        accounts[name] = {"id": user["id"], "token": user["token"]}
    status, _ = request("/api/v1/models/create", {"id": "mission-synthetique", "name": "mission-synthetique", "base_model_id": None,
        "meta": {}, "params": {}, "access_grants": [
            {"principal_type": "user", "principal_id": accounts[name]["id"], "permission": "read"} for name in ("alice", "charlie", "bob")]}, accounts["admin"]["token"])
    if status != 200:
        raise SystemExit("Droits natifs de qualification refusés : HTTP " + str(status))
    # Sortie consommée en mémoire uniquement par l'orchestrateur local protégé.
    print("ARCIA_ACCOUNTS=" + json.dumps(accounts))
elif sys.argv[1] == "test":
    accounts = json.load(sys.stdin)
    results = {}
    links = {}
    for name in ("alice", "charlie", "bob"):
        token = accounts[name]["token"]
        serial = {"alice": "111", "charlie": "222", "bob": "333"}[name]
        status, body = request("/openai/chat/completions", {"model": "mission-synthetique", "stream": name == "charlie",
                "messages": [{"role": "user", "content": "Génère le fichier CSV synthétique demandé pour cette recette. ARCIA_SYNTHETIC_OWNER_" + serial + " contact.synthetic+input@example.org"}]}, token)
        results[name + "_generation_http"] = status
        if status != 200:
            results[name + "_failure_boundary"] = json.loads(body).get("reason_code", "unknown")
        match = re.search(rb"/api/v1/arcia/hermes-files/[a-f0-9]{32}", body)
        results[name + "_download_link"] = bool(match)
        if not match:
            # Statistiques de protocole uniquement, jamais le contenu ni les comptes.
            events = []
            if name == "charlie":
                for line in body.splitlines():
                    if line.startswith(b"data:"):
                        try:
                            events.append(json.loads(line[5:]))
                        except ValueError:
                            pass
            else:
                try:
                    events.append(json.loads(body))
                except ValueError:
                    pass
            results[name + "_response_diagnostic"] = {
                "finish_reasons": [choice.get("finish_reason") for event in events if isinstance(event, dict)
                                   for choice in event.get("choices", []) if isinstance(choice, dict) and choice.get("finish_reason")],
                "error_present": any(isinstance(event, dict) and bool(event.get("error")) for event in events),
                "done_present": b"data: [DONE]" in body,
            }
        if match:
            link = match[0].decode()
            links[name] = link
            download_status, downloaded = request(link, token=token)
            results[name + "_download_exact_bytes"] = download_status == 200 and downloaded == ("proprietaire,valeur\n" + name + ",42\n").encode()
            cookie_status, cookie_bytes = request(link, cookie=token)
            results[name + "_session_cookie_download"] = cookie_status == 200 and cookie_bytes == downloaded
            for other in ("alice", "charlie", "bob"):
                if other != name:
                    results[name + "_denied_to_" + other] = request(link, token=accounts[other]["token"])[0] == 404
                    results[name + "_cookie_denied_to_" + other] = request(link, cookie=accounts[other]["token"])[0] == 404
            results[name + "_anonymous_denied"] = request(link)[0] == 401
            results[name + "_admin_denied"] = request(link, token=accounts["admin"]["token"])[0] == 403
    results["_links"] = links
    print("ARCIA_QUALIFICATION=" + json.dumps(results))
elif sys.argv[1] == "recheck":
    payload = json.load(sys.stdin)
    status, body = request(payload["link"], token=payload["token"])
    print("ARCIA_QUALIFICATION=" + json.dumps({"download_after_restart": status == 200 and body == b"proprietaire,valeur\nalice,42\n"}))
