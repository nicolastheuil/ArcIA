"""Canaris aval : exécutés dans le proxy du namespace synthétique uniquement."""
import json
import sys
import time
import urllib.error
import urllib.request

payload = json.load(sys.stdin)


def count():
    return json.load(urllib.request.urlopen("http://synthetic-provider:4000/health", timeout=10))["llm_requests"]


def turn(text, stream=False):
    data = json.dumps({"model": "mission-synthetique", "stream": stream,
                       "messages": [{"role": "user", "content": text}]}).encode()
    request = urllib.request.Request("http://127.0.0.1:4000/v1/chat/completions", data=data,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + payload["key"]})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read().decode()
            return response.status, "[DONE]" in body
    except urllib.error.HTTPError as error:
        return error.code, False


results = {}
if payload["mode"] == "online":
    results["benign_http_200"] = turn("Bonjour synthétique")[0] == 200
    results["streaming_complete"] = turn("Bonjour synthétique", stream=True) == (200, True)
    for name, text in (("pem", "-----BEGIN PRIVATE KEY-----\nSYNTHETIC_ONLY\n-----END PRIVATE KEY-----"),
                       ("cidr", "10.240.0.0/16"), ("mac", "00:1A:2B:3C:4D:5E"), ("hostname", "synthetic.internal")):
        before = count()
        results[name + "_http_422"] = turn(text)[0] == 422
        results[name + "_no_provider_call"] = count() == before
elif payload["mode"] == "outage":
    # Le retrait des endpoints ne coupe pas une connexion HTTP déjà ouverte.
    # Laisser expirer le keep-alive Uvicorn (5 s dans cette configuration).
    time.sleep(7)
    before = count()
    results["outage_http_422"] = turn("Canari de panne synthétique")[0] == 422
    results["outage_no_provider_call"] = count() == before
elif payload["mode"] == "recovery":
    results["recovery_http_200"] = turn("Canari de reprise synthétique")[0] == 200
else:
    raise ValueError("Mode de qualification inconnu")
print("ARCIA_GATEWAY_GUARD=" + json.dumps(results))
