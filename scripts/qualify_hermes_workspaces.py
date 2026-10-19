"""Recette réelle Open-WebUI/Hermes dans un namespace Kubernetes synthétique isolé.

Aucun montage de PVC/Secret d'instance ; aucun fournisseur cloud ; suppression
limitée au namespace créé par cette exécution et portant son nonce de propriété.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
import uuid

import yaml
import deploy
import hermes_files

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--report", default="artifacts/hermes-workspaces-qualification.json")
    parser.add_argument("--real-gateway", action="store_true", help="Intercaler LiteLLM et PostgreSQL réels avant le fournisseur synthétique")
    args = parser.parse_args()
    cfg = deploy.parse_yaml_or_env(args.config)
    k, s = cfg.get("kubernetes", {}), cfg.get("kubernetes", {}).get("remote_ssh", {})
    identity, known = deploy.find_harness_ssh()
    configured = os.path.expandvars(os.path.expanduser(s.get("ssh_key", "")))
    runner = deploy.K8sRunner(mode=k.get("mode", "local"), kubeconfig=k.get("kubeconfig", ""), context=k.get("context", ""),
        ssh_node=s.get("node_ip", "127.0.0.1"), ssh_user=s.get("ssh_user", "debian"), ssh_port=s.get("ssh_port", 22),
        ssh_key=configured if configured and Path(configured).is_file() else identity, known_hosts=known or s.get("known_hosts_file", ""))
    nonce = uuid.uuid4().hex
    namespace = "arcia-qual-files-" + nonce[:12]
    versions = json.loads((ROOT / "deploy/versions.json").read_text(encoding="utf-8"))["components"]
    hermes_image, portal_image = versions["hermes-agent"]["image"], versions["open-webui"]["image"]
    provider_name = "synthetic-provider" if args.real_gateway else "litellm-proxy"
    inference_key = "sk-" + secrets.token_urlsafe(32) if args.real_gateway else "synthetic"
    report = {"namespace": namespace, "hermes_image": hermes_image, "portal_image": portal_image,
              "cloud_provider": False, "production_modified": False, "passed": False,
              "scope": "isolated_hermes_files_api", "security_release_ready": False,
              "real_litellm": args.real_gateway,
              "excluded": ["native_dlp_before_sqlite", "authenticated_browser", "fresh_cluster_rebuild"]}
    stage = "bootstrap"

    def apply(obj):
        runner.apply_manifest(obj if isinstance(obj, str) else json.dumps(obj))

    def exec_portal(mode, payload=None):
        source = (ROOT / "services/open_webui/qualify_workspaces.py").read_text(encoding="utf-8")
        # Le code part sur stdin, le payload privé est inclus uniquement en mémoire.
        if payload is not None:
            source = "import io, sys\nsys.stdin=io.StringIO(" + repr(json.dumps(payload)) + ")\n" + source
        rc, output, error = runner.run(["exec", "-i", "deployment/open-webui", "-n", namespace, "--", "python3", "-", mode], stdin_input=source, timeout=650)
        if rc:
            import re
            report["client_http_errors"] = re.findall(r"HTTP (\d{3})", output + error)
            report["client_error_types"] = re.findall(r"[A-Za-z]+Error(?=:)", error)
            raise RuntimeError("Client de qualification en échec ; aucune donnée de compte affichée")
        prefix = "ARCIA_ACCOUNTS=" if mode == "create" else "ARCIA_QUALIFICATION="
        return json.loads(next(line[len(prefix):] for line in output.splitlines() if line.startswith(prefix)))

    def gateway_guard(mode):
        if not args.real_gateway:
            return {}
        source = (ROOT / "tests/fixtures/gateway_guard_probe.py").read_text(encoding="utf-8")
        source = "import io,sys\nsys.stdin=io.StringIO(" + repr(json.dumps({"mode": mode, "key": inference_key})) + ")\n" + source
        rc, output, _ = runner.run(["exec", "-i", "deployment/litellm-proxy", "-n", namespace, "--", "python3", "-"],
                                   stdin_input=source, timeout=180)
        if rc:
            raise RuntimeError("Canaris du guardrail aval en échec")
        return json.loads(next(line[len("ARCIA_GATEWAY_GUARD="):] for line in output.splitlines() if line.startswith("ARCIA_GATEWAY_GUARD=")))

    try:
        print("Création du namespace de qualification isolé.", flush=True)
        apply({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace, "annotations": {"arcia.io/qualification": nonce}}})
        # Aucun egress hors du namespace, sauf DNS système.
        apply({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "qualification-isolation", "namespace": namespace},
               "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"], "ingress": [{"from": [{"podSelector": {}}]}],
                        "egress": [{"to": [{"podSelector": {}}]}, {"to": [{"namespaceSelector": {}, "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}}}],
                                                                    "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]}]}})
        code = {"files.py": (ROOT / "services/hermes/files.py").read_text(encoding="utf-8"),
                "provider.py": (ROOT / "tests/fixtures/hermes_e2e_provider.py").read_text(encoding="utf-8"),
                "error_handler.py": (ROOT / "services/litellm/error_handler.py").read_text(encoding="utf-8")}
        apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "qualification-code", "namespace": namespace}, "data": code})
        apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "hermes-files-code", "namespace": namespace}, "data": {"files.py": code["files.py"]}})
        apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "hermes-runtime-guard", "namespace": namespace}, "data": hermes_files.governance_code(ROOT)})
        presidio_code = {name: (ROOT / "services/presidio" / name).read_text(encoding="utf-8") for name in ("app.py", "requirements.txt")}
        apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "presidio-code", "namespace": namespace}, "data": presidio_code})
        # Uniquement le DLP synthétique peut télécharger ses dépendances publiques.
        apply({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "qualification-presidio-bootstrap", "namespace": namespace},
               "spec": {"podSelector": {"matchLabels": {"app": "presidio-dlp"}}, "policyTypes": ["Egress"], "egress": [{"ports": [{"protocol": "TCP", "port": 443}]}]}})
        presidio_manifest = deploy.adapt_manifest_namespace((ROOT / "deploy/manifests/03-presidio.yaml").read_text(encoding="utf-8"), namespace)
        apply(presidio_manifest)
        print("Initialisation du véritable Presidio et des modèles NLP épinglés.", flush=True)
        stage = "presidio_startup"
        rc, _, _ = runner.run(["rollout", "status", "deployment/presidio-dlp", "-n", namespace, "--timeout=600s"], timeout=620)
        if rc:
            raise RuntimeError("Presidio réel de qualification indisponible")
        provider_pod = {"automountServiceAccountToken": False, "containers": [{"name": "provider", "image": hermes_image,
            "command": ["python3", "/code/provider.py"], "ports": [{"containerPort": 4000}],
            "volumeMounts": [{"name": "code", "mountPath": "/code", "readOnly": True}]}], "volumes": [{"name": "code", "configMap": {"name": "qualification-code"}}]}
        apply({"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": provider_name, "namespace": namespace},
               "spec": {"replicas": 1, "selector": {"matchLabels": {"app": provider_name}}, "template": {"metadata": {"labels": {"app": provider_name}}, "spec": provider_pod}}})
        apply({"apiVersion": "v1", "kind": "Service", "metadata": {"name": provider_name, "namespace": namespace},
               "spec": {"selector": {"app": provider_name}, "ports": [{"port": 4000, "targetPort": 4000}]}})
        if args.real_gateway:
            stage = "real_gateway_startup"
            db_password = secrets.token_urlsafe(32)
            apply(deploy.make_secret_manifest("qualification-gateway", namespace, {"master-key": inference_key,
                "db-password": db_password, "database-url": "postgresql://litellm:" + db_password + "@litellm-db:5432/litellm"}))
            gateway_config = {"model_list": [{"model_name": "mission-synthetique", "litellm_params": {
                "model": "openai/synthetic-model", "api_base": "http://synthetic-provider:4000/v1", "api_key": "synthetic"}}],
                "general_settings": {"master_key": "os.environ/LITELLM_MASTER_KEY", "database_url": "os.environ/DATABASE_URL"},
                "litellm_settings": {"callbacks": "error_handler.proxy_handler_instance"},
                "guardrails": [{"guardrail_name": "presidio-guard", "litellm_params": {"guardrail": "presidio", "mode": "pre_call",
                    "pii_entities_config": {"EMAIL_ADDRESS": "MASK"}, "timeout": 5,
                    "default_on": True, "presidio_analyzer_api_base": "http://presidio-dlp:8080", "presidio_anonymizer_api_base": "http://presidio-dlp:8080"}}]}
            apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "qualification-gateway", "namespace": namespace},
                   "data": {"config.yaml": yaml.safe_dump(gateway_config)}})
            db_env = [{"name": "POSTGRES_DB", "value": "litellm"}, {"name": "POSTGRES_USER", "value": "litellm"},
                      {"name": "POSTGRES_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "qualification-gateway", "key": "db-password"}}}]
            for name, image, container in (
                ("litellm-db", versions["litellm-db"]["image"], {"env": db_env,
                    "volumeMounts": [{"name": "data", "mountPath": "/var/lib/postgresql"}]}),
                ("litellm-proxy", versions["litellm-proxy"]["image"], {"args": ["--config", "/config/config.yaml", "--port", "4000"],
                    "env": [{"name": "PYTHONPATH", "value": "/code"}] + [{"name": name, "valueFrom": {"secretKeyRef": {"name": "qualification-gateway", "key": key}}}
                            for name, key in (("LITELLM_MASTER_KEY", "master-key"), ("DATABASE_URL", "database-url"))],
                    "volumeMounts": [{"name": "config", "mountPath": "/config", "readOnly": True},
                                     {"name": "code", "mountPath": "/code", "readOnly": True}],
                    "readinessProbe": {"httpGet": {"path": "/health/liveliness", "port": 4000}, "periodSeconds": 5}})):
                container.update(name=name, image=image, resources={"requests": {"cpu": "100m", "memory": "256Mi"},
                    "limits": {"cpu": "1", "memory": "2Gi"}})
                pod = {"automountServiceAccountToken": False, "containers": [container], "volumes": [
                    {"name": "data", "emptyDir": {}}, {"name": "config", "configMap": {"name": "qualification-gateway"}},
                    {"name": "code", "configMap": {"name": "qualification-code"}}]}
                apply({"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": name, "namespace": namespace},
                    "spec": {"replicas": 1, "selector": {"matchLabels": {"app": name}}, "template": {"metadata": {"labels": {"app": name}}, "spec": pod}}})
                port = 5432 if name == "litellm-db" else 4000
                apply({"apiVersion": "v1", "kind": "Service", "metadata": {"name": name, "namespace": namespace},
                    "spec": {"selector": {"app": name}, "ports": [{"port": port, "targetPort": port}]}})
            print("Qualification du véritable LiteLLM et de PostgreSQL ; données exclusivement synthétiques.", flush=True)
            rc, _, _ = runner.run(["rollout", "status", "deployment/litellm-proxy", "-n", namespace, "--timeout=600s"], timeout=620)
            if rc:
                raise RuntimeError("Passerelle réelle de qualification indisponible")
            report["litellm_image"] = versions["litellm-proxy"]["image"]
            report["postgres_image"] = versions["litellm-db"]["image"]
            report["gateway_guard_checks"] = gateway_guard("online")
            if not all(report["gateway_guard_checks"].values()):
                raise RuntimeError("La barrière LiteLLM ne refuse pas correctement les canaris ; arrêt avant la recette longue")
        portal_code = {name: (ROOT / "services/open_webui" / name).read_text(encoding="utf-8") for name in ("start.py", "arcia_webui.py", "branding.py", "arcia_hermes_files.py")}
        apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "portal-code", "namespace": namespace}, "data": portal_code})
        portal_env = {"WEBUI_AUTH": "true", "ENABLE_SIGNUP": "true", "DEFAULT_USER_ROLE": "user", "ENABLE_OLLAMA_API": "false",
            "ENABLE_PERSISTENT_CONFIG": "false", "ENABLE_DIRECT_CONNECTIONS": "false", "ENABLE_FORWARD_USER_INFO_HEADERS": "true",
            "ARCIA_HERMES_FILES_ENABLED": "true", "OPENAI_API_BASE_URLS": "http://litellm-proxy:4000/v1;http://127.0.0.1:8080/api/v1/arcia/hermes/v1",
            "OPENAI_API_KEYS": "synthetic;__ARCIA_HERMES_FILES_KEY__", "OPENAI_API_CONFIGS": json.dumps({"0": {"enable": False, "model_ids": []}, "1": {"enable": True, "model_ids": ["mission-synthetique"]}}),
            "DEFAULT_MODELS": "mission-synthetique", "ENABLE_VERSION_UPDATE_CHECK": "false", "HF_HUB_OFFLINE": "1", "OFFLINE_MODE": "true",
            "RAG_EMBEDDING_ENGINE": "openai", "RAG_EMBEDDING_OPENAI_API_BASE_URL": "http://litellm-proxy:4000/v1",
            "RAG_EMBEDDING_OPENAI_API_KEY": "synthetic", "RAG_EMBEDDING_MODEL_AUTO_UPDATE": "false",
            "RAG_RERANKING_MODEL_AUTO_UPDATE": "false", "WHISPER_MODEL_AUTO_UPDATE": "false"}
        portal_pod = {"automountServiceAccountToken": False, "containers": [{"name": "open-webui", "image": portal_image,
            "command": ["python3", "/code/start.py"], "env": [{"name": name, "value": value} for name, value in portal_env.items()],
            "readinessProbe": {"httpGet": {"path": "/health", "port": 8080}, "initialDelaySeconds": 20},
            "volumeMounts": [{"name": "code", "mountPath": "/code", "readOnly": True}, {"name": "data", "mountPath": "/app/backend/data"},
                             {"name": "bindings", "mountPath": "/etc/arcia-hermes-files", "readOnly": True}]}],
            "volumes": [{"name": "code", "configMap": {"name": "portal-code"}}, {"name": "data", "emptyDir": {}},
                        {"name": "bindings", "secret": {"secretName": "arcia-hermes-files-bindings", "optional": True}}]}
        apply({"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "open-webui", "namespace": namespace},
               "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "open-webui"}}, "template": {"metadata": {"labels": {"app": "open-webui"}}, "spec": portal_pod}}})
        print("Démarrage des images officielles Open-WebUI et Hermes.", flush=True)
        stage = "portal_startup"
        rc, _, _ = runner.run(["rollout", "status", "deployment/open-webui", "-n", namespace, "--timeout=360s"], timeout=380)
        if rc:
            raise RuntimeError("Portail de qualification indisponible")
        stage = "account_creation"
        accounts = exec_portal("create")
        fixture_cfg = {"kubernetes": {"namespace": namespace}, "llm_gateway": {"models_routing": [
            {"alias": "mission-synthetique", "category": "agentic", "provider": "openai", "target_model": "synthetic-model"}]}}
        hermes_config = deploy.build_hermes_config_data(fixture_cfg, namespace)
        apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "hermes-config", "namespace": namespace}, "data": {"config.yaml": hermes_config}})
        bindings = {}
        for name in ("alice", "charlie", "bob"):
            stage = "runtime_startup_" + name
            identity = accounts[name]["id"]
            runtime = hermes_files.runtime_for(identity)
            service = "hermes-poweruser-synthetic-expert" if name == "bob" else "hermes-files-" + runtime
            key = secrets.token_urlsafe(48)
            apply(deploy.make_secret_manifest(service, namespace, {"api-server-key": key}))
            template = (ROOT / "deploy/manifests/templates/hermes-files.template.yaml").read_text(encoding="utf-8")
            for variable, value in {"NAME": service, "NAMESPACE": namespace, "IMAGE": hermes_image, "OWNER": hashlib.sha256(identity.encode()).hexdigest(),
                                    "INFERENCE_SECRET": service, "CODE_REVISION": "synthetic", "CONFIG_REVISION": "synthetic",
                                    "GOVERNANCE_REVISION": hermes_files.governance_revision(ROOT)}.items():
                template = template.replace("{{" + variable + "}}", value)
            documents = list(yaml.safe_load_all(template))
            # La même image et le vrai outil terminal, avec une clé fournisseur factice.
            apply(deploy.make_secret_manifest(service, namespace, {"api-server-key": key, "virtual-key": inference_key}))
            if name == "bob":
                command = documents[1]["spec"]["template"]["spec"]["initContainers"][0]["command"]
                command[2] += "; test -f /opt/data/SOUL.md || echo ARCIA_SYNTHETIC_POWERUSER_PERSONALIZATION > /opt/data/SOUL.md"
                documents[0]["metadata"]["name"] = "hermes-user-synthetic-expert-pvc"
                private_pod = documents[1]["spec"]["template"]["spec"]
                next(volume for volume in private_pod["volumes"] if volume["name"] == "state")["persistentVolumeClaim"]["claimName"] = "hermes-user-synthetic-expert-pvc"
                private_pod["containers"] = [c for c in private_pod["containers"] if c["name"] == "hermes"]
                documents[1]["spec"]["template"]["metadata"]["labels"].pop("arcia.io/component")
                documents[1]["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/name"] = "hermes-poweruser"
                apply(deploy.make_secret_manifest("hermes-user-synthetic-expert-secret", namespace, {"litellm-pat": key}))
            # Fixture sans plugin d'instance : aucun montage de données privées.
            pod = documents[1]["spec"]["template"]["spec"]
            next(c for c in pod["containers"] if c["name"] == "hermes")["env"].append({"name": "ARCIA_DLP_TRACE", "value": "true"})
            pod["initContainers"][0]["command"][2] = pod["initContainers"][0]["command"][2].replace("cp /etc/governance/plugin.py /opt/data/plugins/arcia_governance/plugin.py; ", "")
            pod["volumes"] = [v for v in pod["volumes"] if v["name"] != "governance"]
            pod["initContainers"][0]["volumeMounts"] = [v for v in pod["initContainers"][0]["volumeMounts"] if v["name"] != "governance"]
            for document in documents:
                apply(document)
            bindings[identity] = {"runtime": runtime, "namespace": namespace, "key": key, "service": service}
            if name == "bob":
                bindings[identity]["poweruser_slug"] = "synthetic-expert"
            rc, _, _ = runner.run(["rollout", "status", "deployment/" + service, "-n", namespace, "--timeout=360s"], timeout=380)
            if rc:
                raise RuntimeError("Runtime Hermes de qualification indisponible")
            if name == "bob":
                rc, output, _ = runner.run(["get", "deployment", service, "-n", namespace, "-o", "json"], timeout=20)
                previous_hermes = next(c for c in json.loads(output)["spec"]["template"]["spec"]["containers"] if c["name"] == "hermes")
                preserve_probe = "import hashlib; from pathlib import Path; p=Path('/opt/data/config.yaml'); print(hashlib.sha256(p.read_bytes()).hexdigest())"
                rc, config_before, _ = runner.run(["exec", "-i", "deployment/" + service, "-c", "hermes", "-n", namespace, "--", "python3", "-"],
                    stdin_input="from pathlib import Path\np=Path('/opt/data/config.yaml')\np.write_text(p.read_text() + '\\narcia_synthetic_preference: preserve_studio_settings\\n')\n" + preserve_probe, timeout=30)
                if rc:
                    raise RuntimeError("Personnalisation synthétique impossible")
                bindings[identity] = hermes_files.attach_poweruser(
                    {"webui_user_id": identity, "poweruser_slug": "synthetic-expert"}, runner, namespace, ROOT)
                rc, output, _ = runner.run(["get", "deployment", service, "-n", namespace, "-o", "json"], timeout=20)
                actual = next(c for c in json.loads(output)["spec"]["template"]["spec"]["containers"] if c["name"] == "hermes")
                report["poweruser_launch_preserved"] = actual["image"] == previous_hermes["image"] and actual["command"] == hermes_files.guarded_command(previous_hermes["command"])
                rc, config_after, _ = runner.run(["exec", "-i", "deployment/" + service, "-c", "hermes", "-n", namespace, "--", "python3", "-"],
                    stdin_input=preserve_probe, timeout=30)
                report["poweruser_config_unchanged"] = rc == 0 and config_before.strip() == config_after.strip()
        apply(deploy.make_secret_manifest("arcia-hermes-files-bindings", namespace, {"bindings.json": json.dumps(bindings)}))
        # Retirer l'autorisation de bootstrap et tester les véritables politiques du socle.
        policy = (ROOT / "deploy/manifests/09-network-policy.yaml").read_text(encoding="utf-8")
        runner.apply_manifest(deploy.adapt_manifest_namespace(policy, namespace))
        if args.real_gateway:
            for app, direction, peer in (("litellm-proxy", "Egress", "synthetic-provider"), ("synthetic-provider", "Ingress", "litellm-proxy")):
                rule = "egress" if direction == "Egress" else "ingress"
                to_from = "to" if direction == "Egress" else "from"
                apply({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {
                    "name": "qualification-" + app, "namespace": namespace}, "spec": {"podSelector": {"matchLabels": {"app": app}},
                    "policyTypes": [direction], rule: [{to_from: [{"podSelector": {"matchLabels": {"app": peer}}}],
                    "ports": [{"protocol": "TCP", "port": 4000}]}]}})
            # Diagnostic en lecture seule du fournisseur déterministe, réservé
            # aux trois runtimes de cette recette ; aucune destination cloud.
            runtime_selector = {"matchExpressions": [{"key": "app", "operator": "In", "values": [b["service"] for b in bindings.values()]}]}
            apply({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {
                "name": "qualification-provider-counter-ingress", "namespace": namespace}, "spec": {
                "podSelector": {"matchLabels": {"app": "synthetic-provider"}}, "policyTypes": ["Ingress"],
                "ingress": [{"from": [{"podSelector": runtime_selector}], "ports": [{"protocol": "TCP", "port": 4000}]}]}})
            apply({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {
                "name": "qualification-provider-counter-egress", "namespace": namespace}, "spec": {
                "podSelector": runtime_selector, "policyTypes": ["Egress"], "egress": [{"to": [{"podSelector": {
                    "matchLabels": {"app": "synthetic-provider"}}}], "ports": [{"protocol": "TCP", "port": 4000}]}]}})
        runner.run(["delete", "networkpolicy", "qualification-isolation", "-n", namespace], timeout=20)
        runner.run(["delete", "networkpolicy", "qualification-presidio-bootstrap", "-n", namespace], timeout=20)
        print("Recette authentifiée : génération réelle, téléchargement et droits croisés.", flush=True)
        stage = "generation_and_download"
        # Un Secret optionnel créé après le pod peut attendre plusieurs cycles
        # kubelet. Vérifier le contenu projeté, sans jamais l'afficher.
        stage = "bindings_projection"
        expected = hashlib.sha256(json.dumps(bindings, sort_keys=True).encode()).hexdigest()
        projection_probe = """import hashlib, json, pathlib, sys
try:
    data = json.loads(pathlib.Path('/etc/arcia-hermes-files/bindings.json').read_text())
    sys.exit(0 if hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest() == sys.argv[1] else 1)
except (OSError, ValueError):
    sys.exit(1)
"""
        for _ in range(45):
            rc, _, _ = runner.run(["exec", "-i", "deployment/open-webui", "-n", namespace, "--", "python3", "-", expected],
                                   stdin_input=projection_probe, timeout=10)
            if rc == 0:
                break
            time.sleep(4)
        else:
            raise RuntimeError("Associations privées non projetées dans le délai de qualification")
        stage = "generation_and_download"
        report["checks"] = exec_portal("test", accounts)
        links = report["checks"].pop("_links", {})
        # Lire seulement les bases jetables de cette recette. Le rapport ne contient
        # que les booléens, jamais un transcript ou un identifiant de compte.
        for name in ("alice", "charlie", "bob"):
            source = """import json, pathlib, sqlite3, sys
home = pathlib.Path('/opt/data')
databases = list(home.rglob('state.db'))
contents = ''
for path in databases:
    connection = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)
    contents += '\\n'.join(connection.iterdump())
    connection.close()
owner = sys.argv[1]
markers = {name: 'ARCIA_SYNTHETIC_OWNER_' + serial for name, serial in (('alice', '111'), ('charlie', '222'), ('bob', '333'))}
print(json.dumps({'own_history_persisted': markers[owner] in contents,
                  'other_histories_absent': all(marker not in contents for name, marker in markers.items() if name != owner),
                  'raw_pii_absent': all(pii not in contents for pii in ('contact.synthetic+input@example.org', 'tool.synthetic+dlp@example.org')),
                  '_diagnostic': {'message_rows': sum(sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True).execute('SELECT count(*) FROM messages').fetchone()[0] for path in databases),
                                  'marker_prefix_present': 'ARCIA_SYNTHETIC_OWNER_' in contents}}))
"""
            rc, output, _ = runner.run(["exec", "-i", "deployment/" + bindings[accounts[name]["id"]]["service"], "-c", "hermes", "-n", namespace,
                                       "--", "python3", "-", name], stdin_input=source, timeout=30)
            history = json.loads(output) if rc == 0 else {"own_history_persisted": False, "other_histories_absent": False}
            report.setdefault("history_diagnostics", {})[name] = history.pop("_diagnostic", {})
            report["checks"].update({name + "_" + key: value for key, value in history.items()})
        alice_binding = bindings[accounts["alice"]["id"]]
        charlie_binding = bindings[accounts["charlie"]["id"]]
        bob_binding = bindings[accounts["bob"]["id"]]
        probe = "import socket,sys; s=socket.socket(); s.settimeout(3); rc=s.connect_ex((sys.argv[1],8643)); print('ISOLATED='+str(rc!=0))"
        rc, output, _ = runner.run(["exec", "-i", "deployment/" + alice_binding["service"], "-c", "hermes", "-n", namespace,
                                   "--", "python3", "-", bob_binding["service"]], stdin_input=probe, timeout=20)
        report["checks"]["cross_pod_network_denied"] = rc == 0 and "ISOLATED=True" in output
        rc, output, _ = runner.run(["exec", "-i", "deployment/" + alice_binding["service"], "-c", "hermes", "-n", namespace,
                                   "--", "python3", "-", charlie_binding["service"]], stdin_input=probe, timeout=20)
        report["checks"]["standard_to_standard_network_denied"] = rc == 0 and "ISOLATED=True" in output
        rc, output, _ = runner.run(["exec", "-i", "deployment/" + charlie_binding["service"], "-c", "hermes", "-n", namespace,
                                   "--", "python3", "-", alice_binding["service"]], stdin_input=probe, timeout=20)
        report["checks"]["reverse_standard_network_denied"] = rc == 0 and "ISOLATED=True" in output
        if "alice" in links:
            runner.run(["rollout", "restart", "deployment/" + alice_binding["service"], "-n", namespace], timeout=20)
            rc, _, _ = runner.run(["rollout", "status", "deployment/" + alice_binding["service"], "-n", namespace, "--timeout=180s"], timeout=200)
            report["checks"].update(exec_portal("recheck", {"link": links["alice"], "token": accounts["alice"]["token"]}) if rc == 0 else {"download_after_restart": False})
        stage = "native_dlp_qualification"
        print("Recette DLP native : SQLite, outils, refus de secrets, panne et reprise.", flush=True)

        def governance(mode):
            source = (ROOT / "services/hermes/qualify_governance.py").read_text(encoding="utf-8")
            if args.real_gateway:
                source = "import os\nos.environ['ARCIA_QUAL_PROVIDER_HEALTH_URL']='http://synthetic-provider:4000/health'\n" + source
            rc, output, _ = runner.run(["exec", "-i", "deployment/" + alice_binding["service"], "-c", "hermes", "-n", namespace,
                                       "--", "python3", "-", mode], stdin_input=source, timeout=180)
            if rc:
                raise RuntimeError("Client de qualification DLP en échec")
            return json.loads(next(line[len("ARCIA_GOVERNANCE="):] for line in output.splitlines() if line.startswith("ARCIA_GOVERNANCE=")))


        report["governance_checks"] = governance("online")
        report["gateway_guard_checks"] = gateway_guard("online")
        # Simuler une coupure réseau du service sans perdre le Vault en RAM.
        unavailable_service = {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "presidio-dlp", "namespace": namespace},
                               "spec": {"selector": {"app": "arcia-synthetic-dlp-unavailable"}, "ports": [{"port": 8080, "targetPort": 8080}]}}
        apply(unavailable_service)
        time.sleep(3)
        try:
            report["governance_checks"].update(governance("outage"))
            report["gateway_guard_checks"].update(gateway_guard("outage"))
        finally:
            for document in yaml.safe_load_all(presidio_manifest):
                if document and document.get("kind") == "Service":
                    apply(document)
        time.sleep(3)
        report["governance_checks"].update(governance("recovery"))
        report["gateway_guard_checks"].update(gateway_guard("recovery"))
        rc, output, _ = runner.run(["exec", "-i", "deployment/" + provider_name, "-n", namespace, "--", "python3", "-"],
            stdin_input="import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:4000/health').read().decode())", timeout=20)
        report["provider_checks"] = json.loads(output) if rc == 0 else {}
        provider = report["provider_checks"]
        report["governance_checks"]["tool_pii_not_sent_to_provider"] = provider.get("raw_tool_pii_seen") is False and provider.get("tool_result_token_seen") is True
        report["native_dlp_qualified"] = all(value is True for value in report["governance_checks"].values())
        report["passed"] = all(value is True or type(value) is int and value == 200 for value in report["checks"].values()) and bool(provider.get("personalization_seen")) and report.get("poweruser_launch_preserved", False) and report.get("poweruser_config_unchanged", False) and report["native_dlp_qualified"]
        if args.real_gateway:
            report["passed"] = report["passed"] and bool(report["gateway_guard_checks"]) and all(report["gateway_guard_checks"].values())
        if report["native_dlp_qualified"]:
            report["excluded"].remove("native_dlp_before_sqlite")
        print("Résultat de qualification : " + ("réussi" if report["passed"] else "échec"), flush=True)
    except Exception as error:
        import traceback
        report["error_type"] = type(error).__name__
        report["error_locations"] = [{"file": Path(frame.filename).name, "line": frame.lineno} for frame in traceback.extract_tb(error.__traceback__)]
        report["failed_stage"] = stage
        # Le message de K8sRunner peut contenir des Secrets : ne jamais l'afficher.
        print("Qualification interrompue : " + type(error).__name__, flush=True)
    finally:
        if not report["passed"]:
            rc, output, _ = runner.run(["get", "pods", "-n", namespace, "-o", "json"], timeout=20)
            report["pod_diagnostics"] = []
            for pod in json.loads(output).get("items", []) if rc == 0 else []:
                for status in pod.get("status", {}).get("containerStatuses", []):
                    item = {"container": status["name"], "ready": status["ready"], "restart_count": status["restartCount"],
                            "waiting_reason": status.get("state", {}).get("waiting", {}).get("reason"),
                            "exit_code": status.get("lastState", {}).get("terminated", {}).get("exitCode")}
                    rc_log, log, _ = runner.run(["logs", pod["metadata"]["name"], "-c", status["name"], "-n", namespace, "--tail=400"], timeout=20)
                    import re
                    item["import_errors"] = re.findall(r"(?:ModuleNotFoundError: No module named '[\w.]+'|ImportError: cannot import name '[\w.]+'|[A-Za-z]+Error(?=:))", log) if rc_log == 0 else []
                    item["trace_locations"] = [{"file": Path(file).name, "line": int(line)} for file, line in re.findall(r'File "([^"\n]+)", line (\d+)', log)] if rc_log == 0 else []
                    item["guard_events"] = re.findall(r"ArcIA DLP (?:trace: [\w.]+|frame: [\w.]+:\d+:\w+|: refus[^\n]+)", log) if rc_log == 0 else []
                    # Le namespace ne contient que les fixtures synthétiques.
                    # Masquer néanmoins tous les credentials jetables avant de
                    # retenir les erreurs natives utiles au diagnostic.
                    if rc_log == 0:
                        for binding in locals().get("bindings", {}).values():
                            log = log.replace(binding["key"], "[CREDENTIAL]")
                        for account in locals().get("accounts", {}).values():
                            log = log.replace(account["token"], "[CREDENTIAL]")
                        item["synthetic_runtime_errors"] = [line[:500] for line in log.splitlines()
                            if "Agent task " in line and "failed during SSE" in line or "Agent crashed mid-stream" in line or "Error handling request" in line]
                    report["pod_diagnostics"].append(item)
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        rc, output, _ = runner.run(["get", "namespace", namespace, "-o", "json"], timeout=20)
        if rc == 0 and json.loads(output).get("metadata", {}).get("annotations", {}).get("arcia.io/qualification") == nonce:
            runner.run(["delete", "namespace", namespace, "--wait=false"], timeout=30)
            print("Namespace de qualification supprimé ; instance réelle préservée.", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
