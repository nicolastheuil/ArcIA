"""Provisionnement déclaratif des espaces Hermes privés pour Open-WebUI.

Les identités et références de secrets viennent exclusivement de la configuration
d'instance. Aucun pouvoir Kubernetes n'est donné aux agents.
"""
import hashlib
import json
from pathlib import Path
import re
import secrets
import base64

GOVERNANCE_FILES = ("plugin.py", "runtime_guard.py", "bootstrap.py", "sitecustomize.py", "arcia_required.py", "arcia_governance.pth", "__init__.py", "plugin.yaml")


def governance_code(root_dir):
    return {name: (Path(root_dir) / "services/hermes" / name).read_text(encoding="utf-8") for name in GOVERNANCE_FILES}


def governance_revision(root_dir):
    return hashlib.sha256(json.dumps(governance_code(root_dir), sort_keys=True).encode()).hexdigest()


def guarded_command(command):
    prefix = ["python3", "/opt/arcia-governance/bootstrap.py"]
    if not command:
        raise RuntimeError("Commande Hermes existante absente ; migration refusée")
    return command if command[:2] == prefix else prefix + command


def existing_secret(runner, namespace, name, field):
    """Une erreur de lecture ne signifie jamais qu'il faut remplacer une identité."""
    rc, output, _ = runner.run(["get", "secret", name, "-n", namespace, "--ignore-not-found", "-o", "json"], timeout=20)
    if rc != 0:
        raise RuntimeError("Secret privé invérifiable ; aucune identité remplacée")
    if not output.strip():
        return None
    try:
        return base64.b64decode(json.loads(output)["data"][field], validate=True).decode("utf-8")
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("Secret privé incomplet ; aucune identité remplacée") from None


def declared_users(cfg):
    section = cfg.get("hermes_workspaces") or {}
    users = section.get("users") or []
    if not isinstance(users, list):
        raise ValueError("hermes_workspaces.users doit être une liste")
    seen, pods, inference_secrets = set(), set(), set()
    for user in users:
        if not isinstance(user, dict) or not isinstance(user.get("webui_user_id"), str) or not user["webui_user_id"].strip():
            raise ValueError("Identifiant Open-WebUI stable requis pour chaque espace privé")
        identity = user["webui_user_id"]
        if identity in seen:
            raise ValueError("Compte Open-WebUI déclaré plusieurs fois")
        seen.add(identity)
        slug = user.get("poweruser_slug")
        if slug is not None:
            if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?", slug) or slug in pods:
                raise ValueError("Un pod Power User ne peut appartenir qu'à un seul compte WebUI")
            pods.add(slug)
            continue
        secret = user.get("inference_secret", "")
        if not isinstance(secret, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", secret) or secret == "litellm-secret":
            raise ValueError("Secret LiteLLM nominatif requis, distinct du secret administrateur")
        if secret in inference_secrets:
            raise ValueError("Chaque utilisateur standard doit avoir sa propre clé d'inférence")
        inference_secrets.add(secret)
    return users


def runtime_for(identity):
    return "u-" + hashlib.sha256(identity.encode()).hexdigest()[:24]


def preserve_initializers(pod):
    """Les initialiseurs historiques gérés ne doivent pas réécrire un profil existant."""
    patches = []
    prefix = "# ArcIA preserve existing state\nif [ -f /opt/data/config.yaml ]; then exit 0; fi\n"
    for container in pod.get("initContainers", []):
        if container["name"] not in ("init-user-state", "init-private-state"):
            continue
        command = container.get("command", [])
        if len(command) != 3 or command[0] not in ("sh", "/bin/sh") or command[1] != "-c":
            raise RuntimeError("Initialiseur du Power User non qualifié ; configuration préservée sans modification")
        script = command[2]
        patches.append({"name": container["name"], "command": [*command[:2], script if script.startswith(prefix) else prefix + script]})
    return patches


def sync_private_runtimes(cfg, runner, namespace, root_dir):
    import deploy
    if not isinstance(namespace, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", namespace):
        raise ValueError("Namespace des espaces privés invalide")
    users = declared_users(cfg)
    image = json.loads((Path(root_dir) / "deploy/versions.json").read_text(encoding="utf-8"))["components"]["hermes-agent"]["image"]
    # Isolation installée avant la création du premier pod privé, y compris au rebuild.
    policy = (Path(root_dir) / "deploy/manifests/09-network-policy.yaml").read_text(encoding="utf-8")
    runner.apply_manifest(deploy.adapt_manifest_namespace(policy, namespace))
    bindings = {}
    for user in users:
        identity = user["webui_user_id"]
        runtime = runtime_for(identity)
        name = "hermes-files-" + runtime
        owner = hashlib.sha256(identity.encode()).hexdigest()
        if user.get("poweruser_slug"):
            bindings[identity] = attach_poweruser(user, runner, namespace, root_dir)
            continue
        # Le PVC conserve le propriétaire même si un Deployment a été supprimé.
        rc, output, error = runner.run(["get", "pvc", name, "-n", namespace, "--ignore-not-found", "-o", "json"], timeout=20)
        if rc != 0:
            raise RuntimeError("Propriétaire du volume privé invérifiable ; déploiement refusé")
        if output.strip() and json.loads(output).get("metadata", {}).get("annotations", {}).get("arcia.io/owner") != owner:
            raise RuntimeError("Réaffectation d'un volume Hermes privé interdite")
        # Vérifier la référence sans jamais lire ni afficher sa valeur.
        rc, output, error = runner.run(["get", "secret", user["inference_secret"], "-n", namespace,
                                        "-o", "go-template={{if index .data \"virtual-key\"}}present{{end}}"], timeout=20)
        if not getattr(runner, "dry_run", False) and (rc != 0 or output.strip() != "present"):
            raise RuntimeError("Clé d'inférence nominative absente ; espace privé non provisionné")
        key = existing_secret(runner, namespace, name, "api-server-key") or secrets.token_urlsafe(48)
        runner.apply_manifest(deploy.make_secret_manifest(name, namespace, {"api-server-key": key}))
        bindings[identity] = {"runtime": runtime, "namespace": namespace, "key": key, "service": name}
        template = (Path(root_dir) / "deploy/manifests/templates/hermes-files.template.yaml").read_text(encoding="utf-8")
        values = {"NAMESPACE": namespace, "NAME": name, "OWNER": owner, "IMAGE": image,
                  "INFERENCE_SECRET": user["inference_secret"],
                  "CODE_REVISION": hashlib.sha256((Path(root_dir) / "services/hermes/files.py").read_bytes()).hexdigest(),
                  "GOVERNANCE_REVISION": governance_revision(root_dir),
                  "CONFIG_REVISION": hashlib.sha256(deploy.build_hermes_config_data(cfg, namespace).encode()).hexdigest()}
        for key_name, value in values.items():
            template = template.replace("{{" + key_name + "}}", value)
        storage_class = cfg.get("kubernetes", {}).get("storage_class")
        if storage_class:
            template = template.replace("  accessModes: [ReadWriteOnce]", "  storageClassName: " + json.dumps(storage_class) + "\n  accessModes: [ReadWriteOnce]")
        runner.apply_manifest(template)
        rc, _, _ = runner.run(["rollout", "status", "deployment/" + name, "-n", namespace, "--timeout=360s"], timeout=380)
        if rc != 0:
            raise RuntimeError("Espace privé non disponible ; activation du portail interrompue")
    # Secret monté seulement dans Open-WebUI. Ne jamais ajouter à un ConfigMap public.
    if len({binding["key"] for binding in bindings.values()}) != len(bindings):
        raise RuntimeError("Clés de runtimes partagées interdites ; activation du portail refusée")
    runner.apply_manifest(deploy.make_secret_manifest("arcia-hermes-files-bindings", namespace,
                                                     {"bindings.json": json.dumps(bindings)}))
    if bindings:
        payload = {"user_ids": list(bindings), "model_ids": deploy.build_model_catalog(cfg)["agentic_models"]}
        code = (Path(root_dir) / "services/open_webui/provision_model_access.py").read_text(encoding="utf-8")
        source = "import io, sys\nsys.stdin = io.StringIO(" + repr(json.dumps(payload)) + ")\n" + code
        rc, output, _ = runner.run(["exec", "-i", "deployment/open-webui", "-n", namespace, "--", "python3", "-"], stdin_input=source, timeout=60)
        if rc != 0 or "ARCIA_MODEL_ACCESS=" not in output:
            raise RuntimeError("Droits natifs des modèles WebUI non vérifiés")


def attach_poweruser(user, runner, namespace, root_dir):
    """Ajouter seulement le relais au pod existant. Ne pas réappliquer sa configuration Studio."""
    import deploy
    import tempfile
    identity, slug = user["webui_user_id"], user["poweruser_slug"]
    name = "hermes-poweruser-" + slug
    rc, output, _ = runner.run(["get", "deployment", name, "-n", namespace, "-o", "json"], timeout=20)
    if rc != 0 or not output.strip():
        raise RuntimeError("Pod Power User existant introuvable ; aucun pod de remplacement créé")
    current = json.loads(output)
    if current.get("spec", {}).get("replicas", 1) not in (0, 1):
        raise RuntimeError("Le Power User doit avoir au plus un propriétaire actif")
    pod = current["spec"]["template"]["spec"]
    container = next(c for c in pod["containers"] if c["name"] == "hermes")
    expected_image = json.loads((Path(root_dir) / "deploy/versions.json").read_text(encoding="utf-8"))["components"]["hermes-agent"]["image"]
    if container["image"] != expected_image and not container["image"].startswith(expected_image + "@sha256:"):
        raise RuntimeError("Version installée du Power User non qualifiée pour le relais de fichiers")
    home = next(e["value"] for e in container["env"] if e["name"] == "HERMES_HOME")
    state = next(v for v in container["volumeMounts"] if v["mountPath"] == home)
    pvc_name = next(v["persistentVolumeClaim"]["claimName"] for v in pod["volumes"] if v["name"] == state["name"])
    if home != "/opt/data" or pvc_name != "hermes-user-" + slug + "-pvc":
        raise RuntimeError("Volume du Power User non conforme ; adaptation manuelle requise")
    rc, output, _ = runner.run(["get", "pvc", pvc_name, "-n", namespace, "-o", "json"], timeout=20)
    if rc != 0:
        raise RuntimeError("Propriétaire du volume Power User invérifiable")
    pvc = json.loads(output)
    owner = hashlib.sha256(identity.encode()).hexdigest()
    annotations = pvc["metadata"].get("annotations", {})
    if annotations.get("arcia.io/owner", owner) != owner:
        raise RuntimeError("Le volume Power User est déjà associé à un autre compte")
    key = existing_secret(runner, namespace, "hermes-user-" + slug + "-secret", "litellm-pat")
    if not key or len(key) < 24:
        raise RuntimeError("Clé existante du Power User absente ; aucune identité remplacée")
    # Réutiliser l'image réellement installée et le PVC réellement monté.
    sidecar = {"name": "arcia-files", "image": container["image"],
               "command": ["python3", "/opt/arcia-files/files.py"],
               "securityContext": {"runAsUser": 10000, "runAsGroup": 10000, "allowPrivilegeEscalation": False,
                                   "capabilities": {"drop": ["ALL"]}},
               "env": [{"name": "ARCIA_FILES_ROOT", "value": home + "/exports"},
                       {"name": "API_SERVER_KEY", "valueFrom": {"secretKeyRef": {
                           "name": "hermes-user-" + slug + "-secret", "key": "litellm-pat"}}}],
               "ports": [{"name": "files", "containerPort": 8643}],
               "readinessProbe": {"httpGet": {"path": "/health", "port": 8643}, "initialDelaySeconds": 15},
               "resources": {"requests": {"cpu": "50m", "memory": "128Mi"}, "limits": {"cpu": "500m", "memory": "512Mi"}},
               "volumeMounts": [{"name": state["name"], "mountPath": home},
                                {"name": "arcia-files-code", "mountPath": "/opt/arcia-files", "readOnly": True}]}
    pythonpath = next((entry for entry in container.get("env", []) if entry["name"] == "PYTHONPATH"), {})
    if "valueFrom" in pythonpath:
        raise RuntimeError("PYTHONPATH indirect non qualifié ; personnalisation conservée sans modification")
    pythonpath = ":".join(dict.fromkeys(part for part in ["/opt/arcia-governance", *pythonpath.get("value", "").split(":")] if part))
    revision = hashlib.sha256((Path(root_dir) / "services/hermes/files.py").read_bytes()).hexdigest()
    hermes_patch = {"name": "hermes", "command": guarded_command(container.get("command")),
                    "env": [{"name": "ARCIA_GOVERNANCE_REQUIRED", "value": "true"},
                            {"name": "PYTHONPATH", "value": pythonpath},
                            {"name": "PRESIDIO_DLP_URL", "value": "http://presidio-dlp." + namespace + ".svc:8080/sanitize"},
                            {"name": "PRESIDIO_FAIL_CLOSED", "value": "true"}],
                    "volumeMounts": [{"name": "arcia-runtime-guard", "mountPath": "/opt/arcia-governance", "readOnly": True},
                                     {"name": "arcia-runtime-guard", "mountPath": home + "/plugins/arcia_governance", "readOnly": True},
                                     {"name": "arcia-runtime-guard", "mountPath": "/opt/hermes/.venv/lib/python3.14/site-packages/arcia_governance.pth", "subPath": "arcia_governance.pth", "readOnly": True}]}
    patch = {"spec": {"strategy": {"type": "Recreate", "rollingUpdate": None}, "template": {"metadata": {"annotations": {"checksum/files-code": revision, "checksum/runtime-governance": governance_revision(root_dir)}},
                                   "spec": {"automountServiceAccountToken": False,
                                            "containers": [hermes_patch, sidecar], "volumes": [
                                                {"name": "arcia-runtime-guard", "configMap": {"name": "hermes-runtime-guard"}},
                                                {"name": "arcia-files-code", "configMap": {"name": "hermes-files-code"}}]}}}}
    initializers = preserve_initializers(pod)
    if initializers:
        patch["spec"]["template"]["spec"]["initContainers"] = initializers

    def patch_resource(resource, name, payload, kind):
        if getattr(runner, "mode", "local") == "local":
            with tempfile.TemporaryDirectory(prefix="arcia-workspace-") as directory:
                path = Path(directory) / "patch.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                return runner.run(["patch", resource, name, "-n", namespace, "--type=" + kind, "--patch-file=" + str(path)], timeout=30)[0]
        return runner.run(["patch", resource, name, "-n", namespace, "--type=" + kind, "--patch-file=/dev/stdin"],
                          stdin_input=json.dumps(payload), timeout=30)[0]

    # Test de resourceVersion : une association concurrente ne peut pas être écrasée.
    claim = [{"op": "test", "path": "/metadata/resourceVersion", "value": pvc["metadata"]["resourceVersion"]},
             {"op": "add", "path": "/metadata/annotations", "value": {**annotations, "arcia.io/owner": owner}}]
    if patch_resource("pvc", pvc_name, claim, "json") or patch_resource("deployment", name, patch, "strategic"):
        raise RuntimeError("Association du Power User non appliquée ; activation refusée")
    runner.apply_manifest(json.dumps({"apiVersion": "v1", "kind": "Service", "metadata": {"name": name, "namespace": namespace},
                                     "spec": {"selector": {"app": name}, "ports": [
                                         {"name": "studio", "port": 9119, "targetPort": 9119},
                                         {"name": "gateway", "port": 8642, "targetPort": 8642},
                                         {"name": "files", "port": 8643, "targetPort": 8643}]}}))
    # Règles dédiées, sans ouvrir 8643 à un pod d'un autre utilisateur.
    policy = {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": name + "-files", "namespace": namespace},
              "spec": {"podSelector": {"matchLabels": {"app": name}}, "policyTypes": ["Ingress"],
                       "ingress": [{"from": [{"podSelector": {"matchLabels": {"app": "open-webui"}}}],
                                    "ports": [{"protocol": "TCP", "port": 8643}]}]}}
    runner.apply_manifest(json.dumps(policy))
    rc, _, _ = runner.run(["rollout", "status", "deployment/" + name, "-n", namespace, "--timeout=360s"], timeout=380)
    if rc != 0:
        raise RuntimeError("Relais du Power User indisponible ; activation du portail refusée")
    return {"runtime": runtime_for(identity), "namespace": namespace, "key": key, "service": name, "poweruser_slug": slug}
