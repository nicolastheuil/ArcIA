#!/usr/bin/env python3
"""Diagnostic en lecture seule, sans clés, prompts ni réponses fournisseur."""
import argparse
import base64
import hashlib
import inspect
import json
from pathlib import Path

import deploy
import wizard


def probe_runtime(expected):
    """Exécuté dans le pod ; seules des comparaisons et des quantités sortent."""
    import hashlib
    import json
    import os
    from pathlib import Path
    import urllib.error
    import urllib.request

    key = os.environ.get("LITELLM_MASTER_KEY", "")
    result = {"pod_master_present": bool(key),
              "pod_master_matches_secret": bool(key) and hashlib.sha256(key.encode()).hexdigest() == expected["master_hash"]}
    try:
        result["mounted_config_matches_configmap"] = hashlib.sha256(Path("/app/config.yaml").read_bytes()).hexdigest() == expected["config_hash"]
    except OSError:
        result["mounted_config_matches_configmap"] = False
    for label, endpoint in (("models", "/v1/models"), ("admin_models", "/model/info")):
        try:
            request = urllib.request.Request("http://127.0.0.1:4000" + endpoint,
                                             headers={"Authorization": "Bearer " + key})
            with urllib.request.urlopen(request, timeout=8) as response:
                data = json.load(response).get("data", [])
                result[label + "_http_status"] = response.status
                result[label + "_count"] = len(data)
                names = {m.get("id") if label == "models" else m.get("model_name") for m in data}
                names.discard(None)
                result[label + "_unique_count"] = len(names)
                result[label + "_contains_configured_models"] = set(expected["names"]).issubset(names)
        except urllib.error.HTTPError as exc:
            result[label + "_http_status"] = exc.code
        except Exception:
            result[label + "_http_status"] = None
    return result


def diagnose(cfg, runner):
    ns = cfg.get("kubernetes", {}).get("namespace", "arcia")
    mappings = cfg.get("llm_gateway", {}).get("models_routing", [])
    report = {"local_mapping_count": len(mappings)}
    objects = {}
    for kind, name in (("secret", "litellm-secret"), ("configmap", "litellm-config")):
        rc, out, _ = runner.run(["get", kind, name, "-n", ns, "-o", "json"], timeout=12)
        report[kind + "_read_ok"] = rc == 0
        if rc != 0:
            return report
        objects[kind] = json.loads(out)
    master = base64.b64decode(objects["secret"].get("data", {}).get("master-key", "")).decode()
    config = objects["configmap"].get("data", {}).get("config.yaml", "")
    local_master = cfg.get("llm_gateway", {}).get("master_key", "")
    report.update({"secret_master_present": bool(master),
                   "local_master_matches_secret": local_master == master if local_master else None,
                   "configmap_model_count": config.count("model_name:"),
                   "configmap_matches_local": config == deploy.build_litellm_config_data(cfg, ns)})
    expected = {"master_hash": hashlib.sha256(master.encode()).hexdigest(),
                "config_hash": hashlib.sha256(config.encode()).hexdigest(),
                "names": [m.get("alias") or m.get("name") for m in mappings]}
    source = "import json\n" + inspect.getsource(probe_runtime) + "\nprint(json.dumps(probe_runtime(" + repr(expected) + ")))\n"
    rc, out, _ = runner.run(["exec", "-i", "deployment/litellm-proxy", "-n", ns, "--", "python3", "-"],
                             stdin_input=source, timeout=25)
    report["pod_probe_ok"] = rc == 0
    if rc == 0:
        # Whitelist the output: no raw kubectl, HTTP error body or credentials.
        runtime = json.loads(out)
        for field in ("pod_master_present", "pod_master_matches_secret", "mounted_config_matches_configmap",
                      "models_http_status", "models_count", "models_unique_count", "models_contains_configured_models",
                      "admin_models_http_status", "admin_models_count", "admin_models_unique_count", "admin_models_contains_configured_models"):
            value = runtime.get(field)
            if value is None or isinstance(value, (bool, int)):
                report[field] = value
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "arcia.config.yaml"))
    args = parser.parse_args()
    try:
        cfg = deploy.parse_yaml_or_env(args.config)
        result = diagnose(cfg, wizard.get_k8s_runner(cfg))
    except Exception:
        print(json.dumps({"diagnostic_ok": False, "error": "Diagnostic inaccessible ou incomplet ; vérifier le fichier cible et les accès locaux."}, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    checks = ("secret_read_ok", "configmap_read_ok", "secret_master_present", "configmap_matches_local",
              "pod_probe_ok", "pod_master_matches_secret", "mounted_config_matches_configmap",
              "models_contains_configured_models", "admin_models_contains_configured_models")
    return 0 if all(result.get(k) is True for k in checks) and result.get("models_http_status") == 200 and result.get("admin_models_http_status") == 200 and result.get("local_master_matches_secret") is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
