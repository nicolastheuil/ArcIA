"""Qualification synthétique : identité serveur, fichiers privés et pod Power User conservé."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from unittest.mock import AsyncMock

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from fastapi import FastAPI, Header, HTTPException
import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy
import hermes_files as provision
from services.hermes.files import Store, create_app, frame, relay_sse, RETENTION
from services.open_webui import arcia_hermes_files as portal
from services.open_webui.provision_model_access import reconcile as reconcile_model_access


def binding(identity, poweruser=None):
    runtime = provision.runtime_for(identity)
    value = {"runtime": runtime, "namespace": "synthetic", "key": "synthetic-key-" + identity + "-" * 32,
             "service": "hermes-files-" + runtime}
    if poweruser:
        value.update(service="hermes-poweruser-" + poweruser, poweruser_slug=poweruser)
    return value


class StoreTests(unittest.TestCase):
    def test_exact_bytes_and_cross_user_id_denied_even_when_known(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inbox = root / "inbox"
            inbox.mkdir()
            original = b"PK\x03\x04synthetic-office-file\x00\xff"
            (inbox / "rapport.xlsx").write_bytes(original)
            alice, bob = Store(root / "alice"), Store(root / "bob")
            links = alice.publish(inbox)
            artifact = re.search(r"hermes-files/([a-f0-9]{32})", links)[1]
            self.assertEqual(alice.read(artifact), ("rapport.xlsx", original))
            with self.assertRaises(web.HTTPNotFound):
                bob.read(artifact)
            for path in ("../alice", "/etc/passwd", artifact + ".blob", "%2e%2e"):
                with self.assertRaises(web.HTTPNotFound):
                    alice.read(path)

    def test_expired_and_modified_files_are_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inbox = root / "inbox"
            inbox.mkdir()
            (inbox / "result.txt").write_bytes(b"synthetic")
            store = Store(root / "published")
            artifact = re.search(r"hermes-files/([a-f0-9]{32})", store.publish(inbox))[1]
            blob = store.root / (artifact + ".blob")
            blob.write_bytes(b"tampered")
            with self.assertRaises(web.HTTPNotFound):
                store.read(artifact)
            record = store.root / (artifact + ".json")
            os.utime(record, (time.time() - RETENTION - 1,) * 2)
            with self.assertRaises(web.HTTPNotFound):
                store.read(artifact)
            store.prune()
            self.assertFalse(blob.exists())
            self.assertFalse(record.exists())

    def test_hardlinks_hidden_files_and_oversize_are_not_published(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inbox = root / "inbox"
            inbox.mkdir()
            (root / "private.txt").write_bytes(b"private synthetic")
            os.link(root / "private.txt", inbox / "hardlink.txt")
            (inbox / ".hidden").write_bytes(b"hidden")
            (inbox / "large.txt").write_bytes(b"too large")
            with patch("services.hermes.files.MAX_BYTES", 3):
                self.assertEqual(Store(root / "published").publish(inbox), "")


class BindingTests(unittest.TestCase):
    def test_binding_is_derived_from_verified_user_with_no_admin_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bindings.json"
            path.write_text(json.dumps({"alice": binding("alice"), "bob": binding("bob", "expert")}), encoding="utf-8")
            self.assertIn("hermes-poweruser-expert", portal.binding_for("bob", path)[1])
            self.assertIn(provision.runtime_for("alice"), portal.binding_for("alice", path)[1])
            for user in ("unbound", "admin", ""):
                with self.assertRaises(HTTPException) as error:
                    portal.binding_for(user, path)
                self.assertEqual(error.exception.status_code, 403)
            values = {"alice": binding("alice", "expert"), "bob": binding("bob", "expert")}
            path.write_text(json.dumps(values), encoding="utf-8")
            with self.assertRaises(HTTPException):
                portal.binding_for("alice", path)

    def test_forged_runtime_host_and_corrupt_bindings_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bindings.json"
            for field, value in (("namespace", "evil/../../"), ("runtime", provision.runtime_for("bob")),
                                 ("service", "169.254.169.254"), ("key", "")):
                record = binding("alice")
                record[field] = value
                path.write_text(json.dumps({"alice": record}), encoding="utf-8")
                with self.assertRaises(HTTPException):
                    portal.binding_for("alice", path)
            path.write_text("broken", encoding="utf-8")
            with self.assertRaises(HTTPException):
                portal.binding_for("alice", path)

    def test_duplicate_users_pods_and_inference_keys_refused_before_mutation(self):
        for users in ([{"webui_user_id": "alice", "poweruser_slug": "expert"}, {"webui_user_id": "bob", "poweruser_slug": "expert"}],
                      [{"webui_user_id": "alice", "inference_secret": "litellm-secret"}],
                      [{"webui_user_id": "alice", "inference_secret": "same"}, {"webui_user_id": "bob", "inference_secret": "same"}]):
            with self.assertRaises(ValueError):
                provision.declared_users({"hermes_workspaces": {"users": users}})


class FlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bindings = {"alice": binding("alice"), "bob": binding("bob", "expert")}
        path = self.root / "bindings.json"
        path.write_text(json.dumps(self.bindings), encoding="utf-8")
        self.env = patch.dict(os.environ, {"ARCIA_HERMES_FILES_ENABLED": "true", "ARCIA_HERMES_FILES_KEY": "portal-internal-key",
                                           "ARCIA_HERMES_FILES_BINDINGS": str(path)})
        self.env.start()
        self.clients = {}
        self.upstreams = []
        self.calls = []
        for identity in self.bindings:
            upstream = web.Application()

            async def health(request):
                return web.json_response({"ok": True})

            async def chat(request, identity=identity):
                body = await request.json()
                self.calls.append((identity, body, dict(request.headers)))
                prompt = body["messages"][-1]["content"]
                output = re.search(r"directement dans (.+?)\. Pas de sous-dossiers", prompt)[1]
                self.assertRegex(Path(output).name, r"^[a-p]{32}$")
                (Path(output) / "rapport.xlsx").write_bytes(b"synthetic-file-of-" + identity.encode())
                event = {"id": "synthetic", "object": "chat.completion.chunk", "model": body["model"],
                         "choices": [{"index": 0, "delta": {"content": "Rapport généré"}, "finish_reason": None}]}
                if body.get("stream"):
                    response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
                    await response.prepare(request)
                    await response.write(frame(event))
                    event["choices"][0] = {"index": 0, "delta": {}, "finish_reason": "stop"}
                    await response.write(frame(event))
                    await response.write(b"data: [DONE]\n\n")
                    await response.write_eof()
                    return response
                return web.json_response({"choices": [{"message": {"content": "Rapport généré"}, "finish_reason": "stop"}]})
            upstream.router.add_get("/health", health)
            upstream.router.add_post("/v1/chat/completions", chat)
            server = TestServer(upstream)
            await server.start_server()
            self.upstreams.append(server)
            client = TestClient(TestServer(create_app(self.root / identity, self.bindings[identity]["key"], str(server.make_url("")).rstrip("/"))))
            await client.start_server()
            self.clients[identity] = client

        app = FastAPI()
        # Même obstacle que le backend réel : un montage SPA final sur /.
        from fastapi.responses import PlainTextResponse
        from starlette.applications import Starlette
        from starlette.routing import Route
        app.mount("/", Starlette(routes=[Route("/{path:path}", lambda request: PlainTextResponse("SPA", status_code=404))]))

        async def user(x_test_user: str = Header(default="")):
            if not x_test_user:
                raise HTTPException(401)
            return SimpleNamespace(id=x_test_user, role="admin" if x_test_user == "admin" else "user")
        fake_openai = SimpleNamespace()

        async def native_headers(*args, **kwargs):
            return {"X-ArcIA-User": "bob", "Authorization": "forged"}, {"token": "not-forwarded"}
        fake_openai.get_headers_and_cookies = native_headers
        module = ModuleType("open_webui.routers")
        module.openai = fake_openai
        with patch.dict(sys.modules, {"open_webui.routers": module}):
            portal.install(app, user)
        self.native = fake_openai
        actual_binding = portal.binding_for

        def local_binding(identity, path):
            record, _ = actual_binding(identity, path)
            return record, str(self.clients[identity].make_url("")).rstrip("/")
        self.resolve = patch.object(portal, "binding_for", side_effect=local_binding)
        self.resolve.start()
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://synthetic")

    async def asyncTearDown(self):
        await self.http.aclose()
        self.resolve.stop()
        self.env.stop()
        for client in self.clients.values():
            await client.close()
        for server in self.upstreams:
            await server.close()
        self.temp.cleanup()

    async def generate(self, identity, stream=False):
        headers, cookies = await self.native.get_headers_and_cookies(None, portal.LOCAL_BASE,
                metadata={"chat_id": "same-chat"}, user=SimpleNamespace(id=identity))
        self.assertEqual(cookies, {})
        return await self.http.post("/api/v1/arcia/hermes/v1/chat/completions", headers=headers,
                                    json={"model": "agentic/auto", "stream": stream,
                                          "session_id": "forged-other-session", "user": "bob",
                                          "messages": [{"role": "user", "content": "synthetic report"}]})

    async def test_end_to_end_known_link_cannot_be_downloaded_by_other_user_or_admin(self):
        result = await self.generate("alice")
        self.assertEqual(result.status_code, 200, result.text)
        link = re.search(r"\]\((/api/v1/arcia/hermes-files/[a-f0-9]{32})\)", result.text)[1]
        for identity, status in (("alice", 200), ("bob", 404), ("admin", 403), ("", 401)):
            response = await self.http.get(link, headers={"X-Test-User": identity})
            self.assertEqual(response.status_code, status, response.text)
            if identity == "alice":
                self.assertEqual(response.content, b"synthetic-file-of-alice")
                self.assertEqual(response.headers["cache-control"], "private, no-store")
                self.assertTrue(response.headers["content-disposition"].startswith("attachment"))
        self.assertNotIn("session_id", self.calls[0][1])
        self.assertNotIn("user", self.calls[0][1])

    async def test_streaming_and_private_session_continuity(self):
        results = await asyncio.gather(self.generate("alice", True), self.generate("bob", True))
        for result in results:
            self.assertEqual(result.status_code, 200, result.text)
            text = result.text
            self.assertIn("Fichiers à télécharger", text)
            self.assertLess(text.index("hermes-files/"), text.index('"finish_reason": "stop"'))
            self.assertEqual(text.count("data: [DONE]"), 1)
        keys = {identity: headers["X-Hermes-Session-Key"] for identity, _, headers in self.calls}
        self.assertNotEqual(keys["alice"], keys["bob"])

    async def test_direct_internal_request_and_backend_without_key_refused(self):
        result = await self.http.post("/api/v1/arcia/hermes/v1/chat/completions", headers={"X-ArcIA-User": "alice"}, json={})
        self.assertEqual(result.status_code, 401)
        response = await self.clients["alice"].get("/files/" + "a" * 32)
        self.assertEqual(response.status, 401)
        result = await self.generate("unbound")
        self.assertEqual(result.status_code, 403)
        self.assertEqual(self.calls, [])

    async def test_stream_keepalive_does_not_cancel_a_successful_publication(self):
        async def chunks():
            for data in (b"data: null\n\n", b'event: approval.request\ndata: {"choices": ["once", "deny"]}\n\n', frame({"choices": None}), frame({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}), b"data: [DONE]\n\n"):
                yield data
        async def publish():
            return "synthetic-link"
        result = b"".join([part async for part in relay_sse(chunks(), publish)])
        self.assertIn(b"synthetic-link", result)

    async def test_incomplete_or_error_stream_never_publishes(self):
        async def chunks(data):
            for line in data.splitlines(keepends=True):
                yield line
        for data in (frame({"choices": []}), frame({"error": {"message": "failed"}}) + b"data: [DONE]\n\n",
                     b"data: null\n\ndata: [DONE]\n\n", frame({"choices": [None]}) + b"data: [DONE]\n\n",
                     frame({"choices": None}) + b"data: [DONE]\n\n"):
            called = []
            async def publish():
                called.append(True)
                return "bad link"
            output = b"".join([chunk async for chunk in relay_sse(chunks(data), publish)])
            self.assertEqual(called, [])
            self.assertNotIn(b"bad link", output)


class NativeModelAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_grants_use_declared_ids_without_overwriting_existing_model(self):
        users = SimpleNamespace(get_super_admin_user=AsyncMock(return_value=SimpleNamespace(id="admin")),
                                get_user_by_id=AsyncMock(return_value=SimpleNamespace(role="user")))
        models = SimpleNamespace(get_model_by_id=AsyncMock(return_value=SimpleNamespace(params={"system": "existing"})),
                                 insert_new_model=AsyncMock())
        grants = SimpleNamespace(grant_access=AsyncMock(return_value=object()))
        result = await reconcile_model_access({"user_ids": ["alice", "bob"], "model_ids": ["agentic/auto"]},
                                              users, models, dict, grants)
        models.insert_new_model.assert_not_called()
        self.assertEqual(result["granted"], 2)
        self.assertEqual([call.args for call in grants.grant_access.call_args_list],
                         [("model", "agentic/auto", "user", "alice", "read"),
                          ("model", "agentic/auto", "user", "bob", "read")])

    async def test_pending_account_is_not_given_model_access(self):
        users = SimpleNamespace(get_super_admin_user=AsyncMock(return_value=SimpleNamespace(id="admin")),
                                get_user_by_id=AsyncMock(return_value=SimpleNamespace(role="pending")))
        models, grants = SimpleNamespace(), SimpleNamespace(grant_access=AsyncMock())
        with self.assertRaises(ValueError):
            await reconcile_model_access({"user_ids": ["pending"], "model_ids": ["agentic/auto"]}, users, models, dict, grants)
        grants.grant_access.assert_not_called()


class ProvisionTests(unittest.TestCase):
    def test_existing_profile_is_kept_when_legacy_initializer_restarts(self):
        pod = {"initContainers": [{"name": "init-user-state", "command": ["sh", "-c", "cp initial.yaml /opt/data/config.yaml"]}]}
        first = provision.preserve_initializers(pod)
        self.assertIn("if [ -f /opt/data/config.yaml ]; then exit 0; fi", first[0]["command"][2])
        self.assertEqual(provision.preserve_initializers({"initContainers": first}), first)
        with self.assertRaises(RuntimeError):
            provision.preserve_initializers({"initContainers": [{"name": "init-user-state", "command": ["unknown-bootstrap"]}]})

    def test_model_sync_does_not_reapply_a_bound_poweruser(self):
        from unittest.mock import Mock
        import arcia_poweruser
        cfg = {"hermes_workspaces": {"users": [{"webui_user_id": "alice", "poweruser_slug": "expert"}]}}
        runner = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps({"items": [{"metadata": {"name": "hermes-poweruser-expert"}}]})))
        with patch.object(arcia_poweruser, "load_arcia_config", return_value=cfg), patch.object(arcia_poweruser, "sync_single_user") as sync:
            self.assertEqual(arcia_poweruser.sync_all_powerusers(runner_func=runner), 0)
        sync.assert_not_called()

    def test_ci_fixture_cannot_deploy_or_touch_cluster(self):
        cfg = deploy.parse_yaml_or_env(str(ROOT / "tests/fixtures/deploy.synthetic.yaml"))
        with patch.object(deploy, "K8sRunner") as runner:
            with self.assertRaisesRegex(ValueError, "fixture synthétique"):
                deploy.deploy_arcia(cfg, str(ROOT))
            runner.assert_not_called()
    def test_private_template_has_no_ingress_service_account_or_other_volume(self):
        text = (ROOT / "deploy/manifests/templates/hermes-files.template.yaml").read_text(encoding="utf-8")
        for key, value in {"NAME": "hermes-files-synthetic", "NAMESPACE": "synthetic", "IMAGE": "image:v1.0.0",
                           "OWNER": "synthetic", "INFERENCE_SECRET": "synthetic-key", "CODE_REVISION": "code", "CONFIG_REVISION": "cfg"}.items():
            text = text.replace("{{" + key + "}}", value)
        documents = list(yaml.safe_load_all(text))
        pod = documents[1]["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(documents[1]["spec"]["strategy"]["type"], "Recreate")
        self.assertEqual([p["port"] for p in documents[2]["spec"]["ports"]], [8643])
        self.assertFalse(any(d["kind"] == "Ingress" for d in documents))
        claims = [v["persistentVolumeClaim"]["claimName"] for v in pod["volumes"] if "persistentVolumeClaim" in v]
        self.assertEqual(claims, ["hermes-files-synthetic"])
        self.assertTrue(all(c["securityContext"]["capabilities"]["drop"] == ["ALL"] for c in pod["containers"]))

    def test_poweruser_patch_preserves_actual_hermes_container_and_personalization(self):
        from copy import deepcopy
        existing = {"name": "hermes", "image": "nousresearch/hermes-agent:v0.22.2", "command": ["custom-existing-launch"],
                    "env": [{"name": "HERMES_HOME", "value": "/opt/data"}, {"name": "CUSTOM_SOUL", "value": "synthetic-personalization"}, {"name": "PYTHONPATH", "value": "/custom-agent-code"}],
                    "volumeMounts": [{"name": "user-data", "mountPath": "/opt/data"}]}
        original = deepcopy(existing)
        deployment = {"spec": {"template": {"spec": {"containers": [existing], "volumes": [
            {"name": "user-data", "persistentVolumeClaim": {"claimName": "hermes-user-expert-pvc"}}]}}}}
        class Runner:
            mode = "local"
            def __init__(self): self.patches, self.manifests = [], []
            def run(self, args, **kwargs):
                if args[:2] == ["get", "deployment"]:
                    return 0, json.dumps(deployment), ""
                if args[:2] == ["get", "pvc"]:
                    return 0, json.dumps({"metadata": {"resourceVersion": "1"}}), ""
                if args[0] == "patch":
                    path = next(a.split("=", 1)[1] for a in args if a.startswith("--patch-file="))
                    self.patches.append((args[1], json.loads(Path(path).read_text())))
                return 0, "", ""
            def apply_manifest(self, manifest): self.manifests.append(json.loads(manifest))
        runner = Runner()
        with patch.object(provision, "existing_secret", return_value="synthetic-existing-key-" + "x" * 30):
            result = provision.attach_poweruser({"webui_user_id": "alice", "poweruser_slug": "expert"}, runner, "synthetic", ROOT)
        self.assertEqual(existing, original)
        changes = next(p for resource, p in runner.patches if resource == "deployment")
        self.assertEqual([c["name"] for c in changes["spec"]["template"]["spec"]["containers"]], ["hermes", "arcia-files"])
        guarded = changes["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(guarded["command"][2:], original["command"])
        self.assertEqual(changes["spec"]["strategy"], {"type": "Recreate", "rollingUpdate": None})
        self.assertEqual(next(e["value"] for e in guarded["env"] if e["name"] == "PYTHONPATH"), "/opt/arcia-governance:/custom-agent-code")
        self.assertNotIn("image", guarded)
        self.assertNotIn("initContainers", changes["spec"]["template"]["spec"])
        self.assertEqual(result["service"], "hermes-poweruser-expert")
        self.assertFalse(any(m["kind"] in ("Secret", "PersistentVolumeClaim", "ConfigMap") for m in runner.manifests))

    def test_webui_always_routes_agentic_to_authenticated_private_router(self):
        text = (ROOT / "deploy/manifests/07-open-webui.yaml").read_text(encoding="utf-8")
        rendered = deploy.render_model_manifest("open-webui", text, {}, "synthetic")
        self.assertIn(portal.LOCAL_BASE, rendered)
        self.assertNotIn("http://hermes-studio.synthetic.svc:8642/v1", rendered)


if __name__ == "__main__":
    unittest.main()
