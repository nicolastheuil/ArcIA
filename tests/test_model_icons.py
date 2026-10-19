"""Classification et projection d'icônes sans backend ou modèle privé."""
import importlib.util
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch
from services.open_webui.branding import projected_icon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy


class TestModelIcons(unittest.TestCase):
    def test_launcher_imports_backend_from_image_working_directory(self):
        import os
        import shutil
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            adapter = Path(directory) / "adapter"
            backend = Path(directory) / "backend"
            adapter.mkdir()
            (backend / "open_webui").mkdir(parents=True)
            (backend / "open_webui" / "__init__.py").write_text('marker = "synthetic-backend"', encoding="utf-8")
            (adapter / "uvicorn.py").write_text(
                'def run(*args, **kwargs):\n    import open_webui\n    assert open_webui.marker == "synthetic-backend"\n', encoding="utf-8")
            shutil.copyfile(ROOT / "services/open_webui/start.py", adapter / "start.py")
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            env["WEBUI_SECRET_KEY"] = "synthetic-session-key"
            result = subprocess.run([sys.executable, str(adapter / "start.py")], cwd=backend,
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_icon_ids_use_the_same_normalization_as_the_catalogue(self):
        cfg = {"llm_gateway": {"models_routing": [
            {"alias": " synthetic-chat ", "target_model": "openrouter/auto", "zdr": False}
        ]}}
        self.assertEqual(set(deploy.compute_models_branding_dict(cfg)["models"]), {"synthetic-chat"})

    def test_false_string_never_gets_a_zdr_badge(self):
        cfg = {"llm_gateway": {"models_routing": [
            {"alias": "synthetic-chat", "target_model": "openai/synthetic", "provider": "openai", "zdr": "false"}
        ]}}
        result = deploy.compute_models_branding_dict(cfg)
        self.assertEqual(result["models"]["synthetic-chat"]["type"], "default")

    def test_hosting_and_not_name_controls_local_icon(self):
        cfg = {"llm_gateway": {"models_routing": [
            {"alias": "synthetic-local-word", "target_model": "openai/local-model", "provider": "custom", "hosting": "cloud", "zdr": False},
            {"alias": "synthetic-private", "target_model": "openai/model", "provider": "custom", "hosting": "local", "zdr": True}
        ]}}
        result = deploy.compute_models_branding_dict(cfg)["models"]
        self.assertEqual(result["synthetic-local-word"]["type"], "default")
        self.assertEqual(result["synthetic-private"]["type"], "local")

    def test_missing_zdr_is_normal_and_mapping_has_only_declared_ids(self):
        cfg = {"llm_gateway": {"models_routing": [
            {"alias": "synthetic-chat", "target_model": "openrouter/model", "provider": "openrouter"}
        ]}}
        result = deploy.compute_models_branding_dict(cfg)["models"]
        self.assertEqual(set(result), {"synthetic-chat"})
        self.assertEqual(result["synthetic-chat"]["type"], "default")


    def test_projection_rejects_hidden_models_and_untrusted_paths(self):
        mapping = {"models": {"synthetic": {"icon": "/static/icon-model-local.svg"}}}
        self.assertIsNone(projected_icon("synthetic", mapping, set()))
        self.assertIsNone(projected_icon("unknown", mapping, {"unknown"}))
        self.assertEqual(projected_icon("synthetic", mapping, {"synthetic"}), "/static/icon-model-local.svg")
        mapping["models"]["synthetic"]["icon"] = "https://example.invalid/untrusted.svg"
        self.assertIsNone(projected_icon("synthetic", mapping, {"synthetic"}))

    def test_session_key_is_preserved_on_restart(self):
        spec = importlib.util.spec_from_file_location("arcia_webui_start", ROOT / "services" / "open_webui" / "start.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        from types import SimpleNamespace
        import os
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.key"
            path.write_text("synthetic-existing-session-key", encoding="utf-8")
            with patch.dict(os.environ, {"WEBUI_SECRET_KEY": "", "WEBUI_SECRET_KEY_FILE": str(path)}), patch.dict(sys.modules, {"uvicorn": SimpleNamespace(run=lambda *a, **k: None)}):
                module.main()
                self.assertEqual(path.read_text(encoding="utf-8"), "synthetic-existing-session-key")
                self.assertEqual(os.environ["WEBUI_SECRET_KEY"], "synthetic-existing-session-key")

    def test_sync_does_not_modify_public_mapping_and_hashes_all_assets(self):
        class Runner:
            def __init__(self): self.applied = []
            def apply_manifest(self, value): self.applied.append(value)
        path = ROOT / "assets" / "branding" / "models-branding.json"
        before = path.read_bytes()
        runner = Runner()
        first = deploy.sync_webui_branding(runner, "synthetic", str(ROOT), cfg={"llm_gateway": {"models_routing": []}})
        second = deploy.sync_webui_branding(Runner(), "synthetic", str(ROOT), cfg={"llm_gateway": {"models_routing": []}})
        self.assertEqual(first["revision"], second["revision"])
        self.assertFalse(first["mapping"]["models"])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(first["asset_hashes"]), 3)
        self.assertIn("arcia-webui-code", runner.applied[1])
        import io
        real_open = open
        def changed_svg(path, *args, **kwargs):
            if str(path).endswith("icon-model-default.svg"):
                return io.StringIO((ROOT / "assets" / "branding" / "icon-model-default.svg").read_text(encoding="utf-8") + "\n<!-- synthetic change -->\n")
            return real_open(path, *args, **kwargs)
        with patch("deploy.open", side_effect=changed_svg, create=True):
            changed = deploy.sync_webui_branding(Runner(), "synthetic", str(ROOT), cfg={"llm_gateway": {"models_routing": []}})
        self.assertNotEqual(first["mapping"]["revision"], changed["mapping"]["revision"])
        self.assertNotEqual(first["revision"], changed["revision"])

    def test_activation_is_targeted_and_reports_rollout_failure(self):
        import json
        class Runner:
            def __init__(self): self.calls = []
            def run(self, args, stdin_input=None, **kwargs):
                self.calls.append((args, stdin_input))
                return (1 if args[0] == "rollout" else 0), "", ""
        runner = Runner()
        result = deploy.activate_webui_branding(runner, "synthetic", {"revision": "synthetic"})
        self.assertFalse(result["runtime_loaded"])
        patch_data = json.loads(runner.calls[0][1])
        container = patch_data["spec"]["template"]["spec"]["containers"][0]
        self.assertNotIn("env", container)
        self.assertEqual(container["volumeMounts"][0]["$patch"], "delete")


class TestNativeAvatarAdapter(unittest.TestCase):
    def test_adapter_preserves_native_fallback_and_calls_native_access_filter(self):
        import asyncio
        import json
        import os
        from types import SimpleNamespace, ModuleType
        from unittest.mock import AsyncMock
        async def native(request, id, user, db):
            return "native-fallback"
        class Route:
            def __init__(self, path, endpoint, **kwargs):
                self.path, self.endpoint = path, endpoint
        path = "/api/v1/models/model/profile/image"
        app = SimpleNamespace(router=SimpleNamespace(routes=[Route(path, native)]))
        get_models = AsyncMock(return_value=[{"id": "synthetic with spaces"}])
        filtered = AsyncMock(return_value=[{"id": "synthetic with spaces"}])
        modules = {}
        for name, values in {
            "fastapi": {"Depends": lambda value: value, "Request": object},
            "fastapi.responses": {"RedirectResponse": lambda url, headers: {"url": url, "headers": headers}},
            "fastapi.routing": {"APIRoute": Route},
            "open_webui.main": {"app": app},
            "open_webui.internal.db": {"get_async_session": object},
            "open_webui.utils.auth": {"get_verified_user": object},
            "open_webui.utils.models": {"get_all_models": get_models, "get_filtered_models": filtered},
            "branding": {"projected_icon": projected_icon},
        }.items():
            module = ModuleType(name)
            module.__dict__.update(values)
            modules[name] = module
        with tempfile.TemporaryDirectory() as directory:
            mapping_file = Path(directory) / "mapping.json"
            mapping_file.write_text(json.dumps({"models": {"synthetic with spaces": {"icon": "/static/icon-model-zdr.svg"}}}), encoding="utf-8")
            with patch.dict(sys.modules, modules), patch.dict(os.environ, {"ARCIA_MODEL_BRANDING_FILE": str(mapping_file)}):
                spec = importlib.util.spec_from_file_location("arcia_test_adapter", ROOT / "services" / "open_webui" / "arcia_webui.py")
                adapter = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(adapter)
                user = SimpleNamespace(role="user")
                result = asyncio.run(adapter.model_image(object(), "synthetic with spaces", user, "synthetic-db"))
                self.assertTrue(result["url"].startswith("/static/icon-model-zdr.svg?v="))
                self.assertEqual(result["headers"]["Cache-Control"], "no-store")
                self.assertEqual(filtered.call_args.kwargs["db"], "synthetic-db")
                filtered.return_value = []
                self.assertEqual(asyncio.run(adapter.model_image(object(), "synthetic with spaces", user, "synthetic-db")), "native-fallback")
                mapping_file.unlink()
                self.assertEqual(asyncio.run(adapter.model_image(object(), "synthetic with spaces", user, "synthetic-db")), "native-fallback")


if __name__ == "__main__":
    unittest.main()
